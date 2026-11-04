"""Lightweight checks for iteration gates, paired aggregation and frozen inference."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from fishing_demo.data import generate_dataset
from fishing_demo.iteration_features import feature_names, feature_units
from fishing_demo.models import Classifier, Preprocessor
from fishing_demo.pipeline import save_json
from tools import run_iterative_models as runner


def metric(score):
    return {"macro_f1": score, "total": 144, "valid": 144, "abstained": 0,
            "evaluated_labeled": 144, "support": [48, 48, 48], "evaluation_row_sha256": "same_rows"}


def records(seeds=runner.DEV_SEEDS, normal=.7, shift=.4):
    return [{"data_seed": seed, "init_seed": init,
             "metrics": {"normal": metric(normal), "shift": metric(shift)}}
            for seed in seeds for init in runner.INIT_SEEDS]


def frozen_bundle(family="shape7"):
    count = len(feature_names(family))
    preprocessor = {"type": "preprocessor", "schema_version": 1,
        "n_features": count, "medians": [0.] * count, "means": [0.] * count,
        "scales": [1.] * count, "all_missing": [False] * count,
        "output_order": "scaled_features_then_missing_mask"}
    config = runner.candidate(f"{family}_mlp", family)
    return {"schema_version": runner.MODEL_SCHEMA, "source_type": "synthetic", "coordinate_system": "local_xy_m",
        "class_names": runner.CLASS_NAMES, "config": config, "data_seed": 1101, "init_seed": 42,
        "feature_names": list(feature_names(family)), "feature_units": list(feature_units(family)),
        "preprocessor": preprocessor, "classifier": Classifier(count * 2, 3, hidden=16, l2=0, seed=42).to_dict(),
        "temperature": 1.3}


def freeze_payload(sources, protocol_hash):
    return {"schema_version": "fishing_iteration_freeze_v1", "source_sha256": sources,
        "protocol_sha256": protocol_hash, "selected_config": runner.ROUNDS[0][0],
        "baseline_config": runner.BASELINE, "training_procedure": runner.TRAINING_PROCEDURE,
        "final_data_seeds": list(runner.FINAL_SEEDS), "init_seeds": list(runner.INIT_SEEDS),
        "model_fixture": {"data_seed": 9101, "init_seed": 42}}


class PairedAggregationTests(unittest.TestCase):
    def test_initializations_are_averaged_before_generator_seed_comparison(self):
        baseline = records()
        changed = records(normal=.695, shift=.46)
        # One seed has discordant initializations; its pair averages to zero.
        changed[0]["metrics"]["shift"]["macro_f1"] = .6
        changed[1]["metrics"]["shift"]["macro_f1"] = .2
        changed[2]["metrics"]["shift"]["macro_f1"] = .56
        changed[3]["metrics"]["shift"]["macro_f1"] = .56
        summary = runner.paired_summary(baseline, changed)
        self.assertAlmostEqual(summary["per_seed"][0]["shift"]["delta"], 0)
        self.assertAlmostEqual(summary["normal_mean_delta"], -.005)
        self.assertAlmostEqual(summary["shift_mean_delta"], .068)
        self.assertEqual(summary["positive_shift_seeds"], 4)
        self.assertTrue(summary["eligible"])

    def test_denominator_and_row_identity_difference_rejects_candidate(self):
        baseline, changed = records(), records(shift=.5)
        changed[0]["metrics"]["normal"]["evaluation_row_sha256"] = "other_rows"
        summary = runner.paired_summary(baseline, changed)
        self.assertFalse(summary["conditions"]["same_denominators"])
        self.assertFalse(summary["eligible"])

    def test_macro_f1_gain_and_positive_seed_count_are_both_required(self):
        baseline, changed = records(), records(shift=.41)
        self.assertFalse(runner.paired_summary(baseline, changed)["eligible"])
        # Very large improvements in only three seeds cannot meet consistency.
        changed = records(shift=.39)
        for row in changed[:6]:
            row["metrics"]["shift"]["macro_f1"] = .8
        summary = runner.paired_summary(baseline, changed)
        self.assertGreater(summary["shift_mean_delta"], .05)
        self.assertEqual(summary["positive_shift_seeds"], 3)
        self.assertFalse(summary["eligible"])

    def test_missing_or_duplicate_seed_initialization_is_an_error(self):
        baseline, changed = records(), records(shift=.5)
        with self.assertRaisesRegex(ValueError, "every preregistered"):
            runner.paired_summary(baseline, changed[:-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            runner.paired_summary(baseline, changed + [changed[0]])

    def test_final_bootstrap_uses_ten_generator_seed_means_and_is_reproducible(self):
        baseline = records(runner.FINAL_SEEDS)
        changed = records(runner.FINAL_SEEDS, normal=.7, shift=.5)
        first = runner.paired_summary(baseline, changed, final=True)
        self.assertEqual(first, runner.paired_summary(baseline, changed, final=True))
        self.assertEqual(first["seed_count"], 10)
        self.assertEqual(len(first["per_seed"]), 10)
        self.assertEqual(first["shift_paired_bootstrap95"]["repetitions"], 2000)
        self.assertAlmostEqual(first["shift_paired_bootstrap95"]["low"], .1)
        self.assertTrue(first["success"])

    def test_final_consistency_requires_eight_of_ten_seeds(self):
        baseline = records(runner.FINAL_SEEDS)
        changed = records(runner.FINAL_SEEDS, shift=.39)
        for row in changed[:14]:
            row["metrics"]["shift"]["macro_f1"] = .6
        summary = runner.paired_summary(baseline, changed, final=True)
        self.assertEqual(summary["positive_shift_seeds"], 7)
        self.assertFalse(summary["success"])


class SeedGateTests(unittest.TestCase):
    def setUp(self):
        self.sources = runner.source_hashes()
        self.protocol_hash = runner.sha256(runner.PROTOCOL_PATH)

    def test_final_generator_is_not_called_before_freeze(self):
        gate = runner.SeedGate(self.sources, self.protocol_hash)
        with patch.object(runner, "generate_dataset", side_effect=AssertionError("must not generate")) as generate:
            with self.assertRaisesRegex(ValueError, "forbidden before freeze"):
                gate.get(9101)
            with self.assertRaisesRegex(ValueError, "outside"):
                gate.get(42)
            generate.assert_not_called()

    def test_valid_freeze_unlocks_and_then_any_freeze_mutation_blocks_generation(self):
        gate = runner.SeedGate(self.sources, self.protocol_hash)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "freeze.json"
            payload = freeze_payload(self.sources, self.protocol_hash)
            save_json(path, payload)
            gate.unlock_final(path)
            # A development fixture stands in for the generator: no final data is generated by this test.
            fixture = generate_dataset(seed=1101, groups_per_split={s: 2 for s in runner.SPLITS}, samples_per_class=1)
            with patch.object(runner, "generate_dataset", return_value=fixture) as generate:
                gate.get(9101)
                gate.get(9101)
                generate.assert_called_once_with(seed=9101)
                self.assertEqual(gate.calls[0]["phase"], "final")
                payload["model_fixture"]["init_seed"] = 137
                save_json(path, payload)
                with self.assertRaisesRegex(ValueError, "changed"):
                    gate.get(9102)
                self.assertEqual(generate.call_count, 1)

    def test_invalid_source_or_candidate_cannot_unlock_final(self):
        gate = runner.SeedGate(self.sources, self.protocol_hash)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "freeze.json"
            payload = freeze_payload(self.sources, self.protocol_hash)
            payload["source_sha256"] = {}
            save_json(path, payload)
            with self.assertRaisesRegex(ValueError, "source changed"):
                gate.unlock_final(path)
            payload = freeze_payload(self.sources, self.protocol_hash)
            payload["selected_config"] = {"name": "unregistered"}
            save_json(path, payload)
            with self.assertRaisesRegex(ValueError, "preregistered"):
                gate.unlock_final(path)


class FrozenInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = generate_dataset(seed=1101, groups_per_split={s: 1 for s in runner.SPLITS}, samples_per_class=1)["records"]

    def test_saved_inference_uses_no_fit_and_no_label_identifier_time_or_quality_features(self):
        bundle = frozen_bundle()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            save_json(path, bundle)
            with patch.object(Classifier, "fit", side_effect=AssertionError("fit forbidden")), \
                 patch.object(Preprocessor, "fit", side_effect=AssertionError("fit forbidden")):
                original, mask = runner.predict_bundle(runner.load_iteration_model(path), self.rows)
                changed = copy.deepcopy(self.rows)
                for row in changed:
                    row["label"] = (row["label"] + 1) % 3
                    row["sample_id"] += "-changed"
                    row["vessel_id"] += "-changed"
                    row["quality"] = {"unrelated": "value"}
                    row["split"] = "stress" if row["split"] != "stress" else "train"
                    row["scenario"] = "shift" if row["split"] == "stress" else "base"
                    row["sim_times"] = [[float(instant * 100) for instant in part] for part in row["sim_times"]]
                probabilities, changed_mask = runner.predict_bundle(bundle, changed)
            np.testing.assert_array_equal(original, probabilities)
            np.testing.assert_array_equal(mask, changed_mask)
            np.testing.assert_allclose(probabilities.sum(axis=1), 1)

    def test_original_validity_mask_is_shared_by_feature_families(self):
        row = copy.deepcopy(self.rows[0])
        row["parts"] = [[[0., 0.], [0., 0.]]]
        row["sim_times"] = [[0., 1.]]
        row["quality"] = {}
        masks = []
        for family in ("original8", "shape7", "shape9", "shape15"):
            probabilities, mask = runner.predict_bundle(frozen_bundle(family), [self.rows[0], row])
            self.assertEqual(mask.tolist(), [True, False])
            self.assertTrue(np.isnan(probabilities[1]).all())
            masks.append(mask)
        for mask in masks[1:]:
            np.testing.assert_array_equal(mask, masks[0])

    def test_feature_order_units_and_temperature_tampering_are_rejected(self):
        for key, value in (("feature_names", ["wrong"]), ("feature_units", ["wrong"]), ("temperature", 0)):
            bundle = frozen_bundle()
            bundle[key] = value
            with self.assertRaises(ValueError):
                runner.predict_bundle(bundle, self.rows)

    def test_tree_loading_requires_explicit_trust_and_integrity_before_unpickle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.with_suffix(".pkl").write_bytes(b"not-a-pickle")
            payload = {"schema_version": runner.MODEL_SCHEMA, "config": {"backend": "extratrees"},
                "classifier": {"format": "trusted_self_generated_pickle", "file": "model.pkl", "sha256": "wrong"}}
            save_json(path, payload)
            with patch.object(runner.pickle, "load", side_effect=AssertionError("must not unpickle")) as load:
                with self.assertRaisesRegex(ValueError, "trusted_local"):
                    runner.load_iteration_model(path)
                with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                    runner.load_iteration_model(path, trusted_local=True)
                load.assert_not_called()


class BoundedRunTests(unittest.TestCase):
    def test_first_round_eligibility_stops_development_and_final_failure_never_restarts_search(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT / "outputs", prefix="iteration-unit-") as directory:
            out = Path(directory) / "new"
            calls = []

            def fake_fit(config, seeds, gate, output, sources, phase):
                calls.append((config["name"], tuple(seeds), phase))
                score = .4 if config["name"] == runner.BASELINE["name"] else (.5 if phase == "development" else .39)
                rows = records(seeds, shift=score)
                for row in rows:
                    row["reload_predictions_identical"] = True
                return rows

            with patch.object(runner, "_run_config", side_effect=fake_fit), \
                 patch.object(runner, "generate_dataset", side_effect=AssertionError("fitting is stubbed")):
                result = runner.run(out)
            self.assertEqual(result["selected_candidate"]["name"], "shape7_mlp")
            self.assertTrue((out / "freeze.json").exists())
            self.assertTrue(result["final"]["executed"])
            self.assertFalse(result["final"]["success"])
            self.assertEqual(result["outcome"], "final_improvement_not_confirmed")
            self.assertEqual([(name, phase) for name, _, phase in calls], [
                ("original8_mlp", "development"), ("shape7_mlp", "development"),
                ("original8_mlp", "final"), ("shape7_mlp", "final")])

    def test_no_eligible_candidate_stops_without_any_final_generation(self):
        # Stub model fitting, while exercising the real bounded control flow.
        with tempfile.TemporaryDirectory(dir=runner.ROOT / "outputs", prefix="iteration-unit-") as directory:
            out = Path(directory) / "new"
            calls = []

            def fake_fit(config, seeds, gate, output, sources, phase):
                calls.append((config["name"], tuple(seeds), phase))
                rows = records(seeds)
                for row in rows:
                    row["reload_predictions_identical"] = True
                return rows

            with patch.object(runner, "_run_config", side_effect=fake_fit), \
                 patch.object(runner, "generate_dataset", side_effect=AssertionError("no generation expected")):
                result = runner.run(out)
            self.assertEqual(result["outcome"], "no_development_candidate_eligible")
            self.assertIsNone(result["selected_candidate"])
            self.assertFalse(result["final"]["executed"])
            self.assertFalse((out / "freeze.json").exists())
            self.assertEqual(len(calls), 6)
            self.assertTrue(all(seeds == runner.DEV_SEEDS and phase == "development" for _, seeds, phase in calls))
            self.assertTrue(all(result["checks"].values()))

    def test_nonempty_output_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT / "outputs", prefix="iteration-unit-") as directory:
            sentinel = Path(directory) / "earlier_evidence.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be empty"):
                runner._prepare_output(directory)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
