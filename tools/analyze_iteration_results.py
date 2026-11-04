#!/usr/bin/env python3
"""Audit the frozen S0 iteration experiment without fitting or reselecting."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.data import CLASS_NAMES, generate_dataset
from fishing_demo.features import feature_matrix as original_matrix
from fishing_demo.iteration_features import feature_matrix, feature_names, feature_units
from fishing_demo.models import Classifier, Preprocessor, softmax
from fishing_demo.pipeline import dataset_digest, save_json, split_indices
from tools import run_iterative_models as runner
# This calculator is independent of the runner's classification_metrics and
# was already checked with hand-calculated confusion matrices in the S0 study.
from tools.analyze_guided_baseline import (_close, _read_json, _same,
                                          manual_forward, recompute_metrics)

OUTPUT_NAMES = ("iteration_analysis.json", "iteration_trace.json", "improvement.png")
METRIC_KEYS = ("accuracy", "macro_f1", "nll", "brier", "confusion", "support")
DENOMINATOR_KEYS = ("total", "valid", "abstained", "evaluated_labeled", "support", "evaluation_row_sha256")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_file_hash(path, expected):
    actual = sha256(path)
    if actual != expected:
        raise AssertionError(f"artifact SHA256 mismatch: {Path(path).name}")
    return actual


def _safe_path(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("artifact path must be a nonempty relative path")
    result = (root / relative).resolve()
    if root not in result.parents:
        raise ValueError("artifact path escapes its expected directory")
    return result


def _valid_label(value):
    return type(value) is int and 0 <= value < len(CLASS_NAMES)


def _index_runs(records, seeds):
    required = {(seed, init) for seed in seeds for init in runner.INIT_SEEDS}
    index = {}
    for row in records:
        key = (row["data_seed"], row["init_seed"])
        if key in index:
            raise ValueError("duplicate generator/initialization pair")
        index[key] = row
    if index.keys() != required:
        raise ValueError("every preregistered generator/initialization pair is required")
    return index


def recompute_paired_summary(baseline_records, candidate_records, *, final=False):
    """Recompute the registered criteria after averaging the two initializations.

    This does not call runner.paired_summary. Rows are paired by generator seed
    and initialization, never by reused sample/vessel IDs alone.
    """
    seeds = runner.FINAL_SEEDS if final else runner.DEV_SEEDS
    baseline, changed = _index_runs(baseline_records, seeds), _index_runs(candidate_records, seeds)
    equal, per_seed = True, []
    for seed in seeds:
        item = {"data_seed": seed}
        for role in ("normal", "shift"):
            before, after = [], []
            for init in runner.INIT_SEEDS:
                left = baseline[(seed, init)]["metrics"][role]
                right = changed[(seed, init)]["metrics"][role]
                if any(left[key] != right[key] for key in DENOMINATOR_KEYS):
                    equal = False
                before.append(float(left["macro_f1"]))
                after.append(float(right["macro_f1"]))
            a, b = math.fsum(before) / len(before), math.fsum(after) / len(after)
            item[role] = {"baseline_macro_f1": a, "candidate_macro_f1": b, "delta": b - a}
        per_seed.append(item)
    normal = math.fsum(row["normal"]["delta"] for row in per_seed) / len(per_seed)
    shifts = np.asarray([row["shift"]["delta"] for row in per_seed])
    shift = float(math.fsum(shifts) / len(shifts))
    positive = int(sum(value > 0 for value in shifts))
    conditions = {"normal_delta_at_least_minus_0_01": normal >= -0.01,
                  "shift_delta_at_least_0_05": shift >= 0.05,
                  "positive_shift_seed_count": positive >= (8 if final else 4),
                  "same_denominators": equal}
    result = {"aggregation_unit": "generator_seed_after_mean_of_two_initializations",
              "per_seed": per_seed, "normal_mean_delta": normal, "shift_mean_delta": shift,
              "positive_shift_seeds": int(positive), "seed_count": len(seeds), "conditions": conditions}
    if final:
        rng = np.random.default_rng(20261026)
        resampled = rng.choice(shifts, size=(2000, len(shifts)), replace=True)
        low, high = np.quantile(resampled.mean(axis=1), [0.025, 0.975])
        result["shift_paired_bootstrap95"] = {"low": float(low), "high": float(high),
            "method": "generator_seed_paired_percentile_bootstrap", "repetitions": 2000, "seed": 20261026}
        conditions["shift_bootstrap_lower_above_zero"] = bool(low > 0)
    result["success" if final else "eligible"] = bool(all(conditions.values()))
    return result


def _index_predictions(predictions):
    result = {}
    for row in predictions:
        key = (row["generator_seed"], row["init_seed"], row["sample_id"])
        if key in result:
            raise ValueError("duplicate generator/initialization/sample prediction key")
        if row.get("source_type") != "synthetic" or row["split"] not in ("test", "stress"):
            raise ValueError("predictions must be synthetic normal/shift records")
        if row["status"] == "ok":
            p = np.asarray(row["probabilities"], dtype=float)
            if (p.shape != (3,) or not np.isfinite(p).all() or np.any(p < 0) or np.any(p > 1)
                    or not np.isclose(p.sum(), 1, rtol=0, atol=1e-7)):
                raise ValueError("invalid saved probability vector")
            if row["predicted_label"] != int(p.argmax()) or type(row["predicted_label"]) is not int:
                raise AssertionError("saved predicted label differs from probability argmax")
        elif row["status"] == "abstained":
            if row["probabilities"] is not None or row["predicted_label"] is not None:
                raise ValueError("abstained rows must retain null probabilities and prediction")
        else:
            raise ValueError("unknown saved prediction status")
        result[key] = row
    return result


def match_prediction_pairs(baseline_predictions, candidate_predictions):
    left, right = _index_predictions(baseline_predictions), _index_predictions(candidate_predictions)
    if left.keys() != right.keys():
        raise AssertionError("baseline/candidate prediction keys differ")
    paired = []
    for key in sorted(left):
        a, b = left[key], right[key]
        for field in ("vessel_id", "split", "true_label", "status"):
            _same(a[field], b[field], f"paired prediction {field}")
        paired.append((a, b))
    return paired


def select_fixture_cases(baseline_predictions, candidate_predictions):
    pairs = [(a, b) for a, b in match_prediction_pairs(baseline_predictions, candidate_predictions)
             if (a["generator_seed"], a["init_seed"], a["split"]) == (9101, 42, "stress")
             and a["status"] == "ok" and _valid_label(a["true_label"])]
    pairs.sort(key=lambda pair: pair[0]["sample_id"])
    improved = [(a, b) for a, b in pairs if a["predicted_label"] != a["true_label"]
                and b["predicted_label"] == b["true_label"]]
    remaining = [(a, b) for a, b in pairs if b["predicted_label"] != b["true_label"]]
    return {"improved": improved[0] if improved else None,
            "remaining_failure": remaining[0] if remaining else None,
            "counts": {"evaluated_shift": len(pairs), "baseline_wrong_candidate_correct": len(improved),
                       "candidate_wrong": len(remaining),
                       "baseline_correct_candidate_wrong": sum(a["predicted_label"] == a["true_label"]
                                                                 and b["predicted_label"] != b["true_label"]
                                                                 for a, b in pairs)}}


def audit_prediction_metrics(predictions, row, manifest):
    """Recalculate metrics, denominators and ordered evaluation-row identities."""
    _index_predictions(predictions)
    for p in predictions:
        if (p["generator_seed"], p["init_seed"]) != (row["data_seed"], row["init_seed"]):
            raise AssertionError("prediction file belongs to another generator/initialization")
    audited = {}
    for role, split in (("normal", "test"), ("shift", "stress")):
        rows = [p for p in predictions if p["split"] == split]
        usable = [p for p in rows if p["status"] == "ok" and _valid_label(p["true_label"])]
        metric = recompute_metrics([p["true_label"] for p in usable], [p["probabilities"] for p in usable])
        metric.update(total=len(rows), valid=sum(p["status"] == "ok" for p in rows),
                      abstained=sum(p["status"] == "abstained" for p in rows),
                      evaluated_labeled=len(usable),
                      evaluation_row_sha256=canonical_digest([p["sample_id"] for p in usable]),
                      evaluation_role=f"{row['phase']}_{role}")
        for key in METRIC_KEYS + ("total", "valid", "abstained", "evaluated_labeled", "evaluation_row_sha256", "evaluation_role"):
            _same(metric[key], row["metrics"][role][key], f"saved/recalculated {row['candidate']} {role}.{key}")
        for key in ("total", "valid", "abstained", "evaluated_labeled", "evaluation_row_sha256"):
            _same(metric[key], manifest["split_metadata"][split][key], f"manifest {role}.{key}")
        audited[role] = metric
    return audited


def _audit_artifact(out, row, config, results):
    model_path, prediction_path = _safe_path(out, row["model_path"]), _safe_path(out, row["predictions_path"])
    verify_file_hash(model_path, row["model_sha256"])
    verify_file_hash(prediction_path, row["predictions_sha256"])
    bundle = _read_json(model_path)
    manifest = results["dataset_manifest"][str(row["data_seed"])]
    for key, expected in (("schema_version", runner.MODEL_SCHEMA), ("source_type", "synthetic"),
                           ("coordinate_system", "local_xy_m"), ("class_names", CLASS_NAMES),
                           ("config", config), ("phase", row["phase"]), ("data_seed", row["data_seed"]),
                           ("init_seed", row["init_seed"]), ("dataset_sha256", manifest["dataset_sha256"]),
                           ("source_sha256", results["protocol"]["source_sha256_before_run"]),
                           ("feature_names", list(feature_names(config["family"]))),
                           ("feature_units", list(feature_units(config["family"]))),
                           ("feature_excludes", runner.FEATURE_EXCLUDES),
                           ("training_procedure", results["protocol"]["training_procedure"])):
        _same(bundle[key], expected, f"model metadata {key}")
    _same(row["dataset_sha256"], manifest["dataset_sha256"], "run/manifest dataset digest")
    _close(bundle["temperature"], row["temperature"], "run/model temperature")
    if bundle["temperature"] <= 0:
        raise ValueError("frozen temperature must be positive")
    preprocessor = Preprocessor.from_dict(bundle["preprocessor"])
    if preprocessor.n_features_ != len(feature_names(config["family"])):
        raise AssertionError("model preprocessing feature dimension differs")
    for key, split in (("fit_groups", "train"), ("selection_groups", "validation"), ("calibration_groups", "calibration")):
        _same(bundle[key], manifest["split_metadata"][split]["groups"], f"model {key}")
    if config["backend"] == "mlp":
        classifier = Classifier.from_dict(bundle["classifier"])
        if (classifier.input_dim != 2 * preprocessor.n_features_ or classifier.hidden != 16
                or classifier.l2 != 0 or classifier.seed != row["init_seed"] or classifier.n_classes != 3):
            raise AssertionError("saved MLP differs from the frozen model contract")
    else:
        state = bundle["classifier"]
        tree_path = model_path.with_suffix(".pkl")
        if state["format"] != "trusted_self_generated_pickle" or state["file"] != tree_path.name:
            raise ValueError("tree artifact must be the self-generated adjacent same-stem pickle")
        verify_file_hash(tree_path, state["sha256"])
    predictions = _read_json(prediction_path)
    audited = copy.deepcopy(row)
    audited["metrics"] = audit_prediction_metrics(predictions, row, manifest)
    return audited, predictions


def _audit_sources_and_protocol(out, results):
    protocol = results["protocol"]
    _same(_read_json(out / "protocol.json"), protocol, "saved/result protocol")
    for key, expected in (("development_data_seeds", list(runner.DEV_SEEDS)),
                           ("final_data_seeds", list(runner.FINAL_SEEDS)),
                           ("init_seeds", list(runner.INIT_SEEDS)), ("baseline", runner.BASELINE),
                           ("training_procedure", runner.TRAINING_PROCEDURE),
                           ("model_fixture", {"data_seed": 9101, "init_seed": 42})):
        _same(protocol[key], expected, f"registered protocol {key}")
    _same(protocol["candidate_rounds"], [[config for config in configs] for configs in runner.ROUNDS], "registered candidate order")
    _same(protocol["development_criteria"], {"normal_mean_delta_min": -.01, "shift_mean_delta_min": .05,
        "positive_shift_seed_min": 4, "same_denominators": True}, "development criteria")
    _same(protocol["final_criteria"], {"normal_mean_delta_min": -.01, "shift_mean_delta_min": .05,
        "positive_shift_seed_min": 8, "same_denominators": True, "shift_paired_bootstrap_lower_strictly_above": 0,
        "bootstrap_repetitions": 2000, "bootstrap_seed": 20261026}, "final criteria")
    sources = protocol["source_sha256_before_run"]
    if set(sources) != set(runner.SOURCE_FILES):
        raise AssertionError("source manifest differs from the frozen source list")
    for relative, digest in sources.items():
        verify_file_hash(_safe_path(ROOT, relative), digest)
        verify_file_hash(_safe_path(out / "source_snapshot", relative), digest)
    verify_file_hash(out / "protocol.md", protocol["protocol_sha256"])
    return sources


def _audit_development(results, audited_stages):
    if not audited_stages or audited_stages[0]["candidate"] != runner.BASELINE:
        raise AssertionError("first stage must be the registered fixed baseline")
    baseline = audited_stages[0]["records"]
    _index_runs(baseline, runner.DEV_SEEDS)
    expected_order, transitions, selected, summaries = [runner.BASELINE["name"]], [], None, {}
    stages = {stage["candidate"]["name"]: stage for stage in audited_stages}
    if len(stages) != len(audited_stages):
        raise ValueError("duplicate development candidate")
    for number, configs in enumerate(runner.ROUNDS, 1):
        evaluated, eligible = [], []
        for config in configs:
            name = config["name"]
            if name not in stages:
                raise ValueError("development analysis requires a completed registered round")
            stage = stages[name]
            _same(stage["candidate"], config, "registered development config")
            _same(stage["round"], number, "development round number")
            summary = recompute_paired_summary(baseline, stage["records"])
            _same(summary, stage["summary"], f"independent/saved development summary {name}")
            summaries[name] = summary
            expected_order.append(name)
            failed = [key for key, value in summary["conditions"].items() if not value]
            evaluated.append({"candidate": config, "hypothesis_before_run": stage["hypothesis"],
                "summary": summary, "eligible": summary["eligible"], "failed_conditions": failed,
                "decision_reason": "all registered development conditions passed" if not failed else "; ".join(failed)})
            if summary["eligible"]:
                eligible.append(config)
        action = "freeze_first_eligible_candidate" if eligible else ("advance_to_next_registered_round" if number < len(runner.ROUNDS) else "stop_no_eligible_candidate")
        transitions.append({"round": number, "evaluated": evaluated, "action": action,
                            "reason": "first eligible in fixed listed order" if eligible else "no candidate in this round passed every registered condition"})
        if eligible:
            selected = eligible[0]
            break
    _same([stage["candidate"]["name"] for stage in audited_stages], expected_order, "bounded development order")
    _same(results["selected_candidate"], selected, "saved/independently checked selection")
    return transitions, summaries


def _audit_freeze(out, results, sources):
    if results["selected_candidate"] is None:
        if results["final"]["executed"] or any(event["phase"] == "final" for event in results.get("generation_events", [])):
            raise AssertionError("final evaluation exists without development eligibility")
        return None
    frozen = _read_json(out / "freeze.json")
    verify_file_hash(out / "freeze.json", results["freeze"]["sha256"])
    _same(frozen, {key: value for key, value in results["freeze"].items() if key not in ("path", "sha256")}, "freeze/result freeze")
    for key, expected in (("schema_version", "fishing_iteration_freeze_v1"),
                           ("source_sha256", sources), ("selected_config", results["selected_candidate"]),
                           ("baseline_config", runner.BASELINE), ("training_procedure", runner.TRAINING_PROCEDURE),
                           ("protocol_sha256", results["protocol"]["protocol_sha256"]),
                           ("model_fixture", {"data_seed": 9101, "init_seed": 42}),
                           ("final_data_seeds", list(runner.FINAL_SEEDS)), ("init_seeds", list(runner.INIT_SEEDS)),
                           ("final_failure_research", False)):
        _same(frozen[key], expected, f"freeze {key}")
    if results["final"]["executed"]:
        events = [event for event in results["generation_events"] if event["phase"] == "final"]
        _same(sorted(event["seed"] for event in events), list(runner.FINAL_SEEDS), "final generation schedule")
        for event in events:
            _same(event["freeze_sha256"], results["freeze"]["sha256"], "generation freeze digest")
            if datetime.fromisoformat(event["at_utc"]) < datetime.fromisoformat(frozen["frozen_at_utc"]):
                raise AssertionError("recorded final generation precedes freezing")
    return frozen


def replay_fixture_if_completed(out, results):
    """Generate only fixed seed 9101, and only after final completion evidence.

    A development-only result returns None before the generator can be called.
    No other development/final data is regenerated by this analysis.
    """
    if not results["final"]["executed"]:
        return None
    if results.get("outcome") not in ("synthetic_improvement_confirmed", "final_improvement_not_confirmed"):
        raise ValueError("a completed final outcome is required before fixture replay")
    if not results.get("runtime", {}).get("finished_at_utc"):
        raise ValueError("final runtime completion evidence is required before fixture replay")
    evidence = _read_json(Path(out) / "run_evidence.json")
    _same(evidence["outcome"], results["outcome"], "final completion outcome")
    if not evidence.get("checks") or not all(evidence["checks"].values()):
        raise ValueError("final completion checks must pass before fixture replay")
    verify_file_hash(Path(out) / "results.json", evidence["artifact_sha256"]["results.json"])
    if results.get("freeze") is None or results.get("selected_candidate") is None:
        raise ValueError("verified selection/freeze is required before fixture replay")
    data = generate_dataset(seed=9101)
    expected = results["dataset_manifest"]["9101"]
    _same(dataset_digest(data), expected["dataset_sha256"], "replayed fixture dataset digest")
    _same(data["metadata"], expected["generator_metadata"], "replayed fixture generator metadata")
    return data


def trace_model(bundle, record, saved_prediction):
    """Expose the dynamic feature basis and frozen inference for one same row."""
    family, backend = bundle["config"]["family"], bundle["config"]["backend"]
    raw = feature_matrix([record], family)
    preprocessor = Preprocessor.from_dict(bundle["preprocessor"])
    mask = np.isnan(raw)
    imputed = np.where(mask, preprocessor.medians_, raw)
    scaled = (imputed - preprocessor.means_) / preprocessor.scales_
    model_input = np.concatenate((scaled, mask.astype(float)), axis=1)
    _close(model_input, preprocessor.transform(raw), "manual/public iteration preprocessing")
    if backend == "mlp":
        classifier = Classifier.from_dict(bundle["classifier"])
        logits, preactivation, hidden = manual_forward(classifier, model_input)
        raw_probabilities = softmax(logits)[0]
        score_kind = "MLP training logits"
    else:
        classifier = bundle["_classifier"]
        raw_probabilities = classifier.predict_proba(model_input)[0]
        logits = np.log(np.clip(raw_probabilities, np.finfo(float).tiny, 1.0))[None, :]
        preactivation = hidden = None
        score_kind = "tree log clipped probabilities; not tree training logits"
    probabilities = softmax(logits, bundle["temperature"])[0]
    public, valid = runner.predict_bundle(bundle, [record])
    if valid.tolist() != [True]:
        raise AssertionError("selected trace must pass the original geometry validity gate")
    _close(probabilities, public[0], "manual/public iteration probabilities")
    _close(probabilities, saved_prediction["probabilities"], "manual/saved iteration probabilities")
    truth, guess = record["label"], int(probabilities.argmax())
    if saved_prediction["true_label"] != truth or saved_prediction["predicted_label"] != guess:
        raise AssertionError("trace true/predicted labels disagree with saved prediction")
    return {"config": bundle["config"], "model_schema": bundle["schema_version"],
            "raw_feature_count": len(feature_names(family)), "model_input_count": model_input.shape[1],
            "phase1_input_count": 16, "input_count_differs_from_phase1": model_input.shape[1] != 16,
            "features": [{"index": i, "name": name, "unit": feature_units(family)[i],
                          "raw_value": None if np.isnan(raw[0, i]) else float(raw[0, i])}
                         for i, name in enumerate(feature_names(family))],
            "train_medians": preprocessor.medians_.tolist(), "train_means": preprocessor.means_.tolist(),
            "train_scales": preprocessor.scales_.tolist(), "imputed_features": imputed[0].tolist(),
            "scaled_features": scaled[0].tolist(), "missing_mask": mask[0].astype(int).tolist(),
            "model_input": model_input[0].tolist(), "input_order": "scaled features then missing mask",
            "hidden_preactivation": preactivation[0].tolist() if preactivation is not None else None,
            "hidden16": hidden[0].tolist() if hidden is not None else None,
            "logits_or_log_probabilities": logits[0].tolist(), "score_kind": score_kind,
            "probabilities_before_temperature": raw_probabilities.tolist(), "temperature": bundle["temperature"],
            "probabilities": probabilities.tolist(), "true_index": truth, "true_name": CLASS_NAMES[truth],
            "predicted_index": guess, "predicted_name": CLASS_NAMES[guess], "correct": truth == guess,
            "confidence": float(probabilities.max()),
            "nll": -math.log(max(float(probabilities[truth]), np.finfo(float).tiny)),
            "forward_matches_saved_atol_1e_10": True}


def _trace_fixture(out, results, data, prediction_cache):
    if data is None:
        return {"schema_version": "fishing_iteration_trace_v1", "source_type": "synthetic",
                "status": "development_only_no_final_fixture_generated", "fixed_fixture": None,
                "improved": None, "remaining_failure": None}
    left = _index_runs(results["final"]["baseline_records"], runner.FINAL_SEEDS)[(9101, 42)]
    right = _index_runs(results["final"]["candidate_records"], runner.FINAL_SEEDS)[(9101, 42)]
    models = [runner.load_iteration_model(_safe_path(out, row["model_path"]), trusted_local=True) for row in (left, right)]
    saved = [prediction_cache[row["predictions_path"]] for row in (left, right)]
    rows = [row for row in data["records"] if row["split"] in ("test", "stress")]
    _, details = original_matrix(data["records"])
    indices, _ = split_indices(data["records"], details)
    for model, predictions in zip(models, saved):
        family = model["config"]["family"]
        train = feature_matrix(data["records"], family)[indices["train"]]
        medians = np.array([np.median(column[~np.isnan(column)]) if (~np.isnan(column)).any() else 0 for column in train.T])
        filled = np.where(np.isnan(train), medians, train)
        means, scales = filled.mean(axis=0), filled.std(axis=0, ddof=0)
        scales[scales == 0] = 1
        for key, values in (("medians", medians), ("means", means), ("scales", scales)):
            _close(values, model["preprocessor"][key], f"replayed train-only frozen {key}")
        probabilities, valid = runner.predict_bundle(model, rows)
        lookup = {p["sample_id"]: p for p in predictions}
        for row, p, usable in zip(rows, probabilities, valid):
            saved_row = lookup[row["sample_id"]]
            _same(saved_row["true_label"], row["label"], "replayed/saved true label")
            _same(saved_row["vessel_id"], row["vessel_id"], "replayed/saved vessel ID")
            _same(saved_row["split"], row["split"], "replayed/saved split")
            if bool(usable) != (saved_row["status"] == "ok"):
                raise AssertionError("replayed/saved validity differs")
            if usable:
                _close(p, saved_row["probabilities"], "fixture reloaded/saved probabilities")
        changed = copy.deepcopy(rows)
        for row in changed:
            row["label"] = None
            row["sample_id"] += "-metadata-check"
            row["vessel_id"] += "-metadata-check"
            row["quality"] = {"ignored": "metadata"}
            row["sim_times"] = [[t * 10 + 1 for t in times] for times in row["sim_times"]]
            row["split"] = "train" if row["split"] == "stress" else "stress"
            row["scenario"] = "shift" if row["split"] == "stress" else "base"
        changed_p, changed_valid = runner.predict_bundle(model, changed)
        np.testing.assert_array_equal(probabilities, changed_p)
        np.testing.assert_array_equal(valid, changed_valid)
    cases = select_fixture_cases(*saved)
    raw_lookup = {row["sample_id"]: row for row in data["records"]}
    result = {"schema_version": "fishing_iteration_trace_v1", "source_type": "synthetic", "status": "final_fixture_replayed_and_checked",
        "fixed_fixture": {"generator_seed": 9101, "init_seed": 42, "evaluation_role": "final_shift",
                          "dataset_sha256": dataset_digest(data), "replay_digest_matches": True},
        "selection_rule": {"improved": "first baseline-wrong/candidate-correct shift sample by sample_id",
                           "remaining_failure": "first candidate-wrong shift sample by sample_id"},
        "counts": cases["counts"], "feature_basis": {"baseline": "original8 -> 16 inputs",
            "selected": f"{models[1]['config']['family']} -> {2 * len(models[1]['feature_names'])} inputs",
            "same_raw_record_different_feature_basis": True},
        "checks": {"replayed_model_predictions_match_saved": True, "train_statistics_match_frozen": True,
                   "label_identifier_split_time_quality_changes_leave_inference_identical": True},
        "meaning": "Replayed generated raw_record; no real observation or actual speed/acceleration."}
    for name in ("improved", "remaining_failure"):
        pair = cases[name]
        if pair is None:
            result[name] = None
            result[f"{name}_status"] = "no_example_under_fixed_fixture_rule"
        else:
            row = raw_lookup[pair[0]["sample_id"]]
            result[name] = {"sample_id": row["sample_id"], "source_type": "synthetic",
                "raw_record_is_real_observation": False, "raw_record": row,
                "baseline": trace_model(models[0], row, pair[0]),
                "selected": trace_model(models[1], row, pair[1]),
                "observed_outcome": "baseline wrong, selected correct" if name == "improved" else "selected remains wrong",
                "identified_cause": None,
                "hypotheses_not_confirmed": ["Feature compression, noise, fragmentation or overlapping generating families may contribute; this example does not isolate a cause."]}
            result[f"{name}_status"] = "available"
    return result


def _mean_score(records, role):
    return math.fsum(row["metrics"][role]["macro_f1"] for row in records) / len(records)


def _plot(path, stages, final_summary, trace):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    x = np.arange(len(stages))
    for role, color in (("normal", "#2369a0"), ("shift", "#df7d21")):
        axes[0, 0].plot(x, [_mean_score(stage["records"], role) for stage in stages], "o-", color=color, label=role)
    axes[0, 0].set_xticks(x, [stage["candidate"]["name"].replace("_", "\n", 1) for stage in stages], fontsize=8)
    axes[0, 0].set_ylabel("Development macro F1")
    axes[0, 0].set_ylim(0, 1)
    axes[0, 0].set_title("Registered development candidates (5 generator seeds)")
    axes[0, 0].legend()
    axes[0, 0].grid(alpha=0.2)
    if final_summary is None:
        for ax in (axes[0, 1], axes[1, 0], axes[1, 1]):
            ax.text(.5, .5, "Final not executed\nNo final data generated by analysis", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
    else:
        per_seed = final_summary["per_seed"]
        for offset, key, name, color in ((-.18, "baseline_macro_f1", "Frozen baseline", "#8a8d91"),
                                         (.18, "candidate_macro_f1", "Frozen selected", "#2a8c69")):
            means = [math.fsum(row[role][key] for row in per_seed) / len(per_seed) for role in ("normal", "shift")]
            bars = axes[0, 1].bar(np.arange(2) + offset, means, width=.36, label=name, color=color)
            axes[0, 1].bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        axes[0, 1].set_xticks([0, 1], ["normal", "shift"])
        axes[0, 1].set_ylim(0, 1)
        axes[0, 1].set_ylabel("Final mean macro F1")
        axes[0, 1].set_title("Locked final: 10 seed means, two initializations each")
        axes[0, 1].legend(fontsize=9)
        axes[1, 0].bar(np.arange(len(per_seed)), [row["shift"]["delta"] for row in per_seed], color="#2a8c69")
        axes[1, 0].axhline(0, color="black", linewidth=.8)
        axes[1, 0].set_xticks(np.arange(len(per_seed)), [str(row["data_seed"]) for row in per_seed], rotation=40, fontsize=8)
        axes[1, 0].set_ylabel("Selected minus baseline: shift macro F1")
        interval = final_summary["shift_paired_bootstrap95"]
        axes[1, 0].set_title(f"Paired generator-seed deltas; mean={final_summary['shift_mean_delta']:+.3f}\nSeed bootstrap 95% [{interval['low']:+.3f}, {interval['high']:+.3f}]")
        axes[1, 0].grid(axis="y", alpha=.2)
        axes[1, 1].set_axis_off()
        axes[1, 1].set_title("Fixed 9101 / init 42 / shift examples", pad=6)
        for name, left, color, title in (("improved", .02, "#2a8c69", "Improved"),
                                        ("remaining_failure", .53, "#b84d4d", "Remaining error")):
            ax = axes[1, 1].inset_axes([left, .06, .45, .75])
            case = trace.get(name)
            if case is None:
                ax.text(.5, .5, "No example under\nfixed selection rule", ha="center", va="center", transform=ax.transAxes)
                ax.set_axis_off()
                continue
            for part in case["raw_record"]["parts"]:
                if part:
                    xy = np.asarray(part)
                    ax.plot(xy[:, 0], xy[:, 1], ".-", color=color, markersize=2, linewidth=1.2)
            ax.set_title(f"{title}: {case['sample_id']}\ntrue={case['selected']['true_name']}\nbase={case['baseline']['predicted_name']}; selected={case['selected']['predicted_name']}", fontsize=7)
            ax.set_xlabel("Local x (m)", fontsize=8)
            ax.set_ylabel("Local y (m)", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.set_aspect("equal", adjustable="datalim")
            ax.grid(alpha=.2)
    fig.suptitle("S0 synthetic iteration audit | frozen procedure | no real-data performance claim", fontsize=13)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def analyze(output_dir):
    out = Path(output_dir).resolve()
    if (ROOT / "outputs").resolve() not in out.parents:
        raise ValueError("analyze the self-generated experiment directory under project outputs")
    preserved = {path.relative_to(out).as_posix(): path for path in out.rglob("*")
                 if path.is_file() and path.relative_to(out).as_posix() not in OUTPUT_NAMES}
    if "results.json" not in preserved:
        raise ValueError("results.json is required")
    for name in OUTPUT_NAMES:
        target = out / name
        if target.resolve().parent != out:
            raise ValueError("analysis output must not alias a file outside its directory")
        if any(target.exists() and target.samefile(source) for source in preserved.values()):
            raise ValueError("analysis output would overwrite a preserved input")
    hashes = {name: sha256(path) for name, path in preserved.items()}
    results = _read_json(out / "results.json")
    if results.get("schema_version") != "fishing_iteration_results_v1" or results.get("source_type") != "synthetic":
        raise ValueError("only the frozen synthetic iteration result schema is supported")
    sources = _audit_sources_and_protocol(out, results)
    audited_stages, prediction_cache, model_count = [], {}, 0
    for stage in results["stage_results"]:
        audited = {key: value for key, value in stage.items() if key != "records"}
        audited["records"] = []
        for row in stage["records"]:
            if row["candidate"] != stage["candidate"]["name"] or row["phase"] != "development":
                raise AssertionError("development run identity differs from its stage")
            checked, predictions = _audit_artifact(out, row, stage["candidate"], results)
            audited["records"].append(checked)
            prediction_cache[row["predictions_path"]] = predictions
            model_count += 1
        audited_stages.append(audited)
    transitions, development_summaries = _audit_development(results, audited_stages)
    frozen = _audit_freeze(out, results, sources)
    final_summary, final_audited = None, {}
    if results["final"]["executed"]:
        for key, config in (("baseline_records", runner.BASELINE), ("candidate_records", results["selected_candidate"])):
            final_audited[key] = []
            for row in results["final"][key]:
                if row["candidate"] != config["name"] or row["phase"] != "final":
                    raise AssertionError("final run identity differs from its frozen config")
                checked, predictions = _audit_artifact(out, row, config, results)
                final_audited[key].append(checked)
                prediction_cache[row["predictions_path"]] = predictions
                model_count += 1
        final_summary = recompute_paired_summary(final_audited["baseline_records"], final_audited["candidate_records"], final=True)
        _same(final_summary, results["final"]["summary"], "independent/saved final summary")
        _same(final_summary["success"], results["final"]["success"], "independent/saved final success")
        expected_outcome = "synthetic_improvement_confirmed" if final_summary["success"] else "final_improvement_not_confirmed"
        _same(results["outcome"], expected_outcome, "registered final outcome")
    # No final generation happens above. Only a completed final run can reach
    # the generator inside replay_fixture_if_completed, and it replays 9101.
    data = replay_fixture_if_completed(out, results)
    trace = _trace_fixture(out, results, data, prediction_cache)
    if "run_evidence.json" in preserved:
        evidence = _read_json(out / "run_evidence.json")
        for relative, digest in evidence["artifact_sha256"].items():
            verify_file_hash(_safe_path(out, relative), digest)
    checks = {"source_snapshot_and_live_source_match_freeze": True, "all_model_and_prediction_file_hashes_match": True,
        "saved_prediction_metrics_independently_recomputed": True, "development_selection_order_and_criteria_match": True,
        "final_paired_summary_and_success_match": True if final_summary is not None else None,
        "final_fixture_generated_only_after_completed_final_run": data is not None,
        "no_final_fixture_generated_for_development_only_result": data is None if final_summary is None else None,
        "preserved_input_hashes_unchanged": True, "no_fit_or_model_reselection_performed": True}
    analysis = {"schema_version": "fishing_iteration_analysis_v1", "source_type": "synthetic",
        "outcome": results.get("outcome", "development_only_final_not_completed"),
        "selected_candidate": results["selected_candidate"], "development_transitions": transitions,
        "development_summaries": development_summaries, "final_summary": final_summary,
        "final_seed_mean_scores": {role: {key: math.fsum(row[role][key] for row in final_summary["per_seed"]) / len(final_summary["per_seed"])
                                          for key in ("baseline_macro_f1", "candidate_macro_f1")}
                                   for role in ("normal", "shift")} if final_summary else None,
        "audited_model_count": model_count, "independent_metric_audits": {"development": audited_stages, "final": final_audited},
        "freeze_sha256": sha256(out / "freeze.json") if frozen else None,
        "input_sha256": hashes, "source_sha256": sources, "checks": checks,
        "fixture": {"status": trace["status"], "fixed_fixture": trace["fixed_fixture"], "counts": trace.get("counts"),
                    "improved_sample_id": trace["improved"]["sample_id"] if trace["improved"] else None,
                    "remaining_failure_sample_id": trace["remaining_failure"]["sample_id"] if trace["remaining_failure"] else None},
        "observations": ["Each development candidate was checked against the same seed/initialization/row identities.",
            "Final comparison averages the two initializations within each of ten generator seeds before pairing.",
            "Selection follows preregistered eligibility and listed order, not the highest final score.",
            "The trace compares the same generated row using separate frozen feature bases and input dimensions."],
        "hypotheses_not_identified_causes": ["Geometric compression, fragmented observations, coordinate noise and overlapping generating families may contribute to remaining errors.",
            "Development results can support or weaken a feature-change hypothesis but do not isolate each feature's causal effect; changing dimension also changes initialization arrays."],
        "limitations": ["All seeds share one synthetic generator; no actual-data, actual-vessel or accident-detection generalization is established.",
            "Normal mean delta >= -0.01 is a registered design criterion, not a statistical noninferiority proof.",
            "No fitting, calibration fitting, final-result-driven retuning, hardware test or external collection is performed by this analysis.",
            "Replayed raw_record is synthetic generated input; sim_times are not actual observation times.",
            "Technical success and learner understanding are separate; learner understanding remains not assessed."],
        "learner_understanding": "not_assessed",
        "analysis_implementation_sha256": {"tools/analyze_iteration_results.py": sha256(__file__),
                                          "tools/analyze_guided_baseline.py": sha256(ROOT / "tools/analyze_guided_baseline.py")}}
    _plot(out / "improvement.png", audited_stages, final_summary, trace)
    if hashes != {name: sha256(path) for name, path in preserved.items()}:
        raise AssertionError("preserved input changed during analysis")
    save_json(out / "iteration_trace.json", trace)
    save_json(out / "iteration_analysis.json", analysis)
    print(f"Iteration audit passed: {model_count} frozen models; outcome={analysis['outcome']}")
    print(f"Fixed examples: improved={analysis['fixture']['improved_sample_id']}; remaining={analysis['fixture']['remaining_failure_sample_id']}")
    return analysis, trace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/iterative_models_20261026")
    args = parser.parse_args(argv)
    try:
        analyze(args.out)
    except (ValueError, AssertionError, OSError, KeyError, TypeError, ImportError) as exc:
        parser.exit(2, f"Iteration analysis failed: {exc}\n")


if __name__ == "__main__":
    main()
