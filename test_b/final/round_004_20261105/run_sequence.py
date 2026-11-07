"""Round 4 execution runner: sequential candidate extraction and event evaluation.

This runner executes the integrated pipeline once after both sequence_rules.py and
evaluate_sequence.py are verified. It performs memory preflight checks before data loading,
prevents overwrite of complete receipts, and records peak working set and file hashes.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
EXPECTED_PEAK = 768 * 1024 * 1024
RESERVE = 640 * 1024 * 1024
TOTAL_MEMORY_REQUIRED = EXPECTED_PEAK + RESERVE


def _available_memory() -> tuple[int, int]:
    """Return (available_bytes, total_bytes) using OS-native APIs."""
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
            raise OSError("GlobalMemoryStatusEx failed; cannot verify available RAM")
        return int(s.ullAvailPhys), int(s.ullTotalPhys)
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2:
            info[parts[0].strip()] = int(parts[1].split()[0]) * 1024
    return info["MemAvailable"], info["MemTotal"]


def _processes() -> list[dict[str, Any]]:
    """Return list of top running processes sorted by RSS/WorkingSet."""
    try:
        import psutil
        out = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                mem = p.info.get("memory_info")
                rss = mem.rss if mem is not None else 0
                out.append({"pid": p.info["pid"], "name": p.info["name"], "rss_bytes": int(rss)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(out, key=lambda x: x["rss_bytes"], reverse=True)[:15]
    except ImportError:
        if os.name == "nt":
            cmd = "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Id,ProcessName,WorkingSet64 | ConvertTo-Json -Compress"
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                data = json.loads(r.stdout)
                data = [data] if isinstance(data, dict) else data
                return [{"pid": x["Id"], "name": x["ProcessName"], "rss_bytes": int(x["WorkingSet64"])} for x in data]
            except Exception as exc:
                return [{"inventory_error": str(exc)}]
        return []


def _peak_working_set() -> int | None:
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
        try:
            import resource
            v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return int(v if sys.platform == "darwin" else v * 1024)
        except Exception:
            return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run(output_dir: Path = HERE / "execution_001", root: Path = ROOT) -> int:
    output_dir = Path(output_dir).resolve()
    root = Path(root).resolve()

    # Enforce round isolation: output must reside inside this round folder
    if output_dir != HERE and HERE not in output_dir.parents:
        raise ValueError(f"Run outputs must stay inside this round folder: {HERE}")

    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "EXECUTION.json"

    # Refuse overwrite if complete execution receipt already exists
    if receipt_path.is_file():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            if existing.get("status") == "complete":
                print(f"Complete execution receipt already exists at {receipt_path}; refusing overwrite.")
                return 0
        except Exception:
            pass

    execution: dict[str, Any] = {
        "status": "starting",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "output_dir": str(output_dir),
        "python": sys.version,
        "platform": platform.platform(),
        "command": sys.argv,
        "memory_requirement_bytes": TOTAL_MEMORY_REQUIRED,
        "estimated_extra_peak_bytes": EXPECTED_PEAK,
        "reserve_bytes": RESERVE,
        "stages": {},
        "other_processes": [],
    }
    started = time.perf_counter()

    try:
        # Preflight inventory and available RAM before data loading or heavy operations
        execution["other_processes"] = [p for p in _processes() if p.get("pid") != os.getpid()]
        available, total = _available_memory()
        allowed = bool(available >= TOTAL_MEMORY_REQUIRED)
        execution["ram_preflight"] = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "available_bytes": available,
            "total_bytes": total,
            "allowed": allowed,
            "simultaneous_dataset_jobs_authorized": False,
        }
        execution["peak_working_set_bytes"] = _peak_working_set()

        if not allowed:
            execution.update(
                status="memory_deferred",
                exit_code=75,
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                elapsed_seconds=time.perf_counter() - started,
                error="Available RAM below 768 MiB estimated peak plus 640 MiB reserve; no data loaded.",
            )
            _write_json_atomic(receipt_path, execution)
            print(f"RAM preflight deferred: available {available / (1024**2):.1f} MiB < required {TOTAL_MEMORY_REQUIRED / (1024**2):.1f} MiB")
            return 75

        # Locate required inputs without reading yet
        parquet_path = root / "testB" / "final" / "round_002_20261105" / "execution_002" / "featured_rows.parquet"
        gear_path = root / "testB" / "final" / "round_003_20261105" / "gear_registry.csv"
        positives_matches = sorted((root / "testB").glob("*/round_008_linkage_audit_20261105/devset_positives.csv"))
        if len(positives_matches) != 1:
            raise FileNotFoundError(f"Expected exactly 1 devset_positives.csv match, found {len(positives_matches)}")
        positives_path = positives_matches[0]

        input_paths = [parquet_path, gear_path, positives_path]
        missing_inputs = [str(p) for p in input_paths if not p.exists()]
        if missing_inputs:
            raise FileNotFoundError(f"Missing required input files: {missing_inputs}")

        source_paths = [
            HERE / "sequence_rules.py",
            HERE / "evaluate_sequence.py",
            HERE / "run_sequence.py",
            HERE / "PROTOCOL.md",
            HERE / "CONTRACT.md",
        ]
        missing_sources = [str(p) for p in source_paths if not p.exists()]
        if missing_sources:
            raise FileNotFoundError(f"Missing required source files: {missing_sources}")

        execution["inputs"] = {
            p.name: {"path": str(p), "sha256": _sha256(p), "bytes": p.stat().st_size}
            for p in input_paths
        }
        execution["sources"] = {
            p.name: {"path": str(p), "sha256": _sha256(p)}
            for p in source_paths
        }
        execution["versions"] = {
            "numpy": _version("numpy"),
            "pandas": _version("pandas"),
            "pyarrow": _version("pyarrow"),
            "psutil": _version("psutil"),
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 1: Data read and schema verification
        stage_start = time.perf_counter()
        import pandas as pd
        import pyarrow.parquet as pq

        frame_cols = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
        frame = pq.read_table(parquet_path, columns=frame_cols).to_pandas()
        frame["rfid_id"] = frame["rfid_id"].astype(str)
        frame["ts"] = frame["ts"].astype("int64")
        frame["source_ordinal"] = frame["source_ordinal"].astype("int64")
        for c in ("len_m", "bbox_m", "cen_lon", "cen_lat", "score"):
            frame[c] = pd.to_numeric(frame[c], errors="coerce").astype(float)
        frame = frame.sort_values(["rfid_id", "ts", "source_ordinal"], kind="mergesort").reset_index(drop=True)

        gear_registry = pd.read_csv(gear_path, usecols=["rfid_id", "primary_gear", "is_single_code"], encoding="utf-8-sig")
        gear_registry["rfid_id"] = gear_registry["rfid_id"].astype(str)

        positives = pd.read_csv(positives_path, usecols=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"], encoding="utf-8-sig")
        positives["rfid_id"] = positives["rfid_id"].astype(str)
        positives["acc_id"] = positives["acc_id"].astype(str)
        positives["tier"] = pd.to_numeric(positives["tier"], errors="raise").astype(int)
        positives["acc_ts"] = pd.to_numeric(positives["acc_ts"], errors="raise").astype("int64")

        execution["stages"]["data_read"] = {
            "seconds": time.perf_counter() - stage_start,
            "rows_frame": int(len(frame)),
            "rows_gear": int(len(gear_registry)),
            "rows_positives": int(len(positives)),
            "peak_working_set_bytes": _peak_working_set(),
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 2: Sequential candidate extraction and ranking (sequence_rules.build_rules)
        stage_start = time.perf_counter()
        from sequence_rules import build_rules
        artifacts = build_rules(frame, gear_registry)
        artifacts["gear_registry"] = gear_registry

        execution["stages"]["build_rules"] = {
            "seconds": time.perf_counter() - stage_start,
            "ledger_rows": int(len(artifacts["ledger"])),
            "stage0_candidates": int(artifacts["ledger"]["stage0_ok"].sum()),
            "stage1_candidates": int(artifacts["ledger"]["stage1_ok"].sum()),
            "stage2_candidates": int(artifacts["ledger"]["stage2_ok"].sum()),
            "stage3_candidates": int(artifacts["ledger"]["stage3_ok"].sum()),
            "prediction_rows": int(len(artifacts["predictions"])),
            "peak_working_set_bytes": _peak_working_set(),
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 3: Deterministic evaluation and output generation (evaluate_sequence.evaluate_rules)
        stage_start = time.perf_counter()
        from evaluate_sequence import evaluate_rules
        evaluate_rules(artifacts, positives, output_dir)

        execution["stages"]["evaluate_rules"] = {
            "seconds": time.perf_counter() - stage_start,
            "peak_working_set_bytes": _peak_working_set(),
        }

        # Finalize execution receipt
        expected_outputs = (
            "predictions.csv",
            "pool_manifest.csv",
            "candidate_ledger.parquet",
            "stage_counts.csv",
            "stage_event_coverage.csv",
            "event_results.csv",
            "metrics.json",
            "diagnostics.json",
        )
        execution["outputs"] = {
            name: {"sha256": _sha256(output_dir / name), "bytes": (output_dir / name).stat().st_size}
            for name in expected_outputs
            if (output_dir / name).is_file()
        }
        execution.update(
            status="complete",
            exit_code=0,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            elapsed_seconds=time.perf_counter() - started,
            peak_working_set_bytes=_peak_working_set(),
        )
        _write_json_atomic(receipt_path, execution)
        print(f"Run completed successfully in {execution['elapsed_seconds']:.2f}s; receipt written to {receipt_path}")
        return 0

    except Exception as exc:
        execution.update(
            status="failed",
            exit_code=1,
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(),
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            elapsed_seconds=time.perf_counter() - started,
            peak_working_set_bytes=_peak_working_set(),
        )
        _write_json_atomic(receipt_path, execution)
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "execution_001")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    return run(args.output_dir, args.root)


if __name__ == "__main__":
    raise SystemExit(main())
