"""Independent, read-only consistency check for the Round022 FIT gate outputs.

Usage: python verify_gate_result.py <round022/artifacts/gate>
The checker reads private saved arrays but only emits aggregate pass/fail
metadata; never prints labels, predictions, IDs, or feature values.
"""
from __future__ import annotations

import hashlib
import json
import sys
import datetime as dt
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    cm = np.zeros((4, 4), dtype=np.int64)
    for actual, predicted in zip(y_true, y_pred):
        cm[int(actual), int(predicted)] += 1
    support = cm.sum(axis=1)
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = support - tp
    precision = np.divide(tp, tp + fp, out=np.zeros(4, dtype=np.float64), where=(tp + fp) != 0)
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support != 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(4, dtype=np.float64), where=(precision + recall) != 0)
    return {"n": int(len(y_true)), "correct": int(tp.sum()), "support": support.tolist(),
            "confusion": cm.tolist(), "class_f1": f1.tolist(), "macro_f1": float(f1.mean()),
            "micro_f1": float(tp.sum() / len(y_true))}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_gate_result.py <gate-output-dir>")
    out = Path(sys.argv[1]).resolve()
    root = out.parents[3]
    round_dir = root / "rounds" / "round_022"
    import psutil
    memory = psutil.virtual_memory()
    other_python = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            if info["pid"] != __import__("os").getpid() and "python" in (info.get("name") or "").lower():
                other_python.append({"pid": int(info["pid"]), "name": info.get("name"),
                                     "rss_bytes": int(info["memory_info"].rss)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    resource_snapshot = {"timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                         "available_bytes": int(memory.available),
                         "expected_peak_bytes": 512 * 2**20,
                         "minimum_free_bytes": 1 * 2**30,
                         "other_python_processes": other_python}
    (round_dir / "review" / "gate_verification_resources.json").write_text(
        json.dumps(resource_snapshot, indent=2) + "\n", encoding="utf-8")
    result = json.loads((out / "gate_result.json").read_text(encoding="utf-8"))
    progress = json.loads((out / "fit_progress.json").read_text(encoding="utf-8"))
    approval = json.loads((round_dir / "review" / "gate_approved_sources.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    recomputed: dict[str, dict] = {}
    arrays: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    all_y_pred: dict[str, np.ndarray] = {}
    for variant in ("baseline", "candidate"):
        path = out / f"predictions_{variant}.npz"
        with np.load(path, allow_pickle=False) as z:
            row_index = np.asarray(z["row_index"], dtype=np.int64)
            y_true = np.asarray(z["y_true"], dtype=np.int64)
            y_pred = np.asarray(z["y_pred"], dtype=np.int64)
            proba = np.asarray(z["proba"], dtype=np.float64)
        if row_index.shape != (3144,) or not np.array_equal(row_index, np.arange(3144)):
            errors.append(f"{variant}: row coverage differs from exact fold0 FIT roster length/order")
        if y_true.shape != (3144,) or y_pred.shape != (3144,) or proba.shape != (3144, 4):
            errors.append(f"{variant}: prediction artifact shape mismatch")
        if np.any((y_true < 0) | (y_true > 3)) or np.any((y_pred < 0) | (y_pred > 3)):
            errors.append(f"{variant}: labels/predictions outside four-class range")
        if not np.isfinite(proba).all() or not np.allclose(proba.sum(axis=1), 1.0, atol=1e-5, rtol=1e-5):
            errors.append(f"{variant}: probabilities are non-finite or do not sum to one")
        arrays[variant] = (row_index, y_true, y_pred)
        all_y_pred[variant] = y_pred
        recomputed[variant] = metrics(y_true, y_pred)
    if not np.array_equal(arrays["baseline"][1], arrays["candidate"][1]):
        errors.append("baseline/candidate saved FIT labels differ")
    for variant in ("baseline", "candidate"):
        saved = result.get("aggregate", {}).get(variant, {})
        calc = recomputed[variant]
        for key in ("n", "correct", "support", "confusion"):
            if saved.get(key) != calc[key]:
                errors.append(f"{variant}: aggregate {key} does not match independent prediction recomputation")
        if abs(float(saved.get("macro_f1", -1)) - calc["macro_f1"]) > 1e-12:
            errors.append(f"{variant}: aggregate macro-F1 does not match independent recomputation")
    delta = recomputed["candidate"]["correct"] - recomputed["baseline"]["correct"]
    thresholds = result.get("gate_thresholds", {})
    expected_pass = (recomputed["candidate"]["correct"] >= int(thresholds.get("minimum_candidate_correct", 10**9))
                     and delta >= int(thresholds.get("minimum_gain_over_matched_baseline", 10**9)))
    if delta != result.get("candidate_minus_matched_baseline_correct"):
        errors.append("saved paired delta does not match independent recomputation")
    if expected_pass != bool(thresholds.get("diagnostic_numeric_gate_pass")):
        errors.append("saved numeric gate boolean does not match both frozen thresholds")
    if result.get("full_3fold_execution_allowed") is not False or result.get("official_score") is not None:
        errors.append("result overstates full-run authorization or official score status")
    if progress.get("status") != "complete" or progress.get("fit_attempts_started") != 8 or progress.get("fits_completed") != 8:
        errors.append("fit progress does not record exactly eight completed gate fits")
    if len(result.get("fit_records", [])) != 8 or len(progress.get("fit_records", [])) != 8:
        errors.append("saved fit-record count differs from the eight-fit scope")
    for record in result.get("fit_records", []):
        model = root / record["model_path"]
        if not model.is_file() or sha256(model).upper() != record.get("model_sha256", "").upper():
            errors.append("a saved model is missing or differs from its recorded hash")
    # Recompute every saved fold metric from the private validation predictions.
    fold_records = result.get("cv", {}).get("fold_metrics", [])
    if len(fold_records) != 4:
        errors.append("saved CV fold record count is not four")
    for fold, fold_record in enumerate(fold_records[:4]):
        ep = out / "feature_evidence" / f"fold_{fold}_features.npz"
        if not ep.is_file():
            continue
        with np.load(ep, allow_pickle=False) as z:
            valid = np.asarray(z["valid_indices"], dtype=np.int64)
        for variant in ("baseline", "candidate"):
            calc = metrics(arrays[variant][1][valid], all_y_pred[variant][valid])
            saved = fold_record.get("models", {}).get(variant, {})
            if saved.get("correct") != calc["correct"] or saved.get("confusion") != calc["confusion"]:
                errors.append(f"fold {fold} {variant}: saved fold metric differs from independent recomputation")
            if abs(float(saved.get("macro_f1", -1)) - calc["macro_f1"]) > 1e-12:
                errors.append(f"fold {fold} {variant}: saved fold macro-F1 differs from independent recomputation")
    input_hashes = result.get("input_hashes", {})
    for rel, expected in approval.get("source_hashes", {}).items():
        if "/code/" in rel or rel.endswith("/configs/experiment.json"):
            key = {"code/t5_rebuild.py": "t5_rebuild_code", "code/s1_features.py": "s1_feature_code",
                   "code/run_gate.py": "run_gate_code", "configs/experiment.json": "config"}.get(rel.split("round_022/")[-1])
            if key and input_hashes.get(key, "").upper() != expected.upper():
                errors.append(f"input hash mismatch for approved {key}")
    for fold in range(4):
        ep = out / "feature_evidence" / f"fold_{fold}_features.npz"
        if not ep.is_file():
            errors.append(f"missing fold {fold} private feature evidence")
            continue
        with np.load(ep, allow_pickle=False) as z:
            tr = np.asarray(z["train_indices"], dtype=np.int64)
            va = np.asarray(z["valid_indices"], dtype=np.int64)
            ty = np.asarray(z["train_labels"], dtype=np.int64)
            t5 = np.asarray(z["t5_matrix"])
            s1 = np.asarray(z["s1_matrix"])
        if len(tr) != len(ty) or len(set(tr.tolist())) != len(tr) or len(set(va.tolist())) != len(va):
            errors.append(f"fold {fold}: train/validation index dimensions or uniqueness mismatch")
        if len(tr) + len(va) != 3144 or set(tr.tolist()) & set(va.tolist()):
            errors.append(f"fold {fold}: train/validation partition is not a disjoint complete FIT split")
        if not np.array_equal(np.sort(np.concatenate([tr, va])), np.arange(3144)):
            errors.append(f"fold {fold}: train/validation partition does not cover the FIT roster")
        if not np.array_equal(ty, arrays["baseline"][1][tr]):
            errors.append(f"fold {fold}: saved feature-builder train labels disagree with FIT truth")
        if t5.shape != (3144, 10) or s1.shape != (3144, 24):
            errors.append(f"fold {fold}: fold-local T5/S1 feature evidence shape mismatch")
        if np.isinf(t5).any() or np.isinf(s1).any():
            errors.append(f"fold {fold}: infinite fold-local feature value")
    # Verify the provenance/observation-count metadata without printing row data.
    s1_manifest_path = round_dir / "tmp" / "s1_profiles.sqlite.manifest.json"
    t5_manifest_path = round_dir / "artifacts" / "t5_fishing_profiles.manifest.json"
    count_audit_path = round_dir / "artifacts" / "t5_mask_equivalence.json"
    if not s1_manifest_path.is_file() or not t5_manifest_path.is_file() or not count_audit_path.is_file():
        errors.append("one or more feature-cache provenance manifests are missing")
    else:
        s1_meta = json.loads(s1_manifest_path.read_text(encoding="utf-8"))
        t5_meta = json.loads(t5_manifest_path.read_text(encoding="utf-8"))
        count_audit = json.loads(count_audit_path.read_text(encoding="utf-8"))
        if s1_meta.get("fit_roster_size") != 3144 or s1_meta.get("ordered_fit_roster_sha256") != result.get("ordered_fit_roster_sha256"):
            errors.append("S1 profile manifest is not bound to the exact FIT roster")
        if s1_meta.get("predicate") != "year == 2026 AND id IN exact fold0 FIT roster":
            errors.append("S1 profile manifest does not state the exact 2026 FIT-only predicate")
        if (t5_meta.get("test2025_labels_read") is not False
                or t5_meta.get("test2025_query_rows_materialized") != 0
                or t5_meta.get("test2025_individual_outputs_retained") is not False
                or t5_meta.get("labels_used") is not False):
            errors.append("T5 cache manifest exceeds the approved unlabeled shared-harbor/query boundary")
        if (count_audit.get("legacy_log1p_count_matches") is not True
                or count_audit.get("current_fit_rows") != 3144
                or count_audit.get("max_abs_log_count_delta") is None
                or float(count_audit["max_abs_log_count_delta"]) > 1e-6):
            errors.append("legacy observed fishing-row count equivalence audit failed")
    # Load each serialized model one at a time; this checks persistence without fitting.
    try:
        if memory.available < resource_snapshot["minimum_free_bytes"]:
            raise MemoryError("available RAM below one-shot verifier threshold; skip model reload")
        import joblib
        for record in result.get("fit_records", []):
            model = joblib.load(root / record["model_path"])
            expected_features = 304 if record.get("variant") == "baseline" else 328
            actual_features = getattr(model, "n_features_in_", None)
            if actual_features is None and hasattr(model, "booster_"):
                actual_features = model.booster_.num_feature()
            if int(actual_features or -1) != expected_features:
                errors.append("reloaded model feature count differs from its recorded baseline/candidate variant")
            if not np.array_equal(np.asarray(getattr(model, "classes_", [])), np.arange(4)):
                errors.append("reloaded model class order differs from frozen four-class order")
            del model
    except Exception as exc:  # report only the exception type, not paths or data
        errors.append(f"serialized model reload failed ({type(exc).__name__})")
    checks = {"status": "pass" if not errors else "fail", "error_count": len(errors),
              "fit_rows": 3144, "folds": 4, "fits": len(result.get("fit_records", [])),
              "baseline_correct": recomputed.get("baseline", {}).get("correct"),
              "candidate_correct": recomputed.get("candidate", {}).get("correct"),
              "candidate_minus_baseline": delta,
              "numeric_gate_pass": bool(expected_pass), "full_3fold_authorized": False,
              "model_reload_checked": len(result.get("fit_records", [])) == 8 and memory.available >= resource_snapshot["minimum_free_bytes"],
              "verification_memory": {"available_bytes": resource_snapshot["available_bytes"],
                                      "expected_peak_bytes": resource_snapshot["expected_peak_bytes"],
                                      "minimum_free_bytes": resource_snapshot["minimum_free_bytes"],
                                      "other_python_process_count": len(other_python)},
              "errors": errors}
    print(json.dumps(checks, ensure_ascii=True, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
