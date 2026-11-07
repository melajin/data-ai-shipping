"""Synthetic boundaries only: no real sources, saved models, or accident labels."""
import copy
import importlib.util
import inspect
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


if "round020_evaluate_under_test" in sys.modules:
    runner = sys.modules["round020_evaluate_under_test"]
else:
    specification = importlib.util.spec_from_file_location(
        "round020_evaluate_under_test", Path(__file__).with_name("evaluate.py"))
    runner = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = runner
    specification.loader.exec_module(runner)


def hours(timestamps, logits):
    return runner.aggregate_hours(timestamps, list(range(len(timestamps))), logits)


def model():
    return {"heldout": "a", "training_ids": ["b", "c"], "train_vessels": 2,
            "heldout_in_fit": False, "optimizer_success": True,
            "center": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0],
            "coefficients_intercept_first": [0.0] * 10}


class SelectorTests(unittest.TestCase):
    def test_missing_center_between_equal_observed_endpoints(self):
        prediction, rows, provenance = runner.select_timing(hours([0, 12], [-100.0, -100.0]))
        self.assertEqual(prediction["pred_ts"], 6)
        self.assertFalse(prediction["observed_at_center"])
        self.assertEqual(prediction["selected_support_share"], 1.0)
        self.assertEqual(prediction["nearby_observed_hours"], 2)
        self.assertEqual([row["candidate_ts"] for row in rows], list(range(13)))
        self.assertEqual(sum(row["selected"] for row in rows), 1)
        self.assertEqual([row["weight"] for row in provenance], [1.0, 1.0])

    def test_noncontiguous_ties_choose_actual_lower_median(self):
        prediction, rows, _ = runner.select_timing(hours([0, 40], [0.0, 0.0]))
        maxima = list(range(7)) + list(range(34, 41))
        self.assertEqual(json.loads(prediction["maximizing_candidate_hours_json"]), maxima)
        self.assertEqual(prediction["pred_ts"], 6)
        self.assertEqual(rows[20]["support_share"], 0.0)
        self.assertEqual(rows[20]["evidence_status"], "no_evidence")
        self.assertEqual(rows[20]["nearby_observed_hours"], 0)

    def test_duplicate_hours_max_and_deterministic_provenance(self):
        aggregated = runner.aggregate_hours([0, 0, 0, 12], [8, 7, 3, 9], [-1.0, 2.0, 2.0, 2.0])
        self.assertEqual(len(aggregated), 2)
        self.assertEqual(aggregated[0]["max_logit"], 2.0)
        self.assertEqual(aggregated[0]["source_ordinal"], 3)
        self.assertEqual(aggregated[0]["row_index_in_sorted_vessel"], 2)
        prediction, _, provenance = runner.select_timing(aggregated)
        self.assertEqual(prediction["pred_ts"], 6)
        self.assertEqual(prediction["normalization_weight_sum"], 2.0)
        self.assertEqual(provenance[0]["source_ordinal"], 3)

    def test_stable_negative_logits_and_local_fsum_preserve_tiny_support(self):
        prediction, _, provenance = runner.select_timing(hours([0, 12], [-10000.0, -10001.0]))
        self.assertEqual(prediction["pred_ts"], 6)
        self.assertEqual(provenance[0]["weight"], 1.0)
        self.assertAlmostEqual(provenance[1]["weight"], math.exp(-1.0))
        _, rows, _ = runner.select_timing(hours([0, 20], [0.0, -40.0]))
        self.assertGreater(rows[20]["support_share"], 0.0)
        self.assertEqual(rows[20]["nearby_weight_sum"], math.exp(-40.0))

    def test_empty_and_underflow_remain_explicit_missing_evidence(self):
        prediction, rows, provenance = runner.select_timing([])
        self.assertIsNone(prediction["pred_ts"])
        self.assertEqual(prediction["prediction_status"], "no_candidates")
        self.assertEqual(rows, [])
        self.assertEqual(provenance, [])
        prediction, rows, _ = runner.select_timing(hours([0, 24], [-10000.0, 0.0]))
        self.assertEqual(rows[0]["evidence_status"], "no_evidence")
        self.assertEqual(rows[0]["nearby_observed_hours"], 1)
        self.assertGreater(prediction["nearby_observed_but_zero_weight_candidate_hours"], 0)
        self.assertGreater(prediction["selected_support_share"], 0)


