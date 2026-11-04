#!/usr/bin/env python3
"""Run the preregistered, bounded S0 development and frozen final experiment.

This module intentionally leaves the original eight-feature pipeline unchanged.
Final generator seeds cannot be requested until a verified freeze.json exists.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.data import CLASS_NAMES, SPLITS, generate_dataset
from fishing_demo.features import feature_matrix as original_feature_matrix
from fishing_demo.iteration_features import feature_matrix, feature_names, feature_units
from fishing_demo.models import Classifier, Preprocessor, classification_metrics, fit_temperature, softmax
from fishing_demo.pipeline import dataset_digest, save_json, split_indices

MODEL_SCHEMA = "fishing_iteration_model_v1"
DEV_SEEDS = tuple(range(1101, 1106))
FINAL_SEEDS = tuple(range(9101, 9111))
INIT_SEEDS = (42, 137)
PROTOCOL_PATH = ROOT / "docs/iterative_model_protocol_20261026.md"
SOURCE_FILES = (
    "fishing_demo/data.py", "fishing_demo/features.py", "fishing_demo/iteration_features.py",
    "fishing_demo/models.py", "fishing_demo/pipeline.py", "tools/run_iterative_models.py",
    "docs/iterative_model_protocol_20261026.md",
)
MLP_SETTINGS = {"hidden": 16, "l2": 0.0, "epochs": 400, "learning_rate": .03, "patience": 35}
TREE_SETTINGS = {"n_estimators": 256, "min_samples_leaf": 2, "max_features": 1.0,
                 "class_weight": None, "n_jobs": 1}
FEATURE_EXCLUDES = ["label", "vessel_id", "sample_id", "split", "scenario", "sim_times", "quality"]
TRAINING_PROCEDURE = {
    "preprocessor_fit_split": "train", "classifier_fit_split": "train",
    "epoch_selection_split": "validation", "epoch_selection_metric": "nll_before_temperature",
    "temperature_fit_split": "calibration", "temperature_grid": "existing_81_point_geometric_0.1_to_10",
    "missing_values": "train_median_then_train_population_standardization_then_missing_mask",
    "validity_rule": "original8_valid_geometry_and_valid_label_for_all_candidates",
    "tree_temperature_logits": "log(clip(predict_proba, float64_tiny, 1))",
    "mlp": MLP_SETTINGS, "extratrees": TREE_SETTINGS,
}


def candidate(name, family, backend="mlp"):
    return {"name": name, "family": family, "backend": backend,
            "settings": copy.deepcopy(MLP_SETTINGS if backend == "mlp" else TREE_SETTINGS)}


BASELINE = candidate("original8_mlp", "original8")
ROUNDS = (
    (candidate("shape7_mlp", "shape7"),),
    (candidate("shape9_mlp", "shape9"), candidate("shape15_mlp", "shape15")),
    (candidate("shape9_extratrees", "shape9", "extratrees"),
     candidate("shape15_extratrees", "shape15", "extratrees")),
)
HYPOTHESES = {
    0: "Original eight-feature tanh16 MLP is the fixed reference procedure.",
    1: "Removing only log total length reduces sensitivity to scale shift.",
    2: "Dimensionless global cloud and within-part resampled turns reduce fragmentation sensitivity.",
    3: "ExtraTrees can exploit the already fixed shape inputs better than the fixed small MLP.",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def source_hashes():
    return {name: sha256(ROOT / name) for name in SOURCE_FILES}


def _canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _positive_temperature(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
        raise ValueError("temperature must be finite and positive")
    return float(value)


def _validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("schema_version") != MODEL_SCHEMA:
        raise ValueError("unsupported iteration model schema")
    if bundle.get("source_type") != "synthetic" or bundle.get("coordinate_system") != "local_xy_m":
        raise ValueError("iteration models require explicitly synthetic local XY metres")
    config = bundle.get("config", {})
    family = config.get("family")
    if bundle.get("feature_names") != list(feature_names(family)):
        raise ValueError("iteration feature order differs from the implementation")
    if bundle.get("feature_units") != list(feature_units(family)):
        raise ValueError("iteration feature units differ from the implementation")
    if bundle.get("class_names") != CLASS_NAMES:
        raise ValueError("class order differs from the implementation")
    _positive_temperature(bundle.get("temperature"))
    preprocessor = Preprocessor.from_dict(bundle.get("preprocessor"))
    expected_dim = 2 * len(feature_names(family))
    if preprocessor.n_features_ * 2 != expected_dim:
        raise ValueError("preprocessor dimensions do not match the feature family")
    if config.get("backend") == "mlp":
        model = Classifier.from_dict(bundle.get("classifier"))
        if model.input_dim != expected_dim or model.n_classes != len(CLASS_NAMES):
            raise ValueError("classifier dimensions differ from the feature contract")
        if model.hidden != 16 or model.l2 != 0 or model.seed != bundle.get("init_seed"):
            raise ValueError("classifier does not match the fixed iteration MLP")
    elif config.get("backend") == "extratrees":
        model = bundle.get("_classifier")
        if model is None:
            raise ValueError("load tree bundles through load_iteration_model with trusted_local=True")
        if model.n_features_in_ != expected_dim or model.classes_.tolist() != [0, 1, 2]:
            raise ValueError("tree dimensions or class order differ from the feature contract")
        actual = model.get_params()
        if any(actual[key] != value for key, value in TREE_SETTINGS.items()) or actual["random_state"] != bundle.get("init_seed"):
            raise ValueError("tree settings differ from the fixed iteration contract")
    else:
        raise ValueError("unsupported iteration model backend")
    return preprocessor, model


def load_iteration_model(path, *, trusted_local=False):
    """Load a frozen model without fitting; tree pickle requires explicit trust.

    ``trusted_local=True`` is only for files generated by this experiment under
    the caller's control. A matching hash detects corruption, not hostile code.
    """
    path = Path(path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != MODEL_SCHEMA:
        raise ValueError("unsupported iteration model schema")
    if bundle.get("config", {}).get("backend") == "extratrees":
        if not trusted_local:
            raise ValueError("tree pickle needs explicit trusted_local=True for self-generated files")
        state = bundle.get("classifier", {})
        expected = path.with_suffix(".pkl")
        if state.get("format") != "trusted_self_generated_pickle" or state.get("file") != expected.name:
            raise ValueError("tree pickle must be the adjacent same-stem generated file")
        if sha256(expected) != state.get("sha256"):
            raise ValueError("tree pickle integrity mismatch")
        import sklearn
        if state.get("sklearn_version") != sklearn.__version__:
            raise ValueError("tree pickle sklearn version differs from the saved runtime")
        with expected.open("rb") as stream:
            bundle["_classifier"] = pickle.load(stream)
    _validate_bundle(bundle)
    return bundle


def _logits(model, backend, Z):
    if backend == "mlp":
        return model.predict_logits(Z)
    probabilities = model.predict_proba(Z)
    return np.log(np.clip(probabilities, np.finfo(np.float64).tiny, 1.0))


def predict_bundle(bundle, records):
    """Return (N x 3 probabilities, original8 geometry-valid mask), without fit.

    Invalid rows have three NaNs. Labels and identifiers never enter features.
    All candidate families share the original eight-feature geometry gate.
    """
    preprocessor, model = _validate_bundle(bundle)
    _, details = original_feature_matrix(records)
    valid = np.asarray([item["valid"] for item in details], dtype=bool)
    values = feature_matrix(records, bundle["config"]["family"])
    probabilities = np.full((len(records), len(CLASS_NAMES)), np.nan)
    if valid.any():
        Z = preprocessor.transform(values[valid])
        probabilities[valid] = softmax(_logits(model, bundle["config"]["backend"], Z), bundle["temperature"])
    return probabilities, valid


class SeedGate:
    """Only this object calls the generator; final seeds require a sealed freeze."""

    def __init__(self, expected_source_hashes, protocol_sha256):
        self.expected_source_hashes = dict(expected_source_hashes)
        self.protocol_sha256 = protocol_sha256
        self.freeze_path = None
        self.freeze_sha256 = None
        self.calls = []
        self.cache = {}

    def unlock_final(self, freeze_path):
        path = Path(freeze_path)
        frozen = json.loads(path.read_text(encoding="utf-8"))
        if frozen.get("schema_version") != "fishing_iteration_freeze_v1":
            raise ValueError("a valid freeze is required before final generation")
        if frozen.get("source_sha256") != self.expected_source_hashes or source_hashes() != self.expected_source_hashes:
            raise ValueError("source changed before final generation")
        if frozen.get("protocol_sha256") != self.protocol_sha256:
            raise ValueError("freeze protocol does not match the pre-run protocol")
        known = [config for configs in ROUNDS for config in configs]
        if frozen.get("selected_config") not in known or frozen.get("training_procedure") != TRAINING_PROCEDURE:
            raise ValueError("freeze does not specify a preregistered candidate and procedure")
        if frozen.get("final_data_seeds") != list(FINAL_SEEDS) or frozen.get("init_seeds") != list(INIT_SEEDS):
            raise ValueError("freeze seed schedule differs from the protocol")
        if frozen.get("model_fixture") != {"data_seed": 9101, "init_seed": 42}:
            raise ValueError("fixture must be the first final seed and first initialization")
        self.freeze_path, self.freeze_sha256 = path, sha256(path)

    def get(self, seed):
        if seed not in DEV_SEEDS and seed not in FINAL_SEEDS:
            raise ValueError("seed is outside the preregistered budget")
        if seed in FINAL_SEEDS:
            if self.freeze_path is None:
                raise ValueError("final data generation is forbidden before freeze")
            if sha256(self.freeze_path) != self.freeze_sha256 or source_hashes() != self.expected_source_hashes:
                raise ValueError("frozen procedure changed before final generation")
        if seed not in self.cache:
            data = generate_dataset(seed=seed)
            _, details = original_feature_matrix(data["records"])
            indices, groups = split_indices(data["records"], details)
            valid = np.asarray([item["valid"] for item in details], dtype=bool)
            split_meta = {}
            for split in SPLITS:
                positions = [i for i, row in enumerate(data["records"]) if row["split"] == split]
                row_ids = [data["records"][int(i)]["sample_id"] for i in indices[split]]
                split_meta[split] = {"total": len(positions), "valid": int(valid[positions].sum()),
                    "abstained": int((~valid[positions]).sum()), "evaluated_labeled": len(indices[split]),
                    "groups": sorted(groups[split]), "evaluation_row_sha256": _canonical_digest(row_ids)}
            self.cache[seed] = {"dataset": data, "indices": indices, "groups": groups,
                "valid": valid, "details": details, "matrices": {}, "metadata": {
                    "data_seed": seed, "dataset_sha256": dataset_digest(data),
                    "generator_sha256": self.expected_source_hashes["fishing_demo/data.py"],
                    "generator_metadata": data["metadata"], "split_metadata": split_meta,
                    "independent_id_key": ["generator_seed", "vessel_id/sample_id"]}}
            self.calls.append({"seed": seed, "phase": "final" if seed in FINAL_SEEDS else "development",
                               "at_utc": utc_now(), "freeze_sha256": self.freeze_sha256})
        return self.cache[seed]


def paired_summary(baseline_records, candidate_records, *, final=False):
    """Average initializations within each seed before paired seed comparison."""
    seeds = FINAL_SEEDS if final else DEV_SEEDS
    required = {(data_seed, init_seed) for data_seed in seeds for init_seed in INIT_SEEDS}

    def index(rows):
        result = {}
        for row in rows:
            key = (row["data_seed"], row["init_seed"])
            if key in result:
                raise ValueError("duplicate data/init pair in aggregation")
            result[key] = row
        if set(result) != required:
            raise ValueError("aggregation requires every preregistered data/init pair exactly once")
        return result

    baseline, changed = index(baseline_records), index(candidate_records)
    denominator_equal = True
    per_seed = []
    for data_seed in seeds:
        result = {"data_seed": data_seed}
        for split in ("normal", "shift"):
            before, after = [], []
            for init_seed in INIT_SEEDS:
                a = baseline[(data_seed, init_seed)]["metrics"][split]
                b = changed[(data_seed, init_seed)]["metrics"][split]
                for field in ("total", "valid", "abstained", "evaluated_labeled", "support", "evaluation_row_sha256"):
                    if a[field] != b[field]:
                        denominator_equal = False
                before.append(a["macro_f1"])
                after.append(b["macro_f1"])
            result[split] = {"baseline_macro_f1": float(np.mean(before)),
                "candidate_macro_f1": float(np.mean(after)), "delta": float(np.mean(after) - np.mean(before))}
        per_seed.append(result)
    normal_delta = float(np.mean([row["normal"]["delta"] for row in per_seed]))
    shifts = np.asarray([row["shift"]["delta"] for row in per_seed])
    shift_delta = float(shifts.mean())
    positive = int((shifts > 0).sum())
    conditions = {"normal_delta_at_least_minus_0_01": normal_delta >= -.01,
        "shift_delta_at_least_0_05": shift_delta >= .05,
        "positive_shift_seed_count": positive >= (8 if final else 4),
        "same_denominators": denominator_equal}
    result = {"aggregation_unit": "generator_seed_after_mean_of_two_initializations",
        "per_seed": per_seed, "normal_mean_delta": normal_delta, "shift_mean_delta": shift_delta,
        "positive_shift_seeds": positive, "seed_count": len(seeds), "conditions": conditions}
    if final:
        rng = np.random.default_rng(20261026)
        samples = rng.choice(shifts, size=(2000, len(shifts)), replace=True).mean(axis=1)
        low, high = np.quantile(samples, [.025, .975])
        result["shift_paired_bootstrap95"] = {"low": float(low), "high": float(high),
            "method": "generator_seed_paired_percentile_bootstrap", "repetitions": 2000, "seed": 20261026}
        conditions["shift_bootstrap_lower_above_zero"] = bool(low > 0)
    result["eligible" if not final else "success"] = bool(all(conditions.values()))
    return result


def _fit_one(prepared, config, data_seed, init_seed, out, expected_sources, phase):
    records = prepared["dataset"]["records"]
    indices = prepared["indices"]
    matrices = prepared["matrices"]
    family = config["family"]
    if family not in matrices:
        matrices[family] = feature_matrix(records, family)
    X = matrices[family]
    y = np.asarray([row["label"] if row.get("label") is not None else -1 for row in records], dtype=int)
    preprocessor = Preprocessor().fit(X[indices["train"]])
    Z = {split: preprocessor.transform(X[ix]) for split, ix in indices.items()}
    if config["backend"] == "mlp":
        model = Classifier(Z["train"].shape[1], len(CLASS_NAMES), hidden=16, l2=0, seed=init_seed)
        model.fit(Z["train"], y[indices["train"]], Z["validation"], y[indices["validation"]],
                  epochs=400, learning_rate=.03, patience=35)
        classifier_state = model.to_dict()
    else:
        from sklearn.ensemble import ExtraTreesClassifier
        model = ExtraTreesClassifier(**TREE_SETTINGS, random_state=init_seed)
        model.fit(Z["train"], y[indices["train"]])
        classifier_state = None
    calibration_logits = _logits(model, config["backend"], Z["calibration"])
    temperature = float(fit_temperature(calibration_logits, y[indices["calibration"]]))
    prefix = f"{config['name']}_d{data_seed}_i{init_seed}"
    model_path = out / "models" / f"{prefix}.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if classifier_state is None:
        tree_path = model_path.with_suffix(".pkl")
        with tree_path.open("wb") as stream:
            pickle.dump(model, stream, protocol=pickle.HIGHEST_PROTOCOL)
        classifier_state = {"format": "trusted_self_generated_pickle", "file": tree_path.name,
            "sha256": sha256(tree_path), "trust_requirement": "only load self-generated local artifacts",
            "sklearn_version": __import__("sklearn").__version__}
    bundle = {"schema_version": MODEL_SCHEMA, "source_type": "synthetic", "coordinate_system": "local_xy_m",
        "class_names": CLASS_NAMES, "config": copy.deepcopy(config), "phase": phase,
        "data_seed": data_seed, "init_seed": init_seed, "dataset_sha256": prepared["metadata"]["dataset_sha256"],
        "feature_names": list(feature_names(family)), "feature_units": list(feature_units(family)),
        "feature_excludes": FEATURE_EXCLUDES, "preprocessor": preprocessor.to_dict(),
        "classifier": classifier_state, "temperature": temperature, "training_procedure": TRAINING_PROCEDURE,
        "fit_groups": sorted(prepared["groups"]["train"]),
        "selection_groups": sorted(prepared["groups"]["validation"]),
        "calibration_groups": sorted(prepared["groups"]["calibration"]), "source_sha256": expected_sources}
    save_json(model_path, bundle)
    if config["backend"] == "extratrees":
        bundle["_classifier"] = model
    # Compute each held-out metric once. Reload inference checks do not fit or select.
    metrics, predictions = {}, []
    eval_records = [row for row in records if row["split"] in ("test", "stress")]
    probabilities, valid = predict_bundle(bundle, eval_records)
    reloaded = load_iteration_model(model_path, trusted_local=True)
    restored_probabilities, restored_valid = predict_bundle(reloaded, eval_records)
    if not np.array_equal(valid, restored_valid) or not np.array_equal(probabilities, restored_probabilities, equal_nan=True):
        raise RuntimeError("saved model predictions do not reproduce in-memory inference exactly")
    restored_preprocessor, restored_model = _validate_bundle(reloaded)
    eval_positions = [i for i, row in enumerate(records) if row["split"] in ("test", "stress")]
    eval_X = X[eval_positions][valid]
    before_Z = preprocessor.transform(eval_X)
    restored_Z = restored_preprocessor.transform(eval_X)
    if config["backend"] == "extratrees":
        raw_probabilities = model.predict_proba(before_Z)
        restored_raw = restored_model.predict_proba(restored_Z)
    else:
        raw_probabilities = softmax(model.predict_logits(before_Z))
        restored_raw = softmax(restored_model.predict_logits(restored_Z))
    if not np.array_equal(raw_probabilities, restored_raw):
        raise RuntimeError("saved model raw probabilities differ from in-memory inference")
    for split, role in (("test", "normal"), ("stress", "shift")):
        positions = np.asarray([i for i, row in enumerate(eval_records) if row["split"] == split])
        labeled = np.asarray([isinstance(eval_records[i].get("label"), int)
            and not isinstance(eval_records[i].get("label"), bool) and 0 <= eval_records[i]["label"] < 3
            for i in positions], dtype=bool)
        chosen = positions[valid[positions] & labeled]
        metric = classification_metrics([eval_records[i]["label"] for i in chosen], probabilities[chosen])
        meta = prepared["metadata"]["split_metadata"][split]
        metric.update({key: meta[key] for key in ("total", "valid", "abstained", "evaluated_labeled", "evaluation_row_sha256")})
        metric["evaluation_role"] = f"{phase}_{role}"
        metrics[role] = metric
    for row, probs, usable in zip(eval_records, probabilities, valid):
        predictions.append({"generator_seed": data_seed, "init_seed": init_seed, "sample_id": row["sample_id"],
            "vessel_id": row["vessel_id"], "split": row["split"],
            "evaluation_role": f"{phase}_{'normal' if row['split'] == 'test' else 'shift'}",
            "true_label": row.get("label"), "predicted_label": int(probs.argmax()) if usable else None,
            "probabilities": probs.tolist() if usable else None, "status": "ok" if usable else "abstained",
            "source_type": "synthetic"})
    prediction_path = out / "predictions" / f"{prefix}.json"
    save_json(prediction_path, predictions)
    validation_logits = _logits(model, config["backend"], Z["validation"])
    result = {"data_seed": data_seed, "init_seed": init_seed, "candidate": config["name"], "phase": phase,
        "metrics": metrics, "temperature": temperature,
        "best_epoch": model.best_epoch if config["backend"] == "mlp" else None,
        "epochs_run": len(model.history) if config["backend"] == "mlp" else None,
        "validation_before_calibration": classification_metrics(y[indices["validation"]], softmax(validation_logits)),
        "model_path": model_path.relative_to(out).as_posix(), "model_sha256": sha256(model_path),
        "predictions_path": prediction_path.relative_to(out).as_posix(), "predictions_sha256": sha256(prediction_path),
        "reload_predictions_identical": True, "reload_raw_probabilities_identical": True,
        "dataset_sha256": prepared["metadata"]["dataset_sha256"]}
    print(f"{phase} {prefix}: normal F1={metrics['normal']['macro_f1']:.4f}, shift F1={metrics['shift']['macro_f1']:.4f}", flush=True)
    return result


def _run_config(config, seeds, gate, out, sources, phase):
    return [_fit_one(gate.get(data_seed), config, data_seed, init_seed, out, sources, phase)
            for data_seed in seeds for init_seed in INIT_SEEDS]


def _prepare_output(output_dir):
    out = Path(output_dir).resolve()
    allowed = (ROOT / "outputs").resolve()
    if allowed not in out.parents:
        raise ValueError("use a new child directory under the project's outputs directory")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("output directory must be empty; earlier evidence is preserved")
    out.mkdir(parents=True, exist_ok=True)
    return out


def run(output_dir):
    started = time.perf_counter()
    out = _prepare_output(output_dir)
    sources = source_hashes()
    protocol = {"schema_version": "fishing_iteration_protocol_v1", "source_type": "synthetic",
        "started_at_utc": utc_now(), "protocol_sha256": sha256(PROTOCOL_PATH),
        "source_sha256_before_run": sources, "development_data_seeds": list(DEV_SEEDS),
        "final_data_seeds": list(FINAL_SEEDS), "init_seeds": list(INIT_SEEDS),
        "baseline": BASELINE, "candidate_rounds": ROUNDS, "training_procedure": TRAINING_PROCEDURE,
        "development_evaluation_roles": {"test": "development_normal", "stress": "development_shift"},
        "final_evaluation_roles": {"test": "final_normal", "stress": "final_shift"},
        "selection_order": "first eligible candidate in preregistered round and listed order",
        "development_criteria": {"normal_mean_delta_min": -.01, "shift_mean_delta_min": .05,
            "positive_shift_seed_min": 4, "same_denominators": True},
        "final_criteria": {"normal_mean_delta_min": -.01, "shift_mean_delta_min": .05,
            "positive_shift_seed_min": 8, "same_denominators": True,
            "shift_paired_bootstrap_lower_strictly_above": 0, "bootstrap_repetitions": 2000, "bootstrap_seed": 20261026},
        "model_fixture": {"data_seed": 9101, "init_seed": 42},
        "independent_id_key": ["generator_seed", "vessel_id/sample_id"],
        "final_seed_generation_before_freeze": False, "final_failure_research": False,
        "learner_understanding": "not_assessed"}
    save_json(out / "protocol.json", protocol)
    (out / "protocol.md").write_bytes(PROTOCOL_PATH.read_bytes())
    for name in SOURCE_FILES:
        target = out / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    print("Protocol and source snapshot written before any data generation or model fitting.", flush=True)
    gate = SeedGate(sources, protocol["protocol_sha256"])
    results = {"schema_version": "fishing_iteration_results_v1", "source_type": "synthetic", "protocol": protocol,
        "stage_results": [], "selected_candidate": None, "freeze": None,
        "final": {"executed": False, "baseline_records": [], "candidate_records": [], "summary": None, "success": False},
        "checks": {}, "limitations": [
            "S0 synthetic path-family experiment; no official fishing labels or real-data performance.",
            "All seeds share one generator; generator bias and real-world generalization are not tested.",
            "Shift preserves generating labels; this is not accident detection or an accident probability.",
            "Normal mean-delta threshold is a design criterion, not statistical noninferiority proof.",
            "No hardware experiment, external acquisition, actual-data evaluation or learner attainment assessment."]}
    baseline_records = _run_config(BASELINE, DEV_SEEDS, gate, out, sources, "development")
    results["stage_results"].append({"candidate": BASELINE, "round": 0, "hypothesis": HYPOTHESES[0],
        "change": "fixed original eight-feature reference", "records": baseline_records,
        "summary": {"role": "fixed_baseline"}, "decision": "reference"})
    save_json(out / "results.json", results)
    selected = None
    for round_number, configs in enumerate(ROUNDS, start=1):
        eligible = []
        for config in configs:
            records = _run_config(config, DEV_SEEDS, gate, out, sources, "development")
            summary = paired_summary(baseline_records, records)
            print(f"Round {round_number} {config['name']}: mean normal delta={summary['normal_mean_delta']:+.6f}, "
                  f"mean shift delta={summary['shift_mean_delta']:+.6f}, "
                  f"positive shift seeds={summary['positive_shift_seeds']}/5, eligible={summary['eligible']}", flush=True)
            entry = {"candidate": config, "round": round_number, "hypothesis": HYPOTHESES[round_number],
                "change": {"feature_family": config["family"], "backend": config["backend"]},
                "records": records, "summary": summary,
                "decision": "eligible" if summary["eligible"] else "rejected_by_preregistered_criteria"}
            results["stage_results"].append(entry)
            if summary["eligible"]:
                eligible.append(config)
            save_json(out / "results.json", results)
        if eligible:
            selected = eligible[0]
            break
    if selected is not None:
        if source_hashes() != sources:
            raise RuntimeError("source changed during development; refusing final generation")
        frozen = {"schema_version": "fishing_iteration_freeze_v1", "frozen_at_utc": utc_now(),
            "selected_config": selected, "baseline_config": BASELINE, "training_procedure": TRAINING_PROCEDURE,
            "source_sha256": sources, "protocol_sha256": protocol["protocol_sha256"],
            "final_data_seeds": list(FINAL_SEEDS), "init_seeds": list(INIT_SEEDS),
            "model_fixture": {"data_seed": 9101, "init_seed": 42},
            "selection_rule": protocol["selection_order"], "final_failure_research": False}
        save_json(out / "freeze.json", frozen)
        results["selected_candidate"] = selected
        results["freeze"] = {**frozen, "path": "freeze.json", "sha256": sha256(out / "freeze.json")}
        save_json(out / "results.json", results)
        gate.unlock_final(out / "freeze.json")
        print(f"Frozen candidate {selected['name']}; first final data generation is now permitted.", flush=True)
        final_baseline = _run_config(BASELINE, FINAL_SEEDS, gate, out, sources, "final")
        final_candidate = _run_config(selected, FINAL_SEEDS, gate, out, sources, "final")
        summary = paired_summary(final_baseline, final_candidate, final=True)
        print(f"Final {selected['name']}: mean normal delta={summary['normal_mean_delta']:+.6f}, "
              f"mean shift delta={summary['shift_mean_delta']:+.6f}, "
              f"positive shift seeds={summary['positive_shift_seeds']}/10, "
              f"bootstrap95={summary['shift_paired_bootstrap95']}, success={summary['success']}", flush=True)
        results["final"] = {"executed": True, "baseline_records": final_baseline,
            "candidate_records": final_candidate, "summary": summary, "success": summary["success"]}
        results["outcome"] = "synthetic_improvement_confirmed" if summary["success"] else "final_improvement_not_confirmed"
    else:
        results["outcome"] = "no_development_candidate_eligible"
    results["dataset_manifest"] = {str(seed): item["metadata"] for seed, item in sorted(gate.cache.items())}
    results["generation_events"] = gate.calls
    source_unchanged = source_hashes() == sources
    all_runs = [row for stage in results["stage_results"] for row in stage["records"]]
    all_runs += results["final"]["baseline_records"] + results["final"]["candidate_records"]
    results["checks"] = {"protocol_written_before_generation": True, "sources_unchanged": source_unchanged,
        "all_saved_model_predictions_identical": all(row["reload_predictions_identical"] for row in all_runs),
        "final_generated_only_after_freeze": all(event["freeze_sha256"] for event in gate.calls if event["phase"] == "final"),
        "no_final_generation_without_development_eligibility": selected is not None or not any(event["phase"] == "final" for event in gate.calls),
        "same_development_denominators": all(stage["summary"]["conditions"]["same_denominators"] for stage in results["stage_results"][1:]),
        "snapshot_hashes_match": all(sha256(out / "source_snapshot" / name) == digest for name, digest in sources.items()),
        "no_real_data_or_hardware_evaluation": True}
    if not all(results["checks"].values()):
        save_json(out / "results.json", results)
        raise RuntimeError(f"iteration audit failed: {results['checks']}")
    results["runtime"] = {"seconds": round(time.perf_counter() - started, 3), "python": platform.python_version(),
        "python_executable": sys.executable, "numpy": np.__version__, "finished_at_utc": utc_now()}
    save_json(out / "results.json", results)
    save_json(out / "run_evidence.json", {"command": f"python tools/run_iterative_models.py --out {out.relative_to(ROOT).as_posix()}",
        "started_at_utc": protocol["started_at_utc"], "finished_at_utc": utc_now(), "checks": results["checks"],
        "runtime": results["runtime"], "outcome": results["outcome"],
        "artifact_sha256": {p.relative_to(out).as_posix(): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print(f"Outcome: {results['outcome']}; outputs: {out}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/iterative_models_20261026")
    args = parser.parse_args()
    try:
        run(args.out)
    except (ValueError, RuntimeError, OSError, ImportError) as exc:
        parser.exit(2, f"Iterative model experiment failed: {exc}\n")


if __name__ == "__main__":
    main()
