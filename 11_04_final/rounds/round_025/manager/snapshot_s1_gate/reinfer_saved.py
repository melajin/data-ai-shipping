"""Sequential one-model-at-a-time reinference verification for Round024 FIT gate."""
from __future__ import annotations

import datetime as dt
import gc
import hashlib
import json
import os
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[3]
ROUND = Path(__file__).resolve().parents[1]
DEFAULT_FOLD0_NPZ = Path(
    r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_0_features.npz"
)
T5_START, T5_STOP = 156, 166


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> int:
    gate_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (ROUND / "artifacts" / "gate").resolve()
    if ROUND.name != "round_025" or gate_dir != (ROUND / "artifacts" / "gate").resolve():
        raise SystemExit("reinference input must be rounds/round_024/artifacts/gate")
    mem = psutil.virtual_memory()
    if mem.available < int(1.0 * 2**30):
        raise MemoryError("Available RAM below 1.0 GiB for sequential model reinference")
    import joblib
    import numpy as np

    result = json.loads((gate_dir / "gate_result.json").read_text(encoding="utf-8"))
    expected_input_hash = result.get("input_hashes", {}).get("fold0_features_npz")
    actual_input_hash = sha256(DEFAULT_FOLD0_NPZ)
    if not expected_input_hash or actual_input_hash.lower() != expected_input_hash.lower():
        raise ValueError("read-only fold0 feature input hash differs from the gate record")
    with np.load(DEFAULT_FOLD0_NPZ, allow_pickle=False) as bundle:
        roles = bundle["roles"].astype(str)
        source_rows = len(roles)
        X_all = bundle["X"]
        y_all = bundle["y"]
        if X_all.shape[0] != source_rows or y_all.shape != (source_rows,):
            raise ValueError("read-only fold0 source arrays have inconsistent row counts")
        fit_mask = roles == "FIT"
        X_fit = np.asarray(X_all[fit_mask], copy=True)
        y_fit = np.asarray(y_all[fit_mask], dtype=np.int64, copy=True)
        del X_all, y_all
    if X_fit.shape != (3144, 304) or y_fit.shape != (3144,):
        raise ValueError("read-only fold0 input does not contain the expected exact FIT feature matrix")
    if np.any((y_fit < 0) | (y_fit > 3)):
        raise ValueError("FIT labels fall outside the frozen four-class order")
    del roles, fit_mask
    gc.collect()

    saved_preds = {}
    for variant in ("baseline", "candidate"):
        with np.load(gate_dir / f"predictions_{variant}.npz", allow_pickle=False) as z:
            saved_preds[variant] = {
                "row_index": np.asarray(z["row_index"], dtype=np.int64),
                "y_true": np.asarray(z["y_true"], dtype=np.int64),
                "y_pred": np.asarray(z["y_pred"], dtype=np.int64),
                "proba": np.asarray(z["proba"], dtype=np.float32),
            }
        if (not np.array_equal(saved_preds[variant]["row_index"], np.arange(3144))
                or not np.array_equal(saved_preds[variant]["y_true"], y_fit)):
            raise ValueError(f"{variant}: saved FIT row/label order differs from the hash-verified source")

    records_by_key = {(int(r["fold"]), r["variant"]): r for r in result.get("fit_records", [])}
    if len(records_by_key) != 8 or set(records_by_key) != {
            (fold, variant) for fold in range(4) for variant in ("baseline", "candidate")
    }:
        raise ValueError("gate record must contain exactly one baseline and candidate model per fold")
    errors: list[str] = []
    fold_checks: list[dict] = []
    all_valid: list[int] = []
    max_abs_diff_overall = 0.0

    for fold in range(4):
        ev_path = gate_dir / "feature_evidence" / f"fold_{fold}_features.npz"
        with np.load(ev_path, allow_pickle=False) as ev:
            tr = np.asarray(ev["train_indices"], dtype=np.int64)
            va = np.asarray(ev["valid_indices"], dtype=np.int64)
            ty = np.asarray(ev["train_labels"], dtype=np.int64)
            t5 = np.asarray(ev["t5_matrix"])
            s1 = np.asarray(ev["s1_matrix"])
        if len(tr) + len(va) != 3144 or (set(tr.tolist()) & set(va.tolist())):
            errors.append(f"fold {fold}: invalid split")
        if not np.array_equal(ty, y_fit[tr]):
            errors.append(f"fold {fold}: train labels mismatch")
        all_valid.extend(va.tolist())

        X_base_va = X_fit[va].copy()
        X_base_va[:, T5_START:T5_STOP] = t5[va].astype(X_base_va.dtype, copy=False)
        X_cand_va = np.concatenate((X_base_va, s1[va]), axis=1)

        for variant, X_va, expected_cols in (("baseline", X_base_va, 304), ("candidate", X_cand_va, 328)):
            rec = records_by_key.get((fold, variant))
            if not rec:
                errors.append(f"fold {fold} {variant}: missing fit_record")
                continue
            model_path = (ROOT / rec["model_path"]).resolve()
            if not model_path.is_relative_to(ROUND) or not model_path.is_file():
                errors.append(f"fold {fold} {variant}: model path is outside round024 or missing")
                continue
            actual_sha = sha256(model_path)
            if actual_sha.lower() != rec["model_sha256"].lower():
                errors.append(f"fold {fold} {variant}: model sha256 mismatch")
            model = joblib.load(model_path)
            classes = np.asarray(getattr(model, "classes_", []))
            if not np.array_equal(classes, np.arange(4)):
                errors.append(f"fold {fold} {variant}: class order mismatch")
            proba = np.asarray(model.predict_proba(X_va), dtype=np.float32)
            pred = np.argmax(proba, axis=1).astype(np.int64)
            del model
            gc.collect()

            saved_p = saved_preds[variant]["proba"][va]
            saved_y = saved_preds[variant]["y_pred"][va]
            max_diff = float(np.max(np.abs(proba - saved_p)))
            max_abs_diff_overall = max(max_abs_diff_overall, max_diff)
            argmax_match = bool(np.array_equal(pred, saved_y))
            if max_diff > 1e-7:
                errors.append(f"fold {fold} {variant}: max probability diff {max_diff} > 1e-7")
            if not argmax_match:
                errors.append(f"fold {fold} {variant}: argmax mismatch")
            fold_checks.append({
                "fold": fold,
                "variant": variant,
                "validation_rows": int(len(va)),
                "feature_columns": int(expected_cols),
                "model_sha256_match": actual_sha.lower() == rec["model_sha256"].lower(),
                "max_abs_proba_diff": max_diff,
                "argmax_exact_match": argmax_match,
            })
        del X_base_va, X_cand_va, t5, s1
        gc.collect()

    if sorted(all_valid) != list(range(3144)):
        errors.append("validation indices across 4 folds do not form an exact partition of 0..3143")

    out_report = {
        "status": "pass" if not errors else "fail",
        "verified_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fold0_feature_input_sha256_match": True,
        "fit_rows_used": 3144,
        "models_reloaded_and_reinferred": len(fold_checks),
        "max_abs_proba_diff": max_abs_diff_overall,
        "tolerance": 1e-7,
        "validation_partition_complete": sorted(all_valid) == list(range(3144)),
        "fold_checks": fold_checks,
        "errors": errors,
    }
    out_path = ROUND / "review" / "saved_output_verification.json"
    out_path.write_text(json.dumps(out_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out_report["status"], "models": len(fold_checks), "max_abs_proba_diff": max_abs_diff_overall, "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
