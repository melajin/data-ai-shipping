"""Numerical parity, leakage, seed sealing, and fixed-comparison checks.

All real fits below use tiny synthetic unit fixtures, never reserved final data.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from fishing_demo.data import SPLITS, generate_dataset
from fishing_demo.models import Classifier, Preprocessor, softmax
from fishing_demo.pipeline import save_json
from tools import critique_comparison_20261027 as runner


def tiny_dataset(seed=731):
    return generate_dataset(seed=seed, groups_per_split={split: 2 for split in SPLITS}, samples_per_class=1)


def metric(score=.4, nll=.8, brier=.5):
    return {"accuracy": score, "macro_f1": score, "nll": nll, "brier": brier,
            "total": 144, "valid": 144, "abstained": 0, "evaluated_labeled": 144,
            "support": [48, 48, 48], "evaluation_row_sha256": "same_rows"}


def records(normal=.7, shift=.4, nll=.8, brier=.5, seeds=runner.DEV_SEEDS):
    return [{"data_seed": seed, "init_seed": init,
             "metrics": {"normal": metric(normal, nll, brier), "shift": metric(shift, nll, brier)}}
            for seed in seeds for init in runner.INIT_SEEDS]


def stage(name, *, normal=.7, shift=.5, nll=.8, brier=.5, formal_selection=True):
    return {"candidate": {"name": name, "formal_selection": formal_selection},
            "summary": runner.summarize_candidate(records(), records(normal, shift, nll, brier))}


class ResearchFitTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(81)
        self.X = rng.normal(size=(37, 6))
        self.X_val = rng.normal(size=(19, 6))
        self.y = rng.integers(0, 3, size=37).astype(float)
        self.y_val = rng.integers(0, 3, size=19).astype(float)
        self.y[[1, 4, 7]] = [np.nan, -1, .5]
        self.y_val[[2, 5, 6]] = [np.inf, 3, -.1]

    def test_exact_existing_400_epoch_semantics_for_both_architectures_and_l2(self):
        for hidden in (0, 16):
            for l2 in (0.0, .001, .01):
                with self.subTest(hidden=hidden, l2=l2):
                    original = Classifier(6, 3, hidden=hidden, l2=l2, seed=42)
                    research = Classifier(6, 3, hidden=hidden, l2=l2, seed=42)
                    expected = original.fit(self.X, self.y, self.X_val, self.y_val, epochs=400)
                    actual = runner.fit_research_classifier(research, self.X, self.y, self.X_val, self.y_val, epochs=400)
                    self.assertEqual(expected, actual)
                    self.assertEqual(original.best_epoch, research.best_epoch)
                    for key in original.params:
                        np.testing.assert_array_equal(original.params[key], research.params[key])

    def test_extended_fit_has_exact_400_prefix_without_lifting_original_cap(self):
        X = np.array([[-2., -1.], [-1., -2.], [2., -1.], [1., -2.], [0., 2.], [1., 2.]])
        y = np.array([0, 0, 1, 1, 2, 2])
        original = Classifier(2, 3, hidden=16, l2=0, seed=137)
        reference = original.fit(X, y, X, y, epochs=400)
        extended = Classifier(2, 3, hidden=16, l2=0, seed=137)
        history = runner.fit_research_classifier(extended, X, y, X, y, epochs=1200)
        self.assertEqual(len(reference), 400)
        self.assertEqual(len(history), 1200)
        self.assertEqual(reference, history[:400])
        self.assertEqual(extended.best_epoch, 1200)
        self.assertLess(history[-1]["val_nll"], reference[-1]["val_nll"])
        with self.assertRaisesRegex(ValueError, "must not exceed 400"):
            original.fit(X, y, X, y, epochs=401)
        with self.assertRaisesRegex(ValueError, "must not exceed 1200"):
            runner.fit_research_classifier(extended, X, y, X, y, epochs=1201)

    def test_validation_checkpoint_is_restored_after_exact_patience(self):
        X, y, y_val = np.ones((4, 1)), np.zeros(4), np.ones(4)
        model = Classifier(1, 3, hidden=0, l2=0)
        for value in model.params.values():
            value.fill(0)
        one_epoch = copy.deepcopy(model)
        runner.fit_research_classifier(one_epoch, X, y, X, y_val, epochs=1)
        history = runner.fit_research_classifier(model, X, y, X, y_val, epochs=100, patience=3)
        self.assertEqual(model.best_epoch, 1)
        self.assertEqual(len(history), 4)
        self.assertGreater(history[-1]["val_nll"], history[0]["val_nll"])
        for key in model.params:
            np.testing.assert_array_equal(model.params[key], one_epoch.params[key])

    def test_training_error_restores_original_parameters(self):
        model = Classifier(6, 3, hidden=16)
        before = {key: value.copy() for key, value in model.params.items()}
        original_gradient = model.loss_and_gradients
        calls = []

        def gradient(X, y):
            calls.append(1)
            if len(calls) == 2:
                raise ValueError("injected gradient failure")
            return original_gradient(X, y)

        with patch.object(model, "loss_and_gradients", side_effect=gradient):
            with self.assertRaisesRegex(ValueError, "injected gradient"):
                runner.fit_research_classifier(model, self.X, self.y, self.X_val, self.y_val)
        for key in before:
            np.testing.assert_array_equal(model.params[key], before[key])

    def test_extended_state_round_trip_and_history_validation(self):
        X, y = np.array([[-1.], [0.], [1.]]), np.arange(3)
        model = Classifier(1, 3, hidden=0, l2=.01)
        runner.fit_research_classifier(model, X, y, X, y, epochs=401)
        state = json.loads(json.dumps(model.to_dict(), allow_nan=False))
        self.assertEqual(len(state["history"]), 401)
        restored = runner.research_classifier_from_dict(state)
        np.testing.assert_array_equal(model.predict_logits(X), restored.predict_logits(X))
        with self.assertRaisesRegex(ValueError, "at most 400"):
            Classifier.from_dict(state)
        for mutation in ("bad_epoch", "bad_best", "bad_objective", "nonfinite"):
            modified = copy.deepcopy(state)
            if mutation == "bad_epoch":
                modified["history"][1]["epoch"] = 3
            elif mutation == "bad_best":
                modified["best_epoch"] = 1
            elif mutation == "bad_objective":
                modified["history"][0]["train_objective"] = 0
            else:
                modified["history"][0]["val_nll"] = float("nan")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runner.research_classifier_from_dict(modified)

    def test_history_endpoint_diagnostic_does_not_claim_underfit(self):
        model = Classifier(1, 3, hidden=0)
        runner.fit_research_classifier(model, [[-1.], [0.], [1.]], [0, 1, 2], [[-1.], [0.], [1.]], [0, 1, 2], epochs=5)
        diagnostic = runner.history_diagnostics(model, 5)
        self.assertEqual(diagnostic["stopping_reason"], "epoch_budget")
        self.assertIsNone(diagnostic["epoch_400"])
        self.assertTrue(diagnostic["last_epoch_validation_nll_decreased"])
        self.assertIn("does not prove", diagnostic["interpretation"])


class AggregationSelectionTests(unittest.TestCase):
    def test_initializations_average_within_seed_before_comparison(self):
        changed = records(normal=.695, shift=.46)
        changed[0]["metrics"]["shift"]["macro_f1"] = .7
        changed[1]["metrics"]["shift"]["macro_f1"] = .3
        result = runner.summarize_candidate(records(), changed)
        self.assertAlmostEqual(result["per_seed"][0]["shift"]["delta"], .1)
        self.assertAlmostEqual(result["normal_mean_delta"], -.005)
        self.assertAlmostEqual(result["shift_mean_delta"], (.1 + .06 + .06) / 3)
        self.assertEqual(result["positive_shift_seeds"], 3)
        self.assertTrue(result["eligible"])

    def test_all_seed_gains_normal_retention_and_denominators_are_required(self):
        baseline = records()
        cases = []
        changed = records(shift=.6)
        for row in changed[:2]:
            row["metrics"]["shift"]["macro_f1"] = .39
        cases.append(changed)
        cases.append(records(normal=.68, shift=.6))
        cases.append(records(shift=.44))
        changed = records(shift=.6)
        changed[0]["metrics"]["normal"]["evaluation_row_sha256"] = "different"
        cases.append(changed)
        changed = records(shift=.6)
        changed[0]["metrics"]["normal"]["support"] = [47, 49, 48]
        cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed[0]):
                self.assertFalse(runner.summarize_candidate(baseline, changed)["eligible"])

    def test_missing_duplicate_and_nonfinite_metrics_are_explicit_errors(self):
        baseline, changed = records(), records(shift=.5)
        with self.assertRaisesRegex(ValueError, "every prespecified"):
            runner.summarize_candidate(baseline, changed[:-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            runner.summarize_candidate(baseline, changed + [changed[0]])
        changed[0]["metrics"]["normal"]["nll"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            runner.summarize_candidate(baseline, changed)

    def test_final_schedule_aggregation_is_supported_without_generating_data(self):
        baseline = records(seeds=runner.RESERVED_FINAL_SEEDS)
        changed = records(shift=.5, seeds=runner.RESERVED_FINAL_SEEDS)
        result = runner.summarize_candidate(baseline, changed, seeds=runner.RESERVED_FINAL_SEEDS, positive_seed_min=8)
        self.assertEqual(result["seed_count"], 10)
        self.assertEqual(result["positive_shift_seeds"], 10)
        self.assertTrue(result["eligible"])

    def test_selection_priority_tolerance_declaration_order_and_runtime_exclusion(self):
        first = stage("first")
        same = stage("second")
        first["timing_seconds"], same["timing_seconds"] = 1000., .0001
        self.assertEqual(runner.select_candidate([first, same])["name"], "first")
        tolerance = stage("within_tolerance", shift=.5 + .5e-12)
        self.assertEqual(runner.select_candidate([first, tolerance])["name"], "first")
        for changed in (stage("shift", shift=.51, normal=.695, nll=2, brier=2),
                        stage("normal", normal=.71, nll=2, brier=2),
                        stage("nll", nll=.7, brier=2), stage("brier", brier=.4)):
            with self.subTest(name=changed["candidate"]["name"]):
                self.assertEqual(runner.select_candidate([first, changed])["name"], changed["candidate"]["name"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            runner.select_candidate([first, first])

    def test_dt_only_is_displayed_but_excluded_from_formal_selection(self):
        good = stage("geometry")
        dt = stage("dt_only", normal=.99, shift=.99, formal_selection=False)
        self.assertTrue(dt["summary"]["eligible"])
        self.assertEqual(runner.select_candidate([good, dt])["name"], "geometry")
        self.assertIsNone(runner.select_candidate([dt]))


class DatasetAndInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = tiny_dataset()

    def test_family_dimensions_shared_train_preprocessor_and_input_preservation(self):
        before = copy.deepcopy(self.dataset)
        prepared = runner.prepare_dataset(self.dataset, 731)
        for family, dimensions in (("shape9", 9), ("shape9_simtime4", 13), ("shape9_edge3", 12), ("shape9_dt_only", 10)):
            with self.subTest(family=family):
                family_data = runner.prepare_family(prepared, family)
                self.assertIs(family_data, runner.prepare_family(prepared, family))
                self.assertEqual(family_data["X"].shape, (30, dimensions))
                self.assertEqual(family_data["Z"]["train"].shape, (6, dimensions * 2))
                expected = Preprocessor().fit(family_data["X"][prepared["indices"]["train"]]).to_dict()
                self.assertEqual(family_data["preprocessor"].to_dict(), expected)
        self.assertEqual(self.dataset, before)
        all_groups = prepared["groups"]
        self.assertEqual(sum(len(group) for group in all_groups.values()), len(set().union(*all_groups.values())))

    def test_fit_roles_serialize_all_fixed_models_and_keep_abstentions(self):
        dataset = copy.deepcopy(self.dataset)
        invalid = copy.deepcopy(next(row for row in dataset["records"] if row["split"] == "test"))
        invalid.update(sample_id=invalid["sample_id"] + "-invalid", parts=[[[0., 0.], [0., 0.]]],
                       sim_times=[[0., 1.]], quality={})
        dataset["records"].append(invalid)
        prepared = runner.prepare_dataset(dataset, 731)
        expected_train = prepared["y"][prepared["indices"]["train"]]
        expected_val = prepared["y"][prepared["indices"]["validation"]]
        expected_cal = prepared["y"][prepared["indices"]["calibration"]]
        original_fit, original_temperature, original_logits = Classifier.fit, runner.fit_temperature, runner._logits
        fit_calls, temperature_calls = [], []
        latest_logits_input = {}
        dimensions_to_family = {2 * len(runner.feature_names(family)): family
                                for family in runner.TRAINING_PROCEDURE["feature_families"]}

        def checked_fit(model, X, y, X_val, y_val, **kwargs):
            np.testing.assert_array_equal(y, expected_train)
            np.testing.assert_array_equal(y_val, expected_val)
            family = dimensions_to_family[model.input_dim]
            np.testing.assert_array_equal(X, prepared["family_cache"][family]["Z"]["train"])
            np.testing.assert_array_equal(X_val, prepared["family_cache"][family]["Z"]["validation"])
            fit_calls.append(1)
            return original_fit(model, X, y, X_val, y_val, **kwargs)

        def checked_logits(model, backend, Z):
            latest_logits_input.update(model=model, Z=Z.copy())
            return original_logits(model, backend, Z)

        def checked_temperature(logits, y):
            np.testing.assert_array_equal(y, expected_cal)
            self.assertEqual(logits.shape, (6, 3))
            model = latest_logits_input["model"]
            input_dim = model.input_dim if isinstance(model, Classifier) else model.n_features_in_
            family = dimensions_to_family[input_dim]
            np.testing.assert_array_equal(latest_logits_input["Z"], prepared["family_cache"][family]["Z"]["calibration"])
            temperature_calls.append(1)
            return original_temperature(logits, y)

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(Classifier, "fit", autospec=True, side_effect=checked_fit), \
                 patch.object(runner, "_logits", side_effect=checked_logits), \
                 patch.object(runner, "fit_temperature", side_effect=checked_temperature):
                outputs = [runner._fit_one(prepared, config, 731, 42, out, {}, phase="final")
                           for config in (runner.BASELINE, *runner.CANDIDATES)]
            self.assertEqual(len(fit_calls), 4)  # Baseline and three 400-epoch timing/control models.
            self.assertEqual(len(temperature_calls), 9)
            for config, result in zip((runner.BASELINE, *runner.CANDIDATES), outputs):
                with self.subTest(candidate=config["name"]):
                    self.assertEqual(result["metrics"]["normal"]["total"], 7)
                    self.assertEqual(result["metrics"]["normal"]["abstained"], 1)
                    self.assertEqual(result["metrics"]["normal"]["support"], [2, 2, 2])
                    self.assertEqual(result["metrics"]["normal"]["evaluation_role"], "final_normal")
                    self.assertTrue(result["reload_raw_and_calibrated_probabilities_identical"])
                    bundle = runner.load_bundle(out / result["model_path"], trusted_local=True)
                    probabilities, valid = runner.predict_bundle(bundle, dataset)
                    self.assertFalse(valid[-1])
                    self.assertTrue(np.isnan(probabilities[-1]).all())
                    np.testing.assert_allclose(probabilities[valid].sum(axis=1), 1)
                    prediction_rows = json.loads((out / result["predictions_path"]).read_text(encoding="utf-8"))
                    abstained = [row for row in prediction_rows if row["status"] == "abstained"]
                    self.assertEqual(len(abstained), 1)
                    self.assertIsNone(abstained[0]["probabilities"])
            baseline, extended = outputs[:2]
            self.assertEqual(baseline["history"], extended["history"][:len(baseline["history"])])
            base_bundle = runner.load_bundle(out / baseline["model_path"])
            changed = copy.deepcopy(dataset)
            for row in changed["records"]:
                row["label"] = (row["label"] + 1) % 3
                row["sample_id"] += "-renamed"
                row["vessel_id"] += "-renamed"
                row["quality"] = {"comment": "unused"}
                row["sim_times"] = [[instant * 2 for instant in part] for part in row["sim_times"]]
            before, mask = runner.predict_bundle(base_bundle, dataset)
            after, changed_mask = runner.predict_bundle(base_bundle, changed)
            np.testing.assert_array_equal(mask, changed_mask)
            np.testing.assert_array_equal(before, after)

    def test_tree_pickle_needs_trust_and_integrity_before_unpickle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tree.json"
            path.with_suffix(".pkl").write_bytes(b"not_a_pickle")
            save_json(path, {"schema_version": runner.MODEL_SCHEMA, "config": {"backend": "extratrees"},
                             "classifier": {"format": "trusted_self_generated_pickle", "file": "tree.pkl", "sha256": "wrong"}})
            with patch.object(runner.pickle, "load", side_effect=AssertionError("must not unpickle")) as load:
                with self.assertRaisesRegex(ValueError, "trusted_local"):
                    runner.load_bundle(path)
                with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                    runner.load_bundle(path, trusted_local=True)
                load.assert_not_called()


class ProtocolGateTests(unittest.TestCase):
    def test_only_fresh_dev_seeds_generate_after_protocol_and_sources_are_sealed(self):
        sources = {"fixture": "hash"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            save_json(path, runner.protocol_payload(sources, started_at="unit_fixture"))
            with patch.object(runner, "source_hashes", return_value=sources):
                gate = runner.DevelopmentSeedGate(path, sources)
                self_fixture = tiny_dataset()
                with patch.object(runner, "generate_dataset", return_value=self_fixture) as generate:
                    for forbidden in (42, 1101, *runner.RETIRED_FINAL_SEEDS, *runner.RESERVED_FINAL_SEEDS):
                        with self.subTest(seed=forbidden), self.assertRaisesRegex(ValueError, "only prespecified"):
                            gate.get(forbidden)
                    generate.assert_not_called()
                    prepared = gate.get(2101)
                    self.assertIs(prepared, gate.get(2101))
                    generate.assert_called_once_with(seed=2101)
                    self.assertEqual(prepared["dataset"], self_fixture)
                    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "changed"):
                        gate.get(2101)
                    self.assertEqual(generate.call_count, 1)

    def test_changed_protocol_settings_cannot_create_a_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            payload = runner.protocol_payload({}, started_at="unit_fixture")
            payload["candidates"][0]["settings"]["epochs"] = 10
            save_json(path, payload)
            with patch.object(runner, "source_hashes", return_value={}):
                with self.assertRaisesRegex(ValueError, "differs from"):
                    runner.DevelopmentSeedGate(path, {})

    def test_development_runs_every_candidate_preserves_old_output_and_never_final(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT / "outputs", prefix="critique-unit-") as directory:
            out = Path(directory) / "new"
            generated = []

            def generated_fixture(*, seed):
                self.assertTrue((out / "protocol.json").is_file())
                self.assertTrue((out / "protocol.sha256").is_file())
                generated.append(seed)
                return tiny_dataset(seed)

            def fake_fit(prepared, config, data_seed, init_seed, output, sources, phase="development"):
                self.assertEqual(phase, "development")
                row = records()[runner.DEV_SEEDS.index(data_seed) * 2 + runner.INIT_SEEDS.index(init_seed)]
                row.update(candidate=config["name"], preprocessor_sha256=config["family"],
                           reload_raw_and_calibrated_probabilities_identical=True)
                return row

            with patch.object(runner, "SOURCE_FILES", ()), patch.object(runner, "source_hashes", return_value={}), \
                 patch.object(runner, "generate_dataset", side_effect=generated_fixture), \
                 patch.object(runner, "_fit_one", side_effect=fake_fit):
                result = runner.run(out)
            self.assertEqual(generated, list(runner.DEV_SEEDS))
            self.assertEqual(len(result["stage_results"]), 9)
            self.assertTrue(all(len(stage["records"]) == 6 for stage in result["stage_results"]))
            self.assertIsNone(result["selected_development_candidate"])
            self.assertFalse(result["final"]["executed"])
            self.assertFalse(result["final"]["generated"])
            self.assertTrue(all(result["checks"].values()))
            sentinel = out / "preserve.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be empty"):
                runner._prepare_output(out)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
