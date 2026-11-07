"""Independent Distance History Availability & Scalar CDF Inventory (Round 11).

Per CONTRACT.md and PROTOCOL.md in round_011_20261106:
- Implemented completely independently from Luna module (no import of position_rules or Luna outputs).
- Reads verified R10 position_ledger.parquet (99,677 rows, 82 RFIDs) and R3 gear_registry.csv.
- Validates raw keys before any lossy cast.
- Computes past distance distribution availability [t-720, t) and peer distance availability.
- Evaluates 12 scalar nearest past Haversine distance CDF queries (4 gears x 3 queries: first, middle, last).
- Writes per_vessel.csv, summary.json, independent_cdf_cases.csv, and EXECUTION.json
  to inventory_outputs/actual_001.
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
R10_LEDGER_PATH = HERE.parent / "round_010_20261106" / "probe_outputs" / "actual_001" / "position_ledger.parquet"
EXPECTED_R10_HASH = "c3943c953143a4f71335bfa8cceadac6c96b30287f40a935e41b375a429b63b8"
GEAR_REGISTRY_PATH = HERE.parent / "round_003_20261105" / "gear_registry.csv"

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


def compute_scalar_cdf(past_distances: np.ndarray, current_d: float) -> float:
    """Compute empirical one-tail CDF with half-weight for exact ties."""
    n = len(past_distances)
    if n == 0:
        return 0.0
    c_less = int(np.sum(past_distances < current_d))
    c_eq = int(np.sum(past_distances == current_d))
    return (float(c_less) + 0.5 * float(c_eq)) / float(n)


def compute_independent_distance_history(
    frame: pd.DataFrame,
    gear_registry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Compute distance history availability, peer eligibility, and 12 scalar CDF samples.

    Returns:
        per_vessel: DataFrame with columns [rfid_id, primary_gear, observed_n, raw_distance_available_n, self_distribution_eligible_n, peer_distribution_eligible_n]
        cases_df: DataFrame with 12 scalar CDF queries
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

    rfid_arr = frame["rfid_id"].astype(str).to_numpy()
    ts_arr = frame["ts"].to_numpy(dtype=np.int64)
    ord_arr = frame["source_ordinal"].to_numpy(dtype=np.int64)
    dist_arr = frame["nearest_distance_m"].to_numpy(dtype=float)
    r10_own_elig = frame["own_distance_eligible"].to_numpy(dtype=bool)

    # 1. Raw distance available:
    # "Raw distance available = R10 own_distance_eligible AND finite nearest_distance_m >= 0."
    raw_dist_avail = r10_own_elig & np.isfinite(dist_arr) & (dist_arr >= 0.0)

    # 2. Extract valid distance observations per vessel
    all_rfids = sorted(gear_registry["rfid_id"].astype(str).unique())
    vessel_dist_points: dict[str, dict[str, np.ndarray]] = {}
    vessel_row_indices: dict[str, np.ndarray] = {}

    for r in all_rfids:
        r_idxs = np.where(rfid_arr == r)[0]
        vessel_row_indices[r] = r_idxs

        mask = (rfid_arr == r) & raw_dist_avail
        v_ts = ts_arr[mask]
        v_ord = ord_arr[mask]
        v_dist = dist_arr[mask]
        v_dates = v_ts // 24
        vessel_dist_points[r] = {
            "ts": v_ts,
            "ordinal": v_ord,
            "dist": v_dist,
            "dates": v_dates,
        }

    # 3. Compute own distance history: self_distance_ref_n, self_distance_ref_dates, self_distribution_eligible
    # "Past distance distributions for vessel v query t contain ALL raw distance available rows at [t-720, t),
    # regardless their past legacy score/len/bbox. Current distance and future excluded.
    # Distribution eligible >= 24 past DISTANCE values and >= 3 distinct source-clock dates."
    self_ref_n = np.zeros(n_rows, dtype=np.int32)
    self_ref_dates = np.zeros(n_rows, dtype=np.int32)
    self_dist_eligible = np.zeros(n_rows, dtype=bool)

    for r in all_rfids:
        r_idxs = vessel_row_indices[r]
        if len(r_idxs) == 0:
            continue
        v_ts = ts_arr[r_idxs]
        v_avail = raw_dist_avail[r_idxs]
        pts = vessel_dist_points[r]
        ts_pts = pts["ts"]
        date_pts = pts["dates"]

        # searchsorted for window [t-720, t)
        left = np.searchsorted(ts_pts, v_ts - 720, side="left")
        right = np.searchsorted(ts_pts, v_ts, side="left")

        for i in range(len(r_idxs)):
            l = left[i]
            ri = right[i]
            cnt = ri - l
            g_idx = r_idxs[i]
            self_ref_n[g_idx] = cnt
            if cnt >= 24:
                d_cnt = len(np.unique(date_pts[l:ri]))
                self_ref_dates[g_idx] = d_cnt
                if d_cnt >= 3 and v_avail[i]:
                    self_dist_eligible[g_idx] = True
            elif cnt > 0:
                self_ref_dates[g_idx] = len(np.unique(date_pts[l:ri]))

    # 4. Peer distance history eligibility at common query t
    # "s4=s3 AND >= 5 OTHER peers whose own past DISTANCE distributions meet 24/3 at SAME t.
    # Other peer need no current row; reference history eligible computed at query t, not at peer last observation.
    # Use past raw distance available, NOT R10 peer_eligible/current coordinate history peer_n as qualification."
    unique_query_ts = np.unique(ts_arr)
    n_queries = len(unique_query_ts)
    ts_to_idx = {t: i for i, t in enumerate(unique_query_ts)}

    # For each vessel p in gear registry: determine boolean eligibility across all unique query timestamps
    vessel_dist_elig_at_query = {}
    for r in all_rfids:
        pts = vessel_dist_points[r]
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
        vessel_dist_elig_at_query[r] = elig_arr

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
        mat = np.vstack([vessel_dist_elig_at_query[r] for r in r_list])
        total_gear = np.sum(mat, axis=0)
        for i, r in enumerate(r_list):
            vessel_peer_n_vector[r] = total_gear - mat[i]

    # Evaluate peer distance distribution eligibility for each row
    peer_n_col = np.zeros(n_rows, dtype=np.int32)
    peer_dist_eligible_col = np.zeros(n_rows, dtype=bool)

    for i in range(n_rows):
        r = rfid_arr[i]
        t = ts_arr[i]
        q_idx = ts_to_idx[t]

        is_single = single_map.get(r, False)
        pn = vessel_peer_n_vector.get(r, np.zeros(n_queries, dtype=int))[q_idx] if is_single else 0
        peer_n_col[i] = pn

        if self_dist_eligible[i] and is_single and pn >= 5:
            peer_dist_eligible_col[i] = True

    # 5. Build per_vessel summary (one row per all 82 RFIDs)
    # Required columns: rfid_id, primary_gear, observed_n, raw_distance_available_n, self_distribution_eligible_n, peer_distribution_eligible_n
    per_vessel_records = []
    for r in all_rfids:
        r_idxs = vessel_row_indices[r]
        g = gear_map.get(r)
        obs_n = len(r_idxs)
        raw_avail_n = int(np.sum(raw_dist_avail[r_idxs])) if obs_n > 0 else 0
        self_el_n = int(np.sum(self_dist_eligible[r_idxs])) if obs_n > 0 else 0
        peer_el_n = int(np.sum(peer_dist_eligible_col[r_idxs])) if obs_n > 0 else 0

        per_vessel_records.append({
            "rfid_id": str(r),
            "primary_gear": g,
            "observed_n": obs_n,
            "raw_distance_available_n": raw_avail_n,
            "self_distribution_eligible_n": self_el_n,
            "peer_distribution_eligible_n": peer_el_n,
        })

    per_vessel = pd.DataFrame(per_vessel_records)
    if len(per_vessel) != 82 or per_vessel["rfid_id"].duplicated().any():
        raise ValueError(f"per_vessel roster mismatch: {len(per_vessel)} rows")

    # 6. Extract independent CDF cases (max 12 queries: 4 gears x 3 queries)
    # Contract: "per gear minimum RFID with any self distribution eligible,
    # first/middle/last self eligible query sort ts/ordinal, max 12, dedupe.
    # Fields: rfid_id, ts, source_ordinal, nearest_distance_m, self_distance_ref_n, self_distance_ref_dates,
    # self_distance_cdf, peer_distance_eligible_n, peer_distance_cdf_mean (null if peer_n 0, else define CDF mean when n > 0 even if < 5)."
    distinct_gears = sorted(gear_registry["primary_gear"].dropna().unique())
    cases_records = []
    gear_case_summary = {}

    for gear in distinct_gears:
        g_vessels = sorted(gear_registry[gear_registry["primary_gear"] == gear]["rfid_id"].astype(str).unique())
        # Filter vessels with any self distribution eligible observation
        eligible_vessels = []
        for r in g_vessels:
            r_idxs = vessel_row_indices[r]
            if np.any(self_dist_eligible[r_idxs]):
                eligible_vessels.append(r)

        if not eligible_vessels:
            gear_case_summary[gear] = {"eligible_vessels_count": 0, "chosen_vessel": None}
            continue

        chosen_rfid = min(eligible_vessels)  # Lexicographically smallest
        gear_case_summary[gear] = {
            "eligible_vessels_count": len(eligible_vessels),
            "chosen_vessel": chosen_rfid,
        }

        # Collect and sort all self eligible observations for this vessel
        r_idxs = vessel_row_indices[chosen_rfid]
        r_mask = self_dist_eligible[r_idxs]
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

        pts = vessel_dist_points[chosen_rfid]
        ts_pts = pts["ts"]
        dist_pts = pts["dist"]

        # Potential peers: OTHER vessels in same single known gear
        candidate_peers = [p for p in g_vessels if p != chosen_rfid and single_map.get(p, False)]

        for pos in deduped_pos:
            g_idx = sorted_elig_idxs[pos]
            t = int(ts_arr[g_idx])
            s_ord = int(ord_arr[g_idx])
            d = float(dist_arr[g_idx])
            ref_n = int(self_ref_n[g_idx])
            ref_d = int(self_ref_dates[g_idx])

            # Self CDF over own past distances in [t-720, t)
            l = np.searchsorted(ts_pts, t - 720, side="left")
            ri = np.searchsorted(ts_pts, t, side="left")
            own_past = dist_pts[l:ri]
            if len(own_past) != ref_n:
                raise ValueError(f"Self ref count mismatch: {len(own_past)} vs {ref_n}")
            self_cdf = compute_scalar_cdf(own_past, d)

            # Peer eligibility & peer CDF at query timestamp t
            qualified_peers = []
            peer_cdfs = []
            for p in candidate_peers:
                p_pts = vessel_dist_points[p]
                p_ts = p_pts["ts"]
                p_dates = p_pts["dates"]
                p_dist = p_pts["dist"]

                p_l = np.searchsorted(p_ts, t - 720, side="left")
                p_ri = np.searchsorted(p_ts, t, side="left")
                p_cnt = p_ri - p_l
                if p_cnt >= 24:
                    p_dcnt = len(np.unique(p_dates[p_l:p_ri]))
                    if p_dcnt >= 3:
                        qualified_peers.append(p)
                        p_past = p_dist[p_l:p_ri]
                        p_cdf = compute_scalar_cdf(p_past, d)
                        peer_cdfs.append(p_cdf)

            peer_n = len(qualified_peers)
            peer_cdf_mean = float(np.mean(peer_cdfs)) if peer_n > 0 else np.nan

            cases_records.append({
                "rfid_id": str(chosen_rfid),
                "ts": t,
                "source_ordinal": s_ord,
                "nearest_distance_m": d,
                "self_distance_ref_n": ref_n,
                "self_distance_ref_dates": ref_d,
                "self_distance_cdf": self_cdf,
                "peer_distance_eligible_n": peer_n,
                "peer_distance_cdf_mean": peer_cdf_mean,
            })

    cases_df = pd.DataFrame(cases_records)
    if len(cases_df) > 12:
        raise ValueError(f"Cases exceed 12 rows: {len(cases_df)}")

    # 7. Summary metrics
    per_gear = per_vessel.groupby("primary_gear", sort=True).agg(
        vessels=("rfid_id", "count"),
        observed_n=("observed_n", "sum"),
        raw_distance_available_n=("raw_distance_available_n", "sum"),
        self_distribution_eligible_n=("self_distribution_eligible_n", "sum"),
        peer_distribution_eligible_n=("peer_distribution_eligible_n", "sum"),
    ).reset_index()

    summary_dict = {
        "observed_n": int(np.sum(per_vessel["observed_n"])),
        "raw_distance_available_n": int(np.sum(per_vessel["raw_distance_available_n"])),
        "self_distribution_eligible_n": int(np.sum(per_vessel["self_distribution_eligible_n"])),
        "peer_distribution_eligible_n": int(np.sum(per_vessel["peer_distribution_eligible_n"])),
        "total_rfids": 82,
        "per_gear": per_gear.to_dict(orient="records"),
        "gear_case_summary": gear_case_summary,
        "cases_n": len(cases_df),
        "notes": "4 vessels x 3 queries = 12 queries not 12 cases of accidents",
    }

    return per_vessel, cases_df, summary_dict


def run_distance_history(
    output_dir: Path | str,
    r10_ledger_parquet: Path | str = R10_LEDGER_PATH,
    gear_registry_csv: Path | str = GEAR_REGISTRY_PATH,
) -> int:
    """Execute complete independent distance history inventory workflow."""
    start_time = time.perf_counter()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    print(f"[{start_iso}] Starting Independent Distance History Inventory (Round 11)...")
    print(f"Output directory: {out}")

    # 1. RAM preflight check
    avail_bytes = get_available_bytes()
    avail_mib = avail_bytes / (1024 * 1024)
    procs = get_active_processes()
    allowed = avail_bytes >= TOTAL_REQUIRED_BYTES

    script_path = Path(__file__).resolve()
    r10_p = Path(r10_ledger_parquet).resolve()
    gear_p = Path(gear_registry_csv).resolve()

    source_files = [script_path, HERE / "CONTRACT.md", HERE / "PROTOCOL.md"]
    source_hashes = {str(p): sha256_file(p) for p in source_files if p.exists()}

    # Verify R10 position ledger hash
    r10_sha = sha256_file(r10_p)
    if r10_sha != EXPECTED_R10_HASH:
        raise ValueError(f"R10 ledger hash mismatch: {r10_sha} != {EXPECTED_R10_HASH}")

    input_files = [r10_p, gear_p]
    input_hashes = {str(p): {"sha256": sha256_file(p), "bytes": p.stat().st_size} for p in input_files}

    receipt: dict[str, Any] = {
        "component": "independent_distance_history.py (Gemini worker)",
        "round": "round_011_20261106",
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
    cols = ["rfid_id", "ts", "source_ordinal", "nearest_distance_m", "own_distance_eligible"]
    table = pq.read_table(r10_p, columns=cols)
    raw_frame = table.to_pandas()
    validated_frame = validate_raw_keys(raw_frame, "r10_position_ledger")

    gear_registry = pd.read_csv(gear_p, usecols=["rfid_id", "primary_gear", "is_single_code"], dtype={"rfid_id": str})

    # 3. Compute distance history availability and CDF cases
    t_comp_start = time.perf_counter()
    per_vessel, cases_df, summary_dict = compute_independent_distance_history(validated_frame, gear_registry)
    t_comp_elapsed = time.perf_counter() - t_comp_start

    # 4. Save outputs
    # A. per_vessel.csv
    per_vessel_path = out / "per_vessel.csv"
    per_vessel.to_csv(per_vessel_path, index=False)

    # B. independent_cdf_cases.csv
    cases_path = out / "independent_cdf_cases.csv"
    cases_df.to_csv(cases_path, index=False)

    # C. summary.json
    summary_path = out / "summary.json"
    summary_dict.update({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ram_preflight": receipt["ram_preflight"],
        "inputs": receipt["inputs"],
    })
    write_json_atomic(summary_path, summary_dict)

    # 5. Output hashes (CONTRACT: non-recursive, must NOT self-reference EXECUTION.json)
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
            "raw_distance_available_n": summary_dict["raw_distance_available_n"],
            "self_distribution_eligible_n": summary_dict["self_distribution_eligible_n"],
            "peer_distribution_eligible_n": summary_dict["peer_distribution_eligible_n"],
            "cases_n": summary_dict["cases_n"],
        },
    )

    execution_path = out / "EXECUTION.json"
    write_json_atomic(execution_path, receipt)

    print(f"[{receipt['finished_at']}] Independent Distance History Completed Successfully in {elapsed_total:.2f}s!")
    print(f"  Observed:                  {summary_dict['observed_n']}")
    print(f"  Raw Distance Available:    {summary_dict['raw_distance_available_n']}")
    print(f"  Self Distribution Eligible:{summary_dict['self_distribution_eligible_n']}")
    print(f"  Peer Distribution Eligible:{summary_dict['peer_distribution_eligible_n']}")
    print(f"  CDF Cases:                 {summary_dict['cases_n']} queries")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Independent Distance History & CDF Inventory")
    parser.add_argument(
        "--output-dir",
        default=str(HERE / "inventory_outputs" / "actual_001"),
        help="Target output directory (default: inventory_outputs/actual_001)",
    )
    parser.add_argument("--r10-parquet", default=str(R10_LEDGER_PATH), help="Path to R10 position_ledger.parquet")
    parser.add_argument("--registry", default=str(GEAR_REGISTRY_PATH), help="Path to gear_registry.csv")
    args = parser.parse_args()

    sys.exit(run_distance_history(args.output_dir, args.r10_parquet, args.registry))
