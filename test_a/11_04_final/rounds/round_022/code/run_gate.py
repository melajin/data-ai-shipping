from __future__ import annotations

"""Round022 paired FIT-internal S1 diagnostic gate; never starts the full run."""

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

import s1_features as s1

ROOT = Path(__file__).resolve().parents[3]
ROUND = Path(__file__).resolve().parents[1]
DEFAULT_FEATURE_NPZ = Path(
    r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_0_features.npz"
)
DEFAULT_SPATIAL_PARQUET = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\26_11_2\work\재식별_투트랙_001r1\s3_hourly.parquet"
)
EXPECTED_SPATIAL_SHA256 = "7f1d433ce06963cdfa0ff131ba7bb21192846ed4b859a7d48ebc200bff81b1eb"
T5_MODULE = ROUND / "code" / "t5_rebuild.py"
T5_PROFILE_NPZ = ROUND / "artifacts" / "t5_fishing_profiles.npz"
T5_PROFILE_MANIFEST = T5_PROFILE_NPZ.with_suffix(".manifest.json")
FEATURE_CACHE = ROUND / "tmp" / "s1_profiles.sqlite"
OUT_DIR = ROUND / "artifacts" / "gate"
T5_START, T5_STOP = 156, 166


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_fold0_fit(path: Path) -> tuple[np.ndarray, np.ndarray, list[str], str, dict]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with np.load(source, allow_pickle=False) as bundle:
        required = {"X", "y", "rfid_ids", "roles", "feature_names"}
        if not required.issubset(set(bundle.files)):
            raise ValueError("Fold feature artifact lacks required arrays")
        X = np.asarray(bundle["X"])
        y = np.asarray(bundle["y"], dtype=np.int64)
        ids_all = bundle["rfid_ids"].astype(str)
        roles = bundle["roles"].astype(str)
        names = bundle["feature_names"].astype(str).tolist()
    if X.ndim != 2 or X.shape != (len(y), 304) or len(y) != len(ids_all) or len(y) != len(roles):
        raise ValueError("Fold feature artifact dimensions differ from frozen fold0 contract")
    if X.dtype.kind not in "fc":
        raise ValueError("Fold feature matrix must be floating point")
    if len(names) != 304 or len(set(names)) != 304:
        raise ValueError("Fold feature name schema is not 304 unique ordered columns")
    fit_mask = roles == "FIT"
    if int(fit_mask.sum()) != 3144:
        raise ValueError("Fold0 FIT row count differs from frozen 3,144")
    X_fit = X[fit_mask]
    y_fit = y[fit_mask]
    ids_fit = ids_all[fit_mask].tolist()
    if np.any((y_fit < 0) | (y_fit > 3)) or len(set(ids_fit)) != len(ids_fit):
        raise ValueError("Fold0 FIT labels or roster violate the frozen four-class contract")
    if tuple(names[T5_START:T5_STOP]) != s1_expected_t5_names():
        raise ValueError("304-column T5 field ordering differs from the frozen adapter schema")
    metadata = {
        "path": str(source), "sha256": sha256_file(source), "bytes": source.stat().st_size,
        "shape": list(X_fit.shape), "fit_roster_sha256": s1.hash_ordered_ids(ids_fit),
        "feature_schema_sha256": hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest(),
    }
    return X_fit, y_fit, ids_fit, metadata["fit_roster_sha256"], metadata


def s1_expected_t5_names() -> tuple[str, ...]:
    # ASCII source escapes avoid editor/console code-page corruption.
    names = ("\uC5F0\uC548\uBCF5\uD569", "\uC790\uB9DD", "\uD1B5\uBC1C",
             "\uCC44\uB09A\uAE30\uC5F0\uC2B9\uB09A\uC2DC")
    return tuple([f"t5_main_{n}" for n in names] + [f"t5_month_{n}" for n in names]
                 + ["t5_fine_grid_ok_ratio", "t5_log1p_fishing_rows"])


