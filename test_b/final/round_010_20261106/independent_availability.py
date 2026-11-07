"""Independent Position Availability and Nearest Past Distance Probe (Round 10).

Per CONTRACT.md and PROTOCOL.md in round_010_20261106:
- Implemented completely independently from Luna module (no import of position_probe or Luna outputs).
- Reads existing canonical R4 candidate_ledger.parquet (99,677 rows, 82 RFIDs) and R3 gear_registry.csv.
- Validates raw keys before any lossy cast.
- Computes valid coordinates, own past history eligibility [t-720, t), and peer history availability.
- Evaluates 12 scalar nearest past Haversine distance queries (4 gears x 3 queries: first, middle, last).
- Writes per_vessel.csv, summary.json, independent_distance_cases.csv, and EXECUTION.json
  to independent_outputs/actual_001.
- No self-reference of EXECUTION.json inside receipt outputs.
- No event/accident/label columns loaded or referenced.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CANONICAL_PATH = HERE.parent / "round_004_20261105" / "execution_001" / "candidate_ledger.parquet"
GEAR_REGISTRY_PATH = HERE.parent / "round_003_20261105" / "gear_registry.csv"

# Haversine radius in meters
HAVERSINE_RADIUS_M = 6371000.0

# Memory preflight constants (MiB)
GEMINI_EXTRA_MIB = 512
LUNA_PROBE_MIB = 768
RESERVE_MIB = 640
TOTAL_REQUIRED_MIB = GEMINI_EXTRA_MIB + LUNA_PROBE_MIB + RESERVE_MIB  # 1920 MiB
TOTAL_REQUIRED_BYTES = TOTAL_REQUIRED_MIB * 1024 * 1024


def sha256_file(path: Path | str) -> str:
    """Compute SHA-256 digest of a file in 1MB chunks."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path: Path | str, value: Any) -> None:
    """Atomically write JSON to file in UTF-8."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(target)


def get_available_bytes() -> int:
    """Return available physical memory in bytes."""
    if os.name == "nt":
        class Memory(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total", ctypes.c_ulonglong),
                ("available", ctypes.c_ulonglong),
                ("totalpage", ctypes.c_ulonglong),
                ("availablepage", ctypes.c_ulonglong),
                ("totalvirtual", ctypes.c_ulonglong),
                ("availablevirtual", ctypes.c_ulonglong),
                ("extended", ctypes.c_ulonglong),
            ]
        mem = Memory()
        mem.length = ctypes.sizeof(mem)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            raise OSError("Windows GlobalMemoryStatusEx failed")
        return int(mem.available)
    # Linux fallback
    try:
        meminfo = Path("/proc/meminfo").read_text()
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except Exception:
        pass
    raise OSError("Unable to determine available memory")


def get_active_processes() -> list[dict[str, Any]]:
    """Return snapshot of active python processes and memory."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                name = p.info.get("name") or ""
                if "python" in name.lower():
                    mem = p.info.get("memory_info")
                    rss = mem.rss if mem is not None else 0
                    procs.append({
                        "pid": p.info["pid"],
                        "name": name,
                        "rss_bytes": int(rss),
                        "rss_mib": round(rss / (1024 * 1024), 2),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(procs, key=lambda x: x["rss_bytes"], reverse=True)
    except ImportError:
        return []


def get_peak_working_set_bytes() -> int | None:
    """Return peak working set in bytes for current process."""
    try:
        import psutil
        info = psutil.Process().memory_info()
        return int(getattr(info, "peak_wset", getattr(info, "rss", 0)))
    except Exception:
        if os.name == "nt":
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            c = PROCESS_MEMORY_COUNTERS()
            c.cb = ctypes.sizeof(c)
            try:
                ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
                )
                return int(c.PeakWorkingSetSize) if ok else None
            except Exception:
                return None
        return None


def validate_raw_keys(df: pd.DataFrame, name: str = "canonical") -> pd.DataFrame:
    """Strictly validate keys before casting to avoid silent truncation."""
    for col in ["rfid_id", "ts", "source_ordinal"]:
        if col not in df.columns:
            raise ValueError(f"Missing required key column '{col}' in {name} frame")

    # 1. rfid_id check
    if df["rfid_id"].isna().any():
        raise ValueError(f"Null or NaN rfid_id detected in {name} frame")
    rid_s = df["rfid_id"].astype(str)
    if (rid_s.str.strip() == "").any():
        raise ValueError(f"Empty rfid_id detected in {name} frame")

    # 2. source_ordinal check: original raw values
    raw_ord = df["source_ordinal"]
    if raw_ord.isna().any():
        raise ValueError(f"Null or NaN source_ordinal detected in {name} frame")
    if raw_ord.dtype == bool or any(isinstance(x, (bool, np.bool_)) for x in raw_ord):
        raise ValueError(f"Boolean source_ordinal detected in {name} frame")

    ord_numeric = pd.to_numeric(raw_ord, errors="coerce")
    if ord_numeric.isna().any():
        raise ValueError(f"Non-numeric source_ordinal detected in {name} frame")
    if not np.all(np.isfinite(ord_numeric.to_numpy(dtype=float))):
        raise ValueError(f"Non-finite source_ordinal detected in {name} frame")
    if (ord_numeric % 1 != 0).any():
        raise ValueError(f"Fractional source_ordinal detected in {name} frame")
    if (ord_numeric < 0).any():
        raise ValueError(f"Negative source_ordinal detected in {name} frame")
    if not ord_numeric.is_unique:
        raise ValueError(f"Duplicate source_ordinal detected in {name} frame")

    # 3. ts check: original raw values
    raw_ts = df["ts"]
    if raw_ts.isna().any():
        raise ValueError(f"Null or NaN ts detected in {name} frame")
    if raw_ts.dtype == bool or any(isinstance(x, (bool, np.bool_)) for x in raw_ts):
        raise ValueError(f"Boolean ts detected in {name} frame")

    ts_numeric = pd.to_numeric(raw_ts, errors="coerce")
    if ts_numeric.isna().any():
        raise ValueError(f"Non-numeric ts detected in {name} frame")
    if not np.all(np.isfinite(ts_numeric.to_numpy(dtype=float))):
        raise ValueError(f"Non-finite ts detected in {name} frame")
    if (ts_numeric % 1 != 0).any():
        raise ValueError(f"Fractional hour timestamp detected in {name} frame")
    if (ts_numeric < 0).any():
        raise ValueError(f"Negative epoch-hour timestamp detected in {name} frame")
    if (ts_numeric > 10_000_000).any():
        raise ValueError(f"Timestamp exceeds reasonable epoch-hour range (>10M hours) in {name} frame")

    # Check (rfid_id, ts) uniqueness
    check_df = pd.DataFrame({"rid": rid_s, "ts": ts_numeric.astype("int64")})
    if check_df.duplicated(subset=["rid", "ts"]).any():
        raise ValueError(f"Duplicate (rfid_id, ts) detected in {name} frame")

    out = df.copy()
    out["rfid_id"] = rid_s
    out["ts"] = ts_numeric.astype("int64")
    out["source_ordinal"] = ord_numeric.astype("int64")
    return out


def haversine_scalar(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Compute spherical Haversine distance in meters with clamping to [0, 1]."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    lam1 = math.radians(lon1)
    lam2 = math.radians(lon2)
    dphi = phi2 - phi1
    dlam = lam2 - lam1
    a = (math.sin(dphi / 2.0) ** 2) + math.cos(phi1) * math.cos(phi2) * (math.sin(dlam / 2.0) ** 2)
    a = max(0.0, min(1.0, a))
    c = 2.0 * math.asin(math.sqrt(a))
    return HAVERSINE_RADIUS_M * c


def compute_independent_availability(
    frame: pd.DataFrame,
    gear_registry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Compute position validity, own history availability, peer eligibility, and distance cases.

    Returns:
        per_vessel: DataFrame with columns [rfid_id, primary_gear, observed_n, valid_position_n, own_eligible_n, peer_eligible_n]
        cases_df: DataFrame with 12 scalar nearest distance queries
        summary_dict: Dictionary of global metrics and breakdowns
    """
    n_rows = len(frame)
    if n_rows != 99677:
        raise ValueError(f"Expected 99,677 rows, found {n_rows}")
    if frame["rfid_id"].nunique() != 82:
        raise ValueError(f"Expected 82 RFIDs, found {frame['rfid_id'].nunique()}")

    if len(gear_registry) != 82 or gear_registry["rfid_id"].nunique() != 82:
        raise ValueError("gear_registry must contain exactly 82 unique RFIDs")

    gear_map = dict(zip(gear_registry["rfid_id"].astype(str), gear_registry["primary_gear"]))
    single_map = dict(zip(gear_registry["rfid_id"].astype(str), gear_registry["is_single_code"]))

    # 1. Coordinate validity
    lon_arr = frame["cen_lon"].to_numpy(dtype=float)
    lat_arr = frame["cen_lat"].to_numpy(dtype=float)
    coord_valid = (
        np.isfinite(lon_arr)
        & np.isfinite(lat_arr)
        & (lon_arr >= -180.0)
        & (lon_arr <= 180.0)
        & (lat_arr >= -90.0)
        & (lat_arr <= 90.0)
    )

    rfid_arr = frame["rfid_id"].astype(str).to_numpy()
    ts_arr = frame["ts"].to_numpy(dtype=np.int64)
    ord_arr = frame["source_ordinal"].to_numpy(dtype=np.int64)

    # 2. Extract valid points per vessel for fast history lookup
    vessel_valid_points: dict[str, dict[str, np.ndarray]] = {}
    for r in sorted(gear_registry["rfid_id"].astype(str).unique()):
        mask = (rfid_arr == r) & coord_valid
        v_ts = ts_arr[mask]
        v_ord = ord_arr[mask]
        v_lon = lon_arr[mask]
        v_lat = lat_arr[mask]
        v_dates = v_ts // 24
        vessel_valid_points[r] = {
            "ts": v_ts,
            "ordinal": v_ord,
            "lon": v_lon,
            "lat": v_lat,
            "dates": v_dates,
        }

    # 3. Compute own history: own_ref_n, own_ref_dates, own_distance_eligible per row
    own_ref_n = np.zeros(n_rows, dtype=np.int32)
    own_ref_dates = np.zeros(n_rows, dtype=np.int32)
    own_distance_eligible = np.zeros(n_rows, dtype=bool)

    # Pre-index row indices by vessel
    vessel_row_indices: dict[str, np.ndarray] = {}
    for r in vessel_valid_points:
        vessel_row_indices[r] = np.where(rfid_arr == r)[0]

    for r, pts in vessel_valid_points.items():
        row_idxs = vessel_row_indices[r]
        if len(row_idxs) == 0:
            continue
        v_ts = ts_arr[row_idxs]
        v_coord_valid = coord_valid[row_idxs]
        ts_pts = pts["ts"]
        date_pts = pts["dates"]

        # searchsorted for interval [t-720, t)
        left = np.searchsorted(ts_pts, v_ts - 720, side="left")
        right = np.searchsorted(ts_pts, v_ts, side="left")

        for i in range(len(row_idxs)):
            l = left[i]
            ri = right[i]
            cnt = ri - l
            global_idx = row_idxs[i]
            own_ref_n[global_idx] = cnt
            if cnt >= 24:
                d_cnt = len(np.unique(date_pts[l:ri]))
                own_ref_dates[global_idx] = d_cnt
                # Stage monotone: valid current coordinate AND own history >= 24 positions & >= 3 dates
                if d_cnt >= 3 and v_coord_valid[i]:
                    own_distance_eligible[global_idx] = True
            elif cnt > 0:
                own_ref_dates[global_idx] = len(np.unique(date_pts[l:ri]))

    # 4. Peer availability calculation at common query timestamp t
    # "Peer eligible count OTHER same SINGLE known group whose VALID past coords meet 24/3 at SAME t, no peer-current row required.
    # own eligible AND peer_n >= 5 marks peer_eligible; unknown/mixed/singleton defer, never normal."
    unique_query_ts = np.unique(ts_arr)
    n_queries = len(unique_query_ts)
    ts_to_idx = {t: i for i, t in enumerate(unique_query_ts)}

    # For each vessel p in gear registry: determine boolean eligibility across all unique query timestamps
    vessel_hist_elig_at_query = {}
    for r in sorted(gear_registry["rfid_id"].astype(str).unique()):
        pts = vessel_valid_points[r]
        ts_pts = pts["ts"]
        date_pts = pts["dates"]

        left = np.searchsorted(ts_pts, unique_query_ts - 720, side="left")
        right = np.searchsorted(ts_pts, unique_query_ts, side="left")
        counts = right - left

        elig_arr = np.zeros(n_queries, dtype=bool)
        cand_indices = np.where(counts >= 24)[0]
        for idx in cand_indices:
            l = left[idx]
            ri = right[idx]
            if len(np.unique(date_pts[l:ri])) >= 3:
                elig_arr[idx] = True
        vessel_hist_elig_at_query[r] = elig_arr

    # Group vessels by primary gear (single code only)
    gear_vessels: dict[str, list[str]] = {}
    for g, grp in gear_registry.groupby("primary_gear"):
        singles = grp[grp["is_single_code"]]["rfid_id"].astype(str).tolist()
        gear_vessels[g] = singles

    # For each vessel r, compute peer_n vector across unique query timestamps
    vessel_peer_n_vector: dict[str, np.ndarray] = {}
    for g, r_list in gear_vessels.items():
        if len(r_list) == 0:
            continue
        # Stack eligibility matrix (shape: num_vessels, n_queries)
        mat = np.vstack([vessel_hist_elig_at_query[r] for r in r_list])
        total_gear = np.sum(mat, axis=0)  # total eligible in gear at each query timestamp
        for i, r in enumerate(r_list):
            # OTHER vessels in same single known gear
            vessel_peer_n_vector[r] = total_gear - mat[i]

    # Evaluate peer eligibility for each row
    peer_n_col = np.zeros(n_rows, dtype=np.int32)
    peer_eligible_col = np.zeros(n_rows, dtype=bool)

    for i in range(n_rows):
        r = rfid_arr[i]
        t = ts_arr[i]
        q_idx = ts_to_idx[t]

        is_single = single_map.get(r, False)
        pn = vessel_peer_n_vector.get(r, np.zeros(n_queries, dtype=int))[q_idx] if is_single else 0
        peer_n_col[i] = pn

        # own_distance_eligible AND peer_n >= 5 AND single known gear
        if own_distance_eligible[i] and is_single and pn >= 5:
            peer_eligible_col[i] = True

    # 5. Build per_vessel summary (one row per all 82 RFIDs)
    # Required columns: rfid_id, primary_gear, observed_n, valid_position_n, own_eligible_n, peer_eligible_n
    per_vessel_records = []
    for r in sorted(gear_registry["rfid_id"].astype(str).unique()):
        row_idxs = vessel_row_indices[r]
        g = gear_map.get(r)
        obs_n = len(row_idxs)
        val_pos_n = int(np.sum(coord_valid[row_idxs])) if obs_n > 0 else 0
        own_el_n = int(np.sum(own_distance_eligible[row_idxs])) if obs_n > 0 else 0
        peer_el_n = int(np.sum(peer_eligible_col[row_idxs])) if obs_n > 0 else 0

        per_vessel_records.append({
            "rfid_id": str(r),
            "primary_gear": g,
            "observed_n": obs_n,
            "valid_position_n": val_pos_n,
            "own_eligible_n": own_el_n,
            "peer_eligible_n": peer_el_n,
        })

    per_vessel = pd.DataFrame(per_vessel_records)
    if len(per_vessel) != 82 or per_vessel["rfid_id"].duplicated().any():
        raise ValueError(f"per_vessel roster mismatch: {len(per_vessel)} rows")

    # 6. Extract independent distance cases (max 12 queries: 4 gears x 3 queries)
    # Contract: "from each gear choose lexicographically smallest RFID with any own eligible observation,
    # then FIRST / MIDDLE (floor(n/2)) / LAST own eligible observations in t/ordinal order, dedup if small; max 12 queries.
    # For each scalar distance verify nearest by scalar stdlib haversine over strict own window, nearest ties earlier ts/ordinal,
    # output rfid_id,ts,source_ordinal,nearest_distance_m,nearest_source_ordinal,nearest_ts,own_ref_n,own_ref_dates."
    distinct_gears = sorted(gear_registry["primary_gear"].dropna().unique())
    cases_records = []
    gear_case_summary = {}

    for gear in distinct_gears:
        g_vessels = sorted(gear_registry[gear_registry["primary_gear"] == gear]["rfid_id"].astype(str).unique())
        # Filter vessels with any own eligible observation
        eligible_vessels = []
        for r in g_vessels:
            r_idxs = vessel_row_indices[r]
            if np.any(own_distance_eligible[r_idxs]):
                eligible_vessels.append(r)

        if not eligible_vessels:
            gear_case_summary[gear] = {"eligible_vessels_count": 0, "chosen_vessel": None}
            continue

        chosen_rfid = min(eligible_vessels)  # Lexicographically smallest
        gear_case_summary[gear] = {
            "eligible_vessels_count": len(eligible_vessels),
            "chosen_vessel": chosen_rfid,
        }

        # Collect and sort all own eligible observations for this vessel
        r_idxs = vessel_row_indices[chosen_rfid]
        r_mask = own_distance_eligible[r_idxs]
        r_elig_idxs = r_idxs[r_mask]

        # Sort by ts ASC, source_ordinal ASC
        order = np.lexsort((ord_arr[r_elig_idxs], ts_arr[r_elig_idxs]))
        sorted_elig_idxs = r_elig_idxs[order]
        n_elig = len(sorted_elig_idxs)

        # FIRST, MIDDLE (floor(n/2)), LAST
        pick_positions = [0, n_elig // 2, n_elig - 1]
        deduped_pos = []
        seen_pos = set()
        for pos in pick_positions:
            if pos not in seen_pos and 0 <= pos < n_elig:
                seen_pos.add(pos)
                deduped_pos.append(pos)

        pts = vessel_valid_points[chosen_rfid]
        ts_pts = pts["ts"]
        ord_pts = pts["ordinal"]
        lon_pts = pts["lon"]
        lat_pts = pts["lat"]

        for pos in deduped_pos:
            g_idx = sorted_elig_idxs[pos]
            t = int(ts_arr[g_idx])
            s_ord = int(ord_arr[g_idx])
            c_lon = float(lon_arr[g_idx])
            c_lat = float(lat_arr[g_idx])
            ref_n = int(own_ref_n[g_idx])
            ref_d = int(own_ref_dates[g_idx])

            # Window [t-720, t)
            l = np.searchsorted(ts_pts, t - 720, side="left")
            ri = np.searchsorted(ts_pts, t, side="left")

            best_dist = float("inf")
            best_ord = None
            best_u = None

            for k in range(l, ri):
                u = int(ts_pts[k])
                u_ord = int(ord_pts[k])
                p_lon = float(lon_pts[k])
                p_lat = float(lat_pts[k])

                d = haversine_scalar(c_lon, c_lat, p_lon, p_lat)

                if d < best_dist:
                    best_dist = d
                    best_ord = u_ord
                    best_u = u
                elif d == best_dist:
                    # Exactly equal min distances tie earlier timestamp, then ordinal
                    if best_u is None or u < best_u or (u == best_u and u_ord < best_ord):
                        best_dist = d
                        best_ord = u_ord
                        best_u = u

            cases_records.append({
                "rfid_id": str(chosen_rfid),
                "ts": t,
                "source_ordinal": s_ord,
                "nearest_distance_m": best_dist,
                "nearest_source_ordinal": best_ord,
                "nearest_ts": best_u,
                "own_ref_n": ref_n,
                "own_ref_dates": ref_d,
            })

    cases_df = pd.DataFrame(cases_records)
    if len(cases_df) > 12:
        raise ValueError(f"Cases exceed 12 rows: {len(cases_df)}")

    # 7. Summary metrics
    # Per gear breakdown
    per_gear = per_vessel.groupby("primary_gear", sort=True).agg(
        vessels=("rfid_id", "count"),
        observed_n=("observed_n", "sum"),
        valid_position_n=("valid_position_n", "sum"),
        own_eligible_n=("own_eligible_n", "sum"),
        peer_eligible_n=("peer_eligible_n", "sum"),
    ).reset_index()

    summary_dict = {
        "observed_n": int(np.sum(per_vessel["observed_n"])),
        "valid_position_n": int(np.sum(per_vessel["valid_position_n"])),
        "own_eligible_n": int(np.sum(per_vessel["own_eligible_n"])),
        "peer_eligible_n": int(np.sum(per_vessel["peer_eligible_n"])),
        "total_rfids": 82,
        "per_gear": per_gear.to_dict(orient="records"),
        "gear_case_summary": gear_case_summary,
        "cases_n": len(cases_df),
        "notes": "4 vessels x 3 queries = 12 queries not 12 cases of accidents",
    }

    return per_vessel, cases_df, summary_dict


def run_availability(
    output_dir: Path | str,
    canonical_parquet: Path | str = CANONICAL_PATH,
    gear_registry_csv: Path | str = GEAR_REGISTRY_PATH,
) -> int:
    """Execute complete independent position availability workflow."""
    start_time = time.perf_counter()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    print(f"[{start_iso}] Starting Independent Position Availability Probe (Round 10)...")
    print(f"Output directory: {out}")

    # 1. RAM preflight check
    avail_bytes = get_available_bytes()
    avail_mib = avail_bytes / (1024 * 1024)
    procs = get_active_processes()
    allowed = avail_bytes >= TOTAL_REQUIRED_BYTES

    script_path = Path(__file__).resolve()
    canon_p = Path(canonical_parquet).resolve()
    gear_p = Path(gear_registry_csv).resolve()

    source_files = [script_path, HERE / "CONTRACT.md", HERE / "PROTOCOL.md"]
    source_hashes = {str(p): sha256_file(p) for p in source_files if p.exists()}

    input_files = [canon_p, gear_p]
    input_hashes = {str(p): {"sha256": sha256_file(p), "bytes": p.stat().st_size} for p in input_files}

    receipt: dict[str, Any] = {
        "component": "independent_availability.py (Gemini worker)",
        "round": "round_010_20261106",
        "started_at": start_iso,
        "status": "starting",
        "ram_preflight": {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "available_bytes": avail_bytes,
            "available_mib": round(avail_mib, 2),
            "gemini_extra_mib": GEMINI_EXTRA_MIB,
            "luna_probe_mib": LUNA_PROBE_MIB,
            "reserve_mib": RESERVE_MIB,
            "total_required_mib": TOTAL_REQUIRED_MIB,
            "allowed": allowed,
            "active_python_processes": procs,
        },
        "sources": source_hashes,
        "inputs": input_hashes,
    }

    if not allowed:
        receipt.update(
            status="failed",
            exit_code=75,
            error=f"RAM preflight deferred: available {avail_mib:.1f} MiB < required {TOTAL_REQUIRED_MIB} MiB",
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        write_json_atomic(out / "EXECUTION.json", receipt)
        print(f"RAM preflight FAILED: Available {avail_mib:.1f} MiB < Required {TOTAL_REQUIRED_MIB} MiB. Deferring.")
        return 75

    print(f"RAM preflight PASSED: Available {avail_mib:.1f} MiB >= Required {TOTAL_REQUIRED_MIB} MiB")

    # 2. Read and validate raw inputs
    cols = ["rfid_id", "ts", "source_ordinal", "cen_lon", "cen_lat"]
    table = pq.read_table(canon_p, columns=cols)
    raw_frame = table.to_pandas()
    validated_frame = validate_raw_keys(raw_frame, "canonical")

    gear_registry = pd.read_csv(gear_p, usecols=["rfid_id", "primary_gear", "is_single_code"], dtype={"rfid_id": str})

    # 3. Compute availability and cases
    t_comp_start = time.perf_counter()
    per_vessel, cases_df, summary_dict = compute_independent_availability(validated_frame, gear_registry)
    t_comp_elapsed = time.perf_counter() - t_comp_start

    # 4. Save outputs
    # A. per_vessel.csv
    per_vessel_path = out / "per_vessel.csv"
    per_vessel.to_csv(per_vessel_path, index=False)

    # B. independent_distance_cases.csv
    cases_path = out / "independent_distance_cases.csv"
    cases_df.to_csv(cases_path, index=False)

    # C. summary.json
    summary_path = out / "summary.json"
    summary_dict.update({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ram_preflight": receipt["ram_preflight"],
        "inputs": receipt["inputs"],
    })
    write_json_atomic(summary_path, summary_dict)

    # 5. Output hashes (CONTRACT: must NOT self-reference EXECUTION.json)
    output_files = [per_vessel_path, cases_path, summary_path]
    receipt["outputs"] = {
        p.name: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
        for p in output_files
    }

    elapsed_total = time.perf_counter() - start_time
    receipt.update(
        status="complete",  # CONTRACT: status='complete' ONLY on full success
        exit_code=0,
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        elapsed_seconds=round(elapsed_total, 4),
        compute_elapsed_seconds=round(t_comp_elapsed, 4),
        peak_working_set_bytes=get_peak_working_set_bytes(),
        counts_summary={
            "observed_n": summary_dict["observed_n"],
            "valid_position_n": summary_dict["valid_position_n"],
            "own_eligible_n": summary_dict["own_eligible_n"],
            "peer_eligible_n": summary_dict["peer_eligible_n"],
            "cases_n": summary_dict["cases_n"],
        },
    )

    execution_path = out / "EXECUTION.json"
    write_json_atomic(execution_path, receipt)

    print(f"[{receipt['finished_at']}] Independent Availability Completed Successfully in {elapsed_total:.2f}s!")
    print(f"  Observed:       {summary_dict['observed_n']}")
    print(f"  Valid Position: {summary_dict['valid_position_n']}")
    print(f"  Own Eligible:   {summary_dict['own_eligible_n']}")
    print(f"  Peer Eligible:  {summary_dict['peer_eligible_n']}")
    print(f"  Distance Cases: {summary_dict['cases_n']} queries")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Independent Position Availability and Nearest Past Distance Probe")
    parser.add_argument(
        "--output-dir",
        default=str(HERE / "independent_outputs" / "actual_001"),
        help="Target output directory (default: independent_outputs/actual_001)",
    )
    parser.add_argument("--canonical", default=str(CANONICAL_PATH), help="Path to candidate_ledger.parquet")
    parser.add_argument("--registry", default=str(GEAR_REGISTRY_PATH), help="Path to gear_registry.csv")
    args = parser.parse_args()

    sys.exit(run_availability(args.output_dir, args.canonical, args.registry))
