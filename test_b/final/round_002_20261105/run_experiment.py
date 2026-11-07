"""Run the Round 2 exploratory dev evaluation.

This command is intentionally not invoked during implementation checks. The
coordinator should launch it once after context_features.py is present.
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
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
EXPECTED_PEAK = 768 * 2**20
RESERVE = 640 * 2**20


def _available_memory() -> tuple[int, int]:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        s = MEMORYSTATUSEX(); s.dwLength = ctypes.sizeof(s)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            raise OSError("GlobalMemoryStatusEx failed; cannot verify available RAM")
        return int(s.ullAvailPhys), int(s.ullTotalPhys)
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) * 1024
    return info["MemAvailable"], info["MemTotal"]


def _processes() -> list[dict]:
    try:
        import psutil
        out = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                out.append({"pid": p.info["pid"], "name": p.info["name"],
                            "rss_bytes": p.info["memory_info"].rss})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(out, key=lambda x: x["rss_bytes"], reverse=True)[:15]
    except ImportError:
        if os.name == "nt":
            cmd = "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Id,ProcessName,WorkingSet64 | ConvertTo-Json -Compress"
            try:
                r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                                   text=True, timeout=20, check=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                data = json.loads(r.stdout); data = [data] if isinstance(data, dict) else data
                return [{"pid": x["Id"], "name": x["ProcessName"], "rss_bytes": x["WorkingSet64"]} for x in data]
            except Exception as exc:
                return [{"inventory_error": str(exc)}]
        return []


def _peak_working_set() -> int | None:
    try:
        import psutil
        info = psutil.Process().memory_info()
        return int(getattr(info, "peak_wset", getattr(info, "rss", 0)))
    except Exception:
        if os.name == "nt":
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            c = PROCESS_MEMORY_COUNTERS(); c.cb = ctypes.sizeof(c)
            try:
                ok = ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                               ctypes.byref(c), c.cb)
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


def _write(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _copy_input_diagnostics(source: Path, output_dir: Path) -> Path:
    target = Path(output_dir) / "input_diagnostics.json"
    if Path(source).resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def _persist_featured_rows(featured, output_dir: Path) -> dict:
    path = Path(output_dir) / "featured_rows.parquet"
    featured.to_parquet(path, engine="pyarrow", index=False)
    return {"path": str(path.resolve()), "sha256": _sha256(path), "bytes": path.stat().st_size}


def run(output_dir: Path = HERE, root: Path = ROOT) -> int:
    output_dir = Path(output_dir).resolve()
    root = Path(root).resolve()
    if output_dir != HERE and HERE not in output_dir.parents:
        raise ValueError("Run outputs must stay inside this round folder")
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "EXECUTION.json"
    execution = {"status": "starting", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "root": str(root), "output_dir": str(output_dir), "python": sys.version,
                 "platform": platform.platform(), "command": sys.argv,
                 "memory_requirement_bytes": EXPECTED_PEAK + RESERVE,
                 "estimated_extra_peak_bytes": EXPECTED_PEAK, "reserve_bytes": RESERVE,
                 "stages": {}, "other_processes": []}
    started = time.perf_counter()
    try:
        # Process inventory precedes the freshest available-RAM query.
        execution["other_processes"] = [p for p in _processes() if p.get("pid") != os.getpid()]
        available, total = _available_memory()
        execution["ram_preflight"] = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                       "available_bytes": available, "total_bytes": total,
                                       "allowed": available >= EXPECTED_PEAK + RESERVE,
                                       "simultaneous_dataset_jobs_authorized": False}
        execution["peak_working_set_bytes"] = _peak_working_set()
        if not execution["ram_preflight"]["allowed"]:
            execution.update(status="memory_deferred", finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                             elapsed_seconds=time.perf_counter() - started,
                             error="Available RAM below 768 MiB estimated peak plus 640 MiB reserve; no data loaded.")
            _write(receipt_path, execution)
            return 75

        # Resolve the archived inputs without scanning/reading their contents.
        matches = sorted((root / "testB").glob("*/round_008_linkage_audit_20261105"))
        if len(matches) != 1:
            raise FileNotFoundError(f"Expected one archived round_008 input directory, found {len(matches)}")
        input_dir = matches[0]
        input_paths = [input_dir / "dev_hourly_scores.parquet", input_dir / "additional_hourly_scores.parquet",
                       input_dir / "devset_positives.csv"]
        source_paths = [HERE / "data_eval.py", HERE / "run_experiment.py", HERE / "PROTOCOL.md", HERE / "CONTRACT.md",
                        HERE / "context_features.py"]
        missing = [str(p) for p in source_paths if not p.exists()]
        if missing:
            raise FileNotFoundError("Required source files unavailable: " + ", ".join(missing))
        execution["inputs"] = {p.name: {"path": str(p), "sha256": _sha256(p), "bytes": p.stat().st_size}
                               for p in input_paths}
        execution["sources"] = {p.name: {"path": str(p), "sha256": _sha256(p)} for p in source_paths}
        execution["versions"] = {"numpy": _version("numpy"), "pandas": _version("pandas"),
                                 "pyarrow": _version("pyarrow"), "psutil": _version("psutil")}
        _write(receipt_path, execution)

        from data_eval import evaluate, load_dev
        stage = time.perf_counter()
        frame, positives = load_dev(root)
        diagnostics_source = HERE / "input_diagnostics.json"
        _copy_input_diagnostics(diagnostics_source, output_dir)
        execution["stages"]["data_read_and_canonicalize"] = {"seconds": time.perf_counter() - stage,
                                                               "rows": int(len(frame)),
                                                               "peak_working_set_bytes": _peak_working_set()}
        _write(receipt_path, execution)

        stage = time.perf_counter()
        # Contract API: returns the same rows/order/index plus U/C/history features.
        from context_features import compute_features
        featured = compute_features(frame)
        if len(featured) != len(frame) or not featured.index.equals(frame.index):
            raise ValueError("context_features.compute_features changed row count/index ordering")
        execution["stages"]["feature_computation"] = {"seconds": time.perf_counter() - stage,
                                                       "rows": int(len(featured)),
                                                       "peak_working_set_bytes": _peak_working_set()}
        _write(receipt_path, execution)

        stage = time.perf_counter()
        featured_record = _persist_featured_rows(featured, output_dir)
        execution["stages"]["featured_rows_persistence"] = {"seconds": time.perf_counter() - stage,
                                                             "rows": int(len(featured)),
                                                             "peak_working_set_bytes": _peak_working_set()}
        execution["featured_rows_parquet"] = featured_record
        _write(receipt_path, execution)

        stage = time.perf_counter()
        evaluate(featured, positives, output_dir)
        execution["stages"]["evaluation_and_outputs"] = {"seconds": time.perf_counter() - stage,
                                                           "peak_working_set_bytes": _peak_working_set()}
        execution.update(status="complete", exit_code=0)
        expected_outputs = ("predictions.csv", "event_results.csv", "metrics.json", "diagnostics.json",
                            "input_diagnostics.json", "featured_rows.parquet")
        execution["outputs"] = {name: {"sha256": _sha256(output_dir / name), "bytes": (output_dir / name).stat().st_size}
                                for name in expected_outputs if (output_dir / name).is_file()}
        execution["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        execution["elapsed_seconds"] = time.perf_counter() - started
        execution["peak_working_set_bytes"] = _peak_working_set()
        _write(receipt_path, execution)
        return 0
    except Exception as exc:
        execution.update(status="failed", exit_code=1, error=f"{type(exc).__name__}: {exc}",
                         traceback=traceback.format_exc(), finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         elapsed_seconds=time.perf_counter() - started,
                         peak_working_set_bytes=_peak_working_set())
        _write(receipt_path, execution)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    return run(args.output_dir, args.root)


if __name__ == "__main__":
    raise SystemExit(main())
