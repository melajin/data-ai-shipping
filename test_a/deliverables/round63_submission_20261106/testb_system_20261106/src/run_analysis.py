"""Reproduce the frozen baseline and create review evidence in a new directory."""
from __future__ import annotations

import argparse
import csv
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import time

PACKAGE = Path(__file__).resolve().parents[1]
NUMERIC = ("s_zone", "s_change", "s_gap", "score")
INPUT_COLUMNS = ("rfid_id", "ts", "source_ordinal", "rfid_time", "len_m", "bbox_m",
                 "cen_lon", "cen_lat", "n_coords")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def memory_preflight(expected_mib=512, reserve_mib=640) -> dict:
    """One fresh read before imports/loading; never poll or terminate processes."""
    if os.name == "nt":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        *[(name, ctypes.c_ulonglong) for name in
                          ("total", "available", "total_page", "available_page",
                           "total_virtual", "available_virtual", "extended")]]
        status = Status()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise MemoryError("Available RAM unknown; workload deferred")
        available = int(status.available)
    else:
        available = None
        with Path("/proc/meminfo").open(encoding="ascii") as source:
            for line in source:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
                    break
        if available is None:
            raise MemoryError("Available RAM unknown; workload deferred")
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(),
                "available_mib": available / 2 ** 20, "expected_peak_mib": expected_mib,
                "reserve_mib": reserve_mib, "passed": available >= (expected_mib + reserve_mib) * 2 ** 20,
                "estimate_basis": "Sequential 46705x9 projection, ~62MB frozen arrays, numpy/pandas/scipy; no training",
                "other_processes": "Their use is reflected in fresh OS available RAM; no process intervention"}
    if not evidence["passed"]:
        raise MemoryError("Insufficient RAM; workload deferred: " + json.dumps(evidence))
    return evidence


def process_peak_mib() -> float | None:
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong),
                        *[(name, ctypes.c_size_t) for name in
                          ("peak_working_set", "working_set", "quota_peak_paged", "quota_paged",
                           "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile")]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.peak_working_set / 2 ** 20
        return None
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / (2 ** 20 if sys.platform == "darwin" else 1024)
    except ImportError:
        return None


def label(hour: int) -> str:
    stamp = datetime(1970, 1, 1) + timedelta(hours=int(hour))
    return f"{stamp:%Y%m%d} {stamp.hour}"


def select_peak(vessel):
    """Original run.py rule: maximum score, then smallest source_ordinal."""
    valid = vessel[vessel["score"].map(math.isfinite)]
    if valid.empty:
        raise ValueError("No finite frozen baseline score")
    best = valid[valid["score"] == valid["score"].max()]
    return best.sort_values("source_ordinal", kind="stable").iloc[0], len(best)


def distribution(series) -> dict:
    return {"count": int(series.count()), "min": float(series.min()), "p25": float(series.quantile(.25)),
            "median": float(series.median()), "p75": float(series.quantile(.75)),
            "max": float(series.max()), "mean": float(series.mean()), "std": float(series.std())}


def compare_rows(actual, expected) -> dict:
    import numpy as np
    actual = actual.sort_values("source_ordinal").reset_index(drop=True)
    expected = expected.sort_values("source_ordinal").reset_index(drop=True)
    keys = ["rfid_id", "ts", "source_ordinal"]
    if len(actual) != len(expected) or not actual[keys].equals(expected[keys]):
        raise ValueError("Input/source row alignment differs from frozen expected results")
    differences, nan_mismatches, exact = {}, {}, {}
    for column in NUMERIC:
        left, right = actual[column].to_numpy(), expected[column].to_numpy()
        nan_mismatches[column] = int(np.count_nonzero(np.isnan(left) != np.isnan(right)))
        good = np.isfinite(left) & np.isfinite(right)
        differences[column] = float(np.max(np.abs(left[good] - right[good]))) if np.any(good) else 0.0
        exact[column] = bool(np.array_equal(left, right, equal_nan=True))
    states = int((actual["state"] != expected["state"]).sum())
    return {"rows_compared": len(actual), "numeric_max_abs_diff": differences,
            "nan_mask_mismatches": nan_mismatches, "numeric_exact": exact,
            "state_mismatches": states, "all_row_checks_passed": all(exact.values()) and states == 0}


