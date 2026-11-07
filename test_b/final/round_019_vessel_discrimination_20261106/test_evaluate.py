"""Meaningful synthetic checks only: no fleet data, event list, or model fitting."""
import sys
sys.dont_write_bytecode = True

import unittest
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

import evaluate as evaluation


class EvaluationTests(unittest.TestCase):
    def test_completed_scorer_artifact_hash_rejects_tampering_and_missing_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny_scores.csv"
            path.write_text("rfid_id,peak_score\nsynthetic,0.5\n", encoding="utf-8")
            certified = evaluation.sha256(path)
            metadata = {"output_sha256": certified}
            self.assertEqual(evaluation.verify_score_artifact(path, metadata), certified)
            path.write_text("rfid_id,peak_score\nsynthetic,0.9\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from completed scorer"):
                evaluation.verify_score_artifact(path, metadata)
            with self.assertRaisesRegex(ValueError, "lacks a valid output_sha256"):
                evaluation.verify_score_artifact(path, {})

    def test_auc_ties_constant_perfect_and_direction(self):
        self.assertEqual(evaluation.auc_greater([1, 1], [1, 1])[0], .5)
        self.assertEqual(evaluation.auc_greater([2, 3], [0, 1])[0], 1)
        self.assertEqual(evaluation.auc_greater([0, 1], [2, 3])[0], 0)
        self.assertEqual(evaluation.auc_greater([1, 2], [1, 1])[0], .75)
        low, high = evaluation.raw_bootstrap_ci([7, 7], [7, 7], np.random.default_rng(2), 100)
        self.assertEqual((low, high), (.5, .5))
        low, high = evaluation.raw_bootstrap_ci([2, 3], [0, 1], np.random.default_rng(2), 100)
        self.assertEqual((low, high), (1, 1))

    def test_matching_caliper_no_reuse_maxfive_and_id_ties(self):
        frame = pd.DataFrame({
            "rfid_id": ["p2", "p1", "a", "b", "c", "d", "e", "f", "far"],
            "n_rows": [100, 100, 100, 100, 100, 100, 100, 110, 111],
            "is_provisional_linked": [True, True] + [False] * 7,
        })
        sets, edges, unmatched = evaluation.build_matches(frame)
        self.assertEqual(frame.loc[sets[0][0], "rfid_id"], "p1")
        self.assertEqual([frame.loc[c, "rfid_id"] for c in sets[0][1]], list("abcde"))
        self.assertEqual([frame.loc[c, "rfid_id"] for c in sets[1][1]], ["f"])
        self.assertEqual(len({e["control_rfid_id"] for e in edges}), len(edges))
        self.assertNotIn("far", {e["control_rfid_id"] for e in edges})
        self.assertEqual(unmatched, [])
        self.assertTrue(all(e["abs_log_count_ratio"] <= evaluation.CALIPER + 1e-14 for e in edges))

    def test_conditional_auc_differs_from_pooled_auc(self):
        # Both within-set comparisons win; a pooled cross-set comparison loses.
        frame = pd.DataFrame({"peak_score": [1., 0., 100., 99.]})
        sets = [(0, [1]), (2, [3])]
        conditional = evaluation.matched_auc_and_inference(
            frame, sets, "peak_score", np.random.default_rng(3), 100, 999)
        pooled, _ = evaluation.auc_greater([1, 100], [0, 99])
        self.assertEqual(conditional["auc"], 1)
        self.assertEqual(pooled, .75)
        self.assertEqual((conditional["ci_low"], conditional["ci_high"]), (1, 1))
        self.assertGreaterEqual(conditional["p_greater"], .001)

    def test_matched_equal_set_weight_and_finite_subset(self):
        frame = pd.DataFrame({"peak_score": [1., 0., 0., 0., 1., 1., np.nan]})
        sets = [(0, [1, 2, 3]), (4, [5, 6])]
        valid = evaluation.finite_metric_sets(frame, sets, "peak_score")
        self.assertEqual(valid, [(0, [1, 2, 3]), (4, [5])])
        result = evaluation.matched_auc_and_inference(
            frame, valid, "peak_score", np.random.default_rng(4), 100, 99)
        self.assertEqual(result["auc"], .75)  # (1 + .5)/2, not control-weighted .875

    def test_rank_frequency_bootstrap_agrees_with_pairwise_resampling(self):
        positive, negative = np.array([0., 1., 1.]), np.array([0., 0., 2., 3.])
        actual = evaluation.raw_bootstrap_ci(positive, negative, np.random.default_rng(19), 300)
        rng, brute = np.random.default_rng(19), []
        for _ in range(300):
            p = positive[rng.integers(len(positive), size=len(positive))]
            n = negative[rng.integers(len(negative), size=len(negative))]
            pairs = p[:, None] - n[None, :]
            brute.append(np.mean((pairs > 0) + .5 * (pairs == 0)))
        np.testing.assert_allclose(actual, np.quantile(brute, [.025, .975]))

    def test_constant_matched_permutation_is_one_with_ties(self):
        frame = pd.DataFrame({"peak_score": [1.] * 5})
        result = evaluation.matched_auc_and_inference(
            frame, [(0, [1]), (2, [3, 4])], "peak_score", np.random.default_rng(20), 100, 99)
        self.assertEqual(result["auc"], .5)
        self.assertEqual(result["p_greater"], 1)
        self.assertEqual((result["ci_low"], result["ci_high"]), (.5, .5))

    def test_f1_identities_and_no_selection(self):
        for p in evaluation.PREVALENCES:
            perfect = evaluation.expected_f1(1, 0, p)
            self.assertAlmostEqual(perfect["expected_time_included_f1"], evaluation.H)
            self.assertEqual(perfect["q"], 1)
            self.assertAlmostEqual(perfect["k_per_100"], 100 * p)
            oracle_time = evaluation.expected_f1(1, 0, p, h=1)
            self.assertEqual(oracle_time["expected_time_included_f1"], 1)
            none = evaluation.expected_f1(0, 0, p)
            self.assertEqual(none["k_per_100"], 0)
            self.assertIsNone(none["q"])
            self.assertEqual(none["expected_time_included_f1"], 0)
        all_selected = evaluation.expected_f1(1, 1, .1)
        self.assertEqual(all_selected["k_per_100"], 100)
        self.assertAlmostEqual(all_selected["q"], .1)
        self.assertAlmostEqual(all_selected["expected_time_included_f1"], 2 * .1 * evaluation.H / 1.1)

    def test_holm_five_candidate_family(self):
        actual = evaluation.holm_adjust([.04, .01, .03, .2, .001])
        np.testing.assert_allclose(actual, [.09, .04, .09, .2, .005])
        missing = evaluation.holm_adjust([.01, None, .5, .6, .8])
        self.assertEqual(missing[0], .05)
        self.assertIsNone(missing[1])

    def test_fixed_thresholds_finite_quantiles_and_explicit_baselines(self):
        specs = evaluation.threshold_specs("peak_score", np.array([0., 1.]))
        self.assertEqual([s["threshold"] for s in specs[2:]],
                         [.4, .45, .5, .55, .6, .65, .7, .75, .8, .85, .9, .95])
        self.assertEqual([s["threshold"] for s in specs if s["representative"]], [.75])
        qspecs = evaluation.threshold_specs("gap_total_h", np.array([0., 10., np.inf, np.nan]))
        self.assertEqual(qspecs[2]["threshold"], 5)
        values = np.array([.75, np.nan, .74])
        np.testing.assert_array_equal(evaluation.selected_mask(values, specs[0]), [False] * 3)
        np.testing.assert_array_equal(evaluation.selected_mask(values, specs[1]), [True, False, True])
        rep = next(s for s in specs if s["representative"])
        np.testing.assert_array_equal(evaluation.selected_mask(values, rep), [True, False, False])


if __name__ == "__main__":
    unittest.main()
