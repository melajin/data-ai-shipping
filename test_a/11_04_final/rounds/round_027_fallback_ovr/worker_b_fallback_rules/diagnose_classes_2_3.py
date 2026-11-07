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
    
    m_preds = np.stack([
        p_lgb5.argmax(axis=1),
        p_cat.argmax(axis=1),
        p_tab42.argmax(axis=1),
        p_tab26.argmax(axis=1),
        p_t1.argmax(axis=1)
    ], axis=1)

    # Pred 2
    idx_tp2 = np.where((pred == 2) & (outer_y == 2))[0]
    idx_fp0_2 = np.where((pred == 2) & (outer_y == 0))[0]
    idx_fp1_2 = np.where((pred == 2) & (outer_y == 1))[0]
    
    print(f"Pred == 2: TP2={len(idx_tp2)}, FP0={len(idx_fp0_2)}, FP1={len(idx_fp1_2)}")
    vote2 = (m_preds == 2).sum(axis=1)
    print("Votes for 2:")
    for v in range(6):
        print(f"  v={v}: TP2={(vote2[idx_tp2]==v).sum()}, FP0={(vote2[idx_fp0_2]==v).sum()}, FP1={(vote2[idx_fp1_2]==v).sum()}")

    # Pred 3
    idx_tp3 = np.where((pred == 3) & (outer_y == 3))[0]
    idx_fp0_3 = np.where((pred == 3) & (outer_y == 0))[0]
    idx_fp1_3 = np.where((pred == 3) & (outer_y == 1))[0]
    print(f"\nPred == 3: TP3={len(idx_tp3)}, FP0={len(idx_fp0_3)}, FP1={len(idx_fp1_3)}")
    vote3 = (m_preds == 3).sum(axis=1)
    print("Votes for 3:")
    for v in range(6):
        print(f"  v={v}: TP3={(vote3[idx_tp3]==v).sum()}, FP0={(vote3[idx_fp0_3]==v).sum()}, FP1={(vote3[idx_fp1_3]==v).sum()}")

if __name__ == "__main__":
    main()
