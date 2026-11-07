"""Independent inventory of contiguous triples and small-small-non-small patterns.

Per CONTRACT.md and PROTOCOL.md in round_009_20261106:
- Implemented completely independently from Luna module (no import of transition_rules).
- Reads existing canonical R4 candidate_ledger.parquet (99,677 rows, 82 RFIDs) and R3 gear_registry.csv.
- Validates raw keys before any lossy cast.
- Computes exact valid geometry contiguous triples (u-2, u-1, u) and patterns (small, small, non-small).
- Geometry validity: finite len_m >= 0 and bbox_m >= 0.
- Small: valid geometry and len_m <= 100 and bbox_m <= 100.
- Produces per_vessel.csv, summary.json, cases.csv, and execution_receipt.json.
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

# Memory preflight constants (MiB)
GEMINI_INVENTORY_MIB = 512
LUNA_FIXTURE_MIB = 768
RESERVE_MIB = 640
TOTAL_REQUIRED_MIB = GEMINI_INVENTORY_MIB + LUNA_FIXTURE_MIB + RESERVE_MIB  # 1920 MiB
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
                    procs.append({"pid": p.info["pid"], "name": name, "rss_bytes": int(rss), "rss_mib": round(rss / (1024 * 1024), 2)})
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
    """Strictly validate keys before casting to avoid silent truncation (Terra review defect 1)."""
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


def count_triples_and_patterns(
    frame: pd.DataFrame,
    gear_registry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Compute contiguous triples and small-small-non-small patterns independently.
    
    Returns:
        per_vessel: DataFrame with columns [rfid_id, primary_gear, valid_triple_n, pattern_n] (82 rows)
        cases: DataFrame with earliest pattern source rows per gear (max 12 rows)
        annotated_frame: DataFrame with boolean columns [triplet_valid, pattern, primary_gear]
        metrics: Dictionary with aggregated counts and breakdown
    """
    n_rows = len(frame)
    if n_rows != 99677:
        raise ValueError(f"Expected 99,677 rows, found {n_rows}")
    if frame["rfid_id"].nunique() != 82:
        raise ValueError(f"Expected 82 RFIDs, found {frame['rfid_id'].nunique()}")

    # Validate gear registry
    if len(gear_registry) != 82 or gear_registry["rfid_id"].nunique() != 82:
        raise ValueError("gear_registry must contain exactly 82 unique RFIDs")
    gear_map = dict(zip(gear_registry["rfid_id"].astype(str), gear_registry["primary_gear"]))

    # Extract arrays for high-performance vectorized checks
    rfid_arr = frame["rfid_id"].astype(str).to_numpy()
    ts_arr = frame["ts"].to_numpy(dtype=np.int64)
    len_arr = frame["len_m"].to_numpy(dtype=float)
    bbox_arr = frame["bbox_m"].to_numpy(dtype=float)

    # Geometry valid: finite and len_m >= 0 and bbox_m >= 0
    valid_geom = (
        np.isfinite(len_arr)
        & np.isfinite(bbox_arr)
        & (len_arr >= 0.0)
        & (bbox_arr >= 0.0)
    )

    # small iff len <= 100 AND bbox <= 100 with valid geometry
    is_small = valid_geom & (len_arr <= 100.0) & (bbox_arr <= 100.0)

    # Build fast lookup map: (rfid_id, ts) -> (is_valid_geom, is_small, index)
    lookup: dict[tuple[str, int], tuple[bool, bool, int]] = {}
    for i in range(n_rows):
        lookup[(rfid_arr[i], int(ts_arr[i]))] = (bool(valid_geom[i]), bool(is_small[i]), i)

    # Evaluate contiguous triple and pattern for each row
    triplet_valid = np.zeros(n_rows, dtype=bool)
    pattern = np.zeros(n_rows, dtype=bool)

    for i in range(n_rows):
        r = rfid_arr[i]
        t = int(ts_arr[i])
        vg = valid_geom[i]
        sm = is_small[i]

        prev1 = lookup.get((r, t - 1))
        prev2 = lookup.get((r, t - 2))

        # Fully observed valid geometry contiguous triple (t-2, t-1, t)
        if vg and prev1 is not None and prev1[0] and prev2 is not None and prev2[0]:
            triplet_valid[i] = True
            # small-small-non-small: prev2 is small AND prev1 is small AND current is NOT small
            if prev2[1] and prev1[1] and (not sm):
                pattern[i] = True

    # Build annotated frame
    annotated = frame.copy()
    annotated["triplet_valid"] = triplet_valid
    annotated["pattern"] = pattern
    annotated["primary_gear"] = [gear_map.get(r) for r in rfid_arr]

    # Aggregate per vessel (MUST have all 82 RFIDs sorted by rfid_id)
    # Ensure all gear registry RFIDs are represented
    per_vessel_records = []
    for r in sorted(gear_registry["rfid_id"].astype(str).unique()):
        r_rows = annotated[annotated["rfid_id"] == r]
        g = gear_map.get(r)
        if len(r_rows) > 0:
            tv_n = int(r_rows["triplet_valid"].sum())
            pat_n = int(r_rows["pattern"].sum())
        else:
            tv_n = 0
            pat_n = 0
        per_vessel_records.append({
            "rfid_id": str(r),
            "primary_gear": g,
            "valid_triple_n": tv_n,
            "pattern_n": pat_n,
        })

    per_vessel = pd.DataFrame(per_vessel_records)
    if len(per_vessel) != 82 or per_vessel["rfid_id"].duplicated().any():
        raise ValueError(f"Roster error: per_vessel has {len(per_vessel)} rows")

    # Extract earliest pattern cases per gear
    # Contract: "Deterministic case one earliest pattern per gear, ties RFID lexicographic then ts/ordinal;
    # save 3 source rows per case (t-2,t-1,t), max 12. If gear has none explicit no sample."
    pattern_indices = np.where(pattern)[0]
    pattern_subset = annotated.iloc[pattern_indices]

    cases_records = []
    gear_cases_summary = {}
    distinct_gears = sorted(gear_registry["primary_gear"].dropna().unique())

    for gear in distinct_gears:
        g_patterns = pattern_subset[pattern_subset["primary_gear"] == gear]
        if len(g_patterns) == 0:
            gear_cases_summary[gear] = {"has_pattern": False, "case": None}
            continue

        # Sort: ts ASC, rfid_id ASC (lexicographical), source_ordinal ASC
        sorted_pats = g_patterns.sort_values(
            by=["ts", "rfid_id", "source_ordinal"],
            ascending=[True, True, True],
        )
        winner = sorted_pats.iloc[0]
        win_rfid = str(winner["rfid_id"])
        win_t = int(winner["ts"])
        win_ord = int(winner["source_ordinal"])

        gear_cases_summary[gear] = {
            "has_pattern": True,
            "rfid_id": win_rfid,
            "pattern_end_ts": win_t,
            "source_ordinal": win_ord,
        }

        # Save 3 source rows: t-2, t-1, t
        for step_label, dt in [("t-2", -2), ("t-1", -1), ("t", 0)]:
            t_target = win_t + dt
            src_info = lookup.get((win_rfid, t_target))
            if src_info is None:
                raise RuntimeError(f"Source row for case ({win_rfid}, {t_target}) missing from lookup")
            src_row = frame.iloc[src_info[2]]
            cases_records.append({
                "gear": gear,
                "case_rfid_id": win_rfid,
                "case_pattern_ts": win_t,
                "step": step_label,
                "rfid_id": str(src_row["rfid_id"]),
                "ts": int(src_row["ts"]),
                "source_ordinal": int(src_row["source_ordinal"]),
                "len_m": float(src_row["len_m"]),
                "bbox_m": float(src_row["bbox_m"]),
                "cen_lon": float(src_row["cen_lon"]),
                "cen_lat": float(src_row["cen_lat"]),
                "score": float(src_row["score"]),
                "is_small": bool((src_row["len_m"] <= 100.0) and (src_row["bbox_m"] <= 100.0)),
            })

    cases_df = pd.DataFrame(cases_records)
    if len(cases_df) > 12:
        raise ValueError(f"Cases exceed 12 rows limit: {len(cases_df)}")

    # Per gear aggregation
    per_gear = per_vessel.groupby("primary_gear", sort=True).agg(
        vessels=("rfid_id", "count"),
        valid_triple_n=("valid_triple_n", "sum"),
        pattern_n=("pattern_n", "sum"),
    ).reset_index()
    per_gear["pattern_rate"] = per_gear["pattern_n"] / per_gear["valid_triple_n"].replace(0, np.nan)

    metrics = {
        "valid_triple_n": int(triplet_valid.sum()),
        "pattern_n": int(pattern.sum()),
        "total_rows": n_rows,
        "unique_rfids": 82,
        "pattern_rate_overall": float(pattern.sum() / triplet_valid.sum()) if triplet_valid.sum() > 0 else 0.0,
        "per_gear": per_gear.to_dict(orient="records"),
        "gear_cases_summary": gear_cases_summary,
        "cases_count": len(cases_df),
    }

    return per_vessel, cases_df, annotated, metrics


