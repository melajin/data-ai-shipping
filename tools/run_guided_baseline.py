#!/usr/bin/env python3
"""Replay the fixed S0 experiment plus one fixed linear baseline; no real-data training."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishing_demo.data import load_dataset
from fishing_demo.features import FEATURE_NAMES, feature_matrix
from fishing_demo.models import Classifier, Preprocessor, classification_metrics, fit_temperature, softmax
from fishing_demo.pipeline import (CANDIDATES, SPLITS, load_model, predict_records,
                                   run_demo, save_json, split_indices)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output_dir):
    out = Path(output_dir).resolve()
    allowed = (ROOT / "outputs").resolve()
    if allowed not in out.parents:
        raise ValueError("use a new child directory under the project's outputs directory")
    if out.exists() and any(out.iterdir()):
        raise ValueError("output directory must be empty; preserve earlier evidence")
    out.mkdir(parents=True, exist_ok=True)
    protocol_path = ROOT / "docs/guided_baseline_protocol_20261026.md"
    sources = ["fishing_demo/data.py", "fishing_demo/features.py", "fishing_demo/models.py",
               "fishing_demo/pipeline.py", "fishing_demo/visualization.py", "tools/run_guided_baseline.py",
               "docs/sample_system_contract.md", "docs/guided_baseline_protocol_20261026.md"]
    started = datetime.now(timezone.utc).isoformat()
    protocol = {
        "schema_version": "guided_baseline_protocol_v1", "client_date": "2026-10-26",
        "started_at_utc": started, "source_type": "synthetic", "evaluation_kind": "known_seed42_replay",
        "new_blind_test": False, "seed": 42, "epochs": 400, "learning_rate": 0.03, "patience": 35,
        "fixed_baseline": {"name": "linear_l2_001", "hidden": 0, "l2": 0.01},
        "replayed_candidates": [list(c) for c in CANDIDATES],
        "trace_rule": "first misclassified test sample sorted by sample_id; otherwise first correct",
        "control_rule": "first correct test sample with same true class, sorted by sample_id",
        "stress_case_rule": "first misclassified stress sample sorted by sample_id",
        "high_confidence_display_cutoff": 0.8, "comparison_tolerance": 1e-10,
        "success_criterion": "contract, reproducibility and trace checks; no arbitrary accuracy target",
        "stop_after_failure_analysis": True, "learner_understanding": "not_assessed",
        "protocol_sha256": sha256(protocol_path),
        "source_sha256_before_run": {p: sha256(ROOT / p) for p in sources},
        "roles_requested": [
            {"role": "astra_decision", "model": "gpt-6-astra", "effort": "high"},
            {"role": "sol_review", "model": "gpt-6.1-sol", "effort": "high"},
            {"role": "sol_complex", "model": "gpt-6.1-sol", "effort": "max"}],
        "runtime_model_independently_queried": False,
    }
    save_json(out / "protocol.json", protocol)
    (out / "protocol.md").write_bytes(protocol_path.read_bytes())
    print("Protocol written before training; fixed S0 replay, not a new blind test.", flush=True)
    report = run_demo(out, seed=42, epochs=400)
    data = load_dataset(out / "sample_dataset.json")
    bundle = load_model(out / "model.json")
    X, details = feature_matrix(data["records"])
    indices, groups = split_indices(data["records"], details)
    y = np.asarray([r["label"] for r in data["records"]], dtype=int)
    preprocessor = Preprocessor.from_dict(bundle["preprocessor"])
    Z = {s: preprocessor.transform(X[index]) for s, index in indices.items()}
    baseline = Classifier(2 * len(FEATURE_NAMES), n_classes=3, hidden=0, l2=0.01, seed=42)
    history = baseline.fit(Z["train"], y[indices["train"]], Z["validation"], y[indices["validation"]],
                           epochs=400, learning_rate=0.03, patience=35)
    temperature = fit_temperature(baseline.predict_logits(Z["calibration"]), y[indices["calibration"]])
    linear_bundle = copy.deepcopy(bundle)
    linear_bundle.update(selected_model="linear_l2_001", classifier=baseline.to_dict(),
                         temperature=float(temperature))
    save_json(out / "baseline_model.json", linear_bundle)
    baseline_predictions = predict_records(data, load_model(out / "baseline_model.json"))
    save_json(out / "baseline_predictions.json", baseline_predictions)
    linear_metrics = {}
    for s in SPLITS:
        logits = baseline.predict_logits(Z[s])
        linear_metrics[s] = classification_metrics(y[indices[s]], softmax(logits, temperature))
    val_replay = classification_metrics(y[indices["validation"]], softmax(baseline.predict_logits(Z["validation"])))
    old_val = report["candidates"][0]["validation_metrics"]
    if any(not np.isclose(val_replay[k], old_val[k], atol=1e-12, rtol=0)
           for k in ("accuracy", "macro_f1", "nll", "brier")):
        raise RuntimeError("fixed linear refit does not match the declared candidate replay")
    checks = {
        "group_overlap_zero": all(not groups[a] & groups[b] for i, a in enumerate(SPLITS) for b in SPLITS[i+1:]),
        "fixed_linear_reproduces_declared_candidate": True,
        "selected_model_serialization_identical": report["audit"]["serialization_predictions_identical"],
        "feature_order_matches": bundle["feature_names"] == list(FEATURE_NAMES),
        "selected_not_using_test_for_selection": not report["audit"]["test_used_for_selection"],
        "selected_not_using_stress_for_selection": not report["audit"]["stress_used_for_selection"],
        "source_files_unchanged_during_training": all(sha256(ROOT / p) == digest
                          for p, digest in protocol["source_sha256_before_run"].items()),
    }
    if not all(checks.values()):
        raise RuntimeError(f"guided baseline check failed: {checks}")
    save_json(out / "baseline_metrics.json", {
        "source_type": "synthetic", "model": "linear_l2_001", "hidden": 0, "l2": 0.01,
        "temperature": float(temperature), "best_epoch": baseline.best_epoch,
        "history": history, "metrics": linear_metrics,
        "validation_before_calibration": val_replay, "anomaly_model": "shared frozen train-fitted distance model",
        "evaluation_kind": "known_seed42_replay", "test_used_to_choose_baseline": False})
    save_json(out / "run_evidence.json", {
        "source_type": "synthetic", "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python tools/run_guided_baseline.py --out outputs/guided_baseline_20261026",
        "python_executable": sys.executable, "python": platform.python_version(), "numpy": np.__version__,
        "protocol_written_before_training": True, "checks": checks,
        "artifact_sha256_at_training_completion": {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file()},
        "learner_understanding": "not_assessed", "actual_data_evaluation": False,
        "hardware_experiment": False})
    for name, metrics in (("fixed linear", linear_metrics), (report["selected_model"], report["metrics"])):
        for split in ("test", "stress"):
            m = metrics[split]
            print(f"{name} {split}: accuracy={m['accuracy']:.6f} macro_f1={m['macro_f1']:.6f} nll={m['nll']:.6f}")
    print(f"Training checks passed. Outputs: {out}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/guided_baseline_20261026")
    args = parser.parse_args()
    try:
        run(args.out)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f"Guided baseline failed: {exc}\n")


if __name__ == "__main__":
    main()
