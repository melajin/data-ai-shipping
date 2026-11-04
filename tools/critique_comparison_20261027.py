#!/usr/bin/env python3
"""Prespecified S0 shape9 model comparison, using fresh development seeds only.

This research runner leaves the sample system's 400-epoch limit unchanged.
It cannot generate final data. Final evaluation needs a separate sealed protocol.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import pickle
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.data import CLASS_NAMES, SPLITS, generate_dataset, validate_dataset
from fishing_demo.features import feature_matrix as original_feature_matrix
from fishing_demo.iteration_features import feature_matrix as geometry_matrix
from fishing_demo.iteration_features import feature_names as geometry_names, feature_units as geometry_units
from fishing_demo import synthetic_temporal_features as temporal_features
from fishing_demo.models import (
    Classifier, Preprocessor, _integer, _matrix, _nll_from_logits, _number,
    _valid_labels, classification_metrics, fit_temperature, softmax,
)
from fishing_demo.pipeline import dataset_digest, save_json, split_indices

DEV_SEEDS = (2101, 2102, 2103)
INIT_SEEDS = (42, 137)
RETIRED_FINAL_SEEDS = tuple(range(9101, 9111))
RESERVED_FINAL_SEEDS = tuple(range(12101, 12111))
FEATURE_FAMILY = "shape9"
MAX_RESEARCH_EPOCHS = 1200
TIE_TOLERANCE = 1e-12
MODEL_SCHEMA = "fishing_critique_comparison_model_v1"
TREE_SETTINGS = {"n_estimators": 256, "min_samples_leaf": 2, "max_features": 1.0,
                 "class_weight": None, "n_jobs": 1}
SOURCE_FILES = (
    "fishing_demo/data.py", "fishing_demo/features.py", "fishing_demo/iteration_features.py",
    "fishing_demo/models.py", "fishing_demo/pipeline.py",
    "tools/critique_comparison_20261027.py", "tests/test_critique_comparison.py",
    "tools/critique_final_comparison_20261027.py", "tests/test_critique_final_comparison.py",
    "fishing_demo/synthetic_temporal_features.py", "tests/test_synthetic_temporal_features.py",
    "docs/iterative_model_protocol_20261026.md", "docs/shape9_critique_comparison_protocol_20261027.md",
)


def feature_names(family):
    return geometry_names(family) if family == FEATURE_FAMILY else temporal_features.feature_names(family)


def feature_units(family):
    return geometry_units(family) if family == FEATURE_FAMILY else temporal_features.feature_units(family)


def comparison_feature_matrix(dataset, family):
    return geometry_matrix(dataset["records"], family) if family == FEATURE_FAMILY else temporal_features.feature_matrix(dataset, family)


def neural_config(name, *, hidden=16, epochs=1200, l2=0.0, family=FEATURE_FAMILY, formal_selection=True):
    return {"name": name, "family": family, "backend": "numpy_softmax", "formal_selection": formal_selection,
            "settings": {"hidden": hidden, "l2": l2, "epochs": epochs,
                         "learning_rate": .03, "patience": 35}}


BASELINE = neural_config("shape9_mlp_e400_l2_0", epochs=400)
CANDIDATES = (
    neural_config("shape9_mlp_e1200_l2_0"),
    neural_config("shape9_mlp_e1200_l2_0_001", l2=.001),
    neural_config("shape9_mlp_e1200_l2_0_01", l2=.01),
    neural_config("shape9_linear_e1200_l2_0_01", hidden=0, l2=.01),
    {"name": "shape9_extratrees", "family": FEATURE_FAMILY,
     "backend": "extratrees", "formal_selection": True, "settings": copy.deepcopy(TREE_SETTINGS)},
    neural_config("shape9_simtime4_mlp_e400_l2_0", epochs=400, family="shape9_simtime4"),
    neural_config("shape9_edge3_mlp_e400_l2_0", epochs=400, family="shape9_edge3"),
    neural_config("shape9_dt_only_mlp_e400_l2_0", epochs=400, family="shape9_dt_only", formal_selection=False),
)
TRAINING_PROCEDURE = {
    "preprocessor_fit_split": "train", "classifier_gradient_or_tree_fit_split": "train",
    "epoch_selection_split": "validation", "epoch_selection_metric": "nll_before_temperature",
    "epoch_semantics": "one_full_batch_gradient_update_then_train_and_validation_loss",
    "checkpoint": "strict_validation_nll_improvement_restore_best_patience_35",
    "temperature_fit_split": "calibration", "temperature_grid": "81_geometric_0.1_to_10_including_1",
    "tree_temperature_logits": "log(clip(predict_proba,float64_tiny,1));not_tree_training_logits",
    "preprocessing": "train_median_then_train_population_scaling_then_missing_mask",
    "feature_families": {family: {"features": list(feature_names(family)),
        "feature_units": list(feature_units(family)), "input_dimension": 2 * len(feature_names(family)),
        "raw_feature_dimension": len(feature_names(family)), "simtime_source": family in ("shape9_simtime4", "shape9_dt_only")}
        for family in (FEATURE_FAMILY, "shape9_simtime4", "shape9_edge3", "shape9_dt_only")},
    "validity_rule": "original8_geometry_valid_and_valid_label_same_rows_for_every_candidate",
    "history": "every_post_update_epoch_train_nll_val_nll_train_objective_no_eval_split_curves",
}
SELECTION_PROCEDURE = {
    "aggregation": "mean_two_initializations_within_generator_seed_then_mean_three_seeds",
    "normal_macro_f1_delta_min": -.01, "shift_macro_f1_delta_min": .05,
    "positive_shift_seed_min": 3, "same_denominators": True, "finite_metrics": True,
    "eligible_priority": ["shift_mean_delta_desc", "normal_mean_delta_desc",
                          "normal_calibrated_nll_asc", "normal_calibrated_brier_asc", "declaration_order"],
    "priority_tie_tolerance": TIE_TOLERANCE, "runtime_used_for_selection": False,
    "excluded_formal_selection_families": ["shape9_dt_only"],
}
DENOMINATOR_FIELDS = ("total", "valid", "abstained", "evaluated_labeled", "support", "evaluation_row_sha256")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def source_hashes():
    return {name: sha256(ROOT / name) for name in SOURCE_FILES}


def fit_research_classifier(model, X, y, X_val, y_val, *, epochs=1200, learning_rate=.03, patience=35):
    """Exact sample-model GD semantics, with a separate research-only 1200 cap.

    Reuses the original validation, loss and gradient functions. At 400 epochs
    this must match ``Classifier.fit`` bit for bit. No test/calibration inputs
    are accepted, and errors restore the original parameters.
    """
    if not isinstance(model, Classifier):
        raise ValueError("research fitting requires the existing NumPy Classifier")
    values = _matrix(X, n_features=model.input_dim, allow_empty=False)
    validation = _matrix(X_val, "X_val", model.input_dim, allow_empty=False)
    train_mask, train_labels = _valid_labels(y, values.shape[0], model.n_classes)
    val_mask, val_labels = _valid_labels(y_val, validation.shape[0], model.n_classes)
    values, validation = values[train_mask], validation[val_mask]
    epochs = _integer(epochs, "epochs", 1)
    if epochs > MAX_RESEARCH_EPOCHS:
        raise ValueError("research epochs must not exceed 1200")
    learning_rate = _number(learning_rate, "learning_rate", positive=True)
    patience = _integer(patience, "patience", 1)
    original = {key: value.copy() for key, value in model.params.items()}
    best_parameters, best_nll, best_epoch = None, math.inf, None
    stale, history = 0, []
    try:
        for epoch in range(1, epochs + 1):
            _, gradients = model.loss_and_gradients(values, train_labels)
            with np.errstate(over="ignore", invalid="ignore"):
                updated = {key: value - learning_rate * gradients[key]
                           for key, value in model.params.items()}
            if any(not np.isfinite(value).all() for value in updated.values()):
                raise ValueError("parameter update overflowed")
            model.params = updated
            train_nll = _nll_from_logits(model.predict_logits(values), train_labels)
            val_nll = _nll_from_logits(model.predict_logits(validation), val_labels)
            objective = _number(train_nll + model._regularization(), "train_objective")
            history.append({"epoch": epoch, "train_nll": train_nll,
                            "val_nll": val_nll, "train_objective": objective})
            if val_nll < best_nll:
                best_nll, best_epoch = val_nll, epoch
                best_parameters = {key: value.copy() for key, value in model.params.items()}
                stale = 0
            else:
                stale += 1
            if stale >= patience:
                break
    except (ValueError, FloatingPointError):
        model.params = original
        raise
    model.params = best_parameters
    model.best_epoch = best_epoch
    model.history = [dict(row) for row in history]
    return history


def research_classifier_from_dict(state):
    """Validate extended history without changing the original state contract."""
    if not isinstance(state, dict):
        raise ValueError("research classifier state must be an object")
    base_state = copy.deepcopy(state)
    history, best_epoch = base_state.get("history"), base_state.get("best_epoch")
    base_state.update(history=[], best_epoch=None)
    model = Classifier.from_dict(base_state)
    if not isinstance(history, list) or not history or len(history) > MAX_RESEARCH_EPOCHS:
        raise ValueError("research history must contain 1 to 1200 epochs")
    checked = []
    for index, row in enumerate(history, start=1):
        if not isinstance(row, dict) or set(row) != {"epoch", "train_nll", "val_nll", "train_objective"}:
            raise ValueError("invalid research history row")
        if _integer(row["epoch"], "history epoch", 1) != index:
            raise ValueError("research history epochs must be consecutive")
        item = {"epoch": index}
        item.update({key: _number(row[key], key, minimum=0)
                     for key in ("train_nll", "val_nll", "train_objective")})
        if item["train_objective"] + 1e-12 < item["train_nll"]:
            raise ValueError("research objective must include train NLL")
        checked.append(item)
    best_epoch = _integer(best_epoch, "best_epoch", 1)
    if best_epoch != min(checked, key=lambda item: item["val_nll"])["epoch"]:
        raise ValueError("research checkpoint must select minimum validation NLL")
    model.best_epoch, model.history = best_epoch, checked
    return model


def _logits(model, backend, Z):
    if backend == "numpy_softmax":
        return model.predict_logits(Z)
    if model.classes_.tolist() != [0, 1, 2]:
        raise ValueError("tree class order must be [0,1,2]")
    return np.log(np.clip(model.predict_proba(Z), np.finfo(np.float64).tiny, 1.0))


def _validate_bundle(bundle):
    if (not isinstance(bundle, dict) or bundle.get("schema_version") != MODEL_SCHEMA
            or bundle.get("source_type") != "synthetic" or bundle.get("coordinate_system") != "local_xy_m"):
        raise ValueError("expected a synthetic critique-comparison model bundle")
    config = bundle.get("config")
    if config not in (BASELINE, *CANDIDATES):
        raise ValueError("model config must match a prespecified comparison model")
    family = config["family"]
    if (bundle.get("feature_names") != list(feature_names(family))
            or bundle.get("feature_units") != list(feature_units(family))
            or bundle.get("class_names") != CLASS_NAMES):
        raise ValueError("feature order, units or class order differ from contract")
    _number(bundle.get("temperature"), "temperature", positive=True)
    preprocessor = Preprocessor.from_dict(bundle.get("preprocessor"))
    if preprocessor.n_features_ != len(feature_names(family)):
        raise ValueError("comparison preprocessing dimension differs from its feature family")
    if config["backend"] == "numpy_softmax":
        model = research_classifier_from_dict(bundle.get("classifier"))
        settings = config["settings"]
        if (model.input_dim != 2 * len(feature_names(family)) or model.n_classes != 3 or model.hidden != settings["hidden"]
                or model.l2 != settings["l2"] or model.seed != bundle.get("init_seed")
                or len(model.history) > settings["epochs"]):
            raise ValueError("research classifier differs from its fixed config")
    else:
        model = bundle.get("_classifier")
        if model is None:
            raise ValueError("tree bundle needs load_bundle(...,trusted_local=True)")
        if model.n_features_in_ != 18 or model.classes_.tolist() != [0, 1, 2]:
            raise ValueError("tree input or class order differs from contract")
        params = model.get_params()
        if any(params[key] != value for key, value in TREE_SETTINGS.items()) or params["random_state"] != bundle.get("init_seed"):
            raise ValueError("tree parameters differ from comparison contract")
    return preprocessor, model


def load_bundle(path, *, trusted_local=False):
    """Load own local artifacts; there is deliberately no external-pickle CLI."""
    path = Path(path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict) or bundle.get("schema_version") != MODEL_SCHEMA:
        raise ValueError("unsupported comparison model schema")
    if bundle.get("config", {}).get("backend") == "extratrees":
        if not trusted_local:
            raise ValueError("self-generated tree pickle requires trusted_local=True")
        state, tree_path = bundle.get("classifier", {}), path.with_suffix(".pkl")
        if state.get("format") != "trusted_self_generated_pickle" or state.get("file") != tree_path.name:
            raise ValueError("tree pickle must be the adjacent same-stem generated file")
        if sha256(tree_path) != state.get("sha256"):
            raise ValueError("tree pickle integrity mismatch")
        import sklearn
        if state.get("sklearn_version") != sklearn.__version__:
            raise ValueError("tree pickle runtime differs from the saved sklearn version")
        with tree_path.open("rb") as stream:
            bundle["_classifier"] = pickle.load(stream)
    _validate_bundle(bundle)
    return bundle


def predict_bundle(bundle, dataset, *, calibrated=True):
    """S0 inference preserves invalid geometry; timing is used only by its family."""
    validate_dataset(dataset)
    records = dataset["records"]
    preprocessor, model = _validate_bundle(bundle)
    _, details = original_feature_matrix(records)
    valid = np.asarray([item["valid"] for item in details], dtype=bool)
    X = comparison_feature_matrix(dataset, bundle["config"]["family"])
    probabilities = np.full((len(records), 3), np.nan)
    if valid.any():
        Z = preprocessor.transform(X[valid])
        probabilities[valid] = softmax(_logits(model, bundle["config"]["backend"], Z),
                                     bundle["temperature"] if calibrated else 1.0)
    return probabilities, valid


def prepare_dataset(dataset, data_seed):
    validate_dataset(dataset)
    records = dataset["records"]
    _, details = original_feature_matrix(records)
    indices, groups = split_indices(records, details)
    y = np.asarray([row["label"] if row.get("label") is not None else -1 for row in records], dtype=int)
    valid = np.asarray([item["valid"] for item in details], dtype=bool)
    metadata = {}
    for split in SPLITS:
        positions = [i for i, row in enumerate(records) if row["split"] == split]
        metadata[split] = {
            "total": len(positions), "valid": int(valid[positions].sum()),
            "abstained": int((~valid[positions]).sum()), "evaluated_labeled": len(indices[split]),
            "evaluation_row_sha256": digest([[data_seed, records[int(i)]["sample_id"]] for i in indices[split]]),
            "groups": sorted(groups[split]),
        }
    return {"dataset": dataset, "y": y, "indices": indices, "groups": groups,
            "valid": valid, "family_cache": {}, "metadata": {
                "data_seed": data_seed, "dataset_sha256": dataset_digest(dataset),
                "generator_metadata": dataset["metadata"], "split_metadata": metadata,
                "family_preprocessor_sha256": {},
                "independent_id_key": ["generator_seed", "vessel_id/sample_id"]}}


def prepare_family(prepared, family):
    """Cache one literal train-only preprocessing fit for each feature family."""
    cache = prepared["family_cache"]
    if family not in cache:
        X = comparison_feature_matrix(prepared["dataset"], family)
        preprocessor = Preprocessor().fit(X[prepared["indices"]["train"]])
        Z = {split: preprocessor.transform(X[ix]) for split, ix in prepared["indices"].items()}
        cache[family] = {"X": X, "preprocessor": preprocessor, "Z": Z}
        prepared["metadata"]["family_preprocessor_sha256"][family] = digest(preprocessor.to_dict())
    return cache[family]


class DevelopmentSeedGate:
    """Only the sealed three-seed development schedule may reach the generator."""

    def __init__(self, protocol_path, expected_sources):
        self.protocol_path = Path(protocol_path)
        self.protocol_sha256 = sha256(protocol_path)
        self.expected_sources = dict(expected_sources)
        self.cache, self.calls = {}, []
        self._verify()

    def _verify(self):
        if sha256(self.protocol_path) != self.protocol_sha256 or source_hashes() != self.expected_sources:
            raise ValueError("sealed protocol or source changed before development generation/fitting")
        protocol = json.loads(self.protocol_path.read_text(encoding="utf-8"))
        if protocol != protocol_payload(self.expected_sources, started_at=protocol.get("started_at_utc")):
            raise ValueError("protocol differs from the prespecified development contract")

    def get(self, seed):
        seed = _integer(seed, "generator seed")
        if seed not in DEV_SEEDS:
            raise ValueError("only prespecified development seeds are allowed; final generation is unavailable")
        self._verify()
        if seed not in self.cache:
            self.cache[seed] = prepare_dataset(generate_dataset(seed=seed), seed)
            self.calls.append({"seed": seed, "phase": "development", "at_utc": utc_now(),
                               "protocol_sha256": self.protocol_sha256})
        return self.cache[seed]


def summarize_candidate(baseline_records, candidate_records, *, seeds=DEV_SEEDS, init_seeds=INIT_SEEDS, positive_seed_min=3):
    seeds, init_seeds = tuple(seeds), tuple(init_seeds)
    required = {(seed, init) for seed in seeds for init in init_seeds}
    if not seeds or not init_seeds or len(required) != len(seeds) * len(init_seeds):
        raise ValueError("aggregation seed schedules must be nonempty and unique")

    def index(rows):
        result = {}
        for row in rows:
            key = (row["data_seed"], row["init_seed"])
            if key in result:
                raise ValueError("duplicate generator/init pair")
            for split in ("normal", "shift"):
                for field in ("accuracy", "macro_f1", "nll", "brier"):
                    _number(row["metrics"][split][field], field, minimum=0)
            result[key] = row
        if set(result) != required:
            raise ValueError("summary requires every prespecified generator/init pair exactly once")
        return result

    baseline, changed = index(baseline_records), index(candidate_records)
    per_seed, same_denominators = [], True
    for seed in seeds:
        item = {"data_seed": seed}
        for split in ("normal", "shift"):
            before, after = [], []
            for init in init_seeds:
                left = baseline[(seed, init)]["metrics"][split]
                right = changed[(seed, init)]["metrics"][split]
                same_denominators &= all(left[field] == right[field] for field in DENOMINATOR_FIELDS)
                before.append(left["macro_f1"])
                after.append(right["macro_f1"])
            item[split] = {"baseline_macro_f1": float(np.mean(before)),
                           "candidate_macro_f1": float(np.mean(after)),
                           "delta": float(np.mean(after) - np.mean(before))}
        per_seed.append(item)
    normal_delta = float(np.mean([item["normal"]["delta"] for item in per_seed]))
    shift_delta = float(np.mean([item["shift"]["delta"] for item in per_seed]))
    positive = sum(item["shift"]["delta"] > 0 for item in per_seed)
    means = {split: {field: float(np.mean([changed[(seed, init)]["metrics"][split][field]
               for seed in seeds for init in init_seeds]))
             for field in ("accuracy", "macro_f1", "nll", "brier")}
             for split in ("normal", "shift")}
    conditions = {"normal_delta_at_least_minus_0_01": normal_delta >= -.01,
                  "shift_delta_at_least_0_05": shift_delta >= .05,
                  "positive_shift_seed_min": positive >= positive_seed_min,
                  "same_denominators": bool(same_denominators), "finite_metrics": True}
    return {"per_seed": per_seed, "normal_mean_delta": normal_delta, "shift_mean_delta": shift_delta,
            "positive_shift_seeds": int(positive), "seed_count": len(seeds), "mean_metrics": means,
            "conditions": conditions, "eligible": all(conditions.values())}


def select_candidate(stages):
    """Use declared metric priorities; elapsed time never enters this decision."""
    best = None
    seen = set()
    for stage in stages:
        name = stage["candidate"]["name"]
        if name in seen:
            raise ValueError("duplicate candidate in selection")
        seen.add(name)
        if not stage["candidate"].get("formal_selection", True):
            continue
        summary = stage["summary"]
        if not summary["eligible"]:
            continue
        key = (summary["shift_mean_delta"], summary["normal_mean_delta"],
               -summary["mean_metrics"]["normal"]["nll"],
               -summary["mean_metrics"]["normal"]["brier"])
        if not np.isfinite(key).all():
            raise ValueError("selection metrics must be finite")
        if best is None:
            best = (key, stage["candidate"])
            continue
        for left, right in zip(key, best[0]):
            if abs(left - right) <= TIE_TOLERANCE:
                continue
            if left > right:
                best = (key, stage["candidate"])
            break
    return copy.deepcopy(best[1]) if best else None


def history_diagnostics(model, max_epochs):
    history = model.history
    prefix = history[:400]
    last = history[-1]
    at_400 = history[399] if len(history) >= 400 else None
    return {
        "best_epoch": model.best_epoch, "epochs_run": len(history), "max_epochs": max_epochs,
        "stopping_reason": "epoch_budget" if len(history) == max_epochs else "validation_patience",
        "best_validation_nll_first_400": min(item["val_nll"] for item in prefix),
        "best_epoch_first_400": min(prefix, key=lambda item: item["val_nll"])["epoch"],
        "epoch_400": at_400, "last_epoch": last,
        "last_epoch_validation_nll_decreased": bool(len(history) >= 2 and last["val_nll"] < history[-2]["val_nll"]),
        "selected_train_validation_gap": history[model.best_epoch - 1]["val_nll"] - history[model.best_epoch - 1]["train_nll"],
        "interpretation": "Endpoint loss trend is an observation; it does not prove convergence, underfit, or an optimization optimum.",
    }


def _fit_one(prepared, config, data_seed, init_seed, out, sources, phase="development"):
    if phase not in ("development", "final"):
        raise ValueError("phase must be development or final")
    started = time.perf_counter()
    family = config["family"]
    family_data = prepare_family(prepared, family)
    Z, y, indices = family_data["Z"], prepared["y"], prepared["indices"]
    settings = config["settings"]
    import_started = time.perf_counter()
    if config["backend"] == "extratrees":
        from sklearn.ensemble import ExtraTreesClassifier
    backend_import_seconds = time.perf_counter() - import_started
    fit_started = time.perf_counter()
    if config["backend"] == "numpy_softmax":
        model = Classifier(2 * len(feature_names(family)), 3, hidden=settings["hidden"], l2=settings["l2"], seed=init_seed)
        if settings["epochs"] <= 400:
            model.fit(Z["train"], y[indices["train"]], Z["validation"], y[indices["validation"]],
                      epochs=settings["epochs"], learning_rate=settings["learning_rate"], patience=settings["patience"])
        else:
            fit_research_classifier(model, Z["train"], y[indices["train"]], Z["validation"], y[indices["validation"]],
                                    epochs=settings["epochs"], learning_rate=settings["learning_rate"], patience=settings["patience"])
        state = model.to_dict()
        diagnostics = history_diagnostics(model, settings["epochs"])
        complexity = {"parameter_count": int(sum(value.size for value in model.params.values())),
                      "weight_parameter_count": int(sum(value.size for key, value in model.params.items() if key.startswith("W")))}
    else:
        model = ExtraTreesClassifier(**settings, random_state=init_seed)
        model.fit(Z["train"], y[indices["train"]])
        if model.classes_.tolist() != [0, 1, 2]:
            raise ValueError("tree is missing a synthetic class")
        state, diagnostics = None, None
        complexity = {"tree_count": len(model.estimators_),
                      "node_count": int(sum(tree.tree_.node_count for tree in model.estimators_))}
    fit_seconds = time.perf_counter() - fit_started
    calibration_started = time.perf_counter()
    temperature = float(fit_temperature(_logits(model, config["backend"], Z["calibration"]), y[indices["calibration"]]))
    calibration_seconds = time.perf_counter() - calibration_started
    prefix = f"{config['name']}_d{data_seed}_i{init_seed}"
    model_path = out / "models" / f"{prefix}.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if state is None:
        tree_path = model_path.with_suffix(".pkl")
        with tree_path.open("wb") as stream:
            pickle.dump(model, stream, protocol=pickle.HIGHEST_PROTOCOL)
        state = {"format": "trusted_self_generated_pickle", "file": tree_path.name,
                 "sha256": sha256(tree_path), "sklearn_version": __import__("sklearn").__version__,
                 "trust_requirement": "only self-generated local artifacts; hash is not provenance trust"}
    bundle = {"schema_version": MODEL_SCHEMA, "source_type": "synthetic", "coordinate_system": "local_xy_m",
              "config": copy.deepcopy(config), "class_names": CLASS_NAMES, "phase": phase,
              "data_seed": data_seed, "init_seed": init_seed, "feature_names": list(feature_names(family)),
              "feature_units": list(feature_units(family)), "temperature": temperature,
              "simtime_source": family in ("shape9_simtime4", "shape9_dt_only"),
              "preprocessor": family_data["preprocessor"].to_dict(), "classifier": state,
              "dataset_sha256": prepared["metadata"]["dataset_sha256"], "source_sha256": sources,
              "fit_groups": sorted(prepared["groups"]["train"]),
              "selection_groups": sorted(prepared["groups"]["validation"]),
              "calibration_groups": sorted(prepared["groups"]["calibration"])}
    save_json(model_path, bundle)
    reloaded = load_bundle(model_path, trusted_local=True)
    live = {**bundle, "_classifier": model} if config["backend"] == "extratrees" else bundle
    metrics, before, predictions = {}, {}, []
    inference_started = time.perf_counter()
    for split in SPLITS:
        role = {"test": "normal", "stress": "shift"}.get(split, split)
        logits = _logits(model, config["backend"], Z[split])
        raw, probs = softmax(logits), softmax(logits, temperature)
        meta = prepared["metadata"]["split_metadata"][split]
        denominator = {key: meta[key] for key in DENOMINATOR_FIELDS if key != "support"}
        before[role] = {**classification_metrics(y[indices[split]], raw), **denominator}
        metrics[role] = {**classification_metrics(y[indices[split]], probs), **denominator}
        metrics[role]["evaluation_role"] = f"{phase}_{role}"
    inference_seconds = time.perf_counter() - inference_started
    all_rows = prepared["dataset"]["records"]
    for calibrated in (False, True):
        probs, valid = predict_bundle(live, prepared["dataset"], calibrated=calibrated)
        restored, restored_valid = predict_bundle(reloaded, prepared["dataset"], calibrated=calibrated)
        if not np.array_equal(valid, restored_valid) or not np.array_equal(probs, restored, equal_nan=True):
            raise RuntimeError("saved raw/calibrated probabilities do not reproduce exactly")
    # The last loop iteration holds calibrated inference, including abstentions.
    for row, probability, usable in zip(all_rows, probs, valid):
        if row["split"] not in ("test", "stress"):
            continue
        predictions.append({"generator_seed": data_seed, "init_seed": init_seed,
            "sample_id": row["sample_id"], "vessel_id": row["vessel_id"],
            "split": row["split"], "true_label": row.get("label"),
            "evaluation_role": f"{phase}_{'normal' if row['split'] == 'test' else 'shift'}",
            "status": "ok" if usable else "abstained",
            "probabilities": probability.tolist() if usable else None,
            "predicted_label": int(probability.argmax()) if usable else None, "source_type": "synthetic"})
    prediction_path = out / "predictions" / f"{prefix}.json"
    save_json(prediction_path, predictions)
    result = {"candidate": config["name"], "data_seed": data_seed, "init_seed": init_seed,
              "phase": phase, "metrics": metrics, "before_calibration": before,
              "temperature": temperature, "history_diagnostics": diagnostics,
              "history": copy.deepcopy(model.history) if diagnostics else None,
              "complexity": complexity, "preprocessor_sha256": prepared["metadata"]["family_preprocessor_sha256"][family],
              "timing_seconds": {"classifier_fit": fit_seconds, "backend_import": backend_import_seconds,
                                 "calibration": calibration_seconds,
                                 "all_split_metrics_inference": inference_seconds,
                                 "fit_calibration_save_reload_total": time.perf_counter() - started},
              "model_path": model_path.relative_to(out).as_posix(), "model_sha256": sha256(model_path),
              "model_file_bytes": model_path.stat().st_size,
              "predictions_path": prediction_path.relative_to(out).as_posix(), "predictions_sha256": sha256(prediction_path),
              "reload_raw_and_calibrated_probabilities_identical": True,
              "dataset_sha256": prepared["metadata"]["dataset_sha256"]}
    if config["backend"] == "extratrees":
        result["tree_pickle_bytes"] = model_path.with_suffix(".pkl").stat().st_size
    epoch_text = (f"best_epoch={model.best_epoch}/{len(model.history)}, "
                  f"train NLL(raw)={before['train']['nll']:.4f}, val NLL(raw)={before['validation']['nll']:.4f}, ") if diagnostics else ""
    print(f"{phase} {prefix}: {epoch_text}normal F1={metrics['normal']['macro_f1']:.4f}, "
          f"shift F1={metrics['shift']['macro_f1']:.4f}, fit={fit_seconds:.3f}s", flush=True)
    return result


def protocol_payload(sources, *, started_at):
    return {"schema_version": "fishing_critique_comparison_protocol_v1", "source_type": "synthetic",
            "started_at_utc": started_at, "source_sha256_before_run": sources,
            "development_data_seeds": list(DEV_SEEDS), "init_seeds": list(INIT_SEEDS),
            "retired_final_seeds_excluded": list(RETIRED_FINAL_SEEDS),
            "reserved_fresh_final_seeds_not_generated": list(RESERVED_FINAL_SEEDS),
            "baseline": copy.deepcopy(BASELINE), "candidates": copy.deepcopy(list(CANDIDATES)),
            "training_procedure": copy.deepcopy(TRAINING_PROCEDURE),
            "selection_procedure": copy.deepcopy(SELECTION_PROCEDURE),
            "evaluation_roles": {"test": "development_normal", "stress": "development_shift"},
            "all_candidates_run_even_after_eligibility": True,
            "final_evaluation": "unavailable_in_this_runner_requires_separate_protocol_and_post_selection_freeze",
            "interpretation": "Three independent generator-seed repetitions are exploratory, not statistical proof.",
            "scope": "S0_synthetic_only_no_real_data_no_external_collection_no_hardware_simulated_timing_only"}


def _prepare_output(output_dir):
    out, allowed = Path(output_dir).resolve(), (ROOT / "outputs").resolve()
    if allowed not in out.parents:
        raise ValueError("use a new child directory under project outputs")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("output directory must be empty; prior evidence is preserved")
    out.mkdir(parents=True, exist_ok=True)
    return out


def run(output_dir):
    started = time.perf_counter()
    out = _prepare_output(output_dir)
    sources = source_hashes()
    protocol = protocol_payload(sources, started_at=utc_now())
    protocol_path = out / "protocol.json"
    save_json(protocol_path, protocol)
    (out / "protocol.sha256").write_text(sha256(protocol_path) + "\n", encoding="ascii")
    for name in SOURCE_FILES:
        target = out / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    gate = DevelopmentSeedGate(protocol_path, sources)
    print("Sealed development protocol and source snapshot saved before any generation or fit.", flush=True)
    result = {"schema_version": "fishing_critique_comparison_results_v1", "source_type": "synthetic",
              "protocol": protocol, "protocol_sha256": sha256(protocol_path), "stage_results": [],
              "selected_development_candidate": None, "final": {"executed": False, "generated": False,
              "reason": "separate_final_protocol_and_post_selection_freeze_required"},
              "limitations": ["Only S0 synthetic generating path families, not official fishing/accident labels.",
                  "Three development generator seeds do not establish real-domain generalization or statistical superiority.",
                  "The same generator and its biases are shared by every candidate.",
                  "Endpoint validation decline does not prove underfit, convergence, or optimality.",
                  "Temperature is a fitted calibration parameter, not proof of a causal failure explanation.",
                  "No real-data training, external collection, hardware test, or learner attainment assessment."]}
    baseline_records = None
    for config in (BASELINE, *CANDIDATES):
        records = []
        for data_seed in DEV_SEEDS:
            prepared = gate.get(data_seed)
            for init_seed in INIT_SEEDS:
                gate._verify()
                records.append(_fit_one(prepared, config, data_seed, init_seed, out, sources))
        if baseline_records is None:
            baseline_records = records
        summary = summarize_candidate(baseline_records, records)
        result["stage_results"].append({"candidate": copy.deepcopy(config), "records": records,
                                        "summary": summary, "role": "reference" if config == BASELINE else "candidate"})
        print(f"Candidate {config['name']}: normal delta={summary['normal_mean_delta']:+.6f}, "
              f"shift delta={summary['shift_mean_delta']:+.6f}, positive shift={summary['positive_shift_seeds']}/3, "
              f"eligible={summary['eligible']}, formal_selection={config.get('formal_selection', True)}", flush=True)
        save_json(out / "results.json", result)
    selected = select_candidate(result["stage_results"][1:])
    result["selected_development_candidate"] = selected
    result["outcome"] = "development_candidate_selected_final_not_run" if selected else "no_development_candidate_meets_criteria"
    result["dataset_manifest"] = {str(seed): prepared["metadata"] for seed, prepared in gate.cache.items()}
    result["generation_events"] = gate.calls
    all_runs = [row for stage in result["stage_results"] for row in stage["records"]]
    result["checks"] = {
        "sealed_protocol_unchanged": sha256(protocol_path) == gate.protocol_sha256,
        "sources_unchanged": source_hashes() == sources,
        "source_snapshot_matches": all(sha256(out / "source_snapshot" / name) == expected for name, expected in sources.items()),
        "only_new_development_data_generated": [event["seed"] for event in gate.calls] == list(DEV_SEEDS),
        "same_denominators": all(stage["summary"]["conditions"]["same_denominators"] for stage in result["stage_results"]),
        "literal_same_train_only_preprocessor_per_family": all(
            len({row["preprocessor_sha256"] for stage in result["stage_results"] if stage["candidate"]["family"] == family
                 for row in stage["records"] if row["data_seed"] == seed}) == 1
            for seed in DEV_SEEDS for family in TRAINING_PROCEDURE["feature_families"]),
        "all_raw_and_calibrated_reload_predictions_identical": all(row["reload_raw_and_calibrated_probabilities_identical"] for row in all_runs),
        "all_prespecified_candidates_completed": len(result["stage_results"]) == 1 + len(CANDIDATES),
        "no_final_real_data_or_hardware_evaluation": True,
    }
    result["runtime"] = {"seconds": time.perf_counter() - started, "python": platform.python_version(),
                         "python_executable": sys.executable, "numpy": np.__version__,
                         "sklearn": __import__("sklearn").__version__, "finished_at_utc": utc_now()}
    save_json(out / "results.json", result)
    if not all(result["checks"].values()):
        raise RuntimeError(f"comparison audit failed: {result['checks']}")
    save_json(out / "run_evidence.json", {"command": f"python tools/critique_comparison_20261027.py --out {out.relative_to(ROOT).as_posix()}",
        "protocol_sha256": gate.protocol_sha256, "checks": result["checks"], "runtime": result["runtime"],
        "outcome": result["outcome"], "artifact_sha256": {
            path.relative_to(out).as_posix(): sha256(path) for path in sorted(out.rglob("*")) if path.is_file()}})
    print(f"Outcome: {result['outcome']}; output: {out}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/critique_comparison_20261027")
    args = parser.parse_args()
    try:
        run(args.out)
    except (ValueError, RuntimeError, OSError, ImportError) as exc:
        parser.exit(2, f"Critique comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
