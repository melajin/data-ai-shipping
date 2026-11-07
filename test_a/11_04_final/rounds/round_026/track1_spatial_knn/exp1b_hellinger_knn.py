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
import hellinger_knn

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


def run_experiment_1b():
    track1_utils.record_resource_check("exp1b_start", expected_peak_mb=350.0)
    print("=== [Experiment 1B] Vessel-to-Vessel Hellinger kNN Evaluation ===")

    # 1. Load fold 0 FIT baseline
    z_f0 = np.load(FOLD0_FEATURES_PATH)
    fit_mask = z_f0["roles"] == "FIT"
    X_fit_orig = z_f0["X"][fit_mask]
    y_fit = z_f0["y"][fit_mask].astype(np.int64)
    rfid_fit = z_f0["rfid_ids"][fit_mask].astype(str)
    del z_f0
    gc.collect()

    n_fit = len(y_fit)

    # 2. Load 4-fold splits & pre-rebuilt T5 matrices
    splits = []
    for k in range(4):
        fe = np.load(EVIDENCE_DIR / f"fold_{k}_features.npz")
        splits.append({
            "tr": fe["train_indices"].astype(np.int64),
            "val": fe["valid_indices"].astype(np.int64),
            "t5": fe["t5_matrix"].astype(np.float64),
        })

    # 3. Initialize Hellinger kNN extractor
    print("Initializing Hellinger kNN feature extractor...")
    extractor = hellinger_knn.HellingerKnnFeatureExtractor()

    # Placeholders for 4-CV predictions
    # (a) Standalone kNN probabilities
    knn_k05_probs = np.full((n_fit, 4), np.nan, dtype=np.float32)
    knn_k15_probs = np.full((n_fit, 4), np.nan, dtype=np.float32)
    knn_k30_probs = np.full((n_fit, 4), np.nan, dtype=np.float32)
    knn_sp15_probs = np.full((n_fit, 4), np.nan, dtype=np.float32)

    # (b) LightGBM with 304 base + kNN features (standard & sqrt_macro)
    lgb_std_probs = np.full((n_fit, 4), np.nan, dtype=np.float32)
    lgb_sqrt_probs = np.full((n_fit, 4), np.nan, dtype=np.float32)

    # All fold kNN feature matrices
    all_knn_features = []

    print("\n--- Running 4-CV Feature Extraction & Model Fits ---")
    start_time = time.perf_counter()

    for k in range(4):
        tr = splits[k]["tr"]
        val = splits[k]["val"]
        t5_mat = splits[k]["t5"]
        track1_utils.record_resource_check(f"exp1b_cv{k}_start", expected_peak_mb=350.0)

        # Extract kNN features (query: all 3144 vessels; gallery: fold train FIT vessels)
        # Leave-one-out ensures that when query in tr, self is masked to inf.
        knn_mat = extractor.extract_features(
            query_ids=rfid_fit,
            gallery_ids=rfid_fit[tr],
            gallery_labels=y_fit[tr],
            is_leave_one_out=True,
        )
        all_knn_features.append(knn_mat)

        # (a) Store standalone kNN probabilities for val set
        knn_k05_probs[val] = knn_mat[val, 0:4]
        knn_k15_probs[val] = knn_mat[val, 4:8]
        knn_k30_probs[val] = knn_mat[val, 8:12]
        knn_sp15_probs[val] = knn_mat[val, 12:16]

        # Combine base features with kNN features (304 + 22 = 326 cols)
        X_base = X_fit_orig.copy()
        X_base[:, 156:166] = t5_mat.astype(X_base.dtype, copy=False)
        X_cand = np.concatenate([X_base, knn_mat], axis=1).astype(np.float32)
        del X_base
        gc.collect()

        # (b1) Standard LightGBM
        clf_std = lgb.LGBMClassifier(**LGB_PARAMS)
        clf_std.fit(X_cand[tr], y_fit[tr])
        lgb_std_probs[val] = clf_std.predict_proba(X_cand[val]).astype(np.float32)
        del clf_std
        gc.collect()

        # (b2) LightGBM with sqrt_macro class weights
        counts = np.bincount(y_fit[tr], minlength=4)
        w = np.sqrt(len(tr) / (4.0 * counts))
        w /= w.mean()
        cw_dict = {c: float(w[c]) for c in range(4)}

        params_sqrt = dict(LGB_PARAMS)
        params_sqrt["class_weight"] = cw_dict
        clf_sqrt = lgb.LGBMClassifier(**params_sqrt)
        clf_sqrt.fit(X_cand[tr], y_fit[tr])
        lgb_sqrt_probs[val] = clf_sqrt.predict_proba(X_cand[val]).astype(np.float32)
        del clf_sqrt, X_cand
        gc.collect()

        print(f"  Fold {k} complete. (tr={len(tr)}, val={len(val)})")

    elapsed = time.perf_counter() - start_time
    print(f"All 4 folds finished in {elapsed:.1f}s.")

    # 4. Evaluate (a) Standalone kNN Models
    print("\n=== (a) Standalone kNN Performance ===")
    knn_results = {}
    for name, p in [
        ("knn_k05", knn_k05_probs),
        ("knn_k15", knn_k15_probs),
        ("knn_k30", knn_k30_probs),
        ("knn_spatial_k15", knn_sp15_probs),
    ]:
        pred = np.argmax(p, axis=1)
        m = track1_utils.calc_metrics(y_fit, pred)
        m["delta_vs_baseline_1811"] = m["correct"] - 1811
        knn_results[name] = m
        print(f"[{name}] Correct: {m['correct']} / 3144 ({m['micro_f1']*100:.2f}%), Macro-F1: {m['macro_f1']:.4f}")
        print(f"  Class F1: {[round(x, 4) for x in m['class_f1']]}")

    # 5. Evaluate (b) LightGBM + kNN Features
    print("\n=== (b) LightGBM + kNN Features Performance ===")
    lgb_knn_results = {}
    for name, p in [
        ("lgb_knn_standard", lgb_std_probs),
        ("lgb_knn_sqrt_macro", lgb_sqrt_probs),
    ]:
        pred = np.argmax(p, axis=1)
        m = track1_utils.calc_metrics(y_fit, pred)
        m["delta_vs_baseline_1811"] = m["correct"] - 1811
        lgb_knn_results[name] = m
        print(f"[{name}] Correct: {m['correct']} / 3144 ({m['micro_f1']*100:.2f}%), Macro-F1: {m['macro_f1']:.4f}")
        print(f"  Delta vs Baseline (1811): {m['delta_vs_baseline_1811']:+d}")
        print(f"  Class F1: {[round(x, 4) for x in m['class_f1']]}")

    # 6. Evaluate (c) Probability Blending
    # Load Round 025 baseline probabilities to test blending with original LightGBM baseline
    base_pred_npz = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_025\artifacts\gate\predictions_baseline.npz")
    with np.load(base_pred_npz) as z:
        lgb_base_probs = z["proba"].astype(np.float32)

    print("\n=== (c) Blending: Base LightGBM + kNN Probs ===")
    blend_results = {}
    best_blend = {"weight_knn": 0.0, "correct": 1811, "macro_f1": 0.4913}
    for w_knn in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
        p_blend = (1.0 - w_knn) * lgb_base_probs + w_knn * knn_k15_probs
        pred_blend = np.argmax(p_blend, axis=1)
        m_b = track1_utils.calc_metrics(y_fit, pred_blend)
        m_b["delta_vs_baseline_1811"] = m_b["correct"] - 1811
        blend_results[f"blend_w_knn_{int(w_knn*100):02d}"] = m_b
        print(f"[w_knn={w_knn:.2f}] Correct: {m_b['correct']} / 3144 ({m_b['micro_f1']*100:.2f}%), Macro-F1: {m_b['macro_f1']:.4f}, Delta: {m_b['delta_vs_baseline_1811']:+d}")
        if m_b["correct"] > best_blend["correct"] or (m_b["correct"] == best_blend["correct"] and m_b["macro_f1"] > best_blend["macro_f1"]):
            best_blend = {"weight_knn": w_knn, "correct": m_b["correct"], "macro_f1": m_b["macro_f1"]}

    # Also blend LGB+kNN model with kNN probs
    print("\n=== Blending: LGB_kNN_standard + kNN Probs ===")
    for w_knn in [0.0, 0.05, 0.10, 0.15, 0.20]:
        p_blend = (1.0 - w_knn) * lgb_std_probs + w_knn * knn_k15_probs
        pred_blend = np.argmax(p_blend, axis=1)
        m_b = track1_utils.calc_metrics(y_fit, pred_blend)
        m_b["delta_vs_baseline_1811"] = m_b["correct"] - 1811
        blend_results[f"lgb_knn_blend_w_{int(w_knn*100):02d}"] = m_b
        print(f"[LGB_kNN + w_knn={w_knn:.2f}] Correct: {m_b['correct']}, Macro-F1: {m_b['macro_f1']:.4f}, Delta: {m_b['delta_vs_baseline_1811']:+d}")

    all_out = {
        "knn_standalone": knn_results,
        "lgb_knn_feature_models": lgb_knn_results,
        "blend_experiments": blend_results,
        "best_blend": best_blend,
        "elapsed_seconds": round(elapsed, 2),
    }

    track1_utils.save_json(OUT_DIR / "exp1b_results.json", all_out)
    print("\nExperiment 1B successfully finished and saved to exp1b_results.json!")


if __name__ == "__main__":
    run_experiment_1b()
