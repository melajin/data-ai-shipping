from __future__ import annotations
import hashlib, io, json, os, platform, sys, time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

WORK = Path(__file__).resolve().parent
TASK = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104")
REPO = Path(r"D:\repos\fishing-track-classification")
DATA_VALIDATION = TASK / "reports" / "exp01" / "data_validation.json"
PROVENANCE = TASK / "reports" / "exp01" / "provenance_addendum.json"
MODEL_DIR = TASK / "artifacts" / "exp01" / "sqrt_macro" / "models"
PRED_DIR = TASK / "artifacts" / "exp01" / "sqrt_macro" / "seed_predictions"
FOLDS = (0, 1, 2)
SEEDS = (1, 7, 42, 2024, 2026)
T5_COLS = [
    "t5_main_연안복합", "t5_main_자망", "t5_main_통발", "t5_main_채낚기연승낚시",
    "t5_month_연안복합", "t5_month_자망", "t5_month_통발", "t5_month_채낚기연승낚시",
    "t5_fine_grid_ok_ratio", "t5_log1p_fishing_rows",
]
CLASS_ORDER = ["연안복합", "자망", "통발", "채낚기연승낚시"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(paths: list[Path]) -> dict[str, dict]:
    result = {}
    for path in sorted(set(paths), key=str):
        st = path.stat()
        result[str(path)] = {
            "bytes": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": sha256(path),
        }
    return result


def rel_stats(a: np.ndarray, b: np.ndarray) -> dict:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    mask_a, mask_b = np.isnan(a), np.isnan(b)
    finite = np.isfinite(a) & np.isfinite(b)
    diff = np.abs(a[finite] - b[finite])
    denom = np.maximum(np.maximum(np.abs(a[finite]), np.abs(b[finite])), np.finfo(np.float64).tiny)
    rel = diff / denom
    finite_a, finite_b = a[finite], b[finite]
    bits_equal = bool(np.array_equal(finite_a.view(np.uint64), finite_b.view(np.uint64)))
    return {
        "shape": list(a.shape),
        "nan_count_a": int(mask_a.sum()),
        "nan_count_b": int(mask_b.sum()),
        "nan_mask_equal": bool(np.array_equal(mask_a, mask_b)),
        "finite_pairs": int(finite.sum()),
        "bitwise_equal_on_finite": bits_equal,
        "exact_equal_with_nan": bool(np.array_equal(a, b, equal_nan=True)),
        "changed_finite_values": int(np.count_nonzero(finite_a != finite_b)),
        "max_abs": float(diff.max()) if diff.size else 0.0,
        "mean_abs": float(diff.mean()) if diff.size else 0.0,
        "max_rel": float(rel.max()) if rel.size else 0.0,
        "allclose_atol_1e_12_rtol_0": bool(np.allclose(a, b, atol=1e-12, rtol=0.0, equal_nan=True)),
        "allclose_atol_1e_10_rtol_0": bool(np.allclose(a, b, atol=1e-10, rtol=0.0, equal_nan=True)),
    }


def read_and_reexport(path: Path, precision: str | None) -> dict[str, np.ndarray]:
    options = {} if precision is None else {"float_precision": precision}
    frame = pd.read_csv(path, dtype={"rfid_id": str}, **options)
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)  # same pandas default float serialization family as producer
    buffer.seek(0)
    default_again = pd.read_csv(buffer, dtype={"rfid_id": str})
    buffer.seek(0)
    roundtrip_again = pd.read_csv(buffer, dtype={"rfid_id": str}, float_precision="round_trip")
    return {
        "direct": frame,
        "reexport_default": default_again,
        "reexport_round_trip": roundtrip_again,
    }


def score(y: np.ndarray, pred: np.ndarray) -> dict:
    # Single-label multiclass micro-F1 equals accuracy.
    total = int(len(y))
    correct = int(np.count_nonzero(y == pred))
    recalls, f1s = [], []
    for c in range(4):
        tp = int(np.count_nonzero((y == c) & (pred == c)))
        fp = int(np.count_nonzero((y != c) & (pred == c)))
        fn = int(np.count_nonzero((y == c) & (pred != c)))
        recalls.append(tp / (tp + fn) if tp + fn else 0.0)
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return {"n": total, "correct": correct, "micro_f1": correct / total if total else None,
            "macro_f1": float(np.mean(f1s)), "class_recall": recalls, "class_f1": f1s}


