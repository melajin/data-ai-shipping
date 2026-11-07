"""Synthetic contract checks; no real-source scoring or detector evaluation."""

import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fishing_demo import causal_replay as replay


def config():
    return {
        "schema_version": "testb_realtime_config_v1", "mode": "contract_replay",
        "scoring": {"enabled": False, "adapter": None, "threshold": None,
                    "calibration_status": "unvalidated"},
        "disabled_operations": list(replay.DISABLED_OPERATIONS),
        "input": {"timestamp_format": "iso8601_with_offset", "real_time_basis_required": "confirmed",
                  "real_availability_required": "confirmed", "unknown_availability_policy": "abstain",
                  "late_event_policy": "quarantine", "duplicate_policy": "idempotent_conflict_quarantine"},
        "memory": {"max_vessels": 10000, "max_line_bytes": 65536,
                   "estimated_peak_mib": 128, "reserve_mib": 640},
        "evaluation": {"label_status": "provisional", "official_f1_enabled": False},
    }


def event(hour=0, vessel="synthetic-vessel", event_id=None, **updates):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hour)
    row = {
        "event_id": event_id or f"synthetic-event-{hour}", "vessel_id": vessel,
        "source_type": "synthetic", "time_basis": "assumed", "availability_status": "assumed",
        "interval_start": start.isoformat(), "interval_end": (start + timedelta(hours=1)).isoformat(),
        "available_at": (start + timedelta(hours=1, minutes=5)).isoformat(),
        "decision_at": (start + timedelta(hours=1, minutes=5)).isoformat(),
        "geometry": {"centroid_lon": 129.5, "centroid_lat": 35.5, "len_m": 800, "bbox_m": 500},
    }
    row.update(updates)
    return row


