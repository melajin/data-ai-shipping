#!/usr/bin/env python
"""Run one controlled 304-feature LightGBM condition at a time."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import psutil
import lightgbm as lgb

HERE = Path(__file__).resolve()
TASK = HERE.parents[2]
SHARED = TASK / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))
from data_adapter import DEFAULT_ARTIFACTS, load_fold, sha256_file
from eval_contract import (
    CLASS_NAMES, CONDITIONS, EARLY_STOPPING_ROUNDS, FOLDS, N_ESTIMATORS,
    N_FEATURES, SEEDS, lightgbm_eval_metric, metrics, obs_days_metrics,
    prediction_frame, sqrt_sample_weights, validate_probabilities,
)

DEFAULT_OUTPUT = TASK / "artifacts" / "exp01"


class TeeStream:
    def __init__(self, console, logfile):
        self.console = console
        self.logfile = logfile
        self.lock = threading.Lock()

    def write(self, text):
        with self.lock:
            self.console.write(text)
            self.console.flush()
            self.logfile.write(text)
            self.logfile.flush()
        return len(text)

    def flush(self):
        with self.lock:
            self.console.flush()
            self.logfile.flush()

    def isatty(self):
        return bool(getattr(self.console, "isatty", lambda: False)())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_array(values) -> str:
    array = np.asarray(values)
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(array.shape).encode("ascii"))
    digest.update(contiguous.view(np.uint8))
    return digest.hexdigest()


def fold_input_hashes(fold_data, feature_artifact: Path) -> dict[str, str]:
    """Bind a saved seed prediction to its matrix, labels, roles, IDs, and schema."""
    feature_names_json = json.dumps(list(fold_data.feature_names), ensure_ascii=False,
                                   separators=(",", ":"))
    return {
        "feature_artifact_sha256": sha256_file(feature_artifact),
        "X_sha256": sha256_array(fold_data.X),
        "y_sha256": sha256_array(fold_data.y),
        "roles_sha256": sha256_array(fold_data.roles),
        "rfid_ids_sha256": sha256_array(fold_data.rfid_ids.astype(str)),
        "feature_names_sha256": hashlib.sha256(feature_names_json.encode("utf-8")).hexdigest(),
    }


def legacy_cache_evidence(report_path: Path, condition_name: str, fold: int,
                          seed: int, expected_hashes: dict[str, str],
                          model_path: Path) -> bool:
    """Accept an old cache only when its completed run report binds inputs and model."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("condition") != condition_name:
            return False
        recorded_artifact = report.get("input_feature_artifact_sha256", {}).get(str(fold))
        if recorded_artifact != expected_hashes["feature_artifact_sha256"]:
            return False
        model_record = next(
            (row for row in report.get("models", [])
             if int(row.get("fold", -1)) == fold and int(row.get("seed", -1)) == seed),
            None,
        )
        return (model_record is not None
                and model_record.get("model_sha256") == sha256_file(model_path))
    except (OSError, ValueError, TypeError, KeyError, StopIteration):
        return False


def cache_input_validation(saved, report_path: Path, condition_name: str,
                           fold: int, seed: int, expected_hashes: dict[str, str],
                           model_path: Path) -> str | None:
    """Return validation evidence label, or None to force a fresh fit."""
    if "input_hashes_json" in saved.files:
        try:
            saved_hashes = json.loads(str(saved["input_hashes_json"].item()))
        except (ValueError, TypeError, KeyError):
            return None
        return "embedded_fold_hashes_match" if saved_hashes == expected_hashes else None
    if legacy_cache_evidence(report_path, condition_name, fold, seed,
                             expected_hashes, model_path):
        return "legacy_run_report_feature_and_model_hashes_match"
    return None


class ResourceSampler:
    def __init__(self, interval: float = 0.25):
        self.interval = interval
        self.process = psutil.Process(os.getpid())
        self.stop_event = threading.Event()
        self.thread = None
        self.peak_rss = 0
        self.min_available = float("inf")

    def _sample(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)
                self.min_available = min(self.min_available, psutil.virtual_memory().available)
            except (psutil.Error, OSError):
                pass

    def __enter__(self):
        self.peak_rss = self.process.memory_info().rss
        self.min_available = psutil.virtual_memory().available
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_event.set()
        self.thread.join(timeout=2)
        self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)
        self.min_available = min(self.min_available, psutil.virtual_memory().available)