def load_t5_rebuilder(ids: list[str]):
    if not T5_MODULE.is_file():
        raise FileNotFoundError("Round022 T5 rebuild module is missing")
    spec = importlib.util.spec_from_file_location("round022_t5_rebuild", T5_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the approved Round022 T5 rebuild module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prepare = getattr(module, "prepare_t5", None)
    if prepare is None:
        raise RuntimeError("T5 rebuild module does not expose prepare_t5(ids)")
    rebuild = prepare(ids)
    if not callable(rebuild):
        raise RuntimeError("prepare_t5 did not return the frozen rebuild(train_indices, labels) callback")
    return rebuild


def package_versions() -> dict:
    versions = {"python": sys.version, "platform": platform.platform()}
    for package in ("numpy", "scikit-learn", "lightgbm", "joblib", "pyarrow"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def resource_snapshot(stage: str) -> dict:
    """One-shot safety check; never waits/polls or terminates another process."""
    import psutil
    memory = psutil.virtual_memory()
    others = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "create_time"]):
        try:
            info = proc.info
            if info["pid"] != os.getpid() and "python" in (info.get("name") or "").lower():
                others.append({"pid": int(info["pid"]), "name": info.get("name"),
                               "rss_bytes": int(info["memory_info"].rss),
                               "create_time": info.get("create_time")})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    snap = {"timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "stage": stage, "available_bytes": int(memory.available),
            "expected_peak_bytes": int(1.5 * 2**30), "minimum_free_bytes": int(2.5 * 2**30),
            "other_python_processes": others,
            "allowed": bool(memory.available >= 2.5 * 2**30),
            "action_on_shortfall": "stop stage before operation; do not terminate other processes"}
    return snap


def record_resource_check(output_dir: Path, checks: list[dict], stage: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = resource_snapshot(stage)
    checks.append(snapshot)
    save_json(output_dir / "resource_checks.json", {"checks": checks})
    if not snapshot["allowed"]:
        raise RuntimeError("RAM gate: available memory below 2.5 GiB; defer and recheck after independent work")
    return snapshot


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    cm = np.zeros((4, 4), dtype=np.int64)
    for actual, predicted in zip(y_true.tolist(), y_pred.tolist()):
        cm[int(actual), int(predicted)] += 1
    support = cm.sum(axis=1)
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = support - tp
    precision = np.divide(tp, tp + fp, out=np.zeros(4, dtype=np.float64), where=(tp + fp) != 0)
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support != 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(4, dtype=np.float64), where=(precision + recall) != 0)
    return {
        "n": int(len(y_true)), "correct": int(tp.sum()), "micro_f1": float(tp.sum() / len(y_true)),
        "macro_f1": float(f1.mean()), "support": support.tolist(), "tp": tp.tolist(),
        "fp": fp.tolist(), "fn": fn.tolist(), "precision": precision.tolist(),
        "recall": recall.tolist(), "class_f1": f1.tolist(), "confusion": cm.tolist(),
    }


