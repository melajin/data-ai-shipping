"""Independent, bounded-memory final audit. Never imports the evaluator/scorer.

Run only after the completed evaluation is authorized for inspection. Reads
small vessel tables and streams source hashes; writes no files or data changes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
OUT = BASE / "execution_001"
METRICS = ("peak_score", "p95_score", "median_score", "n_rows", "gap_total_h", "activity_radius_km")
PROTOCOL_HASH = "10fe34978e36774f7a63ed12c889871a2b2a0edeec77e9380d7f50b016645f0a"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def number(value):
    return None if value is None or value == "" else float(value)


def near(actual, expected, name, tolerance=1e-10):
    if actual is None or expected is None:
        assert actual is expected, (name, actual, expected)
    else:
        assert math.isfinite(actual) and abs(actual - expected) <= tolerance, (name, actual, expected)


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def finite(value):
    return value is not None and math.isfinite(value)


def direct_smd(sets, records, column):
    positive, control, weights = [], [], []
    for p, controls in sets:
        counts = [c for c in controls if finite(records[c][column]) and records[c][column] > 0]
        if not counts or not finite(records[p][column]) or records[p][column] <= 0:
            continue
        positive.append(math.log(records[p][column]))
        control.extend(math.log(records[c][column]) for c in counts)
        weights.extend([1 / len(counts)] * len(counts))
    if not positive:
        return None
    pm = statistics.fmean(positive)
    cm = sum(x * w for x, w in zip(control, weights)) / sum(weights)
    pv = statistics.fmean((x - pm) ** 2 for x in positive)
    cv = sum(w * (x - cm) ** 2 for x, w in zip(control, weights)) / sum(weights)
    scale = math.sqrt((pv + cv) / 2)
    return (pm - cm) / scale if scale else (0.0 if pm == cm else None)


def main():
    # This process has only standard-library imports until the fresh RAM check.
    import psutil
    memory = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "available_mib": psutil.virtual_memory().available / 2**20,
              "expected_peak_mib": 512, "reserve_mib": 640,
              "estimate_basis": "7372 stdlib CSV records, scalar pairwise loops, <=1MiB streamed hash block; no hourly loading or dense pair matrix",
              "other_processes": []}
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            item = process.info
            if item["memory_info"]:
                memory["other_processes"].append({"pid": item["pid"], "name": item["name"], "rss_mib": item["memory_info"].rss / 2**20})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    memory["other_processes"] = sorted(memory["other_processes"], key=lambda x: -x["rss_mib"])[:8]
    if memory["available_mib"] < 1152:
        print(json.dumps({"status": "deferred_memory", "memory": memory}))
        return 75

    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((OUT / "score_metadata.json").read_text(encoding="utf-8"))
    assert summary["stage"] == "evaluation_complete"
    assert metadata["status"] == "complete" and metadata["vessel_error_records"] == 0
    assert metadata["rows_completed"] == 3887065 and metadata["vessels_completed"] == 7372
    assert 490896 <= metadata["min_ts"] <= metadata["max_ts"] < 495240
    assert digest(BASE / "PROTOCOL.md") == PROTOCOL_HASH
    assert digest(OUT / "vessel_peaks.csv") == metadata["output_sha256"]
    hash_files = 0
    for prefix in ("source", "parallel_helper"):
        before = json.loads((OUT / f"{prefix}_checksums_before.json").read_text(encoding="utf-8"))
        after = json.loads((OUT / f"{prefix}_checksums_after.json").read_text(encoding="utf-8"))
        assert before == after
        if prefix == "source":
            assert sorted(Path(p).name for p in before if Path(p).name.startswith("hourly_")) == [f"hourly_{month:02d}.parquet" for month in range(1, 7)]
        for path, item in before.items():
            assert digest(path) == item["sha256"], path
            assert Path(path).stat().st_size == item["bytes"], path
            hash_files += 1
    provenance = summary["provenance"]
    assert provenance["sha256_before"] == provenance["sha256_after"]
    for key, path in provenance["paths"].items():
        assert digest(path) == provenance["sha256_before"][key], key
        hash_files += 1

    rows = read_csv(OUT / "evaluation_vessels.csv")
    assert len(rows) == 7372 and len({r["rfid_id"] for r in rows}) == 7372
    records = {}
    for row in rows:
        item = {m: number(row[m]) for m in (*METRICS, "n_finite_scores")}
        item["linked"] = row["is_provisional_linked"].lower() == "true"
        assert item["n_rows"] >= 1 and item["n_rows"].is_integer()
        assert item["n_finite_scores"].is_integer() and 0 <= item["n_finite_scores"] <= item["n_rows"]
        scores = [item[m] for m in ("median_score", "p95_score", "peak_score")]
        if item["n_finite_scores"]:
            assert all(finite(s) for s in scores)
            assert 0 <= scores[0] <= scores[1] + 1e-14 and scores[1] <= scores[2] + 1e-14 <= 1 + 1e-14
            assert 490896 <= float(row["peak_ts"]) < 495240
        else:
            assert all(s is None for s in scores)
        assert all(item[m] is None or item[m] >= 0 for m in ("gap_total_h", "activity_radius_km"))
        records[row["rfid_id"]] = item
    assert sum(r["n_rows"] for r in records.values()) == 3887065
    positive = [key for key, row in records.items() if row["linked"]]
    negative = [key for key, row in records.items() if not row["linked"]]
    assert len(positive) == 82 and len(negative) == 7290
    assert tuple(summary["metric_order"]) == METRICS
    scorer_rows = {r["rfid_id"]: r for r in read_csv(OUT / "vessel_peaks.csv")}
    assert set(scorer_rows) == set(records)
    for rfid, row in records.items():
        for metric in (*METRICS, "n_finite_scores"):
            near(row[metric], number(scorer_rows[rfid][metric]), "evaluation/scorer field")
    membership = {r["rfid_id"] for r in read_csv(provenance["paths"]["supplied_positive_membership"])}
    assert membership == set(positive)

    edge_rows = read_csv(OUT / "matched_sets.csv")
    grouped = defaultdict(list)
    used = set()
    for edge in edge_rows:
        p, c = edge["positive_rfid_id"], edge["control_rfid_id"]
        assert p in positive and c in negative and c not in used
        used.add(c)
        grouped[p].append(c)
        ratio = records[c]["n_rows"] / records[p]["n_rows"]
        assert abs(math.log(ratio)) <= math.log(1.1) + 1e-14
        near(number(edge["control_positive_count_ratio"]), ratio, "match count ratio")
    sets = list(grouped.items())
    assert all(1 <= len(controls) <= 5 for _, controls in sets)
    for edge in edge_rows:
        p, c = edge["positive_rfid_id"], edge["control_rfid_id"]
        assert int(edge["positive_n_rows"]) == records[p]["n_rows"]
        assert int(edge["control_n_rows"]) == records[c]["n_rows"]
        near(number(edge["control_weight_within_set"]), 1 / len(grouped[p]), "edge weight")
    # Reconstruct the whole greedy choice from counts and IDs, independent of score values.
    remaining = set(negative)
    for p in sorted(positive, key=lambda key: (records[key]["n_rows"], key)):
        candidates = [(abs(math.log(records[c]["n_rows"] / records[p]["n_rows"])), c) for c in remaining]
        chosen = [c for distance, c in sorted(candidates) if distance <= math.log(1.1) + 1e-14][:5]
        assert grouped.get(p, []) == chosen, ("greedy assignment", p)
        remaining.difference_update(chosen)
    near(len(sets) / 82, summary["matching"]["coverage"], "matching coverage")
    assert len(sets) == summary["matching"]["n_sets"] and len(used) == summary["matching"]["n_controls"]
    near(direct_smd(sets, records, "n_rows"), summary["matching"]["log_n_rows_balance"]["log_count_smd"], "base SMD")

    auc_results, metric_sets = {}, {}
    for metric in METRICS:
        p_values = [records[p][metric] for p in positive if finite(records[p][metric])]
        n_values = [records[n][metric] for n in negative if finite(records[n][metric])]
        # At most one positive against <=7290 comparisons; no dense pair allocation.
        pair_wins = sum(sum(1.0 if p > n else .5 if p == n else 0.0 for n in n_values) for p in p_values)
        raw_auc = pair_wins / (len(p_values) * len(n_values)) if p_values and n_values else None
        selected_sets = [(p, [c for c in controls if finite(records[c][metric])])
                         for p, controls in sets if finite(records[p][metric])]
        selected_sets = [(p, controls) for p, controls in selected_sets if controls]
        metric_sets[metric] = selected_sets
        per_set = [statistics.fmean(1.0 if records[p][metric] > records[c][metric] else .5 if records[p][metric] == records[c][metric] else 0.0 for c in controls)
                   for p, controls in selected_sets]
        matched_auc = statistics.fmean(per_set) if per_set else None
        raw, matched = summary["uncontrolled"][metric], summary["controlled_conditional"][metric]
        near(raw_auc, raw["auc"], metric + " raw AUC")
        near(matched_auc, matched["auc"], metric + " conditional AUC")
        assert raw["n_positive_finite"] == len(p_values) and raw["n_control_finite"] == len(n_values)
        near(len(selected_sets) / 82, matched["positive_coverage"], "metric coverage")
        near(direct_smd(selected_sets, records, "n_rows"), matched["log_n_rows_balance"]["log_count_smd"], "metric SMD")
        for result in (raw, matched):
            if result["ci_low"] is not None:
                assert 0 <= result["ci_low"] <= result["ci_high"] <= 1
        auc_results[metric] = {"raw_direct_pairwise": raw_auc, "matched_direct_pairwise": matched_auc}
    candidates = [m for m in METRICS if m != "n_rows"]
    ordered = sorted(candidates, key=lambda m: summary["controlled_conditional"][m]["p_greater"] or 1)
    running = 0.0
    for rank, metric in enumerate(ordered):
        result = summary["controlled_conditional"][metric]
        p = result["p_greater"]
        running = min(1.0, max(running, (5 - rank) * (p if p is not None else 1)))
        near(result["p_holm"], running if p is not None else None, "Holm")

    scenarios = read_csv(OUT / "expected_f1.csv")
    assert len(scenarios) == 504
    assert len({(r["metric"], r["source"], r["threshold_kind"], r["threshold"], r["quantile"], r["prevalence"]) for r in scenarios}) == 504
    max_f1_difference = 0.0
    for scenario in scenarios:
        metric, source = scenario["metric"], scenario["source"]
        threshold = number(scenario["threshold"])
        kind = scenario["threshold_kind"]
        assert kind in ("none", "all", "value")
        if kind != "value":
            assert threshold is None and number(scenario["quantile"]) is None
        elif metric in METRICS[:3]:
            assert threshold in tuple(round(.40 + .05 * i, 2) for i in range(12))
            assert number(scenario["quantile"]) is None
        else:
            quantile = number(scenario["quantile"])
            assert quantile in (.5, .75, .9, .95, .99)
            ordered_values = sorted(r[metric] for r in records.values() if finite(r[metric]))
            if ordered_values:
                position = (len(ordered_values) - 1) * quantile
                lower, upper = math.floor(position), math.ceil(position)
                expected_threshold = ordered_values[lower] + (position - lower) * (ordered_values[upper] - ordered_values[lower])
                near(threshold, expected_threshold, "label-blind linear quantile")
            else:
                assert threshold is None
        def selected(key):
            value = records[key][metric]
            return finite(value) and (kind == "all" or (kind == "value" and threshold is not None and value >= threshold))
        if source == "raw_fleet_uncontrolled":
            valid_p = [p for p in positive if finite(records[p][metric])]
            valid_n = [n for n in negative if finite(records[n][metric])]
            a = sum(map(selected, valid_p)) / len(valid_p) if valid_p else None
            b = sum(map(selected, valid_n)) / len(valid_n) if valid_n else None
        else:
            assert source == "matched_set_weighted"
            valid = metric_sets[metric]
            a = statistics.fmean(selected(p) for p, _ in valid) if valid else None
            b = statistics.fmean(statistics.fmean(selected(c) for c in controls) for _, controls in valid) if valid else None
        near(number(scenario["tpr"]), a, "scenario direct TPR")
        near(number(scenario["fpr"]), b, "scenario direct FPR")
        p, h = float(scenario["prevalence"]), float(scenario["h"])
        assert p in (.0227, .1, .5, 1.) and h == .0366
        if a is None or b is None:
            assert not scenario["expected_time_included_f1"]
            continue
        predicted = 100 * (p * a + (1 - p) * b)
        purity = 100 * p * a / predicted if predicted else None
        near(number(scenario["k_per_100"]), predicted, "scenario k")
        near(number(scenario["q"]), purity, "scenario q")
        # Derive TP from expected submissions * purity * conditional time hit.
        true_positive = predicted * purity * h if predicted else 0.0
        independent_f1 = 2 * true_positive / (predicted + 100 * p)
        difference = abs(float(scenario["expected_time_included_f1"]) - independent_f1)
        assert difference < 1e-12, "scenario F1"
        max_f1_difference = max(max_f1_difference, difference)

    quality = summary["quality"]
    mismatch = sum(r["n_rows"] != r["n_finite_scores"] for r in records.values())
    assert mismatch == quality["n_vessels_finite_scores_differs_from_rows"]
    assert sum(r["n_finite_scores"] for r in records.values()) == quality["total_n_finite_scores"]
    print(json.dumps({"status": "passed", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                      "memory": memory, "cohort": {"vessels": len(records), "rows": 3887065, "linked": len(positive), "unlinked": len(negative)},
                      "fresh_hashes_verified": hash_files, "auc_independent": auc_results,
                      "matched_sets": len(sets), "distinct_controls": len(used),
                      "finite_score_count_mismatch_vessels": mismatch,
                      "scenarios_verified": len(scenarios), "max_f1_absolute_difference": max_f1_difference,
                      "limitations": "CI/bootstrap and Monte Carlo p are implementation-reviewed and synthetic-tested, not independently rerun here; no external labels,2025data,or hardware read."}, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
