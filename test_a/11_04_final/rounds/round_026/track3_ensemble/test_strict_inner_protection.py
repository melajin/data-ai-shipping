import csv
import gc
import json
import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from resource_guard import check_ram
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

def main():
    check_ram("strict_inner_protection_start", expected_peak_mb=100.0)

    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)
    outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

    p_lgb5_in, p_lgb5_out = inner_probs["LightGBM_5seed_sqrt_macro"], outer_probs["LightGBM_5seed_sqrt_macro"]
    p_cat_in, p_cat_out = inner_probs["CatBoost"], outer_probs["CatBoost"]
    p_tab42_in, p_tab42_out = inner_probs["TabICL_seed42"], outer_probs["TabICL_seed42"]

    # Target constraints:
    # Class 0: OUTER target >= 2389 -> recall >= 2389/2920 = 81.815% -> INNER target = 958
    # Class 3: OUTER target >= 92   -> recall >= 92/126   = 73.016% -> INNER target = 38 (38/51 = 74.5%)
    target_tp0_inner = 958
    target_tp3_inner = 38

    print("="*95)
    print("TESTING STRICT INNER THRESHOLD TUNING (INNER TP3 >= 38, TP0 >= 958)")
    print("="*95)

    # Let's test on Blend B1 (50:50 LGB5:TAB42) and B2 (45:10:45 LGB5:CAT:TAB42)
    blends_in = {
        "B1_LGB5_TAB42": 0.50 * p_lgb5_in + 0.50 * p_tab42_in,
        "B2_LGB5_CAT_TAB42": 0.45 * p_lgb5_in + 0.10 * p_cat_in + 0.45 * p_tab42_in,
    }
    blends_out = {
        "B1_LGB5_TAB42": 0.50 * p_lgb5_out + 0.50 * p_tab42_out,
        "B2_LGB5_CAT_TAB42": 0.45 * p_lgb5_out + 0.10 * p_cat_out + 0.45 * p_tab42_out,
    }

    # Method 1: Prior Multiplier Search with a3 up to 1.6
    print("\n--- Method 1: Strict Multipliers (Grid search on INNER 3-fold CV) ---")
    for b_name in blends_in:
        p_in = blends_in[b_name]
        p_out = blends_out[b_name]

        oof_pred_in = np.zeros(len(inner_y), dtype=np.int64)
        fold_alphas = []

        for val_fold in FOLDS:
            tr_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            y_tr, p_tr = inner_y[tr_mask], p_in[tr_mask]
            y_val, p_val = inner_y[val_mask], p_in[val_mask]

            tr_min_tp0 = int(round(target_tp0_inner * (tr_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(target_tp3_inner * (tr_mask.sum() / len(inner_y))))

            best_alpha = None
            best_score = -1

            for a0 in [1.00, 1.02, 1.04, 1.06]:
                for a2 in [0.95, 1.00, 1.05]:
                    for a3 in np.linspace(1.15, 1.65, 21):
                        alpha = np.array([a0, 1.00, a2, a3], dtype=np.float64)
                        pred_tr = (p_tr * alpha).argmax(axis=1)
                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)

                        if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                            if np.trace(cm_tr) > best_score:
                                best_score = np.trace(cm_tr)
                                best_alpha = alpha
                                
            if best_alpha is None:
                # Relax slightly to tp3 >= tr_min_tp3 - 1
                for a0 in [1.00, 1.02, 1.04]:
                    for a3 in np.linspace(1.20, 1.60, 17):
                        alpha = np.array([a0, 1.00, 1.00, a3], dtype=np.float64)
                        pred_tr = (p_tr * alpha).argmax(axis=1)
                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                        if cm_tr[0, 0] >= tr_min_tp0:
                            score = np.trace(cm_tr) + 10 * cm_tr[3, 3]
                            if score > best_score:
                                best_score = score
                                best_alpha = alpha

            fold_alphas.append(best_alpha)
            oof_pred_in[val_mask] = (p_val * best_alpha).argmax(axis=1)

        m_in = compute_metrics(inner_y, oof_pred_in)
        mean_alpha = np.mean(fold_alphas, axis=0)
        print(f"\n{b_name} [Strict Multiplier]:")
        print(f"  Fold Alphas: {[[round(x, 3) for x in a] for a in fold_alphas]}")
        print(f"  Mean Alpha: {[round(x, 3) for x in mean_alpha]}")
        print(f"  INNER: Correct={m_in['correct']}/2361 ({m_in['micro_f1']:.6f}), TP={m_in['tp']}")

        # Apply strictly to OUTER
        # Fold-local
        pred_out_local = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            mask_f = (outer_folds == f)
            pred_out_local[mask_f] = (p_out[mask_f] * fold_alphas[f]).argmax(axis=1)
        m_out_local = compute_metrics(outer_y, pred_out_local)

        # Pooled mean
        pred_out_pooled = (p_out * mean_alpha).argmax(axis=1)
        m_out_pooled = compute_metrics(outer_y, pred_out_pooled)

        print(f"  OUTER (Fold-Local): Correct={m_out_local['correct']}/5897 ({m_out_local['micro_f1']:.6f}), TP={m_out_local['tp']}, PASS={m_out_local['tp'][0]>=2389 and m_out_local['tp'][3]>=92}")
        print(f"  OUTER (Pooled Mean): Correct={m_out_pooled['correct']}/5897 ({m_out_pooled['micro_f1']:.6f}), TP={m_out_pooled['tp']}, PASS={m_out_pooled['tp'][0]>=2389 and m_out_pooled['tp'][3]>=92}")

    # Method 2: Dual Gate Rule
    # If P_lgb(3) >= tau3 or P_blend(3) >= tau_blend, predict 3; else argmax(alpha * P_blend)
    print("\n--- Method 2: Dual Gate Rule (INNER 3-fold CV) ---")
    for b_name in blends_in:
        p_in = blends_in[b_name]
        p_out = blends_out[b_name]

        oof_pred_in = np.zeros(len(inner_y), dtype=np.int64)
        fold_params = []

        for val_fold in FOLDS:
            tr_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            y_tr, p_tr, lgb_tr = inner_y[tr_mask], p_in[tr_mask], p_lgb5_in[tr_mask]
            y_val, p_val, lgb_val = inner_y[val_mask], p_in[val_mask], p_lgb5_in[val_mask]

            tr_min_tp0 = int(round(target_tp0_inner * (tr_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(target_tp3_inner * (tr_mask.sum() / len(inner_y))))

            best_param = None
            best_score = -1

            for a0 in [1.00, 1.02, 1.04]:
                for a2 in [1.00, 1.05]:
                    for tau_lgb in [0.20, 0.22, 0.25, 0.28, 0.30]:
                        pred_tr = (p_tr * np.array([a0, 1.00, a2, 1.00])).argmax(axis=1)
                        pred_tr[lgb_tr[:, 3] >= tau_lgb] = 3

                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                        if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                            if np.trace(cm_tr) > best_score:
                                best_score = np.trace(cm_tr)
                                best_param = (a0, a2, tau_lgb)

            if best_param is None:
                best_param = (1.02, 1.00, 0.22)
            fold_params.append(best_param)

            pred_v = (p_val * np.array([best_param[0], 1.00, best_param[1], 1.00])).argmax(axis=1)
            pred_v[lgb_val[:, 3] >= best_param[2]] = 3
            oof_pred_in[val_mask] = pred_v

        m_in = compute_metrics(inner_y, oof_pred_in)
        print(f"\n{b_name} [Dual Gate]:")
        print(f"  Fold Params: {fold_params}")
        print(f"  INNER: Correct={m_in['correct']}/2361 ({m_in['micro_f1']:.6f}), TP={m_in['tp']}")

        # Apply strictly to OUTER
        pred_out_gate = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            mask_f = (outer_folds == f)
            a0, a2, tau_lgb = fold_params[f]
            pred_f = (p_out[mask_f] * np.array([a0, 1.00, a2, 1.00])).argmax(axis=1)
            pred_f[p_lgb5_out[mask_f, 3] >= tau_lgb] = 3
            pred_out_gate[mask_f] = pred_f

        m_out_gate = compute_metrics(outer_y, pred_out_gate)
        print(f"  OUTER: Correct={m_out_gate['correct']}/5897 ({m_out_gate['micro_f1']:.6f}), TP={m_out_gate['tp']}, PASS={m_out_gate['tp'][0]>=2389 and m_out_gate['tp'][3]>=92}")

    gc.collect()
    check_ram("strict_inner_protection_end", expected_peak_mb=100.0)

if __name__ == "__main__":
    main()
