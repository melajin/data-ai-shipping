"""Numerical and leakage-boundary checks for the synthetic-only NumPy models."""

import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.models import (  # noqa: E402
    AnomalyModel, Classifier, Preprocessor, classification_metrics,
    fit_temperature, softmax,
)


class PreprocessorTests(unittest.TestCase):
    def test_train_only_median_scaling_and_mask_order(self):
        training = np.array([[1, np.nan, 4], [3, np.nan, 4], [np.nan, np.nan, 4]])
        processor = Preprocessor().fit(training)
        np.testing.assert_allclose(processor.medians_, [2, 0, 4])
        np.testing.assert_allclose(processor.means_, [2, 0, 4])
        np.testing.assert_allclose(processor.scales_, [np.sqrt(2 / 3), 1, 1])
        transformed = processor.transform(training)
        self.assertEqual(transformed.shape, (3, 6))
        np.testing.assert_allclose(transformed[2], [0, 0, 0, 1, 1, 0])
        before = copy.deepcopy(processor.to_dict())
        validation = processor.transform([[100, 5, np.nan]])
        np.testing.assert_allclose(validation[0], [98 / np.sqrt(2 / 3), 5, 0, 0, 0, 1])
        self.assertEqual(processor.to_dict(), before)
        np.testing.assert_array_equal(processor.all_missing_, [False, True, False])

    def test_all_missing_fallback_and_json_round_trip(self):
        processor = Preprocessor().fit([[np.nan, 5], [np.nan, 5]])
        np.testing.assert_allclose(processor.transform([[np.nan, np.nan]]), [[0, 0, 1, 1]])
        restored = Preprocessor.from_dict(json.loads(json.dumps(processor.to_dict(), allow_nan=False)))
        np.testing.assert_array_equal(restored.transform([[3, 6], [np.nan, 5]]),
                                      processor.transform([[3, 6], [np.nan, 5]]))

    def test_preprocessing_rejects_invalid_inputs_and_state(self):
        with self.assertRaises(ValueError):
            Preprocessor().transform([[1]])
        with self.assertRaises(ValueError):
            Preprocessor().to_dict()
        for value in ([1, 2], np.empty((0, 2)), [[np.inf]], [[-np.inf]], [[[]]]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Preprocessor().fit(value)
        processor = Preprocessor().fit([[np.nan, 1], [np.nan, 3]])
        for key, value in (("scales", [0, 1]), ("means", [1, 2]),
                           ("medians", [float("nan"), 2]),
                           ("all_missing", [1, False]), ("schema_version", 2),
                           ("schema_version", True),
                           ("output_order", "unknown")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                state = processor.to_dict()
                state[key] = value
                Preprocessor.from_dict(state)
        self.assertEqual(processor.transform(np.empty((0, 2))).shape, (0, 4))


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(17)
        self.X = self.rng.normal(size=(5, 3))
        self.y = np.array([0, 1, 2, -1, np.nan])

    def test_linear_and_tanh_gradients_match_central_finite_differences(self):
        for hidden in (0, 16):
            with self.subTest(hidden=hidden):
                model = Classifier(3, hidden=hidden, l2=0.13, seed=9)
                analytic_loss, analytic = model.loss_and_gradients(self.X, self.y)
                self.assertTrue(np.isfinite(analytic_loss))
                for name, parameter in model.params.items():
                    numeric = np.zeros_like(parameter)
                    for index in np.ndindex(parameter.shape):
                        original = parameter[index]
                        parameter[index] = original + 1e-6
                        plus = model.loss_and_gradients(self.X, self.y)[0]
                        parameter[index] = original - 1e-6
                        minus = model.loss_and_gradients(self.X, self.y)[0]
                        parameter[index] = original
                        numeric[index] = (plus - minus) / 2e-6
                    np.testing.assert_allclose(analytic[name], numeric, rtol=2e-5, atol=2e-7,
                                               err_msg=f"hidden={hidden}, parameter={name}")

    def test_invalid_labels_are_masked_before_indexing_and_denominator(self):
        for hidden in (0, 16):
            model = Classifier(3, hidden=hidden)
            with np.errstate(all="raise"):
                loss, gradients = model.loss_and_gradients(self.X, self.y)
                subset_loss, subset_gradients = model.loss_and_gradients(self.X[:3], [0, 1, 2])
                other_invalid_loss, _ = model.loss_and_gradients(self.X, [0, 1, 2, 999, 0.5])
            self.assertEqual(loss, subset_loss)
            self.assertEqual(loss, other_invalid_loss)
            for key in gradients:
                np.testing.assert_array_equal(gradients[key], subset_gradients[key])
            for labels in ([-1] * 5, [np.nan] * 5, [999] * 5, [0.5] * 5):
                with self.subTest(hidden=hidden, labels=labels), self.assertRaises(ValueError):
                    model.loss_and_gradients(self.X, labels)

    def test_l2_regularizes_only_weights_with_half_factor(self):
        for hidden in (0, 16):
            regularized = Classifier(3, hidden=hidden, l2=0.4, seed=7)
            unregularized = Classifier(3, hidden=hidden, l2=0.0, seed=7)
            loss, gradients = regularized.loss_and_gradients(self.X, self.y)
            baseline, baseline_gradients = unregularized.loss_and_gradients(self.X, self.y)
            expected_penalty = 0.2 * sum(np.sum(value**2) for key, value in regularized.params.items()
                                         if key.startswith("W"))
            self.assertAlmostEqual(loss - baseline, expected_penalty, places=12)
            for key, value in regularized.params.items():
                expected = 0.4 * value if key.startswith("W") else np.zeros_like(value)
                np.testing.assert_allclose(gradients[key] - baseline_gradients[key], expected, atol=1e-14)

    def test_full_batch_training_learns_a_small_three_class_problem(self):
        centers = np.array([[-3, 0], [3, 0], [0, 3]])
        X = np.concatenate([center + self.rng.normal(0, 0.2, size=(15, 2)) for center in centers])
        y = np.repeat(np.arange(3), 15)
        for hidden in (0, 16):
            with self.subTest(hidden=hidden):
                model = Classifier(2, hidden=hidden, l2=0.01, seed=4)
                initial_nll = classification_metrics(y, softmax(model.predict_logits(X)))["nll"]
                history = model.fit(X, y, X, y, epochs=120, learning_rate=0.08, patience=15)
                metrics = classification_metrics(y, softmax(model.predict_logits(X)))
                self.assertGreater(metrics["accuracy"], 0.95)
                self.assertLess(metrics["nll"], initial_nll / 2)
                self.assertEqual(set(history[0]), {"epoch", "train_nll", "val_nll", "train_objective"})
                self.assertAlmostEqual(metrics["nll"], min(row["val_nll"] for row in history), places=12)
                self.assertEqual(model.best_epoch, min(history, key=lambda row: row["val_nll"])["epoch"])

    def test_early_stopping_restores_best_checkpoint(self):
        X = np.array([[-1.0], [1.0]])
        train_y, val_y = [0, 1], [1, 0]
        expected = Classifier(1, n_classes=2, l2=0, seed=2)
        model = Classifier(1, n_classes=2, l2=0, seed=2)
        for classifier in (expected, model):
            classifier.params["W"][:] = 0
        expected.fit(X, train_y, X, val_y, epochs=1, learning_rate=0.2, patience=3)
        history = model.fit(X, train_y, X, val_y, epochs=50, learning_rate=0.2, patience=3)
        self.assertEqual(model.best_epoch, 1)
        self.assertEqual(len(history), 4)
        self.assertGreater(history[-1]["val_nll"], history[0]["val_nll"])
        for key in model.params:
            np.testing.assert_array_equal(model.params[key], expected.params[key])

    def test_fit_ignores_invalid_labels_in_train_and_validation(self):
        model = Classifier(3, seed=3)
        expected = Classifier(3, seed=3)
        actual_history = model.fit(self.X, self.y, self.X, self.y, epochs=8, patience=4)
        expected_history = expected.fit(self.X[:3], [0, 1, 2], self.X[:3], [0, 1, 2],
                                         epochs=8, patience=4)
        self.assertEqual(actual_history, expected_history)
        np.testing.assert_array_equal(model.predict_logits(self.X), expected.predict_logits(self.X))

    def test_fit_and_constructor_reject_nonfinite_or_invalid_inputs(self):
        for kwargs in ({"input_dim": 0}, {"input_dim": 3, "n_classes": 1},
                       {"input_dim": 3, "hidden": 2}, {"input_dim": 3, "l2": -1},
                       {"input_dim": 3, "seed": True}, {"input_dim": 3, "l2": np.inf}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Classifier(**kwargs)
        model = Classifier(3)
        original = copy.deepcopy(model.to_dict())
        X = self.X.copy()
        X[0, 0] = np.nan
        for bad_X, bad_y, bad_val, bad_y_val, kwargs in (
                (X, self.y, self.X, self.y, {}),
                (self.X, [-1] * 5, self.X, self.y, {}),
                (self.X, self.y, self.X, [np.nan] * 5, {}),
                (self.X, self.y, self.X[:, :2], self.y, {}),
                (self.X, self.y, self.X, self.y, {"epochs": 0}),
                (self.X, self.y, self.X, self.y, {"epochs": 401}),
                (self.X, self.y, self.X, self.y, {"learning_rate": np.nan}),
                (self.X, self.y, self.X, self.y, {"learning_rate": -1}),
                (self.X, self.y, self.X, self.y, {"patience": 0})):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                model.fit(bad_X, bad_y, bad_val, bad_y_val, **kwargs)
        self.assertEqual(model.to_dict(), original)
        self.assertEqual(model.predict_logits(np.empty((0, 3))).shape, (0, 3))

    def test_classifier_json_round_trip_and_invalid_states(self):
        for hidden in (0, 16):
            model = Classifier(3, hidden=hidden)
            model.fit(self.X, self.y, self.X, self.y, epochs=5)
            state = json.loads(json.dumps(model.to_dict(), allow_nan=False))
            restored = Classifier.from_dict(state)
            np.testing.assert_array_equal(restored.predict_logits(self.X), model.predict_logits(self.X))
            self.assertEqual(restored.to_dict(), state)
            key = next(iter(state["params"]))
            for field, value in (("input_dim", 99), ("n_classes", 1), ("hidden", 5),
                                 ("schema_version", 2), ("l2", -1), ("best_epoch", 99),
                                 ("objective", "unknown")):
                with self.subTest(hidden=hidden, field=field), self.assertRaises(ValueError):
                    bad = copy.deepcopy(state)
                    bad[field] = value
                    Classifier.from_dict(bad)
            for parameters in ({}, {**state["params"], key: [float("nan")]}):
                with self.subTest(hidden=hidden, params=parameters), self.assertRaises(ValueError):
                    bad = copy.deepcopy(state)
                    bad["params"] = parameters
                    Classifier.from_dict(bad)
            bad = copy.deepcopy(state)
            bad["history"][0]["val_nll"] = float("inf")
            with self.assertRaises(ValueError):
                Classifier.from_dict(bad)


class ProbabilityTests(unittest.TestCase):
    def test_softmax_is_stable_at_extreme_logits_and_temperature(self):
        logits = np.array([[1000, -1000, 0], [1e308, 1e308, -1e308], [-1000, -1000, -1000]])
        for temperature in (0.1, 1, 10):
            with self.subTest(temperature=temperature):
                probabilities = softmax(logits, temperature)
                self.assertTrue(np.isfinite(probabilities).all())
                np.testing.assert_allclose(probabilities.sum(axis=1), 1)
                np.testing.assert_allclose(probabilities[1], [0.5, 0.5, 0])
                np.testing.assert_allclose(probabilities[2], [1 / 3] * 3)
        for temperature in (0, -1, np.inf, np.nan):
            with self.subTest(temperature=temperature), self.assertRaises(ValueError):
                softmax([[0, 1]], temperature)
        with self.assertRaises(ValueError):
            softmax([[np.inf, 1]])
        self.assertEqual(softmax(np.empty((0, 3))).shape, (0, 3))

    def test_metric_definitions_support_confusion_and_invalid_label_masking(self):
        probabilities = np.array([[0.8, 0.1, 0.1], [0.1, 0.7, 0.2], [0.1, 0.6, 0.3],
                                  [0.9, 0.05, 0.05], [0.2, 0.5, 0.3]])
        metrics = classification_metrics([0, 1, 2, -1, np.nan], probabilities)
        self.assertEqual(set(metrics), {"accuracy", "macro_f1", "nll", "brier", "confusion", "support"})
        self.assertEqual(metrics["confusion"], [[1, 0, 0], [0, 1, 0], [0, 1, 0]])
        self.assertEqual(metrics["support"], [1, 1, 1])
        self.assertAlmostEqual(metrics["accuracy"], 2 / 3)
        self.assertAlmostEqual(metrics["macro_f1"], 5 / 9)
        self.assertAlmostEqual(metrics["nll"], -np.mean(np.log([0.8, 0.7, 0.3])))
        self.assertAlmostEqual(metrics["brier"], np.mean([0.06, 0.14, 0.86]))
        absent = classification_metrics([0, 0], [[1, 0, 0], [1, 0, 0]])
        self.assertEqual(absent["support"], [2, 0, 0])
        self.assertAlmostEqual(absent["macro_f1"], 1 / 3)
        zero = classification_metrics([1], [[1, 0]])
        self.assertTrue(np.isfinite(zero["nll"]))

    def test_metrics_reject_bad_probabilities_or_no_valid_labels(self):
        for labels, probabilities in (([-1], [[0.5, 0.5]]), ([0], [[0.5, 0.4]]),
                                      ([0], [[np.nan, 1]]), ([0], [[-0.1, 1.1]]),
                                      ([0, 1], [[0.5, 0.5]])):
            with self.subTest(labels=labels, probabilities=probabilities), self.assertRaises(ValueError):
                classification_metrics(labels, probabilities)

    def test_calibration_grid_improves_nll_without_mutating_logits(self):
        logits = np.array([[0, 5.0]] * 4 + [[9000, -9000]])
        labels = np.array([0, 1, 1, 1, np.nan])
        original = logits.copy()
        temperature = fit_temperature(logits, labels)
        self.assertGreater(temperature, 1)
        self.assertLessEqual(temperature, 10)
        calibrated = classification_metrics(labels, softmax(logits, temperature))["nll"]
        uncalibrated = classification_metrics(labels, softmax(logits))["nll"]
        self.assertLess(calibrated, uncalibrated)
        self.assertEqual(temperature, fit_temperature(logits[:4], labels[:4]))
        np.testing.assert_array_equal(logits, original)
        self.assertEqual(fit_temperature(np.zeros((4, 3)), [0, 1, 2, 2]), 1.0)
        with self.assertRaises(ValueError):
            fit_temperature(logits, [-1] * 5)


class AnomalyTests(unittest.TestCase):
    def test_minimum_squared_mahalanobis_matches_hand_calculation(self):
        model = AnomalyModel().fit([[-1], [1], [9], [11]], [0, 0, 1, 1], n_classes=2)
        np.testing.assert_allclose(model.means_, [[0], [10]])
        np.testing.assert_allclose(model.covariances_, [[[2.000002]], [[2.000002]]])
        scores = model.score([[0], [1], [2], [3], [10], [9]])
        np.testing.assert_allclose(scores, np.array([0, 1, 4, 9, 0, 1]) / 2.000002)
        self.assertTrue(np.all(np.diff(scores[:4]) > 0))
        self.assertEqual(model.to_dict()["score_definition"], "minimum_class_squared_mahalanobis")

    def test_constant_columns_single_rows_and_missing_mask_have_finite_scores(self):
        model = AnomalyModel().fit([[0, 0], [10, 0]], [0, 1], n_classes=2, shrinkage=0)
        scores = model.score([[0, 0], [0, 1], [0, 2], [10, 0]])
        self.assertTrue(np.isfinite(scores).all())
        self.assertEqual(scores[0], 0)
        self.assertGreater(scores[1], 0)
        self.assertGreater(scores[2], scores[1])
        self.assertEqual(scores[3], 0)
        self.assertEqual(model.score(np.empty((0, 2))).shape, (0,))

    def test_anomaly_fits_valid_train_subset_and_json_round_trip(self):
        X = np.array([[-1, 0], [1, 1], [9, 0], [11, 1], [100, 0], [-100, 1]])
        model = AnomalyModel().fit(X, [0, 0, 1, 1, -1, np.nan], n_classes=2)
        expected = AnomalyModel().fit(X[:4], [0, 0, 1, 1], n_classes=2)
        self.assertEqual(model.to_dict(), expected.to_dict())
        restored = AnomalyModel.from_dict(json.loads(json.dumps(model.to_dict(), allow_nan=False)))
        np.testing.assert_allclose(restored.score(X), model.score(X), rtol=0, atol=0)
        self.assertEqual(restored.to_dict(), model.to_dict())
        before = copy.deepcopy(model.to_dict())
        model.score([[1000, 1000]])
        self.assertEqual(model.to_dict(), before)

    def test_anomaly_rejects_missing_classes_nonfinite_and_malformed_state(self):
        with self.assertRaises(ValueError):
            AnomalyModel().score([[0]])
        for X, y, kwargs in (([[0], [1]], [0, 0], {"n_classes": 2}),
                            ([[np.nan], [1]], [0, 1], {"n_classes": 2}),
                            ([[0], [1]], [0, 1], {"n_classes": 2, "shrinkage": 1.1}),
                            ([[0], [1]], [-1, np.nan], {"n_classes": 2})):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AnomalyModel().fit(X, y, **kwargs)
        state = AnomalyModel().fit([[0, 0], [1, 1]], [0, 1], n_classes=2).to_dict()
        for key, value in (("class_counts", [0, 1]), ("input_dim", 99),
                           ("covariances", [[[1, 2], [0, 1]], [[1, 0], [0, 1]]]),
                           ("covariances", [[[-1, 0], [0, 1]], [[1, 0], [0, 1]]]),
                           ("score_definition", "accident_probability")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                bad = copy.deepcopy(state)
                bad[key] = value
                AnomalyModel.from_dict(bad)


if __name__ == "__main__":
    unittest.main()
