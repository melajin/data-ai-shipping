import csv
import gc
import json
import os
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from resource_guard import check_ram
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

def main():
    check_ram("detailed_inner_opt_start", expected_peak_mb=120.0)

    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)

    # Days
    tab_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation\seed_42")
    inner_days_map = {}
    for fold in FOLDS:
        with open(tab_dir / f"fold_{fold}" / "inner_predictions.csv", "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                inner_days_map[(fold, r["rfid_id"])] = float(r["observed_days"])
    inner_keys = [(r[0], r[2]) for r in inner_records]
    inner_days = np.array([inner_days_map[k] for k in inner_keys], dtype=np.float64)

    p_lgb42 = inner_probs["LightGBM_seed42"]
    p_lgb5 = inner_probs["LightGBM_5seed_sqrt_macro"]
    p_cat = inner_probs["CatBoost"]
    p_tab42 = inner_probs["TabICL_seed42"]
    p_tab26 = inner_probs["TabICL_seed2026"]

    # Candidate Blends
    blends = {
        "B1_LGB5_TAB42_50_50": 0.50 * p_lgb5 + 0.50 * p_tab42,
        "B2_LGB5_CAT_TAB42_45_10_45": 0.45 * p_lgb5 + 0.10 * p_cat + 0.45 * p_tab42,
        "B3_LGB5_CAT_TAB_BOTH_40_10_25_25": 0.40 * p_lgb5 + 0.10 * p_cat + 0.25 * p_tab42 + 0.25 * p_tab26,
        "B4_LGB42_TAB42_50_50": 0.50 * p_lgb42 + 0.50 * p_tab42,
        "B5_LGB42_CAT_TAB42_45_10_45": 0.45 * p_lgb42 + 0.10 * p_cat + 0.45 * p_tab42,
    }

    # Routed blend
    p_routed = np.zeros_like(p_lgb5)
    mask_short = inner_days <= 30
    mask_mid = (inner_days > 30) & (inner_days <= 90)
    mask_long = inner_days > 90
    p_routed[mask_short] = 0.40 * p_lgb5[mask_short] + 0.60 * p_tab42[mask_short]
    p_routed[mask_mid] = 0.35 * p_lgb5[mask_mid] + 0.15 * p_cat[mask_mid] + 0.50 * p_tab42[mask_mid]
    p_routed[mask_long] = 0.50 * p_lgb5[mask_long] + 0.20 * p_cat[mask_long] + 0.30 * p_tab42[mask_long]
    blends["B6_ROUTED_DAYS_LGB5_CAT_TAB"] = p_routed

    # Target constraints
    min_tp0 = 959
    min_tp3 = 36

    print("="*95)
    print("DETAILED INNER 3-FOLD CV EVALUATION FOR CANDIDATE BLENDS AND DECISION RULES")
    print(f"INNER N=2,361 (Support: C0={int((inner_y==0).sum())}, C1={int((inner_y==1).sum())}, C2={int((inner_y==2).sum())}, C3={int((inner_y==3).sum())})")
    print(f"Protection Target: TP0 >= {min_tp0}, TP3 >= {min_tp3}")
    print("="*95)

    header = f"{'Blend Name & Rule':<45} | {'Correct':<12} | {'micro-F1':<10} | {'macro-F1':<10} | {'TP(0,1,2,3)':<18} | {'PASS':<5}"
    print(header)
    print("-" * len(header))

    evaluation_records = []

    for blend_name, p_blend in blends.items():
        # Rule 0: Argmax baseline (no calibration)
        pred_r0 = p_blend.argmax(axis=1)
        m_r0 = compute_metrics(inner_y, pred_r0)
        pass_r0 = (m_r0["tp"][0] >= min_tp0) and (m_r0["tp"][3] >= min_tp3)
        tp_str = f"{m_r0['tp'][0]},{m_r0['tp'][1]},{m_r0['tp'][2]},{m_r0['tp'][3]}"
        label_r0 = f"{blend_name} [R0:Raw Argmax]"
        print(f"{label_r0:<45} | {m_r0['correct']:<4}/2361     | {m_r0['micro_f1']:.6f}   | {m_r0['macro_f1']:.6f}   | {tp_str:<18} | {str(pass_r0):<5}")
        evaluation_records.append({"name": label_r0, "blend": blend_name, "rule": "R0_Raw", "metrics": m_r0, "pass": pass_r0})

        # Rule 1: 3-fold OOF Multiplier Tuning with Balanced Objective (protecting TP0 and TP3 while maintaining TP1, TP2)
        oof_pred_r1 = np.zeros(len(inner_y), dtype=np.int64)
        fold_alphas_r1 = []
        for val_fold in FOLDS:
            train_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            y_tr, p_tr = inner_y[train_mask], p_blend[train_mask]
            y_val, p_val = inner_y[val_mask], p_blend[val_mask]

            tr_min_tp0 = int(round(min_tp0 * (train_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(min_tp3 * (train_mask.sum() / len(inner_y))))

            best_alpha = None
            best_score = -1

            # Grid for (a0, a2, a3)
            # Keeping a0 moderately bounded [1.00, 1.08] to avoid draining C1/C2, and a3 in [1.10, 1.35]
            for a0 in [1.00, 1.02, 1.04, 1.06, 1.08]:
                for a2 in [0.95, 1.00, 1.05, 1.10]:
                    for a3 in [1.10, 1.15, 1.20, 1.25, 1.30, 1.35]:
                        alpha = np.array([a0, 1.00, a2, a3], dtype=np.float64)
                        pred_tr = (p_tr * alpha).argmax(axis=1)
                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)

                        if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                            correct_tr = np.trace(cm_tr)
                            if correct_tr > best_score:
                                best_score = correct_tr
                                best_alpha = alpha
            if best_alpha is None:
                best_alpha = np.array([1.04, 1.00, 1.05, 1.25], dtype=np.float64)
            fold_alphas_r1.append(best_alpha)
            oof_pred_r1[val_mask] = (p_val * best_alpha).argmax(axis=1)

        m_r1 = compute_metrics(inner_y, oof_pred_r1)
        pass_r1 = (m_r1["tp"][0] >= min_tp0) and (m_r1["tp"][3] >= min_tp3)
        tp_str = f"{m_r1['tp'][0]},{m_r1['tp'][1]},{m_r1['tp'][2]},{m_r1['tp'][3]}"
        label_r1 = f"{blend_name} [R1:Prior Multiplier OOF]"
        print(f"{label_r1:<45} | {m_r1['correct']:<4}/2361     | {m_r1['micro_f1']:.6f}   | {m_r1['macro_f1']:.6f}   | {tp_str:<18} | {str(pass_r1):<5}")
        evaluation_records.append({
            "name": label_r1, "blend": blend_name, "rule": "R1_Multiplier",
            "metrics": m_r1, "pass": pass_r1, "mean_alpha": np.mean(fold_alphas_r1, axis=0).tolist(),
            "fold_alphas": [a.tolist() for a in fold_alphas_r1]
        })

        # Rule 2: Prior Multiplier + Class 3 High-Precision Gate
        # If P_lgb(3) >= tau_lgb or P_blend(3) >= tau_blend, predict 3
        oof_pred_r2 = np.zeros(len(inner_y), dtype=np.int64)
        fold_params_r2 = []
        lgb_source = p_lgb42 if "LGB42" in blend_name else p_lgb5

        for val_fold in FOLDS:
            train_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            y_tr, p_tr, lgb_tr = inner_y[train_mask], p_blend[train_mask], lgb_source[train_mask]
            y_val, p_val, lgb_val = inner_y[val_mask], p_blend[val_mask], lgb_source[val_mask]

            tr_min_tp0 = int(round(min_tp0 * (train_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(min_tp3 * (train_mask.sum() / len(inner_y))))

            best_param = None
            best_score = -1

            for a0 in [1.00, 1.02, 1.04]:
                for a2 in [1.00, 1.05]:
                    for tau3 in [0.25, 0.30, 0.35, 0.40]:
                        pred_tr = (p_tr * np.array([a0, 1.00, a2, 1.00])).argmax(axis=1)
                        # Gate
                        pred_tr[lgb_tr[:, 3] >= tau3] = 3

                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                        if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                            correct_tr = np.trace(cm_tr)
                            if correct_tr > best_score:
                                best_score = correct_tr
                                best_param = (a0, a2, tau3)
            if best_param is None:
                best_param = (1.02, 1.00, 0.30)
            fold_params_r2.append(best_param)

            # Predict val
            pred_v = (p_val * np.array([best_param[0], 1.00, best_param[1], 1.00])).argmax(axis=1)
            pred_v[lgb_val[:, 3] >= best_param[2]] = 3
            oof_pred_r2[val_mask] = pred_v

        m_r2 = compute_metrics(inner_y, oof_pred_r2)
        pass_r2 = (m_r2["tp"][0] >= min_tp0) and (m_r2["tp"][3] >= min_tp3)
        tp_str = f"{m_r2['tp'][0]},{m_r2['tp'][1]},{m_r2['tp'][2]},{m_r2['tp'][3]}"
        label_r2 = f"{blend_name} [R2:Gate+Multiplier OOF]"
        print(f"{label_r2:<45} | {m_r2['correct']:<4}/2361     | {m_r2['micro_f1']:.6f}   | {m_r2['macro_f1']:.6f}   | {tp_str:<18} | {str(pass_r2):<5}")
        evaluation_records.append({
            "name": label_r2, "blend": blend_name, "rule": "R2_Gate",
            "metrics": m_r2, "pass": pass_r2, "fold_params": fold_params_r2
        })

    # Save detailed inner results
    with open(Path(__file__).resolve().parent / "detailed_inner_optimization.json", "w", encoding="utf-8") as f:
        json.dump(evaluation_records, f, indent=2, ensure_ascii=False)

    gc.collect()
    check_ram("detailed_inner_opt_end", expected_peak_mb=120.0)
    print("\nDetailed inner optimization finished and saved to detailed_inner_optimization.json!")

if __name__ == "__main__":
    main()
