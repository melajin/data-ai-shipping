# -*- coding: utf-8 -*-
"""Round013 Task 1 — §3 Voyage Count Coverage & Eligibility Analysis.

Analyzes voyage count distributions and self-reference eligibility (remaining >= 10)
for dev 82 vessels (ALL and Tier 0-1) and 2025 Test B 100 vessels.
"""
import os
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from round013_util import (
    assert_ram_sufficient,
    get_ram_status,
    append_log,
    compute_file_sha256,
)

OUT_DIR = "testB/round_013_20261105"
G4_VOYAGES_PATH = f"{OUT_DIR}/g4_voyages.csv"
TESTB_2025_PATH = "testB/first_results/hourly_scores.parquet"


def main():
    append_log("Starting §3 Voyage Count Coverage & Eligibility Analysis.")
    assert_ram_sufficient(phase_name="g3_coverage_start", estimated_peak_mib=128.0)
    
    # 1. Dev 82 vessels from g4_voyages.csv
    v_dev = pd.read_csv(G4_VOYAGES_PATH)
    v_dev["rfid_id"] = v_dev["rfid_id"].astype(str)
    
    dev_vessels = []
    for vid, g in v_dev.groupby("rfid_id"):
        n_raw = len(g)
        is_t01 = bool(g["is_tier01_vessel"].iloc[0])
        has_acc = bool(g["is_accident_related"].any())
        
        # Valid voyages per window
        n_valid_w7 = int(g["valid_w7"].sum())
        n_valid_w3 = int(g["valid_w3"].sum())
        
        # Day / Night valid voyages per window
        n_valid_day_w7 = int((g["valid_w7"] & (g["is_daytime_w7"] == True)).sum())
        n_valid_night_w7 = int((g["valid_w7"] & (g["is_daytime_w7"] == False)).sum())
        n_valid_day_w3 = int((g["valid_w3"] & (g["is_daytime_w3"] == True)).sum())
        n_valid_night_w3 = int((g["valid_w3"] & (g["is_daytime_w3"] == False)).sum())
        
        dev_vessels.append({
            "dataset": "dev_82",
            "rfid_id": str(vid),
            "is_tier01_vessel": is_t01,
            "has_accident_related_voyage": has_acc,
            "n_voyages_raw": n_raw,
            # Strict normative rule: remaining >= 10 -> total >= 11
            "eligible_raw_rem_ge_10": bool(n_raw >= 11),
            "ineligible_raw_reason": "insufficient_history (<11)" if n_raw < 11 else "eligible",
            # Protocol table reproduction columns
            "raw_lt_10": bool(n_raw < 10),
            "raw_lt_5": bool(n_raw < 5),
            # Window w=7 valid voyages and eligibility
            "n_valid_voyages_w7": n_valid_w7,
            "eligible_w7_rem_ge_10": bool(n_valid_w7 >= 11),
            "ineligible_w7_reason": "insufficient_history (<11)" if n_valid_w7 < 11 else "eligible",
            # Window w=3 valid voyages and eligibility
            "n_valid_voyages_w3": n_valid_w3,
            "eligible_w3_rem_ge_10": bool(n_valid_w3 >= 11),
            "ineligible_w3_reason": "insufficient_history (<11)" if n_valid_w3 < 11 else "eligible",
            # Diurnal breakdown (for confound branch preparedness)
            "n_valid_day_w7": n_valid_day_w7,
            "n_valid_night_w7": n_valid_night_w7,
            "n_valid_day_w3": n_valid_day_w3,
            "n_valid_night_w3": n_valid_night_w3,
        })
    df_dev_vessels = pd.DataFrame(dev_vessels)
    
    # 2. 2025 Test B 100 vessels from testB/first_results/hourly_scores.parquet
    append_log(f"Loading 2025 Test B from {TESTB_2025_PATH}")
    pf25 = pq.ParquetFile(TESTB_2025_PATH)
    df25 = pf25.read(columns=["rfid_id", "ts"]).to_pandas()
    df25["rfid_id"] = df25["rfid_id"].astype(str)
    df25 = df25.drop_duplicates(["rfid_id", "ts"]).sort_values(["rfid_id", "ts"]).reset_index(drop=True)
    
    testb_vessels = []
    for vid, g in df25.groupby("rfid_id"):
        ts = g["ts"].to_numpy()
        n_raw = 1 + int(np.sum(np.diff(ts) >= 6))
        testb_vessels.append({
            "dataset": "2025_TestB_100",
            "rfid_id": str(vid),
            "is_tier01_vessel": False,  # Not applicable / blind
            "has_accident_related_voyage": False,  # Not applicable / blind
            "n_voyages_raw": n_raw,
            "eligible_raw_rem_ge_10": bool(n_raw >= 11),
            "ineligible_raw_reason": "insufficient_history (<11)" if n_raw < 11 else "eligible",
            "raw_lt_10": bool(n_raw < 10),
            "raw_lt_5": bool(n_raw < 5),
            "n_valid_voyages_w7": np.nan,
            "eligible_w7_rem_ge_10": np.nan,
            "ineligible_w7_reason": "not_computed",
            "n_valid_voyages_w3": np.nan,
            "eligible_w3_rem_ge_10": np.nan,
            "ineligible_w3_reason": "not_computed",
            "n_valid_day_w7": np.nan,
            "n_valid_night_w7": np.nan,
            "n_valid_day_w3": np.nan,
            "n_valid_night_w3": np.nan,
        })
    df_testb_vessels = pd.DataFrame(testb_vessels)
    
    # Combined vessel-level CSV
    df_all_vessels = pd.concat([df_dev_vessels, df_testb_vessels], ignore_index=True)
    vessel_csv_path = f"{OUT_DIR}/g3_vessel_level_coverage.csv"
    df_all_vessels.to_csv(vessel_csv_path, index=False, encoding="utf-8-sig")
    append_log(f"Saved vessel-level coverage to {vessel_csv_path}")
    
    # 3. Build Summary Coverage Table matching PROTOCOL.md §3
    dev_all = df_dev_vessels
    dev_t01 = df_dev_vessels[df_dev_vessels["is_tier01_vessel"] == True]
    t25 = df_testb_vessels
    
    def summarize_pop(df_pop, name):
        n_tot = len(df_pop)
        raw_counts = df_pop["n_voyages_raw"]
        lt_10 = int(df_pop["raw_lt_10"].sum())
        lt_5 = int(df_pop["raw_lt_5"].sum())
        rem_ge_10 = int(df_pop["eligible_raw_rem_ge_10"].sum())
        rem_lt_10 = n_tot - rem_ge_10
        
        # Valid counts if available
        w7_ge_10 = int((df_pop["eligible_w7_rem_ge_10"] == True).sum()) if "eligible_w7_rem_ge_10" in df_pop and not df_pop["eligible_w7_rem_ge_10"].isna().all() else np.nan
        w3_ge_10 = int((df_pop["eligible_w3_rem_ge_10"] == True).sum()) if "eligible_w3_rem_ge_10" in df_pop and not df_pop["eligible_w3_rem_ge_10"].isna().all() else np.nan
        
        return {
            "population": name,
            "n_vessels": n_tot,
            "median_voyages_raw": float(raw_counts.median()),
            "min_voyages_raw": int(raw_counts.min()),
            "max_voyages_raw": int(raw_counts.max()),
            "table_lt_10_count": lt_10,
            "table_lt_10_pct": round(lt_10 / n_tot * 100, 2),
            "table_lt_5_count": lt_5,
            "table_lt_5_pct": round(lt_5 / n_tot * 100, 2),
            "normative_eligible_ge_11_count": rem_ge_10,
            "normative_eligible_ge_11_pct": round(rem_ge_10 / n_tot * 100, 2),
            "normative_ineligible_lt_11_count": rem_lt_10,
            "normative_ineligible_lt_11_pct": round(rem_lt_10 / n_tot * 100, 2),
            "w7_eligible_ge_11_count": w7_ge_10,
            "w7_eligible_ge_11_pct": round(w7_ge_10 / n_tot * 100, 2) if not np.isnan(w7_ge_10) else np.nan,
            "w3_eligible_ge_11_count": w3_ge_10,
            "w3_eligible_ge_11_pct": round(w3_ge_10 / n_tot * 100, 2) if not np.isnan(w3_ge_10) else np.nan,
        }
        
    summary_rows = [
        summarize_pop(dev_all, "dev_ALL (82 vessels)"),
        summarize_pop(dev_t01, "dev_Tier0-1 (55 vessels)"),
        summarize_pop(t25, "2025_TestB (100 vessels)"),
    ]
    df_summary = pd.DataFrame(summary_rows)
    coverage_csv_path = f"{OUT_DIR}/g3_voyage_count_coverage.csv"
    df_summary.to_csv(coverage_csv_path, index=False, encoding="utf-8-sig")
    append_log(f"Saved coverage summary table to {coverage_csv_path}")
    
    summary_json_path = f"{OUT_DIR}/g3_summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_rows, f, ensure_ascii=False, indent=2)
        
    print("=== G3 Voyage Count Coverage Completed Successfully ===")
    print(df_summary.to_string())


if __name__ == "__main__":
    main()
