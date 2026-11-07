"""Label-blind, restartable Round021 scoring of the entire approved 2026 fleet.

Only the six already approved summaries, their verified Round019 partitions,
the original frozen scorer/references, and Round019 vessel_peaks are read.
No labels, 2025 inputs, new identifiers, fitting, or model training are used.
Each of four fixed assignments owns partition_index % 4, even when RAM reduces
concurrent process count. Completed partition files are immutable checkpoints.
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
import psutil

ROUND = Path(__file__).resolve().parent
ROOT = ROUND.parents[2]
LEGACY = ROOT / "testB/final/round_019_vessel_discrimination_20261106"
LEGACY_OUT = LEGACY / "execution_001"
OUT = ROUND / "execution_001"
SELF = Path(__file__).resolve()
FREEZE = ROUND / "freeze.json"
MIB = 1024 ** 2
ASSIGNMENTS = 4
PARENT_BUDGET_MIB = 256
WORKER_BUDGET_MIB = 512
RESERVE_MIB = 640
EXPECTED_ROWS = 3_887_065
EXPECTED_VESSELS = 7_372
SCORE_COLUMNS = ["rfid_id", "ts", "source_ordinal", "score", "s_zone", "s_change",
                 "s_gap", "state", "history_index", "since_previous_row_h", "until_next_row_h"]
PREDICTION_COLUMNS = ["rfid_id", "split", "split_rank", "n_rows", "first_ts", "last_ts",
    "n_unique_hours", "n_finite_scores", "peak_score", "baseline_ts", "tie_center_ts",
    "gap_midpoint_ts", "baseline_source_ordinal", "peak_state", "n_tied_hours", "n_tied_rows",
    "n_tie_runs", "tie_run_start", "tie_run_end", "previous_row_ts", "baseline_row_gap_h",
    "previous_distinct_ts", "preceding_gap_h", "gap_missing_h", "baseline_history_index", "tie_center_changed", "gap_midpoint_changed",
    "median_score", "p95_score", "gap_total_h", "activity_radius_km", "scoring_error"]


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(MIB), b""):
            value.update(block)
    return value.hexdigest()


def fingerprint(paths):
    return {str(Path(p).resolve()): {"sha256": sha256(p), "bytes": Path(p).stat().st_size}
            for p in paths}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class MemoryPause(RuntimeError):
    pass


class Run:
    def __init__(self, directory, budget):
        self.out = Path(directory)
        self.out.mkdir(parents=True, exist_ok=True)
        self.process = psutil.Process()
        self.budget = budget
        self.started = time.perf_counter()
        self.peak = 0
        self.meta = {"status": "running", "started_at": now(), "pid": os.getpid(),
            "training_performed": False, "labels_read": False, "score_definition_changed": False,
            "expected_peak_process_mib": budget, "reserve_mib": RESERVE_MIB,
            "memory_estimate_basis": "Round019 worker observed about 308-355 MiB; 512 MiB worker budget includes one 128th partition, frozen 62 MiB arrays, vessel copies and streamed score output; parent uses stdlib merge of 7372 records within 256 MiB",
            "fixed_worker_assignments": ASSIGNMENTS, "assignment_rule": "partition_index modulo 4",
            "scorer": str(ROOT / "deliverables/testb_system_20261106/src/frozen_baseline.py"),
            "source_ordinal_reference_limitation": "Round019 vessel_peaks.csv stores no source_ordinal; compare all available summary fields and assert ordinal tie policy independently"}

    def sample(self):
        info = self.process.memory_info()
        self.peak = max(self.peak, info.rss, getattr(info, "peak_wset", 0))
        return info.rss

    def event(self, event, **values):
        record = {"at": now(), "event": event, **values}
        with (self.out / "score_progress.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps(record, ensure_ascii=False, allow_nan=False), flush=True)

    def save(self, **values):
        self.meta.update(values)
        self.sample()
        self.meta.update(updated_at=now(), elapsed_seconds=round(time.perf_counter() - self.started, 3),
                         observed_peak_process_mib=round(self.peak / MIB, 3))
        atomic_json(self.out / "score_metadata.json", self.meta)

    def preflight(self, stage, additional_mib=None):
        rss = self.sample() / MIB
        available = psutil.virtual_memory().available / MIB
        needed = max(0, self.budget - rss) if additional_mib is None else additional_mib
        others = []
        for process in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                item = process.info
                if item["pid"] != os.getpid() and item["memory_info"] is not None:
                    others.append({"pid": item["pid"], "name": item["name"],
                                   "rss_mib": round(item["memory_info"].rss / MIB, 2)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        others.sort(key=lambda v: -v["rss_mib"])
        receipt = {"at": now(), "stage": stage, "available_mib": round(available, 2),
            "own_rss_mib": round(rss, 2), "estimated_process_peak_mib": self.budget,
            "additional_expected_mib": round(needed, 2), "reserve_mib": RESERVE_MIB,
            "other_processes": others[:12], "passed": available >= needed + RESERVE_MIB}
        self.event("memory_preflight", **receipt)
        self.meta["last_memory_preflight"] = receipt
        if not receipt["passed"]:
            raise MemoryPause(f"Insufficient RAM before {stage}; deferred without RAM polling")
        return receipt


def legacy_module():
    spec = importlib.util.spec_from_file_location("round019_unchanged_score_helpers", LEGACY / "score_fleet.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stack(sf):
    sf.load_stack()
    spec = importlib.util.spec_from_file_location("round021_unchanged_frozen_baseline", sf.FROZEN)
    fb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fb)
    return fb


def read_freeze(expected_hash=None):
    if not FREEZE.is_file():
        raise FileNotFoundError("Round021 freeze.json must exist before fleet scoring")
    value = json.loads(FREEZE.read_text(encoding="utf-8-sig"))
    digest = sha256(FREEZE)
    if expected_hash is not None and digest != expected_hash:
        raise AssertionError("Frozen protocol receipt changed")
    protocol = Path(value.get("protocol_path", str(ROUND / "PROTOCOL.md")))
    if not protocol.is_absolute():
        protocol = ROOT / protocol
    if protocol.resolve() != (ROUND / "PROTOCOL.md").resolve():
        raise ValueError("Unexpected Round021 protocol location")
    if sha256(protocol) != value["protocol_sha256"]:
        raise AssertionError("Protocol differs from freeze.json")
    return value, digest, protocol


def provenance(run):
    sf = legacy_module()
    freeze, freeze_hash, protocol = read_freeze()
    original = json.loads((LEGACY_OUT / "source_checksums_before.json").read_text(encoding="utf-8"))
    for source, expected in original.items():
        path = Path(source).resolve()
        if path != sf.FROZEN.resolve() and path != (LEGACY / "score_fleet.py").resolve() and path.parent not in (sf.DEFAULT_HOURLY.resolve(), sf.REFERENCES.resolve()):
            raise ValueError(f"Unapproved original source path: {path}")
        if sha256(path) != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise AssertionError(f"Original frozen source changed: {path}")
    manifest_path = LEGACY_OUT / "staging_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["source_fingerprints"] != original:
        raise AssertionError("Round019 staged sources differ from original frozen sources")
    if (manifest["rows"], manifest["vessels"], manifest["partition_count"]) != (EXPECTED_ROWS, EXPECTED_VESSELS, 128):
        raise AssertionError("Unexpected approved cohort")
    if len(manifest["partitions"]) != 128:
        raise AssertionError("Expected all 128 partitions")
    run.preflight("verify_existing_128_partitions")
    partition_paths = []
    for index, item in enumerate(manifest["partitions"]):
        path = (LEGACY_OUT / item["path"]).resolve()
        if LEGACY_OUT.resolve() not in path.parents or path.name != f"part_{index:03d}.parquet":
            raise ValueError("Unexpected staged partition path or chronology")
        if sha256(path) != item["sha256"]:
            raise AssertionError(f"Staged partition changed: {index}")
        partition_paths.append(path)
    paths = [Path(p) for p in original] + partition_paths + [manifest_path, LEGACY_OUT / "vessel_peaks.csv",
                LEGACY / "score_fleet_parallel.py", SELF, ROUND / "test_score_fleet_timing.py", FREEZE, protocol]
    before = fingerprint(paths)
    target = OUT / "score_sources_before.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != before:
        raise AssertionError("Scoring inputs/code changed since first launch")
    if not target.exists():
        atomic_json(target, before)
    run.save(freeze_sha256=freeze_hash, protocol_sha256=freeze["protocol_sha256"],
             source_count=len(before), source_checksums_before=str(target), rows=EXPECTED_ROWS,
             vessels=EXPECTED_VESSELS, staging_reused_without_modification=True)
    return sf, manifest, before, freeze_hash


def split_fleet(rfids):
    ordered = sorted(rfids, key=lambda rfid: (hashlib.sha256(("round021-v1|" + rfid).encode("utf-8")).hexdigest(), rfid))
    return {rfid: {"split": "development" if rank % 2 == 0 else "validation", "split_rank": rank}
            for rank, rfid in enumerate(ordered)}


def policy_record(rfid, one, scored, sf, fb, scoring_error=None):
    """The three protocol-fixed timestamp policies; labels are not an argument."""
    np = sf.np
    base = sf.summarize_vessel(rfid, one, scored, fb)
    hours = np.unique(one["ts"].to_numpy(dtype="int64"))
    record = {**base, "first_ts": int(hours[0]), "last_ts": int(hours[-1]),
        "baseline_ts": base["peak_ts"], "tie_center_ts": None, "gap_midpoint_ts": None,
        "baseline_source_ordinal": None, "n_tied_hours": 0, "n_tied_rows": 0, "n_tie_runs": 0,
        "tie_run_start": None, "tie_run_end": None, "previous_row_ts": None, "previous_distinct_ts": None,
        "baseline_row_gap_h": None,
        "preceding_gap_h": None, "gap_missing_h": None, "baseline_history_index": None,
        "tie_center_changed": False, "gap_midpoint_changed": False, "scoring_error": scoring_error}
    if scored is None:
        return record
    finite = scored[np.isfinite(scored["score"].to_numpy(dtype=float))]
    if len(finite) == 0:
        return record
    best = finite.sort_values(["score", "source_ordinal"], ascending=[False, True], kind="stable").iloc[0]
    top = finite[finite["score"] == best.score]
    tied_hours = np.unique(top["ts"].to_numpy(dtype="int64"))
    runs = np.split(tied_hours, np.flatnonzero(np.diff(tied_hours) != 1) + 1)
    chosen = sorted(runs, key=lambda run: (-len(run), int(run[0])))[0]
    tie_ts = int(chosen[(len(chosen) - 1) // 2])
    b = int(best.ts)
    predecessor_index = int(np.searchsorted(hours, b, side="left")) - 1
    previous_distinct = int(hours[predecessor_index]) if predecessor_index >= 0 else None
    baseline_index = int(best.name)
    previous_row = int(one.iloc[baseline_index - 1].ts) if baseline_index > 0 else None
    gap = b - previous_row if previous_row is not None else None
    midpoint = (previous_row + b) // 2 if gap is not None and gap > 1 else b
    # Stable tie ordinal is independently asserted; the old CSV did not save it.
    if int(best.source_ordinal) != int(top.source_ordinal.min()):
        raise AssertionError("Baseline source-ordinal tie policy violated")
    record.update(tie_center_ts=tie_ts, gap_midpoint_ts=midpoint,
        baseline_source_ordinal=int(best.source_ordinal), n_tied_hours=len(tied_hours), n_tied_rows=len(top),
        n_tie_runs=len(runs), tie_run_start=int(chosen[0]), tie_run_end=int(chosen[-1]),
        previous_row_ts=previous_row, previous_distinct_ts=previous_distinct, baseline_row_gap_h=gap,
        preceding_gap_h=gap, gap_missing_h=max(0, gap - 1) if gap is not None else None,
        baseline_history_index=baseline_index, tie_center_changed=tie_ts != b, gap_midpoint_changed=midpoint != b)
    return record


def score_schema(pa):
    return pa.schema([pa.field("rfid_id", pa.string()), pa.field("ts", pa.int64()),
        pa.field("source_ordinal", pa.int64()), pa.field("score", pa.float64()),
        pa.field("s_zone", pa.float64()), pa.field("s_change", pa.float64()), pa.field("s_gap", pa.float64()),
        pa.field("state", pa.string()), pa.field("history_index", pa.int32()),
        pa.field("since_previous_row_h", pa.float64()), pa.field("until_next_row_h", pa.float64())])


def checkpoint_files(directory, index):
    stem = f"part_{index:03d}"
    return directory / f"{stem}.hourly_scores.parquet", directory / f"{stem}.checkpoint.json"


def load_completed_partition(directory, index, item):
    path, checkpoint = checkpoint_files(directory, index)
    if not checkpoint.exists():
        return None
    receipt = json.loads(checkpoint.read_text(encoding="utf-8"))
    if receipt["input_sha256"] != item["sha256"] or receipt["rows"] != item["rows"]:
        raise AssertionError("Checkpoint input differs")
    if not path.is_file() or sha256(path) != receipt["output_sha256"]:
        raise AssertionError("Checkpoint score parquet is missing or changed")
    return receipt


def worker(index, freeze_hash, source_hash):
    directory = OUT / "workers" / f"worker_{index}"
    run = Run(directory, WORKER_BUDGET_MIB)
    try:
        run.preflight("worker_imports")
        _, _, _ = read_freeze(freeze_hash)
        if sha256(SELF) != source_hash:
            raise AssertionError("Engine changed after parent launch")
        sf = legacy_module()
        fb = stack(sf)
        manifest = json.loads((LEGACY_OUT / "staging_manifest.json").read_text(encoding="utf-8"))
        assigned = [(i, item) for i, item in enumerate(manifest["partitions"]) if i % ASSIGNMENTS == index]
        run.preflight("worker_load_frozen_references")
        references = fb.load_references(sf.REFERENCES)
        nearest, fine, coarse, norm_gap, norm_jump, ref_meta = references
        records = {}
        completed = []
        error_count = 0
        for partition_index, item in assigned:
            cached = load_completed_partition(directory, partition_index, item)
            if cached is not None:
                if set(records).intersection(rec["rfid_id"] for rec in cached["vessels"]):
                    raise AssertionError("Repeated checkpoint vessel")
                records.update({rec["rfid_id"]: rec for rec in cached["vessels"]})
                error_count += cached["scoring_errors"]
                completed.append({key: value for key, value in cached.items() if key != "vessels"})
                run.event("partition_resumed", partition=partition_index, rows=cached["rows"], vessels=len(cached["vessels"]))
                continue
            run.preflight(f"score_partition_{partition_index:03d}")
            input_path = LEGACY_OUT / item["path"]
            if sha256(input_path) != item["sha256"]:
                raise AssertionError("Partition changed before worker read")
            part = sf.pq.read_table(input_path, use_threads=False).to_pandas()
            sf.validate_batch(sf.pa.Table.from_pandas(part, preserve_index=False), input_path)
            if len(part) != item["rows"]:
                raise AssertionError("Partition row conservation failed")
            part["rfid_id"] = part.rfid_id.astype(str)
            part["rfid_time"] = (part.ts % 24).astype(int)
            output_path, checkpoint = checkpoint_files(directory, partition_index)
            temporary = output_path.with_suffix(output_path.suffix + ".tmp")
            for orphan in (output_path, temporary):
                if orphan.exists():
                    os.replace(orphan, orphan.with_name(orphan.name + f".interrupted_{time.time_ns()}"))
            local = []
            local_errors = 0
            schema = score_schema(sf.pa)
            with sf.pq.ParquetWriter(temporary, schema, compression="snappy", use_dictionary=["rfid_id", "state"]) as writer:
                for rfid, raw in part.groupby("rfid_id", sort=True):
                    one = raw.sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
                    error = None
                    try:
                        scored = fb.score_vessel(one, nearest, None, fine, coarse, norm_gap, norm_jump)
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        local_errors += 1
                        scored = None
                        with (directory / "vessel_errors.jsonl").open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps({"at": now(), "rfid_id": str(rfid), "partition": partition_index,
                                "n_rows": len(one), "error": error, "traceback": traceback.format_exc()}, ensure_ascii=False) + "\n")
                            handle.flush()
                            os.fsync(handle.fileno())
                        run.event("vessel_score_error", rfid_id=str(rfid), partition=partition_index, error=error)
                    record = policy_record(rfid, one, scored, sf, fb, error)
                    local.append(record)
                    saved = one[["rfid_id", "ts", "source_ordinal"]].copy()
                    for name in ("score", "s_zone", "s_change", "s_gap"):
                        saved[name] = scored[name] if scored is not None else float("nan")
                    saved["state"] = scored["state"] if scored is not None else "scoring_error"
                    saved["history_index"] = sf.np.arange(len(one), dtype="int32")
                    timestamps = one.ts.to_numpy(dtype=float)
                    saved["since_previous_row_h"] = sf.np.r_[sf.np.nan, sf.np.diff(timestamps)]
                    saved["until_next_row_h"] = sf.np.r_[sf.np.diff(timestamps), sf.np.nan]
                    writer.write_table(sf.pa.Table.from_pandas(saved[SCORE_COLUMNS], schema=schema, preserve_index=False))
                    run.sample()
                    del one, scored, saved
            with temporary.open("rb+") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, output_path)
            receipt = {"partition": partition_index, "completed_at": now(), "input_sha256": item["sha256"],
                "rows": item["rows"], "n_vessels": len(local), "scoring_errors": local_errors,
                "output_path": str(output_path.relative_to(OUT)), "output_sha256": sha256(output_path),
                "output_bytes": output_path.stat().st_size, "vessels": local}
            if sum(rec["n_rows"] for rec in local) != item["rows"] or sf.pq.ParquetFile(output_path).metadata.num_rows != item["rows"]:
                raise AssertionError("Saved score rows do not conserve partition rows")
            if set(records).intersection(rec["rfid_id"] for rec in local):
                raise AssertionError("Worker partition vessel sets overlap")
            atomic_json(checkpoint, receipt)
            records.update({rec["rfid_id"]: rec for rec in local})
            error_count += local_errors
            completed.append({key: value for key, value in receipt.items() if key != "vessels"})
            run.event("partition_complete", partition=partition_index, rows=item["rows"], vessels=len(local),
                      total_vessels=len(records), output_bytes=receipt["output_bytes"])
            run.save(stage="scoring", worker_index=index, partitions_completed=len(completed),
                     rows_completed=sum(rec["n_rows"] for rec in records.values()), vessels_completed=len(records),
                     vessel_error_records=error_count)
            del part, local
            gc.collect()
        run.save(status="complete" if error_count == 0 else "complete_with_vessel_errors", stage="finished",
            completed_at=now(), worker_index=index, rows_completed=sum(rec["n_rows"] for rec in records.values()),
            vessels_completed=len(records), partitions_completed=len(completed), vessel_error_records=error_count,
            partitions=completed, reference_summary=ref_meta, freeze_sha256=freeze_hash, engine_sha256=source_hash)
        return 0 if error_count == 0 else 2
    except MemoryPause as exc:
        run.save(status="paused_memory", reason=str(exc))
        run.event("stage_deferred_memory", reason=str(exc))
        return 75
    except Exception as exc:
        (directory / "score_error_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run.save(status="failed", exception_type=type(exc).__name__, reason=str(exc))
        run.event("worker_failed", exception_type=type(exc).__name__, reason=str(exc))
        return 1


def compare_legacy(records, sf):
    with (LEGACY_OUT / "vessel_peaks.csv").open(encoding="utf-8-sig", newline="") as handle:
        original = {rec["rfid_id"]: rec for rec in csv.DictReader(handle)}
    if set(original) != set(records):
        raise AssertionError("Round019/Round021 fleet sets differ")
    mismatches = []
    integer = {"n_rows", "peak_ts", "n_unique_hours", "n_finite_scores"}
    for rfid, old in original.items():
        new = records[rfid]
        for column in sf.OUTPUT_COLS:
            expected = old[column]
            if column == "rfid_id" or column == "peak_state":
                expected = expected or None
            else:
                expected = (int(expected) if column in integer else float(expected)) if expected else None
            if new[column] != expected:
                mismatches.append({"rfid_id": rfid, "field": column, "old": expected, "new": new[column]})
    result = {"vessels_compared": len(records), "fields": sf.OUTPUT_COLS, "mismatch_count": len(mismatches),
        "mismatches": mismatches[:30], "exact_float_equality": True,
        "source_ordinal_comparison": "unavailable: Round019 vessel_peaks.csv has no ordinal field; independent exact-max minimum source_ordinal assertions passed for every newly scored vessel"}
    atomic_json(OUT / "score_baseline_parity.json", result)
    if mismatches:
        raise AssertionError(f"Frozen baseline changed: {len(mismatches)} summary field mismatches")
    return result


def merge(run, sf, manifest):
    run.preflight("merge_all_fleet_predictions")
    records, score_files, worker_meta = {}, [], []
    errors = 0
    for index in range(ASSIGNMENTS):
        directory = OUT / "workers" / f"worker_{index}"
        meta = json.loads((directory / "score_metadata.json").read_text(encoding="utf-8"))
        if meta["status"] != "complete":
            raise AssertionError(f"Worker {index} did not complete without errors")
        worker_meta.append(meta)
        for pindex, item in enumerate(manifest["partitions"]):
            if pindex % ASSIGNMENTS != index:
                continue
            receipt = load_completed_partition(directory, pindex, item)
            if receipt is None:
                raise AssertionError("Missing completed partition")
            local = {rec["rfid_id"]: rec for rec in receipt["vessels"]}
            if set(records).intersection(local):
                raise AssertionError("Fixed worker assignments overlap")
            records.update(local)
            errors += receipt["scoring_errors"]
            score_files.append({key: value for key, value in receipt.items() if key != "vessels"})
    if len(records) != EXPECTED_VESSELS or sum(r["n_rows"] for r in records.values()) != EXPECTED_ROWS or errors:
        raise AssertionError("Final fleet/row/error conservation failed")
    parity = compare_legacy(records, sf)
    splits = split_fleet(records)
    path = OUT / "fleet_policy_predictions.csv"
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for rfid in sorted(records):
            writer.writerow({**records[rfid], **splits[rfid]})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    atomic_json(OUT / "hourly_score_manifest.json", {"created_at": now(), "rows": EXPECTED_ROWS,
        "vessels": EXPECTED_VESSELS, "columns": SCORE_COLUMNS, "files": sorted(score_files, key=lambda v: v["partition"]),
        "total_bytes": sum(r["output_bytes"] for r in score_files), "labels_read": False})
    summary = {"rows": EXPECTED_ROWS, "vessels": EXPECTED_VESSELS,
        "n_finite_scores": sum(r["n_finite_scores"] for r in records.values()),
        "vessels_without_finite_scores": sum(r["n_finite_scores"] == 0 for r in records.values()),
        "tied_max_vessels": sum(r["n_tied_hours"] > 1 for r in records.values()),
        "tie_center_changed_vessels": sum(r["tie_center_changed"] for r in records.values()),
        "gap_midpoint_changed_vessels": sum(r["gap_midpoint_changed"] for r in records.values()),
        "split_counts": {s: sum(v["split"] == s for v in splits.values()) for s in ("development", "validation")},
        "split_algorithm": "sort by SHA256(UTF8('round021-v1|'+rfid_id)), rfid_id; alternating development/validation starting rank0 development; all fleet before labels",
        "policy_prediction_sha256": sha256(path), "hourly_manifest_sha256": sha256(OUT / "hourly_score_manifest.json"),
        "baseline_parity": parity, "worker_summaries": worker_meta,
        "sum_of_worker_process_peak_mib": round(sum(v["observed_peak_process_mib"] for v in worker_meta), 3),
        "vessel_error_records": errors}
    atomic_json(OUT / "labelblind_score_summary.json", {key: value for key, value in summary.items() if key != "worker_summaries"})
    return summary


def orchestrate(desired, resume):
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / "score_run.lock"
    if lock.exists():
        owner = json.loads(lock.read_text(encoding="utf-8"))
        if psutil.pid_exists(owner["pid"]):
            process = psutil.Process(owner["pid"])
            if abs(process.create_time() - owner["process_create_time"]) < 0.1:
                raise SystemExit(f"Own scoring run already active: PID {owner['pid']}")
        os.replace(lock, OUT / f"score_run_stale_{time.time_ns()}.lock")
    if (OUT / "score_metadata.json").exists() and not resume:
        raise SystemExit("Existing score state; use --resume without overwriting completed partitions")
    with lock.open("x", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "process_create_time": psutil.Process().create_time(), "at": now()}, handle)
    run = Run(OUT, PARENT_BUDGET_MIB)
    active = []
    try:
        initial = run.preflight("parent_source_provenance")
        sf, manifest, before, freeze_hash = provenance(run)
        source_hash = sha256(SELF)
        # Fixed four assignments are preserved; only concurrent process count changes.
        available = psutil.virtual_memory().available / MIB
        concurrency = min(desired, max(0, int((available - PARENT_BUDGET_MIB - RESERVE_MIB) // WORKER_BUDGET_MIB)))
        if concurrency < 1:
            raise MemoryPause("Insufficient RAM for parent256 + worker512 + reserve640 MiB")
        run.event("aggregate_memory_plan", available_mib=round(available, 2), concurrency=concurrency,
            fixed_assignments=ASSIGNMENTS, expected_parent_peak_mib=PARENT_BUDGET_MIB,
            expected_each_worker_peak_mib=WORKER_BUDGET_MIB, reserve_mib=RESERVE_MIB,
            total_estimated_peak_plus_reserve_mib=PARENT_BUDGET_MIB + concurrency * WORKER_BUDGET_MIB + RESERVE_MIB)
        run.save(stage="parallel_scoring", concurrency=concurrency, fixed_assignments=ASSIGNMENTS,
            engine_sha256=source_hash, freeze_sha256=freeze_hash, initial_memory_preflight=initial)
        queue = list(range(ASSIGNMENTS))
        exits = []
        last_report = time.perf_counter()
        while queue or active:
            while queue and len(active) < concurrency:
                index = queue.pop(0)
                # Check once at the actual launch transition; this is not a RAM watch loop.
                run.preflight(f"launch_fixed_worker_{index}", WORKER_BUDGET_MIB + max(0, PARENT_BUDGET_MIB-run.sample()/MIB))
                directory = OUT / "workers" / f"worker_{index}"
                directory.mkdir(parents=True, exist_ok=True)
                stdout = (directory / "stdout.log").open("ab")
                stderr = (directory / "stderr.log").open("ab")
                environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
                child = subprocess.Popen([sys.executable, "-B", "-u", str(SELF), "--worker", str(index),
                    "--freeze-sha256", freeze_hash, "--engine-sha256", source_hash], cwd=ROUND,
                    stdout=stdout, stderr=stderr, env=environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                active.append((index, child, stdout, stderr))
                run.event("worker_launched", worker_index=index, pid=child.pid)
            unfinished = []
            for index, child, stdout, stderr in active:
                code = child.poll()
                if code is None:
                    unfinished.append((index, child, stdout, stderr))
                else:
                    stdout.close()
                    stderr.close()
                    exits.append({"worker_index": index, "pid": child.pid, "exit_code": code})
                    run.event("worker_exited", **exits[-1])
            active = unfinished
            if any(item["exit_code"] != 0 for item in exits):
                # Other owned workers may finish safely; never terminate user processes.
                for _, child, stdout, stderr in active:
                    child.wait()
                    stdout.close()
                    stderr.close()
                active = []
                if any(item["exit_code"] == 75 for item in exits):
                    raise MemoryPause(f"Worker deferred at stage RAM gate: {exits}")
                raise RuntimeError(f"Worker failed explicitly: {exits}")
            if time.perf_counter() - last_report >= 30:
                states = []
                for index in range(ASSIGNMENTS):
                    path = OUT / "workers" / f"worker_{index}" / "score_metadata.json"
                    meta = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                    states.append({"worker_index": index, "status": meta.get("status", "not_started"),
                        "rows_completed": meta.get("rows_completed", 0), "vessels_completed": meta.get("vessels_completed", 0)})
                run.event("fleet_progress", workers=states)
                run.save(rows_completed=sum(v["rows_completed"] for v in states),
                         vessels_completed=sum(v["vessels_completed"] for v in states), workers=states)
                last_report = time.perf_counter()
            if active:
                time.sleep(2)
        summary = merge(run, sf, manifest)
        run.preflight("verify_sources_after_scoring")
        after = fingerprint([Path(p) for p in before])
        atomic_json(OUT / "score_sources_after.json", after)
        if before != after:
            raise AssertionError("Original sources/references/scorer/protocol/engine changed during scoring")
        seal = {"status": "complete", "created_at": now(), "rows_completed": EXPECTED_ROWS,
            "vessels_completed": EXPECTED_VESSELS, "vessel_error_records": 0,
            "labels_read": False, "accident_times_parsed": False, "training_performed": False,
            "score_definition_changed": False, "source_checksums_match": True,
            "freeze_sha256": freeze_hash, "engine_sha256": source_hash,
            "prediction_file": str((OUT / "fleet_policy_predictions.csv").relative_to(ROUND)),
            "policy_prediction_sha256": summary["policy_prediction_sha256"],
            "hourly_manifest_sha256": summary["hourly_manifest_sha256"],
            "sources_before_sha256": sha256(OUT / "score_sources_before.json"),
            "sources_after_sha256": sha256(OUT / "score_sources_after.json"),
            "baseline_parity_sha256": sha256(OUT / "score_baseline_parity.json"),
            "split_counts": summary["split_counts"]}
        atomic_json(OUT / "score_seal.json", seal)
        run.save(status="complete", stage="finished", completed_at=now(), rows_completed=EXPECTED_ROWS,
            vessels_completed=EXPECTED_VESSELS, source_checksums_match=True, accident_times_parsed=False,
            worker_exits=exits, score_seal_sha256=sha256(OUT / "score_seal.json"), **summary)
        run.event("fleet_scoring_complete", rows=EXPECTED_ROWS, vessels=EXPECTED_VESSELS,
            vessel_error_records=0, policy_prediction_sha256=summary["policy_prediction_sha256"])
        return 0
    except MemoryPause as exc:
        run.save(status="paused_memory", reason=str(exc))
        run.event("stage_deferred_memory", reason=str(exc))
        return 75
    except Exception as exc:
        (OUT / "score_error_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run.save(status="failed", exception_type=type(exc).__name__, reason=str(exc))
        run.event("fleet_scoring_failed", exception_type=type(exc).__name__, reason=str(exc))
        return 1
    finally:
        for _, child, stdout, stderr in active:
            child.wait()
            stdout.close()
            stderr.close()
        if lock.exists():
            owner = json.loads(lock.read_text(encoding="utf-8"))
            if owner["pid"] == os.getpid():
                lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker", type=int)
    parser.add_argument("--freeze-sha256")
    parser.add_argument("--engine-sha256")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise SystemExit("One to four concurrent workers required")
    if args.worker is not None:
        if args.worker not in range(ASSIGNMENTS) or not args.freeze_sha256 or not args.engine_sha256:
            raise SystemExit("Worker requires fixed index and parent-frozen hashes")
        return worker(args.worker, args.freeze_sha256, args.engine_sha256)
    return orchestrate(args.workers, args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