def run_inventory(
    output_dir: Path | str,
    canonical_parquet: Path | str = CANONICAL_PATH,
    gear_registry_csv: Path | str = GEAR_REGISTRY_PATH,
) -> int:
    """Execute complete independent inventory workflow."""
    start_time = time.perf_counter()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    print(f"[{start_iso}] Starting Independent Inventory (Round 9)...")
    print(f"Output directory: {out}")

    # 1. RAM preflight check
    avail_bytes = get_available_bytes()
    avail_mib = avail_bytes / (1024 * 1024)
    procs = get_active_processes()
    allowed = avail_bytes >= TOTAL_REQUIRED_BYTES

    receipt: dict[str, Any] = {
        "component": "independent_inventory.py (Gemini worker)",
        "round": "round_009_20261106",
        "started_at": start_iso,
        "status": "starting",
        "ram_preflight": {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "available_bytes": avail_bytes,
            "available_mib": round(avail_mib, 2),
            "gemini_inventory_mib": GEMINI_INVENTORY_MIB,
            "luna_fixture_mib": LUNA_FIXTURE_MIB,
            "reserve_mib": RESERVE_MIB,
            "total_required_mib": TOTAL_REQUIRED_MIB,
            "allowed": allowed,
            "active_python_processes": procs,
        },
    }

    if not allowed:
        receipt.update(
            status="memory_deferred",
            exit_code=75,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            error="Available memory below required 1920 MiB",
        )
        write_json_atomic(out / "execution_receipt.json", receipt)
        print(f"RAM preflight FAILED: Available {avail_mib:.1f} MiB < Required {TOTAL_REQUIRED_MIB} MiB. Deferring.")
        return 75

    print(f"RAM preflight PASSED: Available {avail_mib:.1f} MiB >= Required {TOTAL_REQUIRED_MIB} MiB")

    # 2. Source and Input Hashes
    canon_p = Path(canonical_parquet).resolve()
    gear_p = Path(gear_registry_csv).resolve()
    script_p = Path(__file__).resolve()

    receipt["sources"] = {
        str(script_p): sha256_file(script_p),
        str(HERE / "CONTRACT.md"): sha256_file(HERE / "CONTRACT.md"),
        str(HERE / "PROTOCOL.md"): sha256_file(HERE / "PROTOCOL.md"),
    }
    receipt["inputs"] = {
        str(canon_p): {"sha256": sha256_file(canon_p), "bytes": canon_p.stat().st_size},
        str(gear_p): {"sha256": sha256_file(gear_p), "bytes": gear_p.stat().st_size},
    }

    # 3. Read and validate raw inputs
    cols = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
    table = pq.read_table(canon_p, columns=cols)
    raw_frame = table.to_pandas()
    validated_frame = validate_raw_keys(raw_frame, "canonical")

    gear_registry = pd.read_csv(gear_p, usecols=["rfid_id", "primary_gear", "is_single_code"], dtype={"rfid_id": str})

    # 4. Perform counting
    t_count_start = time.perf_counter()
    per_vessel, cases_df, annotated, metrics = count_triples_and_patterns(validated_frame, gear_registry)
    t_count_elapsed = time.perf_counter() - t_count_start

    # 5. Save outputs
    # A. per_vessel.csv
    per_vessel_path = out / "per_vessel.csv"
    per_vessel.to_csv(per_vessel_path, index=False)

    # B. cases.csv
    cases_path = out / "cases.csv"
    cases_df.to_csv(cases_path, index=False)

    # C. summary.json
    # CONTRACT requires top-level valid_triple_n and pattern_n integer counts
    summary = {
        "valid_triple_n": metrics["valid_triple_n"],
        "pattern_n": metrics["pattern_n"],
        "total_canonical_rows": metrics["total_rows"],
        "unique_rfids": metrics["unique_rfids"],
        "pattern_rate_overall": metrics["pattern_rate_overall"],
        "per_gear": metrics["per_gear"],
        "gear_cases_summary": metrics["gear_cases_summary"],
        "cases_count": metrics["cases_count"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ram_preflight": receipt["ram_preflight"],
        "inputs": receipt["inputs"],
    }
    summary_path = out / "summary.json"
    write_json_atomic(summary_path, summary)

    # Compute output hashes
    output_files = [per_vessel_path, cases_path, summary_path]
    receipt["outputs"] = {
        p.name: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
        for p in output_files
    }

    elapsed_total = time.perf_counter() - start_time
    receipt.update(
        status="completed",
        exit_code=0,
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        elapsed_seconds=round(elapsed_total, 4),
        count_elapsed_seconds=round(t_count_elapsed, 4),
        peak_working_set_bytes=get_peak_working_set_bytes(),
        metrics_summary={
            "valid_triple_n": metrics["valid_triple_n"],
            "pattern_n": metrics["pattern_n"],
            "unique_rfids": metrics["unique_rfids"],
        },
    )

    receipt_path = out / "execution_receipt.json"
    write_json_atomic(receipt_path, receipt)
    # Update outputs to also include execution_receipt.json
    receipt["outputs"]["execution_receipt.json"] = {
        "sha256": sha256_file(receipt_path),
        "bytes": receipt_path.stat().st_size,
    }
    write_json_atomic(receipt_path, receipt)

    print(f"[{receipt['finished_at']}] Independent Inventory Completed Successfully in {elapsed_total:.2f}s!")
    print(f"  Valid Triples: {metrics['valid_triple_n']}")
    print(f"  Patterns:      {metrics['pattern_n']}")
    print(f"  Cases:         {len(cases_df)} rows")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Independent Contiguous Triple & Pattern Inventory (Round 9)")
    parser.add_argument("--output-dir", default=str(HERE / "inventory_outputs"), help="Path to write inventory deliverables")
    parser.add_argument("--canonical", default=str(CANONICAL_PATH), help="Path to canonical candidate_ledger.parquet")
    parser.add_argument("--registry", default=str(GEAR_REGISTRY_PATH), help="Path to gear_registry.csv")
    args = parser.parse_args()

    sys.exit(run_inventory(args.output_dir, args.canonical, args.registry))
