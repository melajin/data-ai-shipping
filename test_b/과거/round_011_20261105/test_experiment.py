"""Small synthetic contract tests. Never read the fixed Round008 dataset.

Run: python -B -m unittest discover -s testB/round_011_20261105 -p test_experiment.py -v
Fixtures are artificial arithmetic checks, not accident or hardware validation.
"""
from __future__ import annotations

import csv
from itertools import combinations
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import run_experiment as experiment


def rows_at(ts, lengths=None, bboxes=None, lon=None, lat=None, vessel=1):
    ts = np.asarray(ts, dtype=np.int64)
    rows = np.empty(len(ts), dtype=experiment.ROW_DTYPE)
    rows["rfid_id_int"] = vessel
    rows["ts"] = ts
    rows["len_m"] = np.full(len(ts), 10.0) if lengths is None else lengths
    rows["bbox_m"] = np.full(len(ts), 5.0) if bboxes is None else bboxes
    rows["cen_lon"] = np.zeros(len(ts)) if lon is None else lon
    rows["cen_lat"] = np.zeros(len(ts)) if lat is None else lat
    return rows


def reference_fixture(ts):
    """Direct feature fixture isolates selector logic from the rolling calculation."""
    n = len(ts)
    return {"ts": np.asarray(ts, dtype=np.int64), "n_rows": np.full(n, 7, dtype=np.int16),
            "n_valid_rows": np.full(n, 7), "n_lin_valid": np.full(n, 7), "n_pairs": np.full(n, 6),
            "quality_valid": np.ones(n, dtype=bool), "end_center_valid": np.ones(n, dtype=bool),
            "end_lon": np.zeros(n), "end_lat": np.zeros(n), "lin_raw": np.full(n, 0.5),
            "A": np.full(n, math.log(11)), "M": np.zeros(n)}


class WindowTests(unittest.TestCase):
    def test_trailing_window_and_future_invariance(self):
        rows = rows_at(np.arange(20), lengths=np.arange(20) + 1.0, bboxes=np.arange(20) + 0.5,
                       lon=np.arange(20) * 0.001)
        before = experiment.build_windows(rows[:13])
        changed = rows.copy()
        changed["len_m"][13:] = 999999
        changed["cen_lon"][13:] = 179
        after = experiment.build_windows(changed)
        for feature in ("n_rows", "n_valid_rows", "n_lin_valid", "n_pairs", "lin_raw", "A", "M", "quality_valid"):
            np.testing.assert_equal(before[feature], after[feature][:13])
        self.assertEqual(before["n_rows"][-1], 7)
        self.assertAlmostEqual(before["A"][-1], np.log1p(rows["len_m"][6:13]).mean())

    def test_gaps_never_connect_and_left_boundary_pair_excluded(self):
        ts = [0, 1, 3, 4, 6, 7]
        windows = experiment.build_windows(rows_at(ts, lon=np.asarray(ts) * 0.001))
        self.assertEqual(windows["n_rows"][-1], 5)
        self.assertEqual(windows["n_pairs"][-1], 2)  # (3,4), (6,7); not (0,1), (1,3), (4,6)
        self.assertAlmostEqual(windows["M"][-1], experiment.haversine(0, 0, 0.001, 0), places=7)

    def test_geometry_masks_and_independent_activity(self):
        rows = rows_at(np.arange(7), lengths=[1, 2, 0, -1, 5, np.nan, 7],
                       bboxes=[0.5, 1, 0, 1, -2, 1, 3.5])
        w = experiment.build_windows(rows)
        self.assertEqual(w["n_rows"][-1], 7)
        self.assertEqual(w["n_valid_rows"][-1], 4)
        self.assertEqual(w["n_lin_valid"][-1], 3)
        self.assertEqual(w["lin_raw"][-1], 0.5)
        self.assertAlmostEqual(w["A"][-1], np.log1p([1, 2, 0, 5, 7]).mean())
        self.assertTrue(w["quality_valid"][-1])

    def test_invalid_center_ranges_and_nonfinite_values(self):
        rows = rows_at(np.arange(7), lon=[0, 0, 181, 0, np.nan, 0, 0], lat=[0, 0, 0, 91, 0, 0, 0])
        w = experiment.build_windows(rows)
        self.assertEqual(w["n_pairs"][-1], 2)
        self.assertTrue(w["quality_valid"][-1])
        np.testing.assert_equal(w["end_center_valid"], [True, True, False, False, False, True, True])
        self.assertFalse(experiment.valid_centers(np.array([np.inf]), np.array([0]))[0])

    def test_low_quality_excluded_even_if_lin_is_finite(self):
        w = experiment.build_windows(rows_at([0, 2, 4, 6]))
        self.assertEqual(w["n_lin_valid"][-1], 4)
        self.assertFalse(w["quality_valid"][-1])
        self.assertIn("exact_1h_center_pairs_lt2", experiment.quality_reason(w, 3))
        with self.assertRaises(ValueError):
            experiment.build_windows(rows_at([1, 1]))


