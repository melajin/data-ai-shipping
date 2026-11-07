"""Round 8 execution runner: shape-history candidate rules and event evaluation.

This runner executes the integrated pipeline. It performs memory preflight checks before data loading,
prevents overwrite of complete receipts, validates receipts from upstream extraction, and records
peak working set and file hashes.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
LUNA_EXTRACT_MIB = 768
SONNET_REVIEW_MIB = 512
RESERVE_MIB = 640
EXPECTED_PEAK = (LUNA_EXTRACT_MIB + SONNET_REVIEW_MIB) * 1024 * 1024
RESERVE = RESERVE_MIB * 1024 * 1024
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


def validate_extractor_receipt(geom_dir: Path | str, expected_rows: int = 99677) -> dict[str, Any]:
    """Validate extractor receipt, output manifest, and geometry ledger parquet hash per contract.

    Requires explicit zero mismatch and error counts, matching row counts, release_ready_for_scoring True,
    and verified SHA-256 match against output_manifest.json. Absent fields are strictly rejected.
    """
    geom_dir = Path(geom_dir).resolve()
    receipt_file = geom_dir / "runtime_receipt.json"
    if not receipt_file.exists():
        raise FileNotFoundError(f"Missing extraction runtime receipt: {receipt_file}")

    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Corrupt runtime receipt {receipt_file}: {exc}") from exc

    # Require explicit fields and exact values - no absent-field-as-success
    required_keys = [
        "status",
        "mismatch_count",
        "error_count",
        "rows_written",
        "canonical_rows_expected",
        "release_ready_for_scoring",
    ]
    missing = [k for k in required_keys if k not in receipt]
    if missing:
        raise ValueError(f"Extractor receipt missing required fields: {missing}")

    if receipt["status"] != "complete":
        raise ValueError(f"Extractor receipt status is '{receipt['status']}', expected 'complete'")
    if receipt["mismatch_count"] != 0:
        raise ValueError(f"Extractor receipt mismatch_count is {receipt['mismatch_count']}, expected 0")
    if receipt["error_count"] != 0:
        raise ValueError(f"Extractor receipt error_count is {receipt['error_count']}, expected 0")
    if receipt["rows_written"] != expected_rows:
        raise ValueError(f"Extractor rows_written is {receipt['rows_written']}, expected {expected_rows}")
    if receipt["canonical_rows_expected"] != expected_rows:
        raise ValueError(f"Extractor canonical_rows_expected is {receipt['canonical_rows_expected']}, expected {expected_rows}")
    if receipt["release_ready_for_scoring"] is not True:
        raise ValueError("Extractor release_ready_for_scoring is not True")

    # Validate output manifest and geometry_ledger.parquet hash
    manifest_file = geom_dir / "output_manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Missing extraction output manifest: {manifest_file}")

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Corrupt output manifest {manifest_file}: {exc}") from exc

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or "geometry_ledger.parquet" not in outputs:
        raise ValueError("Output manifest does not contain 'geometry_ledger.parquet' output entry")

    manifest_sha256 = outputs["geometry_ledger.parquet"].get("sha256")
    if not manifest_sha256:
        raise ValueError("Output manifest missing sha256 for geometry_ledger.parquet")

    geom_parquet = geom_dir / "geometry_ledger.parquet"
    if not geom_parquet.exists():
        raise FileNotFoundError(f"Missing {geom_parquet}")

    actual_sha256 = _sha256(geom_parquet)
    if actual_sha256 != manifest_sha256:
        raise ValueError(
            f"geometry_ledger.parquet hash mismatch: manifest={manifest_sha256}, actual={actual_sha256}"
        )

    return receipt


def validate_raw_keys(df: Any, name: str = "frame") -> Any:
    """Validate original raw key columns before any lossy integer conversion.

    Checks rfid_id, ts, and source_ordinal on raw uncasted columns:
    - ts and source_ordinal must be non-boolean, numeric, finite, non-negative, and exact integers (no fractional parts).
    - ts must be within reasonable epoch-hour range (rejecting nanosecond-scaled timestamps).
    - source_ordinal must be unique, and (rfid_id, ts) pairs must be unique.
    Returns DataFrame with strictly validated int64 ts and source_ordinal, and string rfid_id.
    """
    import pandas as pd

    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")

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
    # Reject nanosecond-scaled timestamps (e.g. > 10,000,000 hours ~ year 3110)
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


def validate_and_merge_geometry(
    canonical_frame: Any,
    geom_df: Any,
    tolerances: dict[str, float] | None = None,
) -> Any:
    """Verify exact keyset, uniqueness, numeric agreement, and merge geometry fields preserving canonical order.

    Ensures no duplicate keys exist, shared numeric fields agree within tolerances (explicitly comparing missingness
    and finite/infinite states without skipping NaNs), timestamps are non-fractional integer hours, and extractor
    duplicate columns are not suffixed (_x/_y) during merge.
    """
    import pandas as pd

    if tolerances is None:
        tolerances = {
            "len_m": 1e-4,
            "bbox_m": 1e-4,
            "cen_lon": 1e-7,
            "cen_lat": 1e-7,
            "score": 1e-6,
        }

    # 1. Key uniqueness and integer timestamp validation on raw columns
    canonical_frame = validate_raw_keys(canonical_frame, name="canonical")
    geom_df = validate_raw_keys(geom_df, name="geometry")

    # 2. Keyset exact match
    if len(canonical_frame) != len(geom_df):
        raise ValueError(f"Row count mismatch: canonical={len(canonical_frame)}, geometry={len(geom_df)}")
    if set(canonical_frame["source_ordinal"]) != set(geom_df["source_ordinal"]):
        raise ValueError("Keyset mismatch: source_ordinal sets do not match")
    canon_keys = set(zip(canonical_frame["rfid_id"].astype(str), canonical_frame["ts"].astype("int64")))
    geom_keys = set(zip(geom_df["rfid_id"].astype(str), geom_df["ts"].astype("int64")))
    if canon_keys != geom_keys:
        raise ValueError("Keyset mismatch: (rfid_id, ts) sets do not match")

    # 3. Numeric column agreement on shared columns: compare missingness and finite/infinite states explicitly
    shared_numeric = [col for col in tolerances if col in canonical_frame.columns and col in geom_df.columns]
    if shared_numeric:
        canon_aligned = canonical_frame.sort_values("source_ordinal").reset_index(drop=True)
        geom_aligned = geom_df.sort_values("source_ordinal").reset_index(drop=True)
        for col in shared_numeric:
            c_s = canon_aligned[col]
            g_s = geom_aligned[col]

            c_missing = c_s.isna().to_numpy()
            g_missing = g_s.isna().to_numpy()

            # One-sided missingness mismatch: if one is NaN and the other is not, fail!
            mismatch_missing = c_missing != g_missing
            if mismatch_missing.any():
                n_mismatch = int(mismatch_missing.sum())
                raise ValueError(
                    f"Shared column '{col}' has {n_mismatch} rows with missingness mismatch (one-sided NaN/null)"
                )

            # Compare non-missing entries
            both_present = ~c_missing
            if both_present.any():
                c_pres = c_s[both_present].to_numpy(dtype=float)
                g_pres = g_s[both_present].to_numpy(dtype=float)

                c_fin = np.isfinite(c_pres)
                g_fin = np.isfinite(g_pres)

                if (c_fin != g_fin).any():
                    raise ValueError(f"Shared column '{col}' has finite vs infinite state mismatch")

                both_inf = ~c_fin
                if both_inf.any():
                    if not np.array_equal(c_pres[both_inf], g_pres[both_inf]):
                        raise ValueError(f"Shared column '{col}' has +/- infinity sign mismatch")

                both_finite = c_fin
                if both_finite.any():
                    c_vals = c_pres[both_finite]
                    g_vals = g_pres[both_finite]
                    diff = np.abs(c_vals - g_vals)
                    max_diff = float(np.max(diff))
                    tol = tolerances[col]
                    if max_diff > tol:
                        raise ValueError(
                            f"Shared column '{col}' discrepancy ({max_diff:.8f}) exceeds tolerance ({tol})"
                        )

    # 4. Merge non-duplicate geometry lineage fields
    # Exclude shared numeric columns from geom_df to prevent pandas _x, _y suffixes
    cols_to_exclude = set(shared_numeric)
    geom_cols_to_merge = [c for c in geom_df.columns if c not in cols_to_exclude]

    merged = pd.merge(
        canonical_frame,
        geom_df[geom_cols_to_merge],
        on=["rfid_id", "ts", "source_ordinal"],
        how="inner",
        validate="one_to_one",
        indicator=True,
    )
    if not (merged["_merge"] == "both").all():
        raise ValueError("Failed one_to_one merge between canonical and geometry frames")
    merged = merged.drop(columns=["_merge"])

    # 5. Verify row count and canonical order preservation
    if len(merged) != len(canonical_frame):
        raise ValueError(f"Merged row count ({len(merged)}) != canonical ({len(canonical_frame)})")
    if not (merged["source_ordinal"].to_numpy() == canonical_frame["source_ordinal"].to_numpy()).all():
        raise ValueError("Merge did not preserve original canonical order")

    # 6. Verify required columns exist unsuffixed
    for col in ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "score"]:
        if col not in merged.columns:
            raise ValueError(f"Required column '{col}' missing in merged frame")
        if f"{col}_x" in merged.columns or f"{col}_y" in merged.columns:
            raise ValueError(f"Column '{col}' was unexpectedly suffixed (_x/_y) during merge")

    return merged


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run(
    output_dir: Path | str = HERE / "execution_001",
    geometry_dir: Path | str | None = None,
    root: Path | str = ROOT,
    synthetic: bool = False,
) -> int:
    output_dir = Path(output_dir).resolve()
    root = Path(root).resolve()

    # Enforce round isolation: output must reside inside this round folder
    if output_dir != HERE and HERE not in output_dir.parents:
        raise ValueError(f"Run outputs must stay inside this round folder: {HERE}")

    # Strict fresh directory: refuse ANY existing output directory containing files per contract
    if output_dir.exists() and (output_dir.is_file() or any(output_dir.iterdir())):
        print(
            f"Refusing execution: output directory '{output_dir}' already exists and contains files. "
            "Per CONTRACT, runner requires a strict fresh output directory to preserve prior evidence.",
            file=sys.stderr,
        )
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "EXECUTION.json"

    execution: dict[str, Any] = {
        "status": "starting",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "output_dir": str(output_dir),
        "synthetic_mode": synthetic,
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
                error=f"Available RAM ({available / (1024**2):.1f} MiB) below {EXPECTED_PEAK / (1024**2):.0f} MiB estimated peak plus {RESERVE / (1024**2):.0f} MiB reserve; no data loaded.",
            )
            _write_json_atomic(receipt_path, execution)
            print(f"RAM preflight deferred: available {available / (1024**2):.1f} MiB < required {TOTAL_MEMORY_REQUIRED / (1024**2):.1f} MiB")
            return 75

        # Record source paths including invoked shape_rules, numerical helpers, and receipts
        source_paths = [
            HERE / "evaluate_shape.py",
            HERE / "run_shape.py",
            HERE / "check_shape_eval.py",
            HERE / "shape_rules.py",
            root / "testB" / "final" / "round_002_20261105" / "data_eval.py",
            HERE / "PROTOCOL.md",
            HERE / "CONTRACT.md",
        ]
        if geometry_dir is not None:
            geom_d = Path(geometry_dir).resolve()
            source_paths.extend([
                geom_d / "runtime_receipt.json",
                geom_d / "output_manifest.json",
                geom_d / "geometry_ledger.parquet",
            ])
        execution["sources"] = {
            p.name: {"path": str(p), "sha256": _sha256(p) if p.exists() else None}
            for p in source_paths
        }
        execution["versions"] = {
            "numpy": _version("numpy"),
            "pandas": _version("pandas"),
            "pyarrow": _version("pyarrow"),
            "psutil": _version("psutil"),
        }
        _write_json_atomic(receipt_path, execution)

        if synthetic:
            print("Executing in SYNTHETIC test mode...")
            from check_shape_eval import build_comprehensive_synthetic_fixture
            fixture = build_comprehensive_synthetic_fixture()
            artifacts = fixture["artifacts"]
            positives = fixture["positives"]

            # Persist pre-label artifacts before positives are read
            persist_start = time.perf_counter()
            artifacts["predictions"].to_csv(output_dir / "predictions.csv", index=False)
            artifacts["pool_manifest"].to_csv(output_dir / "pool_manifest.csv", index=False)
            artifacts["ledger"].to_parquet(output_dir / "candidate_ledger.parquet", engine="pyarrow", index=False)

            pred_hash = _sha256(output_dir / "predictions.csv")
            manifest_hash = _sha256(output_dir / "pool_manifest.csv")
            execution["frozen_predictions"] = {
                "path": str(output_dir / "predictions.csv"),
                "sha256": pred_hash,
                "bytes": (output_dir / "predictions.csv").stat().st_size,
                "persisted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "seconds": time.perf_counter() - persist_start,
                "verified_prior_to_label_parse": True,
            }
            execution["frozen_pool_manifest"] = {
                "path": str(output_dir / "pool_manifest.csv"),
                "sha256": manifest_hash,
                "bytes": (output_dir / "pool_manifest.csv").stat().st_size,
            }

            from evaluate_shape import evaluate_shape
            eval_res = evaluate_shape(artifacts, positives, output_dir)

            # Verify frozen predictions and pool manifest hashes remain byte-identical
            post_eval_pred_hash = _sha256(output_dir / "predictions.csv")
            post_eval_manifest_hash = _sha256(output_dir / "pool_manifest.csv")
            if post_eval_pred_hash != pred_hash:
                raise RuntimeError(
                    f"Frozen predictions.csv was mutated during evaluate_shape! "
                    f"pre={pred_hash}, post={post_eval_pred_hash}"
                )
            if post_eval_manifest_hash != manifest_hash:
                raise RuntimeError(
                    f"Frozen pool_manifest.csv was mutated during evaluate_shape! "
                    f"pre={manifest_hash}, post={post_eval_manifest_hash}"
                )
            execution["frozen_verification_post_eval"] = {
                "predictions_hash_unchanged": True,
                "pool_manifest_hash_unchanged": True,
                "pre_pred_sha256": pred_hash,
                "post_pred_sha256": post_eval_pred_hash,
                "pre_manifest_sha256": manifest_hash,
                "post_manifest_sha256": post_eval_manifest_hash,
                "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }

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
                if (output_dir / name).exists()
            }
            execution.update(
                status="complete",
                exit_code=0,
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                elapsed_seconds=time.perf_counter() - started,
                peak_working_set_bytes=_peak_working_set(),
            )
            _write_json_atomic(receipt_path, execution)
            print("Synthetic execution completed successfully.")
            return 0

        # Non-synthetic (actual data) mode: requires geometry_dir and root release
        if geometry_dir is None:
            raise ValueError(
                "Actual data run requires explicit --geometry-dir. "
                "Per CONTRACT, actual data execution is held until root release."
            )

        geom_dir = Path(geometry_dir).resolve()
        if geom_dir != HERE and HERE not in geom_dir.parents:
            raise ValueError(f"Geometry directory must reside inside this round folder: {HERE}")

        # Validate extraction receipt and output manifest
        receipt_data = validate_extractor_receipt(geom_dir, expected_rows=99677)
        geom_parquet = geom_dir / "geometry_ledger.parquet"

        # Upstream canonical input paths
        parquet_path = root / "testB" / "final" / "round_004_20261105" / "execution_001" / "candidate_ledger.parquet"
        gear_path = root / "testB" / "final" / "round_003_20261105" / "gear_registry.csv"
        r2_helper_path = root / "testB" / "final" / "round_002_20261105" / "data_eval.py"

        positives_matches = sorted((root / "testB").glob("*/round_008_linkage_audit_20261105/devset_positives.csv"))
        if len(positives_matches) != 1:
            raise FileNotFoundError(f"Expected exactly 1 devset_positives.csv match, found {len(positives_matches)}")
        positives_path = positives_matches[0]

        input_paths = [parquet_path, gear_path, positives_path, r2_helper_path, geom_parquet]
        missing_inputs = [str(p) for p in input_paths if not p.exists()]
        if missing_inputs:
            raise FileNotFoundError(f"Missing required input files: {missing_inputs}")

        execution["inputs"] = {
            p.name: {"path": str(p), "sha256": _sha256(p), "bytes": p.stat().st_size}
            for p in input_paths
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 1: Load canonical numeric and geometry ledgers
        stage_start = time.perf_counter()
        import pandas as pd
        import pyarrow.parquet as pq

        canonical_cols = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
        frame = pq.read_table(parquet_path, columns=canonical_cols).to_pandas()
        assert len(frame) == 99677, f"Expected 99,677 canonical rows, got {len(frame)}"
        assert frame["rfid_id"].nunique() == 82, f"Expected 82 distinct RFIDs, got {frame['rfid_id'].nunique()}"

        # Read geometry ledger
        geom_df = pq.read_table(geom_parquet).to_pandas()
        assert len(geom_df) == 99677, f"Expected 99,677 geometry rows, got {len(geom_df)}"

        # Validate original raw keys before any lossy cast and merge frames
        frame = validate_raw_keys(frame, name="canonical")
        geom_df = validate_raw_keys(geom_df, name="geometry")
        merged = validate_and_merge_geometry(frame, geom_df)

        gear_registry = pd.read_csv(gear_path, usecols=["rfid_id", "primary_gear", "is_single_code"], encoding="utf-8-sig")
        gear_registry["rfid_id"] = gear_registry["rfid_id"].astype(str)

        execution["stages"]["data_read"] = {
            "seconds": time.perf_counter() - stage_start,
            "rows_canonical": len(frame),
            "rows_geometry": len(geom_df),
            "peak_working_set_bytes": _peak_working_set(),
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 2: Build shape rules (NO POSITIVES READ)
        stage_start = time.perf_counter()
        try:
            from shape_rules import build_shape_rules
        except ImportError as err:
            raise ImportError("shape_rules module not available. Luna's implementation pending.") from err

        artifacts = build_shape_rules(merged, gear_registry)
        artifacts["gear_registry"] = gear_registry

        execution["stages"]["build_rules"] = {
            "seconds": time.perf_counter() - stage_start,
            "ledger_rows": int(len(artifacts["ledger"])),
            "prediction_rows": int(len(artifacts["predictions"])),
            "pool_manifest_rows": int(len(artifacts["pool_manifest"])),
            "peak_working_set_bytes": _peak_working_set(),
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 2.5: Persist pre-label artifacts before positives are read
        persist_start = time.perf_counter()
        artifacts["predictions"].to_csv(output_dir / "predictions.csv", index=False)
        artifacts["pool_manifest"].to_csv(output_dir / "pool_manifest.csv", index=False)
        artifacts["ledger"].to_parquet(output_dir / "candidate_ledger.parquet", engine="pyarrow", index=False)

        pred_hash = _sha256(output_dir / "predictions.csv")
        manifest_hash = _sha256(output_dir / "pool_manifest.csv")
        execution["frozen_predictions"] = {
            "path": str(output_dir / "predictions.csv"),
            "sha256": pred_hash,
            "bytes": (output_dir / "predictions.csv").stat().st_size,
            "persisted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "seconds": time.perf_counter() - persist_start,
            "verified_prior_to_label_parse": True,
        }
        execution["frozen_pool_manifest"] = {
            "path": str(output_dir / "pool_manifest.csv"),
            "sha256": manifest_hash,
            "bytes": (output_dir / "pool_manifest.csv").stat().st_size,
        }
        _write_json_atomic(receipt_path, execution)

        # Stage 3: Parse positive incident labels ONLY AFTER predictions are frozen
        stage_start = time.perf_counter()
        positives = pd.read_csv(positives_path, usecols=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"], encoding="utf-8-sig")
        positives["rfid_id"] = positives["rfid_id"].astype(str)
        positives["acc_id"] = positives["acc_id"].astype(str)
        positives["tier"] = pd.to_numeric(positives["tier"], errors="raise").astype(int)
        positives["acc_ts"] = pd.to_numeric(positives["acc_ts"], errors="raise").astype("int64")

        # Full cohorts assertion
        assert len(positives) == 100, f"Expected 100 total positive events, got {len(positives)}"
        assert positives["rfid_id"].nunique() == 82, f"Expected 82 distinct RFIDs in positives, got {positives['rfid_id'].nunique()}"
        tier01 = positives[positives["tier"] <= 1]
        assert len(tier01) == 60, f"Expected 60 Tier01 events, got {len(tier01)}"
        assert tier01["rfid_id"].nunique() == 55, f"Expected 55 distinct RFIDs in Tier01, got {tier01['rfid_id'].nunique()}"

        from evaluate_shape import evaluate_shape
        eval_res = evaluate_shape(artifacts, positives, output_dir)

        # Verify frozen predictions and pool manifest are byte-identical after evaluate_shape
        post_eval_pred_hash = _sha256(output_dir / "predictions.csv")
        post_eval_manifest_hash = _sha256(output_dir / "pool_manifest.csv")

        if post_eval_pred_hash != pred_hash:
            raise RuntimeError(
                f"Frozen predictions.csv was mutated during evaluate_shape! "
                f"pre={pred_hash}, post={post_eval_pred_hash}"
            )
        if post_eval_manifest_hash != manifest_hash:
            raise RuntimeError(
                f"Frozen pool_manifest.csv was mutated during evaluate_shape! "
                f"pre={manifest_hash}, post={post_eval_manifest_hash}"
            )

        execution["frozen_verification_post_eval"] = {
            "predictions_hash_unchanged": True,
            "pool_manifest_hash_unchanged": True,
            "pre_pred_sha256": pred_hash,
            "post_pred_sha256": post_eval_pred_hash,
            "pre_manifest_sha256": manifest_hash,
            "post_manifest_sha256": post_eval_manifest_hash,
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }

        execution["stages"]["evaluate_shape"] = {
            "seconds": time.perf_counter() - stage_start,
            "rows_positives": int(len(positives)),
            "gate_overall_passed": eval_res["metrics"]["operational_gate"]["overall_passed"],
            "peak_working_set_bytes": _peak_working_set(),
        }

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
            if (output_dir / name).exists()
        }
        execution.update(
            status="complete",
            exit_code=0,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            elapsed_seconds=time.perf_counter() - started,
            peak_working_set_bytes=_peak_working_set(),
        )
        _write_json_atomic(receipt_path, execution)
        print("Execution completed successfully.")
        return 0

    except Exception as exc:
        execution.update(
            status="failed",
            exit_code=1,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            elapsed_seconds=time.perf_counter() - started,
            error=str(exc),
            traceback=traceback.format_exc(),
            peak_working_set_bytes=_peak_working_set(),
        )
        _write_json_atomic(receipt_path, execution)
        print(f"Runner failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Round 8 shape evaluation runner")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--geometry-dir", type=str, default=None, help="Input geometry directory")
    parser.add_argument("--root", type=str, default=str(ROOT), help="Workspace root")
    parser.add_argument("--synthetic", action="store_true", help="Run with synthetic test data")
    args = parser.parse_args()

    default_out = (HERE / "synthetic_execution") if args.synthetic else (HERE / "execution_001")
    target_out = Path(args.output_dir) if args.output_dir else default_out

    sys.exit(run(output_dir=target_out, geometry_dir=args.geometry_dir, root=args.root, synthetic=args.synthetic))