def candidate_records(scored, stored, roster):
    """Descriptive review rows, retaining missing exact predecessor hours."""
    expected = stored.set_index("source_ordinal")
    records = []
    for rfid in roster:
        vessel = scored[scored["rfid_id"] == rfid].sort_values(
            ["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
        peak, ties = select_peak(vessel)
        peak_ordinal, peak_hour = int(peak["source_ordinal"]), int(peak["ts"])
        prior = int(vessel.index[vessel["source_ordinal"] == peak_ordinal][0])
        components = {key: float(peak[key]) for key in NUMERIC[:3] if math.isfinite(float(peak[key]))}
        largest = max(components.values())
        dominant = "+".join(key for key, value in components.items() if value == largest)
        saved_score = float(expected.loc[peak_ordinal, "score"])
        rec = {"rfid_id": rfid, "rank_by_peak": None, "lead_label": label(peak_hour),
               "lead_ts": peak_hour, "source_ordinal": peak_ordinal, "score": float(peak["score"]),
               "stored_score": saved_score, "score_abs_diff": abs(float(peak["score"]) - saved_score),
               "state": peak["state"],
               **{key: float(peak[key]) if math.isfinite(float(peak[key])) else None for key in NUMERIC[:3]},
               "dominant_component": dominant, "component_count": len(components),
               **{key: float(peak[key]) for key in ("len_m", "bbox_m", "cen_lon", "cen_lat")},
               "n_coords": int(peak["n_coords"]), "n_observations": len(vessel),
               "prior_observation_count": prior, "first_observed_label": label(vessel["ts"].min()),
               "last_observed_label": label(vessel["ts"].max()),
               "observed_span_hours": int(vessel["ts"].max() - vessel["ts"].min()),
               "duplicate_timestamp_rows": int(vessel["ts"].duplicated().sum()), "peak_tie_count": ties}
        by_hour = dict(zip(vessel["ts"], vessel["score"]))
        for offset in (3, 2, 1):
            value = by_hour.get(peak_hour - offset)
            observed = value is not None and math.isfinite(float(value))
            rec[f"reference{offset}_label"] = label(peak_hour - offset) if observed else None
            rec[f"reference{offset}_score"] = float(value) if observed else None
            rec[f"reference{offset}_status"] = "observed" if observed else "not_observed_exact_hour"
        rec["reason"] = (
            f"전체 저장기간 최고점 {rec['score']:.6f}; 동률 {ties}행 중 최소 원행번호 선택. "
            f"가용 구성요소 {len(components)}개 평균, 최대 구성 {dominant}. "
            f"앞선 관측 {prior}행. 사고 정답·확률·실시간 가용성은 미확인."
        )
        records.append(rec)
    ranked = sorted(records, key=lambda row: (-row["score"], row["rfid_id"]))
    for number, row in enumerate(ranked, 1):
        row["rank_by_peak"] = number
    cases = [("highest_score", ranked[0]), ("median_peak_rank", ranked[(len(ranked) - 1) // 2]),
             ("least_prior_history", min(records, key=lambda row: (row["prior_observation_count"], row["rfid_id"])))]
    sample_cases = [{"case_type": name, **{key: row[key] for key in
                    ("rfid_id", "lead_ts", "lead_label", "score", "prior_observation_count")}}
                    for name, row in cases]
    return records, sample_cases


def validate_manifest(config, package: Path) -> dict:
    if config.get("mode") != "frozen_baseline_reproduction" or config.get("training_enabled") is not False:
        raise ValueError("Only frozen baseline reproduction is supported")
    if config.get("threshold") is not None or config.get("external_delivery_enabled") is not False:
        raise ValueError("Thresholds and external delivery must remain disabled")
    paths = {}
    for relative, expected_hash in config["artifacts"].items():
        path = (package / relative).resolve()
        if not path.is_relative_to(package.resolve()) or not path.is_file():
            raise ValueError(f"Artifact outside package or absent: {relative}")
        if sha256(path) != expected_hash:
            raise ValueError(f"Frozen artifact hash mismatch: {relative}")
        paths[relative] = expected_hash
    return paths


def run(output: Path, package: Path = PACKAGE) -> dict:
    started = time.perf_counter()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"New output directory required: {output}")
    config_path = package / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    preflight = memory_preflight()
    hashes = validate_manifest(config, package)
    # Heavy dependencies are deliberately imported only after a fresh RAM gate.
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq
    from frozen_baseline import load_references, score_vessel

    observations = pq.read_table(package / "data/observations.parquet", columns=list(INPUT_COLUMNS)).to_pandas()
    stored = pq.read_table(package / "data/stored_expected.parquet").to_pandas()
    with (package / "data/roster.csv").open(encoding="utf-8-sig", newline="") as source:
        roster = [row["rfid_id"] for row in csv.DictReader(source)]
    if len(roster) != 100 or len(set(roster)) != 100 or len(observations) != 46705:
        raise ValueError("Frozen input cohort must contain 100 vessels and 46705 rows")
    if set(observations["rfid_id"]) != set(roster) or observations["source_ordinal"].duplicated().any():
        raise ValueError("Input roster or source ordinal uniqueness mismatch")
    nearest, fine, coarse, norm_gap, norm_jump, reference_meta = load_references(package / "model")
    results = []
    for number, rfid in enumerate(roster, 1):
        vessel = observations[observations["rfid_id"] == rfid].sort_values(
            ["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
        results.append(score_vessel(vessel, nearest, None, fine, coarse, norm_gap, norm_jump))
        if number % 10 == 0:
            print(f"Rescored {number}/100 vessels", flush=True)
    scored = pd.concat(results, ignore_index=True)
    parity = compare_rows(scored, stored)
    candidates, cases = candidate_records(scored, stored, roster)
    with (package / "data/stored_candidates.csv").open(encoding="utf-8-sig", newline="") as source:
        expected_candidates = {row["rfid_id"]: row for row in csv.DictReader(source)}
    parity["candidate_time_mismatches"] = sum(row["lead_label"] != expected_candidates[row["rfid_id"]]["A"] for row in candidates)
    parity["candidate_source_ordinal_mismatches"] = sum(row["source_ordinal"] != int(expected_candidates[row["rfid_id"]]["source_ordinal"]) for row in candidates)
    parity["candidate_score_max_abs_diff"] = max(abs(row["score"] - float(expected_candidates[row["rfid_id"]]["score"])) for row in candidates)
    parity["all_checks_passed"] = (parity["all_row_checks_passed"]
                                    and parity["candidate_time_mismatches"] == 0
                                    and parity["candidate_source_ordinal_mismatches"] == 0
                                    and parity["candidate_score_max_abs_diff"] == 0)
    if not parity["all_checks_passed"]:
        raise ValueError("Frozen baseline reproduction differs: " + json.dumps(parity))
    source_provenance = json.loads((package / "model/provenance.json").read_text(encoding="utf-8"))
    # Scores are retrospective evidence; this program does not emit submission rows.
    output.mkdir(parents=True, exist_ok=False)
    scored.to_parquet(output / "scored_rows.parquet", index=False)
    with (output / "candidates.csv").open("x", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(candidates[0]))
        writer.writeheader()
        writer.writerows(candidates)
    candidate_scores = pd.Series([row["score"] for row in candidates])
    summary = {
        "schema_version": "testb_frozen_reproduction_v1", "mode": config["mode"], "status": "complete",
        "counts": {"observations": len(scored), "vessels": len(roster), "candidates": len(candidates)},
        "parity": parity, "score_distribution": distribution(scored["score"]),
        "candidate_score_distribution": distribution(candidate_scores),
        "coverage": {"first_observed_label": label(scored["ts"].min()),
                     "last_observed_label": label(scored["ts"].max()),
                     "time_unit": "original integer epoch hours; naive source label",
                     "timezone_status": "unconfirmed", "availability_status": "unconfirmed",
                     "n_rows_min": min(row["n_observations"] for row in candidates),
                     "n_rows_max": max(row["n_observations"] for row in candidates),
                     "prior_history_min": min(row["prior_observation_count"] for row in candidates),
                     "prior_history_max": max(row["prior_observation_count"] for row in candidates),
                     "exact_preceding_hours": {str(offset): sum(row[f"reference{offset}_status"] == "observed" for row in candidates) for offset in (3, 2, 1)},
                     "component_missing_counts": {key: int(scored[key].isna().sum()) for key in NUMERIC[:3]},
                     "state_counts": {str(key): int(value) for key, value in scored["state"].value_counts().items()}},
        "selection": {"mode": "retrospective_full_period_maximum", "tie_policy": "maximum score then minimum original source_ordinal",
                      "vessels_with_peak_ties": sum(row["peak_tie_count"] > 1 for row in candidates),
                      "maximum_peak_tie_count": max(row["peak_tie_count"] for row in candidates),
                      "reference_hours_policy": "exact t-3/t-2/t-1 if observed; last source ordinal within identical hour"},
        "component_description": {"s_zone": "prior visited cells plus frozen training density",
                                  "s_change": "prior >=24 observations: robust length/extent ratio and heuristic state surprise",
                                  "s_gap": "frozen training quantiles of inter-observation hour gap and centroid separation",
                                  "score": "arithmetic mean of finite components clipped to [1e-6,1]",
                                  "dominance_caution": "largest component is descriptive, not causal attribution or an accident explanation"},
        "sample_cases": cases, "reference_meta": reference_meta, "memory_preflight": preflight,
        "telemetry": {"elapsed_seconds": time.perf_counter() - started, "process_peak_mib": process_peak_mib(),
                      "python": sys.version.split()[0], "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pyarrow", "scipy")}},
        "source_provenance": source_provenance, "verified_artifact_hashes": hashes,
        "config_sha256": sha256(config_path),
        "output_sha256": {name: sha256(output / name) for name in ("scored_rows.parquet", "candidates.csv")},
        "limitations": ["Frozen old baseline reproduced; no improved model or confirmed Test B accident accuracy",
                        "Heuristic state names are not verified operation labels",
                        "Centroids/length/extent are supplied geometry summaries, not timestamped GPS or speed",
                        "Availability and timezone unconfirmed: this retrospective run is not live causal validation",
                        "No training, threshold calibration, external delivery, or submission workbook created",
                        "Prior references preserve old behavior; official auxiliary-column meaning remains unconfirmed"],
    }
    with (output / "summary.json").open("x", encoding="utf-8") as target:
        json.dump(summary, target, indent=2, ensure_ascii=False, allow_nan=False)
        target.write("\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New output directory; existing paths are refused")
    args = parser.parse_args(argv)
    try:
        summary = run(args.output.resolve())
    except (OSError, ValueError, MemoryError) as exc:
        parser.exit(2, f"run_analysis: {exc}\n")
    print(json.dumps({"status": summary["status"], "counts": summary["counts"], "parity": summary["parity"],
                      "elapsed_seconds": summary["telemetry"]["elapsed_seconds"],
                      "process_peak_mib": summary["telemetry"]["process_peak_mib"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
