"""Round 10 past-centroid nearest-distance and peer-history availability probe."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_000.0
WINDOW_HOURS = 720
MIN_HISTORY_ROWS = 24
MIN_HISTORY_DATES = 3
MIN_OTHER_PEERS = 5
INPUT_COLUMNS = ["rfid_id", "ts", "source_ordinal", "cen_lon", "cen_lat"]
REGISTRY_COLUMNS = ["rfid_id", "primary_gear", "is_single_code"]
LEDGER_COLUMNS = [
    "rfid_id", "ts", "source_ordinal", "cen_lon", "cen_lat",
    "primary_gear", "is_single_code", "coordinate_valid", "own_ref_n",
    "own_ref_dates", "own_distance_eligible", "nearest_distance_m",
    "nearest_source_ordinal", "nearest_ts", "nearest_cen_lon",
    "nearest_cen_lat", "peer_eligible_n", "peer_eligible", "own_status",
    "own_reason", "peer_status", "peer_reason",
]
VESSEL_COLUMNS = [
    "rfid_id", "primary_gear", "observed_n", "valid_position_n",
    "own_eligible_n", "peer_eligible_n",
]


def _single_code(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _validate_keys(frame: pd.DataFrame, registry: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame) or not isinstance(registry, pd.DataFrame):
        raise TypeError("frame and registry must be pandas DataFrames")
    forbidden = [c for c in frame.columns if any(term in str(c).lower()
                 for term in ("event", "accident", "acc_id", "label", "positive", "incident"))]
    if forbidden:
        raise ValueError(f"event/label-like columns are forbidden: {forbidden}")
    missing = sorted(set(INPUT_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"frame missing required columns: {missing}")
    missing_registry = sorted(set(REGISTRY_COLUMNS) - set(registry.columns))
    if missing_registry:
        raise ValueError(f"registry missing required columns: {missing_registry}")
    if frame["rfid_id"].isna().any() or frame["ts"].isna().any() or frame["source_ordinal"].isna().any():
        raise ValueError("RFID, source-clock hour, and ordinal must be non-null")
    if not pd.api.types.is_integer_dtype(frame["ts"].dtype):
        raise ValueError("ts must be finite integer source-clock epoch hours before casting")
    if not pd.api.types.is_integer_dtype(frame["source_ordinal"].dtype):
        raise ValueError("source_ordinal must be finite integer values before casting")
    int64_min, int64_max = np.iinfo(np.int64).min, np.iinfo(np.int64).max
    for name in ("ts", "source_ordinal"):
        if len(frame) and (int(frame[name].min()) < int64_min or int(frame[name].max()) > int64_max):
            raise ValueError(f"{name} is outside int64 range")
    if frame["rfid_id"].astype(str).str.strip().eq("").any():
        raise ValueError("RFID cannot be empty")
    if registry["rfid_id"].isna().any() or registry["rfid_id"].astype(str).str.strip().eq("").any():
        raise ValueError("registry RFID must be non-null and non-empty")
    if registry["rfid_id"].astype(str).duplicated().any():
        raise ValueError("registry RFID must be unique")
    raw_ids = frame["rfid_id"].astype(str)
    if pd.DataFrame({"rfid_id": raw_ids, "ts": frame["ts"],
                     "source_ordinal": frame["source_ordinal"]}).duplicated().any():
        raise ValueError("(rfid_id, ts, source_ordinal) keys must be unique")


def _history_stats(past_ts: np.ndarray, query_ts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return bounded [t-720,t) row/date counts and eligibility for query hours."""
    left = np.searchsorted(past_ts, query_ts - WINDOW_HOURS, side="left")
    right = np.searchsorted(past_ts, query_ts, side="left")
    row_n = right - left
    date_codes = past_ts // 24
    date_starts = np.r_[0, np.flatnonzero(date_codes[1:] != date_codes[:-1]) + 1].astype(np.int64)
    # Count date-run starts strictly inside (left,right), plus the first date.
    date_n = np.zeros(len(query_ts), dtype=np.int64)
    has_rows = right > left
    date_n[has_rows] = 1 + (
        np.searchsorted(date_starts, right[has_rows], side="left")
        - np.searchsorted(date_starts, left[has_rows], side="right")
    )
    eligible = (row_n >= MIN_HISTORY_ROWS) & (date_n >= MIN_HISTORY_DATES)
    return left, right, row_n, np.column_stack((date_n, eligible.astype(np.int64)))


