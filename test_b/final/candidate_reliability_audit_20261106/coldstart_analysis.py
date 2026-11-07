"""Read-only descriptive audit of the existing 100 per-vessel peak candidates.

No score, model parameter, threshold, or candidate is fitted or replaced. The
24-row split is the pre-existing s_change history requirement. CSV outputs are
analysis intermediates, not a workbook. Source timestamps are naive epoch hours
whose timezone/availability semantics remain unconfirmed.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EPOCH = datetime(1970, 1, 1)
GROUPS = ("all_100", "prior_lt24_39", "prior_ge24_61")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path, records):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def label(hour):
    date = EPOCH + timedelta(hours=int(hour))
    return f"{date:%Y%m%d} {date.hour}"


def date_of(hour):
    return EPOCH + timedelta(hours=int(hour))


def memory_preflight():
    # One fresh check immediately before numerical imports/loading. No polling.
    command = (
        "$os=Get-CimInstance Win32_OperatingSystem; "
        "$top=@(Get-Process | Sort-Object WorkingSet64 -Descending | "
        "Select-Object -First 8 ProcessName,Id,@{n='working_set_mib';"
        "e={[math]::Round($_.WorkingSet64/1MB,2)}}); "
        "[pscustomobject]@{checked_at=(Get-Date).ToString('o');"
        "available_mib=[double]$os.FreePhysicalMemory/1024;"
        "total_mib=[double]$os.TotalVisibleMemorySize/1024;"
        "top_processes=$top} | ConvertTo-Json -Depth 4 -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    evidence = json.loads(result.stdout)
    evidence.update({
        "expected_peak_mib": 250,
        "reserve_mib": 640,
        "estimate_basis": (
            "One sequential pyarrow/numpy process; 46705 x 14 input columns, "
            "3.62MB Parquet uncompressed; numeric arrays <6MiB, string objects "
            "and group indices <20MiB, import/runtime allowance <200MiB. "
            "No pandas/scipy, training, plot rendering, or parallel loading."
        ),
        "other_work": "Concurrent workers are included in fresh OS available RAM; top processes captured.",
    })
    evidence["passed"] = evidence["available_mib"] >= 890
    return evidence


def peak_working_set_mib():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong),
                    *[(name, ctypes.c_size_t) for name in
                      ("peak_ws", "ws", "qpp", "qp", "qpnp", "qnp", "pf", "peak_pf")]]
    value = Counters()
    value.cb = ctypes.sizeof(value)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(value), value.cb):
        raise OSError("Process peak working set unavailable")
    return value.peak_ws / 2**20


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=ROOT / "deliverables/testb_system_20261106/results/reproduction_001")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--vessel-balanced-exposure", action="store_true",
                        help="Also average each vessel's observed-row window share equally.")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "coldstart_summary.json"
    preflight = memory_preflight()
    if not preflight["passed"]:
        summary_path.write_text(json.dumps({"status": "deferred_memory", "memory": preflight},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(75)

    import numpy as np
    import pyarrow.parquet as pq

    paths = {name: args.input_dir / name for name in ("candidates.csv", "scored_rows.parquet")}
    hashes_before = {name: sha256(path) for name, path in paths.items()}
    with paths["candidates.csv"].open(encoding="utf-8-sig", newline="") as source:
        candidates = list(csv.DictReader(source))
    table = pq.read_table(paths["scored_rows.parquet"], use_threads=False)
    columns = {name: table[name].combine_chunks().to_numpy(zero_copy_only=False)
               for name in table.column_names}
    ids, ts, ordinals = (columns[name] for name in ("rfid_id", "ts", "source_ordinal"))
    assert len(candidates) == len(set(c["rfid_id"] for c in candidates)) == 100
    assert len(set(map(int, ordinals))) == len(ordinals) == 46705
    assert set(ids) == {c["rfid_id"] for c in candidates}
    ordinal_index = {int(ordinal): i for i, ordinal in enumerate(ordinals)}
    row_positions = np.empty(len(ids), dtype=np.int64)
    elapsed = np.empty(len(ids), dtype=np.int64)
    ordered = {}
    for vessel in sorted(set(ids)):
        indices = np.flatnonzero(ids == vessel)
        indices = indices[np.lexsort((ordinals[indices], columns["rfid_time"][indices], ts[indices]))]
        ordered[vessel] = indices
        row_positions[indices] = np.arange(len(indices))
        elapsed[indices] = ts[indices] - ts[indices[0]]

    audited = []
    float_fields = ("score", "s_zone", "s_change", "s_gap", "len_m", "bbox_m", "cen_lon", "cen_lat")
    for candidate in candidates:
        vessel = candidate["rfid_id"]
        index = ordinal_index[int(candidate["source_ordinal"])]
        indices = ordered[vessel]
        position = int(row_positions[index])
        checks = {
            "vessel_matches": ids[index] == vessel,
            "timestamp_matches": int(ts[index]) == int(candidate["lead_ts"]),
            "label_matches": label(ts[index]) == candidate["lead_label"],
            "prior_count_matches": position == int(candidate["prior_observation_count"]),
            "strict_prior_timestamp_count_matches": int(np.sum(ts[indices] < ts[index])) == position,
            "n_observations_matches": len(indices) == int(candidate["n_observations"]),
            "first_label_matches": label(ts[indices[0]]) == candidate["first_observed_label"],
            "last_label_matches": label(ts[indices[-1]]) == candidate["last_observed_label"],
            "span_matches": int(ts[indices[-1]] - ts[indices[0]]) == int(candidate["observed_span_hours"]),
            "state_matches": columns["state"][index] == candidate["state"],
            "n_coords_matches": int(columns["n_coords"][index]) == int(candidate["n_coords"]),
        }
        for name in float_fields:
            original = float(candidate[name]) if candidate[name] else float("nan")
            actual = float(columns[name][index])
            checks[f"{name}_matches"] = (original == actual or (math.isnan(original) and math.isnan(actual)))
        finite_indices = indices[np.isfinite(columns["score"][indices])]
        maximum = float(np.max(columns["score"][finite_indices]))
        tied = finite_indices[columns["score"][finite_indices] == maximum]
        checks["existing_peak_rule_matches"] = int(ordinals[index]) == int(np.min(ordinals[tied]))
        checks["peak_tie_count_matches"] = len(tied) == int(candidate["peak_tie_count"])
        assert all(checks.values()), (vessel, checks)
        cold = position < 24
        assert cold == math.isnan(float(columns["s_change"][index]))
        record = {
            "rfid_id": vessel, "source_ordinal": int(ordinals[index]),
            "lead_label": candidate["lead_label"], "lead_ts": int(ts[index]),
            "score": float(columns["score"][index]), "cold_start_prior_lt24": cold,
            "prior_observation_count_stored": int(candidate["prior_observation_count"]),
            "prior_observation_count_recomputed": position,
            "strictly_earlier_timestamp_rows": int(np.sum(ts[indices] < ts[index])),
            "chronological_row_position_1based": position + 1,
            "n_observations": len(indices),
            "row_position_fraction_1based": (position + 1) / len(indices),
            "first_observed_label": label(ts[indices[0]]),
            "elapsed_since_first_hours": int(elapsed[index]),
            "elapsed_since_first_days": float(elapsed[index] / 24),
            "previous_observation_gap_hours": int(ts[index] - ts[indices[position - 1]]) if position else None,
            "candidate_day_of_year": date_of(ts[index]).timetuple().tm_yday,
            "first_observed_day_of_year": date_of(ts[indices[0]]).timetuple().tm_yday,
            "missing_s_change": math.isnan(float(columns["s_change"][index])),
            "component_count": int(candidate["component_count"]),
            **{key: bool(value) for key, value in checks.items()},
            "all_checks_passed": True,
        }
        audited.append(record)
    audited.sort(key=lambda x: x["rfid_id"])
    write_csv(args.output_dir / "coldstart_candidate_positions.csv", audited)
    cold_ids = {row["rfid_id"] for row in audited if row["cold_start_prior_lt24"]}
    assert len(cold_ids) == 39
    candidate_groups = {
        GROUPS[0]: audited,
        GROUPS[1]: [r for r in audited if r["cold_start_prior_lt24"]],
        GROUPS[2]: [r for r in audited if not r["cold_start_prior_lt24"]],
    }
    row_groups = {
        GROUPS[0]: np.ones(len(ids), dtype=bool),
        GROUPS[1]: np.isin(ids, list(cold_ids)),
        GROUPS[2]: ~np.isin(ids, list(cold_ids)),
    }

    def distribution(values):
        values = np.asarray(values, dtype=float)
        assert np.all(np.isfinite(values))
        q1, med, q3 = np.quantile(values, [.25, .5, .75], method="linear")
        return {"count": len(values), "min": float(np.min(values)), "q1": float(q1),
                "median": float(med), "mean": float(np.mean(values)), "q3": float(q3),
                "max": float(np.max(values)), "std_sample_ddof1": float(np.std(values, ddof=1)),
                "std_population_ddof0": float(np.std(values, ddof=0))}

    score_stats = [{"group": name, **distribution([r["score"] for r in records])}
                   for name, records in candidate_groups.items()]
    write_csv(args.output_dir / "coldstart_score_summary.csv", score_stats)
    timing_stats = [{"group": name, "metric": metric, **distribution([r[metric] for r in records])}
                    for name, records in candidate_groups.items()
                    for metric in ("prior_observation_count_recomputed", "chronological_row_position_1based",
                                   "elapsed_since_first_hours", "row_position_fraction_1based")]
    write_csv(args.output_dir / "coldstart_timing_summary.csv", timing_stats)
    edges = np.linspace(0, 1, 26)
    histograms = {name: np.histogram([r["score"] for r in records], bins=edges)[0]
                  for name, records in candidate_groups.items()}
    hourly_hist = np.histogram(columns["score"], bins=edges)[0]
    histogram_rows = []
    for i in range(len(edges) - 1):
        record = {"bin_lower_inclusive": float(edges[i]), "bin_upper": float(edges[i + 1]),
                  "upper_inclusive": i == len(edges) - 2, "all_hourly_observed_rows": int(hourly_hist[i])}
        for name, counts in histograms.items():
            record[f"{name}_count"] = int(counts[i])
            record[f"{name}_fraction"] = float(counts[i] / len(candidate_groups[name]))
        histogram_rows.append(record)
    assert sum(hourly_hist) == len(ids)
    for name, counts in histograms.items():
        assert sum(counts) == len(candidate_groups[name])
    write_csv(args.output_dir / "coldstart_score_histogram.csv", histogram_rows)

    # Supplemental requested check: remove the 25 vessels whose total history
    # cannot ever reach the pre-existing 24-prior-row s_change requirement.
    supplemental_name = "prior_lt24_total_ge25_14"
    supplemental = [r for r in candidate_groups[GROUPS[1]] if r["n_observations"] >= 25]
    assert len(supplemental) == 14
    candidate_groups[supplemental_name] = supplemental
    row_groups[supplemental_name] = np.isin(ids, [r["rfid_id"] for r in supplemental])

    row_dates = np.asarray([date_of(t).strftime("%Y-%m-%d") for t in ts])
    for grain, row_keys, candidate_key in (
        ("daily", row_dates, lambda r: date_of(r["lead_ts"]).strftime("%Y-%m-%d")),
        ("monthly", np.asarray([d[:7] for d in row_dates]), lambda r: date_of(r["lead_ts"]).strftime("%Y-%m")),
    ):
        calendar_rows = []
        for period in sorted(set(row_keys)):
            date_mask = row_keys == period
            record = {"period": period,
                      "all_observed_rows": int(np.sum(date_mask)),
                      "all_observed_vessels": len(set(ids[date_mask])),
                      "observed_rows_with_prior_lt24": int(np.sum(date_mask & (row_positions < 24)))}
            for name, records in candidate_groups.items():
                count = sum(candidate_key(r) == period for r in records)
                observed = int(np.sum(date_mask & row_groups[name]))
                record[f"{name}_candidates"] = count
                record[f"{name}_candidate_fraction"] = count / len(records)
                record[f"{name}_observed_rows"] = observed
                record[f"{name}_observation_fraction"] = observed / int(np.sum(row_groups[name]))
            calendar_rows.append(record)
        for name, records in candidate_groups.items():
            assert sum(r[f"{name}_candidates"] for r in calendar_rows) == len(records)
        assert sum(r["all_observed_rows"] for r in calendar_rows) == len(ids)
        write_csv(args.output_dir / f"coldstart_{grain}_calendar.csv", calendar_rows)

    day_of_year = np.asarray([date_of(t).timetuple().tm_yday for t in ts])
    windows = []
    for name, records in candidate_groups.items():
        cohort_mask = row_groups[name]
        cohort_size = int(np.sum(cohort_mask))
        for basis, sizes in (("calendar_first_days_of_year", (7, 14, 31)),
                             ("elapsed_first_days_since_first_observation", (1, 7, 14, 31)),
                             ("chronological_first_rows", (24,))):
            for size in sizes:
                if basis == "calendar_first_days_of_year":
                    within = day_of_year <= size
                    candidate_count = sum(r["candidate_day_of_year"] <= size for r in records)
                elif basis == "elapsed_first_days_since_first_observation":
                    within = elapsed < size * 24
                    candidate_count = sum(r["elapsed_since_first_hours"] < size * 24 for r in records)
                else:
                    within = row_positions < size
                    candidate_count = sum(r["prior_observation_count_recomputed"] < size for r in records)
                observed = int(np.sum(within & cohort_mask))
                candidate_fraction = candidate_count / len(records)
                observed_fraction = observed / cohort_size
                record = {"group": name, "window_basis": basis, "window_size": size,
                          "candidate_count": candidate_count, "candidate_denominator": len(records),
                          "candidate_fraction": candidate_fraction, "observed_rows": observed,
                          "observation_denominator": cohort_size, "observed_row_fraction": observed_fraction,
                          "candidate_to_observation_share_ratio": candidate_fraction / observed_fraction if observed else None}
                if args.vessel_balanced_exposure:
                    balanced = float(np.mean([np.mean(within[ordered[r["rfid_id"]]]) for r in records]))
                    record["vessel_balanced_observation_fraction"] = balanced
                    record["candidate_to_vessel_balanced_share_ratio"] = candidate_fraction / balanced if balanced else None
                windows.append(record)
    write_csv(args.output_dir / "coldstart_windows_exposure.csv", windows)

    hashes_after = {name: sha256(path) for name, path in paths.items()}
    assert hashes_before == hashes_after
    summary = {
        "schema_version": "existing_candidate_coldstart_descriptive_audit_v1",
        "status": "complete", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_directory": str(args.input_dir.resolve()),
        "input_sha256_before": hashes_before, "input_sha256_after": hashes_after,
        "inputs_unchanged": hashes_before == hashes_after,
        "script_sha256": sha256(__file__),
        "memory": {**preflight, "observed_process_peak_working_set_mib": peak_working_set_mib()},
        "execution": {"numerical_library": "numpy", "parquet_library": "pyarrow",
                      "vessel_balanced_exposure_enabled": args.vessel_balanced_exposure,
                      "parallel_loading": False, "model_refit": False,
                      "new_score_or_detection_threshold": False, "candidate_reselection": False},
        "counts": {"observed_rows": len(ids), "vessels": len(ordered),
                   "existing_candidates": len(audited), "prior_lt24": len(cold_ids),
                   "prior_ge24": len(audited) - len(cold_ids),
                   "observed_rows_prior_lt24": int(np.sum(row_positions < 24)),
                   "vessels_total_observations_lt24": sum(len(v) < 24 for v in ordered.values()),
                   "vessels_total_observations_eq24": sum(len(v) == 24 for v in ordered.values()),
                   "vessels_total_observations_le24": sum(len(v) <= 24 for v in ordered.values()),
                   "cold_candidates_on_vessels_total_observations_lt24": sum(r["n_observations"] < 24 for r in candidate_groups[GROUPS[1]]),
                   "cold_candidates_on_vessels_total_observations_ge25": len(supplemental),
                   "zero_prior_candidates": sum(r["prior_observation_count_recomputed"] == 0 for r in audited),
                   "duplicate_timestamp_rows": sum(len(v) - len(set(map(int, ts[v]))) for v in ordered.values())},
        "coverage": {"first_label": label(np.min(ts)), "last_label": label(np.max(ts)),
                     "time_unit": "naive source integer epoch hours", "timezone_confirmed": False,
                     "availability_confirmed": False},
        "verification": {"matched_candidate_ordinals": len(audited), "all_candidate_checks_passed": True,
                         "prior_count_mismatches": 0, "candidate_score_mismatches": 0,
                         "candidate_peak_rule_mismatches": 0,
                         "cold_indicator_matches_missing_s_change": True,
                         "histogram_and_calendar_counts_reconcile": True},
        "definitions": {
            "cold_split": "Existing candidate prior_observation_count <24; descriptive split only, no replacement candidates.",
            "row_order": "rfid_id group sorted ts, rfid_time, source_ordinal; position is count of preceding observed rows.",
            "elapsed_hours": "candidate source hour minus vessel first observed source hour; not time since actual voyage start.",
            "sample_std": "ddof=1, matching existing run_analysis.distribution; population std also supplied.",
            "quartiles": "numpy linear interpolation (same as default pandas quantile).",
            "histogram": "Existing build_report.py bins=np.linspace(0,1,26); left-closed/right-open, final right edge inclusive.",
            "calendar_window": "Day of year <=7/14/31; data are confined to Jan-Jun 2025. Source timezone unknown.",
            "elapsed_window": "0 <= elapsed_hours < size*24.",
            "observation_exposure": "Observed-row count within window divided by all observed rows for the group's vessel cohort.",
            "vessel_balanced_exposure": "If enabled, equally weighted mean of each cohort vessel's observed-row window fraction; descriptive comparator, no significance test.",
            "share_ratios": "Descriptive concentration comparisons, not causal effects, calibrated likelihoods, F1, or false-positive rates.",
        },
        "score_summary": score_stats,
        "timing_summary": timing_stats,
        "window_exposure": windows,
        "supplemental_cold_candidates_total_observations_ge25": {
            "group": supplemental_name, "count": len(supplemental),
            "rfid_ids": [r["rfid_id"] for r in supplemental],
            "timing_summary": {metric: distribution([r[metric] for r in supplemental])
                               for metric in ("elapsed_since_first_hours", "prior_observation_count_recomputed",
                                              "n_observations")},
            "candidate_month_counts": {month: sum(date_of(r["lead_ts"]).strftime("%Y-%m") == month for r in supplemental)
                                       for month in sorted(set(d[:7] for d in row_dates))},
            "first_observed_month_counts": {month: sum(r["first_observed_label"][:6] == month.replace("-", "") for r in supplemental)
                                            for month in sorted(set(d[:7] for d in row_dates))},
            "note": "Existing cold candidates on vessels with sufficient total rows to eventually calculate s_change; no new candidate selected.",
        },
        "interpretation_limits": [
            "Sparse early history and calendar-start concentration can be compatible with left-truncated observation history, but cannot prove that missing pre-window observations caused the selected maximum.",
            "Vessel entry/coverage gaps, different observation counts, component availability and full-period peak selection are alternative contributors.",
            "Cold and supplemental-14 cohorts are conditioned on the existing peak's early row position; their within-cohort timing/exposure ratios are descriptive and are not independent validation or a causal test.",
            "No incident ground truth or real-time receipt history is assessed; removing these 39 existing peaks does not establish improved accuracy or lower false alarms.",
            "The remaining 61 candidates retain the original full-period maximum selection and are not a validated incident set.",
        ],
        "outputs": ["coldstart_candidate_positions.csv", "coldstart_score_summary.csv", "coldstart_timing_summary.csv",
                    "coldstart_score_histogram.csv", "coldstart_daily_calendar.csv", "coldstart_monthly_calendar.csv",
                    "coldstart_windows_exposure.csv", "coldstart_summary.json"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "counts": summary["counts"],
                      "peak_mib": summary["memory"]["observed_process_peak_working_set_mib"],
                      "score_summary": score_stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
