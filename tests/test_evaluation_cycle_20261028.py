import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "run_evaluation_cycle_20261028.py"
SPEC = importlib.util.spec_from_file_location("evaluation_cycle_20261028", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class GeometrySummaryTests(unittest.TestCase):
    def test_valid_multiline_geometry_returns_counts_and_aggregate_bounds(self):
        result = MOD.geometry_summary("MULTILINESTRING ((1 2, 3 4), (-5 6, 7 8, 9 10))")
        self.assertEqual(result["state"], "structured_nonempty")
        self.assertEqual(result["parts"], 2)
        self.assertEqual(result["points"], 5)
        self.assertEqual(result["bounds"], (-5.0, 2.0, 9.0, 10.0))
        self.assertNotIn("coordinates", result)

    def test_unsupported_and_malformed_are_redacted_to_codes(self):
        self.assertEqual(MOD.geometry_summary("SRID=4326;MULTILINESTRING ((1 2, 3 4))")["state"], "unsupported")
        result = MOD.geometry_summary("MULTILINESTRING ((PRIVATE 2, 3 4))")
        self.assertEqual(result["state"], "invalid")
        self.assertNotIn("PRIVATE", repr(result))


class EvaluationCycleInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.out = root / "out"
        self.source.mkdir()
        path = self.source / "fixture.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["part_dt", "rfid_id", "rfid_time", "geom", "fishing_code", ""])
            writer.writerow(["20260101", "PRIVATE_ID_A", "01", "MULTILINESTRING ((1 2, 3 4))", "자망", "x"])
            writer.writerow(["20260101", "PRIVATE_ID_A", "01", "MULTILINESTRING ((4 5, 6 7))", "자망", ""])

    def test_full_scan_hashes_and_caches_only_safe_derivatives(self):
        source_file = self.source / "fixture.csv"
        result = MOD.scan(self.source, self.out, None, progress_every=0)
        self.assertEqual(result["scan_mode"], "full")
        self.assertEqual(result["files"][0]["rows"], 2)
        self.assertEqual(result["candidate_duplicate_key_extra_rows"], 1)
        self.assertEqual(result["vessels_with_multiple_label_hashes"], 0)
        self.assertEqual(result["label_distribution"][0]["rows"], 2)
        self.assertEqual(result["feature_cache"]["feature_rows_including_invalid"], 2)
        self.assertEqual(result["files"][0]["sha256"], hashlib.sha256(source_file.read_bytes()).hexdigest())
        outputs = (self.out / "full_scan.json").read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE_ID_A", outputs)
        self.assertIn("자망", outputs)
        con = sqlite3.connect(self.out / "inspection_cache.sqlite3")
        try:
            names = {row[1] for row in con.execute("PRAGMA table_info(feature_samples)")}
            self.assertNotIn("geom", names)
            values = " ".join(str(row) for row in con.execute("SELECT * FROM feature_samples"))
            self.assertNotIn("PRIVATE_ID_A", values)
            self.assertIn("자망", values)
            self.assertNotIn("MULTILINESTRING", values)
        finally:
            con.close()
        cached = MOD.scan(self.source, self.out, None, progress_every=0)
        self.assertEqual(cached["files"][0]["status"], "cached")

    def test_sample_mode_is_explicitly_partial_and_bounded(self):
        result = MOD.scan(self.source, self.out, 128, progress_every=0)
        self.assertEqual(result["scan_mode"], "sample")
        self.assertEqual(result["files"][0]["status"], "partial_sample")
        self.assertTrue(result["files"][0]["partial"])
        self.assertIsNone(result["files"][0]["sha256"])

    def test_nonclass_label_is_hash_only_and_structurally_quarantined(self):
        root = Path(self.temp.name)
        source = root / "bad-source"
        out = root / "bad-out"
        source.mkdir()
        bad_label = "127.4 36.5"
        with (source / "vpass_1월 데이터.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["part_dt", "rfid_id", "rfid_time", "geom", "fishing_code"])
            writer.writerow(["20260230", "PRIVATE_BAD_ID", "24", "POINT (127.4 36.5)", bad_label])
        result = MOD.scan(source, out, None, progress_every=0)
        encoded = (out / "full_scan.json").read_text(encoding="utf-8")
        expected_hash = MOD.salted_hash(bad_label)
        self.assertNotIn(bad_label, encoded)
        self.assertNotIn("PRIVATE_BAD_ID", encoded)
        self.assertEqual(result["files"][0]["aggregate"]["quarantined_rows"], 1)
        self.assertEqual(result["unknown_label_buckets"], [{"label_sha256": expected_hash, "rows": 1}])
        self.assertEqual(result["label_distribution"], [])
        self.assertEqual(result["feature_cache"]["feature_rows_including_invalid"], 0)


if __name__ == "__main__":
    unittest.main()
