"""Frozen Round021 evaluation with a persisted development-only policy choice.

No model fitting, identity inference, external data, or 2025 inputs are used.
Only supplied same-rfid provisional links are evaluated.  Fleet selection and
conditional linked-vessel timing are reported separately from official F1.
Scientific imports are delayed until the RAM gate and selection lock.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TRUTH = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
PEAKS = ROOT / "testB/final/round_019_vessel_discrimination_20261106/execution_001/vessel_peaks.csv"
POLICIES = ("B", "T", "G")
POLICY_NAMES = {"B": "baseline", "T": "tie_center", "G": "gap_midpoint"}
PREDICTION_COLUMNS = {"B": "baseline_ts", "T": "tie_center_ts", "G": "gap_midpoint_ts"}
SPLIT_SALT = "round021-v1|"
EXPECTED_VESSELS = 7372
EXPECTED_LINKED = 82
EXPECTED_EVENTS = 100
EXPECTED_ROWS = 3887065
TOLERANCE_H = 6
PREVALENCES = (0.0227, 0.1, 0.2, 0.5, 1.0)
GATES = ("all_submit", "peak_ge_0_75", "radius_ge_q95")
MIB = 2**20


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(MIB), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def fingerprints(paths):
    return {str(Path(path).resolve()): {"sha256": sha256(path), "bytes": Path(path).stat().st_size} for path in paths}


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = list(fields or (rows[0].keys() if rows else []))
    with Path(path).open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def integer(value, name, nullable=False):
    if nullable and (value is None or str(value).strip() == ""):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid integer {name}") from exc
    if str(result) != str(value).strip():
        raise ValueError(f"Noncanonical integer {name}")
    return result


def finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def memory_gate(stage, log, estimate_mib=512):
    """One fresh snapshot per stage; never poll or stop user processes."""
    import psutil
    processes = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            processes.append({"pid": info["pid"], "name": info["name"],
                              "rss_mib": info["memory_info"].rss / MIB})
        except (psutil.Error, AttributeError):
            continue
    available = psutil.virtual_memory().available / MIB
    record = {"checked_at": now(), "stage": stage, "available_mib": available,
              "estimated_peak_mib": estimate_mib, "reserve_mib": 640,
              "estimate_basis": "7372 small CSV records, 82 linked hourly subsets; sequential 32768-row Arrow batches; no all-fleet hourly retention",
              "own_rss_mib": psutil.Process().memory_info().rss / MIB,
              "top_running_processes": sorted(processes, key=lambda row: -row["rss_mib"])[:12],
              "python_processes": [row for row in processes if "python" in (row["name"] or "").lower()],
              "allowed": available >= estimate_mib + 640}
    with Path(log).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    if not record["allowed"]:
        raise MemoryError(f"DEFERRED {stage}: {available:.1f}MiB < {estimate_mib}+640MiB")
    return record


def deterministic_split(ids):
    """Hash order and alternating halves; no linkage or timestamp argument."""
    values = list(ids)
    if len(values) != len(set(values)) or any(not value for value in values):
        raise ValueError("Fleet identifiers must be unique and nonempty")
    order = sorted(values, key=lambda value: (hashlib.sha256((SPLIT_SALT + value).encode("utf-8")).hexdigest(), value))
    return {value: ("dev" if index % 2 == 0 else "validation") for index, value in enumerate(order)}


def provided_membership(path=None):
    """Access only supplied rfid_id; this function never accesses acc_ts."""
    path = TRUTH if path is None else path
    values = [row["rfid_id"] for row in csv_rows(path)]
    if len(values) != EXPECTED_EVENTS or len(set(values)) != EXPECTED_LINKED or any(not value for value in values):
        raise ValueError("Supplied 100-event / 82-rfid membership contract failed")
    return set(values)


def read_events(path, permitted_ids, phase, audit):
    """Skip nonpermitted IDs before accessing or parsing their acc_ts field.

    A CSV scan necessarily traverses file bytes; the access/parse boundary is
    explicit here.  Validation timestamps are never retained during dev.
    """
    events, seen = defaultdict(list), set()
    for row in csv_rows(path):
        key = row["rfid_id"]
        if key not in permitted_ids:
            continue
        event_id = row["acc_id"]
        if not event_id or event_id in seen:
            raise ValueError("Empty or duplicate supplied event ID")
        hour = integer(row["acc_ts"], "acc_ts")
        if not 490896 <= hour < 495240:  # 2026-01-01 <= timestamp < 2026-07-01, UTC hour encoding
            raise ValueError("Supplied event is outside the authorized Jan-Jun 2026 period")
        seen.add(event_id)
        events[key].append({"acc_id": event_id, "rfid_id": key, "acc_ts": hour})
    if set(events) != set(permitted_ids):
        raise ValueError("Permitted supplied-event vessel coverage failed")
    audit.append({"at": now(), "action": "acc_ts_access_and_parse", "phase": phase,
                  "vessels": len(events), "events": len(seen)})
    return dict(events)


def nearest_event(prediction, events):
    if prediction is None:
        return {"nearest_acc_id": None, "abs_error_h": None, "signed_error_h": None, "hit_pm6h": False}
    event = min(events, key=lambda row: (abs(prediction - row["acc_ts"]), row["acc_id"]))
    error = prediction - event["acc_ts"]
    return {"nearest_acc_id": event["acc_id"], "abs_error_h": abs(error),
            "signed_error_h": error, "hit_pm6h": abs(error) <= TOLERANCE_H}


def timing_rows(predictions, events, policies):
    result = []
    for key in sorted(events):
        for policy in policies:
            guess = predictions[key][policy]
            result.append({"rfid_id": key, "policy": policy, "pred_ts": guess,
                           "n_events": len(events[key]), **nearest_event(guess, events[key])})
    return result


def choose_policy(dev_rows, predictions, split):
    """No validation labels argument: only dev hits and all-dev changes select."""
    if any(split[row["rfid_id"]] != "dev" for row in dev_rows):
        raise ValueError("Validation outcome reached development policy selector")
    hits = {policy: sum(row["hit_pm6h"] for row in dev_rows if row["policy"] == policy) for policy in POLICIES}
    changed = {policy: sum(row[policy] != row["B"] for key, row in predictions.items() if split[key] == "dev") for policy in POLICIES}
    candidates = [policy for policy in ("T", "G") if hits[policy] > hits["B"]]
    chosen = min(candidates, key=lambda policy: (-hits[policy], changed[policy], POLICIES.index(policy))) if candidates else "B"
    return {"selected_policy": chosen, "selected_policy_name": POLICY_NAMES[chosen],
            "dev_hits": hits, "development_timestamps_changed": changed,
            "selection_rule": "strict dev hits > B; largest dev hits, fewest changed timestamps across all dev vessels, T before G",
            "validation_outcomes_used": False, "selected_at": now()}


def wilson(hits, total):
    if total == 0:
        return [None, None]
    z = 1.959963984540054
    p = hits / total
    scale = 1 + z * z / total
    center = (p + z * z / (2 * total)) / scale
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    return [max(0.0, center - half), min(1.0, center + half)]


def exact_mcnemar(wins, losses):
    count = wins + losses
    return min(1.0, 2 * sum(math.comb(count, k) for k in range(min(wins, losses) + 1)) / 2**count) if count else 1.0


def comparison(rows, baseline_rows, policy, subset):
    alt = {row["rfid_id"]: row for row in rows if row["policy"] == policy}
    base = {row["rfid_id"]: row for row in baseline_rows if row["policy"] == "B"}
    if set(alt) != set(base):
        raise ValueError("Paired comparison vessel set differs")
    hits = sum(row["hit_pm6h"] for row in alt.values())
    wins = sum(alt[key]["hit_pm6h"] and not base[key]["hit_pm6h"] for key in alt)
    losses = sum(base[key]["hit_pm6h"] and not alt[key]["hit_pm6h"] for key in alt)
    ci = wilson(hits, len(alt))
    errors = [row["abs_error_h"] for row in alt.values() if row["abs_error_h"] is not None]
    return {"subset": subset, "policy": policy, "n_linked": len(alt), "hits": hits,
            "timing_hit_rate": hits / len(alt) if alt else None,
            "wilson95_low": ci[0], "wilson95_high": ci[1],
            "n_missing_predictions": len(alt) - len(errors),
            "median_abs_error_h": statistics.median(errors) if errors else None,
            "paired_wins_vs_B": wins, "paired_losses_vs_B": losses,
            "exact_mcnemar_two_sided_nominal_p": exact_mcnemar(wins, losses),
            "improvement_candidate": hits > sum(row["hit_pm6h"] for row in base.values()) and wins > losses,
            "p_value_is_decision_gate": False}


def linear_quantile(values, quantile):
    values = sorted(values)
    if not values:
        raise ValueError("Quantile requires finite fleet values")
    index = (len(values) - 1) * quantile
    low = math.floor(index)
    fraction = index - low
    return values[low] + fraction * (values[min(low + 1, len(values) - 1)] - values[low])


def scenario_f1(prevalence, joint_recall, linked_selection_recall, unlinked_selection_rate):
    """Raw fleet proxy; use measured joint H/nlinked rather than fixed h."""
    denominator = prevalence * (1 + linked_selection_recall) + (1 - prevalence) * unlinked_selection_rate
    return 2 * prevalence * joint_recall / denominator if denominator else None


def fleet_counts(predictions, peaks, split, linked, hit_by_id, policy):
    if set(peaks) != set(predictions):
        raise ValueError("Same-provided-rfid Round019 fleet alignment failed")
    radii = [row["activity_radius_km"] for row in peaks.values() if row["activity_radius_km"] is not None]
    if len(radii) != len(peaks):
        raise ValueError("Full-fleet label-blind q95 requires all finite radii")
    threshold = linear_quantile(radii, 0.95)
    flags = {key: {"all_submit": True,
                   "peak_ge_0_75": peaks[key]["peak_score"] is not None and peaks[key]["peak_score"] >= 0.75,
                   "radius_ge_q95": peaks[key]["activity_radius_km"] >= threshold} for key in predictions}
    counts, scenarios = [], []
    for subset in ("all", "dev", "validation"):
        ids = {key for key in predictions if subset == "all" or split[key] == subset}
        nlinked, nunlinked = len(ids & linked), len(ids - linked)
        for gate in GATES:
            selected = {key for key in ids if flags[key][gate]}
            linked_selected = selected & linked
            c, a, h, u = len(selected), len(linked_selected), sum(hit_by_id[key] for key in linked_selected), len(selected - linked)
            row = {"subset": subset, "policy": policy, "gate": gate, "n_fleet": len(ids),
                   "n_linked": nlinked, "n_unlinked": nunlinked, "C_selected": c,
                   "A_linked_selected": a, "H_linked_selected_timehit": h, "U_unlinked_selected": u,
                   "conditional_timing_H_over_A": h / a if a else None,
                   "joint_recall_H_over_nlinked": h / nlinked if nlinked else None,
                   "selection_recall_A_over_nlinked": a / nlinked if nlinked else None,
                   "unlinked_selection_rate_U_over_nunlinked": u / nunlinked if nunlinked else None,
                   "unlinked_are_confirmed_false_positives": False}
            counts.append(row)
            for p in PREVALENCES:
                scenarios.append({"subset": subset, "policy": policy, "gate": gate, "assumed_prevalence": p,
                                  "H": h, "A": a, "U": u, "n_linked": nlinked, "n_unlinked": nunlinked,
                                  "raw_fleet_f1_proxy": scenario_f1(p, h/nlinked, a/nlinked, u/nunlinked) if nlinked and nunlinked else None,
                                  "official_F1": False})
    return threshold, flags, counts, scenarios


def failure_category(events, observed_hours, finite_hours, maximizing_hours, baseline_ts):
    """Vessel taxonomy uses the union of its own +/-6h event windows only."""
    def in_windows(hour):
        return any(abs(hour - row["acc_ts"]) <= TOLERANCE_H for row in events)
    if not finite_hours:
        return "no_finite_score_anywhere"
    low, high = min(observed_hours), max(observed_hours)
    if not any(row["acc_ts"] + TOLERANCE_H >= low and row["acc_ts"] - TOLERANCE_H <= high for row in events):
        return "all_windows_outside_observed_span"
    if not any(in_windows(hour) for hour in observed_hours):
        return "span_overlap_but_no_observed_hour_in_any_window"
    if not any(in_windows(hour) for hour in finite_hours):
        return "observed_in_window_but_no_finite_score"
    if not any(in_windows(hour) for hour in maximizing_hours):
        return "finite_in_window_but_no_global_max_ranking_failure"
    if baseline_ts is None or not in_windows(baseline_ts):
        return "some_global_max_in_window_but_B_miss_tie_choice_failure"
    return "B_hit"


def event_error_rows(events, predictions, chosen, split, groups=None):
    rows = []
    for key in sorted(events):
        guesses = {"B": predictions[key]["B"], "selected": predictions[key][chosen]}
        nearest = {name: nearest_event(guess, events[key]) for name, guess in guesses.items()}
        for event in sorted(events[key], key=lambda row: (row["acc_ts"], row["acc_id"])):
            row = {**event, "split": split[key], "selected_policy": chosen}
            if groups is not None:
                group = groups[key]
                hours = sorted(group["observed"])
                gaps = [(a, b) for a, b in zip(hours, hours[1:]) if b - a > 1]
                row.update({"min_abs_observed_hour_error_h": min((abs(hour - event["acc_ts"]) for hour in hours), default=None),
                            "min_abs_finite_score_hour_error_h": min((abs(hour - event["acc_ts"]) for hour in group["finite"]), default=None),
                            "min_abs_global_max_hour_error_h": min((abs(hour - event["acc_ts"]) for hour in group["maximum"]), default=None),
                            "accident_hour_strictly_inside_observation_gap": any(a < event["acc_ts"] < b for a, b in gaps),
                            "accident_window_intersects_missing_integer_hours": any(max(a + 1, event["acc_ts"] - TOLERANCE_H) <= min(b - 1, event["acc_ts"] + TOLERANCE_H) for a, b in gaps),
                            "n_gaps_intersecting_accident_window": sum(max(a + 1, event["acc_ts"] - TOLERANCE_H) <= min(b - 1, event["acc_ts"] + TOLERANCE_H) for a, b in gaps)})
            for name, guess in guesses.items():
                error = guess - event["acc_ts"] if guess is not None else None
                row.update({f"{name}_pred_ts": guess, f"{name}_signed_error_h": error,
                            f"{name}_abs_error_h": abs(error) if error is not None else None,
                            f"{name}_raw_event_tolerance_flag": error is not None and abs(error) <= TOLERANCE_H,
                            f"{name}_matched_tp_event": nearest[name]["hit_pm6h"] and nearest[name]["nearest_acc_id"] == event["acc_id"],
                            f"{name}_vessel_nearest_acc_id": nearest[name]["nearest_acc_id"]})
            rows.append(row)
    return rows


def load_predictions(path):
    predictions = {}
    for row in csv_rows(path):
        key = row["rfid_id"]
        if not key or key in predictions:
            raise ValueError("Duplicate or empty fleet prediction identifier")
        predictions[key] = {policy: integer(row[column], column, nullable=True) for policy, column in PREDICTION_COLUMNS.items()}
        predictions[key]["engine_split"] = row["split"]
    if len(predictions) != EXPECTED_VESSELS:
        raise ValueError("All 7372 fleet predictions required before evaluation")
    return predictions


def load_peaks(path):
    peaks = {}
    for row in csv_rows(path):
        key = row["rfid_id"]
        if key in peaks:
            raise ValueError("Duplicate Round019 provided rfid")
        peaks[key] = {name: finite(row[name]) for name in ("peak_score", "activity_radius_km")}
    return peaks


def stream_linked_hours(paths, linked, predictions):
    """Retain 82 vessels only; import Arrow after the second fresh RAM gate."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    identifiers = pa.array(sorted(linked), type=pa.string())
    groups = {key: {"observed": set(), "finite": set(), "maximum": set(), "max_score": None, "n_rows": 0} for key in linked}
    total = 0
    for path in paths:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=32768, columns=["rfid_id", "ts", "score"], use_threads=False):
            total += batch.num_rows
            table = pa.Table.from_batches([batch])
            selected = table.filter(pc.is_in(table["rfid_id"], value_set=identifiers))
            for row in selected.to_pylist():
                key, hour = row["rfid_id"], integer(row["ts"], "hourly ts")
                group = groups[key]
                group["observed"].add(hour)
                group["n_rows"] += 1
                score = finite(row["score"])
                if score is None:
                    continue
                group["finite"].add(hour)
                if group["max_score"] is None or score > group["max_score"]:
                    group["max_score"], group["maximum"] = score, {hour}
                elif score == group["max_score"]:
                    group["maximum"].add(hour)
    if total != EXPECTED_ROWS:
        raise ValueError(f"Expected {EXPECTED_ROWS} fleet hourly rows, found {total}")
    for key, group in groups.items():
        if group["maximum"] and predictions[key]["B"] not in group["maximum"]:
            raise ValueError("Baseline prediction is not an exact finite hourly maximum")
    return groups, total


