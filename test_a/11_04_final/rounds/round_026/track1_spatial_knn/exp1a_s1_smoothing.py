from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path
import numpy as np
import lightgbm as lgb

sys.path.append(str(Path(__file__).resolve().parent))
import track1_utils
import s1_features_fixed as s1_fixed

SQLITE_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_025\tmp\s1_profiles.sqlite")
EVIDENCE_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_025\artifacts\gate\feature_evidence")
FOLD0_FEATURES_PATH = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_0_features.npz")
OUT_DIR = Path(__file__).resolve().parent

LGB_PARAMS = {
    "objective": "multiclass",
    "num_class": 4,
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "colsample_bytree": 0.7,
    "subsample": 0.8,
    "subsample_freq": 1,
    "random_state": 42,
    "n_jobs": 1,
    "verbose": -1,
}


def run_experiment_1a():
    track1_utils.record_resource_check("exp1a_start", expected_peak_mb=350.0)
    print("=== [Experiment 1A] S1 Prior-Smoothing Fix Evaluation ===")

    # 1. Load fold 0 FIT baseline
    z_f0 = np.load(FOLD0_FEATURES_PATH)
    fit_mask = z_f0["roles"] == "FIT"
    X_fit_orig = z_f0["X"][fit_mask]
    y_fit = z_f0["y"][fit_mask].astype(np.int64)
    del z_f0
    gc.collect()

    n_fit = len(y_fit)
    all_fit_indices = np.arange(n_fit, dtype=np.int64)

    # Load 4-fold splits & pre-rebuilt T5 matrices
    splits = []
    for k in range(4):
        fe = np.load(EVIDENCE_DIR / f"fold_{k}_features.npz")
        splits.append({
            "tr": fe["train_indices"].astype(np.int64),
            "val": fe["valid_indices"].astype(np.int64),
            "t5": fe["t5_matrix"].astype(np.float64),
        })

    store = s1_fixed.S1ProfileStore(SQLITE_PATH)

    configs = [
        {"name": "fix_a2_min3", "alpha": 2.0, "min_vessels": 3, "include_excess": False},
        {"name": "fix_a5_min3", "alpha": 5.0, "min_vessels": 3, "include_excess": False},
        {"name": "fix_a2_min1", "alpha": 2.0, "min_vessels": 1, "include_excess": False},
        {"name": "fix_a2_min3_excess", "alpha": 2.0, "min_vessels": 3, "include_excess": True},
    ]

    results = {}

    for cfg in configs:
        cfg_name = cfg["name"]
        print(f"\n--- Testing Configuration: {cfg_name} (alpha={cfg['alpha']}, min_vessels={cfg['min_vessels']}, excess={cfg['include_excess']}) ---")
        track1_utils.record_resource_check(f"exp1a_{cfg_name}_start", expected_peak_mb=350.0)

        preds = np.full(n_fit, -1, dtype=np.int64)
        probs = np.full((n_fit, 4), np.nan, dtype=np.float32)

        start_time = time.perf_counter()
        for k in range(4):
            tr = splits[k]["tr"]
            val = splits[k]["val"]
            t5_mat = splits[k]["t5"]

            # Compute S1 fixed features for this fold
            s1_mat = s1_fixed.build_fixed_features(
                store, all_fit_indices, tr, y_fit[tr],
                alpha=cfg["alpha"],
                min_vessels=cfg["min_vessels"],
                include_excess=cfg["include_excess"],
            )

            # Build feature matrix
            X_base = X_fit_orig.copy()
            X_base[:, 156:166] = t5_mat.astype(X_base.dtype, copy=False)
            X_cand = np.concatenate((X_base, s1_mat), axis=1)
            del X_base, s1_mat
            gc.collect()

            clf = lgb.LGBMClassifier(**LGB_PARAMS)
            clf.fit(X_cand[tr], y_fit[tr])
            p_val = clf.predict_proba(X_cand[val]).astype(np.float32)
            probs[val] = p_val
            preds[val] = np.argmax(p_val, axis=1)

            del X_cand, clf, p_val
            gc.collect()

        elapsed = time.perf_counter() - start_time
        metrics = track1_utils.calc_metrics(y_fit, preds)
        metrics["elapsed_seconds"] = round(elapsed, 2)
        metrics["delta_vs_baseline_1811"] = metrics["correct"] - 1811
        metrics["delta_vs_buggy_1781"] = metrics["correct"] - 1781
        results[cfg_name] = metrics

        print(f"[{cfg_name}] Correct: {metrics['correct']} / 3144 ({metrics['micro_f1']*100:.2f}%), Macro-F1: {metrics['macro_f1']:.4f}")
        print(f"  Delta vs Baseline (1811): {metrics['delta_vs_baseline_1811']:+d}, Delta vs Buggy S1 (1781): {metrics['delta_vs_buggy_1781']:+d}")
        print(f"  Class F1: {[round(x, 4) for x in metrics['class_f1']]}")
        print(f"  Elapsed: {elapsed:.1f}s")

    track1_utils.save_json(OUT_DIR / "exp1a_results.json", results)
    print("\nExperiment 1A successfully finished and saved to exp1a_results.json!")


if __name__ == "__main__":
    run_experiment_1a()
