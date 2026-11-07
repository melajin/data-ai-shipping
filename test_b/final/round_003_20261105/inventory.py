"""
Inventory script for Round 3 (2026-11-05).
Performs bounded descriptive gear and behavior inventory on 82 RFIDs.
Follows all memory and core alignment rules strictly.
"""

import sys
import os
import time
import json
import hashlib
import tracemalloc
from pathlib import Path
import psutil
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

def get_ram_snapshot():
    vm = psutil.virtual_memory()
    proc = psutil.Process(os.getpid())
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_ram_bytes": vm.total,
        "available_ram_bytes": vm.available,
        "used_ram_bytes": vm.used,
        "percent_used": vm.percent,
        "process_rss_bytes": proc.memory_info().rss,
        "process_vms_bytes": proc.memory_info().vms,
    }

def check_preflight_ram(required_extra_mib=512, reserve_mib=640):
    vm = psutil.virtual_memory()
    avail_mib = vm.available / (1024 * 1024)
    threshold_mib = required_extra_mib + reserve_mib
    print(f"Preflight RAM check: Available={avail_mib:.1f} MiB, Required={threshold_mib:.1f} MiB (Extra<={required_extra_mib} + Reserve={reserve_mib})")
    
    # Check running python processes
    py_procs = []
    current_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in p.name().lower() and p.pid != current_pid:
                py_procs.append({"pid": p.pid, "name": p.name(), "cmdline": p.cmdline()[:3]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    if py_procs:
        print(f"Warning: {len(py_procs)} other python process(es) detected: {py_procs}")
    else:
        print("Confirmed: No other data jobs or python processes running.")
        
    if avail_mib < threshold_mib:
        raise RuntimeError(f"RAM check failed: Available {avail_mib:.1f} MiB is less than required {threshold_mib:.1f} MiB. Halting per memory operating rules.")
    return avail_mib, threshold_mib, py_procs

def compute_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def main():
    start_time = time.time()
    tracemalloc.start()
    
    output_dir = Path(__file__).resolve().parent
    workspace_root = output_dir.parents[2]
    
    print(f"Output directory: {output_dir}")
    print(f"Workspace root: {workspace_root}")
    
    # Preflight RAM check
    ram_before = get_ram_snapshot()
    avail_mib, thresh_mib, py_procs = check_preflight_ram()
    
    # Source file definitions
    devset_positives_path = workspace_root / "testB" / "과거" / "round_008_linkage_audit_20261105" / "devset_positives.csv"
    dev_hourly_scores_path = workspace_root / "testB" / "과거" / "round_008_linkage_audit_20261105" / "dev_hourly_scores.parquet"
    additional_hourly_scores_path = workspace_root / "testB" / "과거" / "round_008_linkage_audit_20261105" / "additional_hourly_scores.parquet"
    train_cache_paths = [
        workspace_root / "29-30일 모델 심층 분석" / "분석 결과" / "outputs" / "remeasure_20261031" / f"rows_train_{i}.parquet"
        for i in range(1, 7)
    ]
    
    source_files = [devset_positives_path, dev_hourly_scores_path, additional_hourly_scores_path] + train_cache_paths
    for sf in source_files:
        if not sf.exists():
            raise FileNotFoundError(f"Required source file not found: {sf}")
            
    print("\n--- Step 1: Loading devset_positives for 82 RFIDs ---")
    positives_df = pd.read_csv(devset_positives_path, usecols=["rfid_id"], dtype={"rfid_id": str})
    rfid_list = sorted(positives_df["rfid_id"].dropna().unique().tolist())
    assert len(rfid_list) == 82, f"Expected 82 RFIDs, got {len(rfid_list)}"
    print(f"Loaded {len(rfid_list)} unique RFIDs from devset_positives.csv")
    
    print("\n--- Step 2: Reading Train Monthly Cache Footers & Streaming fishing_code ---")
    # Read footers (metadata) first
    train_metadata = {}
    for p in train_cache_paths:
        meta = pq.read_metadata(p)
        train_metadata[p.name] = {
            "num_rows": meta.num_rows,
            "num_columns": meta.num_columns,
            "column_names": meta.schema.names,
            "file_size_bytes": p.stat().st_size
        }
        print(f"Footer {p.name}: rows={meta.num_rows}, cols={meta.num_columns}")
        
    # Stream only necessary columns ['rfid_id', 'fishing_code'] with RFID filter
    rfid_set = set(rfid_list)
    train_stream_records = []
    for p in train_cache_paths:
        dataset = ds.dataset(p, format="parquet")
        # filter to 82 RFIDs and select only ['rfid_id', 'fishing_code']
        table = dataset.to_table(columns=["rfid_id", "fishing_code"], filter=ds.field("rfid_id").isin(rfid_list))
        df_chunk = table.to_pandas()
        train_stream_records.append(df_chunk)
        print(f"Streamed {p.name}: matched {len(df_chunk)} rows")
        
    train_matched = pd.concat(train_stream_records, ignore_index=True)
    print(f"Total matched rows in train caches: {len(train_matched)}")
    
    # Build gear registry per vessel
    gear_registry_rows = []
    vessel_gear_map = {}
    for rfid in rfid_list:
        v_rows = train_matched[train_matched["rfid_id"] == rfid]
        n_rows = len(v_rows)
        raw_codes = sorted(set(str(c) for c in v_rows["fishing_code"].dropna()))
        is_missing = (n_rows == 0 or len(raw_codes) == 0)
        is_mixed = (len(raw_codes) > 1)
        is_single = (len(raw_codes) == 1)
        primary_gear = raw_codes[0] if is_single else ("MIXED" if is_mixed else "MISSING")
        raw_str = ";".join(raw_codes) if raw_codes else "NONE"
        
        gear_registry_rows.append({
            "rfid_id": rfid,
            "fishing_code_raw": raw_str,
            "n_distinct_codes": len(raw_codes),
            "total_train_rows": n_rows,
            "is_single_code": is_single,
            "is_mixed": is_mixed,
            "is_missing": is_missing,
            "primary_gear": primary_gear
        })
        vessel_gear_map[rfid] = primary_gear
        
    gear_registry_df = pd.DataFrame(gear_registry_rows)
    gear_registry_csv_path = output_dir / "gear_registry.csv"
    gear_registry_df.to_csv(gear_registry_csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved {gear_registry_csv_path} with {len(gear_registry_df)} rows")
    print("Gear distribution across 82 vessels:")
    print(gear_registry_df["primary_gear"].value_counts())
    
    print("\n--- Step 3: Loading Numeric Behavior from Round008 Score Parquets & Canonicalization ---")
    score_cols = ["rfid_id_int", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
    int_rfids = [int(x) for x in rfid_list]
    
    score_tables = []
    for sp in [dev_hourly_scores_path, additional_hourly_scores_path]:
        meta = pq.read_metadata(sp)
        print(f"Score Parquet footer {sp.name}: rows={meta.num_rows}, cols={meta.num_columns}")
        dataset = ds.dataset(sp, format="parquet")
        table = dataset.to_table(columns=score_cols, filter=ds.field("rfid_id_int").isin(int_rfids))
        score_tables.append(table.to_pandas())
        print(f"  Loaded {len(score_tables[-1])} rows from {sp.name}")
        
    raw_scores = pd.concat(score_tables, ignore_index=True)
    raw_scores = raw_scores.rename(columns={"rfid_id_int": "rfid_id"})
    raw_scores["rfid_id"] = raw_scores["rfid_id"].astype(str)
    print(f"Total raw score rows: {len(raw_scores)}")
    
    # Canonicalization: drop exact duplicates, sort by [rfid_id, ts, source_ordinal], drop hourly duplicate keeping min-source_ordinal
    exact_dedup = raw_scores.drop_duplicates()
    exact_dups_removed = len(raw_scores) - len(exact_dedup)
    print(f"Exact duplicates removed: {exact_dups_removed}")
    
    sorted_scores = exact_dedup.sort_values(["rfid_id", "ts", "source_ordinal"], kind="mergesort")
    canonical = sorted_scores.drop_duplicates(["rfid_id", "ts"], keep="first").reset_index(drop=True)
    hourly_dups_removed = len(exact_dedup) - len(canonical)
    print(f"Hourly duplicates removed: {hourly_dups_removed}")
    print(f"Canonical rows count: {len(canonical)}")
    assert len(canonical) == 99677, f"Assertion failed: expected 99,677 canonical rows, got {len(canonical)}"
    print("Assertion PASSED: Exactly 99,677 canonical rows verified!")
    
    # Add gear column
    canonical["gear_label"] = canonical["rfid_id"].map(vessel_gear_map)
    canonical["is_small_path"] = (canonical["len_m"] <= 100.0) & (canonical["bbox_m"] <= 100.0)
    
    print("\n--- Step 4: Computing Per-Vessel Behavior Summaries ---")
    per_vessel_rows = []
    
    for rfid in rfid_list:
        v_df = canonical[canonical["rfid_id"] == rfid].sort_values("ts").reset_index(drop=True)
        gear = vessel_gear_map[rfid]
        n_obs = len(v_df)
        
        # Timeline and gaps
        ts_vals = v_df["ts"].values
        min_ts = int(ts_vals[0])
        max_ts = int(ts_vals[-1])
        span_hours = max_ts - min_ts + 1
        gap_hours_total = span_hours - n_obs
        
        ts_diffs = np.diff(ts_vals)
        gap_indices = np.where(ts_diffs > 1)[0]
        n_gap_events = len(gap_indices)
        if n_gap_events > 0:
            gap_durations = ts_diffs[gap_indices] - 1
            mean_gap_hours = float(np.mean(gap_durations))
            median_gap_hours = float(np.median(gap_durations))
            max_gap_hours = int(np.max(gap_durations))
        else:
            mean_gap_hours = 0.0
            median_gap_hours = 0.0
            max_gap_hours = 0
            
        # len_m and bbox_m distributions
        len_vals = v_df["len_m"].values
        bbox_vals = v_df["bbox_m"].values
        
        len_mean = float(np.mean(len_vals))
        len_std = float(np.std(len_vals))
        len_min = float(np.min(len_vals))
        len_p25 = float(np.percentile(len_vals, 25))
        len_median = float(np.median(len_vals))
        len_p75 = float(np.percentile(len_vals, 75))
        len_max = float(np.max(len_vals))
        
        bbox_mean = float(np.mean(bbox_vals))
        bbox_std = float(np.std(bbox_vals))
        bbox_min = float(np.min(bbox_vals))
        bbox_p25 = float(np.percentile(bbox_vals, 25))
        bbox_median = float(np.median(bbox_vals))
        bbox_p75 = float(np.percentile(bbox_vals, 75))
        bbox_max = float(np.max(bbox_vals))
        
        # Small-path observations
        is_small = v_df["is_small_path"].values
        n_small_path_obs = int(np.sum(is_small))
        pct_small_path_obs = float(n_small_path_obs / n_obs * 100.0)
        
        # Consecutive-hour small-path runs
        # A run consists of consecutive observed hours where ts[i] == ts[i-1] + 1 and is_small is True
        runs = []
        curr_run = []
        for i in range(n_obs):
            if is_small[i]:
                if not curr_run:
                    curr_run.append(i)
                elif ts_vals[i] == ts_vals[curr_run[-1]] + 1:
                    curr_run.append(i)
                else:
                    runs.append(curr_run)
                    curr_run = [i]
            else:
                if curr_run:
                    runs.append(curr_run)
                    curr_run = []
        if curr_run:
            runs.append(curr_run)
            
        n_runs = len(runs)
        run_lens = [len(r) for r in runs]
        
        if n_runs > 0:
            run_len_min = int(min(run_lens))
            run_len_median = float(np.median(run_lens))
            run_len_mean = float(np.mean(run_lens))
            run_len_max = int(max(run_lens))
        else:
            run_len_min = 0
            run_len_median = 0.0
            run_len_mean = 0.0
            run_len_max = 0
            
        # Buckets: 1h, 2-3h, 4-6h, 7-12h, 13-24h, >=25h
        run_b_1h = sum(1 for l in run_lens if l == 1)
        run_b_2_3h = sum(1 for l in run_lens if 2 <= l <= 3)
        run_b_4_6h = sum(1 for l in run_lens if 4 <= l <= 6)
        run_b_7_12h = sum(1 for l in run_lens if 7 <= l <= 12)
        run_b_13_24h = sum(1 for l in run_lens if 13 <= l <= 24)
        run_b_ge25h = sum(1 for l in run_lens if l >= 25)
        
        # Run termination / departure / censoring
        runs_censored_right = 0
        runs_ended_by_gap = 0
        runs_ended_by_departure = 0
        dep_len_gt100_bbox_le100 = 0
        dep_len_le100_bbox_gt100 = 0
        dep_both_gt100 = 0
        departure_lens = []
        departure_bboxes = []
        
        for r in runs:
            last_idx = r[-1]
            if last_idx == n_obs - 1:
                # Reached end of vessel observation
                runs_censored_right += 1
            else:
                next_idx = last_idx + 1
                if ts_vals[next_idx] > ts_vals[last_idx] + 1:
                    # Broken by an unobserved gap
                    runs_ended_by_gap += 1
                else:
                    # Next observation is consecutive hour, so it broke by condition change (departure)
                    runs_ended_by_departure += 1
                    dep_l = len_vals[next_idx]
                    dep_b = bbox_vals[next_idx]
                    departure_lens.append(dep_l)
                    departure_bboxes.append(dep_b)
                    if dep_l > 100.0 and dep_b <= 100.0:
                        dep_len_gt100_bbox_le100 += 1
                    elif dep_l <= 100.0 and dep_b > 100.0:
                        dep_len_le100_bbox_gt100 += 1
                    else:
                        dep_both_gt100 += 1
                        
        departure_len_median = float(np.median(departure_lens)) if departure_lens else 0.0
        departure_bbox_median = float(np.median(departure_bboxes)) if departure_bboxes else 0.0
        
        # Repeated 0.05-degree cell occupancy (repeated area only, never harbor)
        # Discretize: lon and lat rounded to 0.05 step
        lon_cells = np.round(v_df["cen_lon"].values / 0.05) * 0.05
        lat_cells = np.round(v_df["cen_lat"].values / 0.05) * 0.05
        cell_keys = [f"{lon:.3f}_{lat:.3f}" for lon, lat in zip(lon_cells, lat_cells)]
        cell_series = pd.Series(cell_keys)
        cell_counts = cell_series.value_counts()
        
        n_distinct_cells = len(cell_counts)
        repeated_cells = cell_counts[cell_counts >= 2]
        n_repeated_cells = len(repeated_cells)
        n_repeated_cell_obs = int(repeated_cells.sum()) if n_repeated_cells > 0 else 0
        repeated_cell_occupancy_ratio = float(n_repeated_cell_obs / n_obs)
        max_cell_obs = int(cell_counts.iloc[0])
        max_single_cell_occupancy_ratio = float(max_cell_obs / n_obs)
        
        per_vessel_rows.append({
            "rfid_id": rfid,
            "gear_label": gear,
            "n_observations": n_obs,
            "min_ts": min_ts,
            "max_ts": max_ts,
            "span_hours": span_hours,
            "gap_hours_total": gap_hours_total,
            "n_gap_events": n_gap_events,
            "mean_gap_hours": round(mean_gap_hours, 2),
            "median_gap_hours": round(median_gap_hours, 2),
            "max_gap_hours": max_gap_hours,
            "len_m_mean": round(len_mean, 2),
            "len_m_std": round(len_std, 2),
            "len_m_min": round(len_min, 2),
            "len_m_p25": round(len_p25, 2),
            "len_m_median": round(len_median, 2),
            "len_m_p75": round(len_p75, 2),
            "len_m_max": round(len_max, 2),
            "bbox_m_mean": round(bbox_mean, 2),
            "bbox_m_std": round(bbox_std, 2),
            "bbox_m_min": round(bbox_min, 2),
            "bbox_m_p25": round(bbox_p25, 2),
            "bbox_m_median": round(bbox_median, 2),
            "bbox_m_p75": round(bbox_p75, 2),
            "bbox_m_max": round(bbox_max, 2),
            "n_small_path_obs": n_small_path_obs,
            "pct_small_path_obs": round(pct_small_path_obs, 2),
            "n_small_path_runs": n_runs,
            "run_len_min": run_len_min,
            "run_len_median": round(run_len_median, 2),
            "run_len_mean": round(run_len_mean, 2),
            "run_len_max": run_len_max,
            "run_b_1h": run_b_1h,
            "run_b_2_3h": run_b_2_3h,
            "run_b_4_6h": run_b_4_6h,
            "run_b_7_12h": run_b_7_12h,
            "run_b_13_24h": run_b_13_24h,
            "run_b_ge25h": run_b_ge25h,
            "runs_censored_right": runs_censored_right,
            "runs_ended_by_gap": runs_ended_by_gap,
            "runs_ended_by_departure": runs_ended_by_departure,
            "dep_len_gt100_bbox_le100": dep_len_gt100_bbox_le100,
            "dep_len_le100_bbox_gt100": dep_len_le100_bbox_gt100,
            "dep_both_gt100": dep_both_gt100,
            "departure_len_median": round(departure_len_median, 2),
            "departure_bbox_median": round(departure_bbox_median, 2),
            "n_distinct_cells": n_distinct_cells,
            "n_repeated_cells": n_repeated_cells,
            "n_repeated_cell_obs": n_repeated_cell_obs,
            "repeated_cell_occupancy_ratio": round(repeated_cell_occupancy_ratio, 4),
            "max_single_cell_occupancy_ratio": round(max_single_cell_occupancy_ratio, 4),
            "repeated_cell_interpretation": "repeated area only, never harbor",
            "route_following_status": "unavailable (point-level geometry/heading missing in hourly frame)",
            "within_part_straightness_status": "unavailable (point-level geometry missing in hourly frame)"
        })
        
    per_vessel_df = pd.DataFrame(per_vessel_rows)
    per_vessel_csv_path = output_dir / "per_vessel.csv"
    per_vessel_df.to_csv(per_vessel_csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved {per_vessel_csv_path} with {len(per_vessel_df)} vessels")
    
    print("\n--- Step 5: Computing Vessel-Balanced Per-Gear Summaries ---")
    # Vessel-balanced group summary: group by gear, compute statistics over vessel-level metrics
    group_summary_rows = []
    gear_groups = list(per_vessel_df["gear_label"].unique()) + ["ALL_VESSELS"]
    
    for g in gear_groups:
        if g == "ALL_VESSELS":
            gdf = per_vessel_df
        else:
            gdf = per_vessel_df[per_vessel_df["gear_label"] == g]
            
        n_vessels = len(gdf)
        total_obs = int(gdf["n_observations"].sum())
        
        group_summary_rows.append({
            "gear_label": g,
            "n_vessels": n_vessels,
            "total_canonical_observations": total_obs,
            "obs_per_vessel_mean": round(float(gdf["n_observations"].mean()), 1),
            "obs_per_vessel_median": round(float(gdf["n_observations"].median()), 1),
            "obs_per_vessel_min": int(gdf["n_observations"].min()),
            "obs_per_vessel_max": int(gdf["n_observations"].max()),
            
            # Gaps (vessel balanced)
            "gap_hours_per_vessel_mean": round(float(gdf["gap_hours_total"].mean()), 1),
            "gap_hours_per_vessel_median": round(float(gdf["gap_hours_total"].median()), 1),
            "gap_events_per_vessel_median": round(float(gdf["n_gap_events"].median()), 1),
            
            # Length and Bbox (vessel balanced median of medians)
            "vessel_median_len_m_mean": round(float(gdf["len_m_median"].mean()), 1),
            "vessel_median_len_m_median": round(float(gdf["len_m_median"].median()), 1),
            "vessel_median_bbox_m_mean": round(float(gdf["bbox_m_median"].mean()), 1),
            "vessel_median_bbox_m_median": round(float(gdf["bbox_m_median"].median()), 1),
            
            # Small-path percentage (vessel balanced)
            "pct_small_path_mean": round(float(gdf["pct_small_path_obs"].mean()), 2),
            "pct_small_path_median": round(float(gdf["pct_small_path_obs"].median()), 2),
            "pct_small_path_min": round(float(gdf["pct_small_path_obs"].min()), 2),
            "pct_small_path_max": round(float(gdf["pct_small_path_obs"].max()), 2),
            
            # Run counts and run lengths (vessel balanced)
            "runs_per_vessel_mean": round(float(gdf["n_small_path_runs"].mean()), 1),
            "runs_per_vessel_median": round(float(gdf["n_small_path_runs"].median()), 1),
            "vessel_run_len_median_mean": round(float(gdf["run_len_median"].mean()), 2),
            "vessel_run_len_median_median": round(float(gdf["run_len_median"].median()), 2),
            "vessel_run_len_max_median": round(float(gdf["run_len_max"].median()), 1),
            
            # Run length buckets total count in group
            "group_run_b_1h": int(gdf["run_b_1h"].sum()),
            "group_run_b_2_3h": int(gdf["run_b_2_3h"].sum()),
            "group_run_b_4_6h": int(gdf["run_b_4_6h"].sum()),
            "group_run_b_7_12h": int(gdf["run_b_7_12h"].sum()),
            "group_run_b_13_24h": int(gdf["run_b_13_24h"].sum()),
            "group_run_b_ge25h": int(gdf["run_b_ge25h"].sum()),
            
            # Run endings & censoring total count in group
            "group_runs_censored_right": int(gdf["runs_censored_right"].sum()),
            "group_runs_ended_by_gap": int(gdf["runs_ended_by_gap"].sum()),
            "group_runs_ended_by_departure": int(gdf["runs_ended_by_departure"].sum()),
            "group_dep_len_gt100_bbox_le100": int(gdf["dep_len_gt100_bbox_le100"].sum()),
            "group_dep_len_le100_bbox_gt100": int(gdf["dep_len_le100_bbox_gt100"].sum()),
            "group_dep_both_gt100": int(gdf["dep_both_gt100"].sum()),
            
            # Repeated cell occupancy (vessel balanced)
            "repeated_cell_occupancy_mean": round(float(gdf["repeated_cell_occupancy_ratio"].mean()), 4),
            "repeated_cell_occupancy_median": round(float(gdf["repeated_cell_occupancy_ratio"].median()), 4),
            "max_single_cell_occupancy_mean": round(float(gdf["max_single_cell_occupancy_ratio"].mean()), 4),
            "max_single_cell_occupancy_median": round(float(gdf["max_single_cell_occupancy_ratio"].median()), 4),
        })
        
    group_summary_df = pd.DataFrame(group_summary_rows)
    group_summary_csv_path = output_dir / "group_summary.csv"
    group_summary_df.to_csv(group_summary_csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved {group_summary_csv_path} with {len(group_summary_df)} rows")
    
    print("\n--- Step 6: Deterministic Case Selection per Single-Code Gear ---")
    # For each single-code gear:
    # 1. filter vessels with >= 72 valid observations
    # 2. lexicographically first RFID
    # 3. find first qualifying small-path run (len<=100 and bbox<=100)
    # 4. save run observations plus adjacent prior and post observed rows with source_ordinal lineage
    single_gears = sorted(set(g for g in vessel_gear_map.values() if g not in ["MIXED", "MISSING"]))
    print(f"Available single-code gears: {single_gears}")
    
    case_rows = []
    case_selection_summary = []
    
    for gear in single_gears:
        vessels_in_gear = [r for r, g in vessel_gear_map.items() if g == gear]
        qualifying_vessels = [
            r for r in vessels_in_gear
            if per_vessel_df.loc[per_vessel_df["rfid_id"] == r, "n_observations"].iloc[0] >= 72
        ]
        qualifying_vessels.sort()
        
        if not qualifying_vessels:
            print(f"Gear {gear}: SHORTAGE (no vessels with >= 72 observations)")
            case_selection_summary.append({
                "gear_label": gear,
                "chosen_rfid": None,
                "status": "SHORTAGE",
                "available_vessels_ge72": 0
            })
            continue
            
        chosen_rfid = qualifying_vessels[0]
        v_df = canonical[canonical["rfid_id"] == chosen_rfid].sort_values("ts").reset_index(drop=True)
        is_small = v_df["is_small_path"].values
        ts_vals = v_df["ts"].values
        n_obs = len(v_df)
        
        # Find consecutive runs
        runs = []
        curr_run = []
        for i in range(n_obs):
            if is_small[i]:
                if not curr_run:
                    curr_run.append(i)
                elif ts_vals[i] == ts_vals[curr_run[-1]] + 1:
                    curr_run.append(i)
                else:
                    runs.append(curr_run)
                    curr_run = [i]
            else:
                if curr_run:
                    runs.append(curr_run)
                    curr_run = []
        if curr_run:
            runs.append(curr_run)
            
        if not runs:
            print(f"Gear {gear}: chosen RFID {chosen_rfid} has NO small-path runs!")
            case_selection_summary.append({
                "gear_label": gear,
                "chosen_rfid": chosen_rfid,
                "status": "NO_SMALL_PATH_RUN",
                "available_vessels_ge72": len(qualifying_vessels)
            })
            continue
            
        first_run = runs[0]
        start_idx = first_run[0]
        end_idx = first_run[-1]
        run_len = len(first_run)
        
        prior_idx = start_idx - 1 if start_idx > 0 else None
        post_idx = end_idx + 1 if end_idx < n_obs - 1 else None
        
        case_info = {
            "gear_label": gear,
            "chosen_rfid": chosen_rfid,
            "total_observations": n_obs,
            "run_length_hours": run_len,
            "run_start_ts": int(ts_vals[start_idx]),
            "run_end_ts": int(ts_vals[end_idx]),
            "has_prior_adjacent": prior_idx is not None,
            "has_post_adjacent": post_idx is not None,
            "departure_type": (
                "RIGHT_CENSORED" if post_idx is None else (
                    "GAP_BREAK" if ts_vals[post_idx] > ts_vals[end_idx] + 1 else "CONDITION_CHANGE"
                )
            )
        }
        case_selection_summary.append(case_info)
        print(f"Gear {gear}: chosen RFID {chosen_rfid}, run_len={run_len}h, ts={case_info['run_start_ts']}..{case_info['run_end_ts']}, dep={case_info['departure_type']}")
        
        # Add prior adjacent row
        if prior_idx is not None:
            p_row = v_df.iloc[prior_idx]
            case_rows.append({
                "gear_label": gear,
                "rfid_id": chosen_rfid,
                "case_role": "prior_adjacent",
                "step_offset": -1,
                "ts": int(p_row["ts"]),
                "source_ordinal": int(p_row["source_ordinal"]),
                "len_m": round(float(p_row["len_m"]), 2),
                "bbox_m": round(float(p_row["bbox_m"]), 2),
                "cen_lon": round(float(p_row["cen_lon"]), 5),
                "cen_lat": round(float(p_row["cen_lat"]), 5),
                "score": round(float(p_row["score"]), 4),
                "is_small_path": bool(p_row["is_small_path"]),
                "cell_005_lon": round(round(float(p_row["cen_lon"]) / 0.05) * 0.05, 3),
                "cell_005_lat": round(round(float(p_row["cen_lat"]) / 0.05) * 0.05, 3),
            })
            
        # Add run rows
        for step_i, idx in enumerate(first_run):
            r_row = v_df.iloc[idx]
            case_rows.append({
                "gear_label": gear,
                "rfid_id": chosen_rfid,
                "case_role": "run_observation",
                "step_offset": step_i,
                "ts": int(r_row["ts"]),
                "source_ordinal": int(r_row["source_ordinal"]),
                "len_m": round(float(r_row["len_m"]), 2),
                "bbox_m": round(float(r_row["bbox_m"]), 2),
                "cen_lon": round(float(r_row["cen_lon"]), 5),
                "cen_lat": round(float(r_row["cen_lat"]), 5),
                "score": round(float(r_row["score"]), 4),
                "is_small_path": bool(r_row["is_small_path"]),
                "cell_005_lon": round(round(float(r_row["cen_lon"]) / 0.05) * 0.05, 3),
                "cell_005_lat": round(round(float(r_row["cen_lat"]) / 0.05) * 0.05, 3),
            })
            
        # Add post adjacent row
        if post_idx is not None:
            post_row = v_df.iloc[post_idx]
            case_rows.append({
                "gear_label": gear,
                "rfid_id": chosen_rfid,
                "case_role": "post_adjacent",
                "step_offset": run_len,
                "ts": int(post_row["ts"]),
                "source_ordinal": int(post_row["source_ordinal"]),
                "len_m": round(float(post_row["len_m"]), 2),
                "bbox_m": round(float(post_row["bbox_m"]), 2),
                "cen_lon": round(float(post_row["cen_lon"]), 5),
                "cen_lat": round(float(post_row["cen_lat"]), 5),
                "score": round(float(post_row["score"]), 4),
                "is_small_path": bool(post_row["is_small_path"]),
                "cell_005_lon": round(round(float(post_row["cen_lon"]) / 0.05) * 0.05, 3),
                "cell_005_lat": round(round(float(post_row["cen_lat"]) / 0.05) * 0.05, 3),
            })
            
    case_df = pd.DataFrame(case_rows)
    case_csv_path = output_dir / "case_observations.csv"
    case_df.to_csv(case_csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved {case_csv_path} with {len(case_df)} rows")
    
    print("\n--- Step 7: Computing Source Hashes & Generating Receipts ---")
    source_hashes = {}
    for sf in source_files:
        h = compute_sha256(sf)
        source_hashes[sf.name] = {
            "relative_path": str(sf.relative_to(workspace_root)).replace("\\", "/"),
            "sha256": h,
            "size_bytes": sf.stat().st_size
        }
        print(f"Hash {sf.name}: {h}")
        
    current_tracemalloc, peak_tracemalloc = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ram_after = get_ram_snapshot()
    elapsed_sec = time.time() - start_time
    
    execution_receipt = {
        "execution_meta": {
            "task_id": "task_08043a3d31b2",
            "dispatch_id": "ctx_d9b85151783d",
            "coordinator_session": "codex_a55fd2e5_500d_4503_925f_12df6a69b424",
            "agent_model": "Gemini 3.8 Flash (High)",
            "execution_date": time.strftime("%Y-%m-%d %H:%M:%S%z"),
            "elapsed_seconds": round(elapsed_sec, 2),
        },
        "preflight_ram_check": {
            "checked_at": ram_before["timestamp"],
            "total_system_ram_mib": round(ram_before["total_ram_bytes"] / (1024 * 1024), 1),
            "available_ram_before_mib": round(ram_before["available_ram_bytes"] / (1024 * 1024), 1),
            "percent_used_before": ram_before["percent_used"],
            "required_extra_mib": 512,
            "reserve_mib": 640,
            "threshold_required_mib": 1152,
            "headroom_confirmed": True,
            "other_python_processes_running": len(py_procs),
        },
        "memory_during_run": {
            "tracemalloc_peak_mib": round(peak_tracemalloc / (1024 * 1024), 2),
            "process_rss_before_mib": round(ram_before["process_rss_bytes"] / (1024 * 1024), 2),
            "process_rss_after_mib": round(ram_after["process_rss_bytes"] / (1024 * 1024), 2),
            "delta_rss_mib": round((ram_after["process_rss_bytes"] - ram_before["process_rss_bytes"]) / (1024 * 1024), 2),
            "available_ram_after_mib": round(ram_after["available_ram_bytes"] / (1024 * 1024), 1),
        },
        "source_hashes": source_hashes,
        "data_assertions": {
            "target_rfid_count": 82,
            "verified_rfid_count": len(rfid_list),
            "raw_train_matched_rows": len(train_matched),
            "canonical_rows_target": 99677,
            "canonical_rows_verified": len(canonical),
            "exact_duplicates_removed": exact_dups_removed,
            "hourly_duplicates_removed": hourly_dups_removed,
            "assertion_canonical_rows_exact_99677": True,
        }
    }
    
    receipt_path = output_dir / "execution_receipt.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(execution_receipt, f, indent=2, ensure_ascii=False)
    print(f"Saved {receipt_path}")
    
    # Save summary.json
    summary_obj = {
        "round": 3,
        "round_title": "Descriptive Gear and Behavior Inventory",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "agent": "Gemini 3.8 Flash (High)",
        "hardware_environment": {
            "os": sys.platform,
            "total_ram_gb": round(ram_before["total_ram_bytes"] / (1024**3), 2),
            "peak_memory_used_mib": round(peak_tracemalloc / (1024 * 1024), 2),
            "runtime_seconds": round(elapsed_sec, 2),
        },
        "gear_distribution_82_rfids": {
            "연안복합": int((gear_registry_df["primary_gear"] == "연안복합").sum()),
            "자망": int((gear_registry_df["primary_gear"] == "자망").sum()),
            "통발": int((gear_registry_df["primary_gear"] == "통발").sum()),
            "채낚기연승낚시": int((gear_registry_df["primary_gear"] == "채낚기연승낚시").sum()),
            "mixed_vessels": int(gear_registry_df["is_mixed"].sum()),
            "missing_vessels": int(gear_registry_df["is_missing"].sum()),
            "total_vessels": len(gear_registry_df),
        },
        "canonical_data": {
            "total_canonical_rows": len(canonical),
            "rfid_count": len(rfid_list),
            "dedup_rule": "drop exact duplicates, sort by [rfid_id, ts, source_ordinal], drop hourly dup keep first (min-source_ordinal)"
        },
        "behavior_metrics_summary": {
            "total_small_path_observations": int(canonical["is_small_path"].sum()),
            "overall_small_path_percentage": round(float(canonical["is_small_path"].mean() * 100.0), 2),
            "vessel_balanced_pct_small_path_mean": round(float(per_vessel_df["pct_small_path_obs"].mean()), 2),
            "vessel_balanced_pct_small_path_median": round(float(per_vessel_df["pct_small_path_obs"].median()), 2),
            "vessel_balanced_repeated_cell_occupancy_mean": round(float(per_vessel_df["repeated_cell_occupancy_ratio"].mean()), 4),
            "vessel_balanced_repeated_cell_occupancy_median": round(float(per_vessel_df["repeated_cell_occupancy_ratio"].median()), 4),
        },
        "unavailable_inputs": {
            "route_following": "unavailable (GPS points / geometry sequences missing in hourly score frame)",
            "within_part_straightness": "unavailable (GPS points / sub-hourly trajectories missing in hourly frame)",
            "official_harbor_boundaries": "unavailable (not supplied; repeated cells represent repeated 0.05-deg area occupancy only, never harbor)",
            "operational_behavior_labels": "unavailable (ground truth for anchoring, waiting, towing, hauling not present in dataset)"
        },
        "deterministic_cases": case_selection_summary
    }
    
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_obj, f, indent=2, ensure_ascii=False)
    print(f"Saved {summary_path}")
    print("\nExecution completed successfully!")

if __name__ == "__main__":
    main()
