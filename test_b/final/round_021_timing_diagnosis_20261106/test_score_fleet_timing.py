"""Synthetic engine checks only. No outcome or real vessel data are read."""
import hashlib
import json
import sys
import time
import unittest

sys.dont_write_bytecode = True
import score_fleet_timing as engine

sf = engine.legacy_module()
fb = engine.stack(sf)
np, pd = sf.np, sf.pd


class EngineChecks(unittest.TestCase):
    def fixture(self, hours, scores, ordinals=None):
        size = len(hours)
        if ordinals is None:
            ordinals = list(range(size))
        one = pd.DataFrame({"rfid_id": ["synthetic-A"] * size,
            "ts": [sf.START_H + h for h in hours], "source_ordinal": ordinals,
            "cen_lon": [127.] * size, "cen_lat": [35.] * size, "len_m": [100.] * size,
            "bbox_m": [50.] * size, "n_coords": [3] * size})
        one["rfid_time"] = one.ts % 24
        scored = one.copy()
        scored["score"] = scores
        scored["state"] = "synthetic"
        return one, scored

    def record(self, hours, scores, ordinals=None):
        one, scored = self.fixture(hours, scores, ordinals)
        return engine.policy_record("synthetic-A", one, scored, sf, fb)

    def test_baseline_exact_max_source_ordinal(self):
        got = self.record([0, 2, 3], [.8, .8, .8], [20, 10, 30])
        self.assertEqual(got["baseline_ts"], sf.START_H + 2)
        self.assertEqual(got["baseline_source_ordinal"], 10)

    def test_near_tie_is_not_exact_tie(self):
        got = self.record([0, 1], [.8, np.nextafter(.8, 1.)])
        self.assertEqual(got["n_tied_hours"], 1)
        self.assertEqual(got["tie_center_ts"], sf.START_H + 1)

    def test_longest_run_lower_middle(self):
        got = self.record([0, 1, 5, 6, 7, 8], [.8] * 6)
        self.assertEqual(got["tie_center_ts"], sf.START_H + 6)
        self.assertEqual(got["n_tie_runs"], 2)
        self.assertEqual((got["tie_run_start"], got["tie_run_end"]), (sf.START_H + 5, sf.START_H + 8))

    def test_tie_run_earliest_start(self):
        got = self.record([0, 1, 5, 6], [.8] * 4)
        self.assertEqual(got["tie_center_ts"], sf.START_H)

    def test_duplicate_hours_not_multiple_votes(self):
        got = self.record([0, 0, 0, 3, 4], [.8] * 5)
        self.assertEqual(got["n_tied_rows"], 5)
        self.assertEqual(got["n_tied_hours"], 3)
        self.assertEqual(got["tie_center_ts"], sf.START_H + 3)

    def test_gap_uses_immediate_row_even_if_same_hour(self):
        got = self.record([0, 10, 10], [.1, .3, .9])
        self.assertEqual(got["previous_row_ts"], sf.START_H + 10)
        self.assertEqual(got["previous_distinct_ts"], sf.START_H)
        self.assertEqual(got["baseline_row_gap_h"], 0)
        self.assertEqual(got["gap_midpoint_ts"], sf.START_H + 10)

    def test_gap_floor_midpoint(self):
        got = self.record([0, 5], [.1, .9])
        self.assertEqual(got["gap_midpoint_ts"], sf.START_H + 2)
        self.assertEqual(got["gap_missing_h"], 4)

    def test_first_row_and_adjacent_gap_fallback(self):
        first = self.record([0, 10], [.9, .1])
        adjacent = self.record([0, 1], [.1, .9])
        self.assertIsNone(first["previous_row_ts"])
        self.assertEqual(first["gap_midpoint_ts"], first["baseline_ts"])
        self.assertEqual(adjacent["gap_midpoint_ts"], adjacent["baseline_ts"])

    def test_no_finite_score_preserves_unknown(self):
        got = self.record([0, 3], [np.nan, np.inf])
        self.assertEqual(got["n_finite_scores"], 0)
        for field in ("baseline_ts", "tie_center_ts", "gap_midpoint_ts", "peak_score"):
            self.assertIsNone(got[field])

    def test_scoring_error_keeps_rows_explicit(self):
        one, _ = self.fixture([0, 2], [.1, .9])
        got = engine.policy_record("synthetic-A", one, None, sf, fb, "synthetic failure")
        self.assertEqual(got["n_rows"], 2)
        self.assertEqual(got["scoring_error"], "synthetic failure")
        self.assertIsNone(got["baseline_ts"])

    def test_fleet_split_all_ids_without_labels_or_times(self):
        ids = [f"synthetic-{i:04d}" for i in range(7372)]
        result = engine.split_fleet(ids)
        self.assertEqual(result, engine.split_fleet(reversed(ids)))
        self.assertEqual(sum(v["split"] == "development" for v in result.values()), 3686)
        self.assertEqual(sum(v["split"] == "validation" for v in result.values()), 3686)
        first = min(ids, key=lambda r: (hashlib.sha256(("round021-v1|"+r).encode()).hexdigest(), r))
        self.assertEqual(result[first], {"split": "development", "split_rank": 0})

    def test_frozen_scorer_and_original_summarizer_match(self):
        one, _ = self.fixture(list(range(36)), [.1] * 36)
        one["len_m"] = np.arange(36) % 5 * 1250.
        one["bbox_m"] = np.arange(36) % 5 * 800.
        one["cen_lon"] = 127 + np.arange(36) * .001
        nearest = lambda lon, lat: np.full(len(lon), np.inf)
        norm = lambda value: np.minimum(np.asarray(value, dtype=float) / 20, 1)
        scored = fb.score_vessel(one, nearest, None, {}, {}, norm, norm)
        expected = sf.summarize_vessel("synthetic-A", one, scored, fb)
        observed = engine.policy_record("synthetic-A", one, scored, sf, fb)
        self.assertEqual(expected, {column: observed[column] for column in sf.OUTPUT_COLS})
        self.assertTrue(np.isfinite(scored.score).all())

    def test_checkpoint_hash_and_row_mismatch_rejected(self):
        directory = engine.ROUND / "engine_synthetic_validation" / f"checkpoint_{time.time_ns()}"
        directory.mkdir(parents=True)
        path, checkpoint = engine.checkpoint_files(directory, 0)
        schema = engine.score_schema(sf.pa)
        sf.pq.write_table(sf.pa.Table.from_pylist([], schema=schema), path)
        with path.open("rb+") as handle:
            import os
            os.fsync(handle.fileno())
        item = {"sha256": "synthetic-input", "rows": 0}
        receipt = {"input_sha256": item["sha256"], "rows": 0, "output_sha256": engine.sha256(path)}
        engine.atomic_json(checkpoint, receipt)
        self.assertEqual(engine.load_completed_partition(directory, 0, item), receipt)
        with self.assertRaisesRegex(AssertionError, "input differs"):
            engine.load_completed_partition(directory, 0, {**item, "rows": 1})
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(AssertionError, "changed"):
            engine.load_completed_partition(directory, 0, item)

    def test_fixed_assignments_cover_each_partition_once(self):
        assignments = [[p for p in range(128) if p % engine.ASSIGNMENTS == i] for i in range(4)]
        self.assertEqual(sorted(p for group in assignments for p in group), list(range(128)))
        self.assertEqual([len(group) for group in assignments], [32] * 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
