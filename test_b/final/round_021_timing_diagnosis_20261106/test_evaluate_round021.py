"""Synthetic evaluation tests. Never open fleet inputs or actual accident labels."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("evaluate_round021.py")
spec = importlib.util.spec_from_file_location("round021_evaluation_under_test", MODULE_PATH)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def event(key="a", hour=490920, event_id="e"):
    return {"rfid_id": key, "acc_ts": hour, "acc_id": event_id}


def prediction(b=490900, t=490920, g=490910):
    return {"B": b, "T": t, "G": g}


class EvaluationTests(unittest.TestCase):
    def test_split_disjoint_balanced_and_input_order_independent(self):
        ids = [f"synthetic-{index:04d}" for index in range(100)]
        split = ev.deterministic_split(ids)
        self.assertEqual(split, ev.deterministic_split(reversed(ids)))
        dev = {key for key, value in split.items() if value == "dev"}
        val = set(split) - dev
        self.assertEqual((len(dev), len(val)), (50, 50))
        self.assertFalse(dev & val)
        self.assertEqual(dev | val, set(ids))
        with self.assertRaises(ValueError):
            ev.deterministic_split(["same", "same"])

    def test_policy_requires_strict_development_gain(self):
        rows = [{"rfid_id": "d", "policy": policy, "hit_pm6h": True} for policy in ev.POLICIES]
        choice = ev.choose_policy(rows, {"d": prediction()}, {"d": "dev"})
        self.assertEqual(choice["selected_policy"], "B")

    def test_policy_tiebreak_uses_changes_in_all_dev_including_unlinked(self):
        rows = [{"rfid_id": "linked", "policy": policy, "hit_pm6h": policy != "B"} for policy in ev.POLICIES]
        predictions = {"linked": prediction(1, 2, 3), "unlinked": prediction(1, 2, 1), "v": prediction(1, 1, 3)}
        choice = ev.choose_policy(rows, predictions, {"linked": "dev", "unlinked": "dev", "v": "validation"})
        self.assertEqual(choice["selected_policy"], "G")
        self.assertEqual(choice["development_timestamps_changed"], {"B": 0, "T": 2, "G": 1})

    def test_policy_max_hits_precedes_change_count_then_T_precedes_G(self):
        predictions = {"a": prediction(1, 2, 3), "b": prediction(1, 2, 3)}
        split = dict.fromkeys(predictions, "dev")
        rows = [{"rfid_id": key, "policy": p, "hit_pm6h": p == "T" or (p == "G" and key == "a")} for key in predictions for p in ev.POLICIES]
        self.assertEqual(ev.choose_policy(rows, predictions, split)["selected_policy"], "T")
        for row in rows:
            row["hit_pm6h"] = row["policy"] != "B"
        self.assertEqual(ev.choose_policy(rows, predictions, split)["selected_policy"], "T")

    def test_selector_rejects_validation_outcome(self):
        with self.assertRaises(ValueError):
            ev.choose_policy([{"rfid_id": "v", "policy": "G", "hit_pm6h": True}], {"v": prediction()}, {"v": "validation"})

    def test_dev_reader_does_not_access_validation_timestamp(self):
        class Guard(dict):
            def __getitem__(self, key):
                if key == "acc_ts":
                    raise AssertionError("Validation timestamp accessed before lock")
                return super().__getitem__(key)
        rows = [Guard(rfid_id="v", acc_id="bad"), {"rfid_id": "d", "acc_id": "good", "acc_ts": "490920"}]
        with mock.patch.object(ev, "csv_rows", return_value=iter(rows)):
            result = ev.read_events(Path("unused-synthetic"), {"d"}, "dev", [])
        self.assertEqual(list(result), ["d"])

    def test_nearest_event_tie_uses_acc_id_not_timestamp(self):
        events = [event(hour=100, event_id="z"), event(hour=104, event_id="a")]
        self.assertEqual(ev.nearest_event(102, events)["nearest_acc_id"], "a")

    def test_one_prediction_matches_at_most_one_event(self):
        events = {"a": [event(hour=100, event_id="z"), event(hour=104, event_id="a")]}
        rows = ev.event_error_rows(events, {"a": prediction(102, 102, 102)}, "T", {"a": "dev"})
        self.assertEqual(sum(row["selected_raw_event_tolerance_flag"] for row in rows), 2)
        self.assertEqual(sum(row["selected_matched_tp_event"] for row in rows), 1)
        self.assertEqual(next(row["acc_id"] for row in rows if row["selected_matched_tp_event"]), "a")

    def test_tolerance_is_inclusive_and_missing_is_miss(self):
        events = [event(hour=100)]
        self.assertTrue(ev.nearest_event(106, events)["hit_pm6h"])
        self.assertFalse(ev.nearest_event(107, events)["hit_pm6h"])
        self.assertFalse(ev.nearest_event(None, events)["hit_pm6h"])

    def test_exclusive_failure_taxonomy_order_and_own_union_windows(self):
        cases = [
            ([], [], [], None, "no_finite_score_anywhere"),
            ([0, 1], [0, 1], [1], 1, "all_windows_outside_observed_span"),
            ([0, 200], [0, 200], [200], 200, "span_overlap_but_no_observed_hour_in_any_window"),
            ([0, 100, 200], [0, 200], [200], 200, "observed_in_window_but_no_finite_score"),
            ([0, 100, 200], [100, 200], [200], 200, "finite_in_window_but_no_global_max_ranking_failure"),
            ([0, 100, 200], [100, 200], [100, 200], 200, "some_global_max_in_window_but_B_miss_tie_choice_failure"),
            ([100], [100], [100], 100, "B_hit"),
        ]
        for observed, scored, maxima, baseline, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(ev.failure_category([event(hour=100)], observed, scored, maxima, baseline), expected)
        self.assertEqual(ev.failure_category([event(hour=100)], [100], [], [], None), "no_finite_score_anywhere")
        self.assertEqual(ev.failure_category([event(hour=100), event(hour=200)], [0, 200], [0, 200], [200], 200), "B_hit")

    def test_event_gap_intersection_and_minimum_timing_errors(self):
        groups = {"a": {"observed": {100, 120}, "finite": {120}, "maximum": {120}}}
        rows = ev.event_error_rows({"a": [event(hour=110)]}, {"a": prediction(120, 120, 110)}, "G", {"a": "dev"}, groups)
        self.assertTrue(rows[0]["accident_hour_strictly_inside_observation_gap"])
        self.assertTrue(rows[0]["accident_window_intersects_missing_integer_hours"])
        self.assertEqual(rows[0]["min_abs_observed_hour_error_h"], 10)

    def test_joint_scenario_uses_actual_H_instead_of_fixed_h(self):
        self.assertAlmostEqual(ev.scenario_f1(.2, 2/10, 4/10, 3/90), 2*.2*.2/(.2*1.4+.8*(3/90)))
        self.assertEqual(ev.scenario_f1(.2, 0, .4, .1), 0)
        self.assertEqual(ev.scenario_f1(1, .2, .4, .9), 2*.2/1.4)

    def test_fleet_gate_counts_keep_unknowns_and_conditional_joint_distinct(self):
        predictions = {key: prediction() for key in "abcdef"}
        peaks = {key: {"peak_score": .9 if key in "ace" else .5, "activity_radius_km": index} for index, key in enumerate("abcdef")}
        split = {key: "dev" if key in "abc" else "validation" for key in predictions}
        threshold, flags, counts, scenarios = ev.fleet_counts(predictions, peaks, split, set("ab"), {"a": True, "b": False}, "T")
        self.assertEqual(threshold, 4.75)
        row = next(row for row in counts if row["subset"] == "all" and row["gate"] == "peak_ge_0_75")
        self.assertEqual((row["C_selected"], row["A_linked_selected"], row["H_linked_selected_timehit"], row["U_unlinked_selected"]), (3, 1, 1, 2))
        self.assertEqual(row["conditional_timing_H_over_A"], 1)
        self.assertEqual(row["joint_recall_H_over_nlinked"], .5)
        self.assertFalse(row["unlinked_are_confirmed_false_positives"])
        self.assertEqual(sum(flags[key]["radius_ge_q95"] for key in flags), 1)

    def test_wilson_and_paired_wins_losses_nominal_only(self):
        rows = [{"rfid_id": "a", "policy": "B", "hit_pm6h": False, "abs_error_h": 20},
                {"rfid_id": "b", "policy": "B", "hit_pm6h": True, "abs_error_h": 2},
                {"rfid_id": "a", "policy": "T", "hit_pm6h": True, "abs_error_h": 2},
                {"rfid_id": "b", "policy": "T", "hit_pm6h": False, "abs_error_h": 20}]
        result = ev.comparison(rows, rows, "T", "validation")
        self.assertEqual((result["paired_wins_vs_B"], result["paired_losses_vs_B"]), (1, 1))
        self.assertFalse(result["improvement_candidate"])
        self.assertFalse(result["p_value_is_decision_gate"])
        self.assertAlmostEqual(ev.wilson(0, 10)[1], .2775327998628892)
        self.assertEqual(ev.exact_mcnemar(3, 0), .25)

    def test_manifest_hash_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            part = root / "scores.parquet"
            part.write_bytes(b"synthetic-only")
            manifest = {"rows": 1, "vessels": 1, "files": [{"output_path": part.name, "output_sha256": ev.sha256(part), "output_bytes": part.stat().st_size, "rows": 1}]}
            ev.write_json(root / "hourly_score_manifest.json", manifest)
            seal = {"hourly_manifest_sha256": ev.sha256(root / "hourly_score_manifest.json")}
            with mock.patch.multiple(ev, EXPECTED_ROWS=1, EXPECTED_VESSELS=1):
                self.assertEqual(ev.verified_hourly_paths(root, seal), [part])
                part.write_bytes(b"tampered")
                with self.assertRaises(RuntimeError):
                    ev.verified_hourly_paths(root, seal)

    def test_stream_retains_linked_only_and_exact_maxima_with_duplicate_hours(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tiny-synthetic.parquet"
            pq.write_table(pa.table({"rfid_id": ["a", "a", "a", "a", "unlinked", "unlinked"],
                                     "ts": [100, 100, 102, 110, 100, 120],
                                     "score": [float("nan"), .5, .9, .9, 1., 1.]}), path)
            with mock.patch.object(ev, "EXPECTED_ROWS", 6):
                groups, total = ev.stream_linked_hours([path], {"a"}, {"a": prediction(102, 102, 106)})
                self.assertEqual(total, 6)
                self.assertEqual(set(groups), {"a"})
                self.assertEqual(groups["a"]["observed"], {100, 102, 110})
                self.assertEqual(groups["a"]["maximum"], {102, 110})
                self.assertEqual(groups["a"]["n_rows"], 4)
                with self.assertRaises(ValueError):
                    ev.stream_linked_hours([path], {"a"}, {"a": prediction(100, 102, 106)})

    def test_sealed_pipeline_never_evaluates_unselected_validation_alternative(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            score_dir = root / "execution_001"
            score_dir.mkdir()
            for name in ("PROTOCOL.md", "freeze.json", "score_fleet_timing.py", "evaluate_round021.py", "test_evaluate_round021.py"):
                (root / name).write_text("synthetic-only", encoding="utf-8")
            ids = [f"fixture-{index}" for index in range(8)]
            split = ev.deterministic_split(ids)
            dev = sorted(key for key in ids if split[key] == "dev")
            val = sorted(key for key in ids if split[key] == "validation")
            linked = dev[:2] + val[:2]
            rows = []
            for key in ids:
                rows.append({"rfid_id": key, "split": "development" if split[key] == "dev" else "validation", "baseline_ts": 490900,
                             "tie_center_ts": 490920 if key in dev else 490930,
                             "gap_midpoint_ts": 490920 if key != dev[1] else 490910})
            ev.write_csv(score_dir / "fleet_policy_predictions.csv", rows)
            truth = root / "synthetic_truth.csv"
            labels = [event(key, 490920, f"event-{index}") for index, key in enumerate(linked)]
            labels.append(event(dev[0], 490922, "extra-event"))
            ev.write_csv(truth, labels)
            peaks = root / "synthetic_peaks.csv"
            ev.write_csv(peaks, [{"rfid_id": key, "peak_score": .9, "activity_radius_km": index} for index, key in enumerate(ids)])
            part = score_dir / "synthetic.hourly_scores.parquet"
            part.write_bytes(b"synthetic-score-part")
            ev.write_json(score_dir / "hourly_score_manifest.json", {"rows": 8, "vessels": 8, "files": [{"output_path": part.name, "output_sha256": ev.sha256(part), "output_bytes": part.stat().st_size, "rows": 8}]})
            seal = {"status": "complete", "vessels_completed": 8, "rows_completed": 8, "vessel_error_records": 0,
                    "labels_read": False, "accident_times_parsed": False, "training_performed": False,
                    "score_definition_changed": False, "source_checksums_match": True,
                    "freeze_sha256": ev.sha256(root / "freeze.json"), "engine_sha256": ev.sha256(root / "score_fleet_timing.py"),
                    "policy_prediction_sha256": ev.sha256(score_dir / "fleet_policy_predictions.csv"),
                    "hourly_manifest_sha256": ev.sha256(score_dir / "hourly_score_manifest.json")}
            ev.write_json(score_dir / "score_seal.json", seal)
            ev.write_json(score_dir / "score_metadata.json", {"score_seal_sha256": ev.sha256(score_dir / "score_seal.json")})
            ev.write_json(score_dir / "labelblind_score_summary.json", {"synthetic": True})
            original_reader = ev.read_events
            phases = []
            def guarded_reader(path, permitted, phase, audit):
                phases.append(phase)
                if phase == "validation":
                    self.assertTrue((root / "evaluation_001/selection_sealed.json").is_file())
                    lock = ev.read_json(root / "evaluation_001/selection_sealed.json")
                    self.assertEqual(lock["selection_sha256"], ev.sha256(root / "evaluation_001/selection.json"))
                return original_reader(path, permitted, phase, audit)
            groups = {key: {"observed": {490900, 490920}, "finite": {490900, 490920}, "maximum": {490900}, "n_rows": 2, "max_score": .9} for key in linked}
            with mock.patch.multiple(ev, HERE=root, TRUTH=truth, PEAKS=peaks, __file__=str(root / "evaluate_round021.py"),
                                     EXPECTED_VESSELS=8, EXPECTED_LINKED=4, EXPECTED_EVENTS=5, EXPECTED_ROWS=8), \
                 mock.patch.object(ev, "memory_gate", return_value={"synthetic": True}), \
                 mock.patch.object(ev, "read_events", side_effect=guarded_reader), \
                 mock.patch.object(ev, "stream_linked_hours", return_value=(groups, 8)):
                summary = ev.evaluate(score_dir, root / "evaluation_001", ev.sha256(root / "PROTOCOL.md"))
            self.assertEqual(phases, ["dev", "validation"])
            self.assertEqual(summary["selection"]["selected_policy"], "T")
            self.assertEqual({row["policy"] for row in summary["validation"]}, {"B", "T"})
            self.assertEqual({row["policy"] for row in summary["all_linked"]}, {"B", "T"})
            self.assertEqual({row["policy"] for row in summary["fleet_selection_counts"]}, {"B", "T"})
            audit = [row["action"] for row in summary["audit"]]
            self.assertLess(audit.index("selection_persisted_and_hashed"), len(audit) - 1)
            self.assertEqual(len(list(ev.csv_rows(root / "evaluation_001/time_errors_vessel.csv"))), 4)
            self.assertEqual(len(list(ev.csv_rows(root / "evaluation_001/event_errors.csv"))), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
