# -*- coding: utf-8 -*-
"""Component 2: Multi-Hypothesis Feature Extraction Engine.

Extracts offshore-masked physical features for each voyage:
- f1_offshore_sea_stop_streak: Longest consecutive '해상정지' in offshore waters.
- t_offshore_sea_stop_start: Timestamp when the longest offshore stop began.
- f2_offshore_speed_drop: Max drop (len[t-1] - len[t]) occurring in offshore waters.
- f2_speed_drop_ratio: Max relative drop (len[t-1] - len[t]) / len[t-1] in offshore waters.
- t_offshore_speed_drop: Timestamp of max offshore drop.
- f3_towing_straightness: Post-stoppage return straightness (disp / sum(len)).
- f3_towing_speed_std: Speed standard deviation during return (low std = uniform towing).
"""
import os
import sys
import time
import json
import datetime
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from h0_geofence_mask import build_vessel_harbor_trees, tag_offshore_rows

OUT_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
R8_DIR = "testB/round_008_linkage_audit_20261105"
DEVSET_POS_PATH = f"{R8_DIR}/devset_positives.csv"
DEV_HOURLY_PATH = f"{R8_DIR}/dev_hourly_scores.parquet"
ADD_HOURLY_PATH = f"{R8_DIR}/additional_hourly_scores.parquet"


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def extract_voyage_features(v_ts, v_len, v_bbox, v_lon, v_lat, v_state, v_offshore, v_score):
    t_start = int(v_ts[0])
    t_end = int(v_ts[-1])
    t_mid = int(v_ts[len(v_ts) // 2])
    voy_span = int(t_end - t_start + 1)
    voy_hours = int(len(v_ts))
    
    # Anomaly score metrics
    max_score = float(np.max(v_score)) if len(v_score) > 0 else 0.0
    mean_score = float(np.mean(v_score)) if len(v_score) > 0 else 0.0
    top3_score = float(np.mean(np.sort(v_score)[-min(3, len(v_score)):])) if len(v_score) > 0 else 0.0
    
    # --- Feature 1: Longest offshore '해상정지' streak ---
    is_offshore_stop = (v_state == "해상정지") & (v_offshore == True)
    max_streak = 0
    cur_streak = 0
    best_streak_start = t_mid
    cur_streak_start = t_mid
    total_offshore_stop_hours = int(np.sum(is_offshore_stop))
    
    for i in range(len(v_ts)):
        if is_offshore_stop[i]:
            if cur_streak == 0:
                cur_streak_start = int(v_ts[i])
            cur_streak += 1
            if cur_streak > max_streak:
                max_streak = cur_streak
                best_streak_start = cur_streak_start
        else:
            cur_streak = 0
            
    f1_offshore_stop_streak = float(max_streak)
    t_offshore_stop_start = int(best_streak_start) if max_streak > 0 else None
    
    # Also track any general sea stop (including unmasked)
    is_any_stop = (v_state == "해상정지")
    f1_any_stop_streak = float(np.max(np.concatenate([[0], np.diff(np.where(np.concatenate([[False], is_any_stop, [False]]))[0]) - 1]))) if np.any(is_any_stop) else 0.0
    
    # --- Feature 2: Offshore speed drop & steepness ---
    max_drop = 0.0
    max_drop_ratio = 0.0
    best_drop_ts = None
    best_drop_idx = None
    
    for i in range(1, len(v_ts)):
        dt = v_ts[i] - v_ts[i - 1]
        if 1 <= dt <= 2:
            prev_len = v_len[i - 1]
            curr_len = v_len[i]
            prev_offshore = v_offshore[i - 1]
            
            # Offshore speed drop when cruising (1500m <= prev_len <= 40000m, physically valid)
            if prev_offshore and 1500.0 <= prev_len <= 40000.0 and curr_len <= 40000.0:
                drop = prev_len - curr_len
                ratio = drop / max(prev_len, 1.0)
                if drop > max_drop:
                    max_drop = float(drop)
                    best_drop_ts = int(v_ts[i])
                    best_drop_idx = i
                if ratio > max_drop_ratio:
                    max_drop_ratio = float(ratio)
                    
    f2_offshore_speed_drop = float(max_drop)
    f2_speed_drop_ratio = float(max_drop_ratio)
    t_offshore_drop = best_drop_ts
    
    # --- Feature 3: Post-incident towing straightness & uniformity ---
    pivot_idx = best_drop_idx if best_drop_idx is not None else (len(v_ts) // 2)
    post_lens = v_len[pivot_idx:]
    
    if len(post_lens) > 1 and np.isfinite(v_lon[pivot_idx]) and np.isfinite(v_lon[-1]):
        disp = float(haversine(v_lon[pivot_idx], v_lat[pivot_idx], v_lon[-1], v_lat[-1]))
        path_len = float(np.sum(post_lens))
        f3_straightness = float(disp / max(path_len, 1.0))
        f3_straightness = min(1.0, max(0.0, f3_straightness))
        f3_speed_std = float(np.std(post_lens))
    else:
        f3_straightness = 0.0
        f3_speed_std = 0.0
        
    return {
        "t_start": t_start,
        "t_end": t_end,
        "t_mid": t_mid,
        "voy_span": voy_span,
        "voy_hours": voy_hours,
        "f1_offshore_stop_streak": f1_offshore_stop_streak,
        "t_offshore_stop_start": t_offshore_stop_start,
        "total_offshore_stop_hours": total_offshore_stop_hours,
        "f1_any_stop_streak": f1_any_stop_streak,
        "f2_offshore_speed_drop": f2_offshore_speed_drop,
        "f2_speed_drop_ratio": f2_speed_drop_ratio,
        "t_offshore_drop": t_offshore_drop,
        "f3_straightness": f3_straightness,
        "f3_speed_std": f3_speed_std,
        "max_score": max_score,
        "mean_score": mean_score,
        "top3_score": top3_score,
    }


def main():
    start_time = time.time()
    print("Starting h1_hypothesis_engine.py: Multi-hypothesis feature extraction.")
    
    pos = pd.read_csv(DEVSET_POS_PATH)
    pos["rfid_id"] = pos["rfid_id"].astype(str)
    target_vessels_int = set(pos["rfid_id"].astype(int).unique())
    tier01_vessels = set(pos[pos["tier"] <= 1]["rfid_id"].unique())
    
    vessel_accidents = {}
    for vid, group in pos.groupby("rfid_id"):
        vessel_accidents[vid] = [
            {"acc_id": int(r["acc_id"]), "acc_ts": int(r["acc_ts"]), "tier": int(r["tier"])}
            for _, r in group.iterrows()
        ]
        
    # Read parquet
    cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state", "score"]
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
    df = raw_df.drop_duplicates(subset=["rfid_id", "ts"], keep="first").copy()
    df = df.sort_values(["rfid_id", "ts"]).reset_index(drop=True)
    
    # 1. Apply Component 1 Harbor Geofence Masking
    print("Building harbor geofence trees and tagging offshore rows...")
    harbor_trees = build_vessel_harbor_trees(df)
    df = tag_offshore_rows(df, harbor_trees, radius_km=2.0)
    print(f"Offshore rows fraction: {df['is_offshore'].mean():.2%}")
    
    # 2. Extract features per voyage
    records = []
    for vid, g in df.groupby("rfid_id", sort=True):
        ts = g["ts"].to_numpy()
        lens = g["len_m"].to_numpy(dtype=float)
        bboxes = g["bbox_m"].to_numpy(dtype=float)
        lons = g["cen_lon"].to_numpy(dtype=float)
        lats = g["cen_lat"].to_numpy(dtype=float)
        states = g["state"].to_numpy()
        offshores = g["is_offshore"].to_numpy(dtype=bool)
        scores = g["score"].to_numpy(dtype=float)
        
        diffs = np.diff(ts)
        seg = np.concatenate([[0], np.cumsum(diffs >= 6)])
        n_voyages = int(seg.max()) + 1
        is_t01 = (vid in tier01_vessels)
        acc_list = vessel_accidents.get(vid, [])
        
        for v in range(n_voyages):
            idx = np.where(seg == v)[0]
            feats = extract_voyage_features(
                ts[idx], lens[idx], bboxes[idx], lons[idx], lats[idx], states[idx], offshores[idx], scores[idx]
            )
            
            t_s = feats["t_start"]
            t_e = feats["t_end"]
            matched_accs = [a for a in acc_list if (t_s - 6 <= a["acc_ts"] <= t_e + 6)]
            is_acc_rel = len(matched_accs) > 0
            
            records.append({
                "rfid_id": vid,
                "voy": int(v),
                "n_voyages": n_voyages,
                "eligible_rem_ge_10": bool(n_voyages >= 11),
                "is_tier01_vessel": is_t01,
                "is_accident_related": is_acc_rel,
                "matched_acc_ids": ";".join(str(a["acc_id"]) for a in matched_accs) if is_acc_rel else "",
                "matched_tiers": ";".join(str(a["tier"]) for a in matched_accs) if is_acc_rel else "",
                **feats,
            })
            
    df_out = pd.DataFrame(records)
    csv_path = f"{OUT_DIR}/voyage_features_all_hypotheses.csv"
    df_out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Extraction complete in {time.time() - start_time:.2f}s. Saved {len(df_out)} voyages to {csv_path}")


if __name__ == "__main__":
    main()
