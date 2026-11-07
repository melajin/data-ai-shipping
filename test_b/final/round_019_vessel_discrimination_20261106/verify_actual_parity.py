"""One label-blind, complete-history input/score parity check during fleet run."""
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import psutil
import score_fleet as sf


def main():
    started = time.perf_counter()
    available = psutil.virtual_memory().available / sf.MIB
    processes = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            if info["memory_info"]:
                processes.append({"pid": info["pid"], "name": info["name"],
                                  "rss_mib": round(info["memory_info"].rss / sf.MIB, 2)})
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    processes.sort(key=lambda entry: entry["rss_mib"], reverse=True)
    output = sf.ROUND_DIR / "unlabeled_full_history_parity.json"
    result = {"started_at": sf.now(), "available_mib": round(available, 2),
              "expected_peak_process_mib": 512, "reserve_mib": 640,
              "memory_estimate_basis": "one 64K Arrow batch, one bounded partition, one full-history vessel; unchanged reference arrays loaded once",
              "other_processes": processes[:10], "labels_read": False,
              "selection_rule": "lexicographically first RFID in first deterministic hash partition"}
    if available < 1152:
        result.update(status="paused_memory")
        sf.atomic_json(output, result)
        return 75
    sf.load_stack()
    import pyarrow.compute as pc
    import frozen_baseline as fb

    out = sf.ROUND_DIR / "execution_001"
    manifest = json.loads((out / "staging_manifest.json").read_text(encoding="utf-8"))
    part = sf.pq.read_table(out / manifest["partitions"][0]["path"], use_threads=False)
    rfid = min(part["rfid_id"].to_pylist())
    staged = part.filter(pc.equal(part["rfid_id"], rfid)).to_pandas()
    direct_chunks = []
    input_rows_scanned = 0
    for month in range(1, 7):
        source = sf.DEFAULT_HOURLY / f"hourly_{month:02d}.parquet"
        for batch in sf.pq.ParquetFile(source).iter_batches(batch_size=65536, columns=sf.COLS, use_threads=False):
            table = sf.pa.Table.from_batches([batch])
            input_rows_scanned += len(table)
            selected = table.filter(pc.equal(table["rfid_id"], rfid))
            if len(selected):
                direct_chunks.append(selected)
    direct = sf.pa.concat_tables(direct_chunks).to_pandas()
    for frame in (direct, staged):
        frame["rfid_time"] = (frame.ts % 24).astype(int)
    sort_cols = ["ts", "rfid_time", "source_ordinal"]
    direct = direct.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    staged = staged.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    sf.pd.testing.assert_frame_equal(direct, staged, check_exact=True)
    nearest, fine, coarse, gap, jump, _ = fb.load_references(sf.REFERENCES)
    direct_scores = fb.score_vessel(direct, nearest, None, fine, coarse, gap, jump)
    staged_scores = fb.score_vessel(staged, nearest, None, fine, coarse, gap, jump)
    sf.pd.testing.assert_frame_equal(direct_scores, staged_scores, check_exact=True)
    expected = sf.summarize_vessel(rfid, direct, direct_scores, fb)
    observed = sf.summarize_vessel(rfid, staged, staged_scores, fb)
    assert expected == observed
    source_hashes = json.loads((out / "source_checksums_before.json").read_text(encoding="utf-8"))
    for source, expected_hash in source_hashes.items():
        assert sf.sha256(Path(source)) == expected_hash["sha256"]
    mi = psutil.Process().memory_info()
    result.update(status="passed", completed_at=sf.now(), elapsed_seconds=round(time.perf_counter()-started, 3),
                  rfid_id=rfid, n_rows=len(direct), input_rows_scanned=input_rows_scanned,
                  full_input_frame_exact=True, full_scored_frame_exact=True,
                  summary_exact=True, max_absolute_score_difference=0.0,
                  compared_score_columns=["state", "s_zone", "s_change", "s_gap", "score"],
                  sources_still_match_pre_run_checksums=True,
                  observed_peak_process_mib=round(getattr(mi, "peak_wset", mi.rss)/sf.MIB, 2))
    sf.atomic_json(output, result)
    print(json.dumps({key: result[key] for key in ("status", "rfid_id", "n_rows", "elapsed_seconds", "observed_peak_process_mib")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(sf.FROZEN.parent))
    raise SystemExit(main())