def verified_hourly_paths(score_dir, seal):
    manifest_path = score_dir / "hourly_score_manifest.json"
    if seal["hourly_manifest_sha256"] != sha256(manifest_path):
        raise RuntimeError("Hourly manifest differs from the label-blind seal")
    manifest = read_json(manifest_path)
    if manifest["rows"] != EXPECTED_ROWS or manifest["vessels"] != EXPECTED_VESSELS:
        raise RuntimeError("Hourly manifest fleet count contract failed")
    paths, seen = [], set()
    for entry in manifest["files"]:
        path = (score_dir / entry["output_path"]).resolve(strict=True)
        if not path.is_relative_to(score_dir.resolve()) or path in seen or not path.is_file():
            raise RuntimeError("Hourly manifest path is duplicated or escapes score directory")
        if sha256(path) != entry["output_sha256"] or path.stat().st_size != entry["output_bytes"]:
            raise RuntimeError("Hourly score parquet digest or byte count changed")
        paths.append(path)
        seen.add(path)
    if sum(entry["rows"] for entry in manifest["files"]) != EXPECTED_ROWS:
        raise RuntimeError("Hourly manifest partition row totals differ")
    return paths


def verify_score_seal(score_dir):
    """Require the scorer's completion/parity/source seal before label access."""
    seal = read_json(score_dir / "score_seal.json")
    prediction_path = score_dir / "fleet_policy_predictions.csv"
    if seal.get("policy_prediction_sha256") != sha256(prediction_path):
        raise RuntimeError("All-fleet prediction seal mismatch")
    required = {"status": "complete", "vessels_completed": EXPECTED_VESSELS,
                "rows_completed": EXPECTED_ROWS, "vessel_error_records": 0,
                "labels_read": False, "accident_times_parsed": False,
                "training_performed": False, "score_definition_changed": False,
                "source_checksums_match": True}
    if any(key not in seal or type(seal[key]) is not type(value) or seal[key] != value for key, value in required.items()):
        raise RuntimeError("Score seal completion, no-label, no-training or source-parity attestation failed")
    if seal.get("freeze_sha256") != sha256(HERE / "freeze.json") or seal.get("engine_sha256") != sha256(HERE / "score_fleet_timing.py"):
        raise RuntimeError("Score engine or freeze digest differs from completion seal")
    return seal


