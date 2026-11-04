#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only accident / hourly-centroid candidate linkage audit.

Run --self-test without external data. Production example (use a NEW output path):
  python audit_linkage.py --accidents ACCIDENTS.xlsx --train-cache-dir CACHE_DIR \
      --output-dir NEW_OUTPUT_DIR

Only selected columns of existing train caches are read. No model, project module,
raw WKT, scoring cache, or pickle is loaded. CSV outputs are UTF-8 with BOM.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import re
import sys
import time
from typing import Iterator

import numpy as np
import pandas as pd


SCRIPT_VERSION = "1.0.0"
EARTH_RADIUS_M = 6_371_000.0
HOUR_NS = 3_600_000_000_000
CONDITIONS = tuple((h, r) for h in (0, 1, 2) for r in (1000, 3000, 5000))
BASELINE = (1, 5000)
FORBIDDEN_OUTPUT_ROOT = Path(r"D:\repos\fishing-track-classification")
TRACK_COLUMNS = ("row_index", "part_dt", "rfid_id", "rfid_time", "cen_lon",
                 "cen_lat", "key_valid", "wkt_valid")
POOL_COLUMNS = ("event_id", "rfid_id", "source_filename", "source_row_index",
                "source_cache_row_index", "source_row_index_basis", "track_hour",
                "cen_lon", "cen_lat", "centroid_distance_m", "bucket_offset_hours",
                "track_hour_start_minus_accident_minutes", "interval_gap_minutes",
                "accident_within_track_hour_interval")
DUPLICATE_COLUMNS = ("event_id_a", "event_id_b", "duplicate_rule", "same_all_original_fields",
                     "same_exact_time_and_coordinates", "accident_time_gap_minutes",
                     "accident_coordinate_distance_m", "merged")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clock_record(value: datetime) -> dict:
    return {"utc": value.isoformat(),
            "kst": value.astimezone(timezone(timedelta(hours=9))).isoformat()}


