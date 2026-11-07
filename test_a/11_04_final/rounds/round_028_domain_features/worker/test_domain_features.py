from __future__ import annotations

import csv
import ctypes
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

import domain_features as df


def wkt(points: list[tuple[float, float]]) -> str:
    body = ", ".join(f"{x:.8f} {y:.8f}" for x, y in points)
    return f"MULTILINESTRING (({body}))"


class ParseAndFeatureTests(unittest.TestCase):
    def test_parser_preserves_part_boundaries(self):
        parts = df.parse_multilinestring(
            "MULTILINESTRING ((0 0, 0.001 0), (1 1, 1.001 1))"
        )
        self.assertEqual(len(parts), 2)
        self.assertEqual([len(part) for part in parts], [2, 2])

    def test_coordinate_order_requires_explicit_confirmation(self):
        result = df.extract_row_features(wkt([(0, 0), (0.001, 0)]))
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "coordinate_order_unconfirmed")

    def test_turn_sign_reversal_and_exact_duplicate_collapse(self):
        points = [
            (0.0, 0.0), (0.001, 0.0), (0.001, 0.001),
            (0.001, 0.001),  # exact adjacent duplicate only
            (0.0, 0.001), (0.0, 0.002),
        ]
        result = df.extract_row_features(wkt(points), coordinate_order_confirmed=True)
        self.assertTrue(result.valid, result.reason)
        self.assertEqual(result.turn_numerator, 1)
        self.assertEqual(result.turn_denominator, 2)
        self.assertAlmostEqual(result.turn_numerator / result.turn_denominator, 0.5)

    def test_turn_pairs_never_cross_parts(self):
        source = (
            "MULTILINESTRING ((0 0, 0.001 0, 0.001 0.001), "
            "(1 1, 1.001 1, 1.001 1.001))"
        )
        result = df.extract_row_features(source, coordinate_order_confirmed=True)
        self.assertTrue(result.valid, result.reason)
        self.assertEqual(result.turn_numerator, 0)
        self.assertEqual(result.turn_denominator, 0)

    def test_return_vertex_requires_500m_prior_path_and_within_100m(self):
        inside = wkt([(0.0, 0.0), (0.006, 0.0), (0.0008, 0.0)])
        result = df.extract_row_features(inside, coordinate_order_confirmed=True)
        self.assertTrue(result.valid, result.reason)
        self.assertEqual(result.return_numerator, 1)
        self.assertEqual(result.return_denominator, 2)
        self.assertAlmostEqual(result.return_numerator / result.return_denominator, 0.5)

        outside = wkt([(0.0, 0.0), (0.006, 0.0), (0.00091, 0.0)])
        result_outside = df.extract_row_features(outside, coordinate_order_confirmed=True)
        self.assertTrue(result_outside.valid, result_outside.reason)
        self.assertEqual(result_outside.return_numerator, 0)
        self.assertEqual(result_outside.return_denominator, 2)

    def test_zero_length_intervals_are_collapsed_and_zero_denominators_stay_missing(self):
        result = df.extract_row_features(
            wkt([(0.0, 0.0), (0.0, 0.0)]), coordinate_order_confirmed=True
        )
        self.assertTrue(result.valid, result.reason)
        self.assertEqual(result.turn_denominator, 0)
        self.assertEqual(result.return_denominator, 0)
        accumulator = df.VesselAccumulator()
        accumulator.add(result)
        output = accumulator.output_row("fixture")
        self.assertEqual(output["turn_sign_reversal_fraction"], "")
        self.assertEqual(output["nonlocal_return_vertex_fraction"], "")

    def test_nonlocal_return_does_not_cross_parts(self):
        source = (
            "MULTILINESTRING ((0 0, 0.006 0), "
            "(0.006 0, 0 0))"
        )
        result = df.extract_row_features(source, coordinate_order_confirmed=True)
        self.assertTrue(result.valid, result.reason)
        self.assertEqual(result.return_numerator, 0)
        self.assertEqual(result.return_denominator, 2)

    def test_empty_missing_malformed_one_point_and_out_of_range_are_distinct(self):
        cases = [
            (None, "missing_wkt"),
            ("MULTILINESTRING EMPTY", "empty_geometry"),
            ("MULTILINESTRING ((0 0, 0.001 0)", "malformed_wkt"),
            ("MULTILINESTRING ((0 0))", "part_too_short"),
            ("MULTILINESTRING ((181 0, 181 0.001))", "coordinate_out_of_lonlat_range"),
        ]
        for text, expected in cases:
            with self.subTest(expected=expected):
                result = df.extract_row_features(text, coordinate_order_confirmed=True)
                self.assertFalse(result.valid)
                self.assertEqual(result.reason, expected)

    def test_long_jump_and_row_caps_reject_the_entire_row(self):
        long_jump = wkt([(0.0, 0.0), (0.1, 0.0)])
        result = df.extract_row_features(long_jump, coordinate_order_confirmed=True)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "adjacent_segment_over_10km")

        capped_points = df.extract_row_features(
            wkt([(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]),
            coordinate_order_confirmed=True,
            max_points=2,
        )
        self.assertEqual(capped_points.reason, "point_limit_exceeded")
        capped_chars = df.extract_row_features(
            "MULTILINESTRING ((0 0, 0.001 0))",
            coordinate_order_confirmed=True,
            max_wkt_chars=8,
        )
        self.assertEqual(capped_chars.reason, "wkt_char_limit_exceeded")

    def test_candidate_comparison_budget_is_an_explicit_row_abstention(self):
        old_budget = df.MAX_RETURN_DISTANCE_CHECKS_PER_ROW
        try:
            df.MAX_RETURN_DISTANCE_CHECKS_PER_ROW = 0
            result = df.extract_row_features(
                wkt([(0.0, 0.0), (0.006, 0.0), (0.0, 0.0)]),
                coordinate_order_confirmed=True,
            )
        finally:
            df.MAX_RETURN_DISTANCE_CHECKS_PER_ROW = old_budget
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "return_comparison_budget_exceeded")

    def test_vessel_aggregation_pools_counts_not_row_fractions(self):
        first = df.extract_row_features(
            wkt([(0, 0), (0.001, 0), (0.001, 0.001), (0, 0.001), (0, 0.002)]),
            coordinate_order_confirmed=True,
        )
        second = df.extract_row_features(
            wkt([(0, 0), (0.001, 0), (0.001, 0.001), (0.002, 0.001)]),
            coordinate_order_confirmed=True,
        )
        accumulator = df.VesselAccumulator()
        accumulator.add(first)
        accumulator.add(second)
        output = accumulator.output_row("fixture")
        self.assertEqual(output["turn_sign_reversal_numerator"], 2)
        self.assertEqual(output["turn_sign_reversal_denominator"], 3)
        self.assertAlmostEqual(output["turn_sign_reversal_fraction"], 2 / 3)


