#!/usr/bin/env python3
"""Independently verify completed S0 comparison evidence without fitting models.

Reads one prediction/model/dataset at a time. The only write is a separate
audit JSON outside the frozen experiment. --self-test touches no experiment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEEDS = tuple(range(12101, 12111))
INITS = (42, 137)
METRICS = ("accuracy", "macro_f1", "nll", "brier")
NAMES = ("shape9_mlp_e400_l2_0", "shape9_mlp_e1200_l2_0", "shape9_mlp_e1200_l2_0_001",
         "shape9_mlp_e1200_l2_0_01", "shape9_linear_e1200_l2_0_01", "shape9_extratrees",
         "shape9_simtime4_mlp_e400_l2_0", "shape9_edge3_mlp_e400_l2_0", "shape9_dt_only_mlp_e400_l2_0")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def reject(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream, parse_constant=reject)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def safe_path(directory, relative):
    directory = Path(directory).resolve()
    path = (directory / relative).resolve()
    require(not Path(relative).is_absolute() and directory in path.parents, "artifact outside evidence directory")
    return path


def independent_metrics(labels, probabilities):
    labels, probabilities = np.asarray(labels), np.asarray(probabilities, dtype=float)
    require(labels.ndim == 1 and labels.size > 0 and probabilities.shape == (labels.size, 3), "invalid metric input shape")
    require(np.issubdtype(labels.dtype, np.integer) and ((0 <= labels) & (labels < 3)).all(), "invalid class labels")
    require(np.isfinite(probabilities).all() and ((0 <= probabilities) & (probabilities <= 1)).all()
        and np.allclose(probabilities.sum(axis=1), 1, rtol=0, atol=1e-12), "invalid probability distribution")
    predicted = probabilities.argmax(axis=1)
    confusion = np.zeros((3, 3), dtype=int)
    for truth, guess in zip(labels, predicted):
        confusion[int(truth), int(guess)] += 1
    support = confusion.sum(axis=1)
    f1 = []
    for k in range(3):
        denominator = int(support[k] + confusion[:, k].sum())
        f1.append(2 * int(confusion[k, k]) / denominator if denominator else 0.0)
    chosen = np.maximum(probabilities[np.arange(labels.size), labels], np.finfo(float).tiny)
    target = np.eye(3)[labels]
    return {"accuracy": float(np.trace(confusion) / labels.size), "macro_f1": float(np.mean(f1)),
        "nll": float(-np.log(chosen).mean()), "brier": float(((probabilities - target) ** 2).sum(axis=1).mean()),
        "confusion": confusion.tolist(), "support": support.tolist()}


def bootstrap(differences):
    differences = np.asarray(differences, dtype=float)
    require(differences.shape == (10,) and np.isfinite(differences).all(), "bootstrap needs ten finite seed means")
    rng = np.random.default_rng(20261027)
    draws = rng.integers(0, 10, size=(2000, 10))
    return np.quantile(differences[draws].mean(axis=1), [.025, .975])


class Audit:
    def __init__(self):
        self.hashes = {}
        self.maximum_differences = {"prediction_metrics": 0.0, "seed_aggregation_and_intervals": 0.0}
        self.comparisons = 0

    def file_hash(self, path, expected=None):
        actual = sha256(path)
        if expected is not None:
            require(actual == expected, f"hash mismatch: {path}")
        self.hashes[str(Path(path).resolve())] = actual
        return actual

    def close(self, actual, recorded, category):
        require(np.isfinite(actual) and np.isfinite(recorded), "nonfinite compared metric")
        delta = float(abs(actual - recorded))
        self.maximum_differences[category] = max(self.maximum_differences[category], delta)
        self.comparisons += 1
        require(delta <= 1e-12, f"numeric mismatch: {actual} != {recorded}")


def verify(directory):
    audit = Audit()
    directory = directory.resolve()
    result_path = directory / "results.json"
    results = read_json(result_path)
    require(results.get("status") == "complete", "final execution must be complete before auditing")
    result_hash = audit.file_hash(result_path)
    require(results["source_type"] == "synthetic" and len(results["stage_results"]) == 9, "requires nine completed synthetic models")
    stages = results["stage_results"]
    require(tuple(stage["candidate"]["name"] for stage in stages) == NAMES, "fixed nine-model order changed")
    protocol, frozen = read_json(directory / "protocol.json"), read_json(directory / "freeze.json")
    protocol_hash = audit.file_hash(directory / "protocol.json", results["protocol_sha256"])
    freeze_hash = audit.file_hash(directory / "freeze.json", results["freeze"]["sha256"])
    require(results["protocol"] == protocol and {k: v for k, v in results["freeze"].items() if k not in ("path", "sha256")} == frozen,
        "embedded protocol/freeze differ from files")
    for name, expected in (("protocol", protocol_hash), ("freeze", freeze_hash)):
        sidecar = directory / f"{name}.sha256"
        require(sidecar.read_text(encoding="ascii").strip() == expected, "hash sidecar differs")
        audit.file_hash(sidecar)
    sources = protocol["source_sha256_before_run"]
    require(sources == frozen["source_sha256"] and frozen["protocol_sha256"] == protocol_hash, "source/protocol lock differs")
    require(protocol["final_data_seeds"] == list(SEEDS) and frozen["final_data_seeds"] == list(SEEDS)
        and protocol["init_seeds"] == list(INITS) and frozen["init_seeds"] == list(INITS), "seed schedule changed")
    require([protocol["baseline"], *protocol["candidates"]] == [stage["candidate"] for stage in stages], "candidate lock differs")
    for field in ("development", "baseline", "candidates", "primary_candidate", "training_procedure",
                  "development_selection_procedure", "final_criteria", "intervals", "other_comparisons"):
        require(frozen[field] == protocol[field], f"freeze contract differs: {field}")
    require(protocol["primary_candidate"] is None and frozen["primary_candidate"] is None
        and results["selected_development_candidate"] is None and results["primary"]["candidate"] is None
        and results["primary"]["success"] is None, "this run must preserve no primary")
    require(protocol["candidate_selection_from_final_scores"] is False and frozen["candidate_selection_from_final_scores"] is False
        and results["final_scores_used_for_selection"] is False, "final-score selection forbidden")
    require(protocol["other_comparisons"] == "auxiliary_exploratory_unadjusted_for_multiple_comparisons", "auxiliary scope changed")
    dev = Path(protocol["development"]["path"])
    for relative, key in (("results.json", "results_sha256"), ("protocol.json", "protocol_sha256"), ("run_evidence.json", "run_evidence_sha256")):
        audit.file_hash(dev / relative, protocol["development"][key])
    dev_results = read_json(dev / "results.json")
    require(dev_results["selected_development_candidate"] is None, "development primary changed")
    require(all(not stage["summary"]["eligible"] for stage in dev_results["stage_results"][1:]
        if stage["candidate"].get("formal_selection", True)), "formal development eligibility contradicts no primary")
    for name, expected in sources.items():
        audit.file_hash(ROOT / name, expected)
        audit.file_hash(safe_path(directory / "source_snapshot", name), expected)
        audit.file_hash(safe_path(dev / "source_snapshot", name), expected)

    events = read_json(directory / "generation_events.json")
    require(events == results["generation_events"] and [event["seed"] for event in events] == list(SEEDS), "generation events differ")
    freeze_time = datetime.fromisoformat(frozen["frozen_at_utc"])
    expected_rows, expected_groups, dataset_hashes = {}, {}, {}
    for event in events:
        seed = event["seed"]
        require(event["phase"] == "final" and event["freeze_sha256"] == freeze_hash
            and event["protocol_sha256"] == protocol_hash and event["source_sha256"] == sources, "generation lock mismatch")
        require(freeze_time <= datetime.fromisoformat(event["verified_before_generation_at_utc"])
            <= datetime.fromisoformat(event["generated_at_utc"]), "generation preceded freeze")
        dataset_path = directory / "datasets" / f"seed_{seed}.json"
        audit.file_hash(dataset_path, event["dataset_file_sha256"])
        dataset = read_json(dataset_path)
        require(dataset["metadata"]["source_type"] == "synthetic" and dataset["metadata"]["seed"] == seed, "dataset is not the fixed synthetic seed")
        dataset_hashes[seed] = canonical_hash(dataset)
        require(dataset_hashes[seed] == event["dataset_sha256"] == results["dataset_manifest"][str(seed)]["dataset_sha256"], "dataset content hash differs")
        expected_rows[seed] = [[row["sample_id"], row["vessel_id"], row["split"], row["label"], "ok"]
            for row in dataset["records"] if row["split"] in ("test", "stress")]
        expected_groups[seed] = {split: sorted({row["vessel_id"] for row in dataset["records"] if row["split"] == split})
            for split in ("train", "validation", "calibration", "test", "stress")}
        group_sets = list(map(set, expected_groups[seed].values()))
        require(all(not a & b for i, a in enumerate(group_sets) for b in group_sets[i + 1:]), "dataset vessel leakage")
        del dataset

    recomputed, model_table, observed_records = {}, [], 0
    for stage in stages:
        config, indexed = stage["candidate"], {}
        require(stage["status"] == "complete" and len(stage["records"]) == 20, "stage incomplete")
        for row in stage["records"]:
            key = (row["data_seed"], row["init_seed"])
            require(key not in indexed and key[0] in SEEDS and key[1] in INITS, "duplicate or out-of-schedule run")
            seed, init = key
            require(row["phase"] == "final" and row["candidate"] == config["name"], "run identity differs")
            model_path, predictions_path = safe_path(directory, row["model_path"]), safe_path(directory, row["predictions_path"])
            audit.file_hash(model_path, row["model_sha256"])
            audit.file_hash(predictions_path, row["predictions_sha256"])
            model = read_json(model_path)
            require(model["config"] == config and model["data_seed"] == seed and model["init_seed"] == init
                and model["source_type"] == "synthetic" and model["source_sha256"] == sources
                and model["phase"] == "final" and model["dataset_sha256"] == dataset_hashes[seed] == row["dataset_sha256"], "model metadata differs")
            require(np.isfinite(model["temperature"]) and model["temperature"] > 0
                and model["temperature"] == row["temperature"], "saved calibrated temperature differs")
            require(model["simtime_source"] == (config["family"] in ("shape9_simtime4", "shape9_dt_only")), "simulated timing provenance differs")
            for model_key, split in (("fit_groups", "train"), ("selection_groups", "validation"), ("calibration_groups", "calibration")):
                require(model[model_key] == expected_groups[seed][split], "model group contract differs")
            require(canonical_hash(model["preprocessor"]) == row["preprocessor_sha256"], "preprocessor hash differs")
            if config["backend"] == "extratrees":
                audit.file_hash(model_path.with_suffix(".pkl"), model["classifier"]["sha256"])
            predictions = read_json(predictions_path)
            identities = [[p["sample_id"], p["vessel_id"], p["split"], p["true_label"], p["status"]] for p in predictions]
            require(identities == expected_rows[seed] and len({(p["split"], p["sample_id"]) for p in predictions}) == 288, "evaluation identities/labels/validity differ")
            require(canonical_hash(identities) == row["evaluation_identity_sha256"], "identity digest differs")
            for prediction in predictions:
                role = {"test": "normal", "stress": "shift"}[prediction["split"]]
                require(prediction["generator_seed"] == seed and prediction["init_seed"] == init
                    and prediction["source_type"] == "synthetic" and prediction["evaluation_role"] == f"final_{role}", "prediction metadata differs")
            indexed[key] = {}
            for split, role in (("test", "normal"), ("stress", "shift")):
                selected = [p for p in predictions if p["split"] == split]
                require(len(selected) == 144 and all(p["status"] == "ok" for p in selected), "requires 144 valid rows per evaluation split")
                metrics = independent_metrics([p["true_label"] for p in selected], [p["probabilities"] for p in selected])
                require(all(p["predicted_label"] == int(np.argmax(p["probabilities"])) for p in selected), "prediction label is not probability argmax")
                recorded = row["metrics"][role]
                require(recorded["confusion"] == metrics["confusion"] and recorded["support"] == metrics["support"] == [48, 48, 48], "confusion/support differs")
                require((recorded["total"], recorded["valid"], recorded["abstained"], recorded["evaluated_labeled"]) == (144, 144, 0, 144)
                    and recorded["evaluation_role"] == f"final_{role}", "metric denominator/role differs")
                require(recorded["evaluation_row_sha256"] == canonical_hash([[seed, p["sample_id"]] for p in selected]), "evaluation row digest differs")
                for metric in METRICS:
                    audit.close(metrics[metric], recorded[metric], "prediction_metrics")
                indexed[key][role] = metrics
                observed_records += len(selected)
            del model, predictions
        require(set(indexed) == {(seed, init) for seed in SEEDS for init in INITS}, "missing run pair")
        recomputed[config["name"]] = indexed

    baseline = recomputed[NAMES[0]]
    for stage in stages:
        name, summary = stage["candidate"]["name"], stage["summary"]
        require(summary["role"] == "auxiliary_exploratory" and summary["multiplicity_adjustment"] == "none"
            and summary["primary_success"] is None and summary["seed_count"] == 10
            and summary["aggregation_unit"] == "generator_seed_after_mean_of_two_initializations", "summary scope/unit differs")
        candidate, display = recomputed[name], {"candidate": name, "mean_metrics": {}, "intervals": {}}
        for role in ("normal", "shift"):
            display["mean_metrics"][role], display["intervals"][role] = {}, {}
            for metric in METRICS:
                deltas = []
                for index, seed in enumerate(SEEDS):
                    before = float(np.mean([baseline[(seed, init)][role][metric] for init in INITS]))
                    after = float(np.mean([candidate[(seed, init)][role][metric] for init in INITS]))
                    delta = after - before
                    deltas.append(delta)
                    recorded = summary["per_seed_metric_differences"][index]
                    require(recorded["data_seed"] == seed, "summary seed order differs")
                    for field, value in (("baseline", before), ("candidate", after), ("delta", delta)):
                        audit.close(value, recorded[role][metric][field], "seed_aggregation_and_intervals")
                    if metric == "macro_f1":
                        simple = summary["per_seed"][index]
                        require(simple["data_seed"] == seed, "simple summary seed order differs")
                        for field, value in (("baseline_macro_f1", before), ("candidate_macro_f1", after), ("delta", delta)):
                            audit.close(value, simple[role][field], "seed_aggregation_and_intervals")
                mean = float(np.mean([candidate[(seed, init)][role][metric] for seed in SEEDS for init in INITS]))
                audit.close(mean, summary["mean_metrics"][role][metric], "seed_aggregation_and_intervals")
                low, high = bootstrap(deltas)
                interval = summary["paired_bootstrap95"][role][metric]
                require(interval["repetitions"] == 2000 and interval["seed"] == 20261027 and interval["seed_count"] == 10
                    and interval["multiplicity_adjustment"] == "none" and interval["confidence_level"] == .95
                    and interval["method"] == "generator_seed_paired_percentile_bootstrap", "bootstrap metadata differs")
                audit.close(float(low), interval["low"], "seed_aggregation_and_intervals")
                audit.close(float(high), interval["high"], "seed_aggregation_and_intervals")
                display["mean_metrics"][role][metric] = mean
                display["intervals"][role][metric] = [float(low), float(high)]
                if metric == "macro_f1":
                    audit.close(float(np.mean(deltas)), summary[f"{role}_mean_delta"], "seed_aggregation_and_intervals")
                    if role == "shift":
                        require(sum(d > 0 for d in deltas) == summary["positive_shift_seeds"], "positive seed count differs")
        require(summary["shift_paired_bootstrap95"] == summary["paired_bootstrap95"]["shift"]["macro_f1"], "shift interval alias differs")
        expected_conditions = {"normal_delta_at_least_minus_0_01": summary["normal_mean_delta"] >= -.01,
            "shift_delta_at_least_0_05": summary["shift_mean_delta"] >= .05, "positive_shift_seed_min": summary["positive_shift_seeds"] >= 8,
            "same_denominators": True, "finite_metrics": True, "shift_bootstrap_lower_above_zero": summary["shift_paired_bootstrap95"]["low"] > 0}
        require(summary["conditions"] == expected_conditions, "final conditions differ")
        model_table.append(display)

    evidence = read_json(directory / "run_evidence.json")
    require(evidence["checks"] == results["checks"] and all(value is True for value in results["checks"].values()), "final checks failed")
    require(evidence["protocol_sha256"] == protocol_hash and evidence["freeze_sha256"] == freeze_hash, "completion lock differs")
    for relative, expected in evidence["artifact_sha256"].items():
        audit.file_hash(safe_path(directory, relative), expected)
    require(audit.file_hash(result_path) == result_hash, "results changed during audit")
    return {"schema_version": "critique_comparison_independent_audit_v1", "passed": True, "source_type": "synthetic",
        "state": "completed_final_evidence_verified_no_fit_no_reselection", "probability_type": "saved_temperature_calibrated",
        "probability_type_code_evidence": "tools/critique_comparison_20261027.py: calibrated loop False,True; final probs saved",
        "tested_cases": {"models": 9, "runs": 180, "evaluation_split_metrics": 360, "prediction_rows": observed_records,
            "generator_seeds": 10, "initializations_per_seed": 2, "bootstrap_repetitions": 2000,
            "bootstrap_intervals": 72, "numeric_comparisons": audit.comparisons, "file_hashes_checked": len(audit.hashes)},
        "maximum_absolute_differences": audit.maximum_differences, "primary": None,
        "all_models_auxiliary_exploratory": True, "multiplicity_adjustment": "none", "model_table": model_table,
        "file_sha256": audit.hashes,
        "limitations": ["S0 synthetic generated path classes only; no real-data or hardware performance claim.",
            "Simulated timing is not real speed, and score differences do not identify an independent causal benefit of time.",
            "This audit verifies stored calibrated probabilities, bookkeeping, hashes and statistics, not the correctness of all model internals.",
            "No fitting, inference re-execution, data generation, tuning or candidate reselection is performed."],
        "execution": {"argv": [sys.executable, *sys.argv], "python": platform.python_version(), "numpy": np.__version__,
            "platform": platform.platform(), "utc": datetime.now(timezone.utc).isoformat(), "script_sha256": sha256(__file__)}}


def self_test():
    probabilities = np.asarray([[.7, .2, .1], [.2, .6, .2], [.1, .3, .6]])
    metrics = independent_metrics([0, 1, 2], probabilities)
    require(metrics["confusion"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]] and metrics["macro_f1"] == 1,
        "known confusion/F1 check failed")
    require(abs(metrics["nll"] + np.log([.7, .6, .6]).mean()) < 1e-15, "known NLL check failed")
    require(np.allclose(bootstrap([.05] * 10), [.05, .05], rtol=0, atol=1e-15), "constant paired bootstrap check failed")
    for invalid in (probabilities * 2, probabilities * np.nan):
        try:
            independent_metrics([0, 1, 2], invalid)
        except ValueError:
            continue
        raise ValueError("invalid probability input was accepted")
    print("Independent formula self-tests passed; no experiment files read or written.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", type=Path, default=ROOT / "outputs/critique_comparison_20261027/final")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/critique_comparison_audit_20261027.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    out, final_directory = args.out.resolve(), args.final.resolve()
    require(final_directory not in out.parents and out != final_directory, "audit output must be outside frozen final directory")
    result = verify(final_directory)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Independent comparison audit passed: {result['tested_cases']}; output={out}")


if __name__ == "__main__":
    main()