def file_record(path: Path) -> dict:
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Input changed while hashing: {path.name}")
    return {"path": str(path), "filename": path.name, "size_bytes": after.st_size,
            "mtime_ns": after.st_mtime_ns, "sha256": digest.hexdigest()}


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return None if pd.isna(value) else value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def write_json(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(json_value(payload), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path: Path, table: pd.DataFrame) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        table.to_csv(stream, index=False, float_format="%.12g")


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    h = (np.sin((p2 - p1) / 2.0) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def valid_lonlat(lon, lat):
    return (np.isfinite(lon) & np.isfinite(lat)
            & (np.abs(lon) <= 180.0) & (np.abs(lat) <= 90.0))


def parse_event_time(value) -> pd.Timestamp:
    # Numeric Excel serial dates are deliberately not interpreted as Unix nanoseconds.
    if value is None or pd.isna(value) or isinstance(value, (int, float, np.number)):
        return pd.NaT
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed) or parsed.tzinfo is not None:
            return pd.NaT
        return pd.Timestamp(parsed)
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def prepare_events(raw: pd.DataFrame, source: Path, sheet: str, time_col: str,
                   lon_col: str, lat_col: str, vessel_count_col: str | None) -> pd.DataFrame:
    required = {time_col, lon_col, lat_col}
    if not required.issubset(raw.columns):
        raise ValueError(f"Missing accident columns: {sorted(required - set(raw.columns))}")
    if not raw.columns.is_unique:
        raise ValueError("Duplicate accident column names are not supported")
    events = pd.DataFrame(index=range(len(raw)))
    events["event_id"] = [f"E{i + 1:04d}" for i in range(len(raw))]
    events["source_filename"] = source.name
    events["source_sheet"] = sheet
    events["source_row_index"] = np.arange(len(raw), dtype=np.int64)
    events["source_excel_row_number"] = events["source_row_index"] + 2
    for column in raw.columns:
        events[f"accident_original__{column}"] = raw[column].map(json_value).to_numpy()
    events["accident_time"] = pd.to_datetime(raw[time_col].map(parse_event_time))
    events["accident_lon"] = pd.to_numeric(raw[lon_col], errors="coerce").to_numpy(dtype=float)
    events["accident_lat"] = pd.to_numeric(raw[lat_col], errors="coerce").to_numpy(dtype=float)
    good_time = events["accident_time"].notna().to_numpy()
    good_coordinates = valid_lonlat(events["accident_lon"].to_numpy(),
                                    events["accident_lat"].to_numpy())
    events["accident_time_valid"] = good_time
    events["accident_coordinates_valid"] = good_coordinates
    events["metadata_valid"] = good_time & good_coordinates
    events["metadata_issue"] = [";".join(s for s, bad in (
        ("invalid_or_timezone_aware_time", not t), ("invalid_lonlat", not c)) if bad)
        for t, c in zip(good_time, good_coordinates)]
    # Do not coerce NaT to an epoch-hour number (NaT has an int64 sentinel).
    hour_values = [int(t.value // HOUR_NS) if pd.notna(t) else pd.NA
                   for t in events["accident_time"]]
    events["accident_hour"] = pd.array(hour_values, dtype="Int64")
    events["accident_hour_start"] = events["accident_time"].dt.floor("h")
    if vessel_count_col and vessel_count_col not in raw.columns:
        raise ValueError(f"Missing requested vessel-count column: {vessel_count_col}")
    events["reported_accident_vessel_count"] = (
        pd.to_numeric(raw[vessel_count_col], errors="coerce").to_numpy(dtype=float)
        if vessel_count_col else np.nan)
    count = events["reported_accident_vessel_count"].to_numpy()
    events["reported_vessel_count_valid"] = np.isfinite(count) & (count >= 1) & (count == np.floor(count))
    events["association_is_confirmed_identity"] = False
    return events


def duplicate_events(raw: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    # Only exact provided metadata coincidences are flagged. No unapproved near-event threshold.
    original_keys = [json.dumps(json_value(row), ensure_ascii=False, sort_keys=True, default=str)
                     for row in raw.to_dict("records")]
    pairs = []
    for i in range(len(events)):
        a = events.iloc[i]
        for j in range(i + 1, len(events)):
            b = events.iloc[j]
            same_original = original_keys[i] == original_keys[j]
            comparable = bool(a["metadata_valid"] and b["metadata_valid"])
            same_time_space = comparable and (
                a["accident_time"] == b["accident_time"]
                and a["accident_lon"] == b["accident_lon"]
                and a["accident_lat"] == b["accident_lat"])
            if not (same_original or same_time_space):
                continue
            pairs.append({"event_id_a": a["event_id"], "event_id_b": b["event_id"],
                          "duplicate_rule": "exact_original_row_or_exact_time_coordinates",
                          "same_all_original_fields": same_original,
                          "same_exact_time_and_coordinates": same_time_space,
                          "accident_time_gap_minutes": (
                              abs((a["accident_time"] - b["accident_time"]).total_seconds()) / 60
                              if comparable else np.nan),
                          "accident_coordinate_distance_m": (
                              float(haversine_m(a["accident_lon"], a["accident_lat"],
                                                b["accident_lon"], b["accident_lat"]))
                              if comparable else np.nan), "merged": False})
    return pd.DataFrame(pairs, columns=DUPLICATE_COLUMNS)


def iter_cache_batches(path: Path, batch_size: int) -> Iterator[tuple[pd.DataFrame, int, str]]:
    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        parquet = pq.ParquetFile(path)
        missing = set(TRACK_COLUMNS) - set(parquet.schema_arrow.names)
        if missing:
            raise ValueError(f"Missing cache columns in {path.name}: {sorted(missing)}")
        offset = 0
        for batch in parquet.iter_batches(batch_size=batch_size, columns=list(TRACK_COLUMNS)):
            frame = batch.to_pandas()
            yield frame, offset, "cache_row_index_field_as_stored"
            offset += len(frame)
    elif path.suffix.lower() == ".npz":
        # No pickled objects. NPZ must carry validity flags and explicit source row indices.
        with np.load(path, allow_pickle=False) as archive:
            names = {c: ("rid" if c == "rfid_id" and c not in archive.files else c)
                     for c in TRACK_COLUMNS}
            missing = [c for c, actual in names.items() if actual not in archive.files]
            if missing:
                raise ValueError(f"Missing NPZ arrays in {path.name}: {missing}")
            arrays = {c: np.asarray(archive[actual]) for c, actual in names.items()}
            lengths = {len(a) for a in arrays.values() if a.ndim == 1}
            if len(lengths) != 1 or any(a.ndim != 1 for a in arrays.values()):
                raise ValueError(f"NPZ arrays must be one-dimensional with equal length: {path.name}")
            for start in range(0, next(iter(lengths)), batch_size):
                yield pd.DataFrame({k: a[start:start + batch_size] for k, a in arrays.items()}), start, "cache_row_index_field_as_stored"
    else:
        raise ValueError("Only .parquet or non-pickled .npz train caches are supported")


def normalize_track_batch(frame: pd.DataFrame, path: Path, offset: int, basis: str,
                          counters: Counter) -> pd.DataFrame:
    counters["raw_rows"] += len(frame)
    # Boolean validity flags must not use bool('False') semantics.
    for name in ("key_valid", "wkt_valid"):
        if not frame[name].dropna().isin([True, False, 0, 1]).all():
            raise ValueError(f"Non-boolean validity flags: {path.name} / {name}")
    key = frame["key_valid"].fillna(False).astype(bool).to_numpy()
    wkt = frame["wkt_valid"].fillna(False).astype(bool).to_numpy()
    counters["key_valid_rows"] += int(key.sum())
    counters["key_and_wkt_valid_rows"] += int((key & wkt).sum())
    data = frame.loc[key & wkt].copy()
    data["source_cache_row_index"] = np.arange(offset, offset + len(frame), dtype=np.int64)[key & wkt]
    numeric = {c: pd.to_numeric(data[c], errors="coerce")
               for c in ("rfid_id", "part_dt", "rfid_time", "row_index", "cen_lon", "cen_lat")}
    id_value = numeric["rfid_id"].to_numpy(dtype=float)
    date_value = numeric["part_dt"].to_numpy(dtype=float)
    hour_value = numeric["rfid_time"].to_numpy(dtype=float)
    source_value = numeric["row_index"].to_numpy(dtype=float)
    valid_numeric_id_date = (np.isfinite(id_value) & np.isfinite(date_value)
                             & (id_value == np.floor(id_value)) & (date_value == np.floor(date_value))
                             & (id_value >= 0) & (id_value < 2 ** 63))
    # Eight-digit calendar date and integral hour are mandatory; invalid values stay counted.
    dates = pd.to_datetime(numeric["part_dt"].astype("Int64").astype(str),
                           format="%Y%m%d", errors="coerce") if (
                               np.isfinite(date_value).all() and (date_value == np.floor(date_value)).all()) else pd.Series(
                                   [pd.to_datetime(str(int(x)), format="%Y%m%d", errors="coerce")
                                    if np.isfinite(x) and x == np.floor(x) else pd.NaT for x in date_value], index=data.index)
    valid_hour = np.isfinite(hour_value) & (hour_value == np.floor(hour_value)) & (hour_value >= 0) & (hour_value <= 23)
    valid_source = np.isfinite(source_value) & (source_value == np.floor(source_value)) & (source_value >= 0) & (source_value < 2 ** 63)
    coord = valid_lonlat(numeric["cen_lon"].to_numpy(dtype=float), numeric["cen_lat"].to_numpy(dtype=float))
    valid = valid_numeric_id_date & dates.notna().to_numpy() & valid_hour & valid_source & coord
    counters["invalid_id_or_date_numeric_rows"] += int((~valid_numeric_id_date).sum())
    counters["invalid_calendar_date_rows"] += int(dates.isna().sum())
    counters["invalid_hour_rows"] += int((~valid_hour).sum())
    counters["invalid_source_row_index_rows"] += int((~valid_source).sum())
    counters["invalid_centroid_rows"] += int((~coord).sum())
    counters["usable_rows"] += int(valid.sum())
    selected = data.loc[valid]
    selected_dates = dates.loc[valid]
    # Guard against accidental Test (2025) caches, even if their filename was renamed.
    in_scope = (selected_dates.dt.year == 2026) & selected_dates.dt.month.between(1, 6)
    if not in_scope.all():
        raise ValueError(f"Cache contains usable rows outside 2026-01..06: {path.name}")
    result = pd.DataFrame({
        "rfid_id": numeric["rfid_id"].loc[valid].to_numpy(dtype=np.int64),
        "source_filename": path.name,
        "source_row_index": numeric["row_index"].loc[valid].to_numpy(dtype=np.int64),
        "source_cache_row_index": selected["source_cache_row_index"].to_numpy(dtype=np.int64),
        "source_row_index_basis": basis,
        "track_hour": (selected_dates.astype("int64").to_numpy() // HOUR_NS
                       + numeric["rfid_time"].loc[valid].to_numpy(dtype=np.int64)),
        "cen_lon": numeric["cen_lon"].loc[valid].to_numpy(dtype=float),
        "cen_lat": numeric["cen_lat"].loc[valid].to_numpy(dtype=float)})
    return result.sort_values("track_hour", kind="stable").reset_index(drop=True)


def match_batch(events: pd.DataFrame, tracks: pd.DataFrame) -> list[pd.DataFrame]:
    pieces = []
    hours = tracks["track_hour"].to_numpy(dtype=np.int64)
    for event in events.loc[events["metadata_valid"]].itertuples(index=False):
        lo = np.searchsorted(hours, int(event.accident_hour) - 2, side="left")
        hi = np.searchsorted(hours, int(event.accident_hour) + 2, side="right")
        if lo == hi:
            continue
        nearby = tracks.iloc[lo:hi]
        distances = haversine_m(event.accident_lon, event.accident_lat,
                                nearby["cen_lon"].to_numpy(), nearby["cen_lat"].to_numpy())
        select = distances <= 5000.0
        if not select.any():
            continue
        chosen = nearby.loc[select].copy()
        chosen["event_id"] = event.event_id
        chosen["centroid_distance_m"] = distances[select]
        chosen["bucket_offset_hours"] = chosen["track_hour"] - int(event.accident_hour)
        event_minutes = event.accident_time.value / 60_000_000_000
        delta = chosen["track_hour"].to_numpy(dtype=float) * 60.0 - event_minutes
        chosen["track_hour_start_minus_accident_minutes"] = delta
        chosen["interval_gap_minutes"] = np.maximum(np.maximum(delta, -delta - 60.0), 0.0)
        chosen["accident_within_track_hour_interval"] = (delta <= 0) & (delta > -60)
        pieces.append(chosen.loc[:, list(POOL_COLUMNS)])
    return pieces


def hour_label(hour: int) -> str:
    return (pd.Timestamp("1970-01-01") + pd.Timedelta(hours=int(hour))).isoformat()


def row_details(row: pd.Series, prefix: str) -> dict:
    fields = ("source_filename", "source_row_index", "source_cache_row_index", "source_row_index_basis",
              "cen_lon", "cen_lat", "centroid_distance_m", "bucket_offset_hours",
              "track_hour_start_minus_accident_minutes", "interval_gap_minutes",
              "accident_within_track_hour_interval")
    result = {prefix + key: row[key] for key in fields}
    result[prefix + "track_hour_start"] = hour_label(row["track_hour"])
    result[prefix + "track_hour_end_exclusive"] = hour_label(row["track_hour"] + 1)
    return result


def candidate_columns() -> list[str]:
    base = ["event_id", "hour_bucket_radius", "spatial_radius_m", "is_baseline_condition",
            "rfid_id", "nearby_row_count", "unique_hour_count", "association_is_confirmed_identity",
            "track_registry_available", "vessel_type_tonnage_filter_applied"]
    sample = pd.Series({key: 0 for key in POOL_COLUMNS})
    return base + list(row_details(sample, "minimum_distance_row__")) + list(row_details(sample, "best_time_row__"))


def summarize(events: pd.DataFrame, pool: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_output = events.copy()
    candidates, summaries = [], []
    for radius_h, radius_m in CONDITIONS:
        selected = pool.loc[(pool["bucket_offset_hours"].abs() <= radius_h)
                            & (pool["centroid_distance_m"] <= radius_m)].copy()
        counts = selected.groupby("event_id")["rfid_id"].nunique()
        row_counts = selected.groupby("event_id").size()
        name = f"h{radius_h}_r{radius_m}m"
        event_output[name + "__candidate_vessel_count"] = event_output["event_id"].map(counts).fillna(0).astype(int)
        event_output[name + "__nearby_row_count"] = event_output["event_id"].map(row_counts).fillna(0).astype(int)
        statuses = []
        for valid, count in zip(event_output["metadata_valid"], event_output[name + "__candidate_vessel_count"]):
            statuses.append("invalid_metadata" if not valid else
                            "no_candidate" if count == 0 else "single_candidate" if count == 1 else "multiple_candidates")
        event_output[name + "__status"] = statuses
        status_counts = Counter(statuses)
        matched = int((counts > 0).sum())
        summaries.append({"hour_bucket_radius": radius_h, "spatial_radius_m": radius_m,
                          "is_baseline_condition": (radius_h, radius_m) == BASELINE,
                          "all_event_count": len(events), "valid_metadata_event_count": int(events["metadata_valid"].sum()),
                          "invalid_metadata_event_count": status_counts["invalid_metadata"],
                          "no_candidate_event_count": status_counts["no_candidate"],
                          "candidate_event_count": matched,
                          "single_candidate_event_count": status_counts["single_candidate"],
                          "multiple_candidate_event_count": status_counts["multiple_candidates"],
                          "candidate_event_vessel_association_count": int(counts.sum()),
                          "mean_candidate_vessels_per_candidate_event": float(counts.sum() / matched) if matched else np.nan,
                          "nearby_event_row_association_count": len(selected)})
        for (event_id, vessel_id), group in selected.groupby(["event_id", "rfid_id"], sort=True):
            stable = ["source_filename", "source_row_index", "source_cache_row_index"]
            minimum_distance = group.sort_values(["centroid_distance_m", "interval_gap_minutes"] + stable, kind="stable").iloc[0]
            group = group.assign(_abs_start_delta=group["track_hour_start_minus_accident_minutes"].abs())
            best_time = group.sort_values(["interval_gap_minutes", "_abs_start_delta", "centroid_distance_m"] + stable, kind="stable").iloc[0]
            record = {"event_id": event_id, "hour_bucket_radius": radius_h,
                      "spatial_radius_m": radius_m, "is_baseline_condition": (radius_h, radius_m) == BASELINE,
                      "rfid_id": int(vessel_id), "nearby_row_count": len(group),
                      "unique_hour_count": int(group["track_hour"].nunique()),
                      "association_is_confirmed_identity": False, "track_registry_available": False,
                      "vessel_type_tonnage_filter_applied": False}
            record.update(row_details(minimum_distance, "minimum_distance_row__"))
            record.update(row_details(best_time, "best_time_row__"))
            candidates.append(record)
    event_output["baseline_status"] = event_output["h1_r5000m__status"]
    event_output["baseline_candidate_vessel_count"] = event_output["h1_r5000m__candidate_vessel_count"]
    event_output["single_candidate_does_not_cover_reported_multi_vessel_event"] = (
        (event_output["baseline_candidate_vessel_count"] == 1)
        & event_output["reported_vessel_count_valid"]
        & (event_output["reported_accident_vessel_count"] > 1))
    event_output["candidate_count_below_reported_vessel_count"] = (
        event_output["reported_vessel_count_valid"]
        & (event_output["baseline_candidate_vessel_count"] < event_output["reported_accident_vessel_count"]))
    event_output["track_registry_available"] = False
    event_output["vessel_type_tonnage_filter_applied"] = False
    return event_output, pd.DataFrame(candidates, columns=candidate_columns()), pd.DataFrame(summaries)


def self_test() -> dict:
    """Synthetic behavioral checks, never a claim about real data or hardware."""
    raw = pd.DataFrame({"발생일시": ["2026-01-01 10:59:00", "bad", "2026-01-01 10:30:00"],
                        "경도(변환)": [0.0, 0.0, np.nan], "위도(변환)": [0.0, 0.0, 0.0],
                        "사고선박수": [2, 1, 1]})
    events = prepare_events(raw, Path("synthetic.xlsx"), "synthetic", "발생일시", "경도(변환)", "위도(변환)", "사고선박수")
    h10 = int(pd.Timestamp("2026-01-01 10:00").value // HOUR_NS)
    # Same vessel: spatially nearest row differs from independently best temporal row.
    tracks = pd.DataFrame({"rfid_id": [10, 10, 20, 30], "source_filename": ["synthetic_train.parquet"] * 4,
                           "source_row_index": [1, 2, 3, 4], "source_cache_row_index": [0, 1, 2, 3],
                           "source_row_index_basis": ["synthetic"] * 4,
                           "track_hour": [h10 - 1, h10, h10 + 1, h10 + 2],
                           "cen_lon": [0.0, 0.001, 0.002, 0.003], "cen_lat": [0.0] * 4})
    pool = pd.concat(match_batch(events, tracks), ignore_index=True)
    ev, cand, summary = summarize(events, pool)
    baseline = cand[cand["is_baseline_condition"]]
    ten = baseline[baseline["rfid_id"] == 10].iloc[0]
    assert len(events) == 3 and int(events["metadata_valid"].sum()) == 1
    assert ev.iloc[0]["baseline_status"] == "multiple_candidates"
    assert ev.iloc[1]["baseline_status"] == "invalid_metadata"
    assert ev.iloc[2]["baseline_status"] == "invalid_metadata"
    assert set(baseline["rfid_id"]) == {10, 20}
    assert ten["minimum_distance_row__source_row_index"] == 1
    assert ten["best_time_row__source_row_index"] == 2
    assert ten["minimum_distance_row__track_hour_start_minus_accident_minutes"] == -119.0
    assert ten["minimum_distance_row__interval_gap_minutes"] == 59.0
    assert ten["nearby_row_count"] == 2 and ten["unique_hour_count"] == 2
    assert bool(ten["best_time_row__accident_within_track_hour_interval"])
    # Exactly 5000 is included without rounding; infinitesimally larger is excluded.
    boundary = pool.iloc[[0, 0]].copy()
    boundary["rfid_id"] = [40, 50]
    boundary["centroid_distance_m"] = [5000.0, np.nextafter(5000.0, np.inf)]
    _, boundary_candidates, _ = summarize(events, boundary)
    assert set(boundary_candidates.loc[boundary_candidates["is_baseline_condition"], "rfid_id"]) == {40}
    lon5000 = np.degrees(5000.0 / EARTH_RADIUS_M)
    assert abs(float(haversine_m(0, 0, lon5000, 0)) - 5000.0) < 1e-8
    assert not bool(valid_lonlat(np.nan, 0)) and not bool(valid_lonlat(181, 0))
    only_one = pool[pool["rfid_id"] == 10]
    one_events, _, _ = summarize(events, only_one)
    assert bool(one_events.iloc[0]["single_candidate_does_not_cover_reported_multi_vessel_event"])
    repeated_raw = pd.concat([raw.iloc[[0]], raw.iloc[[0]]], ignore_index=True)
    repeated_events = prepare_events(repeated_raw, Path("synthetic.xlsx"), "synthetic", "발생일시", "경도(변환)", "위도(변환)", "사고선박수")
    assert len(duplicate_events(repeated_raw, repeated_events)) == 1
    assert len(summary) == 9 and len(ev) == len(raw)
    no_events, no_cand, no_summary = summarize(events, pd.DataFrame(columns=POOL_COLUMNS))
    assert no_cand.empty and len(no_summary) == 9 and no_events.iloc[0]["baseline_status"] == "no_candidate"
    endpoint_raw = raw.iloc[[0]].copy()
    endpoint_raw["발생일시"] = "2026-01-01 11:00:00"
    endpoint_events = prepare_events(endpoint_raw, Path("synthetic.xlsx"), "synthetic", "발생일시", "경도(변환)", "위도(변환)", "사고선박수")
    endpoint_pool = pd.concat(match_batch(endpoint_events, tracks), ignore_index=True)
    ended_hour = endpoint_pool[endpoint_pool["track_hour"] == h10].iloc[0]
    assert ended_hour["interval_gap_minutes"] == 0.0
    assert not bool(ended_hour["accident_within_track_hour_interval"])
    malformed = pd.DataFrame({"row_index": range(7), "part_dt": ["20260101"] * 3 + ["not_date"] + ["20260101"] * 3,
                              "rfid_id": ["1", "2", "3", "4", "5", "6", "bad"],
                              "rfid_time": [10, 10, 10, 10, 10, 24, 10],
                              "cen_lon": [0.0, 0.0, 0.0, 0.0, np.nan, 0.0, 0.0],
                              "cen_lat": [0.0] * 7, "key_valid": [True, False, True, True, True, True, True],
                              "wkt_valid": [True, True, False, True, True, True, True]})
    validation_counts = Counter()
    normalized = normalize_track_batch(malformed, Path("synthetic_train.parquet"), 100, "synthetic", validation_counts)
    assert len(normalized) == 1 and normalized.iloc[0]["source_cache_row_index"] == 100
    assert validation_counts["raw_rows"] == 7 and validation_counts["key_and_wkt_valid_rows"] == 5
    assert validation_counts["invalid_calendar_date_rows"] == 1
    assert validation_counts["invalid_centroid_rows"] == 1 and validation_counts["invalid_hour_rows"] == 1
    return {"result": "passed", "verification_type": "synthetic_code_self_test",
            "checks": ["floor_bucket_is_not_absolute_60_minutes", "hour_interval_and_signed_residual",
                       "half_open_hour_interval", "inclusive_5000m_boundary", "haversine_units_m",
                       "multiple_candidates_preserved", "independent_distance_and_time_rows",
                       "NaT_and_NaN_preserved", "multi_vessel_single_candidate_flag",
                       "duplicate_rows_flagged_not_merged", "nine_conditions", "empty_candidates",
                       "batch_validity_flags_and_invalid_id_date_hour_centroid"]}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--accidents", type=Path)
    sources = p.add_mutually_exclusive_group()
    sources.add_argument("--train-cache-dir", type=Path)
    sources.add_argument("--train-cache", type=Path, action="append", help="Repeat for explicit train-only files")
    p.add_argument("--output-dir", type=Path, help="Must not already exist")
    p.add_argument("--sheet", default="0", help="Excel sheet name or zero-based integer index")
    p.add_argument("--time-column", default="발생일시")
    p.add_argument("--lon-column", default="경도(변환)")
    p.add_argument("--lat-column", default="위도(변환)")
    p.add_argument("--vessel-count-column", help="Exact column; if omitted, detect 사고선박수 / 사고선박 수 / 선박수")
    p.add_argument("--batch-size", type=int, default=131072)
    p.add_argument("--expected-events", type=int, default=167)
    p.add_argument("--expected-candidate-events", type=int, default=118)
    p.add_argument("--expected-single-events", type=int, default=30)
    p.add_argument("--expected-raw-track-rows", type=int, default=3887069)
    p.add_argument("--expected-valid-track-rows", type=int, default=3887065)
    return p


def resolve_inputs(args) -> tuple[Path, list[Path], Path]:
    if not args.accidents or not args.output_dir or not (args.train_cache_dir or args.train_cache):
        raise ValueError("Production requires --accidents, train-cache input, and --output-dir")
    accident_path = args.accidents.resolve(strict=True)
    if accident_path.suffix.lower() != ".xlsx":
        raise ValueError("Accident source must be .xlsx")
    if args.train_cache_dir:
        directory = args.train_cache_dir.resolve(strict=True)
        files = [directory / f"rows_train_{month}.parquet" for month in range(1, 7)]
    else:
        files = args.train_cache
    files = [p.resolve(strict=True) for p in files]
    if len(set(files)) != len(files):
        raise ValueError("Duplicate train-cache input path")
    for path in files:
        if not path.is_file() or path.suffix.lower() not in (".parquet", ".npz") or "train" not in path.stem.lower():
            raise ValueError(f"Expected explicitly named train Parquet/NPZ cache: {path.name}")
    output = args.output_dir.resolve()
    if output == FORBIDDEN_OUTPUT_ROOT or FORBIDDEN_OUTPUT_ROOT in output.parents:
        raise ValueError("Canonical repository is read-only for this audit")
    if output.exists():
        raise FileExistsError("Output directory already exists; choose a new directory")
    if any(output == p or output in p.parents for p in [accident_path, *files, Path(__file__).resolve()]):
        raise ValueError("Output directory must not contain an input or the running script")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    return accident_path, files, output


def run(args, argv: list[str]) -> int:
    started, timer = utc_now(), time.perf_counter()
    accident_path, paths, output = resolve_inputs(args)
    output.mkdir(parents=True, exist_ok=False)
    input_paths = [accident_path, *paths]
    pre = [file_record(p) for p in input_paths]
    script_pre = file_record(Path(__file__).resolve())
    manifest = {"schema_version": SCRIPT_VERSION, "status": "running", "started": clock_record(started),
                "command_argv": [sys.executable, str(Path(__file__).resolve()), *argv],
                "input_pre": pre, "script_pre": script_pre,
                "environment": {"python": sys.version, "executable": sys.executable,
                                "platform": platform.platform(),
                                "packages": {name: importlib.metadata.version(name)
                                             for name in ("numpy", "pandas", "pyarrow", "openpyxl")}},
                "execution_role": {"requested_role": "sol_module", "requested_model": "GPT-6.1 Sol",
                                   "requested_effort": "xhigh", "runtime_model_is_not_introspected": True},
                "contract": {
                    "candidate_rules": [{"hour_bucket_radius": h, "spatial_radius_m": r} for h, r in CONDITIONS],
                    "baseline_rule": "abs(track_hour - floor(accident_time, hour)) <= 1 and centroid_distance_m <= 5000",
                    "time_rule_is_not_absolute_minutes": True,
                    "track_time_semantics": "Hourly interval [hour_start, hour_start + 1h); no per-point timestamps",
                    "time_alignment_assumption": "Naive input wall clocks are compared unchanged; source timezone not independently verified",
                    "signed_residual": "track_hour_start_minus_accident_minutes = track hour start minus exact accident time",
                    "interval_gap": "max(start - event, event - end, 0) in minutes; at exclusive end gap=0 but inside=False",
                    "best_time_rule": "minimum interval_gap, then absolute hour-start residual, distance, source filename, row index, cache index",
                    "minimum_distance_rule": "minimum distance, then interval gap, source filename, row index, cache index",
                    "distance": "Haversine distance from event coordinate to cached centroid proxy, not nearest route point",
                    "earth_radius_m": EARTH_RADIUS_M, "spatial_boundary": "inclusive without pre-comparison rounding",
                    "filter": "key_valid and wkt_valid, numeric integral ID/date/hour/source index, valid calendar date and lonlat",
                    "train_scope": "2026 January through June; usable rows outside scope reject run",
                    "source_row_index": "row_index field copied as stored, not assumed to be an Excel or CSV line number",
                    "source_cache_row_index": "zero-based physical record position within cache file",
                    "accident_source_row_index": "zero-based data row; Excel row assumes first-row header, no skiprows",
                    "duplicate_rule": "exact original row or exact parsed timestamp and coordinates; flag pairs without merging",
                    "vessel_identity": "Candidate RFID associations only; no vessel registry; type and tonnage are not used to filter",
                    "labels": "No confirmed accident identity, cause label, accident-positive label, or negative label created",
                    "reference_counts_are_conditional_linkage_metrics": True,
                    "accident_training_suitability": "Unresolved; source filename says test data; no training performed",
                    "raw_geometry_loaded": False, "project_modules_imported": False}}
    counters, pieces = Counter(), []
    try:
        with pd.ExcelFile(accident_path) as excel:
            selected_sheet = int(args.sheet) if re.fullmatch(r"\d+", args.sheet) else args.sheet
            sheet_name = excel.sheet_names[selected_sheet] if isinstance(selected_sheet, int) else selected_sheet
            raw = pd.read_excel(excel, sheet_name=sheet_name, dtype=object)
        vessel_col = args.vessel_count_column
        if not vessel_col:
            vessel_col = next((c for c in ("사고선박수", "사고선박 수", "선박수") if c in raw.columns), None)
        manifest["accident_schema"] = {"sheet": sheet_name, "columns": list(raw.columns),
                                       "vessel_count_column": vessel_col}
        events = prepare_events(raw, accident_path, sheet_name, args.time_column, args.lon_column, args.lat_column, vessel_col)
        duplicates = duplicate_events(raw, events)
        for file_no, path in enumerate(paths, start=1):
            for frame, offset, basis in iter_cache_batches(path, args.batch_size):
                tracks = normalize_track_batch(frame, path, offset, basis, counters)
                pieces.extend(match_batch(events, tracks))
            print(f"Read train cache {file_no}/{len(paths)}; raw rows={counters['raw_rows']:,}; usable={counters['usable_rows']:,}", flush=True)
        pool = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=POOL_COLUMNS)
        event_output, candidate_output, sensitivity = summarize(events, pool)
        duplicate_ids = set(duplicates["event_id_a"]) | set(duplicates["event_id_b"])
        event_output["possible_duplicate_event_metadata"] = event_output["event_id"].isin(duplicate_ids)
        baseline = sensitivity.loc[sensitivity["is_baseline_condition"]].iloc[0]
        checks = {
            "event_count": {"expected": args.expected_events, "actual": len(events)},
            "candidate_event_count": {"expected": args.expected_candidate_events, "actual": int(baseline["candidate_event_count"])},
            "single_candidate_event_count": {"expected": args.expected_single_events, "actual": int(baseline["single_candidate_event_count"])},
            "raw_track_rows": {"expected": args.expected_raw_track_rows, "actual": counters["raw_rows"]},
            "valid_track_rows": {"expected": args.expected_valid_track_rows, "actual": counters["usable_rows"]}}
        for check in checks.values():
            check["matches"] = check["actual"] == check["expected"]
        replicated = all(c["matches"] for c in checks.values())
        summary = {"schema_version": SCRIPT_VERSION, "verification_type": "real_data_candidate_linkage_audit",
                   "baseline_reproduced": replicated, "baseline_checks": checks,
                   "track_validation": dict(counters), "baseline": baseline.to_dict(),
                   "possible_duplicate_pair_count": len(duplicates),
                   "single_candidate_multi_vessel_incomplete_event_count": int(event_output["single_candidate_does_not_cover_reported_multi_vessel_event"].sum()),
                   "metadata_invalid_event_count": int((~events["metadata_valid"]).sum()),
                   "sensitivity": sensitivity.to_dict("records"),
                   "interpretation": "Candidate association counts and linkage residuals; not accident detection accuracy or confirmed vessel identity"}
        write_csv(output / "event_audit.csv", event_output)
        write_csv(output / "candidate_vessels.csv", candidate_output)
        write_csv(output / "sensitivity_summary.csv", sensitivity)
        write_csv(output / "possible_duplicate_events.csv", duplicates)
        write_json(output / "summary.json", summary)
        manifest["baseline_checks"] = checks
        manifest["track_validation"] = dict(counters)
        manifest["status"] = "completed" if replicated else "completed_with_reference_count_mismatch"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        post = [file_record(p) for p in input_paths]
        script_post = file_record(Path(__file__).resolve())
        unchanged = all(a == b for a, b in zip(pre, post)) and script_pre == script_post
        manifest["input_post"] = post
        manifest["script_post"] = script_post
        manifest["input_and_script_unchanged"] = unchanged
        if not unchanged:
            manifest["status"] = "failed_input_or_script_changed"
        manifest["finished"] = clock_record(utc_now())
        manifest["elapsed_seconds"] = time.perf_counter() - timer
        manifest["outputs"] = [file_record(p) for p in sorted(output.iterdir()) if p.is_file()]
        write_json(output / "manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "baseline_reproduced": replicated,
                      "input_and_script_unchanged": unchanged, "event_count": len(events),
                      "candidate_event_count": int(baseline["candidate_event_count"]),
                      "single_candidate_event_count": int(baseline["single_candidate_event_count"]),
                      "elapsed_seconds": round(manifest["elapsed_seconds"], 3)}, ensure_ascii=False), flush=True)
    return 0 if replicated and unchanged else 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parser().parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False))
        return 0
    return run(args, argv)


if __name__ == "__main__":
    raise SystemExit(main())