def run_gate(features_path: Path, profile_cache: Path, output_dir: Path,
             resource_checks: list[dict] | None = None) -> dict:
    import joblib
    import lightgbm as lgb
    from sklearn.model_selection import StratifiedKFold

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.relative_to(ROOT.resolve())
    result_path = output_dir / "gate_result.json"
    if result_path.exists():
        raise FileExistsError(f"Refusing to overwrite prior gate output: {result_path}")
    resource_checks = resource_checks if resource_checks is not None else []
    record_resource_check(output_dir, resource_checks, "fold0_fit_input_load_and_t5_cache_load")
    X, y, ids, roster_hash, feature_meta = load_fold0_fit(features_path)

    # The callback's prerequisite/provenance check occurs before feature building
    # and before any estimator is instantiated or fit.
    rebuild_t5 = load_t5_rebuilder(ids)
    profiles = s1.S1ProfileStore(profile_cache, expected_source_sha256=EXPECTED_SPATIAL_SHA256)
    if profiles.manifest.get("ordered_fit_roster_sha256") != roster_hash:
        raise ValueError("S1 profile cache FIT roster hash differs from the 304-column fold cache")
    if profiles.n_rows != len(ids):
        raise ValueError("S1 profile cache row count differs from fold0 FIT")

    config = json.loads((ROUND / "configs" / "experiment.json").read_text(encoding="utf-8-sig"))
    if config.get("stage") != "S1_gate" or config.get("cv_folds") != 4 or config.get("seed") != 42:
        raise ValueError("Round022 gate configuration differs from the frozen CV contract")
    if config.get("resolutions") != [0.01, 0.05, 0.1] or config.get("alpha") != 5:
        raise ValueError("Round022 spatial resolution or smoothing config differs from frozen S1")
    clf_cfg = config["lgbm"]
    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)
    predictions = {"baseline": np.full(len(y), -1, dtype=np.int64),
                   "candidate": np.full(len(y), -1, dtype=np.int64)}
    probabilities = {key: np.full((len(y), 4), np.nan, dtype=np.float32) for key in predictions}
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = output_dir / "models"
    model_dir.mkdir(exist_ok=False)
    evidence_dir = output_dir / "feature_evidence"
    evidence_dir.mkdir(exist_ok=False)
    folds: list[dict] = []
    fit_records: list[dict] = []
    progress = {"status": "running", "fit_attempts_started": 0, "fits_completed": 0, "fit_records": []}
    save_json(output_dir / "fit_progress.json", progress)
    all_fit_indices = np.arange(len(y), dtype=np.int64)
    for fold_idx, (train_idx, valid_idx) in enumerate(skf.split(X, y)):
        t5_matrix = np.asarray(rebuild_t5(train_idx, y[train_idx]), dtype=np.float64)
        if t5_matrix.shape != (len(y), 10):
            raise ValueError(f"T5 callback returned unexpected shape on CV fold {fold_idx}")
        if np.isinf(t5_matrix).any():
            raise ValueError(f"T5 callback returned infinite values on CV fold {fold_idx}")
        record_resource_check(output_dir, resource_checks, f"cv{fold_idx}_s1_feature_build")
        s1_matrix = s1.build_features(profiles, all_fit_indices, train_idx, y[train_idx])
        if s1_matrix.shape != (len(y), 24) or np.isinf(s1_matrix).any():
            raise ValueError(f"S1 builder returned invalid fold-local features on CV fold {fold_idx}")
        X_base = X.copy()
        X_base[:, T5_START:T5_STOP] = t5_matrix.astype(X_base.dtype, copy=False)
        X_candidate = np.concatenate((X_base, s1_matrix), axis=1)
        if X_candidate.shape != (len(y), 328):
            raise ValueError("Candidate input does not have the frozen 328 columns")

        fold_result = {"fold": fold_idx, "train_rows": int(len(train_idx)), "validation_rows": int(len(valid_idx)),
                       "validation_labels_passed_to_feature_builders": False, "t5_rebuilt_from_cv_train_labels": True,
                       "s1_grid_counts_cv_train_only": True, "s1_fit_queries_leave_self_out": True, "models": {}}
        np.savez_compressed(
            evidence_dir / f"fold_{fold_idx}_features.npz",
            train_indices=train_idx.astype(np.int32), valid_indices=valid_idx.astype(np.int32),
            train_labels=y[train_idx].astype(np.int8), t5_matrix=t5_matrix,
            s1_matrix=s1_matrix,
        )
        for name, matrix in (("baseline", X_base), ("candidate", X_candidate)):
            params = dict(clf_cfg)
            model = lgb.LGBMClassifier(**params)
            record_resource_check(output_dir, resource_checks, f"cv{fold_idx}_{name}_fit")
            progress["fit_attempts_started"] += 1
            progress["current_fit"] = {"fold": fold_idx, "variant": name,
                                        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
            save_json(output_dir / "fit_progress.json", progress)
            started = time.perf_counter()
            model.fit(matrix[train_idx], y[train_idx])
            proba = np.asarray(model.predict_proba(matrix[valid_idx]), dtype=np.float32)
            pred = np.argmax(proba, axis=1).astype(np.int64)
            predictions[name][valid_idx] = pred
            probabilities[name][valid_idx] = proba
            model_path = model_dir / f"fold_{fold_idx}_{name}.joblib"
            joblib.dump(model, model_path)
            model_sha = sha256_file(model_path)
            fold_metric = metrics(y[valid_idx], pred)
            fold_result["models"][name] = fold_metric
            fit_records.append({"fold": fold_idx, "variant": name, "fit_seconds": time.perf_counter() - started,
                                "model_path": str(model_path.relative_to(ROOT)), "model_sha256": model_sha,
                                "feature_count": int(matrix.shape[1])})
            progress["fits_completed"] += 1
            progress["fit_records"] = list(fit_records)
            progress.pop("current_fit", None)
            save_json(output_dir / "fit_progress.json", progress)
        folds.append(fold_result)
        del s1_matrix, X_base, X_candidate, t5_matrix

    if any(np.any(predictions[key] < 0) or np.isnan(probabilities[key]).any() for key in predictions):
        raise ValueError("CV predictions do not cover the exact FIT roster")
    aggregate = {key: metrics(y, predictions[key]) for key in predictions}
    delta = aggregate["candidate"]["correct"] - aggregate["baseline"]["correct"]
    fixed_reference = int(config.get("fixed_reference_correct", 1817))
    min_delta = int(config.get("min_delta_correct", 16))
    fixed_min_candidate = int(config.get("fixed_reference_min_candidate_correct", fixed_reference + min_delta))
    diagnostic_gate_pass = (aggregate["candidate"]["correct"] >= fixed_min_candidate and delta >= min_delta)

    for name in predictions:
        pred_path = output_dir / f"predictions_{name}.npz"
        np.savez_compressed(pred_path, row_index=all_fit_indices, y_true=y,
                            y_pred=predictions[name], proba=probabilities[name])
    t5_meta = json.loads(T5_PROFILE_MANIFEST.read_text(encoding="utf-8"))
    source_hashes = {
        "fold0_features_npz": feature_meta["sha256"],
        "s3_hourly_parquet": EXPECTED_SPATIAL_SHA256,
        "s1_profile_cache": sha256_file(Path(profile_cache)),
        "s1_profile_manifest": sha256_file(Path(profile_cache).with_suffix(Path(profile_cache).suffix + ".manifest.json")),
        "t5_profile_cache": t5_meta.get("sha256"),
        "t5_profile_manifest": sha256_file(T5_PROFILE_MANIFEST),
        "t5_rebuild_code": sha256_file(T5_MODULE),
        "s1_feature_code": sha256_file(Path(s1.__file__)),
        "run_gate_code": sha256_file(Path(__file__)),
        "config": sha256_file(ROUND / "configs" / "experiment.json"),
    }
    record = {
        "status": "paired_proxy_diagnostic_complete",
        "scope": "fold0 FIT internal 4-fold CV; reconstructed label-based T5 and centroid-based S1 profiles from current 2026 only",
        "exact_original_s1_gate": False,
        "scope_change": "S1 positions are hourly centroid proxies rather than original occupied-geometry cells; do not claim the original S1 hypothesis was tested exactly",
        "full_3fold_execution_allowed": False,
        "full_execution_block_reason": "source representation is a bounded centroid proxy; this diagnostic does not authorize the exact original full S1 run",
        "cv": {"folds": 4, "seed": 42, "shuffle": True, "fit_rows": int(len(y)), "fold_metrics": folds},
        "aggregate": aggregate,
        "candidate_minus_matched_baseline_correct": int(delta),
        "candidate_minus_fixed_1817_correct": int(aggregate["candidate"]["correct"] - fixed_reference),
        "gate_thresholds": {"fixed_reference_correct": fixed_reference,
                            "minimum_candidate_correct": fixed_min_candidate,
                            "minimum_gain_over_matched_baseline": min_delta,
                            "diagnostic_numeric_gate_pass": bool(diagnostic_gate_pass)},
        "feature_schema": {"baseline_columns": 304, "candidate_columns": 328,
                           "s1_columns": list(s1.FEATURE_NAMES), "s1_alpha": 5.0,
                           "resolutions_deg": list(s1.RESOLUTIONS),
                           "s1_donor_count_semantics": "one vote per FIT vessel per occupied cell and period",
                           "s1_query_weight_semantics": "observed record/time-bin profile weight; not dwell time",
                           "s1_laplace": "(cell class votes + 5)/(cell votes total + 4*5)",
                           "s1_empty_cell_fallback": "coarser cell posterior, then leave-self-out CV-train global prior",
                           "s1_t5_columns_replaced": list(s1_expected_t5_names())},
        "fit_records": fit_records, "resource_checks": resource_checks,
        "input_hashes": source_hashes,
        "environment": package_versions(),
        "ordered_fit_roster_sha256": roster_hash,
        "independent_data_evaluation": False,
        "official_score": None,
        "hardware_verified": False,
        "learning_understanding_assessed": False,
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    save_json(result_path, record)
    progress.update({"status": "complete", "finished_at_utc": record["finished_at_utc"]})
    save_json(output_dir / "fit_progress.json", progress)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-s1", action="store_true", help="stream 2026 FIT-only centroid profiles into a row-index-only SQLite cache")
    mode.add_argument("--run-gate", action="store_true", help="requires both S1 and vetted T5 profile caches; runs only the 8-fit diagnostic gate")
    parser.add_argument("--features-npz", type=Path, default=DEFAULT_FEATURE_NPZ)
    parser.add_argument("--spatial-parquet", type=Path, default=DEFAULT_SPATIAL_PARQUET)
    parser.add_argument("--profile-cache", type=Path, default=FEATURE_CACHE)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.prepare_s1:
        preflight_dir = ROUND / "logs"
        preflight_dir.mkdir(parents=True, exist_ok=True)
        preflight = resource_snapshot("s1_profile_build")
        save_json(preflight_dir / "s1_profile_resource_preflight.json", preflight)
        if not preflight["allowed"]:
            raise RuntimeError("RAM gate: available memory below 2.5 GiB; defer and recheck after independent work")
        X, y, ids, _, feature_meta = load_fold0_fit(args.features_npz)
        manifest = s1.build_profile_cache(
            args.spatial_parquet, ids, args.profile_cache,
            expected_source_sha256=EXPECTED_SPATIAL_SHA256,
        )
        manifest["resource_preflight"] = preflight
        s1_manifest_path = Path(args.profile_cache).with_suffix(Path(args.profile_cache).suffix + ".manifest.json")
        save_json(s1_manifest_path, manifest)
        print(json.dumps({"status": manifest["status"], "source_sha256": manifest["source_sha256"],
                          "profile_rows": manifest.get("profile_rows"), "fit_roster_sha256": manifest["ordered_fit_roster_sha256"],
                          "valid_coordinate_timebin_rows": manifest["valid_coordinate_timebin_rows"],
                          "output_bytes": manifest["sqlite_bytes"]}, ensure_ascii=False))
        return 0

    try:
        resource_checks: list[dict] = []
        result = run_gate(args.features_npz, args.profile_cache, args.output_dir, resource_checks)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        progress_path = Path(args.output_dir) / "fit_progress.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {}
        blocked = {"status": "blocked_before_fit", "reason": str(exc),
                   "exact_original_s1_gate": False,
                   "training_fits_started": int(progress.get("fit_attempts_started", 0)),
                   "fits_completed": int(progress.get("fits_completed", 0)),
                   "resource_checks": resource_checks if "resource_checks" in locals() else [],
                   "fold0_feature_sha256": sha256_file(args.features_npz),
                   "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
        save_json(Path(args.output_dir) / "gate_blocked.json", blocked)
        print(json.dumps(blocked, ensure_ascii=False))
        return 3
    print(json.dumps({"status": result["status"], "baseline_correct": result["aggregate"]["baseline"]["correct"],
                      "candidate_correct": result["aggregate"]["candidate"]["correct"],
                      "delta_correct": result["candidate_minus_matched_baseline_correct"],
                      "numeric_gate_pass": result["gate_thresholds"]["diagnostic_numeric_gate_pass"],
                      "full_3fold_execution_allowed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
