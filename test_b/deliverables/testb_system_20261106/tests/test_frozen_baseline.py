"""Small meaningful boundary checks; complete saved-row parity runs in the CLI."""
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from run_analysis import compare_rows, memory_preflight, run, select_peak

# Check RAM before importing scientific dependencies for these tests too.
memory_preflight()
import numpy as np
import pandas as pd
from frozen_baseline import build_quantile_normalizer, score_vessel


def observations(count):
    return pd.DataFrame({"rfid_id": ["synthetic"] * count, "ts": np.arange(count),
                         "rfid_time": np.arange(count) % 24, "source_ordinal": np.arange(count),
                         "cen_lon": np.full(count, 129.0), "cen_lat": np.full(count, 35.0),
                         "len_m": np.full(count, 1000.0), "bbox_m": np.full(count, 500.0)})


def score(frame):
    normalizer, _ = build_quantile_normalizer(np.array([0., 1., 2.]))
    return score_vessel(frame, lambda lon, lat: np.full(len(lon), math.inf), None,
                        {}, {}, normalizer, normalizer)


class FrozenBaselineTests(unittest.TestCase):
    def test_prefix_scores_and_history_threshold_preserve_causality(self):
        prefix = observations(25)
        extended = observations(40)
        extended.loc[25:, "len_m"] = 900000.0
        before, after = score(prefix), score(extended)
        np.testing.assert_array_equal(before["score"], after.iloc[:25]["score"])
        self.assertTrue(before.iloc[:24]["s_change"].isna().all())
        self.assertTrue(math.isfinite(before.iloc[24]["s_change"]))
        self.assertTrue(math.isnan(before.iloc[0]["s_gap"]))

    def test_peak_tie_uses_source_ordinal_instead_of_earliest_time(self):
        frame = pd.DataFrame({"score": [0.9, 0.9, 0.5], "ts": [1, 2, 3],
                              "source_ordinal": [20, 10, 30]})
        peak, ties = select_peak(frame)
        self.assertEqual((int(peak["source_ordinal"]), int(peak["ts"]), ties), (10, 2, 2))

    def test_nan_mask_differences_are_detected_even_if_finite_scores_match(self):
        expected = score(observations(25))
        changed = expected.copy()
        changed.loc[0, "s_change"] = 0.0
        parity = compare_rows(changed, expected)
        self.assertFalse(parity["all_row_checks_passed"])
        self.assertEqual(parity["nan_mask_mismatches"]["s_change"], 1)

    def test_existing_output_refused_before_loading_or_memory_work(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("run_analysis.memory_preflight", side_effect=AssertionError("unexpected work")):
                with self.assertRaises(FileExistsError):
                    run(Path(folder))


if __name__ == "__main__":
    unittest.main()
