"""CLI boundary tests using synthetic fixtures, never competition data."""

import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "inspect_data.py"
SPEC = importlib.util.spec_from_file_location("_inspect_data_for_tests", SCRIPT)
INSPECT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INSPECT
SPEC.loader.exec_module(INSPECT)


class GeometrySubsetTests(unittest.TestCase):
    def test_malformed_structure_and_keyword_are_rejected(self):
        cases = {
            "MULTILINESTRINGLIKE ((1 2, 3 4))": "geom_prefix_mismatch",
            "MULTILINESTRING private-garbage": "geom_malformed_structure",
            "MULTILINESTRING ((1 2, 3 4)) private-trailing-token": "geom_malformed_structure",
            "MULTILINESTRING (1 2, 3 4)": "geom_malformed_structure",
            "MULTILINESTRING ((1 2, 3 4)": "geom_malformed_structure",
            "MULTILINESTRING (((1 2, 3 4)))": "geom_malformed_structure",
            "MULTILINESTRING ((1 2,, 3 4))": "geom_malformed_structure",
            "MULTILINESTRING ((1, 3 4))": "geom_malformed_structure",
            "MULTILINESTRING ((1 2 3, 4 5 6))": "geom_malformed_structure",
            "MULTILINESTRING ((1+2, 3 4))": "geom_malformed_structure",
            "MULTILINESTRING EMPTY trailing": "geom_malformed_structure",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                validation = INSPECT._validate_geometry(value)
                self.assertEqual(validation.state, "invalid")
                self.assertEqual(validation.issue_code, expected)
                self.assertEqual(validation.part_point_counts, ())

    def test_each_part_requires_two_points(self):
        for value in ("MULTILINESTRING ((1 2))", "MULTILINESTRING ((1 2, 3 4), (5 6))"):
            with self.subTest(value=value):
                validation = INSPECT._validate_geometry(value)
                self.assertEqual(validation.state, "invalid")
                self.assertEqual(validation.issue_code, "geom_part_too_short")

    def test_nonfinite_values_and_decimal_overflow_are_rejected(self):
        for number in ("NaN", "inf", "-Infinity", "+INF", "1e309", "-1e309"):
            with self.subTest(number=number):
                validation = INSPECT._validate_geometry(f"MULTILINESTRING (({number} 2, 3 4))")
                self.assertEqual(validation.state, "invalid")
                self.assertEqual(validation.issue_code, "geom_non_finite_coordinate")

    def test_explicit_dimensions_and_ewkt_are_unsupported(self):
        cases = [
            "MULTILINESTRING Z ((1 2 3, 4 5 6))",
            "MULTILINESTRING M ((1 2 3, 4 5 6))",
            "MULTILINESTRING ZM ((1 2 3 4, 5 6 7 8))",
            "SRID=4326;MULTILINESTRING ((1 2, 3 4))",
        ]
        for value in cases:
            with self.subTest(value=value):
                validation = INSPECT._validate_geometry(value)
                self.assertEqual(validation.state, "unsupported")
                self.assertEqual(validation.issue_code, "geom_unsupported_representation")

    def test_whole_empty_is_recognized_but_unanalyzable(self):
        validation = INSPECT._validate_geometry("  multilinestring EMPTY  ")
        self.assertEqual(validation.state, "empty")
        self.assertEqual(validation.issue_code, "geom_empty")
        self.assertEqual(validation.part_point_counts, ())

    def test_parts_remain_separate_and_numbers_support_decimal_exponents(self):
        validation = INSPECT._validate_geometry(
            "  mUlTiLiNeStRiNg ((+1.0 -2e0, .3 4.), (10000 20000, 30000 40000, 50000 60000))  "
        )
        self.assertEqual(validation.state, "structured_nonempty")
        self.assertIsNone(validation.issue_code)
        self.assertEqual(validation.part_point_counts, (2, 3))

    def test_lonlat_bounds_require_explicit_assumption_and_include_boundaries(self):
        outside = "MULTILINESTRING ((181 45, 182 46))"
        self.assertIsNone(INSPECT._validate_geometry(outside).issue_code)
        assumed = INSPECT._validate_geometry(outside, "lonlat")
        self.assertEqual(assumed.state, "structured_nonempty")
        self.assertEqual(assumed.issue_code, "geom_lonlat_out_of_range")
        boundary = INSPECT._validate_geometry("MULTILINESTRING ((-180 -90, 180 90))", "lonlat")
        self.assertIsNone(boundary.issue_code)


class InspectDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              text=True, capture_output=True)

    def write_csv(self, name, rows, header=None, encoding="utf-8"):
        path = self.root / name
        with path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header or ["part_dt", "rfid_id", "rfid_time", "geom"])
            writer.writerows(rows)
        return path

    def test_quoted_multiline_record_and_sample_cutoff_has_unknown_total(self):
        path = self.write_csv("tracks.csv", [
            ["20260102", "vessel\nprivate", "2", "MULTILINESTRING ((1 2, 3 4))"],
            ["20260103", "other", "3", "MULTILINESTRING EMPTY"],
        ])
        result = self.run_cli(path, "--sample-rows", 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(report["sample_rows"], 1)
        self.assertTrue(report["sample_truncated"])
        self.assertIsNone(report["total_rows"])
        self.assertEqual(report["geometry_validation"], INSPECT.GEOMETRY_NOTE)
        self.assertNotIn("vessel", result.stdout)

    def test_invalid_calendar_date_and_hour_report_nonzero(self):
        path = self.write_csv("bad.csv", [["20260230", "id", "24", "POINT (1 2)"]])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["status"], "sample_issues_detected")
        self.assertEqual(report["issue_counts"]["invalid_part_dt"], 1)
        self.assertEqual(report["issue_counts"]["invalid_rfid_time"], 1)
        self.assertEqual(report["issue_counts"]["geom_prefix_mismatch"], 1)

    def test_duplicate_header_suppresses_name_based_semantics(self):
        path = self.write_csv("duplicate.csv", [["20260230", "id", "24", "MULTILINESTRING EMPTY"]],
                              header=["part_dt", "rfid_id", "rfid_time", "geom", "geom"])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["issue_counts"]["duplicate_header_names"], 1)
        self.assertEqual(report["semantic_validation"], "skipped_invalid_header")
        self.assertEqual(report["field_empty_counts"], {})

    def test_strict_encoding_error_returns_inspection_failure(self):
        path = self.root / "bad.csv"
        path.write_bytes(b"part_dt,rfid_id,rfid_time,geom\n\xff\n")
        result = self.run_cli(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("encoding_error", json.loads(result.stdout)["scanned_files"][0]["error"])

    def test_missing_header_does_not_echo_first_record_values(self):
        path = self.root / "no-header.csv"
        path.write_text("20260101,private-vessel-id,1,private-location\n", encoding="utf-8")
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertFalse(report["header_recognized"])
        self.assertEqual(report["header"], [])
        self.assertIsNone(report["total_rows"])
        self.assertNotIn("private-vessel-id", result.stdout)
        self.assertNotIn("private-location", result.stdout)

    def test_empty_required_values_are_reported_as_sample_issues(self):
        path = self.write_csv("empty-values.csv", [["20260101", "", "1", ""]])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["issue_counts"]["empty_required_values"], 2)

    def test_oversize_is_metadata_only(self):
        path = self.write_csv("large.csv", [["20260101", "id", "1", "MULTILINESTRING EMPTY"]])
        result = self.run_cli(path, "--max-bytes", 1)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["status"], "metadata_only_size_limit")
        self.assertIsNone(report["total_rows"])
        self.assertNotIn("header", report)

    def test_long_field_over_default_csv_limit_is_supported(self):
        path = self.write_csv("long.csv", [["20260101", "x" * 140_000, "1", "MULTILINESTRING ((1 2, 3 4))"]])
        result = self.run_cli(path, "--max-bytes", 300_000)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["sample_rows"], 1)
        self.assertNotIn("x" * 100, result.stdout)

    def test_large_configured_byte_limits_inspect_tiny_source_without_traceback(self):
        path = self.write_csv("tiny-source.csv", [
            ["20260101", "private-identifier", "1", "MULTILINESTRING ((1 2, 3 4))"],
        ])
        before = path.read_bytes()
        for limit in (sys.maxsize, sys.maxsize + 1):
            with self.subTest(limit=limit):
                result = self.run_cli(path, "--max-bytes", limit)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                report = json.loads(result.stdout)
                self.assertEqual(report["sampling_limits"]["max_bytes"], limit)
                entry = report["scanned_files"][0]
                self.assertEqual(entry["size_bytes"], len(before))
                self.assertEqual(entry["sample_rows"], 1)
                self.assertEqual(entry["total_rows"], 1)
                self.assertFalse(entry["sample_truncated"])
                self.assertEqual(entry["sampling_stop_reason"], "end_of_file")
                self.assertFalse(report["real_data_evaluation_performed"])
                self.assertNotIn("private-identifier", result.stdout)
                self.assertEqual(path.read_bytes(), before)

    def test_unsupported_csv_field_limit_returns_safe_inspection_error(self):
        path = self.write_csv("safe-limit-error.csv", [])
        before = path.read_bytes()
        args = INSPECT._parser().parse_args([str(path)])
        with mock.patch.object(INSPECT.csv, "field_size_limit", side_effect=OverflowError("private-runtime-detail")):
            report = INSPECT._inspect(path, path.name, args)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["error"], "csv_field_size_limit_unsupported")
        self.assertNotIn("private-runtime-detail", json.dumps(report))
        self.assertEqual(path.read_bytes(), before)

    def test_geometry_summary_uses_safe_codes_and_record_numbers(self):
        private_coordinate = "123.456789 -35.987654"
        path = self.write_csv("geometry.csv", [
            ["20260101", "private-vessel-id", "1",
             f"MULTILINESTRING (({private_coordinate}, 124 -36), (125 -37, 126 -38, 127 -39))"],
            ["20260101", "private-vessel-id", "2", "MULTILINESTRING garbage-private-location"],
            ["20260101", "private-vessel-id", "3", "MULTILINESTRING ((1e309 2, 3 4))"],
            ["20260101", "private-vessel-id", "4", "MULTILINESTRING EMPTY"],
            ["20260101", "private-vessel-id", "5", "MULTILINESTRING Z ((1 2 3, 4 5 6))"],
        ])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(report["geometry_counts"], {
            "checked_values": 5, "structured_nonempty": 1, "empty": 1,
            "unsupported": 1, "invalid": 2, "parts": 2, "points": 5,
            "coordinate_out_of_range": 0,
        })
        self.assertEqual(report["geometry_issue_rows"], [
            {"data_row": 2, "code": "geom_malformed_structure"},
            {"data_row": 3, "code": "geom_non_finite_coordinate"},
            {"data_row": 4, "code": "geom_empty"},
            {"data_row": 5, "code": "geom_unsupported_representation"},
        ])
        self.assertIn("not a full OGC WKT validator", report["geometry_supported_subset"])
        self.assertEqual(report["geometry_issue_row_numbering"], "one_based_data_records_excluding_header")
        for secret in (private_coordinate, "private-vessel-id", "garbage-private-location", "1e309"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_empty_geometry_is_syntactically_recognized_and_flagged(self):
        path = self.write_csv("empty-geometry.csv", [["20260101", "id", "1", "MULTILINESTRING EMPTY"]])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["geometry_counts"]["empty"], 1)
        self.assertEqual(report["geometry_counts"]["invalid"], 0)
        self.assertEqual(report["issue_counts"]["geom_empty"], 1)
        self.assertEqual(report["field_empty_counts"]["geom"], 0)

    def test_coordinate_range_checks_are_opt_in_and_do_not_verify_crs(self):
        path = self.write_csv("coordinate-assumption.csv", [
            ["20260101", "id", "1", "MULTILINESTRING ((181 45, 182 46))"],
        ])
        default = self.run_cli(path)
        default_report = json.loads(default.stdout)["scanned_files"][0]
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(default_report["coordinate_validation"], "not_checked_crs_unconfirmed")
        assumed = self.run_cli(path, "--coordinate-assumption", "lonlat")
        result = json.loads(assumed.stdout)
        report = result["scanned_files"][0]
        self.assertEqual(assumed.returncode, 1)
        self.assertEqual(report["issue_counts"]["geom_lonlat_out_of_range"], 1)
        self.assertEqual(report["geometry_counts"]["structured_nonempty"], 1)
        self.assertEqual(report["geometry_counts"]["coordinate_out_of_range"], 1)
        self.assertEqual(report["coordinate_validation"], "bounds_checked_under_explicit_lonlat_assumption")
        self.assertEqual(result["coordinate_assumption"], "lonlat")
        self.assertFalse(report["crs_verified"])
        self.assertFalse(report["distance_calculation_performed"])

    def test_accidental_known_header_does_not_echo_unknown_first_record_values(self):
        secrets = ["private-vessel-header", "123.456789 -35.987654"]
        path = self.write_csv("accidental-header.csv", [["hidden-id", "", "hidden-coordinate"]],
                              header=[secrets[0], "geom", secrets[1]])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertTrue(report["header_recognized"])
        self.assertEqual(report["header"], ["geom"])
        self.assertEqual(report["unknown_header_column_count"], 2)
        self.assertEqual(report["field_empty_counts"], {"geom": 1})
        self.assertEqual(report["issue_counts"]["missing_required_columns"], 3)
        self.assertEqual(report["issue_counts"]["empty_required_values"], 1)
        for secret in (*secrets, "hidden-id", "hidden-coordinate"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_valid_known_header_with_unknown_columns_uses_only_whitelisted_report_keys(self):
        path = self.write_csv("extra-columns.csv", [
            ["20260101", "private-id", "1", "MULTILINESTRING ((1 2, 3 4))", "private-coordinate"],
        ], header=["part_dt", "rfid_id", "rfid_time", "geom", "private-header-name"])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["header"], list(INSPECT.REQUIRED))
        self.assertEqual(report["header_column_count"], 5)
        self.assertEqual(report["unknown_header_column_count"], 1)
        self.assertEqual(set(report["field_empty_counts"]), set(INSPECT.REQUIRED))
        for secret in ("private-header-name", "private-id", "private-coordinate"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_candidate_key_collisions_are_sample_scoped_counts_without_identifiers(self):
        geometry = "MULTILINESTRING ((1 2, 3 4))"
        path = self.write_csv("candidate-key.csv", [
            ["20260101", "private-identifier", "1", geometry],
            ["20260101", "private-identifier", "1", "MULTILINESTRING ((5 6, 7 8))"],
            ["20260101", "other-private-identifier", "1", geometry],
            ["20260101", "private-identifier", "1", geometry],
        ])
        result = self.run_cli(path, "--sample-rows", 3)
        report = json.loads(result.stdout)["scanned_files"][0]
        key_check = report["candidate_key_check"]
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(key_check["scope"], "inspected_sample_only")
        self.assertEqual(key_check["columns"], list(INSPECT.KEY_COLUMNS))
        self.assertEqual(key_check["eligible_rows"], 3)
        self.assertEqual(key_check["distinct_keys"], 2)
        self.assertEqual(key_check["collision_rows"], 1)
        self.assertEqual(key_check["collision_groups"], 1)
        self.assertFalse(key_check["deduplication_performed"])
        self.assertFalse(key_check["uniqueness_requirement_verified"])
        self.assertTrue(report["sample_truncated"])
        self.assertNotIn("private-identifier", result.stdout + result.stderr)

    def test_lookahead_parse_error_preserves_inspected_sample_and_safe_error_code(self):
        path = self.write_csv("lookahead-error.csv", [
            ["20260101", "private-id", "1", "MULTILINESTRING ((1 2, 3 4))"],
        ])
        with path.open("a", encoding="utf-8", newline="") as stream:
            stream.write('"private-broken-record,123.456789 -35.987654')
        result = self.run_cli(path, "--sample-rows", 1)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["sample_rows"], 1)
        self.assertEqual(report["geometry_counts"]["structured_nonempty"], 1)
        self.assertEqual(report["candidate_key_check"]["eligible_rows"], 1)
        self.assertEqual(report["issue_counts"], {"csv_parse_error_after_sample": 1})
        self.assertEqual(report["csv_parse_error"], {
            "code": "csv_parse_error", "stage": "after_sample", "next_data_row": 2,
        })
        self.assertEqual(report["sampling_stop_reason"], "csv_parse_error_after_sample")
        self.assertTrue(report["sample_truncated"])
        self.assertIsNone(report["total_rows"])
        for secret in ("private-id", "private-broken-record", "123.456789 -35.987654"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_parse_error_within_sample_is_reported_separately(self):
        path = self.write_csv("sample-error.csv", [
            ["20260101", "id", "1", "MULTILINESTRING ((1 2, 3 4))"],
        ])
        with path.open("a", encoding="utf-8", newline="") as stream:
            stream.write('"unclosed-private-record')
        result = self.run_cli(path, "--sample-rows", 2)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["sample_rows"], 1)
        self.assertEqual(report["issue_counts"], {"csv_parse_error_in_sample": 1})
        self.assertEqual(report["csv_parse_error"]["stage"], "in_sample")
        self.assertNotIn("unclosed-private-record", result.stdout + result.stderr)

    def test_long_invalid_hour_does_not_discard_sample_or_expose_value(self):
        private_hour = "9" * 5000
        path = self.write_csv("long-hour.csv", [
            ["20260101", "id", private_hour, "MULTILINESTRING ((1 2, 3 4))"],
        ])
        result = self.run_cli(path)
        report = json.loads(result.stdout)["scanned_files"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["sample_rows"], 1)
        self.assertEqual(report["issue_counts"], {"invalid_rfid_time": 1})
        self.assertNotIn(private_hour, result.stdout + result.stderr)

    def test_unexpected_value_error_is_not_copied_into_report(self):
        path = self.write_csv("safe-exception.csv", [])
        args = INSPECT._parser().parse_args([str(path)])
        with mock.patch.object(INSPECT, "_csv_report", side_effect=ValueError("private-row-value 123.456789")):
            report = INSPECT._inspect(path, path.name, args)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["error"], "inspection_value_error")
        self.assertNotIn("private-row-value", json.dumps(report))

    def test_external_output_keeps_source_bytes_and_report_metadata(self):
        path = self.write_csv("unchanged-source.csv", [
            ["20260101", "id", "1", "MULTILINESTRING ((1 2, 3 4))"],
        ])
        before = path.read_bytes()
        output = self.root / "report.json"
        result = self.run_cli(path, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["evidence"], "local_structure_inspection")
        self.assertFalse(report["real_data_evaluation_performed"])

    def test_symlink_input_file_is_rejected_or_directory_link_is_skipped(self):
        target = self.write_csv("target.csv", [])
        link = self.root / "link.csv"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        result = self.run_cli(link)
        self.assertEqual(result.returncode, 2)

    def test_output_inside_input_directory_is_rejected(self):
        folder = self.root / "input"
        folder.mkdir()
        self.write_csv("input/a.csv", [])
        output = folder / "report.json"
        result = self.run_cli(folder, "--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_hardlinked_output_to_input_is_rejected(self):
        source = self.write_csv("source.csv", [])
        report = self.root / "external-report.json"
        try:
            os.link(source, report)
        except OSError:
            self.skipTest("hard links unavailable")
        before = source.read_bytes()
        result = self.run_cli(source, "--output", report)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(source.read_bytes(), before)

    def test_gitkeep_placeholder_is_not_reported_as_data(self):
        folder = self.root / "folder"
        folder.mkdir()
        (folder / ".gitkeep").touch()
        result = self.run_cli(folder)
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["scanned_files"], [])
        self.assertEqual(report["placeholder_files_excluded"], 1)
        self.assertTrue(report["no_supported_data_found"])


if __name__ == "__main__":
    unittest.main()
