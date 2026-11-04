"""Independent checks for the real-coordinate geometry-only shape9 contract."""
from __future__ import annotations

import math
import unittest

import numpy as np

from fishing_demo.real_geometry_20261028 import (
    FEATURE_NAMES,
    _shape9_from_projected_parts,
    geometry_features,
)


class RealGeometryTests(unittest.TestCase):
    def test_four_point_geometry_has_nine_ordered_features(self):
        result = geometry_features([[[127.0, 36.0], [127.01, 36.0],
                                     [127.01, 36.01], [127.02, 36.01]]])
        self.assertTrue(result["valid"])
        self.assertIsNone(result["reason"])
        self.assertEqual(tuple(result["feature_names"]), FEATURE_NAMES)
        self.assertEqual(len(result["values"]), 9)
        self.assertEqual(result["coordinate_assumption"]["projection"], "local_tangent")
        self.assertFalse(result["coordinate_assumption"]["metric_distance_or_speed"])
        self.assertAlmostEqual(result["values"][1], math.pi / 2, places=12)
        self.assertAlmostEqual(result["values"][2], 0.0, places=12)
        self.assertAlmostEqual(result["values"][4], math.pi / 2, places=12)

    def test_closed_part_has_no_chord_deviation(self):
        result = geometry_features([[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
                                   projection="degree_control")
        self.assertTrue(result["valid"])
        self.assertEqual(result["values"][0], 0.0)
        self.assertIsNone(result["values"][6])
        self.assertEqual(result["coordinate_assumption"]["units"], "degrees")

    def test_parts_are_not_linked_for_turns(self):
        result = geometry_features([
            [[0.0, 0.0], [0.1, 0.0]],
            [[10.0, 5.0], [10.0, 5.1]],
        ], projection="degree_control")
        self.assertTrue(result["valid"])
        self.assertIsNone(result["values"][1])
        self.assertIsNone(result["values"][2])
        self.assertIsNone(result["values"][3])
        self.assertIsNone(result["values"][4])

    def test_empty_zero_length_short_part_and_nonfinite_boundaries(self):
        for parts, reason in (([], "empty"), ([[[1.0, 2.0]]], "part_too_short"),
                              ([[[1.0, 2.0], [1.0, 2.0]]], "no_positive_length"),
                              ([[[1.0, 2.0], [float("nan"), 2.0]]], "nonfinite_coordinate"),
                              ([[[181.0, 2.0], [182.0, 2.0]]], "longitude_out_of_range"),
                              ([[[1.0, 91.0], [2.0, 91.0]]], "latitude_out_of_range")):
            with self.subTest(reason=reason):
                result = geometry_features(parts)
                self.assertFalse(result["valid"])
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["values"], [None] * 9)

    def test_spatial_and_polar_research_bounds_abstain_explicitly(self):
        too_wide = geometry_features([[[-11.0, 0.0], [11.0, 0.0]]])
        polar = geometry_features([[[0.0, 86.0], [0.1, 86.1]]])
        self.assertEqual(too_wide["reason"], "spatial_span_exceeds_20_degrees")
        self.assertEqual(polar["reason"], "mean_latitude_exceeds_85_degrees")

    def test_projected_xy_shape9_is_rotation_translation_and_scale_invariant(self):
        parts = [np.asarray([[0.0, 0.0], [2.0, 0.4], [3.0, 2.0], [2.0, 4.0]]),
                 np.asarray([[10.0, 3.0], [11.0, 2.0], [14.0, 3.0]])]
        angle = 0.73
        rotation = np.asarray([[math.cos(angle), -math.sin(angle)],
                               [math.sin(angle), math.cos(angle)]])
        baseline = _shape9_from_projected_parts(parts)
        transformed = [part @ rotation.T * 3.7 + np.asarray([42.0, -19.0])
                      for part in parts]
        candidate = _shape9_from_projected_parts(transformed)
        self.assertTrue(baseline["valid"] and candidate["valid"])
        np.testing.assert_allclose(baseline["values"], candidate["values"],
                                   rtol=1e-11, atol=1e-11, equal_nan=True)


if __name__ == "__main__":
    unittest.main()
