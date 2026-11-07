"""Small synthetic checks; no accident labels or external/test input is read."""
import importlib
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
import score_fleet as sf

sf.load_stack()
np, pd, pa, pq = sf.np, sf.pd, sf.pa, sf.pq
sys.path.insert(0, str(sf.FROZEN.parent))
fb = importlib.import_module("frozen_baseline")


class ScoringChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = sf.ROUND_DIR / "scoring_validation_20261106"
        cls.artifacts.mkdir(exist_ok=True)

    def fixture(self):
        rows = []
        for j, rfid in enumerate(["synthetic-A", "synthetic-B", "synthetic-C"]):
            for i in range(36):
                rows.append({"rfid_id": rfid, "ts": sf.START_H + i + i // 7,
                             "source_ordinal": i * 3 + j, "len_m": float((i % 5) * 1250),
                             "bbox_m": float((i % 5) * 800), "cen_lon": 127 + j * .03 + i * .001,
                             "cen_lat": 35 + j * .03, "n_coords": 3})
        return pd.DataFrame(rows)[sf.COLS].sample(frac=1, random_state=19).reset_index(drop=True)

    def test_partitioned_scores_equal_direct_frozen_scores(self):
        frame = self.fixture()
        directory = self.artifacts / "synthetic_pipeline"
        directory.mkdir(exist_ok=True)
        files = []
        for i, chunk in enumerate([frame.iloc[::2], frame.iloc[1::2]], 1):
            path = self.artifacts / f"synthetic_{i}.parquet"
            pq.write_table(pa.Table.from_pandas(chunk, preserve_index=False), path)
            files.append(path)
        run = sf.Run(directory)
        manifest = sf.stage_inputs(run, files, sf.fingerprints(files))
        self.assertEqual(manifest["rows"], len(frame))
        self.assertEqual(manifest["vessels"], 3)
        nearest = lambda lon, lat: np.full(len(lon), np.inf)
        norm = lambda values: np.minimum(np.asarray(values, dtype=float) / 20, 1)
        references = (nearest, {}, {}, norm, norm, {"synthetic": True})
        observed, _, _ = sf.score_partitions(run, manifest, fb, references)
        for rfid, raw in frame.groupby("rfid_id"):
            one = raw.copy()
            one["rfid_time"] = (one.ts % 24).astype(int)
            one = one.sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
            scores = fb.score_vessel(one, nearest, None, {}, {}, norm, norm)
            expected = sf.summarize_vessel(rfid, one, scores, fb)
            self.assertEqual(expected, observed[rfid])
        repeated, _, resumed = sf.score_partitions(run, manifest, fb, references)
        self.assertEqual(resumed, 3)
        self.assertEqual(repeated, observed)

    def test_ties_internal_gaps_and_radius(self):
        one = pd.DataFrame({"ts": [sf.START_H, sf.START_H, sf.START_H + 4],
                            "cen_lon": [127., 127., 127.02], "cen_lat": [35., 35., 35.]})
        scored = pd.DataFrame({"score": [.8, .8, np.nan], "source_ordinal": [20, 10, 1],
                               "ts": [sf.START_H, sf.START_H + 1, sf.START_H + 4],
                               "state": ["first", "tie winner", "missing"]})
        rec = sf.summarize_vessel("synthetic", one, scored, fb)
        self.assertEqual(rec["peak_state"], "tie winner")
        self.assertEqual(rec["n_unique_hours"], 2)
        self.assertEqual(rec["gap_total_h"], 3.)
        self.assertEqual(rec["n_finite_scores"], 2)
        self.assertAlmostEqual(rec["activity_radius_km"], fb.haversine_m(127, 35, 127.02, 35) / 1000)

    def test_no_finite_scores_retained(self):
        one = pd.DataFrame({"ts": [sf.START_H], "cen_lon": [np.nan], "cen_lat": [np.nan]})
        scored = pd.DataFrame({"score": [np.nan]})
        rec = sf.summarize_vessel("synthetic", one, scored, fb)
        self.assertIsNone(rec["peak_score"])
        self.assertIsNone(rec["peak_ts"])
        self.assertIsNone(rec["activity_radius_km"])
        self.assertEqual(rec["n_rows"], 1)
        self.assertEqual(rec["n_finite_scores"], 0)

    def test_timestamp_period_rejects_outside_input(self):
        frame = self.fixture().iloc[:1].copy()
        frame.loc[:, "ts"] = sf.END_H
        with self.assertRaisesRegex(ValueError, "outside approved"):
            sf.validate_batch(pa.Table.from_pandas(frame, preserve_index=False), "synthetic")

    def test_partial_checkpoint_tail_preserved(self):
        path = self.artifacts / "partial.jsonl"
        record = {"rfid_id": "synthetic", "n_rows": 2}
        path.write_bytes(json.dumps(record).encode() + b'\n{"rfid_id":')
        observed = sf.read_checkpoints(path)
        self.assertEqual(observed, {"synthetic": record})
        self.assertEqual(path.read_bytes(), json.dumps(record).encode() + b"\n")
        self.assertTrue(list(self.artifacts.glob("checkpoint_interrupted_tail_*.bin")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