class StreamingInputTests(unittest.TestCase):
    def test_trailing_unnamed_source_columns_are_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "month.csv"
            headers, id_index, geom_index = df._headers_and_indices(
                "part_dt,rfid_id,rfid_time,geom,fishing_code,,,,,\n", path
            )
            self.assertEqual((len(headers), id_index, geom_index), (10, 1, 3))
            with self.assertRaises(df.ExtractionError):
                df._headers_and_indices("rfid_id,,geom,rfid_id\n", path)
            with self.assertRaises(df.ExtractionError):
                df._headers_and_indices("rfid_id,,geom\n", path)

    def test_physical_line_pilot_uses_only_id_and_geom_and_keeps_missing_roster_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "train.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["rfid_id", "geom", "fishing_code"])
                writer.writerow(["A", "MULTILINESTRING ((0 0, 0.006 0, 0.0008 0))", "label-secret"])
                writer.writerow(["B", "", "label-secret"])
                writer.writerow(["C", "MALFORMED", "label-secret"])
                writer.writerow(["D", "MALFORMED", "label-secret"])

            ids = {"A", "B", "missing"}
            accumulators, manifest = df.extract_csv_files(
                [source],
                roster_ids=ids,
                coordinate_order_confirmed=True,
                physical_line_limit=3,  # header + first two physical data lines
            )
            self.assertEqual(set(accumulators), ids)
            self.assertEqual(manifest["totals"]["logical_data_rows"], 2)
            self.assertEqual(manifest["totals"].get("non_roster_rows_skipped", 0), 0)
            self.assertEqual(accumulators["A"].geometry_valid_rows, 1)
            self.assertEqual(accumulators["B"].geometry_missing_rows, 1)
            self.assertEqual(accumulators["missing"].rows_seen, 0)
            self.assertEqual(manifest["csv_columns_used"], ["rfid_id", "geom"])
            self.assertFalse(manifest["label_values_read"])
            self.assertTrue(manifest["physical_line_pilot"])

            output = Path(temp) / "pilot_features.csv"
            manifest_path = Path(temp) / "pilot_manifest.json"
            df.write_feature_outputs(accumulators, output, manifest, manifest_path)
            with output.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
            self.assertEqual([row["rfid_id"] for row in rows], ["A", "B", "missing"])
            self.assertNotIn("fishing_code", reader.fieldnames)
            self.assertNotIn("label-secret", output.read_text(encoding="utf-8-sig"))

    def test_roster_loader_filters_to_fit_only(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is not available")
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "fold0.npz"
            ids = np.asarray([f"fit-{i:04d}" for i in range(3144)] + ["select", "outer"])
            roles = np.asarray(["FIT"] * 3144 + ["INNER_SELECT", "OUTER"])
            np.savez(archive, rfid_ids=ids, roles=roles, y=np.zeros(len(ids)))
            selected = df.load_roster_npz(archive)
            self.assertEqual(len(selected), 3144)
            self.assertIn("fit-0000", selected)
            self.assertNotIn("select", selected)
            self.assertNotIn("outer", selected)

    def test_existing_output_is_not_overwritten_without_explicit_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "derived_features.csv"
            manifest_path = Path(temp) / "manifest.json"
            output.write_text("keep", encoding="utf-8")
            with self.assertRaises(df.ExtractionError):
                df.write_feature_outputs({}, output, {}, manifest_path)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")

    def test_resource_recorder_preserves_prior_stage_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "resource_checks.json"
            original_snapshot = df._memory_snapshot
            try:
                df._memory_snapshot = lambda: (4 * 1024**3, 100 * 1024**2, [])
                check = df._resource_recorder(path, execution_controls={
                    "windows_priority": "BELOW_NORMAL_PRIORITY_CLASS"
                })
                check("entry", 1.5)
                check("before_month_1", 1.0)
            finally:
                df._memory_snapshot = original_snapshot
            receipt = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([item["stage"] for item in receipt["checks"]], ["entry", "before_month_1"])
            self.assertTrue(all(item["passed"] for item in receipt["checks"]))

    @unittest.skipUnless(os.name == "nt", "Windows priority class is platform-specific")
    def test_belownormal_priority_api_uses_full_width_process_handle(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        kernel32.GetPriorityClass.restype = ctypes.c_ulong
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.SetPriorityClass.restype = ctypes.c_int
        handle = kernel32.GetCurrentProcess()
        previous = kernel32.GetPriorityClass(handle)
        try:
            controls = df._set_low_priority_and_single_thread()
            self.assertEqual(controls["windows_priority"], "BELOW_NORMAL_PRIORITY_CLASS")
        finally:
            kernel32.SetPriorityClass(handle, previous)


if __name__ == "__main__":
    unittest.main()
