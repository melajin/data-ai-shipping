# -*- coding: utf-8 -*-
"""Round013 Task 1 — §5 Hour-of-Day Confounder Check.

Tests whether local collapse minimum lin_min_w correlates with hour-of-day (|rho| >= 0.2),
and whether collapse hour distribution differs between accident-related and control voyages (two-sample KS test).
Family size = 2 (w=7 and w=3) with Bonferroni correction.
"""
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

from round013_util import (
    assert_ram_sufficient,
    get_ram_status,
    append_log,
)

OUT_DIR = "testB/round_013_20261105"
G4_VOYAGES_PATH = f"{OUT_DIR}/g4_voyages.csv"


def analyze_confound_for_window(df_voy, w):
    col_valid = f"valid_w{w}"
    col_lin = f"lin_min_w{w}"
    col_hour = f"collapse_hour_w{w}"
    col_day = f"is_daytime_w{w}"
    
    # Filter to valid voyages for window w
    df_valid = df_voy[df_voy[col_valid] == True].copy()
    n_valid = len(df_valid)
    
    # Accident vs Control split
    acc_mask = df_valid["is_accident_related"] == True
    df_acc = df_valid[acc_mask]
    df_ctrl = df_valid[~acc_mask]
    
    # 1. Spearman correlation: lin_min_w vs collapse_hour (ALL)
    rho_all, p_rho_all = stats.spearmanr(df_valid[col_lin], df_valid[col_hour])
    
    # 2. Two-sample KS test: Accident vs Control collapse hours (ALL)
    acc_hours = df_acc[col_hour].to_numpy(dtype=float)
    ctrl_hours = df_ctrl[col_hour].to_numpy(dtype=float)
    ks_res_all = stats.ks_2samp(acc_hours, ctrl_hours)
    ks_stat_all = float(ks_res_all.statistic)
    ks_pval_raw_all = float(ks_res_all.pvalue)
    ks_pval_bonf_all = min(1.0, ks_pval_raw_all * 2.0)
    
    # 3. Decision criteria on ALL (primary)
    rho_flag_all = bool(abs(rho_all) >= 0.20)
    ks_flag_all = bool(ks_pval_bonf_all < 0.05)
    confound_detected_all = rho_flag_all or ks_flag_all
    
    # 4. Tier 0-1 subset (descriptive)
    df_t01 = df_valid[df_valid["is_tier01_vessel"] == True]
    acc_mask_t01 = df_t01["is_accident_related"] == True
    df_acc_t01 = df_t01[acc_mask_t01]
    df_ctrl_t01 = df_t01[~acc_mask_t01]
    
    rho_t01, p_rho_t01 = stats.spearmanr(df_t01[col_lin], df_t01[col_hour]) if len(df_t01) > 1 else (np.nan, np.nan)
    acc_hours_t01 = df_acc_t01[col_hour].to_numpy(dtype=float)
    ctrl_hours_t01 = df_ctrl_t01[col_hour].to_numpy(dtype=float)
    if len(acc_hours_t01) > 0 and len(ctrl_hours_t01) > 0:
        ks_res_t01 = stats.ks_2samp(acc_hours_t01, ctrl_hours_t01)
        ks_stat_t01 = float(ks_res_t01.statistic)
        ks_pval_raw_t01 = float(ks_res_t01.pvalue)
    else:
        ks_stat_t01, ks_pval_raw_t01 = np.nan, np.nan
        
    # 5. Diurnal breakdown (Daytime [06, 18) vs Nighttime)
    day_all = int(df_valid[col_day].sum())
    night_all = n_valid - day_all
    day_acc = int(df_acc[col_day].sum())
    night_acc = len(df_acc) - day_acc
    day_ctrl = int(df_ctrl[col_day].sum())
    night_ctrl = len(df_ctrl) - day_ctrl
    
    # 2x2 contingency table for day/night
    contingency = [[day_acc, night_acc], [day_ctrl, night_ctrl]]
    oddsratio, fisher_pval = stats.fisher_exact(contingency)
    
    # 6. 24-hour distribution histograms (counts & fractions)
    hours_dist_all = df_valid[col_hour].value_counts().reindex(range(24), fill_value=0).to_dict()
    hours_dist_acc = df_acc[col_hour].value_counts().reindex(range(24), fill_value=0).to_dict()
    hours_dist_ctrl = df_ctrl[col_hour].value_counts().reindex(range(24), fill_value=0).to_dict()
    
    return {
        "window_size_w": w,
        "n_valid_voyages_all": n_valid,
        "n_accident_related": len(df_acc),
        "n_control": len(df_ctrl),
        # ALL population primary metrics
        "primary_spearman_rho_all": round(float(rho_all), 5),
        "primary_spearman_pvalue_all": float(p_rho_all),
        "primary_ks_statistic_all": round(ks_stat_all, 5),
        "primary_ks_pvalue_raw_all": float(ks_pval_raw_all),
        "primary_ks_pvalue_bonferroni_all": float(ks_pval_bonf_all),
        "rho_threshold_exceeded_all": rho_flag_all,
        "ks_bonferroni_significant_all": ks_flag_all,
        "confound_detected_all": confound_detected_all,
        "recommended_branch_all": (
            "CONFOUND_PRESENT (restrict leave-one-out to same diurnal bucket [06,18) / [18,06))"
            if confound_detected_all
            else "NO_CONFOUND (proceed with all other voyages without diurnal restriction)"
        ),
        # Tier 0-1 subset descriptive metrics
        "n_valid_voyages_t01": len(df_t01),
        "n_accident_related_t01": len(df_acc_t01),
        "n_control_t01": len(df_ctrl_t01),
        "descriptive_spearman_rho_t01": round(float(rho_t01), 5),
        "descriptive_spearman_pvalue_t01": float(p_rho_t01),
        "descriptive_ks_statistic_t01": round(ks_stat_t01, 5) if not np.isnan(ks_stat_t01) else None,
        "descriptive_ks_pvalue_raw_t01": float(ks_pval_raw_t01) if not np.isnan(ks_pval_raw_t01) else None,
        # Diurnal statistics
        "diurnal_counts": {
            "all": {"day": day_all, "night": night_all, "day_pct": round(day_all / n_valid * 100, 2)},
            "accident": {"day": day_acc, "night": night_acc, "day_pct": round(day_acc / len(df_acc) * 100, 2) if len(df_acc) else 0},
            "control": {"day": day_ctrl, "night": night_ctrl, "day_pct": round(day_ctrl / len(df_ctrl) * 100, 2) if len(df_ctrl) else 0},
        },
        "diurnal_fisher_exact_pvalue": float(fisher_pval),
        # 24-hour distribution counts
        "distribution_24h_all": {int(k): int(v) for k, v in hours_dist_all.items()},
        "distribution_24h_acc": {int(k): int(v) for k, v in hours_dist_acc.items()},
        "distribution_24h_ctrl": {int(k): int(v) for k, v in hours_dist_ctrl.items()},
    }


