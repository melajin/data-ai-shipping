"""Contract tests for the frozen real-vessel model-cycle runner."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from fishing_demo.real_model_cycle_20261028 import (
    R2_TREES,
    _evaluate_final_after_freeze,
    _development_splits,
    _fit_one,
    _probability_metrics,
    _best_candidate,
    _stratified_final_split,
    _validate_roster,
    run_cycle,
)


def _vessels(per_class=10, labels=("A", "B", "C")):
    result = []
    for label_index, label in enumerate(labels):
        for vessel_number in range(per_class):
            value = float(label_index + vessel_number / 100)
            result.append({
                "vessel_hash": f"h-{label}-{vessel_number:03d}",
                "label": label,
                "rows": [{"file_ordinal": 0, "record_ordinal": vessel_number,
                          "month": 2, "valid": True, "reason": None,
                          "values": [value, 0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 1.0],
                          "degree_control_values": [value, 0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 1.0]}],
            })
    return result


class RealModelCycleTests(unittest.TestCase):
    def test_seeded_split_is_deterministic_disjoint_and_has_required_minima(self):
        roster = _validate_roster(_vessels(), ["A", "B", "C"])
        final_a, dev_a, _ = _stratified_final_split(roster, ["A", "B", "C"])
        final_b, dev_b, _ = _stratified_final_split(roster, ["A", "B", "C"])
        self.assertEqual(final_a, final_b)
        self.assertEqual(dev_a, dev_b)
        self.assertFalse(set(final_a) & set(dev_a))
        self.assertEqual(len(final_a), 6)
        splits = _development_splits([v for v in roster if v["vessel_hash"] in set(dev_a)],
                                     ["A", "B", "C"])
        for split in splits.values():
            self.assertEqual([len(split[k]) for k in ("train", "validation", "calibration")],
                             [12, 6, 6])
            for label in ("A", "B", "C"):
                for role in split:
                    self.assertEqual(sum(next(v["label"] for v in roster
                                              if v["vessel_hash"] == h) == label
                                         for h in split[role]), 2 if role != "train" else 4)

    def test_selection_uses_absolute_nll_when_f1_delta_is_within_tolerance(self):
        means = {"distribution36_mlp16": {"nll": 0.70},
                 "distribution36_linear": {"nll": 0.60},
                 "distribution36_extratrees256_leaf2": {"nll": 0.5}}
        deltas = {"distribution36_mlp16": {"macro_f1": 0.0300000000000},
                  "distribution36_linear": {"macro_f1": 0.0300000000008},
                  "distribution36_extratrees256_leaf2": {"macro_f1": 0.031}}
        self.assertEqual(_best_candidate(list(means)[:2], means, deltas),
                         "distribution36_linear")
        self.assertEqual(_best_candidate(list(means), means, deltas),
                         "distribution36_extratrees256_leaf2")

    def test_duplicate_vessel_hash_is_rejected(self):
        vessels = _vessels()
        vessels[1]["vessel_hash"] = vessels[0]["vessel_hash"]
        with self.assertRaisesRegex(ValueError, "unique"):
            _validate_roster(vessels, ["A", "B", "C"])

    def test_extratrees_fits_after_masking_zero_feature_training_ship(self):
        train_x = np.asarray([[0.0, 1.0], [0.2, 1.0], [np.nan, np.nan],
                              [1.0, 0.0], [1.2, 0.0]])
        train_y = np.asarray([0, 0, 1, 1, 1])
        val_x = np.asarray([[0.1, 1.0], [1.1, 0.0]])
        val_y = np.asarray([0, 1])
        cal_x = np.asarray([[0.05, 1.0], [1.05, 0.0]])
        cal_y = np.asarray([0, 1])
        fit = _fit_one(R2_TREES, 42, train_x, train_y, val_x, val_y, cal_x, cal_y, 2)
        self.assertEqual(fit["validation_probabilities"].shape, (2, 2))
        self.assertGreater(fit["temperature"], 0)
        self.assertEqual(fit["state"]["estimator_kind"], "pickle")

    def test_final_gate_checks_freeze_candidate_before_loading_final_rows(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            freeze = Path(temp) / "freeze.json"
            freeze.write_text(json.dumps({"selection": {"candidate": "fixed"}}), encoding="utf-8")
            loader_called = []
            with self.assertRaisesRegex(ValueError, "frozen selection"):
                _evaluate_final_after_freeze(freeze, "changed", {}, [], ["A", "B"], Path(temp),
                                             lambda hashes: loader_called.append(hashes))
            self.assertEqual(loader_called, [])

    def test_existing_freeze_blocks_a_second_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "freeze.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "already frozen"):
                run_cycle([], Path(temp), {})

    def test_abstentions_leave_primary_probability_metrics_on_shared_scorable_rows(self):
        y = np.asarray([0, 1, 2])
        probs = np.asarray([[0.8, 0.1, 0.1], [1 / 3, 1 / 3, 1 / 3],
                            [0.1, 0.1, 0.8]])
        metrics = _probability_metrics(y, probs, np.asarray([False, True, False]), 3)
        self.assertEqual(metrics["denominator"], 3)
        self.assertEqual(metrics["probability_metric_denominator"], 2)
        self.assertAlmostEqual(metrics["coverage"], 2 / 3)
        self.assertAlmostEqual(metrics["accuracy"], 1.0)
        self.assertAlmostEqual(metrics["full_roster_accuracy"], 2 / 3)
        self.assertEqual(metrics["abstain_count"], 1)

    def test_runner_persists_freeze_before_entering_final_evaluation_gate(self):
        vessels = _vessels()
        protocol = {"class_names": ["A", "B", "C"], "source_hash": "scanner-sha256"}
        fake_dev = {"selection": {"candidate": "distribution36_mlp16",
                                  "confirmatory_candidate": True,
                                  "eligible_candidates": ["distribution36_mlp16"]},
                    "model_audit": {}}

        def checked_final_gate(freeze_path, candidate, roster_by_hash, final_hashes,
                               class_names, output_dir, final_loader=None):
            self.assertTrue(Path(freeze_path).is_file())
            self.assertEqual(candidate, "distribution36_mlp16")
            self.assertEqual(json_load(freeze_path)["selection"]["candidate"], candidate)
            return {"success_criteria_passed": False, "confirmatory": True}

        with tempfile.TemporaryDirectory() as temp, \
                patch("fishing_demo.real_model_cycle_20261028._evaluate_development",
                      return_value=(fake_dev, "distribution36_mlp16")), \
                patch("fishing_demo.real_model_cycle_20261028._evaluate_final_after_freeze",
                      side_effect=checked_final_gate):
            result = run_cycle(vessels, Path(temp), protocol)
            self.assertTrue((Path(temp) / "freeze.json").exists())
            self.assertTrue((Path(temp) / "split_manifest.json").exists())
            self.assertTrue((Path(temp) / "protocol.json").exists())
            self.assertTrue((Path(temp) / "development_results.json").exists())
            self.assertTrue((Path(temp) / "results.json").exists())
            self.assertTrue((Path(temp) / "run_evidence.json").exists())
            self.assertTrue((Path(temp) / "source_snapshot" / "models.py").exists())
            evidence = json_load(Path(temp) / "run_evidence.json")
            self.assertEqual(evidence["source_file_hashes"], evidence["source_snapshot_hashes"])
            self.assertEqual(result["selected_candidate"], "distribution36_mlp16")

    def test_runner_accepts_four_declared_real_label_classes(self):
        labels = ("채낚기연승낚시", "통발", "자망", "연안복합")
        vessels = _vessels(labels=labels)
        protocol = {"class_names": list(labels), "source_hash": "scanner-sha256"}
        fake_dev = {"selection": {"candidate": "distribution36_mlp16",
                                  "confirmatory_candidate": True,
                                  "eligible_candidates": ["distribution36_mlp16"]},
                    "model_audit": {}}
        with tempfile.TemporaryDirectory() as temp, \
                patch("fishing_demo.real_model_cycle_20261028._evaluate_development",
                      return_value=(fake_dev, "distribution36_mlp16")), \
                patch("fishing_demo.real_model_cycle_20261028._evaluate_final_after_freeze",
                      return_value={"success_criteria_passed": False}):
            result = run_cycle(vessels, Path(temp), protocol)
            manifest = json_load(Path(temp) / "split_manifest.json")
            self.assertEqual(manifest["class_names"], list(labels))
            self.assertEqual(len(manifest["final"]), 8)
            self.assertEqual(result["selected_candidate"], "distribution36_mlp16")


def json_load(path):
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
