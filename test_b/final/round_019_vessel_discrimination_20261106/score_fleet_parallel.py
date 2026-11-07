"""Bounded parallel loader/orchestrator using the frozen sequential scorer helpers.

The original score_fleet.py is imported unchanged. Workers own disjoint disk
partitions and checkpoint files. Only this parent writes the final fleet CSV.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
import psutil
import score_fleet as sf

OUT = sf.ROUND_DIR / "execution_001"
HELPER = Path(__file__).resolve()


def worker(index, count):
    directory = OUT / "workers" / f"worker_{index}"
    directory.mkdir(parents=True, exist_ok=True)
    run = sf.Run(directory)
    try:
        run.preflight("parallel_worker_imports_and_partition_roster")
        sf.load_stack()
        sys.path.insert(0, str(sf.FROZEN.parent))
        fb = importlib.import_module("frozen_baseline")
        original = json.loads((OUT / "staging_manifest.json").read_text(encoding="utf-8"))
        partitions = [item for pos, item in enumerate(original["partitions"]) if pos % count == index]
        ids = set()
        for item in partitions:
            ids.update(sf.pq.read_table(OUT / item["path"], columns=["rfid_id"], use_threads=False)["rfid_id"].to_pylist())
        manifest = {**original, "rows": sum(item["rows"] for item in partitions), "vessels": len(ids),
                    "partitions": [{**item, "path": os.path.relpath(OUT / item["path"], directory)}
                                   for item in partitions]}
        sf.atomic_json(directory / "assigned_manifest.json", manifest)
        run.preflight("parallel_worker_load_unchanged_references")
        references = fb.load_references(sf.REFERENCES)
        run.save(stage="scoring", worker_index=index, worker_count=count,
                 rows=manifest["rows"], vessels=manifest["vessels"])
        records, ref_meta, resumed = sf.score_partitions(run, manifest, fb, references)
        errors_path = directory / "vessel_errors.jsonl"
        errors = sum(1 for line in errors_path.open(encoding="utf-8") if line.strip()) if errors_path.exists() else 0
        run.save(status="complete" if errors == 0 else "complete_with_vessel_errors", stage="finished",
                 completed_at=sf.now(), worker_index=index, worker_count=count,
                 rows=manifest["rows"], rows_completed=sum(rec["n_rows"] for rec in records.values()),
                 vessels=len(records), vessels_completed=len(records), resumed_vessels=resumed,
                 vessel_error_records=errors, reference_summary=ref_meta)
        run.event("worker_complete", worker_index=index, rows=manifest["rows"], vessels=len(records))
        return 0
    except sf.MemoryPause as exc:
        run.save(status="paused_memory", reason=str(exc))
        run.event("stage_deferred_memory", reason=str(exc))
        return 75
    except Exception as exc:
        (directory / "score_error_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run.save(status="failed", exception_type=type(exc).__name__, reason=str(exc))
        run.event("worker_failed", exception_type=type(exc).__name__, reason=str(exc))
        return 1


def aggregate_preflight(run, desired):
    run.preflight("parallel_parent_provenance")
    available = psutil.virtual_memory().available / sf.MIB
    # Total additional process budgets are conservative and independent of measured RSS.
    count = min(desired, int((available - 512 - 640) // 512))
    cpu_count = psutil.cpu_count(logical=True) or 1
    count = min(count, cpu_count)
    if count < 1:
        raise sf.MemoryPause("Insufficient RAM for parent512MiB + worker512MiB + reserve640MiB")
    run.event("aggregate_parallel_memory_preflight", available_mib=round(available, 2),
              expected_parent_peak_mib=512, expected_each_worker_peak_mib=512,
              available_logical_cpus=cpu_count,
              worker_count=count, reserve_mib=640, total_estimated_peak_plus_reserve_mib=512+count*512+640,
              estimate_basis="actual sequential worker RSS about308MiB; synthetic actual-input parity peak355.12MiB; budget512MiB each")
    return count


def orchestrate(desired):
    run = sf.Run(OUT)
    try:
        old_meta_path = OUT / "score_metadata.json"
        if old_meta_path.exists() and not (OUT / "score_metadata_sequential_before_parallel.json").exists():
            shutil.copyfile(old_meta_path, OUT / "score_metadata_sequential_before_parallel.json")
        before = json.loads((OUT / "source_checksums_before.json").read_text(encoding="utf-8"))
        for source, expected in before.items():
            if sf.sha256(Path(source)) != expected["sha256"]:
                raise AssertionError(f"Original frozen source changed: {source}")
        extra_before = sf.fingerprints([HELPER])
        extra_path = OUT / "parallel_helper_checksums_before.json"
        if extra_path.exists() and json.loads(extra_path.read_text(encoding="utf-8")) != extra_before:
            raise AssertionError("Parallel helper changed after launch")
        sf.atomic_json(extra_path, extra_before)
        count = aggregate_preflight(run, desired)
        manifest = json.loads((OUT / "staging_manifest.json").read_text(encoding="utf-8"))
        if manifest["rows"] != 3887065 or manifest["vessels"] != 7372:
            raise AssertionError("Unexpected approved cohort")
        if len(manifest["partitions"]) != 128 or any(Path(item["path"]).name != f"part_{pos:03d}.parquet"
                                                     for pos,item in enumerate(manifest["partitions"])):
            raise AssertionError("Expected all 128 ordered deterministic hash partitions")
        for item in manifest["partitions"]:
            if sf.sha256(OUT / item["path"]) != item["sha256"]:
                raise AssertionError("Staging hash changed")
        original_records = sf.read_checkpoints(OUT / "vessel_checkpoints.jsonl")
        assigned = {index: {} for index in range(count)}
        for rfid, rec in original_records.items():
            partition_index = zlib.crc32(rfid.encode("utf-8")) % manifest["partition_count"]
            assigned[partition_index % count][rfid] = rec
        run.save(stage="parallel_scoring", worker_count=count, rows=manifest["rows"], vessels=manifest["vessels"],
                 original_checkpoint_vessels=len(original_records), original_sources_sha256_verified=True,
                 parallel_helper_sha256=extra_before[str(HELPER)]["sha256"],
                 aggregate_memory_plan={"parent_peak_mib":512,"each_worker_peak_mib":512,"reserve_mib":640})
        children = []
        for index in range(count):
            directory = OUT / "workers" / f"worker_{index}"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "vessel_checkpoints.jsonl"
            existing = sf.read_checkpoints(path)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                for rfid, rec in assigned[index].items():
                    if rfid in existing:
                        if existing[rfid] != rec:
                            raise AssertionError("Original/worker checkpoint mismatch")
                    else:
                        handle.write(json.dumps(rec, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            stdout = (directory / "stdout.log").open("ab")
            stderr = (directory / "stderr.log").open("ab")
            child = subprocess.Popen([sys.executable,"-B","-u",str(HELPER),"--worker",str(index),"--workers",str(count)],
                                     cwd=sf.ROUND_DIR,stdout=stdout,stderr=stderr,
                                     creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            children.append((index,child,stdout,stderr))
            run.event("parallel_worker_launched", worker_index=index, pid=child.pid,
                      original_checkpoint_vessels=len(assigned[index]))
        last = 0.0
        while any(child.poll() is None for _,child,_,_ in children):
            if time.perf_counter() - last >= 30:
                states=[]
                for index,child,_,_ in children:
                    path=OUT / "workers" / f"worker_{index}" / "score_metadata.json"
                    state=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                    states.append({"worker_index":index,"pid":child.pid,"exit_code":child.poll(),
                                   "status":state.get("status","starting"),"vessels_completed":state.get("vessels_completed",0),
                                   "rows_completed":state.get("rows_completed",0)})
                vessels=sum(state["vessels_completed"] for state in states)
                rows=sum(state["rows_completed"] for state in states)
                run.event("parallel_progress",vessels_completed=vessels,rows_completed=rows,workers=states)
                run.save(vessels_completed=vessels,rows_completed=rows,workers=states)
                last=time.perf_counter()
            time.sleep(2)
        for _,child,stdout,stderr in children:
            stdout.close()
            stderr.close()
        if any(child.returncode != 0 for _,child,_,_ in children):
            raise RuntimeError(f"Worker exit failures: {[(i,p.returncode) for i,p,_,_ in children]}")
        run.preflight("merge_disjoint_worker_checkpoints")
        records={}
        errors=0
        worker_meta=[]
        for index in range(count):
            directory=OUT / "workers" / f"worker_{index}"
            state=json.loads((directory / "score_metadata.json").read_text(encoding="utf-8"))
            if state["status"] not in ("complete","complete_with_vessel_errors"):
                raise AssertionError("Worker incomplete")
            local=sf.read_checkpoints(directory / "vessel_checkpoints.jsonl")
            if set(records).intersection(local):
                raise AssertionError("Worker vessel sets overlap")
            records.update(local)
            errors+=state["vessel_error_records"]
            worker_meta.append(state)
        if len(records)!=7372 or sum(rec["n_rows"] for rec in records.values())!=3887065:
            raise AssertionError("Merged cohort conservation failed")
        for rfid,rec in original_records.items():
            if records[rfid]!=rec:
                raise AssertionError("Original checkpoint modified")
        tmp=OUT / "vessel_peaks.csv.tmp"
        with tmp.open("w",encoding="utf-8-sig",newline="") as handle:
            writer=csv.DictWriter(handle,fieldnames=sf.OUTPUT_COLS)
            writer.writeheader()
            writer.writerows(records[rfid] for rfid in sorted(records))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp,OUT / "vessel_peaks.csv")
        after=sf.fingerprints([Path(source) for source in before])
        extra_after=sf.fingerprints([HELPER])
        sf.atomic_json(OUT / "source_checksums_after.json",after)
        sf.atomic_json(OUT / "parallel_helper_checksums_after.json",extra_after)
        if after!=before or extra_after!=extra_before:
            raise AssertionError("Source/reference/scorer/helper changed during parallel run")
        result={"status":"complete" if errors==0 else "complete_with_vessel_errors","stage":"finished",
                "completed_at":sf.now(),"rows":3887065,"vessels":7372,
                "rows_completed":3887065,"vessels_completed":7372,"vessel_error_records":errors,
                "n_finite_scores":sum(rec["n_finite_scores"] for rec in records.values()),
                "vessels_without_finite_scores":sum(rec["n_finite_scores"]==0 for rec in records.values()),
                "source_checksums_match":True,"parallel_helper_checksums_match":True,
                "output_sha256":sf.sha256(OUT / "vessel_peaks.csv"),
                "invalid_centroid_rows":manifest["invalid_centroid_rows"],
                "min_ts":manifest["min_ts"],"max_ts":manifest["max_ts"],
                "worker_summaries":worker_meta,"original_checkpoint_vessels":len(original_records)}
        result["sum_of_worker_process_peak_mib"] = round(sum(item["observed_peak_process_mib"] for item in worker_meta),3)
        run.save(**result)
        run.event("parallel_scoring_complete",**{key:value for key,value in result.items() if key!="worker_summaries"})
        return 0
    except sf.MemoryPause as exc:
        run.save(status="paused_memory",reason=str(exc))
        run.event("stage_deferred_memory",reason=str(exc))
        return 75
    except Exception as exc:
        (OUT / "parallel_error_traceback.txt").write_text(traceback.format_exc(),encoding="utf-8")
        run.save(status="failed",exception_type=type(exc).__name__,reason=str(exc))
        run.event("parallel_failed",exception_type=type(exc).__name__,reason=str(exc))
        return 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--worker",type=int)
    args=parser.parse_args()
    if not 1<=args.workers<=4:
        raise SystemExit("One to four workers required")
    raise SystemExit(worker(args.worker,args.workers) if args.worker is not None else orchestrate(args.workers))
