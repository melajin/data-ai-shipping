"""Independent structural/provenance checks for completed unlabeled fleet output."""
import csv
import json
import math
import sys
import zlib
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
import psutil
import score_fleet as sf

OUT = sf.ROUND_DIR / "execution_001"
INT_COLS = {"n_rows", "peak_ts", "n_unique_hours", "n_finite_scores"}
FLOAT_COLS = {"peak_score", "median_score", "p95_score", "gap_total_h", "activity_radius_km"}


def checkpoints(path):
    result = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            assert line.endswith("\n"), "Incomplete checkpoint tail in completed execution"
            rec = json.loads(line)
            assert rec["rfid_id"] not in result
            result[rec["rfid_id"]] = rec
    return result


def main():
    state = json.loads((OUT / "score_metadata.json").read_text(encoding="utf-8"))
    if state.get("status") != "complete" or state.get("stage") != "finished":
        print("Scoring is incomplete; completion audit deferred")
        return 2
    available = psutil.virtual_memory().available / sf.MIB
    assert available >= 768, "Completion audit deferred: estimated128MiB plus640MiB reserve"
    assert state["rows"] == state["rows_completed"] == 3_887_065
    assert state["vessels"] == state["vessels_completed"] == 7_372
    assert state["vessel_error_records"] == 0
    assert state["source_checksums_match"] and state["parallel_helper_checksums_match"]
    for prefix in ("source_checksums", "parallel_helper_checksums"):
        before = json.loads((OUT / f"{prefix}_before.json").read_text(encoding="utf-8"))
        after = json.loads((OUT / f"{prefix}_after.json").read_text(encoding="utf-8"))
        assert before == after
        assert sf.fingerprints([Path(path) for path in before]) == before
    output = OUT / "vessel_peaks.csv"
    assert sf.sha256(output) == state["output_sha256"]
    records = {}
    with output.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == sf.OUTPUT_COLS
        for row in reader:
            rec = {key: (None if value == "" else int(value) if key in INT_COLS
                         else float(value) if key in FLOAT_COLS else value)
                   for key, value in row.items()}
            rfid = rec["rfid_id"]
            assert rfid not in records
            assert 0 < rec["n_unique_hours"] <= rec["n_rows"]
            assert 0 <= rec["n_finite_scores"] <= rec["n_rows"]
            assert rec["gap_total_h"] >= 0
            assert rec["activity_radius_km"] is None or (math.isfinite(rec["activity_radius_km"]) and rec["activity_radius_km"] >= 0)
            if rec["n_finite_scores"]:
                assert sf.START_H <= rec["peak_ts"] < sf.END_H
                assert rec["peak_state"]
                assert 0 <= rec["peak_score"] <= 1
            else:
                assert all(rec[key] is None for key in ("peak_score", "peak_ts", "peak_state", "median_score", "p95_score"))
            records[rfid] = rec
    assert len(records) == 7_372 and sum(rec["n_rows"] for rec in records.values()) == 3_887_065
    original = checkpoints(OUT / "vessel_checkpoints.jsonl")
    for rfid, rec in original.items():
        assert records[rfid] == rec
        assert rec["n_finite_scores"] > 0
    root_errors = OUT / "vessel_errors.jsonl"
    assert not root_errors.exists() or root_errors.stat().st_size == 0
    manifest = json.loads((OUT / "staging_manifest.json").read_text(encoding="utf-8"))
    full_paths = {(OUT / item["path"]).resolve() for item in manifest["partitions"]}
    assigned_paths = set()
    merged = {}
    count = state["worker_count"]
    worker_peaks = []
    for index in range(count):
        directory = OUT / "workers" / f"worker_{index}"
        local = checkpoints(directory / "vessel_checkpoints.jsonl")
        assert not set(local).intersection(merged)
        assert all(zlib.crc32(rfid.encode("utf-8")) % 128 % count == index for rfid in local)
        for rfid, rec in local.items():
            assert records[rfid] == rec
        merged.update(local)
        assigned = json.loads((directory / "assigned_manifest.json").read_text(encoding="utf-8"))
        paths = {(directory / item["path"]).resolve() for item in assigned["partitions"]}
        assert not paths.intersection(assigned_paths)
        assigned_paths.update(paths)
        local_state = json.loads((directory / "score_metadata.json").read_text(encoding="utf-8"))
        assert local_state["status"] == "complete" and local_state["vessel_error_records"] == 0
        worker_peaks.append(local_state["observed_peak_process_mib"])
        error_file = directory / "vessel_errors.jsonl"
        assert not error_file.exists() or error_file.stat().st_size == 0
    assert merged == records and assigned_paths == full_paths
    guard = json.loads((OUT / "parallel_runtime_guard.json").read_text(encoding="utf-8"))
    assert guard["single_active_orchestrator"] and guard["original_error_records"] == 0
    assert guard["original_all_checkpoint_records_finite"] and guard["worker_count"] == count
    current_orchestrators, current_workers, current_original = [], [], []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            args = process.info["cmdline"] or []
            if any(str(arg).endswith("score_fleet_parallel.py") for arg in args):
                (current_workers if "--worker" in args else current_orchestrators).append(process.pid)
            if any(str(arg).endswith("score_fleet.py") for arg in args):
                current_original.append(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    assert len(current_orchestrators) <= 1 and not current_workers and not current_original
    result = {"status": "passed", "audited_at": sf.now(), "rows": 3_887_065, "vessels": 7_372,
              "n_finite_scores": sum(rec["n_finite_scores"] for rec in records.values()),
              "vessels_without_finite_scores": sum(rec["n_finite_scores"] == 0 for rec in records.values()),
              "source_reference_scorer_helper_hashes_match_live_files": True,
              "final_csv_equals_all_worker_checkpoints": True, "all_128_partitions_owned_exactly_once": True,
              "all_original_seeded_checkpoints_equal_final": True, "original_seeded_vessels": len(original),
              "original_seeded_error_records": 0, "active_parallel_worker_pids": current_workers,
              "active_original_scorer_pids": current_original, "active_orchestrator_pids": current_orchestrators,
              "runtime_single_orchestrator_guard_passed": True,
              "worker_process_peaks_mib": worker_peaks, "sum_worker_process_peaks_mib": round(sum(worker_peaks), 3),
              "memory_preflight": {"at": sf.now(), "available_mib": round(available, 2),
                                   "expected_audit_peak_mib": 128, "reserve_mib": 640},
              "output_sha256": state["output_sha256"], "audit_script_sha256": sf.sha256(Path(__file__).resolve()),
              "labels_read": False, "training_performed": False}
    launch = json.loads((OUT / "score_launch_metadata.json").read_text(encoding="utf-8-sig"))
    result["overall_first_launch_to_completion_seconds"] = round((datetime.fromisoformat(state["completed_at"]) - datetime.fromisoformat(launch["started_at"])).total_seconds(), 3)
    sf.atomic_json(OUT / "score_completion_audit.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
