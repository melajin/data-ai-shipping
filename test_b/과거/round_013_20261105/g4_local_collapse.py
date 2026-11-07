# -*- coding: utf-8 -*-
"""Round013 Task 1 — §4 Local Collapse Feature Calculation.

Computes trailing-window lin_w(h) for w in {3, 7} across all candidate integer hours,
identifies lin_min_w and t_collapse_w for each voyage, and tags accident relationship.
"""
import sys
import os
import json
import time
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Import utilities
from round013_util import (
    assert_ram_sufficient,
    get_ram_status,
    append_log,
    compute_file_sha256,
    compute_voyage_collapse,
)

OUT_DIR = "testB/round_013_20261105"
R8_DIR = "testB/round_008_linkage_audit_20261105"
DEVSET_POS_PATH = f"{R8_DIR}/devset_positives.csv"
DEV_HOURLY_PATH = f"{R8_DIR}/dev_hourly_scores.parquet"
ADD_HOURLY_PATH = f"{R8_DIR}/additional_hourly_scores.parquet"
PROTOCOL_PATH = f"{OUT_DIR}/PROTOCOL.md"
TASK_PATH = f"{OUT_DIR}/SUPERVISOR_TASK_01.md"


def main():
    start_time = time.time()
    append_log("Starting §4 Local Collapse Feature Calculation (Task 1).")
    
    # 1. RAM check before start
    ram_before = assert_ram_sufficient(phase_name="g4_local_collapse_start", estimated_peak_mib=256.0)
    
    # 2. Input hash verification
    hashes_before = {
        "devset_positives.csv": compute_file_sha256(DEVSET_POS_PATH),
        "dev_hourly_scores.parquet": compute_file_sha256(DEV_HOURLY_PATH),
        "additional_hourly_scores.parquet": compute_file_sha256(ADD_HOURLY_PATH),
        "PROTOCOL.md": compute_file_sha256(PROTOCOL_PATH),
        "SUPERVISOR_TASK_01.md": compute_file_sha256(TASK_PATH),
    }
    append_log(f"Input hashes verified: {json.dumps(hashes_before)}")
    
    # 3. Load devset positives
    pos = pd.read_csv(DEVSET_POS_PATH)
    pos["rfid_id"] = pos["rfid_id"].astype(str)
    target_vessels = set(pos["rfid_id"].unique())
    target_vessels_int = set(pos["rfid_id"].astype(int).unique())
    
    # Precompute accident mappings per vessel
    vessel_accidents = {}
    for vid, group in pos.groupby("rfid_id"):
        vessel_accidents[vid] = [
            {"acc_id": int(r["acc_id"]), "acc_ts": int(r["acc_ts"]), "tier": int(r["tier"])}
            for _, r in group.iterrows()
        ]
    
    tier01_vessels = set(pos[pos["tier"] <= 1]["rfid_id"].unique())
    append_log(f"Target vessels: {len(target_vessels)}, Tier 0-1 vessels: {len(tier01_vessels)}, Total accidents: {len(pos)}")

    # 4. Stream parquet batches with iter_batches to minimize peak memory
    cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state"]
    matched_batches = []
    
    for fpath in (DEV_HOURLY_PATH, ADD_HOURLY_PATH):
        pf = pq.ParquetFile(fpath)
        for batch in pf.iter_batches(columns=cols, batch_size=32768):
            df_b = batch.to_pandas()
            matched = df_b[df_b["rfid_id_int"].isin(target_vessels_int)]
            if len(matched) > 0:
                matched_batches.append(matched)
                
    raw_df = pd.concat(matched_batches, ignore_index=True)
    raw_df = raw_df.rename(columns={"rfid_id_int": "rfid_id"})
    raw_df["rfid_id"] = raw_df["rfid_id"].astype(str)
    n_raw_rows = len(raw_df)
    
    # 5. Audit duplicates before dedup
    n_dup_rows = int(raw_df.duplicated(subset=["rfid_id", "ts"], keep=False).sum())
    n_dropped = int(raw_df.duplicated(subset=["rfid_id", "ts"], keep="first").sum())
    
    # Deduplicate keeping first occurrence (exact Round 012 contract)
    df = raw_df.drop_duplicates(subset=["rfid_id", "ts"], keep="first").copy()
    df = df.sort_values(["rfid_id", "ts"]).reset_index(drop=True)
    n_dedup_rows = len(df)
    append_log(f"Parquet loaded: raw_rows={n_raw_rows}, dropped_duplicates={n_dropped}, dedup_rows={n_dedup_rows}")
    
    # 6. Strict sanity audit
    # Non-integer ts check
    ts_is_strictly_int = bool(np.all(df["ts"].astype(int) == df["ts"]))
    # Negative bbox check
    neg_bbox_count = int((df["bbox_m"] < 0).sum())
    neg_len_count = int((df["len_m"] < 0).sum())
    nan_counts = {col: int(df[col].isna().sum()) for col in df.columns}
    
    audit_results = {
        "n_raw_rows": n_raw_rows,
        "n_dup_rows": n_dup_rows,
        "n_dropped_duplicates": n_dropped,
        "n_dedup_rows": n_dedup_rows,
        "ts_is_strictly_int": ts_is_strictly_int,
        "neg_bbox_count": neg_bbox_count,
        "neg_len_count": neg_len_count,
        "nan_counts": nan_counts,
    }
    append_log(f"Audit results: {json.dumps(audit_results)}")
    
    if neg_bbox_count > 0:
        err_msg = f"CRITICAL: Negative bbox_m detected ({neg_bbox_count} rows). Halting execution as instructed."
        append_log(err_msg)
        print(err_msg, file=sys.stderr)
        sys.exit(1)
        
    # 7. Voyage splitting and local collapse computation
    append_log("Starting voyage splitting and §4 local collapse computation.")
    voyages = []
    
    for vid, g in df.groupby("rfid_id", sort=True):
        ts = g["ts"].to_numpy()
        lens = g["len_m"].to_numpy(dtype=float)
        bboxes = g["bbox_m"].to_numpy(dtype=float)
        
        # Voyage segment identification: diff(ts) >= 6
        diffs = np.diff(ts)
        seg = np.concatenate([[0], np.cumsum(diffs >= 6)])
        n_voyages = int(seg.max()) + 1
        
        is_t01_vessel = bool(vid in tier01_vessels)
        acc_list = vessel_accidents.get(vid, [])
        
        for v in range(n_voyages):
            idx = np.where(seg == v)[0]
            v_ts = ts[idx]
            v_len = lens[idx]
            v_bbox = bboxes[idx]
            
            t_start = int(v_ts[0])
            t_end = int(v_ts[-1])
            t_mid = int(v_ts[len(v_ts) // 2])
            voy_span = int(t_end - t_start + 1)
            voy_hours = int(len(v_ts))
            
            # §4 Local collapse for w=7
            val_w7, lin_min_w7, t_col_w7, count_w7 = compute_voyage_collapse(v_ts, v_len, v_bbox, w=7)
            col_hour_w7 = int(t_col_w7 % 24) if val_w7 else np.nan
            is_day_w7 = bool(6 <= col_hour_w7 < 18) if val_w7 else np.nan
            
            # §4 Local collapse for w=3
            val_w3, lin_min_w3, t_col_w3, count_w3 = compute_voyage_collapse(v_ts, v_len, v_bbox, w=3)
            col_hour_w3 = int(t_col_w3 % 24) if val_w3 else np.nan
            is_day_w3 = bool(6 <= col_hour_w3 < 18) if val_w3 else np.nan
            
            # Accident tagging: does any acc_ts satisfy t_start - 6 <= acc_ts <= t_end + 6?
            matched_accs = [
                a for a in acc_list
                if (t_start - 6 <= a["acc_ts"] <= t_end + 6)
            ]
            is_acc_rel = len(matched_accs) > 0
            matched_acc_ids = ";".join(str(a["acc_id"]) for a in matched_accs) if is_acc_rel else ""
            matched_acc_tiers = ";".join(str(a["tier"]) for a in matched_accs) if is_acc_rel else ""
            
            voyages.append({
                "rfid_id": str(vid),
                "voy": int(v),
                "n_voyages": int(n_voyages),
                "t_start": t_start,
                "t_end": t_end,
                "t_mid": t_mid,
                "voy_span": voy_span,
                "voy_hours": voy_hours,
                "valid_w7": bool(val_w7),
                "lin_min_w7": float(lin_min_w7) if val_w7 else np.nan,
                "t_collapse_w7": int(t_col_w7) if val_w7 else np.nan,
                "collapse_hour_w7": col_hour_w7,
                "is_daytime_w7": is_day_w7,
                "n_valid_h_w7": int(count_w7),
                "valid_w3": bool(val_w3),
                "lin_min_w3": float(lin_min_w3) if val_w3 else np.nan,
                "t_collapse_w3": int(t_col_w3) if val_w3 else np.nan,
                "collapse_hour_w3": col_hour_w3,
                "is_daytime_w3": is_day_w3,
                "n_valid_h_w3": int(count_w3),
                "is_accident_related": is_acc_rel,
                "matched_acc_ids": matched_acc_ids,
                "matched_acc_tiers": matched_acc_tiers,
                "is_tier01_vessel": is_t01_vessel,
            })
            
    voy_df = pd.DataFrame(voyages)
    csv_out_path = f"{OUT_DIR}/g4_voyages.csv"
    voy_df.to_csv(csv_out_path, index=False, encoding="utf-8-sig")
    append_log(f"Saved {len(voy_df)} voyages to {csv_out_path}")
    
    # 8. Check RAM and runtime
    ram_after = get_ram_status()
    elapsed = time.time() - start_time
    
    summary = {
        "timestamp_kst": ram_after["timestamp_kst"],
        "elapsed_seconds": round(elapsed, 3),
        "audit": audit_results,
        "n_vessels": int(voy_df["rfid_id"].nunique()),
        "n_voyages_total": len(voy_df),
        "n_accident_related_voyages": int(voy_df["is_accident_related"].sum()),
        "n_control_voyages": int((~voy_df["is_accident_related"]).sum()),
        "w7_valid_voyages": int(voy_df["valid_w7"].sum()),
        "w7_invalid_voyages": int((~voy_df["valid_w7"]).sum()),
        "w3_valid_voyages": int(voy_df["valid_w3"].sum()),
        "w3_invalid_voyages": int((~voy_df["valid_w3"]).sum()),
        "ram_before": ram_before,
        "ram_after": ram_after,
    }
    summary_out_path = f"{OUT_DIR}/g4_summary.json"
    with open(summary_out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    append_log(f"Saved summary to {summary_out_path}")
    
    print("=== G4 Local Collapse Completed Successfully ===")
    print(f"Total voyages: {len(voy_df)}, Vessels: {voy_df['rfid_id'].nunique()}")
    print(f"w=7 valid voyages: {voy_df['valid_w7'].sum()} / {len(voy_df)} ({voy_df['valid_w7'].mean():.2%})")
    print(f"w=3 valid voyages: {voy_df['valid_w3'].sum()} / {len(voy_df)} ({voy_df['valid_w3'].mean():.2%})")
    print(f"Accident-related voyages: {voy_df['is_accident_related'].sum()}, Control: {(~voy_df['is_accident_related']).sum()}")
    print(f"RAM peak RSS: {ram_after['process_rss_mib']} MiB, Available: {ram_after['available_mib']} MiB")


if __name__ == "__main__":
    main()