def main():
    append_log("Starting §5 Hour-of-Day Confounder Check.")
    assert_ram_sufficient(phase_name="g5_confound_check_start", estimated_peak_mib=128.0)
    
    df_voy = pd.read_csv(G4_VOYAGES_PATH)
    
    results = {}
    summary_rows = []
    
    for w in (7, 3):
        res_w = analyze_confound_for_window(df_voy, w)
        results[f"w{w}"] = res_w
        
        summary_rows.append({
            "window_size_w": w,
            "n_valid_all": res_w["n_valid_voyages_all"],
            "n_acc": res_w["n_accident_related"],
            "n_ctrl": res_w["n_control"],
            "rho_all": res_w["primary_spearman_rho_all"],
            "rho_pval_all": res_w["primary_spearman_pvalue_all"],
            "ks_stat_all": res_w["primary_ks_statistic_all"],
            "ks_pval_raw_all": res_w["primary_ks_pvalue_raw_all"],
            "ks_pval_bonf_all": res_w["primary_ks_pvalue_bonferroni_all"],
            "confound_detected": res_w["confound_detected_all"],
            "recommended_branch": res_w["recommended_branch_all"],
            "rho_t01": res_w["descriptive_spearman_rho_t01"],
            "ks_stat_t01": res_w["descriptive_ks_statistic_t01"],
            "ks_pval_raw_t01": res_w["descriptive_ks_pvalue_raw_t01"],
            "acc_day_pct": res_w["diurnal_counts"]["accident"]["day_pct"],
            "ctrl_day_pct": res_w["diurnal_counts"]["control"]["day_pct"],
            "fisher_p": res_w["diurnal_fisher_exact_pvalue"],
        })
        
    df_summary = pd.DataFrame(summary_rows)
    summary_csv_path = f"{OUT_DIR}/g5_confound_summary.csv"
    df_summary.to_csv(summary_csv_path, index=False, encoding="utf-8-sig")
    append_log(f"Saved confound summary CSV to {summary_csv_path}")
    
    results_json_path = f"{OUT_DIR}/g5_confound_result.json"
    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    append_log(f"Saved full confound results JSON to {results_json_path}")
    
    print("=== G5 Hour-of-Day Confounder Check Completed Successfully ===")
    print(df_summary[["window_size_w", "n_valid_all", "rho_all", "ks_stat_all", "ks_pval_raw_all", "ks_pval_bonf_all", "confound_detected", "recommended_branch"]].to_string())


if __name__ == "__main__":
    main()
