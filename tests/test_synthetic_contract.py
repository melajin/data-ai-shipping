"""Boundary and condition-change tests; fixtures are not real competition data."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_synthetic_contract.py"
FIXTURE = ROOT / "examples" / "fishing_contract_synthetic.json"


class SyntheticContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def run_cli(self, path, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), str(path), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8")

    def write_contract(self, data):
        path = self.root / "input.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_fixed_example_separates_calculation_learning_and_wrong_connection(self):
        before = FIXTURE.read_bytes()
        result = self.run_cli(FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report["observed_geometry"]), {"parts", "total_length_m"})
        self.assertEqual(report["observed_geometry"]["total_length_m"], 20)
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        counterexample = report["forbidden_connection_educational_counterexample"]
        self.assertFalse(counterexample["is_observed_feature"])
        self.assertGreater(counterexample["wrong_connected_length_m"], 114)
        self.assertEqual(report["technical_status"]["verification_kind"], "code_calculation_only")
        self.assertEqual(report["learning_status"]["achievement"], "unverified")
        self.assertEqual(FIXTURE.read_bytes(), before)

    def test_real_or_unknown_source_is_rejected_before_any_calculation(self):
        for source in ("real", "competition_data", "unknown", None):
            with self.subTest(source=source):
                data = copy.deepcopy(self.fixture)
                data["source_type"] = source
                result = self.run_cli(self.write_contract(data))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("source_type", result.stderr)

    def test_missing_or_unconfirmed_coordinate_and_observation_contract_is_rejected(self):
        cases = [
            ("coordinate_contract", "unit", "degrees"),
            ("coordinate_contract", "system", "unknown"),
            ("coordinate_contract", "axis_order", ["y", "x"]),
            ("coordinate_contract", "basis", "measured"),
            ("observation_contract", "point_order", "unknown"),
            ("observation_contract", "part_boundaries", "connect"),
            ("observation_contract", "measured_timestamps", "present"),
            ("observation_contract", "fishing_labels", "present"),
        ]
        for section, field, value in cases:
            with self.subTest(section=section, field=field):
                data = copy.deepcopy(self.fixture)
                data[section][field] = value
                result = self.run_cli(self.write_contract(data))
                self.assertEqual(result.returncode, 2)
                self.assertIn(section, result.stderr)
        data = copy.deepcopy(self.fixture)
        del data["coordinate_contract"]
        self.assertEqual(self.run_cli(self.write_contract(data)).returncode, 2)
        data = copy.deepcopy(self.fixture)
        data["parts"][0]["timestamps"] = [0, 1, 2]
        self.assertEqual(self.run_cli(self.write_contract(data)).returncode, 2)

    def test_nonfinite_boolean_missing_and_oversize_coordinates_are_rejected(self):
        for point in ([float("nan"), 0], [float("inf"), 0], [1e308, -1e308], [True, 0], [None, 0], [0], [0, 0, 0]):
            with self.subTest(point=point):
                data = copy.deepcopy(self.fixture)
                data["parts"][0]["points"][0] = point
                if point == [1e308, -1e308]:
                    data["parts"][0]["points"][1] = [-1e308, 1e308]
                result = self.run_cli(self.write_contract(data))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
        data = copy.deepcopy(self.fixture)
        data["parts"][0]["points"] = [[0, 0]]
        self.assertEqual(self.run_cli(self.write_contract(data)).returncode, 2)

    def test_translating_one_part_preserves_observed_length_but_changes_wrong_bridge(self):
        baseline = json.loads(self.run_cli(FIXTURE).stdout)
        data = copy.deepcopy(self.fixture)
        # Same 12 m vertical part, translated so the invented bridge is exactly 10 m.
        data["parts"][1]["points"] = [[6, 14], [6, 26]]
        forbidden = data["expected"]["forbidden_connection"]
        forbidden["bridge_lengths_m"][0] = {"value": 10, "hand_calculation": "sqrt(0^2 + 10^2) = 10 m; invented bridge only"}
        forbidden["wrong_connected_length_m"] = {"value": 30, "hand_calculation": "20 + 10 = 30 m; wrong connection only"}
        result = self.run_cli(self.write_contract(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["observed_geometry"], baseline["observed_geometry"])
        self.assertEqual(report["forbidden_connection_educational_counterexample"]["wrong_connected_length_m"], 30)
        self.assertNotEqual(report["forbidden_connection_educational_counterexample"]["wrong_connected_length_m"],
                            baseline["forbidden_connection_educational_counterexample"]["wrong_connected_length_m"])

    def test_zero_length_records_undefined_straightness_instead_of_zero(self):
        data = copy.deepcopy(self.fixture)
        data["parts"][0]["points"] = [[0, 0], [0, 0], [0, 0]]
        data["parts"][1]["points"] = [[10, 0], [10, 0]]
        for part in data["expected"]["parts"]:
            for segment in part["segment_lengths_m"]:
                segment.update(value=0, hand_calculation="coincident points: 0 m")
            for field in ("length_m", "displacement_m"):
                part[field].update(value=0, hand_calculation="coincident points: 0 m")
            part["straightness"].update(value=None, hand_calculation="L=0: D/L is undefined")
        data["expected"]["total_length_m"].update(value=0, hand_calculation="0 + 0 = 0 m")
        forbidden = data["expected"]["forbidden_connection"]
        forbidden["bridge_lengths_m"][0].update(value=10, hand_calculation="invented bridge: 10 m")
        forbidden["wrong_connected_length_m"].update(value=10, hand_calculation="wrong connection: 0 + 10 = 10 m")
        result = self.run_cli(self.write_contract(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        for part in report["observed_geometry"]["parts"]:
            self.assertIsNone(part["straightness"])
        ratio_checks = [check for check in report["checks"] if check["quantity"].endswith(".straightness")]
        self.assertEqual(len(ratio_checks), 2)
        self.assertTrue(all(check["undefined_reason"] == "zero_observed_length" for check in ratio_checks))

    def test_hand_calculation_mismatch_is_reported_and_has_nonzero_exit(self):
        data = copy.deepcopy(self.fixture)
        data["expected"]["total_length_m"]["value"] = 21
        result = self.run_cli(self.write_contract(data))
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        failed = [check for check in report["checks"] if not check["passed"]]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["quantity"], "total_length_m")
        self.assertEqual(failed[0]["signed_difference"], -1)
        self.assertEqual(report["technical_status"]["calculation_check"], "failed")

    def test_separate_output_and_source_alias_protection(self):
        source = self.write_contract(self.fixture)
        before = source.read_bytes()
        output = self.root / "report.json"
        result = self.run_cli(source, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["technical_status"]["calculation_check"], "passed")
        for alias in (source, self.root / "." / "input.json"):
            with self.subTest(alias=alias):
                rejected = self.run_cli(source, "--output", alias)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("source overwrite is forbidden", rejected.stderr)
                self.assertEqual(source.read_bytes(), before)
        hardlink = self.root / "alias.json"
        try:
            os.link(source, hardlink)
        except (OSError, NotImplementedError):
            self.skipTest("hard links unavailable on this filesystem")
        rejected = self.run_cli(source, "--output", hardlink)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(source.read_bytes(), before)

    def test_duplicate_json_key_is_rejected_instead_of_hiding_source_type(self):
        source = self.root / "duplicate.json"
        source.write_text('{"source_type":"real", "source_type":"synthetic_example"}', encoding="utf-8")
        result = self.run_cli(source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate key", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
