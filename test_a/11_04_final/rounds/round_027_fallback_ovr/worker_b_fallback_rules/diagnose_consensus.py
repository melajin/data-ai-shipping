import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from test_baseline_leakage import load_data

def main():
    inner_y, outer_y, inner_folds, outer_folds, models = load_data()
    p_grand = models["Blend_Grand"][1]
    p_lgb5 = models["LightGBM_5seed_sqrt_macro"][1]
    p_cat = models["CatBoost"][1]
    p_tab42 = models["TabICL_seed42"][1]
    p_tab26 = models["TabICL_seed2026"][1]
    p_t1 = models["Track1_LGB_kNN"][1]
    
    alpha = np.array([1.04, 1.00, 1.00, 1.45], dtype=np.float32)
    pred = (p_grand * alpha).argmax(axis=1)
    
    idx_tp1 = np.where((pred == 1) & (outer_y == 1))[0]
    idx_fp0 = np.where((pred == 1) & (outer_y == 0))[0]
    
    print("For ships predicted as 1:")
    print(f"LGB5 P(1):       TP1={p_lgb5[idx_tp1, 1].mean():.3f}, FP0={p_lgb5[idx_fp0, 1].mean():.3f}")
    print(f"Cat P(1):        TP1={p_cat[idx_tp1, 1].mean():.3f}, FP0={p_cat[idx_fp0, 1].mean():.3f}")
    print(f"Tab42 P(1):      TP1={p_tab42[idx_tp1, 1].mean():.3f}, FP0={p_tab42[idx_fp0, 1].mean():.3f}")
    print(f"Tab26 P(1):      TP1={p_tab26[idx_tp1, 1].mean():.3f}, FP0={p_tab26[idx_fp0, 1].mean():.3f}")
    print(f"Track1 P(1):     TP1={p_t1[idx_tp1, 1].mean():.3f}, FP0={p_t1[idx_fp0, 1].mean():.3f}")

    print("\nFor ships predicted as 1, look at TabICL P(0):")
    print(f"Tab42 P(0):      TP1={p_tab42[idx_tp1, 0].mean():.3f}, FP0={p_tab42[idx_fp0, 0].mean():.3f}")
    print(f"Tab26 P(0):      TP1={p_tab26[idx_tp1, 0].mean():.3f}, FP0={p_tab26[idx_fp0, 0].mean():.3f}")
    print(f"Track1 P(0):     TP1={p_t1[idx_tp1, 0].mean():.3f}, FP0={p_t1[idx_fp0, 0].mean():.3f}")
    print(f"LGB5 P(0):       TP1={p_lgb5[idx_tp1, 0].mean():.3f}, FP0={p_lgb5[idx_fp0, 0].mean():.3f}")

    # Standard deviation among models' P(1)
    p1_stack = np.stack([p_lgb5[:, 1], p_cat[:, 1], p_tab42[:, 1], p_tab26[:, 1], p_t1[:, 1]], axis=1)
    p1_std = p1_stack.std(axis=1)
    print(f"\nModel P(1) std:  TP1={p1_std[idx_tp1].mean():.4f}, FP0={p1_std[idx_fp0].mean():.4f}")

    # Check how many models predict 1 as their individual argmax
    m_preds = np.stack([
        p_lgb5.argmax(axis=1),
        p_cat.argmax(axis=1),
        p_tab42.argmax(axis=1),
        p_tab26.argmax(axis=1),
        p_t1.argmax(axis=1)
    ], axis=1) # (5897, 5)
    
    vote_count_1 = (m_preds == 1).sum(axis=1)
    vote_count_0 = (m_preds == 0).sum(axis=1)
    
    print("\nVote breakdown for Pred == 1:")
    for v in range(6):
        n_tp = (vote_count_1[idx_tp1] == v).sum()
        n_fp = (vote_count_1[idx_fp0] == v).sum()
        print(f"  Votes for Class 1 == {v}: TP1={n_tp:3d} ({n_tp/len(idx_tp1):.1%}), FP0={n_fp:3d} ({n_fp/len(idx_fp0):.1%})")

    print("\nVotes for Class 0 among ships with Pred == 1:")
    for v in range(6):
        n_tp = (vote_count_0[idx_tp1] == v).sum()
        n_fp = (vote_count_0[idx_fp0] == v).sum()
        print(f"  Votes for Class 0 == {v}: TP1={n_tp:3d} ({n_tp/len(idx_tp1):.1%}), FP0={n_fp:3d} ({n_fp/len(idx_fp0):.1%})")

if __name__ == "__main__":
    main()