def main() -> None:
    t0 = time.perf_counter()
    validation = json.loads(DATA_VALIDATION.read_text(encoding="utf-8"))
    csv_paths = {}
    recorded_hashes = {}
    for fold in FOLDS:
        found = [(Path(k), v) for k, v in validation.get("input_hashes", {}).items()
                 if f"fold_{fold}_t5.csv" in k]
        if len(found) != 1:
            raise RuntimeError(f"expected one recorded fold_{fold} T5 path, found {len(found)}")
        csv_paths[fold], recorded_hashes[fold] = found[0]
    fold_paths = {f: TASK / "artifacts" / "exp01" / f"fold_{f}_features.npz" for f in FOLDS}
    model_paths = {(f, s): MODEL_DIR / f"fold_{f}_seed_{s}.txt" for f in FOLDS for s in SEEDS}
    code_paths = [
        REPO / "code" / "tools" / "run_005_main_20261101.py",
        REPO / "code" / "tools" / "run_005_F156_merge_20261101.py",
        TASK / "shared" / "data_adapter.py",
        TASK / "shared" / "eval_contract.py",
        TASK / "experiments" / "exp01" / "run_exp01.py",
        DATA_VALIDATION,
        PROVENANCE,
    ]
    inputs = [*csv_paths.values(), *fold_paths.values(), *model_paths.values(), *code_paths]
    missing = [str(p) for p in inputs if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing required inputs: " + "; ".join(missing))

    pre = snapshot(inputs)
    parser_results = {}
    prepared_checks = {}
    round_trip_features = {}
    for fold in FOLDS:
        csv_path = csv_paths[fold]
        expected_hash = recorded_hashes[fold].get("sha256")
        if expected_hash and pre[str(csv_path)]["sha256"] != expected_hash:
            raise RuntimeError(f"T5 CSV hash does not match prior provenance for fold {fold}")
        variants = {mode: read_and_reexport(csv_path, mode) for mode in (None, "round_trip")}
        default_df = variants[None]["direct"]
        rt_df = variants["round_trip"]["direct"]
        if default_df.columns.tolist() != ["rfid_id"] + T5_COLS:
            raise RuntimeError(f"fold {fold} CSV columns/order differ from generator schema")
        if rt_df["rfid_id"].tolist() != default_df["rfid_id"].tolist():
            raise RuntimeError(f"fold {fold}: pandas parser changed ID order")
        with np.load(fold_paths[fold], allow_pickle=False) as z:
            ids = z["rfid_ids"].astype(str)
            y = z["y"].astype(np.int64)
            roles = z["roles"].astype(str)
            X = z["X"].astype(np.float64, copy=True)
            names = z["feature_names"].astype(str).tolist()
        if X.shape != (5897, 304) or len(ids) != 5897:
            raise RuntimeError(f"fold {fold}: unexpected development matrix dimensions {X.shape}")
        if names[156:166] != T5_COLS:
            raise RuntimeError(f"fold {fold}: cached X304 T5 column order mismatch")
        if len(set(ids.tolist())) != 5897:
            raise RuntimeError(f"fold {fold}: development NPZ IDs not unique")
        if default_df["rfid_id"].tolist() != ids.tolist():
            raise RuntimeError(f"fold {fold}: cached T5 CSV IDs/order differ from development NPZ")
        if sorted(set(roles.tolist())) != ["FIT", "INNER", "OUTER"]:
            raise RuntimeError(f"fold {fold}: unexpected role labels")
        default_values = default_df[T5_COLS].to_numpy(dtype=np.float64)
        rt_values = rt_df[T5_COLS].to_numpy(dtype=np.float64)
        npz_values = X[:, 156:166]
        reexp_default = variants[None]["reexport_default"][T5_COLS].to_numpy(dtype=np.float64)
        reexp_rt = variants[None]["reexport_round_trip"][T5_COLS].to_numpy(dtype=np.float64)
        prepared_checks[str(fold)] = {
            "rows": int(len(ids)), "role_counts": {r: int(np.count_nonzero(roles == r)) for r in ("FIT", "INNER", "OUTER")},
            "class_counts_fit_only": {str(c): int(np.count_nonzero((roles == "FIT") & (y == c))) for c in range(4)},
            "id_order_equal_csv_npz": True,
            "feature_names": names[156:166],
            "X304_T5_vs_default_csv": rel_stats(npz_values, default_values),
        }
        parser_results[str(fold)] = {
            "csv_path": str(csv_path),
            "csv_sha256": pre[str(csv_path)]["sha256"],
            "csv_rows": int(len(default_df)),
            "csv_columns": default_df.columns.tolist(),
            "default_vs_round_trip_reader": rel_stats(default_values, rt_values),
            "default_reader_reexport_default_reader": rel_stats(default_values, reexp_default),
            "default_reader_reexport_round_trip_reader": rel_stats(default_values, reexp_rt),
            "round_trip_reader_reexport_default_reader": rel_stats(rt_values, variants["round_trip"]["reexport_default"][T5_COLS].to_numpy(dtype=np.float64)),
            "round_trip_reader_reexport_round_trip_reader": rel_stats(rt_values, variants["round_trip"]["reexport_round_trip"][T5_COLS].to_numpy(dtype=np.float64)),
        }
        round_trip_features[fold] = rt_values

    replay = []
    for fold in FOLDS:
        with np.load(fold_paths[fold], allow_pickle=False) as z:
            X0 = z["X"].astype(np.float64, copy=True)
            y = z["y"].astype(np.int64)
            roles = z["roles"].astype(str)
        X1 = X0.copy()
        X1[:, 156:166] = round_trip_features[fold]
        outer = roles == "OUTER"
        for seed in SEEDS:
            model_path = model_paths[(fold, seed)]
            model = lgb.Booster(model_file=str(model_path))
            if model.num_feature() != X0.shape[1]:
                raise RuntimeError(f"fold {fold} seed {seed}: model expects {model.num_feature()} features")
            p0 = np.asarray(model.predict(X0, num_threads=1), dtype=np.float64)
            p1 = np.asarray(model.predict(X1, num_threads=1), dtype=np.float64)
            if p0.shape != (len(y), 4) or p1.shape != p0.shape:
                raise RuntimeError(f"fold {fold} seed {seed}: unexpected prediction shape {p0.shape}")
            pred0, pred1 = p0.argmax(axis=1), p1.argmax(axis=1)
            s0, s1 = score(y[outer], pred0[outer]), score(y[outer], pred1[outer])
            replay.append({
                "fold": fold, "seed": seed, "model_sha256": pre[str(model_path)]["sha256"],
                "dev_rows_inferred": int(len(y)), "outer_rows_scored": int(outer.sum()),
                "probability_max_abs_delta": float(np.max(np.abs(p0 - p1))),
                "probability_mean_abs_delta": float(np.mean(np.abs(p0 - p1))),
                "probability_exact_row_changes": int(np.count_nonzero(np.any(p0 != p1, axis=1))),
                "argmax_changed_rows_all_dev": int(np.count_nonzero(pred0 != pred1)),
                "argmax_changed_rows_outer": int(np.count_nonzero(pred0[outer] != pred1[outer])),
                "baseline_outer": s0, "round_trip_outer": s1,
                "outer_micro_delta": s1["micro_f1"] - s0["micro_f1"],
                "outer_macro_delta": s1["macro_f1"] - s0["macro_f1"],
            })
            del p0, p1, model

    post = snapshot(inputs)
    changes = [p for p in pre if pre[p] != post[p]]
    if changes:
        raise RuntimeError("one or more source inputs changed during the run: " + "; ".join(changes))
    aggregate = {
        "models_replayed": len(replay),
        "outer_rows_total_across_fold_seed_models": int(sum(x["outer_rows_scored"] for x in replay)),
        "argmax_changed_rows_outer_total_model_row_instances": int(sum(x["argmax_changed_rows_outer"] for x in replay)),
        "models_with_outer_argmax_change": int(sum(x["argmax_changed_rows_outer"] > 0 for x in replay)),
        "max_probability_abs_delta": max((x["probability_max_abs_delta"] for x in replay), default=0.0),
        "outer_micro_delta_min": min((x["outer_micro_delta"] for x in replay), default=0.0),
        "outer_micro_delta_max": max((x["outer_micro_delta"] for x in replay), default=0.0),
    }
    result = {
        "experiment": "round001 T5 CSV parser/serialization sensitivity and saved sqrt_macro replay",
        "status": "completed_with_dynamic_array_comparison_unmeasured",
        "started_utc": datetime.fromtimestamp(time.time() - (time.perf_counter() - t0), timezone.utc).isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - t0,
        "scope": {
            "development_only": True, "fold_rows": 5897, "holdout_rows_read": 0,
            "raw_csv_or_parquet_parsed": False, "model_training": False,
            "actual_hardware_measurement": False,
            "dynamic_t5_reconstructed": False,
            "dynamic_comparison_blocker": "The source dynamic path reads all Train geometries for the global fishing mask and Train+Test geometries to build shared harbors. The only discovered saved harbor cache is train-only (Run 008) and explicitly differs from T5's Train+Test population. Reusing either full-cohort geometry or a different harbor cache would violate the frozen input condition/holdout boundary.",
        },
        "environment": {
            "python": sys.version, "platform": platform.platform(),
            "numpy": np.__version__, "pandas": pd.__version__, "lightgbm": lgb.__version__,
            "cpu_threads_for_prediction": 1,
            "random_seed": None,
            "thread_environment": {k: os.environ.get(k) for k in (
                "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "TEMP", "TMP")},
        },
        "input_scope": {"source_inputs": pre, "source_inputs_after": post, "source_files_changed": changes,
                        "input_validation_json_sha256": pre[str(DATA_VALIDATION)]["sha256"],
                        "provenance_addendum_sha256": pre[str(PROVENANCE)]["sha256"]},
        "prepared_fold_checks": prepared_checks,
        "csv_reader_and_reexport_checks": parser_results,
        "saved_model_replay": {"aggregate": aggregate, "per_fold_seed": replay},
        "interpretation": [
            "The direct numeric comparison here is cached X304 T5 versus serialized fold CSV parser modes, not dynamic in-memory T5 versus CSV.",
            "CSV default and round_trip parsing only test decimal-to-float decoding. Re-export checks only test pandas reserialization of the already serialized CSV values.",
            "Saved model scores are repeated development OUTER re-inference on the same 5897-vessel roster, not independent validation or a new performance result.",
            "The existing 0.593013 baseline and 0.593353 exploratory aggregate remain prior report values; this diagnostic does not update them.",
        ],
    }
    (WORK / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK / "environment.json").write_text(json.dumps(result["environment"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "elapsed_seconds": result["elapsed_seconds"],
                      "aggregate": aggregate, "result": str(WORK / "result.json")}, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