def model_settings(seed: int, n_jobs: int = 3):
    return dict(
        objective="multiclass", num_class=4, n_estimators=N_ESTIMATORS,
        learning_rate=0.01, num_leaves=127, min_child_samples=10,
        colsample_bytree=0.6, subsample=0.8, subsample_freq=1,
        reg_lambda=1.0, random_state=int(seed), n_jobs=int(n_jobs),
        verbosity=-1, metric="None",
    )


def run_condition(condition_name: str, output_root: Path, artifact_dir: Path,
                  n_jobs: int = 3, force: bool = False) -> dict:
    if condition_name not in CONDITIONS:
        raise ValueError(f"condition must be one of {list(CONDITIONS)}")
    condition = CONDITIONS[condition_name]
    out_dir = output_root / condition_name
    model_dir = out_dir / "models"
    seed_pred_dir = out_dir / "seed_predictions"
    model_dir.mkdir(parents=True, exist_ok=True)
    seed_pred_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "model_runs.jsonl"
    if force and log_path.exists():
        log_path.unlink()

    started_at = utc_now()
    t_all = time.perf_counter()
    mem_before = psutil.virtual_memory()
    process = psutil.Process(os.getpid())
    model_records = []
    fold_inner_frames = []
    fold_outer_frames = []
    fold_summaries = {}
    hashes_by_fold = {}
    input_hashes_by_fold = {}

    for fold in FOLDS:
        fold_data = load_fold(fold, artifact_dir)
        if fold_data.X.shape != (len(fold_data.rfid_ids), N_FEATURES):
            raise ValueError(f"fold {fold}: not the frozen 304-column matrix")
        feature_artifact = artifact_dir / f"fold_{fold}_features.npz"
        current_input_hashes = fold_input_hashes(fold_data, feature_artifact)
        input_hashes_by_fold[str(fold)] = current_input_hashes
        fit_mask = fold_data.roles == "FIT"
        inner_mask = fold_data.roles == "INNER"
        outer_mask = fold_data.roles == "OUTER"
        if not (fit_mask.any() and inner_mask.any() and outer_mask.any()):
            raise ValueError(f"fold {fold}: missing FIT/INNER/OUTER rows")
        if len(np.unique(fold_data.rfid_ids[fit_mask])) != int(fit_mask.sum()):
            raise ValueError(f"fold {fold}: duplicate FIT ship ids")
        fit_y = fold_data.y[fit_mask]
        if condition.sample_weight == "sqrt":
            sample_weight = sqrt_sample_weights(fit_y)
        else:
            sample_weight = np.ones(len(fit_y), dtype=np.float64)
        if sample_weight.shape != fit_y.shape or not np.isfinite(sample_weight).all():
            raise ValueError("sample weights do not align with FIT rows")
        X_fit = fold_data.X[fit_mask]
        X_inner = fold_data.X[inner_mask]
        X_outer = fold_data.X[outer_mask]
        y_inner = fold_data.y[inner_mask]
        inner_ids = fold_data.rfid_ids[inner_mask]
        outer_ids = fold_data.rfid_ids[outer_mask]
        inner_probs_by_seed = []
        outer_probs_by_seed = []
        fold_records = []
        fold_t0 = time.perf_counter()

        for seed in SEEDS:
            seed_path = seed_pred_dir / f"fold_{fold}_seed_{seed}.npz"
            model_path = model_dir / f"fold_{fold}_seed_{seed}.txt"
            cached = False
            cache_validation = None
            if seed_path.is_file() and model_path.is_file() and not force:
                with np.load(seed_path, allow_pickle=False) as saved:
                    saved_name = str(saved["condition"].item())
                    saved_seed = int(saved["seed"])
                    if saved_name == condition_name and saved_seed == seed:
                        ip = validate_probabilities(saved["inner_probs"], n_rows=int(inner_mask.sum()))
                        op = validate_probabilities(saved["outer_probs"], n_rows=int(outer_mask.sum()))
                        if np.array_equal(saved["inner_ids"].astype(str), inner_ids.astype(str)) and np.array_equal(saved["outer_ids"].astype(str), outer_ids.astype(str)):
                            cache_validation = cache_input_validation(
                                saved, out_dir / "run_report.json", condition_name,
                                fold, seed, current_input_hashes, model_path,
                            )
                            cached = cache_validation is not None
                            if cached:
                                best_iter = int(saved["best_iteration"])
                                model_hash = sha256_file(model_path)
                                elapsed = float(saved["fit_seconds"])
                                resource_record = json.loads(str(saved["resource_json"].item()))
                if cached:
                    inner_probs_by_seed.append(ip)
                    outer_probs_by_seed.append(op)
                    record = {"fold": fold, "seed": seed, "condition": condition_name,
                              "cached_resume": True, "best_iteration": best_iter,
                              "cache_validation": cache_validation,
                              "fit_seconds": elapsed, "model_path": str(model_path),
                              "model_sha256": model_hash, **resource_record}
                    model_records.append(record)
                    fold_records.append(record)
                    continue

            t_seed = time.perf_counter()
            rss_start_bytes = int(process.memory_info().rss)
            sampler = ResourceSampler()
            try:
                with sampler:
                    model = lgb.LGBMClassifier(**model_settings(seed, n_jobs=n_jobs))
                    model.fit(
                        X_fit, fit_y, sample_weight=sample_weight,
                        eval_set=[(X_inner, y_inner)],
                        eval_metric=lightgbm_eval_metric(condition.early_stop_metric),
                        callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS,
                                                      first_metric_only=True, verbose=False)],
                    )
                    model_classes = np.asarray(model.classes_, dtype=np.int64)
                    if not np.array_equal(model_classes, np.arange(4)):
                        raise ValueError(f"fold {fold} seed {seed}: model classes {model_classes.tolist()}")
                    inner_p = validate_probabilities(model.predict_proba(X_inner), n_rows=len(inner_ids))
                    outer_p = validate_probabilities(model.predict_proba(X_outer), n_rows=len(outer_ids))
                    best_iter = int(model.best_iteration_ or N_ESTIMATORS)
                    model.booster_.save_model(str(model_path))
                elapsed = time.perf_counter() - t_seed
                model_hash = sha256_file(model_path)
                resource_record = {
                    "rss_start_bytes": rss_start_bytes,
                    "rss_peak_bytes": int(sampler.peak_rss),
                    "available_ram_min_bytes": int(sampler.min_available),
                    "available_ram_after_bytes": int(psutil.virtual_memory().available),
                }
                np.savez_compressed(
                    seed_path, condition=np.asarray(condition_name), seed=np.int64(seed),
                    best_iteration=np.int64(best_iter), fit_seconds=np.float64(elapsed),
                    inner_ids=inner_ids.astype(str), outer_ids=outer_ids.astype(str),
                    inner_probs=inner_p, outer_probs=outer_p,
                    input_hashes_json=np.asarray(json.dumps(current_input_hashes, sort_keys=True)),
                    resource_json=np.asarray(json.dumps(resource_record)),
                )
                del model
                gc.collect()
            except Exception as exc:
                failure = {"condition": condition_name, "fold": fold, "seed": seed,
                           "failed_at": utc_now(), "error_type": type(exc).__name__,
                           "error": str(exc), "elapsed_seconds": time.perf_counter() - t_seed,
                           "available_ram_bytes": int(psutil.virtual_memory().available)}
                write_json(out_dir / "failure.json", failure)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(failure, ensure_ascii=False) + "\n")
                raise

            resource_record = {
                "rss_peak_bytes": int(sampler.peak_rss),
                "available_ram_min_bytes": int(sampler.min_available),
                "available_ram_after_bytes": int(psutil.virtual_memory().available),
            }
            record = {"fold": fold, "seed": seed, "condition": condition_name,
                      "cached_resume": False, "best_iteration": best_iter,
                      "fit_seconds": elapsed, "model_path": str(model_path),
                      "model_sha256": model_hash, **resource_record}
            model_records.append(record)
            fold_records.append(record)
            inner_probs_by_seed.append(inner_p)
            outer_probs_by_seed.append(outer_p)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[{utc_now()}] condition={condition_name} fold={fold} seed={seed} "
                  f"best_iter={best_iter} seconds={elapsed:.1f} "
                  f"rss_peak_GiB={sampler.peak_rss / 2**30:.3f} "
                  f"available_min_GiB={sampler.min_available / 2**30:.3f}", flush=True)

        inner_mean = validate_probabilities(np.mean(inner_probs_by_seed, axis=0), n_rows=int(inner_mask.sum()))
        outer_mean = validate_probabilities(np.mean(outer_probs_by_seed, axis=0), n_rows=int(outer_mask.sum()))
        inner_frame = prediction_frame(inner_ids, fold, "INNER", y_inner, inner_mean)
        outer_frame = prediction_frame(outer_ids, fold, "OUTER", fold_data.y[outer_mask], outer_mean)
        fold_inner_frames.append(inner_frame)
        fold_outer_frames.append(outer_frame)
        inner_metrics = metrics(y_inner, inner_mean.argmax(axis=1))
        outer_metrics = metrics(fold_data.y[outer_mask], outer_mean.argmax(axis=1))
        fold_summaries[str(fold)] = {
            "n_fit": int(fit_mask.sum()), "n_inner": int(inner_mask.sum()),
            "n_outer": int(outer_mask.sum()), "fit_seconds": float(sum(x["fit_seconds"] for x in fold_records)),
            "best_iterations": [int(x["best_iteration"]) for x in fold_records],
            "inner_metrics": inner_metrics, "outer_metrics": outer_metrics,
            "inner_obs_days": obs_days_metrics(y_inner, inner_mean.argmax(axis=1), fold_data.obs_days[inner_mask]),
            "outer_obs_days": obs_days_metrics(fold_data.y[outer_mask], outer_mean.argmax(axis=1), fold_data.obs_days[outer_mask]),
        }
        hashes_by_fold[str(fold)] = sha256_file(artifact_dir / f"fold_{fold}_features.npz")
        print(f"[{utc_now()}] fold={fold} condition={condition_name} complete; "
              f"outer_micro={outer_metrics['micro_f1']:.6f} "
              f"outer_macro_f1={outer_metrics['macro_f1']:.6f} "
              f"elapsed={time.perf_counter() - fold_t0:.1f}s", flush=True)
        del fold_data, X_fit, X_inner, X_outer, inner_p, outer_p
        gc.collect()

    inner_all = pd.concat(fold_inner_frames, ignore_index=True)
    outer_all = pd.concat(fold_outer_frames, ignore_index=True)
    if outer_all["rfid_id"].duplicated().any():
        raise ValueError("outer OOF predictions must contain one row per development vessel")
    if len(outer_all) != 5897:
        raise ValueError(f"expected 5897 outer OOF predictions, got {len(outer_all)}")
    inner_path = out_dir / "inner_predictions.csv"
    outer_path = out_dir / "outer_predictions.csv"
    all_path = out_dir / "predictions.csv"
    inner_all.to_csv(inner_path, index=False, encoding="utf-8")
    outer_all.to_csv(outer_path, index=False, encoding="utf-8")
    pd.concat([inner_all, outer_all], ignore_index=True).to_csv(all_path, index=False, encoding="utf-8")

    outer_metrics = metrics(outer_all["y_true"].to_numpy(), outer_all["pred"].to_numpy())
    outer_obs_days = {}
    for fold in FOLDS:
        fold_data = load_fold(fold, artifact_dir)
        mask = fold_data.roles == "OUTER"
        outer_obs_days.update({str(rid): float(days)
                               for rid, days in zip(fold_data.rfid_ids[mask], fold_data.obs_days[mask])})
        del fold_data
    pooled_outer_days = np.asarray([outer_obs_days[str(r)] for r in outer_all["rfid_id"]], dtype=np.float64)
    outer_by_obs_days = obs_days_metrics(outer_all["y_true"].to_numpy(), outer_all["pred"].to_numpy(), pooled_outer_days)
    mem_after = psutil.virtual_memory()
    source_validation_path = TASK / "reports" / "exp01" / "data_validation.json"
    source_validation = json.loads(source_validation_path.read_text(encoding="utf-8"))
    config = {
        "condition": condition.as_dict(), "n_estimators": N_ESTIMATORS,
        "learning_rate": 0.01, "num_leaves": 127, "min_child_samples": 10,
        "colsample_bytree": 0.6, "subsample": 0.8, "subsample_freq": 1,
        "reg_lambda": 1.0, "n_jobs": n_jobs, "early_stopping_rounds": EARLY_STOPPING_ROUNDS,
        "seeds": list(SEEDS), "folds": list(FOLDS), "feature_count": N_FEATURES,
        "decision_rule": "raw argmax; w=1.0; no post-hoc selection",
        "class_order": list(CLASS_NAMES),
    }
    report = {
        "experiment": "exp01", "condition": condition_name,
        "started_at_utc": started_at, "finished_at_utc": utc_now(),
        "elapsed_seconds": time.perf_counter() - t_all,
        "command": [sys.executable, *sys.argv], "working_directory": str(Path.cwd()),
        "environment": {
            "python": sys.version, "platform": platform.platform(),
            "numpy": np.__version__, "pandas": pd.__version__, "lightgbm": lgb.__version__,
            "cpu_logical": os.cpu_count(), "ram_total_bytes": int(mem_before.total),
            "ram_available_before_bytes": int(mem_before.available),
            "ram_available_after_bytes": int(mem_after.available),
            "gpu_note": "AMD Radeon 780M; CUDA not assumed or used",
        },
        "model_config": config, "folds": fold_summaries,
        "source_input_hashes": source_validation["input_hashes"],
        "source_data_validation_sha256": sha256_file(source_validation_path),
        "source_split_validation": source_validation["split_validation"],
        "t5_cache_provenance": source_validation["t5_cache_provenance"],
        "outer_oof_metrics": outer_metrics,
        "outer_oof_obs_days": outer_by_obs_days,
        "models": model_records,
        "input_feature_artifact_sha256": hashes_by_fold,
        "fold_input_hashes": input_hashes_by_fold,
        "prediction_files": {},
    }
    for name, path in (("inner", inner_path), ("outer", outer_path), ("all", all_path)):
        report["prediction_files"][name] = {
            "path": str(path), "rows": int(len(inner_all) if name == "inner" else len(outer_all) if name == "outer" else len(inner_all) + len(outer_all)),
            "sha256": sha256_file(path),
        }
    report_path = out_dir / "run_report.json"
    write_json(report_path, report)
    print(f"[{utc_now()}] condition={condition_name} done seconds={report['elapsed_seconds']:.1f} "
          f"outer_micro={outer_metrics['micro_f1']:.6f} outer_macro_f1={outer_metrics['macro_f1']:.6f} "
          f"report={report_path}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, choices=sorted(CONDITIONS))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--threads", type=int, default=3, choices=(2, 3, 4))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    console_dir = args.output_root / args.condition
    console_dir.mkdir(parents=True, exist_ok=True)
    stdout_file = (console_dir / "stdout.log").open("a", encoding="utf-8", buffering=1)
    stderr_file = (console_dir / "stderr.log").open("a", encoding="utf-8", buffering=1)
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = TeeStream(sys.__stdout__, stdout_file)
    sys.stderr = TeeStream(sys.__stderr__, stderr_file)
    try:
        run_condition(args.condition, args.output_root, args.artifact_dir, args.threads, args.force)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        sys.stdout, sys.stderr = old_stdout, old_stderr
        stdout_file.close()
        stderr_file.close()

if __name__ == "__main__":
    main()
