"""Unlabeled, restartable fleet scoring with the unchanged portable baseline.

Only six approved hourly summaries and the frozen portable references are read.
Partitioning changes data loading only; each complete vessel is scored in order.
Centroid radius is a summary-location statistic, never GPS motion or speed.
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib
import json
import math
import os
import sys
import time
import traceback
import zlib
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
import psutil

ROUND_DIR = Path(__file__).resolve().parent
ROOT = ROUND_DIR.parents[2]
FROZEN = ROOT / "deliverables/testb_system_20261106/src/frozen_baseline.py"
REFERENCES = ROOT / "deliverables/testb_system_20261106/references"
DEFAULT_HOURLY = ROOT / "testB/final/round_017_fleet_negatives_20261106/execution_001"
COLS = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "n_coords"]
OUTPUT_COLS = ["rfid_id", "n_rows", "peak_score", "peak_ts", "peak_state",
               "median_score", "p95_score", "n_unique_hours", "gap_total_h",
               "activity_radius_km", "n_finite_scores"]
START_H = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() // 3600)
END_H = int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp() // 3600)
MIB = 1024 ** 2


def now():
    return datetime.now(timezone.utc).astimezone().isoformat()


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprints(paths):
    return {str(path.resolve()): {"sha256": sha256(path), "bytes": path.stat().st_size}
            for path in paths}


def load_stack():
    global np, pd, pa, pq
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    # Bound Arrow's I/O/CPU pools even if a local environment has large defaults.
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)


class MemoryPause(RuntimeError):
    pass


class Run:
    def __init__(self, out):
        self.out = out
        self.process = psutil.Process()
        self.started = time.perf_counter()
        self.peak_rss = self.process.memory_info().rss
        self.meta = {"status": "running", "started_at": now(), "pid": os.getpid(),
                     "training_performed": False, "labels_read": False,
                     "scorer_path": str(FROZEN), "references_path": str(REFERENCES),
                     "score_definition_changed": False,
                     "expected_peak_process_mib": 1024, "reserve_mib": 640,
                     "memory_estimate_basis": "64K Arrow batches, 128 disk partitions, one pandas partition and one vessel at a time; 62 MiB frozen normalizer arrays plus sorting/copies; conservative 1 GiB process peak",
                     "timestamp_contract": {"unit": "epoch hours", "start_inclusive": START_H,
                                            "end_exclusive": END_H, "period": "2026 Jan-Jun"},
                     "tie_break": "score DESC, source_ordinal ASC, stable",
                     "centroid_radius_interpretation": "max distance from median summary centroid; not actual GPS, heading, or speed"}

    def event(self, kind, **values):
        item = {"at": now(), "event": kind, **values}
        with (self.out / "score_progress.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps(item, ensure_ascii=False, allow_nan=False), flush=True)

    def save(self, **values):
        self.meta.update(values)
        self.meta["updated_at"] = now()
        self.meta["elapsed_seconds"] = round(time.perf_counter() - self.started, 3)
        self.sample_peak()
        self.meta["observed_peak_process_mib"] = round(self.peak_rss / MIB, 3)
        atomic_json(self.out / "score_metadata.json", self.meta)

    def sample_peak(self):
        info = self.process.memory_info()
        self.peak_rss = max(self.peak_rss, info.rss, getattr(info, "peak_wset", 0))
        return info.rss

    def preflight(self, stage):
        rss = self.sample_peak()
        available = psutil.virtual_memory().available
        additional = max(0, 1024 * MIB - rss)
        others = []
        for process in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                data = process.info
                if data["pid"] != os.getpid() and data["memory_info"] is not None:
                    others.append({"pid": data["pid"], "name": data["name"],
                                   "rss_mib": round(data["memory_info"].rss / MIB, 2)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        others.sort(key=lambda entry: entry["rss_mib"], reverse=True)
        passed = available >= additional + 640 * MIB
        item = {"stage": stage, "available_mib": round(available / MIB, 2),
                "process_rss_mib": round(rss / MIB, 2),
                "expected_peak_process_mib": 1024,
                "expected_additional_mib": round(additional / MIB, 2),
                "reserve_mib": 640, "passed": passed, "other_processes": others[:8]}
        self.event("memory_preflight", **item)
        self.meta["last_memory_preflight"] = {"at": now(), **item}
        if not passed:
            raise MemoryPause(f"Insufficient RAM before {stage}; stage deferred, no RAM polling loop")


def validate_batch(table, source):
    if table.column_names != COLS:
        raise ValueError(f"Unexpected source columns: {source}: {table.column_names}")
    for name in ("rfid_id", "ts", "source_ordinal"):
        if table[name].null_count:
            raise ValueError(f"Missing required {name}: {source}")
    if not pa.types.is_integer(table.schema.field("ts").type):
        raise ValueError(f"Timestamp must be integer epoch hours: {source}")
    ts = table["ts"].to_numpy(zero_copy_only=False)
    if len(ts) and (int(ts.min()) < START_H or int(ts.max()) >= END_H):
        raise ValueError(f"Timestamp outside approved 2026 Jan-Jun: {source}")


def stage_inputs(run, files, before, partition_count=128, batch_size=65536):
    manifest_path = run.out / "staging_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["source_fingerprints"] != before:
            raise ValueError("Existing staging source fingerprints differ")
        run.preflight("validate_existing_staging")
        for item in manifest["partitions"]:
            path = run.out / item["path"]
            if not path.is_file() or sha256(path) != item["sha256"]:
                raise ValueError(f"Staging hash mismatch: {path}")
        run.event("staging_reused", rows=manifest["rows"], vessels=manifest["vessels"])
        return manifest

    run.preflight("stream_inputs_to_partitions")
    stage_dir = run.out / "staging" / f"attempt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    stage_dir.mkdir(parents=True)
    writers = {}
    paths = {}
    rows_by_partition = [0] * partition_count
    rows = 0
    vessels = set()
    invalid_centroid_rows = 0
    min_ts, max_ts = END_H, START_H
    try:
        for source in files:
            pf = pq.ParquetFile(source)
            source_rows = 0
            for batch in pf.iter_batches(batch_size=batch_size, columns=COLS, use_threads=False):
                table = pa.Table.from_batches([batch])
                validate_batch(table, source)
                lon = table["cen_lon"].to_numpy(zero_copy_only=False)
                lat = table["cen_lat"].to_numpy(zero_copy_only=False)
                invalid_centroid_rows += int(np.count_nonzero(~(np.isfinite(lon) & np.isfinite(lat))))
                ids = table["rfid_id"].to_pylist()
                vessels.update(ids)
                keys = np.fromiter((zlib.crc32(value.encode("utf-8")) % partition_count
                                    for value in ids), dtype=np.int32, count=len(ids))
                timestamps = table["ts"].to_numpy(zero_copy_only=False)
                min_ts = min(min_ts, int(timestamps.min()))
                max_ts = max(max_ts, int(timestamps.max()))
                for key in np.unique(keys):
                    key = int(key)
                    selected = table.take(pa.array(np.flatnonzero(keys == key)))
                    if key not in writers:
                        path = stage_dir / f"part_{key:03d}.parquet"
                        paths[key] = path
                        writers[key] = pq.ParquetWriter(path, selected.schema, compression="snappy",
                                                        use_dictionary=["rfid_id"])
                    writers[key].write_table(selected)
                    rows_by_partition[key] += len(selected)
                rows += len(table)
                source_rows += len(table)
                run.sample_peak()
            if source_rows != pf.metadata.num_rows:
                raise AssertionError(f"Source row count mismatch: {source}")
            run.event("source_partitioned", file=source.name, rows=source_rows,
                      cumulative_rows=rows, cumulative_vessels=len(vessels))
    finally:
        for writer in writers.values():
            writer.close()
    manifest = {"completed_at": now(), "source_fingerprints": before,
                "rows": rows, "vessels": len(vessels), "min_ts": min_ts, "max_ts": max_ts,
                "invalid_centroid_rows": invalid_centroid_rows,
                "partition_count": partition_count, "batch_size": batch_size,
                "partition_rule": "zlib.crc32(UTF8 rfid_id) modulo 128",
                "partitions": [{"path": str(paths[key].relative_to(run.out)),
                                "rows": rows_by_partition[key], "sha256": sha256(paths[key])}
                               for key in sorted(paths)]}
    if sum(item["rows"] for item in manifest["partitions"]) != rows:
        raise AssertionError("Partition row conservation failed")
    atomic_json(manifest_path, manifest)
    run.event("staging_complete", rows=rows, vessels=len(vessels), min_ts=min_ts, max_ts=max_ts,
              invalid_centroid_rows=invalid_centroid_rows)
    gc.collect()
    return manifest


def clean_number(value):
    return float(value) if math.isfinite(float(value)) else None


def summarize_vessel(rfid, one, scored, fb):
    hours = np.unique(one["ts"].to_numpy())
    gap = float(np.maximum(np.diff(hours) - 1, 0).sum()) if len(hours) > 1 else 0.0
    lon = one["cen_lon"].to_numpy(dtype=float)
    lat = one["cen_lat"].to_numpy(dtype=float)
    finite_coordinates = np.isfinite(lon) & np.isfinite(lat)
    radius = None
    if np.any(finite_coordinates):
        center_lon = float(np.nanmedian(lon))
        center_lat = float(np.nanmedian(lat))
        if math.isfinite(center_lon) and math.isfinite(center_lat):
            distances = fb.haversine_vec(center_lon, center_lat,
                                         lon[finite_coordinates], lat[finite_coordinates]) / 1000.0
            radius = clean_number(np.max(distances))
    rec = {"rfid_id": str(rfid), "n_rows": len(one), "peak_score": None,
           "peak_ts": None, "peak_state": None, "median_score": None, "p95_score": None,
           "n_unique_hours": len(hours), "gap_total_h": gap,
           "activity_radius_km": radius, "n_finite_scores": 0}
    if scored is None:
        return rec
    finite = scored[np.isfinite(scored["score"].to_numpy(dtype=float))]
    rec["n_finite_scores"] = len(finite)
    if len(finite):
        best = finite.sort_values(["score", "source_ordinal"], ascending=[False, True],
                                  kind="stable").iloc[0]
        rec.update(peak_score=float(best.score), peak_ts=int(best.ts), peak_state=str(best.state),
                   median_score=float(finite.score.median()), p95_score=float(finite.score.quantile(.95)))
    return rec


def read_checkpoints(path):
    if not path.exists():
        return {}
    records = {}
    with path.open("rb") as handle:
        lines = handle.readlines()
    original_size = sum(len(line) for line in lines)
    valid_bytes = 0
    for index, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            if index != len(lines) - 1:
                raise ValueError("Corrupted nonterminal checkpoint line")
            # Preserve an interrupted trailing append before removing its invalid bytes.
            path.with_name(f"checkpoint_interrupted_tail_{time.time_ns()}.bin").write_bytes(line)
            with path.open("r+b") as handle:
                handle.truncate(valid_bytes)
            break
        if rec["rfid_id"] in records:
            raise ValueError("Duplicate completed-vessel checkpoint")
        records[rec["rfid_id"]] = rec
        valid_bytes += len(line)
    if lines and valid_bytes == original_size and not lines[-1].endswith(b"\n"):
        # A complete JSON append interrupted immediately before its line terminator.
        with path.open("ab") as handle:
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    return records


def score_partitions(run, manifest, fb, references):
    nearest, fine, coarse, norm_gap, norm_jump, ref_meta = references
    checkpoint_path = run.out / "vessel_checkpoints.jsonl"
    records = read_checkpoints(checkpoint_path)
    resumed_count = len(records)
    run.event("scoring_started", resumed_vessels=resumed_count, total_vessels=manifest["vessels"])
    last_report = time.perf_counter()
    with checkpoint_path.open("a", encoding="utf-8", newline="\n") as checkpoints:
        for partition_no, item in enumerate(manifest["partitions"], 1):
            run.preflight(f"score_partition_{partition_no:03d}")
            path = run.out / item["path"]
            part = pq.read_table(path, use_threads=False).to_pandas()
            if len(part) != item["rows"]:
                raise AssertionError(f"Partition row count mismatch: {path}")
            part["rfid_id"] = part.rfid_id.astype(str)
            part["rfid_time"] = (part.ts % 24).astype(int)
            for rfid, raw in part.groupby("rfid_id", sort=True):
                if rfid in records:
                    if records[rfid]["n_rows"] != len(raw):
                        raise AssertionError(f"Checkpoint row count mismatch: {rfid}")
                    continue
                one = raw.sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
                scored = None
                try:
                    scored = fb.score_vessel(one, nearest, None, fine, coarse, norm_gap, norm_jump)
                except Exception as exc:
                    error = {"rfid_id": str(rfid), "n_rows": len(one),
                             "exception_type": type(exc).__name__, "message": str(exc)}
                    with (run.out / "vessel_errors.jsonl").open("a", encoding="utf-8") as errors:
                        errors.write(json.dumps(error, ensure_ascii=False) + "\n")
                        errors.flush()
                        os.fsync(errors.fileno())
                    run.event("vessel_score_error", **error)
                rec = summarize_vessel(rfid, one, scored, fb)
                checkpoints.write(json.dumps(rec, ensure_ascii=False, allow_nan=False) + "\n")
                checkpoints.flush()
                os.fsync(checkpoints.fileno())
                records[rfid] = rec
                rss = run.sample_peak()
                if len(records) % 25 == 0 or time.perf_counter() - last_report >= 30:
                    run.event("scoring_progress", vessels_completed=len(records),
                              vessels_total=manifest["vessels"], rows_completed=sum(r["n_rows"] for r in records.values()),
                              elapsed_seconds=round(time.perf_counter()-run.started, 2),
                              process_rss_mib=round(rss/MIB, 2), partition=partition_no)
                    run.save(vessels_completed=len(records), rows_completed=sum(r["n_rows"] for r in records.values()))
                    last_report = time.perf_counter()
                del one, scored
            del part
            gc.collect()
    if len(records) != manifest["vessels"] or sum(r["n_rows"] for r in records.values()) != manifest["rows"]:
        raise AssertionError("Final vessel/row conservation failed")
    tmp = run.out / "vessel_peaks.csv.tmp"
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(records[key] for key in sorted(records))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, run.out / "vessel_peaks.csv")
    return records, ref_meta, resumed_count


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hourly", type=Path, default=DEFAULT_HOURLY)
    ap.add_argument("--output", type=Path, default=ROUND_DIR / "execution_001")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    # Paths are deliberately restricted: no raw/test files, roster or label files.
    hourly = args.hourly.resolve()
    if hourly != DEFAULT_HOURLY.resolve():
        raise SystemExit("Only the approved round017 hourly-summary directory is allowed")
    out = args.output.resolve()
    if out.parent != ROUND_DIR or not out.name.startswith("execution_"):
        raise SystemExit("Output must be a round019 execution_* child directory")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "score_metadata.json").exists() and not args.resume:
        raise SystemExit("Existing scoring state: use --resume; nothing overwritten")
    lock = out / "score_run.lock"
    if lock.exists():
        owner = json.loads(lock.read_text(encoding="utf-8"))
        if psutil.pid_exists(owner["pid"]):
            raise SystemExit(f"Scoring process already active: PID {owner['pid']}")
        os.replace(lock, out / f"score_run_stale_{time.time_ns()}.lock")
    with lock.open("x", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "at": now()}, handle)
    run = Run(out)
    try:
        run.preflight("imports_and_input_provenance")
        files = [hourly / f"hourly_{month:02d}.parquet" for month in range(1, 7)]
        if not all(path.is_file() for path in files):
            raise FileNotFoundError("All six hourly input files are required")
        ref_files = sorted(path for path in REFERENCES.iterdir() if path.is_file())
        sources = files + [FROZEN, Path(__file__).resolve()] + ref_files
        before = fingerprints(sources)
        before_path = out / "source_checksums_before.json"
        if before_path.exists():
            original = json.loads(before_path.read_text(encoding="utf-8"))
            if original != before:
                raise ValueError("Source checksums changed since original execution")
        else:
            atomic_json(before_path, before)
        run.save(stage="partitioning", source_checksums_before=str(before_path),
                 frozen_scorer_sha256=before[str(FROZEN.resolve())]["sha256"])
        load_stack()
        manifest = stage_inputs(run, files, before)
        if manifest["rows"] != 3_887_065 or manifest["vessels"] != 7_372:
            raise AssertionError(f"Approved cohort mismatch: {manifest['rows']} rows / {manifest['vessels']} vessels")
        run.save(stage="loading_frozen_references", rows=manifest["rows"], vessels=manifest["vessels"],
                 min_ts=manifest["min_ts"], max_ts=manifest["max_ts"],
                 invalid_centroid_rows=manifest["invalid_centroid_rows"])
        run.preflight("load_frozen_references")
        sys.path.insert(0, str(FROZEN.parent))
        fb = importlib.import_module("frozen_baseline")
        if Path(fb.__file__).resolve() != FROZEN.resolve():
            raise AssertionError("Unexpected scorer module path")
        references = fb.load_references(REFERENCES)
        run.save(stage="scoring", reference_summary=references[-1])
        records, ref_meta, resumed = score_partitions(run, manifest, fb, references)
        run.preflight("verify_source_checksums_and_finalize")
        after = fingerprints(sources)
        atomic_json(out / "source_checksums_after.json", after)
        if after != before:
            raise AssertionError("Source/reference/scorer checksum changed during execution")
        errors_path = out / "vessel_errors.jsonl"
        errors = sum(1 for line in errors_path.open(encoding="utf-8") if line.strip()) if errors_path.exists() else 0
        result = {"status": "complete" if errors == 0 else "complete_with_vessel_errors",
                  "stage": "finished", "completed_at": now(), "rows": manifest["rows"],
                  "vessels": len(records), "vessels_completed": len(records),
                  "rows_completed": sum(r["n_rows"] for r in records.values()),
                  "n_finite_scores": sum(r["n_finite_scores"] for r in records.values()),
                  "vessels_without_finite_scores": sum(r["n_finite_scores"] == 0 for r in records.values()),
                  "vessel_error_records": errors, "resumed_vessels": resumed,
                  "source_checksums_match": True, "reference_summary": ref_meta,
                  "output_sha256": sha256(out / "vessel_peaks.csv")}
        run.save(**result)
        run.event("scoring_complete", **result)
    except MemoryPause as exc:
        run.save(status="paused_memory", reason=str(exc))
        run.event("stage_deferred_memory", reason=str(exc))
        return 75
    except Exception as exc:
        (out / "score_error_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run.save(status="failed", exception_type=type(exc).__name__, reason=str(exc))
        run.event("scoring_failed", exception_type=type(exc).__name__, reason=str(exc))
        return 1
    finally:
        if lock.exists():
            lock.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
