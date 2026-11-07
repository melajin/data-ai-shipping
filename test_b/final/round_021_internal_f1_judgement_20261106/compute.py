"""Fixed, descriptive whole-fleet F1 accounting and explanatory case evidence."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "testB/final/round_019_vessel_discrimination_20261106"
PEAKS = OLD / "execution_001/vessel_peaks.csv"
TRUTH = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
FLEET = ROOT / "testB/final/round_017_fleet_negatives_20261106/execution_001"
PARQUETS = [FLEET / f"hourly_{m:02d}.parquet" for m in range(1, 7)]
SOURCES = [HERE / "PROTOCOL.md", Path(__file__).resolve(), PEAKS, TRUTH,
           OLD / "PROTOCOL.md", OLD / "execution_001/score_metadata.json", *PARQUETS]


def now():
    return datetime.now().astimezone().isoformat()


def dump(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def manifest():
    result = {}
    for p in SOURCES:
        if not p.resolve(strict=True).is_relative_to(ROOT.resolve()):
            raise ValueError("Input escapes authorized workspace")
        result[str(p.relative_to(ROOT))] = sha(p)
    return result


def memory(stage, log):
    import psutil
    processes = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            if "python" in (p.info["name"] or "").lower():
                processes.append({"pid": p.pid, "rss_mib": p.info["memory_info"].rss / 2**20})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    record = {"stage": stage, "checked_at": now(), "available_mib": psutil.virtual_memory().available / 2**20,
              "estimated_peak_mib": 512, "reserve_mib": 640, "python_processes": processes,
              "basis": "7372 CSV rows and at most five cases; 32768-row parquet batches; no fitting"}
    record["allowed"] = record["available_mib"] >= 1152
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    if not record["allowed"]:
        raise MemoryError("Deferred: estimate plus 640MiB reserve unavailable")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        raise ValueError("Unexpected empty output")
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def number(raw):
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def hour(raw):
    value = number(raw)
    return int(value) if value is not None and value.is_integer() else None


def quantile(values, q):
    values = sorted(values)
    if not values:
        raise ValueError("No finite radius values")
    x = (len(values) - 1) * q
    lo, hi = math.floor(x), math.ceil(x)
    return values[lo] + (values[hi] - values[lo]) * (x - lo)


def counts(tp, k, positives):
    if not 0 <= tp <= min(k, positives):
        raise ValueError("Invalid TP count")
    return {"tp": tp, "fp": k - tp, "fn": positives - tp,
            "precision": tp / k if k else 0.0, "recall": tp / positives if positives else 0.0,
            "f1": 2 * tp / (k + positives) if k + positives else 0.0}


def match_event(predicted_hour, events):
    if predicted_hour is None or not events:
        return None, None
    best = min(events, key=lambda e: (abs(predicted_hour - e["acc_ts"]), str(e["acc_id"])))
    error = abs(predicted_hour - best["acc_ts"])
    return (best["acc_id"] if error <= 6 else None), error


def policy_results(policy_rows, events, linked):
    per_vessel = defaultdict(list)
    for event in events:
        per_vessel[event["rfid_id"]].append(event)
    k, vessel_tp, event_tp = 0, 0, 0
    records, matched = [], set()
    for row in policy_rows:
        key, selected = row["rfid_id"], row["selected"]
        event_id, error = match_event(row["candidate_ts"], per_vessel[key])
        linked_flag = key in linked
        k += selected
        vessel_tp += selected and linked_flag
        is_time_match = selected and event_id is not None
        event_tp += is_time_match
        if is_time_match:
            if event_id in matched:
                raise ValueError("Event matched more than once")
            matched.add(event_id)
        records.append({**row, "is_provisional_linked": linked_flag,
                        "min_candidate_error_h": error, "matched_event_id": event_id if is_time_match else None,
                        "time_match": is_time_match})
    summary = {"policy": policy_rows[0]["policy"], "selected": k, "population": len(policy_rows),
               "linked_vessels": len(linked), "truth_events": len(events),
               "unlinked_selected": k - vessel_tp,
               "withheld_for_missing_input": sum(r["decision"] == "input_insufficient" for r in policy_rows),
               "vessel_selection": counts(vessel_tp, k, len(linked)),
               "event_time_pm6h": counts(event_tp, k, len(events)),
               "collapsed_vessel_time_pm6h_secondary": counts(event_tp, k, len(linked))}
    return summary, records, matched


def category(row):
    if row["selected"] and row["is_provisional_linked"]:
        return "selected_linked_time_match" if row["time_match"] else "selected_linked_time_miss"
    if row["is_provisional_linked"]:
        return "not_selected_linked"
    return "selected_unlinked" if row["selected"] else "not_selected_unlinked"


def extract_cases(main_rows, out):
    kinds = ["selected_linked_time_match", "selected_linked_time_miss", "not_selected_linked",
             "selected_unlinked", "not_selected_unlinked"]
    cases = []
    for kind in kinds:
        eligible = sorted((r for r in main_rows if category(r) == kind), key=lambda r: r["rfid_id"])
        cases.append({"category": kind, "available": bool(eligible), "row": eligible[0] if eligible else None})
    targets = {case["row"]["rfid_id"]: case["row"] for case in cases if case["available"]}
    memory("case_evidence", out / "memory.jsonl")
    import pyarrow.parquet as pq
    prior_rows, before_hours, after_hours = Counter(), defaultdict(set), defaultdict(set)
    evidence = []
    # Read only the permitted original geometry; no scores or coordinates are invented.
    for path in PARQUETS:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=32768,
                columns=["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "n_coords"],
                use_threads=False):
            raw = batch.to_pydict()
            for i, key in enumerate(raw["rfid_id"]):
                if key not in targets:
                    continue
                center, ts = targets[key]["candidate_ts"], int(raw["ts"][i])
                if center is None:
                    continue
                if ts < center:
                    prior_rows[key] += 1
                if abs(ts - center) <= 24:
                    if ts < center:
                        before_hours[key].add(ts)
                    if ts > center:
                        after_hours[key].add(ts)
                    evidence.append({"case_category": category(targets[key]), "rfid_id": key,
                        "candidate_ts": center, "offset_h": ts - center,
                        **{name: raw[name][i] for name in raw if name != "rfid_id"}})
    evidence.sort(key=lambda r: (r["rfid_id"], r["ts"], r["source_ordinal"]))
    if evidence:
        write_csv(out / "case_observations_pm24h.csv", evidence)
    for case in cases:
        if case["available"]:
            key = case["row"]["rfid_id"]
            case["observations_strictly_before_candidate_hour"] = prior_rows[key]
            case["exact_scorer_history_count_available"] = False
            case["history_note"] = "Same-hour preceding source rows are excluded; cached peak source_ordinal is unavailable"
            case["observed_hours_before_in_24h"] = len(before_hours[key])
            case["observed_hours_after_in_24h"] = len(after_hours[key])
            case["missing_hours_before_in_24h"] = 24 - len(before_hours[key])
            case["missing_hours_after_in_24h"] = 24 - len(after_hours[key])
            case["geometry_evidence_rows"] = sum(r["rfid_id"] == key for r in evidence)
            case["human_accident_judgement_completed"] = False
    dump(out / "cases.json", {"selection": "first RFID string per prespecified error category; explanatory only",
                               "window_hours": 24, "case_categories": cases})


def selftest():
    events = [{"rfid_id": "a", "acc_id": "1", "acc_ts": 10},
              {"rfid_id": "a", "acc_id": "2", "acc_ts": 12}]
    assert match_event(4, events) == ("1", 6)
    assert match_event(3, events) == (None, 7)
    assert match_event(11, events) == ("1", 1)
    rows = [{"rfid_id": "a", "selected": True, "candidate_ts": 11,
             "policy": "test", "decision": "review_candidate"},
            {"rfid_id": "b", "selected": True, "candidate_ts": 11,
             "policy": "test", "decision": "review_candidate"}]
    s, _, matched = policy_results(rows, events, {"a"})
    assert s["event_time_pm6h"] == counts(1, 2, 2) and len(matched) == 1
    assert s["vessel_selection"]["f1"] == 2 / 3
    rows[0]["candidate_ts"] = 30
    s, _, _ = policy_results(rows, events, {"a"})
    assert s["event_time_pm6h"]["tp"] == 0 and s["event_time_pm6h"]["fp"] == 2
    assert s["event_time_pm6h"]["fn"] == 2
    assert counts(0, 0, 100)["f1"] == 0
    assert quantile([0, 10], .95) == 9.5
    return {"passed": True, "checks": ["inclusive 6h", "outside 6h", "fixed tie", "one-to-one multi-event",
             "unlinked FP assumption", "vessel vs event denominator", "wrong-time FP+FN", "empty selection", "linear quantile"]}


def run():
    out = HERE / "execution_001"
    if out.exists():
        raise FileExistsError("Existing execution cannot be overwritten")
    memory("admission", HERE / "memory_preflight.jsonl")
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    if manifest() != frozen["files"]:
        raise ValueError("Frozen inputs changed")
    out.mkdir()
    dump(out / "started.json", {"started_at": now(), "frozen_at": frozen["frozen_at"]})
    try:
        rows = read_csv(PEAKS)
        assert len(rows) == 7372 and len({r["rfid_id"] for r in rows}) == 7372
        radius = [x for r in rows if (x := number(r["activity_radius_km"])) is not None]
        radius_threshold = quantile(radius, .95)
        predictions = []
        for r in rows:
            score, ts, rad = number(r["peak_score"]), hour(r["peak_ts"]), number(r["activity_radius_km"])
            valid = score is not None and 0 <= score <= 1 and ts is not None
            for policy in ["peak_ge_075", "all_valid", "radius_q95"]:
                policy_valid = valid and (policy != "radius_q95" or rad is not None)
                selected = bool(policy_valid and (policy == "all_valid" or
                    (policy == "peak_ge_075" and score >= .75) or
                    (policy == "radius_q95" and rad >= radius_threshold)))
                decision = "input_insufficient" if not policy_valid else "review_candidate" if selected else "not_selected_by_fixed_rule"
                predictions.append({"policy": policy, "rfid_id": r["rfid_id"], "selected": selected,
                    "decision": decision, "candidate_ts": ts, "submitted_ts": ts if selected else None,
                    "peak_score": score, "peak_state": r["peak_state"],
                    "median_score": number(r["median_score"]), "p95_score": number(r["p95_score"]),
                    "n_rows": int(r["n_rows"]), "n_unique_hours": int(r["n_unique_hours"]),
                    "n_finite_scores": int(r["n_finite_scores"]), "gap_total_h": number(r["gap_total_h"]),
                    "activity_radius_km": rad})
        write_csv(out / "all_fleet_policy_predictions.csv", predictions)
        dump(out / "predictions_sealed.json", {"sealed_at": now(), "rows": len(predictions),
             "sha256": sha(out / "all_fleet_policy_predictions.csv"), "accident_times_evaluated": False})
        events = read_csv(TRUTH)
        assert len(events) == 100 and len({e["acc_id"] for e in events}) == 100
        for e in events:
            e["acc_ts"] = hour(e["acc_ts"])
            if e["acc_ts"] is None:
                raise ValueError("Invalid event hour")
        linked = {e["rfid_id"] for e in events}
        assert len(linked) == 82 and linked <= {r["rfid_id"] for r in rows}
        summaries, evaluations, event_rows = [], [], []
        for policy in ["peak_ge_075", "all_valid", "radius_q95"]:
            summary, records, matched = policy_results([p for p in predictions if p["policy"] == policy], events, linked)
            summaries.append(summary)
            evaluations.extend(records)
            event_rows.extend({"policy": policy, "rfid_id": e["rfid_id"], "acc_id": e["acc_id"],
                               "acc_ts": e["acc_ts"], "matched_once": e["acc_id"] in matched} for e in events)
        write_csv(out / "all_fleet_evaluation.csv", evaluations)
        write_csv(out / "event_matches.csv", event_rows)
        extract_cases([r for r in evaluations if r["policy"] == "peak_ge_075"], out)
        if manifest() != frozen["files"]:
            raise ValueError("Input changed during execution")
        dump(out / "integrity.json", {"checked_at": now(), "all_frozen_files_match": True,
             "predictions_sha256": sha(out / "all_fleet_policy_predictions.csv")})
        import psutil
        mem = psutil.Process().memory_info()
        result = {"round": "Round021", "completed_at": now(), "population": 7372,
            "linked_vessels": 82, "unlinked_comparators": 7290, "events": 100,
            "main_policy": "peak_ge_075", "peak_threshold": .75, "radius_q95_threshold_km": radius_threshold,
            "official_f1": False, "new_training": False, "new_operational_policy_validated": False,
            "assumption": "unlinked vessels treated as negative only for surrogate metric; not verified nonaccidents",
            "time_contract": "integer-hour +/-6 inclusive; at most one event matched per vessel prediction",
            "primary_time_denominator": "100 events", "policies": summaries,
            "peak_process_mib": getattr(mem, "peak_wset", mem.rss) / 2**20}
        dump(out / "summary.json", result)
        print(json.dumps({"policies": summaries, "radius_threshold": radius_threshold}, ensure_ascii=True))
    except Exception as exc:
        dump(out / "failure.json", {"at": now(), "type": type(exc).__name__, "message": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["selftest", "freeze", "run"])
    mode = parser.parse_args().mode
    if mode == "selftest":
        check = selftest()
        dump(HERE / "synthetic_checks.json", {"at": now(), **check})
        print(json.dumps(check))
    elif mode == "freeze":
        if (HERE / "execution_001").exists():
            raise RuntimeError("Cannot freeze after execution")
        memory("freeze", HERE / "memory_preflight.jsonl")
        dump(HERE / "freeze.json", {"frozen_at": now(), "files": manifest(), "new_fit": False})
        print("Fixed policy and report accounting frozen")
    else:
        run()
