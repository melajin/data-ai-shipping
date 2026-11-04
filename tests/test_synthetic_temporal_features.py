"""Meaningful guards for simulated time units and isolated part boundaries."""
import copy
import unittest

import numpy as np

from fishing_demo.data import generate_dataset
from fishing_demo.synthetic_temporal_features import compute_matrices, feature_matrix


class SyntheticTemporalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.dataset = generate_dataset(seed=17, groups_per_split={
            "train": 1, "validation": 1, "calibration": 1, "test": 1, "stress": 1},
            samples_per_class=1)
        record = self.dataset["records"][0]
        record["parts"] = [[[0, 0], [3, 0]], [[1000000, 1000000], [1000000, 1000004]]]
        record["sim_times"] = [[0, 1], [2, 3]]
        record["quality"] = {}

    def test_separate_parts_are_not_joined(self):
        temporal, geometric = compute_matrices(self.dataset)
        self.assertAlmostEqual(temporal[0, 0], 1)
        self.assertAlmostEqual(temporal[0, 1], 3.5)
        self.assertAlmostEqual(geometric[0, 0], 3.5)
        self.assertAlmostEqual(temporal[0, 2], 0.25)
        self.assertAlmostEqual(temporal[0, 3], geometric[0, 2])

    def test_doubling_simulated_time_halves_speed_only(self):
        modified = copy.deepcopy(self.dataset)
        for record in modified["records"]:
            record["sim_times"] = [[2 * t for t in part] for part in record["sim_times"]]
        time1, geom1 = compute_matrices(self.dataset)
        time2, geom2 = compute_matrices(modified)
        np.testing.assert_allclose(time2[:, 0], 2 * time1[:, 0], equal_nan=True)
        np.testing.assert_allclose(time2[:, 1], time1[:, 1] / 2, equal_nan=True)
        np.testing.assert_allclose(time2[:, 2], time1[:, 2] / 4, equal_nan=True)
        np.testing.assert_allclose(time2[:, 3], time1[:, 3], equal_nan=True)
        np.testing.assert_allclose(geom1, geom2, equal_nan=True)

    def test_generated_constant_dt_makes_speed_a_reexpression_of_edge_lengths(self):
        temporal, geometric = compute_matrices(self.dataset)
        # In this generator each record uses one fixed simulated step interval.
        np.testing.assert_allclose(temporal[:, 1] * temporal[:, 0], geometric[:, 0],
                                   rtol=1e-12, atol=1e-10, equal_nan=True)
        np.testing.assert_allclose(temporal[:, 2] * temporal[:, 0] ** 2, geometric[:, 1],
                                   rtol=1e-12, atol=1e-10, equal_nan=True)
        np.testing.assert_allclose(temporal[:, 3], geometric[:, 2],
                                   rtol=1e-12, atol=1e-10, equal_nan=True)

    def test_undefined_speed_cv_remains_missing(self):
        record = self.dataset["records"][0]
        record["parts"] = [[[1, 1], [1, 1]]]
        record["sim_times"] = [[0, 1]]
        temporal, geometric = compute_matrices(self.dataset)
        self.assertEqual(temporal[0, 1], 0)
        self.assertEqual(temporal[0, 2], 0)
        self.assertTrue(np.isnan(temporal[0, 3]))
        self.assertTrue(np.isnan(geometric[0, 2]))

    def test_real_or_unidentified_sources_are_rejected(self):
        self.dataset["metadata"]["source_type"] = "real"
        with self.assertRaises(ValueError):
            compute_matrices(self.dataset)

    def test_feature_dimensions_and_label_independence(self):
        original = feature_matrix(self.dataset, "shape9_simtime4")
        unlabeled = copy.deepcopy(self.dataset)
        for record in unlabeled["records"]:
            record["label"] = None
        np.testing.assert_allclose(original, feature_matrix(unlabeled, "shape9_simtime4"), equal_nan=True)
        self.assertEqual(original.shape[1], 13)
        self.assertEqual(feature_matrix(self.dataset, "shape9_edge3").shape[1], 12)
        self.assertEqual(feature_matrix(self.dataset, "shape9_dt_only").shape[1], 10)


if __name__ == "__main__":
    unittest.main()
