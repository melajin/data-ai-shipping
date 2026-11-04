"""Frozen analysis checks: seed pairing, metric validation and no-fit traces."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from fishing_demo.models import Classifier, Preprocessor, classification_metrics
from fishing_demo.iteration_features import feature_names, feature_units
from tools import analyze_iteration_results as analysis
from tools import run_iterative_models as runner


def metric(value):
    return {"macro_f1": value, "total": 144, "valid": 144, "abstained": 0,
            "evaluated_labeled": 144, "support": [48, 48, 48], "evaluation_row_sha256": "same"}


def runs(seeds=runner.DEV_SEEDS, normal=.7, shift=.4):
    return [{"data_seed": seed, "init_seed": init,
             "metrics": {"normal": metric(normal), "shift": metric(shift)}}
            for seed in seeds for init in runner.INIT_SEEDS]


def prediction(sample_id, truth, guess, seed=9101, split="stress"):
    p = [0.1, 0.1, 0.1]
    p[guess] = 0.8
    return {"generator_seed": seed, "init_seed": 42, "sample_id": sample_id,
            "vessel_id": "same-vessel", "split": split, "true_label": truth,
            "predicted_label": guess, "probabilities": p, "status": "ok", "source_type": "synthetic"}


def frozen_bundle(family):
    count = len(feature_names(family))
    return {"schema_version": runner.MODEL_SCHEMA, "source_type": "synthetic",
        "coordinate_system": "local_xy_m", "class_names": runner.CLASS_NAMES,
        "config": runner.candidate(f"{family}_mlp", family), "init_seed": 42,
        "feature_names": list(feature_names(family)), "feature_units": list(feature_units(family)),
        "preprocessor": {"type": "preprocessor", "schema_version": 1, "n_features": count,
            "medians": [0.] * count, "means": [0.] * count, "scales": [1.] * count,
            "all_missing": [False] * count, "output_order": "scaled_features_then_missing_mask"},
        "classifier": Classifier(count * 2, 3, hidden=16, l2=0, seed=42).to_dict(), "temperature": 1.3}


class IterationAnalysisTests(unittest.TestCase):
    def test_initialization_mean_precedes_generator_seed_pairing(self):
        baseline, candidate = runs(), runs(normal=.695, shift=.46)
        candidate[0]["metrics"]["shift"]["macro_f1"] = .6
        candidate[1]["metrics"]["shift"]["macro_f1"] = .2
        candidate[2]["metrics"]["shift"]["macro_f1"] = .56
        candidate[3]["metrics"]["shift"]["macro_f1"] = .56
        result = analysis.recompute_paired_summary(baseline, list(reversed(candidate)))
        self.assertAlmostEqual(result["per_seed"][0]["shift"]["delta"], 0)
        self.assertAlmostEqual(result["normal_mean_delta"], -.005)
        self.assertAlmostEqual(result["shift_mean_delta"], .068)
        self.assertEqual(result["positive_shift_seeds"], 4)
        self.assertTrue(result["eligible"])

    def test_pairing_rejects_missing_duplicate_and_row_identity_differences(self):
        baseline, candidate = runs(), runs(shift=.5)
        with self.assertRaisesRegex(ValueError, "every preregistered"):
            analysis.recompute_paired_summary(baseline, candidate[:-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            analysis.recompute_paired_summary(baseline, candidate + [candidate[0]])
        candidate[0]["metrics"]["shift"]["evaluation_row_sha256"] = "different"
        result = analysis.recompute_paired_summary(baseline, candidate)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["conditions"]["same_denominators"])

    def test_final_criteria_and_seed_bootstrap_are_independent_and_deterministic(self):
        baseline, candidate = runs(runner.FINAL_SEEDS), runs(runner.FINAL_SEEDS, shift=.5)
        result = analysis.recompute_paired_summary(baseline, candidate, final=True)
        self.assertEqual(result, analysis.recompute_paired_summary(baseline, candidate, final=True))
        self.assertEqual(result["seed_count"], 10)
        self.assertEqual(result["positive_shift_seeds"], 10)
        self.assertAlmostEqual(result["shift_paired_bootstrap95"]["low"], .1)
        self.assertAlmostEqual(result["shift_paired_bootstrap95"]["high"], .1)
        self.assertTrue(result["success"])
        for row in candidate[:6]:
            row["metrics"]["shift"]["macro_f1"] = .39
        self.assertFalse(analysis.recompute_paired_summary(baseline, candidate, final=True)["success"])

    def test_fixed_fixture_uses_composite_identity_and_lexicographic_cases(self):
        baseline = [prediction("b", 0, 2), prediction("a", 1, 0), prediction("c", 2, 2),
                    prediction("0-other-seed", 0, 2, seed=9102)]
        candidate = [prediction("b", 0, 0), prediction("a", 1, 1), prediction("c", 2, 0),
                     prediction("0-other-seed", 0, 0, seed=9102)]
        result = analysis.select_fixture_cases(list(reversed(baseline)), candidate)
        self.assertEqual(result["improved"][0]["sample_id"], "a")
        self.assertEqual(result["remaining_failure"][0]["sample_id"], "c")
        self.assertEqual(result["counts"]["evaluated_shift"], 3)
        self.assertEqual(result["counts"]["baseline_wrong_candidate_correct"], 2)
        self.assertEqual(result["counts"]["baseline_correct_candidate_wrong"], 1)
        with self.assertRaises(AssertionError):
            analysis.match_prediction_pairs(baseline, candidate[:-1])
        candidate[0]["true_label"] = 2
        with self.assertRaises(AssertionError):
            analysis.match_prediction_pairs(baseline, candidate)

    def test_prediction_metric_recomputation_detects_saved_metric_tampering(self):
        predictions = [prediction("n0", 0, 0, split="test"), prediction("n1", 1, 0, split="test"),
                       prediction("s0", 0, 0), prediction("s1", 1, 1)]
        run = {"data_seed": 9101, "init_seed": 42, "candidate": "shape9_mlp", "phase": "final", "metrics": {}}
        manifest = {"split_metadata": {}}
        for role, split in (("normal", "test"), ("shift", "stress")):
            rows = [p for p in predictions if p["split"] == split]
            meta = {"total": 2, "valid": 2, "abstained": 0, "evaluated_labeled": 2,
                    "evaluation_row_sha256": analysis.canonical_digest([p["sample_id"] for p in rows])}
            values = classification_metrics([p["true_label"] for p in rows], [p["probabilities"] for p in rows])
            values.update(meta, evaluation_role=f"final_{role}")
            run["metrics"][role] = values
            manifest["split_metadata"][split] = meta
        checked = analysis.audit_prediction_metrics(predictions, run, manifest)
        self.assertEqual(checked["normal"]["confusion"], [[1, 0, 0], [1, 0, 0], [0, 0, 0]])
        damaged = copy.deepcopy(run)
        damaged["metrics"]["shift"]["macro_f1"] += .01
        with self.assertRaises(AssertionError):
            analysis.audit_prediction_metrics(predictions, damaged, manifest)

    def test_development_only_analysis_does_not_generate_final_data(self):
        with patch.object(analysis, "generate_dataset", side_effect=AssertionError("generation forbidden")) as generate:
            self.assertIsNone(analysis.replay_fixture_if_completed(Path("unused"), {"final": {"executed": False}}))
            with self.assertRaisesRegex(ValueError, "completed final"):
                analysis.replay_fixture_if_completed(Path("unused"), {"final": {"executed": True}})
            generate.assert_not_called()

    def test_artifact_hash_mismatch_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.json"
            path.write_text("frozen", encoding="utf-8")
            digest = analysis.sha256(path)
            analysis.verify_file_hash(path, digest)
            path.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "SHA256 mismatch"):
                analysis.verify_file_hash(path, digest)

    def test_dynamic_trace_is_18_inputs_and_calls_no_fit(self):
        row = {"sample_id": "fixture", "vessel_id": "v", "split": "stress", "label": 1,
               "parts": [[[0, 0], [2, 0], [3, 2]]], "sim_times": [[0, 1, 2]],
               "scenario": "shift", "quality": {}}
        bundle = frozen_bundle("shape9")
        with patch.object(Classifier, "fit", side_effect=AssertionError("fit forbidden")), \
             patch.object(Preprocessor, "fit", side_effect=AssertionError("fit forbidden")):
            probabilities, valid = runner.predict_bundle(bundle, [row])
            saved = {"probabilities": probabilities[0].tolist(), "true_label": 1,
                     "predicted_label": int(probabilities[0].argmax())}
            trace = analysis.trace_model(bundle, row, saved)
            self.assertEqual(trace["raw_feature_count"], 9)
            self.assertEqual(trace["model_input_count"], 18)
            self.assertEqual(len(trace["model_input"]), 18)
            self.assertEqual(len(trace["hidden16"]), 16)
            self.assertTrue(trace["input_count_differs_from_phase1"])
            self.assertTrue(trace["forward_matches_saved_atol_1e_10"])
            saved["probabilities"][0] += .001
            with self.assertRaises(AssertionError):
                analysis.trace_model(bundle, row, saved)


if __name__ == "__main__":
    unittest.main()
