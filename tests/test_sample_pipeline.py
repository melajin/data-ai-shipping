"""Integration checks for split boundaries and frozen inference, not score targets."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from fishing_demo.data import generate_dataset
from fishing_demo.pipeline import load_model, predict_records, train_experiment
from fishing_demo.models import Classifier, Preprocessor, AnomalyModel


class SamplePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.dataset = generate_dataset(seed=17, groups_per_split={
            "train": 3, "validation": 2, "calibration": 2, "test": 2, "stress": 2}, samples_per_class=2)
        cls.report = train_experiment(cls.dataset, cls.root / "first", seed=17, epochs=12)
        cls.bundle = load_model(cls.root / "first/model.json")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_full_pipeline_creates_frozen_outputs(self):
        for name in ("model.json", "report.json", "predictions.json", "dashboard.html"):
            self.assertTrue((self.root / "first" / name).is_file())
        self.assertEqual(self.report["audit"]["group_overlap_count"], 0)
        self.assertTrue(self.report["audit"]["serialization_predictions_identical"])
        self.assertEqual(self.report["audit"]["fit_split"], "train")
        self.assertFalse(self.report["audit"]["test_used_for_selection"])

    def test_prediction_does_not_read_labels(self):
        original = predict_records(self.dataset, self.bundle)
        no_labels = copy.deepcopy(self.dataset)
        for r in no_labels["records"]:
            r["label"] = None
        without = predict_records(no_labels, self.bundle)
        for a, b in zip(original, without):
            self.assertEqual(a["probabilities"], b["probabilities"])
            self.assertEqual(a["anomaly_score"], b["anomaly_score"])

    def test_test_changes_do_not_change_fit_select_or_calibration(self):
        changed = copy.deepcopy(self.dataset)
        for r in changed["records"]:
            if r["split"] in ("test", "stress"):
                for part in r["parts"]:
                    for point in part:
                        point[0] *= 1.2
                        point[1] *= 1.2
        train_experiment(changed, self.root / "changed", seed=17, epochs=12)
        other = load_model(self.root / "changed/model.json")
        for name in ("preprocessor", "classifier", "selected_model", "temperature", "anomaly_model", "anomaly_threshold"):
            self.assertEqual(self.bundle[name], other[name], name)
        self.assertNotEqual(self.bundle["dataset_sha256"], other["dataset_sha256"])

    def test_invalid_geometry_abstains_instead_of_normal_score(self):
        dataset = copy.deepcopy(self.dataset)
        row = dataset["records"][0]
        row["parts"] = [[[0.0, 0.0], [0.0, 0.0]]]
        row["sim_times"] = [[0.0, 1.0]]
        row["quality"] = {}
        out = predict_records(dataset, self.bundle)[0]
        self.assertEqual(out["status"], "abstained")
        self.assertIsNone(out["anomaly_score"])
        self.assertIsNone(out["probabilities"])

    def test_model_contract_tampering_rejected(self):
        damaged = copy.deepcopy(self.bundle)
        damaged["feature_names"] = list(reversed(damaged["feature_names"]))
        with self.assertRaises(ValueError):
            predict_records(self.dataset, damaged)

    def test_model_semantic_and_module_contracts_rejected(self):
        replacements = [
            ("class_names", ["turn", "sweep", "straight"]),
            ("feature_units", ["unknown"] * 8),
            ("classifier", Classifier(16, n_classes=2).to_dict()),
            ("classifier", Classifier(14, n_classes=3).to_dict()),
            ("preprocessor", Preprocessor().fit(np.zeros((3, 7))).to_dict()),
            ("anomaly_model", AnomalyModel().fit(np.zeros((6, 14)), [0, 1, 2, 0, 1, 2]).to_dict()),
            ("anomaly_model", AnomalyModel().fit(np.zeros((4, 16)), [0, 1, 0, 1], n_classes=2).to_dict()),
        ]
        for key, value in replacements:
            with self.subTest(key=key, value_type=type(value).__name__):
                damaged = copy.deepcopy(self.bundle)
                damaged[key] = value
                with self.assertRaises(ValueError):
                    predict_records(self.dataset, damaged)
                path = self.root / "invalid_model.json"
                path.write_text(json.dumps(damaged), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_model(path)


if __name__ == "__main__":
    unittest.main()
