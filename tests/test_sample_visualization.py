"""Safety and missing-data boundaries for the offline synthetic dashboard."""

import json
from pathlib import Path
import re
import tempfile
import unittest

from fishing_demo.visualization import write_dashboard


class SampleVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "dashboard.html"

    def embedded_data(self, html):
        match = re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>',
                          html, re.DOTALL)
        self.assertIsNotNone(match)
        return match.group(1), json.loads(match.group(1))

    def test_payload_is_embedded_once_and_injection_is_inert(self):
        hostile = '</script><script>alert("sample")</script>&<>\u2028\u2029'
        report = {"source_type": "synthetic", "class_names": [hostile, "sweep", "turn"],
                  "limitations": [hostile]}
        predictions = [{"sample_id": hostile, "vessel_id": "v&1", "split": "test",
                        "parts": [[[0, 0], [3, 4]], [[100, 0], [100, 12]]],
                        "true_label": 0, "predicted_label": 1,
                        "probabilities": [0.2, 0.7, 0.1], "features": [None, 5]}]
        written = write_dashboard(report, predictions, self.path)
        self.assertEqual(written, self.path)
        html = self.path.read_text(encoding="utf-8")
        raw, data = self.embedded_data(html)
        self.assertEqual(data, {"report": report, "predictions": predictions})
        self.assertNotIn(hostile, html)
        self.assertNotIn("<", raw)
        self.assertNotIn(">", raw)
        self.assertNotIn("&", raw)
        self.assertNotIn("\u2028", raw)
        self.assertNotIn("\u2029", raw)
        self.assertIn(r"\u003c/script\u003e", raw)
        self.assertEqual(html.count('id="dashboard-data"'), 1)
        self.assertEqual(len(re.findall(r"<script(?:\s|>)", html)), 2)
        self.assertNotIn(".innerHTML", html)
        self.assertNotIn("insertAdjacentHTML", html)
        self.assertNotRegex(html, r'<(?:script|link|img)[^>]+(?:src|href)="https?://')
        self.assertNotIn("fetch(", html)
        self.assertNotIn("XMLHttpRequest", html)
        self.assertIn("실제 지도가 아닙니다", html)
        self.assertIn("사고 확률이나 사고 판정이 아닙니다", html)

    def test_none_and_empty_inputs_are_viewable(self):
        for report, predictions in ((None, None), ({}, []),
                                    ({"metrics": None, "candidates": None,
                                      "selected_model": None, "feature_units": None},
                                     [{"sample_id": None, "parts": None,
                                       "features": None, "probabilities": None}])):
            with self.subTest(report=report):
                write_dashboard(report, predictions, self.path)
                html = self.path.read_text(encoding="utf-8")
                _, data = self.embedded_data(html)
                self.assertEqual(data["report"], report or {})
                self.assertEqual(data["predictions"], predictions or [])
                self.assertIn("표시할 유효 XY 좌표가 없습니다", html)
                self.assertIn("조건에 맞는 표본 없음", html)

    def test_nonfinite_results_become_missing_without_mutating_inputs(self):
        report = {"metrics": {"test": {"accuracy": float("nan"),
                                         "nll": float("inf")}},
                  "nested": (float("-inf"), 1.0)}
        predictions = [{"features": [float("nan"), 0.0]}]
        write_dashboard(report, predictions, self.path)
        _, data = self.embedded_data(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["report"]["metrics"]["test"],
                         {"accuracy": None, "nll": None})
        self.assertEqual(data["report"]["nested"], [None, 1.0])
        self.assertEqual(data["predictions"][0]["features"], [None, 0.0])
        self.assertIsInstance(report["nested"], tuple)

    def test_wrong_top_level_types_fail_before_writing(self):
        for report, predictions in (([], []), ({}, "not a record collection"),
                                    ({}, {"sample_id": "not a sequence"})):
            with self.subTest(report=report, predictions=predictions):
                with self.assertRaises(TypeError):
                    write_dashboard(report, predictions, self.path)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
