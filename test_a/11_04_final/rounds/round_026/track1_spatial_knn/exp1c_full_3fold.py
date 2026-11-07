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

BASE_FEATURES_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
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


def run_full_3fold_evaluation():
    track1_utils.record_resource_check("exp1c_full_3fold_start", expected_peak_mb=350.0)
    print("=== [Experiment 1C] Full 3-Fold INNER & OUTER 5,897 Evaluation ===")

    start_time = time.perf_counter()
    extractor = hellinger_knn.HellingerKnnFeatureExtractor()

    variant_names = ["baseline", "lgb_knn_std", "lgb_knn_sqrt", "knn_k15"]

    fold_outer_probs = {var: {} for var in variant_names}
    fold_inner_probs = {var: [] for var in variant_names}
    outer_y_dict = {}
    inner_y_list = []

    for fold_idx in [0, 1, 2]:
        track1_utils.record_resource_check(f"exp1c_fold{fold_idx}_start", expected_peak_mb=350.0)
        print(f"\n==================== Processing Fold {fold_idx} ====================")

        z = np.load(BASE_FEATURES_DIR / f"fold_{fold_idx}_features.npz")
        rfid_ids = z["rfid_ids"].astype(str)
        y = z["y"].astype(np.int64)
        roles = z["roles"].astype(str)
        X = z["X"]
        del z
        gc.collect()

        fit_mask = roles == "FIT"
        inner_mask = roles == "INNER"
        outer_mask = roles == "OUTER"

        fit_ids = rfid_ids[fit_mask]
        fit_y = y[fit_mask]
        fit_X = X[fit_mask]

        inner_ids = rfid_ids[inner_mask]
        inner_y = y[inner_mask]
        inner_X = X[inner_mask]
        inner_y_list.append(inner_y)

        outer_ids = rfid_ids[outer_mask]
        outer_y = y[outer_mask]
        outer_X = X[outer_mask]

        for vid, yt in zip(outer_ids, outer_y):
            outer_y_dict[vid] = yt

        print(f"  FIT: {len(fit_y)}, INNER: {len(inner_y)}, OUTER: {len(outer_y)}")

        # 1. Extract kNN features (strict leak-free: gallery = FIT only)
        # FIT queries use Leave-One-Out (self-distance = inf)
        knn_fit = extractor.extract_features(
            query_ids=fit_ids,
            gallery_ids=fit_ids,
            gallery_labels=fit_y,
            is_leave_one_out=True,
        )
        knn_inner = extractor.extract_features(
            query_ids=inner_ids,
            gallery_ids=fit_ids,
            gallery_labels=fit_y,
            is_leave_one_out=False,
        )
        knn_outer = extractor.extract_features(
            query_ids=outer_ids,
            gallery_ids=fit_ids,
            gallery_labels=fit_y,
            is_leave_one_out=False,
        )

        p_knn_inner = knn_inner[:, 4:8]
        p_knn_outer = knn_outer[:, 4:8]

        fold_inner_probs["knn_k15"].append(p_knn_inner)
        for vid, p in zip(outer_ids, p_knn_outer):
            fold_outer_probs["knn_k15"][vid] = p

        # 2. Train Variant 1: Baseline (304 feat, standard LGB)
        clf_base = lgb.LGBMClassifier(**LGB_PARAMS)
        clf_base.fit(fit_X.astype(np.float32), fit_y)
        p_base_inner = clf_base.predict_proba(inner_X.astype(np.float32)).astype(np.float32)
        p_base_outer = clf_base.predict_proba(outer_X.astype(np.float32)).astype(np.float32)
        del clf_base
        gc.collect()

        fold_inner_probs["baseline"].append(p_base_inner)
        for vid, p in zip(outer_ids, p_base_outer):
            fold_outer_probs["baseline"][vid] = p

        # 3. Concatenate kNN features (304 + 22 = 326 cols)
        train_X_cand = np.concatenate([fit_X, knn_fit], axis=1).astype(np.float32)
        inner_X_cand = np.concatenate([inner_X, knn_inner], axis=1).astype(np.float32)
        outer_X_cand = np.concatenate([outer_X, knn_outer], axis=1).astype(np.float32)

        del fit_X, inner_X, outer_X, knn_fit, knn_inner, knn_outer
        gc.collect()

        # 4. Train Variant 2: LGB + kNN features (standard)
        clf_knn_std = lgb.LGBMClassifier(**LGB_PARAMS)
        clf_knn_std.fit(train_X_cand, fit_y)
        p_std_inner = clf_knn_std.predict_proba(inner_X_cand).astype(np.float32)
        p_std_outer = clf_knn_std.predict_proba(outer_X_cand).astype(np.float32)
        del clf_knn_std
        gc.collect()

        fold_inner_probs["lgb_knn_std"].append(p_std_inner)
        for vid, p in zip(outer_ids, p_std_outer):
            fold_outer_probs["lgb_knn_std"][vid] = p

        # 5. Train Variant 3: LGB + kNN features (sqrt_macro)
        counts = np.bincount(fit_y, minlength=4)
        w = np.sqrt(len(fit_y) / (4.0 * counts))
        w /= w.mean()
        params_sqrt = dict(LGB_PARAMS)
        params_sqrt["class_weight"] = {c: float(w[c]) for c in range(4)}

        clf_knn_sqrt = lgb.LGBMClassifier(**params_sqrt)
        clf_knn_sqrt.fit(train_X_cand, fit_y)
        p_sqrt_inner = clf_knn_sqrt.predict_proba(inner_X_cand).astype(np.float32)
        p_sqrt_outer = clf_knn_sqrt.predict_proba(outer_X_cand).astype(np.float32)
        del clf_knn_sqrt, train_X_cand, inner_X_cand, outer_X_cand
        gc.collect()

        fold_inner_probs["lgb_knn_sqrt"].append(p_sqrt_inner)
        for vid, p in zip(outer_ids, p_sqrt_outer):
            fold_outer_probs["lgb_knn_sqrt"][vid] = p

        m_base_f = track1_utils.calc_metrics(outer_y, np.argmax(p_base_outer, axis=1))
        m_sqrt_f = track1_utils.calc_metrics(outer_y, np.argmax(p_sqrt_outer, axis=1))
        print(f"  Fold {fold_idx} OUTER Baseline: {m_base_f['correct']}/{len(outer_y)} ({m_base_f['micro_f1']:.4f}), Macro-F1: {m_base_f['macro_f1']:.4f}")
        print(f"  Fold {fold_idx} OUTER LGB+kNN (sqrt): {m_sqrt_f['correct']}/{len(outer_y)} ({m_sqrt_f['micro_f1']:.4f}), Macro-F1: {m_sqrt_f['macro_f1']:.4f}")

    elapsed = time.perf_counter() - start_time
    print(f"\nAll 3 folds processed in {elapsed:.1f}s.")

    # Format arrays for all 5,897 vessels
    sorted_vids = np.array(sorted(outer_y_dict.keys()))
    y_true_outer = np.array([outer_y_dict[vid] for vid in sorted_vids], dtype=np.int64)

    probs_matrix = {}
    for var in variant_names:
        probs_matrix[var] = np.array([fold_outer_probs[var][vid] for vid in sorted_vids], dtype=np.float32)

    configurations = {
        "1_baseline_304": probs_matrix["baseline"],
        "2_knn_standalone_k15": probs_matrix["knn_k15"],
        "3_lgb_knn_standard": probs_matrix["lgb_knn_std"],
        "4_lgb_knn_sqrt_macro": probs_matrix["lgb_knn_sqrt"],
        # Blends: Baseline + kNN
        "5_blend_base_knn_w15": 0.85 * probs_matrix["baseline"] + 0.15 * probs_matrix["knn_k15"],
        "6_blend_base_knn_w25": 0.75 * probs_matrix["baseline"] + 0.25 * probs_matrix["knn_k15"],
        "7_blend_base_knn_w30": 0.70 * probs_matrix["baseline"] + 0.30 * probs_matrix["knn_k15"],
        "8_blend_base_knn_w40": 0.60 * probs_matrix["baseline"] + 0.40 * probs_matrix["knn_k15"],
        "9_blend_base_knn_w50": 0.50 * probs_matrix["baseline"] + 0.50 * probs_matrix["knn_k15"],
        # Blends: LGB_kNN_sqrt + kNN
        "10_blend_sqrt_knn_w15": 0.85 * probs_matrix["lgb_knn_sqrt"] + 0.15 * probs_matrix["knn_k15"],
        "11_blend_sqrt_knn_w25": 0.75 * probs_matrix["lgb_knn_sqrt"] + 0.25 * probs_matrix["knn_k15"],
        "12_blend_sqrt_knn_w30": 0.70 * probs_matrix["lgb_knn_sqrt"] + 0.30 * probs_matrix["knn_k15"],
    }

    print("\n" + "=" * 80)
    print("=== GLOBAL OUTER 5,897 COMPREHENSIVE BENCHMARK ===")
    print("=" * 80)

    summary_table = []
    base_correct = -1

    for name, p in configurations.items():
        pred = np.argmax(p, axis=1)
        m = track1_utils.calc_metrics(y_true_outer, pred)

        tp0 = m["tp"][0]
        tp3 = m["tp"][3]
        rule_tp0 = tp0 >= 2389
        rule_tp3 = tp3 >= 90

        if name == "1_baseline_304":
            base_correct = m["correct"]

        row = {
            "name": name,
            "correct": m["correct"],
            "micro_f1": round(m["micro_f1"], 6),
            "macro_f1": round(m["macro_f1"], 6),
            "class_f1": [round(x, 4) for x in m["class_f1"]],
            "tp": m["tp"],
            "tp0": tp0,
            "tp3": tp3,
            "rule_tp0_pass": bool(rule_tp0),
            "rule_tp3_pass": bool(rule_tp3),
            "all_rules_pass": bool(rule_tp0 and rule_tp3),
            "delta_vs_baseline": m["correct"] - base_correct,
        }
        summary_table.append(row)

        print(f"[{name}] Correct: {m['correct']} / 5897 ({m['micro_f1']*100:.2f}%), Macro-F1: {m['macro_f1']:.4f}")
        print(f"  TP: {m['tp']} | TP0>=2389: {'PASS' if rule_tp0 else 'FAIL'} ({tp0}) | TP3>=90: {'PASS' if rule_tp3 else 'FAIL'} ({tp3})")
        print(f"  Class F1: {row['class_f1']}")

    # Select best candidate by maximum correct
    best_candidate_row = max(summary_table, key=lambda r: (r["correct"], r["macro_f1"]))
    best_candidate_name = best_candidate_row["name"]

    print("\n" + "=" * 80)
    print(f"SELECTED BEST CANDIDATE (ACCURACY OPTIMAL): {best_candidate_name}")
    print(f"Correct: {best_candidate_row['correct']} / 5897 (Delta vs Baseline: {best_candidate_row['delta_vs_baseline']:+d})")
    print(f"Macro-F1: {best_candidate_row['macro_f1']:.6f}")
    print(f"TP Distribution: {best_candidate_row['tp']}")
    print("=" * 80)

    # Threshold calibration exploration to meet protection rules TP0 >= 2389 and TP3 >= 90
    print("\n=== Threshold Calibration for Protection Conditions (TP0 >= 2389, TP3 >= 90) ===")
    p_best = configurations[best_candidate_name]
    best_calib = None
    best_calib_correct = -1

    # Grid search on class multipliers [m0, 1.0, 1.0, m3]
    for m0 in [1.0, 1.02, 1.04, 1.06, 1.08, 1.10]:
        for m3 in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6]:
            multipliers = np.array([m0, 1.0, 1.0, m3], dtype=np.float32)
            calib_p = p_best * multipliers
            calib_pred = np.argmax(calib_p, axis=1)
            cm = track1_utils.calc_metrics(y_true_outer, calib_pred)
            tp0_c = cm["tp"][0]
            tp3_c = cm["tp"][3]
            if tp0_c >= 2389 and tp3_c >= 90:
                if cm["correct"] > best_calib_correct:
                    best_calib_correct = cm["correct"]
                    best_calib = {
                        "multipliers": [m0, 1.0, 1.0, m3],
                        "metrics": cm,
                        "tp0": tp0_c,
                        "tp3": tp3_c,
                    }

    if best_calib:
        m_c = best_calib["metrics"]
        print(f"Found Calibrated Operating Point:")
        print(f"  Multipliers: {best_calib['multipliers']}")
        print(f"  Correct: {m_c['correct']} / 5897 ({m_c['micro_f1']*100:.2f}%), Macro-F1: {m_c['macro_f1']:.4f}")
        print(f"  TP: {m_c['tp']} | TP0: {best_calib['tp0']} (>=2389: PASS) | TP3: {best_calib['tp3']} (>=90: PASS)")
    else:
        print("  Notice: No simple linear threshold multiplier met both TP0>=2389 and TP3>=90 without sacrificing accuracy.")

    # Save the selected best candidate probabilities
    selected_probs = configurations[best_candidate_name]
    npz_path = OUT_DIR / "probabilities_track1.npz"

    # Determine inner probabilities corresponding to best blend
    if "blend" in best_candidate_name:
        if "base" in best_candidate_name:
            w = float(best_candidate_name.split("_w")[-1]) / 100.0
            inner_probs_final = [
                (1.0 - w) * p_base + w * p_knn
                for p_base, p_knn in zip(fold_inner_probs["baseline"], fold_inner_probs["knn_k15"])
            ]
        else:
            w = float(best_candidate_name.split("_w")[-1]) / 100.0
            inner_probs_final = [
                (1.0 - w) * p_sqrt + w * p_knn
                for p_sqrt, p_knn in zip(fold_inner_probs["lgb_knn_sqrt"], fold_inner_probs["knn_k15"])
            ]
    elif best_candidate_name == "4_lgb_knn_sqrt_macro":
        inner_probs_final = fold_inner_probs["lgb_knn_sqrt"]
    elif best_candidate_name == "3_lgb_knn_standard":
        inner_probs_final = fold_inner_probs["lgb_knn_std"]
    else:
        inner_probs_final = fold_inner_probs["baseline"]

    save_dict = {
        "vessel_ids": sorted_vids,
        "outer_probs": selected_probs,
        "y_true": y_true_outer,
        "inner_probs_fold0": inner_probs_final[0],
        "inner_probs_fold1": inner_probs_final[1],
        "inner_probs_fold2": inner_probs_final[2],
    }
    if best_calib:
        calib_multipliers = np.array(best_calib["multipliers"], dtype=np.float32)
        save_dict["outer_probs_calibrated"] = selected_probs * calib_multipliers
        save_dict["calibration_multipliers"] = calib_multipliers

    np.savez_compressed(npz_path, **save_dict)
    print(f"\nSaved track1 probabilities to: {npz_path}")

    results_json = {
        "status": "track1_complete",
        "selected_best_candidate": best_candidate_name,
        "selected_metrics": best_candidate_row,
        "calibrated_protection_point": best_calib,
        "all_configurations": summary_table,
        "elapsed_seconds": round(elapsed, 2),
    }
    track1_utils.save_json(OUT_DIR / "track1_results.json", results_json)
    print(f"Saved results summary to: {OUT_DIR / 'track1_results.json'}")

    return results_json


if __name__ == "__main__":
    run_full_3fold_evaluation()
