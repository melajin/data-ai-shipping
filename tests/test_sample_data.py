"""Independent geometry checks and strict synthetic input-boundary tests."""

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from fishing_demo.data import generate_dataset, load_dataset, validate_dataset, validate_record, write_dataset
from fishing_demo.features import FEATURE_NAMES, FEATURE_UNITS, extract_features, feature_matrix


def record(parts):
    count = 0
    times = []
    for part in parts:
        times.append(list(range(count, count + len(part))))
        count += len(part)
    return {"sample_id": "example", "vessel_id": "vessel", "split": "test", "label": None,
            "parts": parts, "sim_times": times, "scenario": "base", "quality": {}}


class SampleDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.small = generate_dataset(seed=7, groups_per_split={
            "train": 2, "validation": 1, "calibration": 1, "test": 1, "stress": 1}, samples_per_class=2)

    def test_default_counts_and_group_disjointness(self):
        dataset = generate_dataset()
        self.assertEqual(len(dataset["records"]), 1008)
        split_groups = {}
        for item in dataset["records"]:
            split_groups.setdefault(item["split"], set()).add(item["vessel_id"])
        for left, groups in split_groups.items():
            self.assertEqual(len(groups), dataset["metadata"]["split_group_counts"][left])
            for right, other in split_groups.items():
                if left != right:
                    self.assertFalse(groups & other)
        self.assertEqual(len({item["sample_id"] for item in dataset["records"]}), 1008)

    def test_repeatability_and_seed_change(self):
        kwargs = dict(groups_per_split={"train": 2, "validation": 1, "calibration": 1,
                                       "test": 1, "stress": 1}, samples_per_class=2)
        self.assertEqual(self.small, generate_dataset(seed=7, **kwargs))
        self.assertNotEqual(self.small["records"], generate_dataset(seed=8, **kwargs)["records"])

    def test_hand_calculated_geometry_and_no_boundary_angle(self):
        # 3-4 right-angle route: L=7, D=5, straightness=5/7.
        item = extract_features(record([[[0, 0], [3, 0], [3, 4]]]))
        self.assertAlmostEqual(item["values"][0], math.log(8))
        self.assertAlmostEqual(item["parts"][0]["displacement_m"], 5)
        self.assertAlmostEqual(item["values"][1], 5 / 7)
        self.assertAlmostEqual(item["values"][2], math.pi / 2)
        self.assertAlmostEqual(item["values"][3], 1)
        self.assertAlmostEqual(item["values"][4], 0)
        self.assertAlmostEqual(item["values"][5], math.pi / 2)
        self.assertAlmostEqual(item["values"][7], (12 / 5) / 7)
        # Distinct one-segment parts: L=3+4=7, neither a jump nor a turn.
        broken = extract_features(record([[[0, 0], [3, 0]], [[100, 100], [100, 104]]]))
        self.assertAlmostEqual(broken["values"][0], math.log(8))
        self.assertAlmostEqual(broken["values"][1], 1)
        self.assertIsNone(broken["values"][2])
        self.assertEqual(broken["quality"]["turn_count"], 0)

    def test_mean_straightness_is_not_sum_displacement_over_sum_length(self):
        item = extract_features(record([[[0, 0], [3, 0], [3, 4]], [[20, 0], [21, 0]]]))
        self.assertAlmostEqual(item["values"][1], (5 / 7 + 1) / 2)
        self.assertNotAlmostEqual(item["values"][1], (5 + 1) / (7 + 1))

    def test_turn_direction_and_closed_chord(self):
        sweep = extract_features(record([[[0, 0], [1, 0], [1, 1], [2, 1]]]))
        self.assertAlmostEqual(sweep["values"][3], 0)
        self.assertAlmostEqual(sweep["values"][4], math.pi / 2)
        loop = extract_features(record([[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]))
        self.assertTrue(loop["valid"])
        self.assertIsNone(loop["values"][7])

    def test_translation_rotation_invariance_and_no_metadata_features(self):
        source = record([[[0, 0], [3, 0], [3, 4]], [[11, 12], [9, 13], [7, 12]]])
        transformed = copy.deepcopy(source)
        angle = 0.713
        rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        transformed["parts"] = [(np.asarray(part) @ rotation.T + [500, -210]).tolist() for part in source["parts"]]
        transformed.update({"sample_id": "changed", "vessel_id": "changed", "label": 2})
        transformed["sim_times"] = [[float(t * 10 + 10) for t in times] for times in source["sim_times"]]
        transformed["quality"] = {"unrelated": 123}
        original, _ = feature_matrix([source])
        shifted, _ = feature_matrix([transformed])
        np.testing.assert_allclose(original, shifted, atol=1e-12, rtol=1e-12)
        self.assertEqual(len(FEATURE_NAMES), 8)
        self.assertEqual(len(FEATURE_NAMES), len(FEATURE_UNITS))
        self.assertFalse(any(name in FEATURE_NAMES for name in ("point_count", "part_count", "missing_ratio")))

    def test_empty_zero_and_repeated_points(self):
        for parts in ([], [[]], [[[1, 1]]], [[[1, 1], [1, 1]]]):
            result = extract_features(record(parts))
            self.assertFalse(result["valid"])
            self.assertEqual(result["values"], [None] * len(FEATURE_NAMES))
        result = extract_features(record([[[0, 0], [0, 0], [2, 0], [2, 0], [2, 3]]]))
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["values"][2], math.pi / 2)
        matrix, details = feature_matrix([record([])])
        self.assertTrue(np.isnan(matrix).all())
        self.assertFalse(details[0]["valid"])
        self.assertEqual(feature_matrix([])[0].shape, (0, len(FEATURE_NAMES)))

    def test_record_type_finite_and_time_validation(self):
        base = record([[[0, 0], [1, 0]], [[2, 1], [3, 1]]])
        mutations = [
            ("label", True), ("label", 3), ("split", "unknown"), ("scenario", "shift"),
            ("parts", [[[True, 0]]]), ("parts", [[[float("nan"), 0]]]),
            ("parts", [[["0", 0]]]), ("parts", [[[0, 0, 1]]]),
            ("sim_times", [[0, 0], [2, 3]]), ("sim_times", [[0, 1], [1, 3]]),
            ("sim_times", [[0, 1]]), ("sim_times", [[0, 1], [2, float("inf")]]),
            ("quality", {"observed_points": 999}), ("quality", {"missing_ratio": 1.5}),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(base)
                changed[key] = value
                with self.assertRaises(ValueError):
                    validate_record(changed)

    def test_metadata_ids_and_vessel_split_validation(self):
        for mode in ("coordinate", "duplicate", "vessel", "counts"):
            data = copy.deepcopy(self.small)
            if mode == "coordinate":
                data["metadata"]["coordinate_system"] = "lon_lat"
            elif mode == "duplicate":
                data["records"][1]["sample_id"] = data["records"][0]["sample_id"]
            elif mode == "vessel":
                data["records"][-1]["vessel_id"] = data["records"][0]["vessel_id"]
            elif mode == "counts":
                data["metadata"]["split_group_counts"]["train"] = 1
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_dataset(data)

    def test_prediction_subset_does_not_require_training_class_coverage(self):
        data = copy.deepcopy(self.small)
        data["records"] = [data["records"][0]]
        data["records"][0]["label"] = None
        validate_dataset(data)

    def test_json_roundtrip_and_untrusted_json_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "samples.json"
            write_dataset(self.small, path)
            self.assertEqual(self.small, load_dataset(path))
            path.write_text('{"metadata": {}, "metadata": {}, "records": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_dataset(path)
            bad = copy.deepcopy(self.small)
            bad["records"][0]["parts"][0][0][0] = float("nan")
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite"):
                load_dataset(path)
            bad["records"][0]["parts"][0][0][0] = True
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "finite JSON number"):
                load_dataset(path)

    def test_stress_is_declared_shift_without_new_labels(self):
        stress = [item for item in self.small["records"] if item["split"] == "stress"]
        self.assertEqual({item["label"] for item in stress}, {0, 1, 2})
        shift = self.small["metadata"]["assumptions"]["stress_shift"]
        self.assertEqual(shift["scale_multiplier"], 2.6)
        self.assertTrue(all(item["scenario"] == "shift" for item in stress))
        self.assertTrue(all(item["quality"]["point_drop_probability"] == shift["point_drop_probability"]
                            for item in stress))


if __name__ == "__main__":
    unittest.main()
