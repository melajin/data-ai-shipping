"""Independent invariance and boundary checks for the separate S0 families."""
from __future__ import annotations

import copy
import math
import unittest

import numpy as np

from fishing_demo.data import generate_dataset
from fishing_demo.features import extract_features, feature_matrix as original_matrix
from fishing_demo.iteration_features import (FAMILIES, feature_matrix, feature_names,
                                             feature_units)


def record(parts):
    elapsed, times = 0, []
    for part in parts:
        times.append(list(range(elapsed, elapsed + len(part))))
        elapsed += len(part)
    return {"sample_id": "shape-example", "vessel_id": "vessel", "split": "test",
            "label": None, "parts": parts, "sim_times": times, "scenario": "base", "quality": {}}


def transformed(source, matrix, scale=1.0, translation=(0.0, 0.0)):
    result = copy.deepcopy(source)
    result["parts"] = [(np.asarray(part, dtype=float).reshape((-1, 2)) @ matrix.T * scale
                        + translation).tolist() for part in source["parts"]]
    return result


class IterationFeatureTests(unittest.TestCase):
    def setUp(self):
        self.curves = record([[[0, 0], [2, 0.4], [3, 2], [2, 4], [0.5, 4.5]],
                              [[10, 3], [11, 2], [14, 3], [16, 2]]])

    def test_family_contract_and_empty_matrix_shapes(self):
        for family, count in zip(FAMILIES, (8, 7, 9, 15)):
            with self.subTest(family=family):
                self.assertIsInstance(feature_names(family), tuple)
                self.assertIsInstance(feature_units(family), tuple)
                self.assertEqual(len(feature_names(family)), count)
                self.assertEqual(len(feature_units(family)), count)
                self.assertEqual(len(set(feature_names(family))), count)
                empty = feature_matrix([], family)
                self.assertEqual(empty.shape, (0, count))
                self.assertEqual(empty.dtype, np.float64)
        self.assertEqual(feature_units("shape15")[-6:], ("rad",) * 6)
        for bad in (None, "shape8", [], True):
            for function in (feature_names, feature_units):
                with self.assertRaises(ValueError):
                    function(bad)
            with self.assertRaises(ValueError):
                feature_matrix([], bad)

    def test_original_values_and_partial_straightness_are_unchanged(self):
        rows = [self.curves, record([[[0, 0], [3, 0], [3, 4]], [[20, 0], [21, 0]]]),
                record([[[0, 0], [1, 0]]]), record([])]
        expected, _ = original_matrix(rows)
        np.testing.assert_array_equal(feature_matrix(rows, "original8"), expected)
        for family in ("shape7", "shape9", "shape15"):
            np.testing.assert_array_equal(feature_matrix(rows, family)[:, :7], expected[:, 1:])
        self.assertAlmostEqual(feature_matrix(rows, "shape15")[1, 0], (5 / 7 + 1) / 2)
        self.assertNotAlmostEqual(feature_matrix(rows, "shape15")[1, 0], 6 / 8)

    def test_cloud_values_have_hand_calculated_reference(self):
        square = record([[[-1, -1], [1, -1], [1, 1], [-1, 1]]])
        line = record([[[-1, 0], [0, 0], [1, 0]]])
        actual = feature_matrix([square, line], "shape9")[:, -2:]
        np.testing.assert_allclose(actual, [[1, 1], [0, 1.5]], rtol=0, atol=1e-12)

    def test_cloud_is_invariant_to_boundaries_with_same_observed_points(self):
        points = [[0, 0], [1, 0.2], [2, 1], [3, 1.7], [4, 2], [5, 1]]
        whole = record([points])
        broken = record([points[:2], [], points[2:3], points[3:]])
        self.assertTrue(extract_features(whole)["valid"])
        self.assertTrue(extract_features(broken)["valid"])
        np.testing.assert_array_equal(feature_matrix([whole], "shape9")[:, -2:],
                                      feature_matrix([broken], "shape9")[:, -2:])

    def test_turn_summaries_match_right_angle_and_use_partwise_maximum(self):
        corner = [[0, 0], [3, 0], [3, 4]]
        opposite_corner = [[20, 0], [20, 3], [24, 3]]
        source = record([corner, opposite_corner, [[50, 0], [51, 0], [52, 0]],
                         [[60, 0], [61, 0]]])
        actual = feature_matrix([source], "shape15")[0, -6:]
        # Opposite turns belong to different parts and must not cancel. The
        # straight and two-point parts must not dilute a partwise maximum.
        np.testing.assert_allclose(actual, [math.pi / 2] * 6, rtol=0, atol=1e-12)

    def test_two_point_parts_are_valid_but_have_no_arc_turns(self):
        source = record([[[0, 0], [1, 0]], [[100, 100], [100, 101]], [[8, 8]], []])
        self.assertTrue(extract_features(source)["valid"])
        result = feature_matrix([source], "shape15")[0]
        self.assertTrue(np.isfinite(result[-8:-6]).all())
        self.assertTrue(np.isnan(result[-6:]).all())
        self.assertEqual(result[0], 1.0)

    def test_consecutive_duplicates_do_not_change_arc_turns_or_mutate_input(self):
        deduplicated = record([[[0, 0], [3, 0], [3, 4]]])
        repeated = record([[[0, 0], [0, 0], [3, 0], [3, 0], [3, 4], [3, 4]]])
        before = copy.deepcopy(repeated)
        np.testing.assert_allclose(feature_matrix([repeated], "shape15")[0, -6:],
                                   feature_matrix([deduplicated], "shape15")[0, -6:],
                                   rtol=0, atol=1e-12)
        self.assertEqual(repeated, before)
        only_two = record([[[0, 0], [0, 0], [1, 0], [1, 0]]])
        self.assertTrue(np.isnan(feature_matrix([only_two], "shape15")[0, -6:]).all())

    def test_revisits_are_retained_as_turns(self):
        reversal = record([[[0, 0], [1, 0], [0, 0]]])
        np.testing.assert_allclose(feature_matrix([reversal], "shape15")[0, -6:],
                                   [math.pi] * 6, rtol=0, atol=1e-12)

    def test_rotation_translation_and_reflection_invariance(self):
        angle = 0.713
        rotation = np.array([[math.cos(angle), -math.sin(angle)],
                             [math.sin(angle), math.cos(angle)]])
        for matrix in (rotation, np.diag([-1.0, 1.0])):
            other = transformed(self.curves, matrix, translation=(500, -210))
            for family in FAMILIES:
                with self.subTest(family=family, matrix=matrix.tolist()):
                    np.testing.assert_allclose(feature_matrix([self.curves], family),
                                               feature_matrix([other], family),
                                               rtol=1e-10, atol=1e-10, equal_nan=True)

    def test_shape_families_are_scale_invariant_and_original_length_is_not(self):
        for scale in (0.01, 2.6, 1000.0):
            other = transformed(self.curves, np.eye(2), scale=scale)
            for family in ("shape7", "shape9", "shape15"):
                with self.subTest(family=family, scale=scale):
                    np.testing.assert_allclose(feature_matrix([self.curves], family),
                                               feature_matrix([other], family),
                                               rtol=1e-10, atol=1e-10, equal_nan=True)
            self.assertNotEqual(feature_matrix([self.curves], "original8")[0, 0],
                                feature_matrix([other], "original8")[0, 0])

    def test_reversing_path_direction_is_invariant(self):
        reversed_path = record([list(reversed(part)) for part in reversed(self.curves["parts"])])
        for family in FAMILIES:
            with self.subTest(family=family):
                np.testing.assert_allclose(feature_matrix([self.curves], family),
                                           feature_matrix([reversed_path], family),
                                           rtol=1e-10, atol=1e-10, equal_nan=True)

    def test_base_validity_mask_and_all_invalid_rows_are_preserved(self):
        rows = [self.curves, record([]), record([[]]), record([[[1, 1]]]),
                record([[[1, 1], [1, 1]]]), record([[[0, 0]], [[10, 10]]])]
        valid = [extract_features(row)["valid"] for row in rows]
        self.assertEqual(valid, [True, False, False, False, False, False])
        for family in FAMILIES:
            matrix = feature_matrix(rows, family)
            self.assertTrue(np.isfinite(matrix[0]).all())
            self.assertTrue(np.isnan(matrix[1:]).all())
            self.assertFalse(np.isinf(matrix).any())

    def test_label_and_other_metadata_do_not_supply_features(self):
        data = generate_dataset(seed=19, groups_per_split={s: 1 for s in
            ("train", "validation", "calibration", "test", "stress")}, samples_per_class=1)
        original = data["records"]
        changed = copy.deepcopy(original)
        for i, row in enumerate(changed):
            row.update(label=None, sample_id=f"changed-{i}", vessel_id=f"changed-vessel-{i}",
                       split="stress", scenario="shift", quality={"irrelevant": 123}, seed=9876)
            row["sim_times"] = [[10 * t + 1000 for t in times] for times in row["sim_times"]]
        for family in FAMILIES:
            np.testing.assert_array_equal(feature_matrix(original, family), feature_matrix(changed, family))

    def test_malformed_input_is_rejected_by_existing_validator(self):
        malformed = copy.deepcopy(self.curves)
        malformed["parts"][0][0][0] = float("nan")
        for family in FAMILIES:
            with self.assertRaises(ValueError):
                feature_matrix([malformed], family)


if __name__ == "__main__":
    unittest.main()
