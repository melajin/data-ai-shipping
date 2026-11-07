"""Extract low-memory vessel-day segment features from s3_hourly.parquet."""
from __future__ import annotations

import datetime as dt
import gc
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from resource_check import record_resource_check

TRACK_DIR = Path(__file__).resolve().parent
NPZ_FOLD0 = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_0_features.npz")
PARQUET_HOURLY = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\26_11_2\work\재식별_투트랙_001r1\s3_hourly.parquet")
OUTPUT_PARQUET = TRACK_DIR / "vessel_day_segments.parquet"
OUTPUT_SUMMARY = TRACK_DIR / "segments_summary.json"


def extract_daily_segments() -> pd.DataFrame:
    record_resource_check("extract_segments_start", expected_peak_mb=350.0)
    t0 = time.time()
    
    # 1. Load dev roster
    data0 = np.load(NPZ_FOLD0)
    rfid_ids = data0["rfid_ids"].astype(str)
    y_labels = data0["y"].astype(np.int8)
    dev_ids_int = rfid_ids.astype(np.int64)
    dev_ids_set = set(dev_ids_int)
    id_to_y = dict(zip(dev_ids_int, y_labels))
    del data0
    gc.collect()
    
    print(f"Loaded {len(dev_ids_set)} dev vessels. Scanning {PARQUET_HOURLY}...")
    
    # 2. Stream/load only 2026 and dev vessels with numeric columns
    cols = ["id", "date", "hour", "cen_lon", "cen_lat", "stationary", "gap_hours", "n_points"]
    dataset = ds.dataset(PARQUET_HOURLY, format="parquet")
    scanner = dataset.scanner(
        filter=(ds.field("year") == 2026) & (ds.field("id").isin(dev_ids_set)),
        columns=cols,
    )
    tbl = scanner.to_table()
    df = tbl.to_pandas().dropna(subset=["cen_lon", "cen_lat"]).reset_index(drop=True)
    del tbl
    gc.collect()
    
    print(f"Read {len(df)} hourly rows in {time.time()-t0:.2f}s. Downcasting types...")
    
    # 3. Downcast types to save RAM
    df["id"] = df["id"].astype(np.int32)
    df["hour"] = df["hour"].astype(np.int8)
    df["cen_lon"] = df["cen_lon"].astype(np.float32)
    df["cen_lat"] = df["cen_lat"].astype(np.float32)
    df["stationary"] = df["stationary"].fillna(0).astype(np.int8)
    df["gap_hours"] = df["gap_hours"].fillna(0).astype(np.float32)
    df["n_points"] = df["n_points"].fillna(0).astype(np.int32)
    
    # 4. Integer spatial codes
    lon100 = np.floor(df["cen_lon"] * 100).astype(np.int32)
    lat100 = np.floor(df["cen_lat"] * 100).astype(np.int32)
    df["cell_001_code"] = lon100 * 10000 + lat100

    lon20 = np.floor(df["cen_lon"] * 20).astype(np.int32)
    lat20 = np.floor(df["cen_lat"] * 20).astype(np.int32)
    df["cell_005_code"] = lon20 * 10000 + lat20
    del lon100, lat100, lon20, lat20
    gc.collect()

    # 5. Compute homeport per vessel
    stat_mask = df["stationary"] == 1
    if stat_mask.any():
        stat_modes = df[stat_mask].groupby(["id", "cell_001_code"]).size().reset_index(name="n")
        stat_modes = stat_modes.sort_values(["id", "n"], ascending=[True, False]).drop_duplicates(subset=["id"])
    else:
        stat_modes = pd.DataFrame(columns=["id", "cell_001_code"])

    all_modes = df.groupby(["id", "cell_001_code"]).size().reset_index(name="n")
    all_modes = all_modes.sort_values(["id", "n"], ascending=[True, False]).drop_duplicates(subset=["id"])

    home_cell = pd.concat([stat_modes, all_modes]).drop_duplicates(subset=["id"], keep="first")
    del stat_modes, all_modes

    home_coords = (
        df.merge(home_cell[["id", "cell_001_code"]], on=["id", "cell_001_code"])
        .groupby("id")[["cen_lon", "cen_lat"]]
        .mean()
        .rename(columns={"cen_lon": "home_lon", "cen_lat": "home_lat"})
    )
    df = df.merge(home_coords, on="id", how="left")
    del home_cell, home_coords
    gc.collect()

    # 6. Sort for step distance within day
    df = df.sort_values(["id", "date", "hour"]).reset_index(drop=True)

    same_day = (df["id"] == df["id"].shift(1)) & (df["date"] == df["date"].shift(1))
    dx = (df["cen_lon"] - df["cen_lon"].shift(1)) * 88.0
    dy = (df["cen_lat"] - df["cen_lat"].shift(1)) * 111.0
    df["step_dist"] = np.where(same_day, np.sqrt(dx**2 + dy**2), 0.0).astype(np.float32)

    dx_h = (df["cen_lon"] - df["home_lon"]) * 88.0
    dy_h = (df["cen_lat"] - df["home_lat"]) * 111.0
    df["dist_home"] = np.sqrt(dx_h**2 + dy_h**2).astype(np.float32)

    rad = df["hour"] * (2.0 * np.pi / 24.0)
    df["sin_hour"] = np.sin(rad).astype(np.float32)
    df["cos_hour"] = np.cos(rad).astype(np.float32)

    df["is_night"] = (df["hour"] < 6).astype(np.float32)
    df["is_morning"] = ((df["hour"] >= 6) & (df["hour"] < 12)).astype(np.float32)
    df["is_afternoon"] = ((df["hour"] >= 12) & (df["hour"] < 18)).astype(np.float32)
    df["is_evening"] = (df["hour"] >= 18).astype(np.float32)

    print("Computing dominant cell_005 and top cell ratio...")
    # Dominant cell_005 per (id, date)
    c005_counts = df.groupby(["id", "date", "cell_005_code"]).size().reset_index(name="n")
    c005_mode = (
        c005_counts.sort_values(["id", "date", "n"], ascending=[True, True, False])
        .drop_duplicates(subset=["id", "date"])[["id", "date", "cell_005_code"]]
        .rename(columns={"cell_005_code": "dom_cell_005"})
    )
    del c005_counts
    gc.collect()

    # Top cell_001 count
    c001_counts = df.groupby(["id", "date", "cell_001_code"]).size().reset_index(name="n")
    c001_max = (
        c001_counts.groupby(["id", "date"])["n"]
        .max()
        .reset_index(name="top_cell_cnt")
    )
    del c001_counts
    gc.collect()

    print("Aggregating daily segment features...")
    g = df.groupby(["id", "date"])
    agg_df = g.agg(
        n_active_hours=("hour", "count"),
        sum_n_points=("n_points", "sum"),
        stationary_ratio=("stationary", "mean"),
        max_gap_hours=("gap_hours", "max"),
        ratio_night=("is_night", "mean"),
        ratio_morning=("is_morning", "mean"),
        ratio_afternoon=("is_afternoon", "mean"),
        ratio_evening=("is_evening", "mean"),
        mean_sin_hour=("sin_hour", "mean"),
        mean_cos_hour=("cos_hour", "mean"),
        mean_lon=("cen_lon", "mean"),
        mean_lat=("cen_lat", "mean"),
        min_lon=("cen_lon", "min"),
        max_lon=("cen_lon", "max"),
        min_lat=("cen_lat", "min"),
        max_lat=("cen_lat", "max"),
        daily_dist_sum_km=("step_dist", "sum"),
        daily_dist_mean_km=("step_dist", "mean"),
        daily_dist_max_km=("step_dist", "max"),
        dist_from_home_mean_km=("dist_home", "mean"),
        dist_from_home_max_km=("dist_home", "max"),
        n_unique_cells_001=("cell_001_code", "nunique"),
    ).reset_index()

    del df
    gc.collect()

    # Merge top cell cnt and dominant cell_005
    agg_df = agg_df.merge(c001_max, on=["id", "date"], how="left")
    agg_df = agg_df.merge(c005_mode, on=["id", "date"], how="left")
    del c001_max, c005_mode
    gc.collect()

    # Derived columns
    span_lon = agg_df["max_lon"] - agg_df["min_lon"]
    span_lat = agg_df["max_lat"] - agg_df["min_lat"]
    agg_df["span_lon"] = span_lon.astype(np.float32)
    agg_df["span_lat"] = span_lat.astype(np.float32)
    agg_df["bbox_diag_km"] = np.sqrt((span_lat * 111.0)**2 + (span_lon * 88.0)**2).astype(np.float32)
    agg_df["top_cell_ratio"] = (agg_df["top_cell_cnt"] / agg_df["n_active_hours"]).astype(np.float32)
    agg_df["month"] = agg_df["date"].dt.month.astype(np.int8)

    # Clean intermediate min/max columns
    agg_df.drop(columns=["min_lon", "max_lon", "min_lat", "max_lat", "top_cell_cnt"], inplace=True)

    # Attach vessel weak label
    agg_df["y_vessel"] = agg_df["id"].map(id_to_y).astype(np.int8)

    # Downcast floats to float32
    float_cols = agg_df.select_dtypes(include=["float64"]).columns
    for c in float_cols:
        agg_df[c] = agg_df[c].astype(np.float32)
    int_cols = ["n_active_hours", "sum_n_points", "n_unique_cells_001", "dom_cell_005"]
    for c in int_cols:
        agg_df[c] = agg_df[c].astype(np.int32)

    # Save to parquet
    print(f"Writing {len(agg_df)} segment rows to {OUTPUT_PARQUET}...")
    agg_df.to_parquet(OUTPUT_PARQUET, index=False, engine="pyarrow", compression="snappy")
    
    elapsed = time.time() - t0
    summary = {
        "status": "success",
        "elapsed_seconds": round(elapsed, 2),
        "total_segments": int(len(agg_df)),
        "unique_vessels": int(agg_df["id"].nunique()),
        "columns": list(agg_df.columns),
        "class_distribution_segments": {int(k): int(v) for k, v in agg_df["y_vessel"].value_counts().items()},
        "avg_segments_per_vessel": round(len(agg_df) / agg_df["id"].nunique(), 2),
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Extraction complete in {elapsed:.2f}s. Summary:")
    print(json.dumps(summary, indent=2))
    
    record_resource_check("extract_segments_complete", expected_peak_mb=100.0)
    return agg_df


if __name__ == "__main__":
    extract_daily_segments()
