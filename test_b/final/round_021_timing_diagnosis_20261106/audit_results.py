"""Independent, post-selection, read-only Round021 checks; no rescoring.

Own outputs are independent_audit*.json only.  Never evaluate an unselected
alternative against validation accident times.  Do not import production code.
"""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SCORE = HERE / "execution_001"
EVAL = HERE / "evaluation_001"
ROOT = HERE.parents[2]
MIB = 2**20
CHECKS = Counter()


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    CHECKS[name] += 1


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(MIB), b""):
            h.update(b)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def number(value):
    if value is None or value == "":
        return None
    n = float(value)
    return n if math.isfinite(n) else None


def integer(value):
    return int(value) if value is not None and value != "" else None


def flag(value):
    check(value in ("True", "False"), "canonical_boolean")
    return value == "True"


def close(a, b):
    return a is b if a is None or b is None else math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)


def nearest(pred, events):
    if pred is None:
        return None, None, False
    event = sorted(events, key=lambda x: (abs(pred-x[1]), x[0]))[0]
    error = pred-event[1]
    return event[0], error, abs(error) <= 6


def wilson(h, n):
    if not n:
        return (None, None)
    z2 = 1.959963984540054**2
    root = math.sqrt(z2 * (h/n*(1-h/n)/n + z2/(4*n*n)))
    return ((h/n+z2/(2*n)-root)/(1+z2/n), (h/n+z2/(2*n)+root)/(1+z2/n))


def category(events, observed, finite, maxima, b):
    inside = lambda h: any(abs(h-e[1]) <= 6 for e in events)
    if not finite:
        return "no_finite_score_anywhere"
    if not any(e[1]+6 >= min(observed) and e[1]-6 <= max(observed) for e in events):
        return "all_windows_outside_observed_span"
    if not any(map(inside, observed)):
        return "span_overlap_but_no_observed_hour_in_any_window"
    if not any(map(inside, finite)):
        return "observed_in_window_but_no_finite_score"
    if not any(map(inside, maxima)):
        return "finite_in_window_but_no_global_max_ranking_failure"
    return "B_hit" if b is not None and inside(b) else "some_global_max_in_window_but_B_miss_tie_choice_failure"


