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
    check_ram("inner_diagnostics_start", expected_peak_mb=100.0)
    
    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    
    # Extract days for INNER
    # Let's get observed_days for INNER from TabICL inner files
    tab_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation\seed_42")
    inner_days_map = {}
    for fold in FOLDS:
        with open(tab_dir / f"fold_{fold}" / "inner_predictions.csv", "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                inner_days_map[(fold, r["rfid_id"])] = float(r["observed_days"])
                
    inner_keys = [(r[0], r[2]) for r in inner_records]
    inner_days = np.array([inner_days_map[k] for k in inner_keys], dtype=np.float64)
    
    day_bins = {
        "1-7 days": (inner_days >= 1) & (inner_days <= 7),
        "8-30 days": (inner_days >= 8) & (inner_days <= 30),
        "31-90 days": (inner_days >= 31) & (inner_days <= 90),
        "91+ days": inner_days >= 91,
    }
    
    print("="*90)
    print("INNER OBSERVED DAYS DISTRIBUTION & ACCURACY PER BIN")
    print("="*90)
    models_to_check = ["LightGBM_seed42", "LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42", "TabICL_seed2026"]
    
    for bin_name, mask in day_bins.items():
        n_bin = int(mask.sum())
        print(f"\n--- {bin_name} (N = {n_bin}, {n_bin/len(inner_y):.1%}) ---")
        y_bin = inner_y[mask]
        print(f"Class support: {np.bincount(y_bin, minlength=4).tolist()}")
        for m in models_to_check:
            pred_bin = inner_probs[m][mask].argmax(axis=1)
            correct_bin = int(np.count_nonzero(pred_bin == y_bin))
            print(f"  {m:<28}: {correct_bin:4d}/{n_bin} ({correct_bin/n_bin:.4f})")

    # Probability calibration / mean entropy
    print("\n" + "="*90)
    print("PROBABILITY DISTRIBUTION CHARACTERISTICS (INNER)")
    print("="*90)
    for m in models_to_check:
        p = inner_probs[m]
        p_clipped = np.clip(p, 1e-12, 1.0)
        entropy = -np.sum(p_clipped * np.log(p_clipped), axis=1).mean()
        max_p_mean = p.max(axis=1).mean()
        print(f"  {m:<28}: Mean Entropy = {entropy:.4f}, Mean Max Proba = {max_p_mean:.4f}, Class Proba Mean = {[round(x, 4) for x in p.mean(axis=0)]}")

    # Test baseline blends on INNER
    print("\n" + "="*90)
    print("SIMPLE BLENDS ON INNER (N=2,361)")
    print("="*90)
    p_lgb42 = inner_probs["LightGBM_seed42"]
    p_lgb5 = inner_probs["LightGBM_5seed_sqrt_macro"]
    p_cat = inner_probs["CatBoost"]
    p_tab42 = inner_probs["TabICL_seed42"]
    p_tab26 = inner_probs["TabICL_seed2026"]
    
    blends = [
        ("LGB42 50% + Tab42 50% (Linear)", 0.5 * p_lgb42 + 0.5 * p_tab42),
        ("LGB5 50% + Tab42 50% (Linear)", 0.5 * p_lgb5 + 0.5 * p_tab42),
        ("LGB5 50% + Tab26 50% (Linear)", 0.5 * p_lgb5 + 0.5 * p_tab26),
        ("LGB5 33% + Cat 33% + Tab42 33% (Linear)", (p_lgb5 + p_cat + p_tab42) / 3.0),
        ("LGB42 33% + Cat 33% + Tab42 33% (Linear)", (p_lgb42 + p_cat + p_tab42) / 3.0),
        ("LGB5 40% + Cat 20% + Tab42 40% (Linear)", 0.4 * p_lgb5 + 0.2 * p_cat + 0.4 * p_tab42),
        ("LGB5 50% + Tab42 50% (Log-Linear)", np.exp(0.5 * np.log(np.clip(p_lgb5, 1e-12, 1.0)) + 0.5 * np.log(np.clip(p_tab42, 1e-12, 1.0)))),
        ("LGB42 50% + Tab42 50% (Log-Linear)", np.exp(0.5 * np.log(np.clip(p_lgb42, 1e-12, 1.0)) + 0.5 * np.log(np.clip(p_tab42, 1e-12, 1.0)))),
    ]
    
    for name, p_blend in blends:
        pred = p_blend.argmax(axis=1)
        met = compute_metrics(inner_y, pred)
        print(f"  {name:<42}: Correct={met['correct']:4d}/2361 ({met['micro_f1']:.6f}), TP={met['tp']}")

    gc.collect()
    check_ram("inner_diagnostics_end", expected_peak_mb=100.0)

if __name__ == "__main__":
    main()
