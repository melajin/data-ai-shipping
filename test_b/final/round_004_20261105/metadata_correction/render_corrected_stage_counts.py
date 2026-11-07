"""Bounded metadata rendering script for Round 4 stage_counts correction.

Reads saved execution_001 candidate_ledger and pool_manifest selected columns
under a strict memory preflight check (<=384MiB estimated extra + 640MiB reserve).
Regenerates stage_counts_corrected.csv without rerunning rule calculations or metrics,
preserves original execution bytes, and verifies row/candidate count identicality.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROUND4_DIR = HERE.parent
if str(ROUND4_DIR) not in sys.path:
    sys.path.insert(0, str(ROUND4_DIR))

from evaluate_sequence import _build_stage_counts

ESTIMATED_EXTRA = 384 * 1024 * 1024
RESERVE = 640 * 1024 * 1024
REQUIRED_RAM = ESTIMATED_EXTRA + RESERVE


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _available_memory() -> tuple[int, int]:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        s = MEMORYSTATUSEX()
        s.dwLength = ctypes.sizeof(s)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            raise OSError("GlobalMemoryStatusEx failed")
        return int(s.ullAvailPhys), int(s.ullTotalPhys)
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2:
            info[parts[0].strip()] = int(parts[1].split()[0]) * 1024
    return info["MemAvailable"], info["MemTotal"]


def render() -> int:
    t0 = time.perf_counter()
    avail, total = _available_memory()
    print(f"RAM Preflight: available {avail / (1024**2):.1f} MiB / required {REQUIRED_RAM / (1024**2):.1f} MiB")
    if avail < REQUIRED_RAM:
        print(f"ERROR: Available memory {avail} < required {REQUIRED_RAM}", file=sys.stderr)
        return 75

    exec_dir = ROUND4_DIR / "execution_001"
    ledger_path = exec_dir / "candidate_ledger.parquet"
    manifest_path = exec_dir / "pool_manifest.csv"
    orig_counts_path = exec_dir / "stage_counts.csv"

    if not ledger_path.exists() or not manifest_path.exists() or not orig_counts_path.exists():
        print(f"ERROR: Missing inputs in {exec_dir}", file=sys.stderr)
        return 1

    # Selected columns only to keep memory footprint bounded
    selected_cols = [
        "rfid_id", "stage0_ok", "stage1_ok", "stage2_ok", "stage3_ok",
        "geometry_valid", "stage1_reason", "stage2_reason", "gear_missing_reason"
    ]
    print(f"Reading {len(selected_cols)} selected columns from candidate_ledger.parquet...")
    ledger = pq.read_table(ledger_path, columns=selected_cols).to_pandas()

    print("Reading pool_manifest.csv...")
    manifest = pd.read_csv(manifest_path, encoding="utf-8")

    print("Building corrected stage counts...")
    df_corrected = _build_stage_counts(ledger, manifest)

    out_csv = HERE / "stage_counts_corrected.csv"
    df_corrected.to_csv(out_csv, index=False)
    print(f"Wrote corrected stage counts to {out_csv.name} ({out_csv.stat().st_size} bytes)")

    # Read original stage_counts for comprehensive comparison
    df_orig = pd.read_csv(orig_counts_path, encoding="utf-8")

    assert len(df_orig) == len(df_corrected), f"Row count mismatch: {len(df_orig)} vs {len(df_corrected)}"

    comparison_records: list[dict[str, Any]] = []
    status_changes: list[dict[str, Any]] = []

    for i in range(len(df_orig)):
        row_o = df_orig.iloc[i]
        row_c = df_corrected.iloc[i]

        assert row_o["category_type"] == row_c["category_type"]
        assert row_o["stage"] == row_c["stage"]
        assert str(row_o["reason"]) == str(row_c["reason"])
        assert int(row_o["row_count"]) == int(row_c["row_count"]), f"Row count changed for {row_o['reason']}!"
        assert int(row_o["rfid_count"]) == int(row_c["rfid_count"]), f"RFID count changed for {row_o['reason']}!"

        changed = (row_o["status"] != row_c["status"])
        rec = {
            "category_type": row_o["category_type"],
            "stage": row_o["stage"],
            "reason": str(row_o["reason"]),
            "row_count": int(row_o["row_count"]),
            "rfid_count": int(row_o["rfid_count"]),
            "original_status": row_o["status"],
            "corrected_status": row_c["status"],
            "status_changed": changed,
        }
        comparison_records.append(rec)
        if changed:
            status_changes.append(rec)

    # Validate that keep counts stay exactly identical
    keep_orig = df_orig[df_orig["status"] == "keep"][["stage", "row_count", "rfid_count"]].to_dict("records")
    keep_corr = df_corrected[df_corrected["status"] == "keep"][["stage", "row_count", "rfid_count"]].to_dict("records")
    assert keep_orig == keep_corr, "Stage keep counts were altered!"

    comp_summary = {
        "timestamp_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_ledger_rows": len(ledger),
        "total_stage_count_rows": len(df_corrected),
        "status_change_count": len(status_changes),
        "status_changes": status_changes,
        "keep_counts_identical": (keep_orig == keep_corr),
        "keep_counts": keep_corr,
        "full_comparison": comparison_records,
    }

    comp_path = HERE / "counts_comparison.json"
    comp_path.write_text(json.dumps(comp_summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote comparison summary to {comp_path.name}")

    # Record old and new source hashes
    hashes = {
        "source_before_evaluator.py": _sha256(HERE / "source_before_evaluator.py"),
        "evaluate_sequence.py_corrected": _sha256(ROUND4_DIR / "evaluate_sequence.py"),
        "original_stage_counts.csv": _sha256(orig_counts_path),
        "stage_counts_corrected.csv": _sha256(out_csv),
    }
    hashes_path = HERE / "source_hashes.json"
    hashes_path.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote source hashes to {hashes_path.name}")

    elapsed = time.perf_counter() - t0
    print(f"Completed rendering in {elapsed:.2f}s with {len(status_changes)} status adjustments (missing_previous, missing_next).")
    return 0


if __name__ == "__main__":
    raise SystemExit(render())