def main():
    import psutil
    memory = {"checked_at": datetime.now().astimezone().isoformat(),
              "available_mib": psutil.virtual_memory().available/MIB,
              "estimated_peak_mib": 512, "reserve_mib": 640,
              "basis": "one score partition of tuples; 7372 CSV records; 82 linked hour sets; no all-fleet hourly retention or rescoring"}
    processes = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            processes.append({"pid": info["pid"], "name": info["name"], "rss_mib": info["memory_info"].rss/MIB})
        except (psutil.Error, AttributeError):
            continue
    memory["top_processes"] = sorted(processes, key=lambda x: -x["rss_mib"])[:12]
    memory["python_processes"] = [x for x in processes if "python" in (x["name"] or "").lower()]
    memory["allowed"] = memory["available_mib"] >= 512+640
    (HERE / "independent_audit_memory.json").write_text(json.dumps(memory, indent=2), encoding="utf-8")
    if not memory["allowed"]:
        print("DEFERRED_MEMORY")
        return 75
    # This entry point is deliberately unusable until selection and evaluation finish.
    summary = read_json(EVAL / "summary.json")
    selection = read_json(EVAL / "selection.json")
    selected = selection["selected_policy"]
    check(selected in ("B", "T", "G"), "selected_policy_valid")
    check(digest(EVAL / "selection.json") == read_json(EVAL / "selection_sealed.json")["selection_sha256"], "selection_seal")
    seal = read_json(SCORE / "score_seal.json")
    check(seal["status"] == "complete" and seal["labels_read"] is False, "score_complete_labelblind")
    check(digest(SCORE / "fleet_policy_predictions.csv") == seal["policy_prediction_sha256"] == summary["predictions_sha256"], "prediction_seal")
    freeze = read_json(HERE / "freeze.json")
    check(digest(HERE / "PROTOCOL.md") == freeze["protocol_sha256"] == summary["protocol_sha256"], "protocol_seal")
    for name in ("score_sources_before.json", "score_sources_after.json"):
        check(digest(SCORE / name) == seal["sources_"+("before" if "before" in name else "after")+"_sha256"], "score_source_receipt_seal")
    check(read_json(SCORE / "score_sources_before.json") == read_json(SCORE / "score_sources_after.json"), "score_sources_unchanged")
    for path, fingerprint in read_json(SCORE / "score_sources_before.json").items():
        check(digest(path) == fingerprint["sha256"], "score_input_current_digest")
    check(digest(SCORE / "score_baseline_parity.json") == seal["baseline_parity_sha256"], "baseline_parity_seal")
    parity = read_json(SCORE / "score_baseline_parity.json")
    check(parity["mismatch_count"] == 0 and parity["vessels_compared"] == 7372, "baseline_parity_receipt")
    before, after = read_json(EVAL / "evaluation_inputs_before.json")["files"], read_json(EVAL / "evaluation_inputs_after.json")["files"]
    check(before == after, "evaluation_inputs_unchanged")
    for path, fingerprint in before.items():
        check(digest(path) == fingerprint["sha256"], "evaluation_input_current_digest")
    integrity = read_json(EVAL / "evaluation_integrity.json")
    for name, fingerprint in integrity["all_output_files"].items():
        check(digest(EVAL / name) == fingerprint["sha256"], "evaluation_output_current_digest")
    raw = {r["rfid_id"]: r for r in rows(SCORE / "fleet_policy_predictions.csv")}
    check(len(raw) == 7372 and sum(int(r["n_rows"]) for r in raw.values()) == 3887065, "fleet_row_counts")
    columns = {"B": "baseline_ts", "T": "tie_center_ts", "G": "gap_midpoint_ts"}
    predictions = {k: {p: integer(r[c]) for p, c in columns.items()} for k, r in raw.items()}
    order = sorted(raw, key=lambda k: (hashlib.sha256(("round021-v1|"+k).encode()).digest(), k))
    split = {k: "dev" if i % 2 == 0 else "validation" for i, k in enumerate(order)}
    check(Counter(split.values()) == {"dev": 3686, "validation": 3686}, "independent_split_counts")
    for rank, key in enumerate(order):
        check(raw[key]["split"] == ("development" if rank % 2 == 0 else "validation") and int(raw[key]["split_rank"]) == rank, "independent_split_exact")
    truth = defaultdict(list)
    for r in rows(ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"):
        truth[r["rfid_id"]].append((r["acc_id"], int(r["acc_ts"])))
    check(len(truth) == 82 and sum(map(len, truth.values())) == 100, "linked_membership")
    dev = {k for k in truth if split[k] == "dev"}
    hit = {"B": {}, selected: {}}
    for policy in set(("B", selected)):
        hit[policy] = {k: nearest(predictions[k][policy], truth[k])[2] for k in truth}
    dev_hits = {p: sum(nearest(predictions[k][p], truth[k])[2] for k in dev) for p in columns}
    changed = {p: sum(predictions[k][p] != predictions[k]["B"] for k in raw if split[k] == "dev") for p in columns}
    candidates = [p for p in ("T", "G") if dev_hits[p] > dev_hits["B"]]
    expected = min(candidates, key=lambda p: (-dev_hits[p], changed[p], p != "T")) if candidates else "B"
    check(selected == expected and selection["dev_hits"] == dev_hits and selection["development_timestamps_changed"] == changed, "independent_development_choice")
    check({r["policy"] for r in summary["validation"]} == set(("B", selected)), "validation_selected_only")
    for r in summary["development"] + summary["validation"] + summary["all_linked"]:
        ids = {k for k in truth if r["subset"] == "all" or split[k] == r["subset"]}
        p = r["policy"]
        check(r["subset"] == "dev" or p in ("B", selected), "no_unchosen_validation_computation")
        hits = {k: nearest(predictions[k][p], truth[k])[2] for k in ids}
        wins = sum(hits[k] and not hit["B"][k] for k in ids)
        losses = sum(hit["B"][k] and not hits[k] for k in ids)
        lo, hi = wilson(sum(hits.values()), len(ids))
        n = wins+losses
        pv = min(1., 2*sum(math.comb(n,j) for j in range(min(wins,losses)+1))/2**n) if n else 1.
        check(r["hits"] == sum(hits.values()) and r["n_linked"] == len(ids) and r["paired_wins_vs_B"] == wins and r["paired_losses_vs_B"] == losses, "timing_paired_counts")
        check(close(lo,r["wilson95_low"]) and close(hi,r["wilson95_high"]) and close(pv,r["exact_mcnemar_two_sided_nominal_p"]), "independent_statistics")
        errors=[abs(nearest(predictions[k][p],truth[k])[1]) for k in ids if predictions[k][p] is not None]
        check(close(r["median_abs_error_h"],statistics.median(errors) if errors else None), "independent_median_error")
    val_ids={k for k in truth if split[k]=="validation"}
    check(summary["development_candidate"] == (selected!="B" and sum(hit[selected][k] for k in val_ids)>sum(hit["B"][k] for k in val_ids)), "validation_decision_flag")
    timeline = summary["audit"]
    index = lambda action: next(i for i, r in enumerate(timeline) if r["action"] == action)
    check(index("all_fleet_prediction_seal_verified") < index("all_fleet_split_persisted_before_labels") < index("selection_persisted_and_hashed"), "seal_audit_order")
    check(next(i for i,r in enumerate(timeline) if r.get("phase") == "validation") > index("selection_persisted_and_hashed"), "validation_parse_after_choice")
    # One partition at a time; verify all three label-blind policies without
    # comparing unselected validation predictions to events.
    stream_memory = {"checked_at": datetime.now().astimezone().isoformat(),
                     "stage": "before_arrow_streaming_import", "available_mib": psutil.virtual_memory().available/MIB,
                     "estimated_peak_mib": 512, "reserve_mib": 640}
    stream_processes = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            stream_processes.append({"pid": info["pid"], "name": info["name"], "rss_mib": info["memory_info"].rss/MIB})
        except (psutil.Error, AttributeError):
            continue
    stream_memory["top_processes"] = sorted(stream_processes, key=lambda x: -x["rss_mib"])[:12]
    stream_memory["python_processes"] = [x for x in stream_processes if "python" in (x["name"] or "").lower()]
    stream_memory["allowed"] = stream_memory["available_mib"] >= 512+640
    memory["before_streaming"] = stream_memory
    (HERE / "independent_audit_memory.json").write_text(json.dumps(memory, indent=2), encoding="utf-8")
    if not stream_memory["allowed"]:
        print("DEFERRED_MEMORY_BEFORE_STREAMING")
        return 75
    import pyarrow.parquet as pq
    manifest = read_json(SCORE / "hourly_score_manifest.json")
    check(digest(SCORE / "hourly_score_manifest.json") == seal["hourly_manifest_sha256"], "hourly_manifest_seal")
    diagnosis, seen, total = {}, set(), 0
    for entry in manifest["files"]:
        path = SCORE / entry["output_path"]
        check(digest(path) == entry["output_sha256"], "hourly_partition_hash")
        group = defaultdict(list)
        part_rows = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=16384, columns=["rfid_id","ts","source_ordinal","score","history_index"], use_threads=False):
            for r in batch.to_pylist():
                check(490896 <= r["ts"] < 495240, "approved_2026_hour_range")
                group[r["rfid_id"]].append((r["history_index"], r["ts"], r["source_ordinal"], number(r["score"])))
                part_rows += 1
        check(part_rows == entry["rows"], "hourly_partition_rows")
        total += part_rows
        for key, records in group.items():
            check(key not in seen, "vessel_single_partition")
            seen.add(key)
            records.sort()
            check([r[0] for r in records] == list(range(len(records))), "history_indices_contiguous")
            check([(r[1],r[2]) for r in records] == sorted((r[1],r[2]) for r in records), "history_timestamp_ordinal_order")
            finite = [r for r in records if r[3] is not None]
            maximum = max((r[3] for r in finite), default=None)
            tied = [r for r in finite if r[3] == maximum]
            hours = sorted({r[1] for r in tied})
            if tied:
                winner = min(tied, key=lambda r: (r[2], r[0]))
                b = winner[1]
                previous = records[winner[0]-1][1] if winner[0] else None
                g = (previous+b)//2 if previous is not None and b-previous > 1 else b
                runs = []
                for hour in hours:
                    if not runs or hour != runs[-1][-1]+1:
                        runs.append([])
                    runs[-1].append(hour)
                run = min(runs, key=lambda r: (-len(r),r[0]))
                t = run[(len(run)-1)//2]
            else:
                b = g = t = None
            check(predictions[key] == {"B":b,"T":t,"G":g}, "independent_all_fleet_policy_reconstruction")
            if key in truth:
                observed = {r[1] for r in records}
                finite_hours = {r[1] for r in finite}
                diagnosis[key] = {"category":category(truth[key],observed,finite_hours,set(hours),b), "observed":observed,"finite":finite_hours,"maximum":set(hours)}
        del group
    check(total == 3887065 and len(seen) == 7372, "hourly_fleet_conservation")
    vessel_rows = rows(EVAL / "time_errors_vessel.csv")
    check(len(vessel_rows) == 82 and {r["rfid_id"] for r in vessel_rows} == set(truth), "diagnosis_82_coverage")
    for r in vessel_rows:
        check(r["diagnostic_category"] == diagnosis[r["rfid_id"]]["category"], "independent_failure_taxonomy")
    diagnostics = Counter(("all",x["category"]) for x in diagnosis.values())
    diagnostics.update((split[k],x["category"]) for k,x in diagnosis.items())
    check(diagnostics == Counter({(r["subset"],r["category"]):int(r["vessels"]) for r in rows(EVAL / "diagnostic_counts.csv")}), "diagnostic_counts_exact")
    event_rows = rows(EVAL / "event_errors.csv")
    check(len(event_rows) == 100 and len({r["acc_id"] for r in event_rows}) == 100, "event_rows_100")
    for r in event_rows:
        key, event_hour = r["rfid_id"], int(r["acc_ts"])
        d = diagnosis[key]
        for name,p in (("B","B"),("selected",selected)):
            event_id, error, ishit = nearest(predictions[key][p],truth[key])
            check(flag(r[name+"_matched_tp_event"]) == (ishit and event_id == r["acc_id"]), "independent_one_event_assignment")
            check(flag(r[name+"_raw_event_tolerance_flag"]) == (predictions[key][p] is not None and abs(predictions[key][p]-event_hour)<=6), "independent_event_raw_flag")
        for column, hours in (("min_abs_observed_hour_error_h",d["observed"]),("min_abs_finite_score_hour_error_h",d["finite"]),("min_abs_global_max_hour_error_h",d["maximum"])):
            check(close(number(r[column]),min((abs(h-event_hour) for h in hours),default=None)), "independent_event_min_errors")
        observed=sorted(d["observed"])
        gaps=[(a,b) for a,b in zip(observed,observed[1:]) if b-a>1]
        check(flag(r["accident_hour_strictly_inside_observation_gap"]) == any(a<event_hour<b for a,b in gaps), "independent_event_inside_gap")
        intersections=sum(max(a+1,event_hour-6)<=min(b-1,event_hour+6) for a,b in gaps)
        check(int(r["n_gaps_intersecting_accident_window"]) == intersections and flag(r["accident_window_intersects_missing_integer_hours"]) == bool(intersections), "independent_event_gap_intersection")
    for name,p in (("B","B"),("selected",selected)):
        assigned=sum(flag(r[name+"_matched_tp_event"]) for r in event_rows)
        raw_flags=sum(flag(r[name+"_raw_event_tolerance_flag"]) for r in event_rows)
        check(assigned == sum(hit[p].values()) == summary["events"][name+"_matched_TP_events_max_one_per_vessel"] and raw_flags == summary["events"][name+"_raw_per_event_tolerance_flags"], "event_summary_and_vessel_hits_agree")
    peaks={r["rfid_id"]:r for r in rows(ROOT / "testB/final/round_019_vessel_discrimination_20261106/execution_001/vessel_peaks.csv")}
    check(peaks.keys() == raw.keys(), "round019_exact_fleet_keys")
    for key in raw:
        for field in ("n_rows", "n_unique_hours", "n_finite_scores", "peak_score", "median_score", "p95_score", "gap_total_h", "activity_radius_km"):
            check(number(raw[key][field]) == number(peaks[key][field]), "independent_round019_summary_exact_parity")
        check(integer(raw[key]["baseline_ts"]) == integer(peaks[key]["peak_ts"]) and raw[key]["peak_state"] == peaks[key]["peak_state"], "independent_round019_peak_time_state_exact_parity")
    radii=sorted(float(r["activity_radius_km"]) for r in peaks.values())
    ix=(len(radii)-1)*.95; low=math.floor(ix); q=radii[low]+(ix-low)*(radii[math.ceil(ix)]-radii[low])
    check(close(q,summary["radius_gate"]["threshold_km_full_precision"]), "independent_full_fleet_q95")
    counts={}
    for r in rows(EVAL / "fleet_selection_counts.csv"):
        subset,p,gate=r["subset"],r["policy"],r["gate"]
        check(p in ("B",selected), "gate_selected_policy_only")
        ids={k for k in raw if subset=="all" or split[k]==subset}
        chosen_ids={k for k in ids if gate=="all_submit" or (gate=="peak_ge_0_75" and number(peaks[k]["peak_score"]) is not None and float(peaks[k]["peak_score"])>=.75) or (gate=="radius_ge_q95" and float(peaks[k]["activity_radius_km"])>=q)}
        linked=chosen_ids & truth.keys(); c=len(chosen_ids); a=len(linked); h=sum(hit[p][k] for k in linked); u=c-a
        nl=len(ids & truth.keys()); nu=len(ids)-nl
        check(tuple(int(r[c]) for c in ("C_selected","A_linked_selected","H_linked_selected_timehit","U_unlinked_selected")) == (c,a,h,u), "independent_joint_counts")
        for col,value in (("conditional_timing_H_over_A",h/a if a else None),("joint_recall_H_over_nlinked",h/nl if nl else None),("selection_recall_A_over_nlinked",a/nl if nl else None),("unlinked_selection_rate_U_over_nunlinked",u/nu if nu else None)):
            check(close(number(r[col]),value), "independent_joint_rates")
        counts[(subset,p,gate)]=(a,h,u,nl,nu)
    for r in rows(EVAL / "f1_scenarios.csv"):
        a,h,u,nl,nu=counts[(r["subset"],r["policy"],r["gate"])];p=float(r["assumed_prevalence"])
        denominator=p*(1+a/nl)+(1-p)*u/nu
        expected=2*p*h/nl/denominator if denominator else None
        check(close(number(r["raw_fleet_f1_proxy"]),expected), "independent_joint_scenario")
    result={"status":"PASS","finished_at":datetime.now().astimezone().isoformat(),"audit_code_sha256":digest(__file__),"selected_policy":selected,"validation_alternatives_evaluated":sorted(set(("B",selected))),"unselected_validation_outcomes_computed":False,"rows_checked":total,"vessels_checked":len(seen),"linked_diagnoses_checked":len(diagnosis),"events_checked":len(event_rows),"checks":dict(CHECKS),"total_checks":sum(CHECKS.values()),"memory":memory}
    (HERE / "independent_audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("checks","memory")},ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