class ReferenceTests(unittest.TestCase):
    def test_inclusive_lower_upper_and_prior_only(self):
        ts = [279] + [280 + 24 * day for day in range(10)] + [1000]
        w = reference_fixture(ts)
        result = experiment.select_references(w, len(ts) - 1, "L")
        selected = w["ts"][result["indices"]]
        self.assertIn(280, selected)
        self.assertNotIn(279, selected)
        self.assertEqual(len(selected), 10)
        ts = [736 + 24 * day for day in range(9)] + [976, 977, 1000]
        w = reference_fixture(ts)
        w["end_lon"][-3] = 0.001  # out-of-range 977 would win L if mistakenly included
        selected = w["ts"][experiment.select_references(w, len(ts) - 1, "L")["indices"]]
        self.assertIn(976, selected)
        self.assertNotIn(977, selected)
        self.assertTrue(np.all(selected <= 1000 - 24))

    def test_recent_ten_distinct_days_and_context_sorting(self):
        # Current hour=16. T/TL prefer hour16 despite farther distance; L prefers hour17.
        ts = [day * 24 + h for day in range(10, 30) for h in (15, 16, 17)] + [40 * 24 + 16]
        w = reference_fixture(ts)
        for i, t in enumerate(ts[:-1]):
            w["end_lon"][i] = {15: 0.01, 16: 0.02, 17: 0.0}[t % 24]
        for context, hour in (("T", 16), ("L", 17), ("TL", 16)):
            ref = experiment.select_references(w, len(ts) - 1, context)
            chosen = w["ts"][ref["indices"]]
            self.assertEqual(ref["eligible_days"], 20)  # oldest day partly inside 720h
            self.assertEqual(len(chosen), 10)
            np.testing.assert_equal(chosen // 24, np.arange(29, 19, -1))
            np.testing.assert_equal(chosen % 24, hour)

    def test_tie_prefers_coverage_then_earlier_timestamp(self):
        ts = [day * 24 + h for day in range(20, 30) for h in (15, 17)] + [40 * 24 + 16]
        w = reference_fixture(ts)
        selected = experiment.select_references(w, len(ts) - 1, "T")["indices"]
        np.testing.assert_equal(w["ts"][selected] % 24, 15)
        w["n_rows"][:-1:2] = 6
        selected = experiment.select_references(w, len(ts) - 1, "T")["indices"]
        np.testing.assert_equal(w["ts"][selected] % 24, 17)

    def test_quality_coverage_and_spatial_filters(self):
        ts = [day * 24 + 16 for day in range(20, 30)] + [40 * 24 + 16]
        w = reference_fixture(ts)
        w["quality_valid"][0] = False
        self.assertEqual(experiment.select_references(w, 10, "T")["eligible_days"], 9)
        w["quality_valid"][0] = True
        w["n_rows"][0] = 5
        self.assertEqual(experiment.select_references(w, 10, "T")["eligible_days"], 9)
        w["n_rows"][0] = 7
        w["end_lon"][0] = 1
        self.assertEqual(experiment.select_references(w, 10, "L")["eligible_days"], 9)
        w["end_center_valid"][-1] = False
        self.assertEqual(experiment.select_references(w, 10, "L")["unknown_reason"], "current_end_center_invalid")
        self.assertEqual(experiment.select_references(w, 10, "T")["unknown_reason"], "")

    def test_exact_float_midties_and_zero_movement_joint(self):
        self.assertEqual(experiment.mid_percentile(1.0, np.array([0.0, 1.0, 1.0, 2.0])), 0.5)
        self.assertEqual(experiment.mid_percentile(np.nextafter(1.0, 2.0), np.ones(10)), 1.0)
        # Midrank intentionally yields joint=.25 when all A and M are identical, including M=0.
        result = experiment.score_vessel(rows_at(np.arange(400)))
        # Avoid the initial six-row window: its floating mean can differ in the
        # final bit, and the protocol intentionally uses exact float equality.
        common = result["common"] & (result["windows"]["ts"] >= 300)
        self.assertTrue(common.any())
        np.testing.assert_equal(result["scores"][common, 2], 0.25)
        np.testing.assert_equal(result["windows"]["M"][common], 0.0)


class RankingTests(unittest.TestCase):
    def test_uniform_top1_and_exact_top10_boundary(self):
        scores = np.array([5, 5, 4, 3, 3, 3, 3, 2], dtype=float)
        near = np.array([False, True, False, False, True, False, False, False])
        result = experiment.ranking_metrics(scores, near, k=5)
        self.assertEqual(result["top1_expected"], 0.5)
        self.assertEqual(result["top10_probability"], 1.0)  # certain hit above boundary
        near[1] = False
        result = experiment.ranking_metrics(scores, near, k=5)
        self.assertAlmostEqual(result["top10_probability"], 1 - math.comb(3, 2) / math.comb(4, 2))
        possibilities = list(combinations(range(3, 7), 2))
        exact = sum(any(near[i] for i in draw) for draw in possibilities) / len(possibilities)
        self.assertAlmostEqual(result["top10_probability"], exact)

    def test_all_equal_top10_probability_is_not_independent_draws(self):
        near = np.zeros(100, dtype=bool)
        near[:13] = True
        result = experiment.ranking_metrics(np.zeros(100), near)
        self.assertEqual(result["top1_expected"], 0.13)
        self.assertAlmostEqual(result["top10_probability"], 1 - math.comb(87, 10) / math.comb(100, 10))
        self.assertNotAlmostEqual(result["top10_probability"], 1 - 0.87**10, places=5)

    def test_no_near_event_retained_and_unknown_unconditional_zero(self):
        rows = rows_at(np.arange(100))
        result = {"windows": experiment.build_windows(rows), "scores": np.zeros((100, 10)),
                  "common": np.ones(100, dtype=bool)}
        event = {"acc_id": 1, "rfid_id": 1, "tier": 0, "acc_ts": 1000}
        metrics = experiment.evaluate_vessel([event], result)
        self.assertEqual(len(metrics), 10)
        self.assertTrue(all(m["evaluable"] and m["top1_expected"] == 0 and m["top10_probability"] == 0 for m in metrics))
        result["common"][0] = False
        metrics = experiment.evaluate_vessel([event], result)
        self.assertTrue(all(not m["evaluable"] and m["conservative_top1_expected"] == 0 for m in metrics))
        self.assertTrue(all("top1_expected" not in m for m in metrics))

    def test_cluster_resampling_keeps_repeated_vessel_events_together(self):
        # Every cluster mean=1/3. Event bootstrap would have variable means; cluster bootstrap is degenerate.
        ids = [1, 1, 1, 2, 2, 2]
        differences = np.array([1, 0, 0, 1, 0, 0], dtype=float)
        result = experiment.cluster_bootstrap(ids, differences, b=40)
        self.assertEqual(result["n_clusters"], 2)
        self.assertEqual(result["ci_low"], [1 / 3])
        self.assertEqual(result["ci_high"], [1 / 3])
        self.assertEqual(result, experiment.cluster_bootstrap(ids, differences, b=40))


class ExecutionTests(unittest.TestCase):
    def test_memory_refusal_receipt_and_exit75_without_inputs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "memory_state", return_value=(100, 200)), patch.object(experiment, "process_snapshot", return_value=[]):
            output = Path(directory)
            status = experiment.run_experiment(output / "absent.parquet", output / "absent.csv", output, output / "absent.md")
            self.assertEqual(status, 75)
            receipt = json.loads((output / "execution.json").read_text())
            memory = json.loads((output / "memory.json").read_text())
            self.assertEqual(receipt["status"], "memory_deferred")
            self.assertFalse(memory[0]["allowed"])
            self.assertIn("checked_at", memory[0])
            self.assertFalse((output / "experiment.lock").exists())
            self.assertFalse((output / "timestamp_scores.csv").exists())

    def test_competing_invocation_preserves_active_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "experiment.lock").write_text("active runner")
            (output / "execution.json").write_text('{"status":"active"}')
            status = experiment.run_experiment(output / "none", output / "none", output, output / "none")
            self.assertEqual(status, 1)
            self.assertEqual((output / "execution.json").read_text(), '{"status":"active"}')
            self.assertEqual((output / "experiment.lock").read_text(), "active runner")

    def test_small_end_to_end_streamed_fixture(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            fixture = rows_at(np.arange(500), vessel=1)
            excluded = rows_at(np.arange(10), vessel=999)
            both = np.concatenate([fixture, excluded])
            parquet = folder / "fixture.parquet"
            pq.write_table(pa.table({column: both[column] for column in experiment.COLS}), parquet, row_group_size=37)
            event_path = folder / "events.csv"
            with event_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["acc_id", "rfid_id", "tier", "acc_ts"])
                writer.writeheader()
                writer.writerows([{"acc_id": 1, "rfid_id": 1, "tier": 0, "acc_ts": 450},
                                  {"acc_id": 2, "rfid_id": 1, "tier": 2, "acc_ts": 1000}])
            protocol = folder / "PROTOCOL.md"
            protocol.write_text("synthetic test fixture only", encoding="utf-8")
            output = folder / "outputs"
            # Actual resource preflight for this tiny fixture; no fixed data is read.
            available, total = experiment.memory_state()
            self.assertGreaterEqual(available, experiment.MIN_AVAILABLE_BYTES,
                                    "Synthetic integration deferred: actual RAM below protocol floor")
            status = experiment.run_experiment(parquet, event_path, output, protocol, expected_counts=(2, 1, 1))
            self.assertEqual(status, 0)
            receipt = json.loads((output / "execution.json").read_text())
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(receipt["status"], "complete")
            self.assertEqual(receipt["input_profile"]["retained_rows"], 500)
            self.assertEqual(receipt["input_profile"]["scanned_rows"], 510)
            self.assertEqual(summary["event_metric_rows"], 20)
            self.assertEqual(summary["profiles"]["tier01"]["n_total"], 1)
            self.assertEqual(summary["profiles"]["all100"]["n_total"], 2)
            self.assertTrue(all(c["decision"] == "insufficient_common_evaluable_events" for c in summary["primary_contrasts"]))
            with (output / "timestamp_scores.csv").open(newline="", encoding="utf-8") as handle:
                score_rows = list(csv.DictReader(handle))
            self.assertEqual(len(score_rows), 500)
            for row in score_rows:
                for context in experiment.CONTEXTS:
                    refs = json.loads(row[f"{context}_ref_ts_json"])
                    self.assertTrue(all(int(row["ts"]) - 720 <= t <= int(row["ts"]) - 24 for t in refs))
            with (output / "event_metrics.csv").open(newline="", encoding="utf-8") as handle:
                event_rows = list(csv.DictReader(handle))
            missing_near = [r for r in event_rows if r["acc_id"] == "2"]
            self.assertTrue(all(r["evaluable"] == "1" and float(r["top1_expected"]) == 0 for r in missing_near))
            for name, profile in receipt["outputs"].items():
                self.assertEqual(experiment.sha256(output / name), profile["sha256"])


if __name__ == "__main__":
    unittest.main()
