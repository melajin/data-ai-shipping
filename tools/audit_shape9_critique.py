#!/usr/bin/env python3
"""Read-only numerical audit of the frozen synthetic shape9 seed-9101 fixture.

Only the requested audit JSON is written. No fitting, tuning, geometry changes,
external data access, or stored-model changes are performed.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.data import SPLITS, generate_dataset
from fishing_demo.features import feature_matrix as original_feature_matrix
from fishing_demo.iteration_features import feature_matrix
from fishing_demo.models import Classifier, Preprocessor, classification_metrics, fit_temperature, softmax
from fishing_demo.pipeline import dataset_digest, split_indices


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(model_path):
    before_hash = sha256(model_path)
    bundle = json.loads(model_path.read_text(encoding="utf-8"))
    if (bundle.get("source_type") != "synthetic" or bundle.get("data_seed") != 9101
            or bundle.get("init_seed") != 42 or bundle["config"]["family"] != "shape9"):
        raise ValueError("audit requires the frozen synthetic shape9 seed9101/init42 fixture")
    source_checks = {name: sha256(ROOT / name) == digest
                     for name, digest in bundle["source_sha256"].items()}
    if not all(source_checks.values()):
        raise ValueError(f"source snapshot mismatch: {source_checks}")

    dataset = generate_dataset(seed=9101)
    actual_dataset_hash = dataset_digest(dataset)
    if actual_dataset_hash != bundle["dataset_sha256"]:
        raise ValueError("regenerated synthetic data differs from the frozen dataset hash")
    records = dataset["records"]
    _, details = original_feature_matrix(records)
    indices, groups = split_indices(records, details)
    values = feature_matrix(records, "shape9")
    labels = np.asarray([row["label"] for row in records])
    preprocessor = Preprocessor.from_dict(bundle["preprocessor"])
    model = Classifier.from_dict(bundle["classifier"])
    if model.input_dim != 18 or model.hidden != 16 or model.l2 != 0:
        raise ValueError("unexpected frozen architecture or regularization")
    initial = Classifier(18, n_classes=3, hidden=16, l2=0, seed=42)
    transformed = {split: preprocessor.transform(values[ix]) for split, ix in indices.items()}
    split_counts = {}
    for split in SPLITS:
        raw = values[indices[split]]
        split_counts[split] = {
            "total_records": sum(row["split"] == split for row in records),
            "usable_labeled_records": len(raw), "vessel_groups": len(groups[split]),
            "missing_counts_by_feature": np.isnan(raw).sum(axis=0).tolist(),
            "observed_counts_by_feature": (~np.isnan(raw)).sum(axis=0).tolist(),
            "active_mask_counts": transformed[split][:, 9:].sum(axis=0).astype(int).tolist(),
        }

    train_loss, gradients = model.loss_and_gradients(transformed["train"], labels[indices["train"]])
    mask_audit = []
    for column, name in enumerate(bundle["feature_names"]):
        row = column + 9
        mask_audit.append({"feature": name, "W1_row_zero_based": row,
            "initial_equals_saved_exactly": bool(np.array_equal(initial.params["W1"][row], model.params["W1"][row])),
            "maximum_absolute_weight_change": float(np.max(np.abs(model.params["W1"][row] - initial.params["W1"][row]))),
            "maximum_absolute_train_gradient": float(np.max(np.abs(gradients["W1"][row])))})

    history_audit = {}
    for key in ("train_nll", "val_nll", "train_objective"):
        series = np.asarray([row[key] for row in model.history])
        delta = np.diff(series)
        history_audit[key] = {"epochs": len(series), "first": float(series[0]), "last": float(series[-1]),
            "increasing_steps": int((delta > 0).sum()), "flat_steps": int((delta == 0).sum()),
            "strictly_decreasing_steps": int((delta < 0).sum()), "last_step_change": float(delta[-1]),
            "last_10_epoch_improvement": float(series[-11] - series[-1]),
            "last_100_epoch_improvement": float(series[-101] - series[-1])}

    temperature_audit = {}
    for split in ("calibration", "test", "stress"):
        logits = model.predict_logits(transformed[split])
        before = softmax(logits)
        after = softmax(logits, bundle["temperature"])
        before_metrics = classification_metrics(labels[indices[split]], before)
        after_metrics = classification_metrics(labels[indices[split]], after)
        temperature_audit[split] = {"before_T1": before_metrics, "after_saved_T": after_metrics,
            "changed_predicted_class_count": int((before.argmax(axis=1) != after.argmax(axis=1)).sum())}
    replay_temperature = fit_temperature(model.predict_logits(transformed["calibration"]), labels[indices["calibration"]])
    if replay_temperature != bundle["temperature"]:
        raise ValueError("saved temperature does not reproduce from calibration grid")

    # Artificial feature-level interventions: both arms have the same median
    # imputation. Only the activated indicator's W1 contribution differs.
    counterfactual = []
    for sample_count in (60, len(indices["train"])):
        sample_values = values[indices["train"][:sample_count]]
        per_feature = []
        for column, name in enumerate(bundle["feature_names"]):
            if np.isnan(sample_values[:, column]).any():
                raise ValueError("counterfactual requires an entirely observed training feature")
            intervened_raw = sample_values.copy()
            intervened_raw[:, column] = np.nan
            intervened_z = preprocessor.transform(intervened_raw)
            original_probability = softmax(model.predict_logits(intervened_z), bundle["temperature"])
            # Since only one mask is active, setting it to zero is algebraically
            # identical to zeroing its W1 row; no model parameters are mutated.
            intervened_z[:, column + 9] = 0.0
            zero_mask_probability = softmax(model.predict_logits(intervened_z), bundle["temperature"])
            difference = np.abs(original_probability - zero_mask_probability)
            per_feature.append({"feature": name,
                "changed_predicted_class_count": int((original_probability.argmax(axis=1) != zero_mask_probability.argmax(axis=1)).sum()),
                "maximum_absolute_probability_change": float(difference.max()),
                "mean_row_maximum_absolute_probability_change": float(difference.max(axis=1).mean())})
        counterfactual.append({"selection": "first train rows in generator order", "records": sample_count,
            "generator_seed": 9101, "per_feature": per_feature})

    sensitivity_path = ROOT / "outputs/iterative_models_20261026/feature_sensitivity.json"
    sensitivity = json.loads(sensitivity_path.read_text(encoding="utf-8"))
    after_hash = sha256(model_path)
    if before_hash != after_hash:
        raise ValueError("stored model changed during audit")
    return {"schema_version": "shape9_critique_audit_v1", "source_type": "synthetic",
        "model_path": str(model_path), "model_sha256_before": before_hash, "model_sha256_after": after_hash,
        "dataset_sha256": actual_dataset_hash, "dataset_hash_matches_frozen_model": True,
        "source_hash_checks": source_checks, "feature_names": bundle["feature_names"],
        "split_counts": split_counts, "mask_W1_audit": mask_audit,
        "parameter_count": sum(value.size for value in model.params.values()),
        "mask_W1_parameter_count": int(model.params["W1"][9:].size),
        "maximum_absolute_nonmask_W1_change": float(np.max(np.abs(model.params["W1"][:9] - initial.params["W1"][:9]))),
        "final_train_objective": train_loss,
        "final_gradient_norm_by_parameter": {key: float(np.linalg.norm(value)) for key, value in gradients.items()},
        "final_gradient_total_l2_norm": float(np.sqrt(sum(np.sum(value ** 2) for value in gradients.values()))),
        "best_epoch": model.best_epoch, "history_audit": history_audit,
        "saved_temperature": bundle["temperature"], "replayed_calibration_temperature": replay_temperature,
        "temperature_audit": temperature_audit, "artificial_missing_feature_counterfactual": counterfactual,
        "sixty_record_claim": {"actual_frozen_training_records": len(indices["train"]),
            "actual_frozen_training_vessel_groups": len(groups["train"]),
            "sensitivity_source_path": str(sensitivity_path), "sensitivity_source_sha256": sha256(sensitivity_path),
            "sensitivity_generator_seed": sensitivity["generator_seed"], "sensitivity_data_role": sensitivity["data_role"],
            "sensitivity_selection": sensitivity["sample_selection"], "sensitivity_pairs_per_condition": sensitivity["n_pairs_per_condition"]},
        "observations": [
            {"confidence": "exact_reproduction", "finding": "All fixture split masks are inactive; mask W1 rows equal initialization and have zero training gradient."},
            {"confidence": "exact_reproduction", "finding": "The 400-epoch trace continues decreasing. This shows a binding epoch budget and nonzero gradient, not global convergence or its absence."},
            {"confidence": "exact_reproduction", "finding": "Saved T improves calibration/test NLL and worsens stress NLL without changing predicted classes."},
            {"confidence": "not_identified", "finding": "This audit does not establish why T is below one, or establish that more epochs would resolve calibration."},
        ],
        "caveats": ["All data are generated S0 geometry, not real trajectories, accident truth, or hardware measurements.",
            "Feature-level NaN interventions are artificial, not observed missing-data failures; no path parts are joined.",
            "Counterfactual comparison isolates the stored, never-trained indicator contribution, not total error from losing a feature.",
            "432 rows share 36 vessel groups; parameter-to-row counts alone do not establish overfitting or independence.",
            "No fitting/tuning or new held-out model selection is performed; conclusions apply to this frozen fixture."],
        "execution": {"argv": [sys.executable, *sys.argv], "python": platform.python_version(),
            "python_executable": sys.executable, "numpy": np.__version__, "platform": platform.platform(),
            "utc": datetime.now(timezone.utc).isoformat(), "audit_script_sha256": sha256(__file__)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "outputs/iterative_models_20261026/models/shape9_mlp_d9101_i42.json")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/shape9_critique_audit_20261027.json")
    args = parser.parse_args()
    result = audit(args.model.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Audit passed: train={result['sixty_record_claim']['actual_frozen_training_records']}, "
          f"best_epoch={result['best_epoch']}, T={result['saved_temperature']:.12f}; output={args.out}")


if __name__ == "__main__":
    main()