def _haversine_many(lon0: float, lat0: float, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon0r, lat0r = np.radians(lon0), np.radians(lat0)
    lonr, latr = np.radians(lon), np.radians(lat)
    dlon, dlat = lonr - lon0r, latr - lat0r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat0r) * np.cos(latr) * np.sin(dlon / 2.0) ** 2
    np.clip(a, 0.0, 1.0, out=a)
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def build_position_probe(frame: pd.DataFrame, registry: pd.DataFrame) -> dict[str, Any]:
    """Return all-row nearest past-centroid ledger and vessel/global counts.

    Histories use valid finite/range-checked coordinates in ``[t-720,t)``.
    Distances are centroid proxies only, not vessel routes, travel range, or
    operational status.
    """
    _validate_keys(frame, registry)
    ledger = frame[INPUT_COLUMNS].copy(deep=True).reset_index(drop=True)
    ledger["rfid_id"] = ledger["rfid_id"].astype(str)
    ledger["ts"] = ledger["ts"].astype("int64")
    ledger["source_ordinal"] = ledger["source_ordinal"].astype("int64")
    lon = pd.to_numeric(ledger["cen_lon"], errors="coerce").to_numpy(dtype=np.float64)
    lat = pd.to_numeric(ledger["cen_lat"], errors="coerce").to_numpy(dtype=np.float64)
    coordinate_valid = (np.isfinite(lon) & np.isfinite(lat) & (lon >= -180.0) & (lon <= 180.0)
                        & (lat >= -90.0) & (lat <= 90.0))
    ledger["cen_lon"] = lon
    ledger["cen_lat"] = lat
    ledger["coordinate_valid"] = coordinate_valid

    registry_view = registry[REGISTRY_COLUMNS].copy()
    registry_view["rfid_id"] = registry_view["rfid_id"].astype(str)
    gear_map: dict[str, tuple[str | None, bool]] = {}
    for row in registry_view.itertuples(index=False):
        gear = None if pd.isna(row.primary_gear) or str(row.primary_gear).strip() == "" else str(row.primary_gear)
        gear_map[str(row.rfid_id)] = (gear, bool(gear is not None and _single_code(row.is_single_code)))
    ledger["primary_gear"] = [gear_map.get(rid, (None, False))[0] for rid in ledger["rfid_id"]]
    ledger["is_single_code"] = [gear_map.get(rid, (None, False))[1] for rid in ledger["rfid_id"]]

    n = len(ledger)
    query_ts = np.sort(ledger["ts"].unique().astype(np.int64))
    row_query_idx = np.searchsorted(query_ts, ledger["ts"].to_numpy(dtype=np.int64))
    row_groups: dict[str, np.ndarray] = {
        str(rid): np.asarray(indices, dtype=np.int64)
        for rid, indices in ledger.groupby("rfid_id", sort=False).indices.items()
    }
    history_by_rid: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    eligible_by_rid: dict[str, np.ndarray] = {}
    raw_history_by_rid: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for rid, row_idx in row_groups.items():
        order = np.lexsort((ledger.loc[row_idx, "source_ordinal"].to_numpy(dtype=np.int64),
                            ledger.loc[row_idx, "ts"].to_numpy(dtype=np.int64)))
        sorted_rows = row_idx[order]
        valid_rows = sorted_rows[coordinate_valid[sorted_rows]]
        past_ts = ledger.loc[valid_rows, "ts"].to_numpy(dtype=np.int64)
        past_ord = ledger.loc[valid_rows, "source_ordinal"].to_numpy(dtype=np.int64)
        past_lon = lon[valid_rows]
        past_lat = lat[valid_rows]
        left, right, row_n, date_and_eligible = _history_stats(past_ts, query_ts)
        date_n = date_and_eligible[:, 0]
        eligible = date_and_eligible[:, 1].astype(bool)
        history_by_rid[rid] = (past_ts, past_ord, past_lon, past_lat, np.column_stack((left, right)))
        eligible_by_rid[rid] = eligible
        raw_history_by_rid[rid] = (row_n, date_n)

    gear_members: dict[str, list[str]] = defaultdict(list)
    for rid, (gear, single) in gear_map.items():
        if single and gear is not None:
            gear_members[gear].append(rid)
    eligible_count_by_gear: dict[str, np.ndarray] = {}
    for gear, members in gear_members.items():
        counts = np.zeros(len(query_ts), dtype=np.int64)
        for rid in members:
            eligible = eligible_by_rid.get(rid)
            if eligible is not None:
                counts += eligible.astype(np.int64)
        eligible_count_by_gear[gear] = counts

    own_ref_n = np.zeros(n, dtype=np.int64)
    own_ref_dates = np.zeros(n, dtype=np.int64)
    own_distance_eligible = np.zeros(n, dtype=bool)
    nearest_distance = np.full(n, np.nan, dtype=np.float64)
    nearest_ordinal: list[int | None] = [None] * n
    nearest_ts: list[int | None] = [None] * n
    nearest_lon = np.full(n, np.nan, dtype=np.float64)
    nearest_lat = np.full(n, np.nan, dtype=np.float64)
    peer_eligible_n = np.zeros(n, dtype=np.int64)

    for rid, row_idx in row_groups.items():
        past_ts, past_ord, past_lon, past_lat, bounds = history_by_rid[rid]
        hist_row_n, hist_date_n = raw_history_by_rid[rid]
        time_idx = row_query_idx[row_idx]
        own_ref_n[row_idx] = hist_row_n[time_idx]
        own_ref_dates[row_idx] = hist_date_n[time_idx]
        valid_current = coordinate_valid[row_idx]
        own_ok_at_time = eligible_by_rid[rid][time_idx]
        own_distance_eligible[row_idx] = valid_current & own_ok_at_time

        gear, single = gear_map.get(rid, (None, False))
        if single and gear is not None and gear in eligible_count_by_gear:
            peer_eligible_n[row_idx] = eligible_count_by_gear[gear][time_idx] - own_ok_at_time.astype(np.int64)

        for idx in row_idx[own_distance_eligible[row_idx]]:
            qidx = row_query_idx[idx]
            lo, hi = bounds[qidx]
            # Chunk even duplicate-hour inputs so each distance vector is
            # bounded by the 720-hour window length in unique source hours.
            best_distance = float("inf")
            chosen = -1
            for chunk_lo in range(int(lo), int(hi), WINDOW_HOURS):
                chunk_hi = min(chunk_lo + WINDOW_HOURS, int(hi))
                d = _haversine_many(lon[idx], lat[idx], past_lon[chunk_lo:chunk_hi], past_lat[chunk_lo:chunk_hi])
                dmin = float(np.min(d))
                tied = np.flatnonzero(d == dmin)
                chunk_choice = min((chunk_lo + int(k) for k in tied),
                                   key=lambda k: (int(past_ts[k]), int(past_ord[k])))
                if dmin < best_distance or (dmin == best_distance and
                    (chosen < 0 or (int(past_ts[chunk_choice]), int(past_ord[chunk_choice])) <
                     (int(past_ts[chosen]), int(past_ord[chosen])))):
                    best_distance = dmin
                    chosen = chunk_choice
            nearest_distance[idx] = best_distance
            nearest_ordinal[idx] = int(past_ord[chosen])
            nearest_ts[idx] = int(past_ts[chosen])
            nearest_lon[idx] = float(past_lon[chosen])
            nearest_lat[idx] = float(past_lat[chosen])

    peer_eligible = own_distance_eligible & (peer_eligible_n >= MIN_OTHER_PEERS)
    own_status, own_reason, peer_status, peer_reason = [], [], [], []
    for i in range(n):
        if own_distance_eligible[i]:
            own_status.append("keep")
            own_reason.append("passed")
        elif not coordinate_valid[i]:
            own_status.append("defer")
            own_reason.append("invalid_current_coordinate")
        else:
            own_status.append("defer")
            own_reason.append("insufficient_24_valid_positions_or_3_source_clock_dates")
        if peer_eligible[i]:
            peer_status.append("keep")
            peer_reason.append("passed")
        elif not coordinate_valid[i]:
            peer_status.append("not_applicable")
            peer_reason.append("upstream_current_coordinate_invalid")
        elif not own_distance_eligible[i]:
            peer_status.append("not_applicable")
            peer_reason.append("upstream_own_history_ineligible")
        else:
            gear, single = gear_map.get(str(ledger.at[i, "rfid_id"]), (None, False))
            if gear is None or not single:
                peer_reason.append("unknown_mixed_or_non_single_gear")
            else:
                peer_reason.append("fewer_than_5_other_same_gear_history_eligible_vessels")
            peer_status.append("defer")

    ledger["own_ref_n"] = own_ref_n
    ledger["own_ref_dates"] = own_ref_dates
    ledger["own_distance_eligible"] = own_distance_eligible
    ledger["nearest_distance_m"] = nearest_distance
    ledger["nearest_source_ordinal"] = pd.array(nearest_ordinal, dtype="Int64")
    ledger["nearest_ts"] = pd.array(nearest_ts, dtype="Int64")
    ledger["nearest_cen_lon"] = nearest_lon
    ledger["nearest_cen_lat"] = nearest_lat
    ledger["peer_eligible_n"] = peer_eligible_n
    ledger["peer_eligible"] = peer_eligible
    ledger["own_status"] = own_status
    ledger["own_reason"] = own_reason
    ledger["peer_status"] = peer_status
    ledger["peer_reason"] = peer_reason
    ledger = ledger[LEDGER_COLUMNS]

    vessel_ids = sorted(set(gear_map) | set(row_groups))
    vessel_rows: list[dict[str, Any]] = []
    for rid in vessel_ids:
        idx = row_groups.get(rid, np.asarray([], dtype=np.int64))
        gear, _ = gear_map.get(rid, (None, False))
        vessel_rows.append({
            "rfid_id": rid, "primary_gear": gear, "observed_n": int(len(idx)),
            "valid_position_n": int(coordinate_valid[idx].sum()) if len(idx) else 0,
            "own_eligible_n": int(own_distance_eligible[idx].sum()) if len(idx) else 0,
            "peer_eligible_n": int(peer_eligible[idx].sum()) if len(idx) else 0,
        })
    per_vessel = pd.DataFrame(vessel_rows, columns=VESSEL_COLUMNS)
    summary = {
        "row_n": int(n), "rfid_n": int(len(vessel_ids)),
        "observed_n": int(per_vessel["observed_n"].sum()),
        "valid_position_n": int(per_vessel["valid_position_n"].sum()),
        "own_eligible_n": int(per_vessel["own_eligible_n"].sum()),
        "peer_eligible_n": int(per_vessel["peer_eligible_n"].sum()),
        "definitions": {
            "history_window": "valid finite/range-checked centroid rows in [t-720,t); current/future excluded",
            "history_gate": "at least 24 valid positions and 3 distinct floor(ts/24) source-clock dates",
            "distance": "minimum haversine distance to past centroid rows, Earth radius 6371000 m; proxy only",
            "peer_gate": "own distance eligible and at least 5 other history-eligible vessels in same known single-code gear at query t",
        },
    }
    return {"ledger": ledger, "per_vessel": per_vessel, "summary": summary}