class CausalContractTests(unittest.TestCase):
    def setUp(self):
        self.engine = replay.CausalReplay(config())

    def assert_disabled(self, result):
        self.assertIsNone(result["score"])
        self.assertIsNone(result["alarm"])
        self.assertFalse(result["alert_emitted"])
        self.assertEqual(result["score_status"], "disabled")
        self.assertNotEqual(result["status"], "normal")

    def test_future_append_cannot_change_prefix_decisions(self):
        prefix = [event(0), event(1), event(1, vessel="synthetic-other", event_id="other-1")]
        future = [event(2), event(6), event(10, available_at="2026-01-02T00:00:00+00:00")]
        left, right = replay.CausalReplay(config()), replay.CausalReplay(config())
        expected = [left.decide(row) for row in prefix]
        actual = [right.decide(row) for row in prefix + future]
        self.assertEqual(expected, actual[:len(prefix)])
        self.assertTrue(all(row["status"] == "observed_unscored" for row in expected))
        for result in actual:
            self.assert_disabled(result)
        self.assertEqual(actual[-1]["reason"], "not_available_at_decision")

    def test_missing_availability_or_confirmation_abstains_without_state(self):
        for key, value, reason in (
                ("available_at", None, "missing_available_at"),
                ("available_at", "unknown", "missing_available_at"),
                ("availability_status", None, "unconfirmed_availability_status"),
                ("availability_status", "unknown", "unconfirmed_availability_status"),
                ("time_basis", "unknown", "unconfirmed_time_basis")):
            with self.subTest(key=key, value=value):
                engine = replay.CausalReplay(config())
                row = event(**{key: value})
                result = engine.decide(row)
                self.assertEqual((result["status"], result["reason"]), ("abstained", reason))
                self.assertEqual(engine.vessel_count, 0)
                self.assertEqual(engine.decide(event())["status"], "observed_unscored")

    def test_next_hour_and_delayed_availability_are_unavailable_now(self):
        rows = [event(1, decision_at="2026-01-01T01:05:00+00:00"),
                event(0, available_at="2026-01-01T03:00:00+00:00")]
        for row in rows:
            with self.subTest(row=row):
                result = self.engine.decide(row)
                self.assertEqual(result["status"], "quarantined")
                self.assertEqual(result["reason"], "not_available_at_decision")
        self.assertEqual(self.engine.decide(event())["status"], "observed_unscored")

    def test_naive_timestamps_abstain_and_malformed_timestamps_quarantine(self):
        for key in replay.TIME_FIELDS:
            with self.subTest(key=key):
                row = event()
                row[key] = row[key].removesuffix("+00:00")
                result = self.engine.decide(row)
                self.assertEqual(result["status"], "abstained")
                self.assertEqual(result["reason"], f"timezone_unknown_{key}")
        for value in ("garbage", "2026-01-01T00:00:00+24:00", "2026-01-01 00:00:00+00:00"):
            with self.subTest(value=value):
                result = self.engine.decide(event(interval_start=value))
                self.assertEqual(result["status"], "quarantined")

    def test_equivalent_offsets_obey_chronological_order(self):
        row = event(interval_start="2026-01-01T09:00:00+09:00",
                    interval_end="2026-01-01T10:00:00+09:00",
                    available_at="2026-01-01T10:05:00+09:00",
                    decision_at="2026-01-01T01:05:00Z")
        result = self.engine.decide(row)
        self.assertEqual(result["status"], "observed_unscored")
        self.assertEqual(result["evidence_level"], "synthetic_contract_check")

    def test_utc_year_overflow_and_invalid_offset_minutes_quarantine_then_continue(self):
        for timestamp in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00",
                          "2026-01-01T00:00:00+00:60", "2026-01-01T00:00:00+01:99"):
            with self.subTest(timestamp=timestamp):
                result = self.engine.decide(event(interval_start=timestamp))
                self.assertEqual((result["status"], result["reason"]),
                                 ("quarantined", "invalid_interval_start"))
        self.assertEqual(self.engine.decide(event())["status"], "observed_unscored")

    def test_interval_and_availability_order_are_enforced(self):
        rows = [event(interval_start="2026-01-01T01:00:00+00:00"),
                event(interval_end="2025-12-31T23:00:00+00:00"),
                event(available_at="2026-01-01T00:59:00+00:00")]
        for row in rows:
            self.assertEqual(self.engine.decide(row)["status"], "quarantined")
        self.assertEqual(self.engine.vessel_count, 0)

    def test_last_retry_is_idempotent_even_after_other_vessel_advanced_clock(self):
        row = event()
        self.assertEqual(self.engine.decide(row)["status"], "observed_unscored")
        self.assertEqual(self.engine.decide(event(4, vessel="other"))["status"], "observed_unscored")
        reordered = dict(reversed(list(row.items())))
        duplicate = self.engine.decide(reordered)
        self.assertEqual((duplicate["status"], duplicate["reason"]),
                         ("duplicate", "exact_last_accepted_retry"))
        self.assertEqual(self.engine.vessel_count, 2)

    def test_conflicts_and_old_retries_do_not_poison_accepted_state(self):
        row = event()
        self.engine.decide(row)
        for conflict in [event(1, event_id=row["event_id"]),
                         event(event_id="different-id"), event(geometry={"len_m": 999})]:
            result = self.engine.decide(conflict)
            self.assertEqual(result["status"], "quarantined")
            self.assertEqual(result["reason"], "last_accepted_conflict")
        self.assertEqual(self.engine.decide(row)["status"], "duplicate")
        self.assertEqual(self.engine.decide(event(1))["status"], "observed_unscored")
        result = self.engine.decide(row)
        self.assertEqual((result["status"], result["reason"]), ("quarantined", "late_vessel_interval"))

    def test_global_regression_and_per_vessel_late_intervals_quarantine(self):
        self.engine.decide(event(2))
        result = self.engine.decide(event(1, vessel="other"))
        self.assertEqual(result["reason"], "decision_clock_regression")
        self.assertEqual(self.engine.vessel_count, 1)
        result = self.engine.decide(event(1, decision_at="2026-01-02T00:00:00+00:00"))
        self.assertEqual(result["reason"], "late_vessel_interval")
        self.assertEqual(self.engine.decide(event(3))["status"], "observed_unscored")

    def test_supplied_scores_and_nonempty_references_are_never_used(self):
        for value in (None, 0, 999, {"cached": 0.1}):
            result = self.engine.decide(event(score=value))
            self.assertEqual((result["status"], result["reason"]), ("quarantined", "scoring_disabled"))
            self.assert_disabled(result)
        for value in ([{"event_id": "future"}], "file.json", {}, None):
            result = self.engine.decide(event(references=value))
            self.assertEqual(result["reason"], "unsupported_reference")
            self.assert_disabled(result)
        self.assertEqual(self.engine.decide(event(references=[]))["status"], "observed_unscored")

    def test_geometry_validates_units_ranges_and_unsupported_computed_values(self):
        for geometry in ({"centroid_lon": 181}, {"centroid_lat": -91}, {"len_m": -1},
                         {"bbox_m": -1}, {"len_m": True}, {"len_m": "1"},
                         {"speed_m_s": 5}, None, {"len_m": float("inf")}):
            with self.subTest(geometry=geometry):
                result = self.engine.decide(event(geometry=geometry))
                self.assertEqual(result["status"], "quarantined")
        self.assertEqual(self.engine.decide(event(geometry={"len_m": 0}))["status"], "observed_unscored")

    def test_identifiers_are_bounded_and_invalid_rows_preserve_state(self):
        for identifier in ("", " " , "a" * 129, "has\nnewline", 123):
            self.assertEqual(self.engine.decide(event(vessel_id=identifier))["status"], "quarantined")
        self.assertEqual(self.engine.vessel_count, 0)
        row = event()
        self.engine.decide(row)
        self.engine.decide(event(10, geometry={"len_m": -1}))
        self.assertEqual(self.engine.decide(event(1))["status"], "observed_unscored")

    def test_vessel_capacity_does_not_evict_or_advance_clock(self):
        cfg = config()
        cfg["memory"]["max_vessels"] = 1
        engine = replay.CausalReplay(cfg)
        row = event()
        engine.decide(row)
        result = engine.decide(event(10, vessel="new"))
        self.assertEqual((result["status"], result["reason"]), ("abstained", "max_vessels_reached"))
        self.assertEqual(engine.vessel_count, 1)
        self.assertEqual(engine.decide(event(1))["status"], "observed_unscored")

    def test_disabled_config_is_detached_from_caller_mutation(self):
        cfg = config()
        engine = replay.CausalReplay(cfg)
        cfg["scoring"]["enabled"] = True
        self.assertFalse(engine.config["scoring"]["enabled"])
        self.assert_disabled(engine.decide(event()))


class ConfigAndStreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "synthetic.jsonl"
        self.output = self.root / "new-output"
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(config()), encoding="utf-8")

    def write_rows(self, rows):
        self.input.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in rows))

    def run_replay(self, cfg=None):
        with patch.object(replay, "available_memory_bytes", return_value=2 * 1024 ** 3):
            return replay.replay(cfg or config(), self.input, self.output)

    def test_safety_configuration_cannot_enable_scoring_or_official_evaluation(self):
        changes = [("mode", "detector"), ("scoring.enabled", True), ("scoring.enabled", 0),
                   ("scoring.adapter", "model.py"), ("scoring.threshold", 1),
                   ("scoring.calibration_status", "validated"),
                   ("evaluation.official_f1_enabled", True), ("evaluation.label_status", "official"),
                   ("input.real_time_basis_required", "assumed"),
                   ("input.real_availability_required", "assumed"),
                   ("input.late_event_policy", "reorder"), ("disabled_operations", [])]
        for path, value in changes:
            with self.subTest(path=path, value=value):
                cfg = config()
                keys = path.split(".")
                obj = cfg if len(keys) == 1 else cfg[keys[0]]
                obj[keys[-1]] = value
                with self.assertRaises(replay.ConfigError):
                    replay.validate_config(cfg)

    def test_capacity_bounds_cannot_bypass_ram_floor_or_allow_unbounded_state(self):
        cases = {"max_vessels": [0, 10001, True], "max_line_bytes": [0, 65537],
                 "estimated_peak_mib": [0, 127, 128.0], "reserve_mib": [-1, 639, False]}
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    cfg = config()
                    cfg["memory"][key] = value
                    with self.assertRaises(replay.ConfigError):
                        replay.validate_config(cfg)

    def test_configuration_rejects_unknown_fields_and_duplicate_json_keys(self):
        cfg = config()
        cfg["extra"] = True
        with self.assertRaises(replay.ConfigError):
            replay.validate_config(cfg)
        self.config_path.write_bytes(b'{"mode":"contract_replay","mode":"detector"}')
        with self.assertRaisesRegex(replay.ConfigError, "duplicate_json_key"):
            replay.load_config(self.config_path)
        self.config_path.write_bytes(b" " * (replay.CONFIG_MAX_BYTES + 1))
        with self.assertRaisesRegex(replay.ConfigError, "config_file_too_large"):
            replay.load_config(self.config_path)

    def test_check_config_needs_no_workload_or_ram_probe(self):
        output = io.StringIO()
        with patch.object(replay, "available_memory_bytes", side_effect=AssertionError("unexpected probe")):
            with contextlib.redirect_stdout(output):
                code = replay.main(["--config", str(self.config_path), "--check-config"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "config_valid")
        self.assertFalse(self.output.exists())

    def test_summary_and_decisions_keep_auditable_hashes_and_disabled_outputs(self):
        row = event()
        self.write_rows([row, row, event(1, available_at=None), event(2, score=0.9)])
        summary = self.run_replay()
        self.assertEqual(summary["counts"], {"observed_unscored": 1, "abstained": 1,
                                            "quarantined": 1, "duplicate": 1})
        self.assertEqual(summary["source_types"], {"synthetic": 4})
        self.assertEqual(summary["input_digest"], hashlib.sha256(self.input.read_bytes()).hexdigest())
        rows = [json.loads(line) for line in (self.output / "decisions.jsonl").read_text().splitlines()]
        source_lines = self.input.read_bytes().splitlines(keepends=True)
        for line, decision in zip(source_lines, rows):
            self.assertEqual(decision["input_digest"], hashlib.sha256(line).hexdigest())
            self.assertEqual(decision["config_digest"], summary["config_digest"])
            self.assertIsNone(decision["score"])
            self.assertIsNone(decision["alarm"])
            self.assertFalse(decision["alert_emitted"])
        self.assertFalse(summary["evaluation"]["official_f1_enabled"])
        self.assertFalse(summary["scoring"]["enabled"])
        self.assertNotIn("f1", summary)
        self.assertEqual(json.loads((self.output / "summary.json").read_text()), summary)

    def test_future_append_preserves_streaming_prefix_bytes(self):
        self.write_rows([event(), event(1)])
        self.run_replay()
        prefix_bytes = (self.output / "decisions.jsonl").read_bytes()
        self.output = self.root / "extended"
        with self.input.open("ab") as handle:
            handle.write(json.dumps(event(10)).encode() + b"\n")
        self.run_replay()
        self.assertTrue((self.output / "decisions.jsonl").read_bytes().startswith(prefix_bytes))

    def test_existing_outputs_including_empty_directory_and_input_are_preserved(self):
        self.write_rows([event()])
        for output in (self.root / "empty", self.input, self.config_path):
            with self.subTest(path=output):
                if output.suffix == "":
                    output.mkdir()
                before = output.read_bytes() if output.is_file() else None
                with self.assertRaisesRegex(FileExistsError, "output_already_exists"):
                    replay.replay(config(), self.input, output)
                self.assertEqual(output.read_bytes() if output.is_file() else None, before)

    def test_low_or_unknown_ram_aborts_before_any_output(self):
        self.write_rows([event()])
        for value in (0, 767 * 1024 ** 2):
            with patch.object(replay, "available_memory_bytes", return_value=value) as probe:
                with self.assertRaisesRegex(replay.MemoryPreflightError, "insufficient_available_ram"):
                    replay.replay(config(), self.input, self.output)
                probe.assert_called_once_with()
                self.assertFalse(self.output.exists())
        with patch.object(replay, "available_memory_bytes",
                          side_effect=replay.MemoryPreflightError("available_ram_unknown")):
            with self.assertRaises(replay.MemoryPreflightError):
                replay.replay(config(), self.input, self.output)
        self.assertFalse(self.output.exists())

    def test_each_execution_rechecks_available_ram_once(self):
        self.write_rows([event()])
        with patch.object(replay, "available_memory_bytes", side_effect=[2 * 1024 ** 3, 0]) as probe:
            replay.replay(config(), self.input, self.output)
            with self.assertRaises(replay.MemoryPreflightError):
                replay.replay(config(), self.input, self.root / "deferred")
        self.assertEqual(probe.call_count, 2)
        self.assertFalse((self.root / "deferred").exists())

    def test_oversized_malformed_and_duplicate_key_lines_are_bounded_and_recover(self):
        cfg = config()
        cfg["memory"]["max_line_bytes"] = 1024
        raw = (b"x" * 200000 + b"\n" + b'{"event_id":"a","event_id":"b"}\n' +
               b'{"geometry":{"len_m":NaN}}\n' + b"\xff\n" + b"\n" +
               json.dumps(event()).encode() + b"\n")
        self.input.write_bytes(raw)
        summary = self.run_replay(cfg)
        self.assertEqual(summary["counts"]["quarantined"], 5)
        self.assertEqual(summary["counts"]["observed_unscored"], 1)
        self.assertEqual(summary["input_digest"], hashlib.sha256(raw).hexdigest())
        rows = [json.loads(line) for line in (self.output / "decisions.jsonl").read_text().splitlines()]
        self.assertEqual(rows[0]["reason"], "line_too_large")
        self.assertEqual(rows[0]["input_digest"], hashlib.sha256(b"x" * 200000 + b"\n").hexdigest())
        self.assertEqual(rows[-1]["line_number"], 6)

    def test_line_reader_never_requests_unbounded_or_large_reads(self):
        class GuardedBytes(io.BytesIO):
            def readline(self, size=-1):
                self_test.assertLessEqual(size, 257)
                self_test.assertGreater(size, 0)
                return super().readline(size)
        self_test = self
        raw = b"x" * 10000 + b"\n{}"
        digest = hashlib.sha256()
        lines = list(replay._bounded_lines(GuardedBytes(raw), 256, digest))
        self.assertEqual([line for line, _ in lines], [None, b"{}"])
        self.assertEqual(digest.hexdigest(), hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
