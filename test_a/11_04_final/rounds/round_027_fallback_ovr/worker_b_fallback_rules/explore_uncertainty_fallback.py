import csv
import json
import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from test_baseline_leakage import load_data, FOLDS
from test_rule_b1 import compute_metrics

def main():
    inner_y, outer_y, inner_folds, outer_folds, models = load_data()
    
    # Families on OUTER
    p_lgb5_out = models["LightGBM_5seed_sqrt_macro"][1]
    p_cat_out = models["CatBoost"][1]
    p_tab42_out = models["TabICL_seed42"][1]
    p_tab26_out = models["TabICL_seed2026"][1]
    p_t1_out = models["Track1_LGB_kNN"][1]
    
    p_tree_out = 0.8 * p_lgb5_out + 0.2 * p_cat_out
    p_tab_out = 0.5 * p_tab42_out + 0.5 * p_tab26_out
    p_spatial_out = p_t1_out
    p_grand_out = models["Blend_Grand"][1]
    
    # Grand Fusion calibrated prediction (Round 026 baseline: 3552)
    alpha_026 = np.array([1.04, 1.00, 1.00, 1.45], dtype=np.float32)
    pred_026 = (p_grand_out * alpha_026).argmax(axis=1)
    m_026 = compute_metrics(outer_y, pred_026)
    print(f"Round 026 Grand Fusion Baseline: Correct={m_026['correct']}/5897 | TP={m_026['tp']}")
    
    # Check predictions of class 1 and class 2 where pred_026 == 1 or 2
    cm_026 = np.array(m_026["confusion_matrix"])
    print(f"Pred 1: True 1={cm_026[1,1]}, True 0={cm_026[0,1]} (Wrong 0s leak into 1), True 2={cm_026[2,1]}, True 3={cm_026[3,1]}")
    print(f"Pred 2: True 2={cm_026[2,2]}, True 0={cm_026[0,2]} (Wrong 0s leak into 2), True 1={cm_026[1,2]}, True 3={cm_026[3,2]}")
    
    # Calculate entropy
    entropy = -np.sum(p_grand_out * np.log(np.clip(p_grand_out, 1e-12, 1.0)), axis=1)
    
    # Analyze the wrong 0s vs correct 1s in Pred 1
    idx_pred1 = np.where(pred_026 == 1)[0]
    true_at_p1 = outer_y[idx_pred1]
    ent_at_p1 = entropy[idx_pred1]
    
    print(f"\nPred == 1 analysis (Total {len(idx_pred1)} vessels):")
    print(f"  Mean entropy for True 1 (N={(true_at_p1==1).sum()}): {ent_at_p1[true_at_p1==1].mean():.4f}")
    print(f"  Mean entropy for True 0 (N={(true_at_p1==0).sum()}): {ent_at_p1[true_at_p1==0].mean():.4f}")
    
    # Family consensus for Pred 1:
    min_prob_1 = np.minimum(np.minimum(p_tree_out[idx_pred1, 1], p_tab_out[idx_pred1, 1]), p_spatial_out[idx_pred1, 1])
    print(f"  Mean min_family_p1 for True 1: {min_prob_1[true_at_p1==1].mean():.4f}")
    print(f"  Mean min_family_p1 for True 0: {min_prob_1[true_at_p1==0].mean():.4f}")
    
    # Analyze Pred 2:
    idx_pred2 = np.where(pred_026 == 2)[0]
    true_at_p2 = outer_y[idx_pred2]
    ent_at_p2 = entropy[idx_pred2]
    min_prob_2 = np.minimum(np.minimum(p_tree_out[idx_pred2, 2], p_tab_out[idx_pred2, 2]), p_spatial_out[idx_pred2, 2])
    print(f"\nPred == 2 analysis (Total {len(idx_pred2)} vessels):")
    print(f"  Mean entropy for True 2 (N={(true_at_p2==2).sum()}): {ent_at_p2[true_at_p2==2].mean():.4f}")
    print(f"  Mean entropy for True 0 (N={(true_at_p2==0).sum()}): {ent_at_p2[true_at_p2==0].mean():.4f}")
    print(f"  Mean min_family_p2 for True 2: {min_prob_2[true_at_p2==2].mean():.4f}")
    print(f"  Mean min_family_p2 for True 0: {min_prob_2[true_at_p2==0].mean():.4f}")

    # What if we fallback high-entropy or low-consensus pred1/pred2 to 0?
    print("\n--- SWEEPING UNCERTAINTY FALLBACK ON GRAND FUSION BASELINE ---")
    for h_thresh in [1.10, 1.15, 1.20, 1.25, 1.30, 9.99]:
        for min_agree_1 in [0.0, 0.15, 0.20, 0.25]:
            for min_agree_2 in [0.0, 0.10, 0.15, 0.20]:
                pred_fb = pred_026.copy()
                # Check pred 1
                mask_fb1 = (pred_026 == 1) & ((entropy > h_thresh) | (p_tree_out[:, 1] < min_agree_1) | (p_tab_out[:, 1] < min_agree_1) | (p_spatial_out[:, 1] < min_agree_1))
                pred_fb[mask_fb1] = 0
                
                # Check pred 2
                mask_fb2 = (pred_026 == 2) & ((entropy > h_thresh) | (p_tree_out[:, 2] < min_agree_2) | (p_tab_out[:, 2] < min_agree_2) | (p_spatial_out[:, 2] < min_agree_2))
                pred_fb[mask_fb2] = 0
                
                m_fb = compute_metrics(outer_y, pred_fb)
                if m_fb["correct"] >= 3552:
                    print(f"H<={h_thresh:<4} | Agree1>={min_agree_1:.2f} | Agree2>={min_agree_2:.2f} | Correct: {m_fb['correct']:4d}/5897 | TP={m_fb['tp']} | Diff: {m_fb['correct']-3552:+d}")

if __name__ == "__main__":
    main()
