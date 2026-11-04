#!/usr/bin/env python3
"""Explore frozen final probabilities; never fit, select or modify a model.

Predictions contain calibrated probabilities only. For strictly positive rows,
T * centered(log(p)) reconstructs model logits up to a common additive offset.
For ExtraTrees this would be a transformed probability, not a training logit;
we therefore restrict reconstructed-logit summaries to the NumPy classifiers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_critique_comparison_20261027 import independent_metrics

BASELINE = "shape9_mlp_e400_l2_0"
LINEAR = "shape9_linear_e1200_l2_0_01"
TREE = "shape9_extratrees"
TINY = np.finfo(np.float64).tiny


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def reject(value):
        raise ValueError(f"nonfinite JSON: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_path(directory, relative):
    path = (directory / relative).resolve()
    require(not Path(relative).is_absolute() and directory in path.parents,
            "artifact path escapes frozen directory")
    return path


def distribution(values):
    values = np.asarray(values, dtype=float)
    require(np.isfinite(values).all(), "summary includes nonfinite values")
    if not values.size:
        return {"count": 0, "mean": None, "min": None, "p01": None,
                "p05": None, "median": None, "p95": None, "p99": None, "max": None}
    quantiles = np.quantile(values, [0, .01, .05, .5, .95, .99, 1])
    return {"count": int(values.size), "mean": float(values.mean()),
            **{name: float(value) for name, value in zip(
                ("min", "p01", "p05", "median", "p95", "p99", "max"), quantiles)}}


def cohort(loss, selected):
    loss, selected = np.asarray(loss), np.asarray(selected, dtype=bool)
    total = float(loss.sum())
    return {"count": int(selected.sum()), "fraction": float(selected.mean()),
            "mean_nll_within_cohort": float(loss[selected].mean()) if selected.any() else None,
            "contribution_to_overall_mean_nll": float(loss[selected].sum() / loss.size),
            "fraction_of_total_nll": float(loss[selected].sum() / total) if total else 0.0}


def probability_diagnostics(probabilities, labels):
    p, y = np.asarray(probabilities), np.asarray(labels)
    chosen = p[np.arange(y.size), y]
    loss = -np.log(np.maximum(chosen, TINY))
    correct = p.argmax(axis=1) == y
    confidence = p.max(axis=1)
    threshold_cohorts = {f"p_true_lt_{threshold:g}": cohort(loss, chosen < threshold)
                         for threshold in (.1, .01, 1e-6, 1e-12, 1e-100)}
    threshold_cohorts["p_true_exact_zero"] = cohort(loss, chosen == 0)
    sorted_indices = np.argsort(-loss, kind="stable")
    tails = {}
    for fraction in (.01, .05, .1):
        selected = np.zeros(y.size, dtype=bool)
        selected[sorted_indices[:max(1, int(np.ceil(y.size * fraction)))]] = True
        tails[f"highest_loss_{fraction:g}_fraction"] = cohort(loss, selected)
    return {"records": int(y.size), "calibrated_nll": float(loss.mean()),
            "accuracy": float(correct.mean()), "p_true": distribution(chosen),
            "nll": distribution(loss), "correct": cohort(loss, correct),
            "wrong": cohort(loss, ~correct),
            "correct_p_true": distribution(chosen[correct]),
            "wrong_p_true": distribution(chosen[~correct]),
            "wrong_confidence": distribution(confidence[~correct]),
            "wrong_confidence_ge_0_9": cohort(loss, ~correct & (confidence >= .9)),
            "wrong_confidence_ge_0_99": cohort(loss, ~correct & (confidence >= .99)),
            "threshold_cohorts": threshold_cohorts, "highest_loss_cohorts": tails}


def centered_logits(probabilities, temperature):
    p = np.asarray(probabilities, dtype=float)
    require((p > 0).all(), "zero probabilities prevent exact centered-logit reconstruction")
    logp = np.log(p)
    return temperature * (logp - logp.mean(axis=1, keepdims=True))


def raw_nll_from_centered_logits(logits, labels):
    shifted = logits - logits.max(axis=1, keepdims=True)
    logsum = np.log(np.exp(shifted).sum(axis=1))
    return -shifted[np.arange(len(labels)), labels] + logsum


def logit_diagnostics(logits, labels, correct):
    z, y, correct = np.asarray(logits), np.asarray(labels), np.asarray(correct)
    wrong_logits = z.copy()
    wrong_logits[np.arange(y.size), y] = -np.inf
    margin = z[np.arange(y.size), y] - wrong_logits.max(axis=1)
    spread = z.max(axis=1) - z.min(axis=1)
    return {"definition": "temperature*(log(calibrated_p)-row_mean(log(calibrated_p)))",
            "interpretation": "raw NumPy logits up to a common additive offset; original absolute logits are unidentified",
            "records": int(y.size), "row_logit_range": distribution(spread),
            "row_centered_l2_norm": distribution(np.linalg.norm(z, axis=1)),
            "true_class_margin": distribution(margin),
            "correct_true_class_margin": distribution(margin[correct]),
            "wrong_true_class_margin": distribution(margin[~correct]),
            "wrong_logit_range": distribution(spread[~correct])}


def paired_comparison(left, right):
    require(left["identities"] == right["identities"], "paired model rows do not match")
    y = np.asarray(left["labels"])
    a, b = np.asarray(left["p"]), np.asarray(right["p"])
    a_loss = -np.log(np.maximum(a[np.arange(y.size), y], TINY))
    b_loss = -np.log(np.maximum(b[np.arange(y.size), y], TINY))
    a_correct, b_correct = a.argmax(axis=1) == y, b.argmax(axis=1) == y
    groups = {}
    for name, selected in (("both_correct", a_correct & b_correct),
                           ("left_correct_right_wrong", a_correct & ~b_correct),
                           ("left_wrong_right_correct", ~a_correct & b_correct),
                           ("both_wrong", ~a_correct & ~b_correct)):
        groups[name] = {"count": int(selected.sum()),
                       "left_mean_nll": float(a_loss[selected].mean()) if selected.any() else None,
                       "right_mean_nll": float(b_loss[selected].mean()) if selected.any() else None,
                       "contribution_to_left_minus_right_overall_nll": float((a_loss[selected] - b_loss[selected]).sum() / y.size)}
    return {"direction": "left minus right", "paired_records": int(y.size),
            "nll_difference": float((a_loss - b_loss).mean()), "transition_cohorts": groups}


def analyze(directory):
    directory = directory.resolve()
    source = directory / "results.json"
    results = read_json(source)
    require(results["status"] == "complete" and results["source_type"] == "synthetic", "requires completed S0 results")
    require(results["primary"]["candidate"] is None and not results["final_scores_used_for_selection"], "preserve no-primary exploratory status")
    hashes = {str(source): sha256(source)}
    pooled, summaries, numeric_differences, records_checked = {}, {}, [], 0
    model_count = metric_splits = reconstructed_count = 0
    for stage in results["stage_results"]:
        name, backend = stage["candidate"]["name"], stage["candidate"]["backend"]
        pooled[name] = {split: {"identities": [], "labels": [], "p": [], "z": [], "runs": []}
                        for split in ("test", "stress")}
        require(len(stage["records"]) == 20, "requires 20 fixed runs per model")
        for run in stage["records"]:
            model_path = safe_path(directory, run["model_path"])
            prediction_path = safe_path(directory, run["predictions_path"])
            for path, expected in ((model_path, run["model_sha256"]),
                                   (prediction_path, run["predictions_sha256"])):
                actual = sha256(path)
                require(actual == expected, f"artifact hash mismatch: {path}")
                hashes[str(path)] = actual
            model = read_json(model_path)
            require(model["temperature"] == run["temperature"] > 0, "temperature mismatch")
            predictions = read_json(prediction_path)
            require(len(predictions) == 288, "requires 288 test+stress predictions per run")
            model_count += 1
            for split, role in (("test", "normal"), ("stress", "shift")):
                rows = [row for row in predictions if row["split"] == split]
                require(len(rows) == 144 and all(row["status"] == "ok" for row in rows), "incomplete split")
                p = np.asarray([row["probabilities"] for row in rows], dtype=float)
                y = np.asarray([row["true_label"] for row in rows], dtype=int)
                m = independent_metrics(y, p)
                require(all(row["predicted_label"] == int(np.argmax(row["probabilities"])) for row in rows), "predicted class differs")
                for metric in ("accuracy", "macro_f1", "nll", "brier"):
                    delta = abs(m[metric] - run["metrics"][role][metric])
                    numeric_differences.append(delta)
                    require(delta < 1e-12, f"saved {metric} does not reproduce")
                target = pooled[name][split]
                target["p"].extend(p.tolist())
                target["labels"].extend(y.tolist())
                target["identities"].extend((run["data_seed"], run["init_seed"], row["sample_id"], row["true_label"]) for row in rows)
                if backend == "numpy_softmax":
                    z = centered_logits(p, run["temperature"])
                    target["z"].extend(z.tolist())
                    raw_nll = float(raw_nll_from_centered_logits(z, y).mean())
                    delta = abs(raw_nll - run["before_calibration"][role]["nll"])
                    require(delta < 1e-12, "reconstructed raw NLL does not reproduce")
                    numeric_differences.append(delta)
                    reconstructed_count += len(rows)
                target["runs"].append({"generator_seed": run["data_seed"], "init_seed": run["init_seed"],
                                       "temperature": run["temperature"], "before_nll": run["before_calibration"][role]["nll"],
                                       "after_nll": m["nll"]})
                metric_splits += 1
                records_checked += len(rows)
        summaries[name] = {}
        for split, target in pooled[name].items():
            p, y = np.asarray(target["p"]), np.asarray(target["labels"])
            summary = probability_diagnostics(p, y)
            summary["before_calibration_nll_mean_from_frozen_results"] = float(np.mean([run["before_nll"] for run in target["runs"]]))
            summary["temperature"] = distribution([run["temperature"] for run in target["runs"]])
            summary["generator_seed_count"] = 10
            summary["model_initializations_per_seed"] = 2
            summary["before_after_per_run"] = target["runs"]
            chosen = p[np.arange(y.size), y]
            losses = -np.log(np.maximum(chosen, TINY))
            worst = np.argsort(-losses, kind="stable")[:10]
            summary["highest_loss_examples"] = [
                {"generator_seed": target["identities"][i][0], "init_seed": target["identities"][i][1],
                 "sample_id": target["identities"][i][2], "true_label": int(y[i]),
                 "calibrated_probabilities": p[i].tolist(), "nll": float(losses[i])}
                for i in worst]
            summary["exact_zero_true_probability_unique_trajectories"] = len({
                (target["identities"][i][0], target["identities"][i][2])
                for i in np.flatnonzero(chosen == 0)})
            if backend == "numpy_softmax":
                summary["reconstructed_centered_raw_logits"] = logit_diagnostics(np.asarray(target["z"]), y, p.argmax(axis=1) == y)
            else:
                summary["reconstructed_centered_raw_logits"] = None
                summary["raw_probability_limitation"] = "No raw per-row probabilities saved. Calibrated zero/tiny probabilities cannot prove raw tree zeros or identify clipping/temperature as the principal cause."
            summaries[name][split] = summary
    require(model_count == 180 and records_checked == 51840 and metric_splits == 360, "unexpected final evidence count")
    comparisons = {}
    for left, right in ((LINEAR, BASELINE), (TREE, BASELINE), ("shape9_mlp_e1200_l2_0", BASELINE)):
        comparisons[f"{left}_minus_{right}"] = {split: paired_comparison(pooled[left][split], pooled[right][split]) for split in ("test", "stress")}
    return {"schema_version": "fishing_posthoc_probability_diagnostics_v1", "source_type": "synthetic",
            "analysis_role": "posthoc_exploratory_no_multiple_comparison_adjustment",
            "training_performed": False, "model_selection_performed": False,
            "aggregation": "2880 rows per candidate/split: 10 generator seeds x 2 initializations x 144 rows. Equal denominators reproduce run and seed means; rows are not independent experimental replicates.",
            "limitations": ["Previously examined final data; no new confirmation or model promotion.",
                "Class-conditional and extreme-loss summaries describe associations, not causes of linear superiority or shift.",
                "Stored predictions have calibrated probabilities, not original logits or raw tree probabilities.",
                "Centered raw NumPy logits are reconstructed only for strictly positive saved probabilities using each run's saved temperature; common offsets cannot be recovered.",
                "No real-vessel observations, real missingness, accident labels, or scale/noise/fragment intervention are evaluated."],
            "verification": {"models": model_count, "prediction_rows": records_checked,
                "metric_splits": metric_splits, "centered_logit_rows_reconstructed": reconstructed_count,
                "numeric_comparisons": len(numeric_differences), "maximum_absolute_metric_difference": float(max(numeric_differences)),
                "source_hashes": hashes, "script_sha256": sha256(Path(__file__)),
                "metric_helper_sha256": sha256(ROOT / "tools/verify_critique_comparison_20261027.py")},
            "models": summaries, "paired_model_comparisons": comparisons}


def self_test():
    z = np.array([[1., 2., -1.], [-3., .5, 2.]])
    temperature = .7
    scaled = (z - z.max(axis=1, keepdims=True)) / temperature
    p = np.exp(scaled) / np.exp(scaled).sum(axis=1, keepdims=True)
    reconstructed = centered_logits(p, temperature)
    require(np.allclose(reconstructed, z - z.mean(axis=1, keepdims=True), atol=1e-14), "logit reconstruction test failed")
    shifted = z + np.array([[18.], [-29.]])
    require(np.allclose(z.max(axis=1)-z.min(axis=1), shifted.max(axis=1)-shifted.min(axis=1)), "offset invariance failed")
    d = probability_diagnostics(np.array([[1., 0., 0.], [.1, .8, .1]]), np.array([1, 1]))
    require(d["threshold_cohorts"]["p_true_exact_zero"]["count"] == 1 and
            abs(d["correct"]["contribution_to_overall_mean_nll"] + d["wrong"]["contribution_to_overall_mean_nll"] - d["calibrated_nll"]) < 1e-12,
            "zero-probability clipping or contribution decomposition failed")
    try:
        centered_logits(np.array([[1., 0., 0.]]), 1.)
    except ValueError:
        pass
    else:
        raise ValueError("zero probability must reject logit reconstruction")
    print("4 diagnostic self-checks passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "outputs/critique_comparison_20261027/final")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/posthoc_prediction_diagnostics_20261027.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    result = analyze(args.directory)
    require(args.out.resolve() != args.directory.resolve() and args.directory.resolve() not in args.out.resolve().parents,
            "output must be outside the frozen input experiment")
    require(args.out.resolve() not in [Path(path) for path in result["verification"]["source_hashes"]], "output cannot overwrite input")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result["verification"][key] for key in ("models", "prediction_rows", "metric_splits", "maximum_absolute_metric_difference")}, indent=2))


if __name__ == "__main__":
    main()
