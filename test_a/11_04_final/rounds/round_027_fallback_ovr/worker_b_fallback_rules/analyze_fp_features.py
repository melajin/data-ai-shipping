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
    
    alpha = np.array([1.04, 1.00, 1.00, 1.45], dtype=np.float32)
    pred = (p_grand * alpha).argmax(axis=1)
    
    # Let's inspect Pred == 1: True 0 (FP) vs True 1 (TP)
    idx_tp1 = np.where((pred == 1) & (outer_y == 1))[0]
    idx_fp0 = np.where((pred == 1) & (outer_y == 0))[0]
    
    print(f"Pred == 1: TP(True 1) = {len(idx_tp1)}, FP(True 0) = {len(idx_fp0)}")
    
    print("\nMean probabilities:")
    print(f"TP(True 1): P0={p_grand[idx_tp1, 0].mean():.3f}, P1={p_grand[idx_tp1, 1].mean():.3f}, P2={p_grand[idx_tp1, 2].mean():.3f}, P3={p_grand[idx_tp1, 3].mean():.3f}")
    print(f"FP(True 0): P0={p_grand[idx_fp0, 0].mean():.3f}, P1={p_grand[idx_fp0, 1].mean():.3f}, P2={p_grand[idx_fp0, 2].mean():.3f}, P3={p_grand[idx_fp0, 3].mean():.3f}")
    
    # Margin P1 - P0:
    margin_tp1 = p_grand[idx_tp1, 1] - p_grand[idx_tp1, 0]
    margin_fp0 = p_grand[idx_fp0, 1] - p_grand[idx_fp0, 0]
    
    print("\nMargin (P1 - P0):")
    print(f"TP(True 1): mean={margin_tp1.mean():.3f}, median={np.median(margin_tp1):.3f}, min={margin_tp1.min():.3f}, 10%={np.percentile(margin_tp1, 10):.3f}")
    print(f"FP(True 0): mean={margin_fp0.mean():.3f}, median={np.median(margin_fp0):.3f}, min={margin_fp0.min():.3f}, 90%={np.percentile(margin_fp0, 90):.3f}")
    
    # Look at quantiles of margin
    print("\nCumulative distribution of Margin (P1 - P0):")
    for thresh in np.linspace(-0.05, 0.30, 8):
        tp_lost = (margin_tp1 < thresh).sum()
        fp_recovered = (margin_fp0 < thresh).sum()
        net_gain = fp_recovered - tp_lost
        print(f"Thresh {thresh:+.2f}: TP1 Lost={tp_lost:3d}, FP0 Recovered={fp_recovered:3d} | Net Gain = {net_gain:+3d}")

    # Inspect Pred == 2: True 0 (FP) vs True 2 (TP)
    idx_tp2 = np.where((pred == 2) & (outer_y == 2))[0]
    idx_fp0_2 = np.where((pred == 2) & (outer_y == 0))[0]
    print(f"\nPred == 2: TP(True 2) = {len(idx_tp2)}, FP(True 0) = {len(idx_fp0_2)}")
    margin_tp2 = p_grand[idx_tp2, 2] - p_grand[idx_tp2, 0]
    margin_fp0_2 = p_grand[idx_fp0_2, 2] - p_grand[idx_fp0_2, 0]
    print("\nCumulative distribution of Margin (P2 - P0):")
    for thresh in np.linspace(-0.05, 0.30, 8):
        tp_lost = (margin_tp2 < thresh).sum()
        fp_recovered = (margin_fp0_2 < thresh).sum()
        net_gain = fp_recovered - tp_lost
        print(f"Thresh {thresh:+.2f}: TP2 Lost={tp_lost:3d}, FP0 Recovered={fp_recovered:3d} | Net Gain = {net_gain:+3d}")

if __name__ == "__main__":
    main()
