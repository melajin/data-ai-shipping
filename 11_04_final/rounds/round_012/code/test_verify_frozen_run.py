"""Pure standard-library fixtures for round010 provenance classification."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_frozen_run import audit_round


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(root: Path, live_wrapper_drift: bool) -> None:
    round_root = root / "rounds" / "round_010"
    code_bytes = b"def run():\n    return 'saved-only fixture'\n"
    approved_wrapper = (
        b"def main(root_identity_capture_failed):\n"
        b"    if root_identity_capture_failed:\n"
        b"        return 7\n"
        b"    return 0\n"
    )
    drift_wrapper = (
        b"def main(root_identity_capture_failed):\n"
        b"    if root_identity_capture_failed:\n"
        b"        receipt['wrapper_unchanged'] = False\n"
        b"        receipt['wrapper_unchanged_detail'] = 'diagnostic'\n"
        b"        return 7\n"
        b"    return 0\n"
    )
    live_wrapper = drift_wrapper if live_wrapper_drift else approved_wrapper
    code_key = "rounds/round_010/code/replay.py"
    wrapper_key = "rounds/round_010/manager/run_bounded.py"
    npz_key = "rounds/round_010/artifacts/private_context.npz"
    approved_sha = {code_key: _sha(code_bytes), wrapper_key: _sha(approved_wrapper), npz_key: "f" * 64}
    approved = {"schema": "round010_approved_sources.v1", "sha256": approved_sha,
                "runtime_guards": {"checkpoint": {"path": "model_cache/model.ckpt", "bytes": 12, "sha256": "a" * 64}}}
    _write_json(round_root / "review" / "approved_sources.json", approved)

    code_live = root / code_key
    wrapper_live = root / wrapper_key
    code_live.parent.mkdir(parents=True, exist_ok=True)
    wrapper_live.parent.mkdir(parents=True, exist_ok=True)
    code_live.write_bytes(code_bytes)
    wrapper_live.write_bytes(live_wrapper)

    for run_id in ("mock_01", "pilot_01"):
        run_root = round_root / "logs" / run_id
        source_dir = run_root / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        script_name = "replay.py"
        (source_dir / script_name).write_bytes(code_bytes)
        (source_dir / "run_bounded.py").write_bytes(approved_wrapper)
        is_pilot = run_id == "pilot_01"
        receipt = {
            "schema": "round010_bounded_receipt.v1",
            "kind": "pilot" if is_pilot else "mock",
            "run_id": run_id,
            "status": "failed_or_stopped" if is_pilot else "completed",
            "exit_code": 0,
            "launched": True,
            "source_sha256": approved_sha[code_key],
            "wrapper_sha256": approved_sha[wrapper_key],
            "wrapper_snapshot_sha256": approved_sha[wrapper_key],
            "wrapper_unchanged": not is_pilot,
            "approved_sources": approved,
            "source_snapshot": {code_key: str(source_dir / script_name)},
            "executed_source_snapshot": str(source_dir / script_name),
            "script": str(code_live),
            "process_creation_started_utc": "2026-11-04T19:56:30+00:00",
            "passed_mock_run_id": "mock_01" if is_pilot else None,
        }
        _write_json(run_root / "receipt.json", receipt)

    model_rows = [[0.8, 0.1, 0.05, 0.05], [0.1, 0.7, 0.1, 0.1]]
    reference_rows = [[0.79999, 0.10001, 0.05, 0.05], [0.10002, 0.69999, 0.1, 0.09999]]
    difference = max(abs(a - b) for model, ref in zip(model_rows, reference_rows) for a, b in zip(model, ref))
    per_query = []
    for query_id, model, ref in zip(("36001915", "31703435"), model_rows, reference_rows):
        model_argmax = max(range(4), key=model.__getitem__)
        ref_argmax = max(range(4), key=ref.__getitem__)
        per_query.append({"query_id": query_id, "max_abs_probability_difference": max(abs(a-b) for a, b in zip(model, ref)),
                          "model_argmax": model_argmax, "reference_argmax": ref_argmax,
                          "argmax_equal": model_argmax == ref_argmax})
    comparison = {
        "max_abs_probability_difference": difference,
        "absolute_tolerance": 1e-4,
        "exact_numeric_equal_after_float64_parse": False,
        "argmax_equal": True,
        "within_1e_4_absolute_tolerance": True,
        "per_query": per_query,
        "is_performance_or_F1_claim": False,
    }
    pilot_result = {
        "status": "PILOT_COMPLETE",
        "stage": "comparison_complete",
        "current_stage": "managers_restored",
        "probabilities": {"query_ids": ["36001915", "31703435"], "class_order": [0, 1, 2, 3], "values": model_rows, "shape": [2, 4]},
        "reference_evidence": {"selected_reference_probability_rows": [
            {"rfid_id": query_id, "p0_p3": row} for query_id, row in zip(("36001915", "31703435"), reference_rows)
        ]},
        "comparison": comparison,
        "predict_proba_completed_count": 1,
        "f1_computed": False,
        "training_performed": False,
        "inner_labels_loaded_or_used": False,
    }
    _write_json(round_root / "artifacts" / "pilot_01" / "pilot_result.json", pilot_result)
    journal = [
        {"event": "stage", "stage": "predict_proba_complete"},
        {"event": "stage", "stage": "managers_restored"},
    ]
    (round_root / "artifacts" / "pilot_01").mkdir(parents=True, exist_ok=True)
    (round_root / "artifacts" / "pilot_01" / "progress.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in journal), encoding="utf-8"
    )

    gates = {name: True for name in (
        "finite_range_shape", "row_sum", "reference_tolerance", "argmax_equal", "reported_gate", "reported_values_agree"
    )}
    result = {
        "status": "completed_numeric_replay_pass_source_freeze_violation",
        "all_execution_gates_passed": False,
        "saved_numeric_replay_gates_passed": True,
        "source_freeze_incident_recorded": True,
        "independent_saved_json_checks": {"gates": gates, "exact_numeric_equal": False},
    }
    _write_json(round_root / "artifacts" / "result.json", result)

    mutation_wrapper_sha = _sha(drift_wrapper)
    incident = {
        "mutation_at_utc": "2026-11-04T19:57:09+00:00",
        "approved_wrapper_sha": approved_sha[wrapper_key],
        "running_receipt_wrapper_sha": approved_sha[wrapper_key],
        "current_wrapper_sha": mutation_wrapper_sha,
        "new_execution_authorized": False,
    }
    _write_json(round_root / "manager" / "source_freeze_incident.json", incident)
    postcheck = {"checks": [{"path": wrapper_key, "expected": approved_sha[wrapper_key],
                              "actual": mutation_wrapper_sha, "match": False}]}
    _write_json(round_root / "manager" / "post_execution_hash_check.json", postcheck)


class FrozenRunAuditFixtureTests(unittest.TestCase):
    def _run_fixture(self, live_wrapper_drift: bool) -> dict:
        workspace_round = Path.cwd().resolve()
        task_root = next((candidate for candidate in (workspace_round, *workspace_round.parents)
                          if (candidate / "rounds" / "round_012").is_dir()), None)
        if task_root is None:
            task_root = next((candidate for candidate in Path(__file__).resolve().parents
                              if (candidate / "rounds" / "round_012").is_dir()), None)
        if task_root is None:
            raise RuntimeError("Could not locate task root for round012-only fixtures")
        fixture_parent = task_root / "rounds" / "round_012" / "temp"
        fixture_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="verify_fixture_", dir=fixture_parent) as temporary:
            root = Path(temporary)
            _fixture(root, live_wrapper_drift)
            return audit_round(root, "round_010")

    def test_clean_live_source_preserves_historical_failure(self) -> None:
        report = self._run_fixture(live_wrapper_drift=False)
        self.assertTrue(report["executed_snapshot_matches_approved"])
        self.assertTrue(report["live_source_unchanged"])
        self.assertTrue(report["current_source_gate"])
        self.assertTrue(report["saved_numeric_replay_passed"])
        self.assertTrue(report["audit_integrity_passed"])
        self.assertFalse(report["historical_overall_gate"])

    def test_live_wrapper_drift_does_not_invalidate_launch_snapshot_or_numeric_record(self) -> None:
        report = self._run_fixture(live_wrapper_drift=True)
        self.assertTrue(report["executed_snapshot_matches_approved"])
        self.assertFalse(report["live_source_unchanged"])
        self.assertFalse(report["current_source_gate"])
        self.assertTrue(report["saved_numeric_replay_passed"])
        self.assertTrue(report["audit_integrity_passed"])
        self.assertFalse(report["historical_overall_gate"])
        branch = report["wrapper_source_diff_and_branch_progress"]["root_identity_capture_failed_branch"]
        self.assertTrue(branch["in_approved_launch_snapshot"])
        self.assertTrue(branch["in_live_wrapper"])
        self.assertTrue(branch["live_diff_added_early_return_diagnostic"])
        self.assertTrue(branch["pilot_child_completed"])
        self.assertFalse(branch["entered_by_pilot"])


if __name__ == "__main__":
    unittest.main()