class EvaluationTests(unittest.TestCase):
    def test_full_grid_chance_unions_multiple_inclusive_windows(self):
        self.assertEqual(runner.candidate_chance(0, 20, [6, 10]), (17, 21, 17 / 21))
        self.assertEqual(runner.candidate_chance(0, 40, [0, 40]), (14, 41, 14 / 41))
        self.assertEqual(runner.candidate_chance(None, None, [0]), (0, 0, 0.0))
        self.assertEqual(runner.window_mask([0, 6, 7, 14, 20, 26, 27], [0, 20]),
                         [True, True, False, True, True, True, False])

    def test_exact_chance_and_worst_overlap_are_diagnostics(self):
        probability, pmf = runner.poisson_binomial([0.5, 0.5], 2)
        self.assertEqual(probability, 0.25)
        self.assertEqual(pmf, [0.25, 0.5, 0.25])
        self.assertGreater(runner.worst_overlap(9)["worst_one_sided_p"], 0.05)
        self.assertLessEqual(runner.worst_overlap(10)["worst_one_sided_p"], 0.05)
        self.assertEqual(runner.worst_overlap(3)["worst_one_sided_p"], 1.0)

    def test_user_screening_h3_h4_h5_and_strict_above_chance(self):
        self.assertEqual(runner.classify_result(3, 0.0)["decision_label"], "rejected")
        self.assertEqual(runner.classify_result(4, 0.0)["decision_label"], "hold")
        decision = runner.classify_result(5, 0.0)
        self.assertEqual(decision["decision_label"], "improvement_candidate")
        self.assertTrue(decision["improvement_candidate"])
        self.assertFalse(decision["confirmed_statistical_improvement"])
        self.assertFalse(decision["statistical_significance_required_for_decision"])
        self.assertNotIn("accepted", decision)
        self.assertEqual(runner.classify_result(5, 5 / 82)["decision_label"], "rejected")
        self.assertEqual(runner.classify_result(4, 5 / 82)["decision_label"], "rejected")


class ProvenanceTests(unittest.TestCase):
    def test_frozen_training_ids_and_parameter_shapes_cannot_leak_heldout(self):
        ids = {"a", "b", "c"}
        self.assertEqual(runner.validate_model(model(), ids)["training_ids"], ["b", "c"])
        bad_models = []
        for replacement in (["a", "b"], ["b", "b"], ["b"]):
            bad = model()
            bad["training_ids"] = replacement
            bad_models.append(bad)
        for key, replacement in (("center", [0.0, 0.0]), ("scale", [1.0, 0.0, 1.0]),
                                 ("coefficients_intercept_first", [0.0] * 9 + [math.inf])):
            bad = model()
            bad[key] = replacement
            bad_models.append(bad)
        bad = model()
        bad["heldout_in_fit"] = True
        bad_models.append(bad)
        for bad in bad_models:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                runner.validate_model(bad, ids)
        self.assertEqual(list(inspect.signature(runner.predict_vessel).parameters),
                         ["key", "group", "model", "old_prediction"])
        self.assertEqual(list(inspect.signature(runner.select_timing).parameters), ["hours"])

    def test_feature_order_and_original_top_parity_failure(self):
        import numpy as np
        features = runner.basis(np.array([[2.0, 3.0, 4.0]]), [0.0] * 3, [1.0] * 3)
        self.assertEqual(features.tolist(), [[2.0, 3.0, 4.0, 4.0, 9.0, 16.0, 6.0, 8.0, 12.0]])
        group = {"ts": np.array([0, 12]), "source_ordinal": np.array([5, 2]),
                 "log_geometry": np.zeros((2, 3))}
        stored = {"rfid_id": "a", "pred_ts": 12, "source_ordinal": 2, "peak_logit": 0.0,
                  "n_rows": 2, "prediction_status": "predicted"}
        prediction, _, _, audit = runner.predict_vessel("a", group, model(), stored)
        self.assertEqual(prediction["pred_ts"], 6)
        self.assertTrue(audit["passed"])
        for name, replacement in (("pred_ts", 0), ("source_ordinal", 5), ("peak_logit", 1e-8)):
            changed = {**stored, name: replacement}
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                runner.predict_vessel("a", group, model(), changed)
        close = {**stored, "peak_logit": 0.5e-10}
        self.assertTrue(runner.reconstruct_old_top("a", group, np.zeros(2), close)["passed"])

    def test_seal_is_verified_before_any_accident_timestamp_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(runner, "read_events") as events:
                with self.assertRaises(FileNotFoundError):
                    runner.evaluate_predictions(out, set(), {}, [])
                events.assert_not_called()
            for name in runner.PREDICTION_ARTIFACTS:
                (out / name).write_text("synthetic-only\n", encoding="utf-8")
            predictions = [{"rfid_id": f"synthetic_{i}"} for i in range(82)]
            runner.seal_predictions(out, predictions)
            runner.verify_prediction_seal(out)
            (out / "hourly_scores.csv").write_text("modified\n", encoding="utf-8")
            with patch.object(runner, "read_events") as events:
                with self.assertRaises(RuntimeError):
                    runner.evaluate_predictions(out, set(), {}, [])
                events.assert_not_called()

    def test_memory_deferral_precedes_execution_directory_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner, "HERE", Path(directory)), \
                    patch.object(runner, "memory_gate", side_effect=MemoryError("synthetic unavailable")):
                with self.assertRaises(MemoryError):
                    runner.run()
                self.assertFalse((Path(directory) / "execution_001").exists())


if __name__ == "__main__":
    # Independent invocation has the same pre-import RAM admission as --selftest.
    record = runner.memory_gate("synthetic_unittest", 384,
        "Small synthetic arrays and library imports; no real sources", log=None)
    runner.console({"synthetic_memory_gate": record})
    unittest.main(verbosity=2)