def evaluate(score_dir, output_dir, expected_protocol_sha256):
    score_dir, output_dir = Path(score_dir), Path(output_dir)
    if score_dir.resolve() != (HERE / "execution_001").resolve() or not output_dir.resolve().is_relative_to(HERE.resolve()):
        raise ValueError("Evaluation reads the authorized Round021 execution only and writes inside its Round021 folder")
    if sha256(HERE / "PROTOCOL.md") != expected_protocol_sha256:
        raise RuntimeError("Frozen protocol SHA256 mismatch")
    output_dir.mkdir(parents=True, exist_ok=False)
    audit = []
    memory_gate("before_prediction_or_label_load", output_dir / "evaluation_memory.jsonl")
    seal = verify_score_seal(score_dir)
    immutable_paths = [HERE / "PROTOCOL.md", HERE / "freeze.json", Path(__file__),
                       HERE / "test_evaluate_round021.py", HERE / "score_fleet_timing.py", TRUTH, PEAKS,
                       score_dir / "score_seal.json",
                       score_dir / "labelblind_score_summary.json", score_dir / "score_metadata.json",
                       score_dir / "hourly_score_manifest.json", score_dir / "fleet_policy_predictions.csv"]
    before = fingerprints(immutable_paths)
    write_json(output_dir / "evaluation_inputs_before.json", {"checked_at": now(), "files": before})
    prediction_path = score_dir / "fleet_policy_predictions.csv"
    audit.append({"at": now(), "action": "all_fleet_prediction_seal_verified", "predictions_sha256": sha256(prediction_path)})
    predictions = load_predictions(prediction_path)
    split = deterministic_split(predictions)
    if Counter(split.values()) != {"dev": EXPECTED_VESSELS // 2, "validation": EXPECTED_VESSELS // 2}:
        raise ValueError("Frozen whole-fleet split count failed")
    if any(predictions[key]["engine_split"] != ("development" if split[key] == "dev" else "validation") for key in split):
        raise ValueError("Engine split differs from independent hash split")
    write_csv(output_dir / "split.csv", [{"rfid_id": key, "split": split[key], "split_hash": hashlib.sha256((SPLIT_SALT + key).encode()).hexdigest()} for key in sorted(split)])
    write_json(output_dir / "split_sealed.json", {"sealed_at": now(), "split_sha256": sha256(output_dir / "split.csv"), "predictions_sha256": sha256(prediction_path), "acc_ts_parsed": False})
    audit.append({"at": now(), "action": "all_fleet_split_persisted_before_labels", "split_sha256": sha256(output_dir / "split.csv")})
    linked = provided_membership()
    if not linked <= set(predictions):
        raise ValueError("Supplied membership absent from all-fleet predictions")
    dev_ids = {key for key in linked if split[key] == "dev"}
    val_ids = linked - dev_ids
    dev_events = read_events(TRUTH, dev_ids, "dev", audit)
    dev_rows = timing_rows(predictions, dev_events, POLICIES)
    decision = choose_policy(dev_rows, predictions, split)
    decision.update(protocol_sha256=expected_protocol_sha256, predictions_sha256=sha256(prediction_path), split_sha256=sha256(output_dir / "split.csv"), n_dev_linked=len(dev_ids), n_validation_linked=len(val_ids))
    write_json(output_dir / "selection.json", decision)
    selection_hash = sha256(output_dir / "selection.json")
    write_json(output_dir / "selection_sealed.json", {"sealed_at": now(), "selection_sha256": selection_hash, "validation_acc_ts_accessed": False})
    audit.append({"at": now(), "action": "selection_persisted_and_hashed", "selection_sha256": selection_hash})
    chosen = decision["selected_policy"]
    # This boundary must remain after both exclusive selection writes.
    val_events = read_events(TRUTH, val_ids, "validation", audit)
    if sha256(output_dir / "selection.json") != selection_hash:
        raise RuntimeError("Selection lock changed before validation")
    val_policies = ("B", chosen) if chosen != "B" else ("B",)
    val_rows = timing_rows(predictions, val_events, val_policies)
    events = {**dev_events, **val_events}
    if sum(map(len, events.values())) != EXPECTED_EVENTS or len(events) != EXPECTED_LINKED:
        raise ValueError("Final 100-event / 82-vessel coverage failed")
    dev_comparison = [comparison(dev_rows, dev_rows, policy, "dev") for policy in POLICIES]
    val_comparison = [comparison(val_rows, val_rows, policy, "validation") for policy in val_policies]
    write_csv(output_dir / "dev_comparison.csv", dev_comparison)
    write_csv(output_dir / "validation_comparison.csv", val_comparison)
    write_csv(output_dir / "dev_policy_errors.csv", [{**row, "split": "dev"} for row in dev_rows])
    all_rows = timing_rows(predictions, events, val_policies)
    all_comparison = [comparison(all_rows, all_rows, policy, "all") for policy in val_policies]
    by_policy = {(row["rfid_id"], row["policy"]): row for row in all_rows}
    memory_gate("before_streaming_linked_hour_diagnosis", output_dir / "evaluation_memory.jsonl")
    hourly_paths = verified_hourly_paths(score_dir, seal)
    if not hourly_paths:
        raise RuntimeError("Sealed worker hourly score parquets missing")
    groups, total_hour_rows = stream_linked_hours(hourly_paths, linked, predictions)
    errors, diagnostic = [], Counter()
    for key in sorted(linked):
        group = groups[key]
        category = failure_category(events[key], group["observed"], group["finite"], group["maximum"], predictions[key]["B"])
        diagnostic[("all", category)] += 1
        diagnostic[(split[key], category)] += 1
        row = {"rfid_id": key, "split": split[key], "n_events": len(events[key]), "selected_policy": chosen,
               "diagnostic_category": category, "n_observed_rows": group["n_rows"],
               "n_observed_hours": len(group["observed"]), "n_finite_hours": len(group["finite"]),
               "observed_min_ts": min(group["observed"], default=None), "observed_max_ts": max(group["observed"], default=None),
               "n_global_max_hours": len(group["maximum"])}
        for name, policy in (("B", "B"), ("selected", chosen)):
            row.update({f"{name}_{field}": value for field, value in by_policy[(key, policy)].items() if field not in ("rfid_id", "policy", "n_events")})
        errors.append(row)
    write_csv(output_dir / "time_errors_vessel.csv", errors)
    event_rows = event_error_rows(events, predictions, chosen, split, groups)
    write_csv(output_dir / "event_errors.csv", event_rows)
    write_csv(output_dir / "diagnostic_counts.csv", [{"subset": subset, "category": category, "vessels": count} for (subset, category), count in sorted(diagnostic.items())])
    peaks = load_peaks(PEAKS)
    counts, scenarios = [], []
    for policy in val_policies:
        hit_by_id = {key: by_policy[(key, policy)]["hit_pm6h"] for key in linked}
        radius_threshold, flags, policy_counts, policy_scenarios = fleet_counts(predictions, peaks, split, linked, hit_by_id, policy)
        counts.extend(policy_counts)
        scenarios.extend(policy_scenarios)
    write_csv(output_dir / "fleet_selection_counts.csv", counts)
    write_csv(output_dir / "f1_scenarios.csv", scenarios)
    write_csv(output_dir / "predictions_with_selection.csv", [{"rfid_id": key, "split": split[key],
               **{PREDICTION_COLUMNS[policy]: predictions[key][policy] for policy in POLICIES},
               "selected_policy": chosen, "selected_pred_ts": predictions[key][chosen],
               **flags[key]} for key in sorted(predictions)])
    validation_selected = next(row for row in val_comparison if row["policy"] == chosen)
    after = fingerprints(immutable_paths)
    if before != after:
        raise RuntimeError("Frozen evaluation inputs or code changed during execution")
    if any(sha256(path) != entry["output_sha256"] for path, entry in zip(hourly_paths, read_json(score_dir / "hourly_score_manifest.json")["files"])):
        raise RuntimeError("Hourly score parquet changed during diagnosis")
    write_json(output_dir / "evaluation_inputs_after.json", {"checked_at": now(), "files": after, "unchanged": True})
    summary = {"round": "Round021", "finished_at": now(), "protocol_sha256": expected_protocol_sha256,
               "predictions_sha256": sha256(prediction_path), "selection_sha256": selection_hash,
               "fleet_vessels_predicted_before_label_access": len(predictions), "fleet_hourly_rows": total_hour_rows,
               "split": {"salt": SPLIT_SALT, "method": "sha256 sorted; alternating dev/validation before labels", "all_fleet": dict(Counter(split.values())), "linked_dev": len(dev_ids), "linked_validation": len(val_ids)},
               "selection": decision, "development": dev_comparison, "validation": val_comparison, "all_linked": all_comparison,
               "development_candidate": chosen != "B" and validation_selected["improvement_candidate"],
               "validation_other_alternative_evaluated": False,
               "input_and_code_before_after_hashes_unchanged": True,
               "hourly_manifest_and_partition_hashes_verified_before_after": True,
               "events": {"denominator": EXPECTED_EVENTS,
                          "B_matched_TP_events_max_one_per_vessel": sum(row["B_matched_tp_event"] for row in event_rows),
                          "selected_matched_TP_events_max_one_per_vessel": sum(row["selected_matched_tp_event"] for row in event_rows),
                          "B_raw_per_event_tolerance_flags": sum(row["B_raw_event_tolerance_flag"] for row in event_rows),
                          "selected_raw_per_event_tolerance_flags": sum(row["selected_raw_event_tolerance_flag"] for row in event_rows),
                          "raw_flags_are_TP_event_count": False},
               "radius_gate": {"quantile": 0.95, "method": "linear, whole 7372 fleet, label-blind", "threshold_km_full_precision": radius_threshold, "round019_peaks_sha256": sha256(PEAKS)},
               "fleet_selection_counts": counts,
               "scenario_assumptions": {"formula": "2*p*(H/nlinked)/(p*(1+A/nlinked)+(1-p)*(U/nunlinked))", "H_is_actual_selected_linked_timing_hits": True, "unlinked_status": "unknown comparison group; U is not confirmed FP", "assumed_prevalences": PREVALENCES, "transportability": "provisional linked and unlinked selection/timing rates are assumed to transport to target prevalence", "official_F1": False},
               "scope": {"conditional_timing_only_for_82_provisionally_linked_vessels": True, "labels_and_full_2026_reference_history_previously_reused": True, "split_isolates_rule_choice_only_not_unseen_reference_or_ground_truth": True, "pristine_holdout": False, "real_time_validation": False, "new_training": False, "2025_data_used": False, "external_identity_join": False},
               "audit": audit}
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "evaluation_integrity.json", {"finished_at": now(), "selection_still_matches": sha256(output_dir / "selection.json") == selection_hash,
               "all_output_files": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in sorted(output_dir.iterdir()) if path.is_file()}})
    print(json.dumps({"output_dir": str(output_dir), "selected_policy": chosen, "development_candidate": summary["development_candidate"]}, ensure_ascii=True), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=HERE / "evaluation_001")
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    evaluate(args.score_dir, args.output_dir, args.protocol_sha256)


if __name__ == "__main__":
    main()
