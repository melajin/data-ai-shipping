"""Post-hoc audit checks using frozen states; these tests never fit a model."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from fishing_demo.data import CLASS_NAMES, generate_dataset
from fishing_demo.features import FEATURE_NAMES, FEATURE_UNITS, extract_features
from fishing_demo.models import AnomalyModel, Classifier, Preprocessor, classification_metrics
from fishing_demo.pipeline import MODEL_SCHEMA, predict_records
from tools.analyze_guided_baseline import (_check_destinations, _same, build_trace_case,
                                            manual_forward, manual_geometry, recompute_metrics,
                                            select_cases)


def frozen_bundle(hidden=16):
    dimension = 2 * len(FEATURE_NAMES)
    # Initialization produces a fixed valid state; no gradients, selection or fit.
    classifier = Classifier(dimension, hidden=hidden, seed=19)
    return {"schema_version": MODEL_SCHEMA, "source_type": "synthetic",
            "coordinate_system": "local_xy_m", "class_names": CLASS_NAMES.copy(),
            "feature_names": list(FEATURE_NAMES), "feature_units": list(FEATURE_UNITS),
            "selected_model": "frozen_test_mlp" if hidden else "linear_l2_001",
            "temperature": 1.3, "anomaly_threshold": 30.0,
            "classifier": classifier.to_dict(),
            "preprocessor": {"type": "preprocessor", "schema_version": 1,
                "n_features": len(FEATURE_NAMES), "medians": [0.0] * 8,
                "means": [0.0] * 8, "scales": [1.0] * 8, "all_missing": [False] * 8,
                "output_order": "scaled_features_then_missing_mask"},
            "anomaly_model": {"type": "anomaly", "schema_version": 1,
                "input_dim": dimension, "n_classes": 3, "shrinkage": 0.2,
                "means": np.zeros((3, dimension)).tolist(),
                "covariances": np.tile(np.eye(dimension), (3, 1, 1)).tolist(),
                "class_counts": [1, 1, 1], "score_definition": "minimum_class_squared_mahalanobis"}}


def prediction(sample_id, truth, guess, split="test"):
    return {"sample_id": sample_id, "true_label": truth, "predicted_label": guess,
            "split": split, "status": "ok"}


class GuidedBaselineAnalysisTests(unittest.TestCase):
    def test_case_choice_is_lexicographic_and_same_class(self):
        rows = [prediction("b-error", 1, 0), prediction("a-error", 2, 0),
                prediction("d-control", 2, 2), prediction("c-control", 2, 2),
                prediction("0-other-class", 0, 0), prediction("stress-b", 0, 2, "stress"),
                prediction("stress-a", 1, 0, "stress")]
        expected = select_cases(rows)
        actual = select_cases(list(reversed(rows)))
        self.assertEqual(expected, actual)
        self.assertEqual(actual["selected"]["sample_id"], "a-error")
        self.assertEqual(actual["comparison"]["sample_id"], "c-control")
        self.assertEqual(actual["stress_misclassification"]["sample_id"], "stress-a")
        self.assertEqual(actual["selected_kind"], "first_test_misclassification")

    def test_no_error_fallback_and_missing_comparison_are_explicit(self):
        result = select_cases([prediction("a", 0, 0), prediction("b", 1, 1)])
        self.assertEqual(result["selected_kind"], "first_test_correct_fallback")
        self.assertIsNone(result["comparison"])
        self.assertEqual(result["comparison_status"], "no_other_same_class_correct_test_example")
        self.assertIsNone(result["stress_misclassification"])
        with self.assertRaisesRegex(ValueError, "no evaluable"):
            select_cases([prediction("x", 0, 1, "stress")])

    def test_confusion_mapping_metrics_and_invalid_label_mask(self):
        y = [0, 1, 1, 2, None, -1, 3, True]
        p = np.array([[0.8, 0.1, 0.1], [0.7, 0.2, 0.1], [0.1, 0.6, 0.3],
                      [0.1, 0.7, 0.2]] + [[0.2, 0.3, 0.5]] * 4)
        result = recompute_metrics(y, p)
        self.assertEqual(result["confusion"], [[1, 0, 0], [1, 1, 0], [0, 1, 0]])
        self.assertEqual(result["support"], [1, 2, 1])
        self.assertEqual(result["per_class"][0]["precision"], 0.5)
        self.assertEqual(result["per_class"][1]["recall"], 0.5)
        self.assertEqual(result["per_class"][2]["f1"], 0.0)
        reference = classification_metrics([0, 1, 1, 2], p[:4])
        for key in ("accuracy", "macro_f1", "nll", "brier", "confusion", "support"):
            np.testing.assert_allclose(result[key], reference[key], rtol=0, atol=1e-10)
        with self.assertRaisesRegex(ValueError, "valid label"):
            recompute_metrics([None], [[0.2, 0.3, 0.5]])

    def test_manual_geometry_preserves_parts_and_uses_unweighted_mean(self):
        row = {"sample_id": "manual", "vessel_id": "v", "split": "test", "label": 0,
               "parts": [[[0, 0], [3, 0], [3, 4]], [[1000, 1000], [1001, 1000]], [[9, 9]]],
               "sim_times": [[0, 1, 2], [3, 4], [5]], "scenario": "base", "quality": {}}
        extracted = extract_features(row)
        checked = manual_geometry(row, extracted)
        self.assertEqual(checked["total_length_m"], 8.0)
        self.assertAlmostEqual(checked["mean_part_straightness"], (5 / 7 + 1) / 2)
        self.assertNotAlmostEqual(checked["mean_part_straightness"], 6 / 8)
        self.assertEqual(len(checked["parts"]), 3)
        self.assertIsNone(checked["parts"][-1]["straightness"])

    def test_manual_forward_agrees_for_linear_and_tanh(self):
        values = np.linspace(-2, 2, 48).reshape(3, 16)
        for hidden in (0, 16):
            with self.subTest(hidden=hidden):
                model = Classifier.from_dict(frozen_bundle(hidden)["classifier"])
                logits, preactivation, activation = manual_forward(model, values)
                np.testing.assert_allclose(logits, model.predict_logits(values), atol=1e-10, rtol=0)
                if hidden:
                    self.assertEqual(preactivation.shape, (3, 16))
                    np.testing.assert_allclose(activation, np.tanh(preactivation), rtol=0, atol=1e-10)
                else:
                    self.assertIsNone(preactivation)
                    self.assertIsNone(activation)

    def test_output_alias_cannot_overwrite_preserved_dashboard(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder).resolve()
            source = out / "dashboard.html"
            source.write_text("preserved", encoding="utf-8")
            os.link(source, out / "analysis.json")
            with self.assertRaisesRegex(ValueError, "overwrite a source"):
                _check_destinations(out, [source])
            self.assertEqual(source.read_text(encoding="utf-8"), "preserved")

    def test_json_check_rejects_bool_label_and_numeric_drift(self):
        with self.assertRaises(AssertionError):
            _same({"label": True}, {"label": 1}, "prediction")
        with self.assertRaises(AssertionError):
            _same([0.2, 0.8], [0.2 + 1e-5, 0.8], "probabilities")
        _same([0.2, 0.8], [0.2 + 1e-12, 0.8], "probabilities")

    def test_trace_has_reproducible_forward_and_rejects_saved_tampering_without_fit(self):
        data = generate_dataset(seed=9, groups_per_split={s: 1 for s in
            ("train", "validation", "calibration", "test", "stress")}, samples_per_class=1)
        selected, baseline = frozen_bundle(), frozen_bundle(0)
        # Any accidental fitting by inference or tracing turns this test into a failure.
        with patch.object(Classifier, "fit", side_effect=AssertionError("fit forbidden")), \
             patch.object(Preprocessor, "fit", side_effect=AssertionError("fit forbidden")), \
             patch.object(AnomalyModel, "fit", side_effect=AssertionError("fit forbidden")):
            predictions = predict_records(data, selected)
            baseline_predictions = predict_records(data, baseline)
            row = data["records"][0]
            trace = build_trace_case(row, extract_features(row), selected, baseline,
                                     predictions[0], baseline_predictions[0])
            self.assertEqual(len(trace["raw8"]), 8)
            self.assertEqual(len(trace["preprocessing"]["model_input16"]), 16)
            self.assertEqual(len(trace["selected_prediction"]["hidden16"]), 16)
            self.assertEqual(trace["raw_record"], row)
            self.assertFalse(trace["raw_record_is_real_observation"])
            self.assertTrue(trace["baseline_prediction"]["same_model_input_as_selected"])
            damaged = copy.deepcopy(predictions[0])
            damaged["probabilities"][0] += 1e-5
            with self.assertRaises(AssertionError):
                build_trace_case(row, extract_features(row), selected, baseline, damaged)


if __name__ == "__main__":
    unittest.main()
