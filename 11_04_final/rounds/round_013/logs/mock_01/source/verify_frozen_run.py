"""Audit round010's saved provenance without loading model or source data.

The audit deliberately separates immutable launch snapshots, the current live
source tree, and the already-saved two-query numeric comparison. It never
recomputes the historical overall gate.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


CHUNK_BYTES = 1024 * 1024
AUDIT_SCHEMA = "round013_provenance_audit.v1"
FROZEN_QUERY_IDS = ["36001915", "31703435"]
FROZEN_CLASS_ORDER = [0, 1, 2, 3]


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256; never reads a whole file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _safe_path(root: Path, relative: str) -> Path:
    parsed = PurePosixPath(relative.replace("\\", "/"))
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"Unsafe manifest path: {relative}")
    candidate = root.joinpath(*parsed.parts).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError(f"Manifest path escapes workspace: {relative}")
    return candidate


def _excluded_asset_reason(relative: str) -> str | None:
    """Deny-list data and checkpoint assets before any file access or hashing."""
    lowered = relative.replace("\\", "/").lower()
    name = PurePosixPath(lowered).name
    parts = set(PurePosixPath(lowered).parts)
    if name.endswith((".npz", ".npy", ".csv", ".tsv", ".parquet", ".feather", ".arrow")):
        return "array/table data content is explicitly not re-read or re-hashed"
    if name.endswith((".ckpt", ".pt", ".pth")) or "checkpoint" in lowered:
        return "checkpoint content is explicitly not re-read or re-hashed"
    if parts.intersection({"raw", "raw_data", "reference", "reference_data", "holdout", "hold_out", "holdout_data"}):
        return "raw/reference/holdout data path is explicitly not re-read or re-hashed"
    return None


def _map_entries(root: Path, sha_map: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    checks: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for relative, expected_value in sorted(sha_map.items()):
        expected = str(expected_value).lower()
        reason = _excluded_asset_reason(relative)
        if reason:
            excluded.append({"path": relative, "reason": reason, "reverified": False})
            continue
        path = _safe_path(root, relative)
        if not path.is_file():
            checks.append({"path": relative, "expected_sha256": expected, "actual_sha256": None, "match": False, "error": "missing"})
            continue
        actual = sha256_file(path)
        checks.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    return checks, excluded


def _same_json_value(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _receipt_snapshot_check(root: Path, source_round: str, run_id: str,
                            receipt: dict[str, Any], approved: dict[str, Any]) -> dict[str, Any]:
    round_root = root / "rounds" / source_round
    expected_map = approved.get("sha256", {})
    details: list[dict[str, Any]] = []
    ok = True

    map_matches = _same_json_value(receipt.get("approved_sources", {}).get("sha256"), expected_map)
    details.append({"check": "receipt_approved_map_matches", "passed": map_matches})
    ok &= map_matches

    wrapper_candidates = [name for name in expected_map if name.endswith("/manager/run_bounded.py")]
    if len(wrapper_candidates) != 1:
        wrapper_key = None
        wrapper_expected = None
        details.append({"check": "unique_approved_wrapper", "passed": False, "matches": wrapper_candidates})
        ok = False
    else:
        wrapper_key = wrapper_candidates[0]
        wrapper_expected = str(expected_map[wrapper_key]).lower()

    code_keys = sorted(name for name in expected_map if name.startswith(f"rounds/{source_round}/code/") and name.endswith(".py"))
    source_dir = round_root / "logs" / run_id / "source"
    expected_names = {PurePosixPath(name).name for name in code_keys}
    expected_names.add("run_bounded.py")
    actual_names = {path.name for path in source_dir.iterdir()} if source_dir.is_dir() else set()
    names_match = actual_names == expected_names
    details.append({"check": "snapshot_file_set", "passed": names_match,
                    "expected": sorted(expected_names), "actual": sorted(actual_names)})
    ok &= names_match

    source_snapshot = receipt.get("source_snapshot")
    source_mapping_matches = isinstance(source_snapshot, dict) and set(source_snapshot) == set(code_keys)
    if source_mapping_matches:
        for key, recorded in source_snapshot.items():
            expected_path = (source_dir / PurePosixPath(key).name).resolve()
            try:
                source_mapping_matches &= Path(str(recorded)).resolve() == expected_path
            except (OSError, RuntimeError):
                source_mapping_matches = False
    details.append({"check": "receipt_source_snapshot_paths", "passed": bool(source_mapping_matches)})
    ok &= bool(source_mapping_matches)

    for relative in code_keys:
        snapshot = source_dir / PurePosixPath(relative).name
        expected = str(expected_map[relative]).lower()
        actual = sha256_file(snapshot) if snapshot.is_file() else None
        matches = actual == expected
        details.append({"check": "approved_code_snapshot", "path": relative,
                        "expected_sha256": expected, "actual_sha256": actual, "passed": matches})
        ok &= matches

    wrapper_snapshot = source_dir / "run_bounded.py"
    wrapper_actual = sha256_file(wrapper_snapshot) if wrapper_snapshot.is_file() else None
    wrapper_snapshot_matches = bool(wrapper_expected and wrapper_actual == wrapper_expected
                                     and receipt.get("wrapper_sha256") == wrapper_expected
                                     and receipt.get("wrapper_snapshot_sha256") == wrapper_expected)
    details.append({"check": "approved_wrapper_snapshot", "path": wrapper_key,
                    "expected_sha256": wrapper_expected, "snapshot_sha256": wrapper_actual,
                    "receipt_wrapper_sha256": receipt.get("wrapper_sha256"),
                    "receipt_snapshot_sha256": receipt.get("wrapper_snapshot_sha256"),
                    "passed": wrapper_snapshot_matches})
    ok &= wrapper_snapshot_matches

    script_path = receipt.get("script")
    script_key: str | None = None
    try:
        resolved_script = Path(str(script_path)).resolve()
        script_key = resolved_script.relative_to(root.resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        pass
    script_expected = str(expected_map.get(script_key, "")).lower() if script_key else ""
    executed_snapshot = receipt.get("executed_source_snapshot")
    expected_executed = source_dir / PurePosixPath(script_key).name if script_key else None
    executed_path_matches = bool(expected_executed and executed_snapshot
                                 and Path(str(executed_snapshot)).resolve() == expected_executed.resolve())
    executed_hash = sha256_file(expected_executed) if expected_executed and expected_executed.is_file() else None
    executed_matches = bool(script_expected and receipt.get("source_sha256") == script_expected
                            and executed_path_matches and executed_hash == script_expected)
    details.append({"check": "executed_script_snapshot", "script": script_key,
                    "expected_sha256": script_expected or None, "snapshot_sha256": executed_hash,
                    "path_matches": executed_path_matches, "passed": executed_matches})
    ok &= executed_matches

    return {"run_id": run_id, "kind": receipt.get("kind"), "receipt_status": receipt.get("status"),
            "receipt_exit_code": receipt.get("exit_code"), "receipt_wrapper_unchanged": receipt.get("wrapper_unchanged"),
            "snapshot_matches_approved": bool(ok), "checks": details}


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _wrapper_diff(root: Path, source_round: str, mock_receipt: dict[str, Any],
                  pilot_receipt: dict[str, Any], pilot_result: dict[str, Any],
                  incident: dict[str, Any]) -> dict[str, Any]:
    round_root = root / "rounds" / source_round
    approved_path = round_root / "logs" / "mock_01" / "source" / "run_bounded.py"
    live_path = round_root / "manager" / "run_bounded.py"
    if not approved_path.is_file() or not live_path.is_file():
        return {"available": False, "approved_snapshot_path": str(approved_path), "live_path": str(live_path)}

    approved_bytes = approved_path.read_bytes()
    live_bytes = live_path.read_bytes()
    approved_text = approved_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    live_text = live_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    raw_diff = list(difflib.unified_diff(approved_text, live_text,
                                         fromfile="approved-launch-snapshot/run_bounded.py",
                                         tofile="live/manager/run_bounded.py", n=3))
    max_diff_lines = 500
    live_sha = hashlib.sha256(approved_bytes).hexdigest() if approved_bytes == live_bytes else sha256_file(live_path)
    approved_sha = sha256_file(approved_path)
    added = sum(1 for line in raw_diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in raw_diff if line.startswith("-") and not line.startswith("---"))
    branch_token = "root_identity_capture_failed"
    launch_has_branch = any(branch_token in line for line in approved_text)
    live_has_branch = any(branch_token in line for line in live_text)
    mutation_at = _parse_utc(incident.get("mutation_at_utc"))
    process_started = _parse_utc(pilot_receipt.get("process_creation_started_utc") or pilot_receipt.get("started_utc"))
    mutation_after_start = bool(mutation_at and process_started and mutation_at > process_started)
    expected_launch_hash = str(incident.get("approved_wrapper_sha", "")).lower()
    running_hash = str(incident.get("running_receipt_wrapper_sha", "")).lower()
    launched_approved = bool(expected_launch_hash and running_hash == expected_launch_hash
                             and pilot_receipt.get("wrapper_sha256") == expected_launch_hash
                             and approved_sha == expected_launch_hash)
    progress_path = round_root / "artifacts" / "pilot_01" / "progress.jsonl"
    progress_events = 0
    stage_names: list[str] = []
    parse_errors = 0
    if progress_path.is_file():
        with progress_path.open("r", encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                progress_events += 1
                if event.get("event") == "stage" and isinstance(event.get("stage"), str):
                    stage_names.append(event["stage"])
    child_completed = bool(
        pilot_result.get("status") == "PILOT_COMPLETE"
        and pilot_result.get("stage") == "comparison_complete"
        and pilot_result.get("current_stage") == "managers_restored"
        and pilot_result.get("predict_proba_completed_count") == 1
        and "predict_proba_complete" in stage_names
        and "managers_restored" in stage_names
        and pilot_receipt.get("launched") is True
    )
    early_failure_recorded = bool(
        pilot_receipt.get("root_identity_capture_failed") is True
        or pilot_receipt.get("status") == "root_identity_capture_failed"
        or "root_identity_capture_failed" in stage_names
    )
    entered_value = pilot_receipt.get("root_identity_capture_failed")
    # In the launch version the branch already existed. The changed two-line
    # diagnostic is inside that branch; the saved child/progress proves the
    # pilot continued through prediction and restoration instead of returning.
    diagnostic_added = any("wrapper_unchanged" in line for line in raw_diff if line.startswith("+") and not line.startswith("+++"))
    branch_entered_by_pilot = early_failure_recorded if early_failure_recorded else (False if child_completed else None)

    return {
        "available": True,
        "approved_snapshot_path": str(approved_path),
        "live_path": str(live_path),
        "approved_sha256": approved_sha,
        "live_sha256": live_sha,
        "added_lines": added,
        "removed_lines": removed,
        "unified_diff": raw_diff[:max_diff_lines],
        "diff_truncated": len(raw_diff) > max_diff_lines,
        "root_identity_capture_failed_branch": {
            "in_approved_launch_snapshot": launch_has_branch,
            "in_live_wrapper": live_has_branch,
            "live_diff_added_early_return_diagnostic": diagnostic_added,
            "incident_mutation_at_utc": incident.get("mutation_at_utc"),
            "pilot_process_started_utc": pilot_receipt.get("process_creation_started_utc"),
            "mutation_after_pilot_process_start": mutation_after_start,
            "launch_used_approved_wrapper_bytes": launched_approved,
            "receipt_branch_flag": entered_value,
            "pilot_progress_journal": {
                "path": str(progress_path),
                "event_count": progress_events,
                "stage_count": len(stage_names),
                "first_stage": stage_names[0] if stage_names else None,
                "last_stage": stage_names[-1] if stage_names else None,
                "predict_proba_complete_seen": "predict_proba_complete" in stage_names,
                "managers_restored_seen": "managers_restored" in stage_names,
                "root_identity_capture_failed_stage_seen": "root_identity_capture_failed" in stage_names,
                "parse_errors": parse_errors,
            },
            "pilot_child_completed": child_completed,
            "early_failure_return_recorded": early_failure_recorded,
            "entered_by_pilot": branch_entered_by_pilot,
            "conclusion": ("The two added wrapper_unchanged diagnostics are inside an early-return branch that existed in the approved wrapper. pilot_01 launched the child and its saved journal reaches predict_proba_complete and managers_restored, so this early-return branch was not taken."
                           if diagnostic_added and launched_approved and child_completed and not early_failure_recorded
                           else "Branch progress is reported only from the saved source, receipt, and progress evidence."),
        },
    }


def _numeric_replay_check(result: dict[str, Any], pilot: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    probabilities = pilot.get("probabilities") or {}
    ids = probabilities.get("query_ids")
    class_order = probabilities.get("class_order")
    values = probabilities.get("values")
    references = (pilot.get("reference_evidence") or {}).get("selected_reference_probability_rows")
    comparison = pilot.get("comparison") or {}

    if ids != FROZEN_QUERY_IDS:
        issues.append("saved query IDs do not match the frozen two-query order")
    if class_order != FROZEN_CLASS_ORDER:
        issues.append("saved class order does not match the four frozen columns")
    if not isinstance(values, list) or len(values) != 2 or not isinstance(references, list) or len(references) != 2:
        issues.append("saved probability arrays are not two rows")

    per_query: list[dict[str, Any]] = []
    max_difference = 0.0
    exact_numeric_equal = True
    all_rows_valid = not issues
    if not issues:
        for row_index, (model_row, reference_row) in enumerate(zip(values, references)):
            reference_values = reference_row.get("p0_p3") if isinstance(reference_row, dict) else None
            reference_id = reference_row.get("rfid_id") if isinstance(reference_row, dict) else None
            if reference_id != ids[row_index] or not isinstance(model_row, list) or not isinstance(reference_values, list) or len(model_row) != 4 or len(reference_values) != 4:
                issues.append(f"saved row {row_index} has mismatched IDs or shape")
                all_rows_valid = False
                continue
            try:
                model_numbers = [float(item) for item in model_row]
                reference_numbers = [float(item) for item in reference_values]
            except (TypeError, ValueError, OverflowError):
                issues.append(f"saved row {row_index} contains a non-numeric probability")
                all_rows_valid = False
                continue
            finite = all(math.isfinite(item) for item in model_numbers + reference_numbers)
            in_range = all(0.0 <= item <= 1.0 for item in model_numbers + reference_numbers)
            model_sum_error = abs(sum(model_numbers) - 1.0)
            ref_sum_error = abs(sum(reference_numbers) - 1.0)
            row_difference = max(abs(left - right) for left, right in zip(model_numbers, reference_numbers))
            model_argmax = max(range(4), key=model_numbers.__getitem__)
            reference_argmax = max(range(4), key=reference_numbers.__getitem__)
            row_exact_numeric_equal = all(left == right for left, right in zip(model_numbers, reference_numbers))
            exact_numeric_equal &= row_exact_numeric_equal
            argmax_equal = model_argmax == reference_argmax
            max_difference = max(max_difference, row_difference)
            row_pass = finite and in_range and model_sum_error <= 1e-5 and ref_sum_error <= 1e-5 and row_difference <= 1e-4 and argmax_equal
            all_rows_valid &= row_pass
            per_query.append({"query_id": ids[row_index], "max_abs_difference": row_difference,
                              "model_row_sum_error": model_sum_error, "reference_row_sum_error": ref_sum_error,
                              "model_argmax": model_argmax, "reference_argmax": reference_argmax,
                              "exact_numeric_equal_after_float64_parse": row_exact_numeric_equal,
                              "argmax_equal": argmax_equal, "finite_in_range": finite and in_range,
                              "passed": row_pass})

    reported_difference = comparison.get("max_abs_probability_difference")
    reported_tolerance = comparison.get("absolute_tolerance")
    reported_exact_numeric_equal = comparison.get("exact_numeric_equal_after_float64_parse")
    recorded_check = result.get("independent_saved_json_checks", {})
    gates = recorded_check.get("gates", {}) if isinstance(recorded_check, dict) else {}
    metric_agrees = isinstance(reported_difference, (int, float)) and abs(float(reported_difference) - max_difference) <= 1e-12
    exact_equality_agrees = isinstance(reported_exact_numeric_equal, bool) and reported_exact_numeric_equal == exact_numeric_equal
    if isinstance(recorded_check, dict) and isinstance(recorded_check.get("exact_numeric_equal"), bool):
        exact_equality_agrees &= recorded_check["exact_numeric_equal"] == exact_numeric_equal
    tolerance_agrees = isinstance(reported_tolerance, (int, float)) and float(reported_tolerance) == 1e-4
    saved_report_gate = result.get("saved_numeric_replay_gates_passed") is True
    summary_gates = all(gates.get(name) is True for name in (
        "finite_range_shape", "row_sum", "reference_tolerance", "argmax_equal", "reported_gate", "reported_values_agree"
    ))
    claim_scope_ok = (pilot.get("f1_computed") is False and pilot.get("training_performed") is False
                      and pilot.get("inner_labels_loaded_or_used") is False
                      and comparison.get("is_performance_or_F1_claim") is False)
    if not metric_agrees:
        issues.append("computed saved-JSON difference does not agree with the recorded metric")
    if not exact_equality_agrees:
        issues.append("computed float64 exact-equality status does not agree with the saved status")
    if not tolerance_agrees:
        issues.append("recorded comparison tolerance is not the approved 1e-4")
    if not saved_report_gate or not summary_gates:
        issues.append("manager saved-numeric report gates are not all true")
    if not claim_scope_ok:
        issues.append("saved record indicates labels, training, or an F1/performance claim")

    passed = bool(all_rows_valid and metric_agrees and exact_equality_agrees and tolerance_agrees
                  and saved_report_gate and summary_gates and claim_scope_ok)
    return {
        "passed": passed,
        "scope": "saved JSON probabilities and saved selected reference rows only; no inference, labels, F1, or model imports",
        "query_ids": ids,
        "class_order": class_order,
        "shape": [len(values), len(values[0])] if isinstance(values, list) and values and isinstance(values[0], list) else None,
        "computed_max_abs_probability_difference": max_difference if all_rows_valid else None,
        "recorded_max_abs_probability_difference": reported_difference,
        "computed_exact_numeric_equal_after_float64_parse": exact_numeric_equal if all_rows_valid else None,
        "recorded_exact_numeric_equal_after_float64_parse": reported_exact_numeric_equal,
        "exact_equality_status_agrees": exact_equality_agrees,
        "tolerance_passed": bool(all_rows_valid and max_difference <= 1e-4),
        "recorded_tolerance": reported_tolerance,
        "per_query": per_query,
        "manager_saved_numeric_gate": saved_report_gate,
        "summary_numeric_gates": {name: gates.get(name) for name in (
            "finite_range_shape", "row_sum", "reference_tolerance", "argmax_equal", "reported_gate", "reported_values_agree"
        )},
        "no_training_or_f1_claim": claim_scope_ok,
        "issues": issues,
    }


def audit_round(root: Path, source_round: str = "round_010") -> dict[str, Any]:
    if source_round != "round_010":
        raise ValueError("This auditor is bounded to the current round010 provenance contract")
    root = root.resolve()
    round_root = root / "rounds" / source_round
    approved = _json(round_root / "review" / "approved_sources.json")
    if approved.get("schema") != "round010_approved_sources.v1" or not isinstance(approved.get("sha256"), dict):
        raise ValueError("Unexpected round010 approved-source manifest")

    live_checks, excluded_assets = _map_entries(root, approved["sha256"])
    live_source_unchanged = bool(live_checks) and all(item["match"] for item in live_checks)

    receipts = {
        "mock_01": _json(round_root / "logs" / "mock_01" / "receipt.json"),
        "pilot_01": _json(round_root / "logs" / "pilot_01" / "receipt.json"),
    }
    snapshot_reports = [_receipt_snapshot_check(root, source_round, run_id, receipt, approved)
                        for run_id, receipt in receipts.items()]
    executed_snapshot_matches_approved = all(item["snapshot_matches_approved"] for item in snapshot_reports)
    current_source_gate = bool(executed_snapshot_matches_approved and live_source_unchanged)
    mock_gate = (receipts["mock_01"].get("status") == "completed" and receipts["mock_01"].get("exit_code") == 0
                 and receipts["mock_01"].get("launched") is True)
    pilot_matched_mock = (receipts["pilot_01"].get("passed_mock_run_id") == "mock_01" and mock_gate)

    incident_path = round_root / "manager" / "source_freeze_incident.json"
    postcheck_path = round_root / "manager" / "post_execution_hash_check.json"
    incident = _json(incident_path)
    postcheck = _json(postcheck_path)
    result = _json(round_root / "artifacts" / "result.json")
    pilot_result = _json(round_root / "artifacts" / "pilot_01" / "pilot_result.json")

    wrapper_diff = _wrapper_diff(root, source_round, receipts["mock_01"], receipts["pilot_01"], pilot_result, incident)
    saved_numeric = _numeric_replay_check(result, pilot_result)
    recorded_wrapper_check = next((item for item in postcheck.get("checks", [])
                                   if item.get("path") == f"rounds/{source_round}/manager/run_bounded.py"), None)
    incident_consistent = bool(
        incident.get("approved_wrapper_sha") == receipts["pilot_01"].get("wrapper_sha256")
        and incident.get("running_receipt_wrapper_sha") == receipts["pilot_01"].get("wrapper_sha256")
        and incident.get("new_execution_authorized") is False
        and recorded_wrapper_check is not None
        and recorded_wrapper_check.get("expected") == incident.get("approved_wrapper_sha")
        and recorded_wrapper_check.get("actual") == incident.get("current_wrapper_sha")
        and recorded_wrapper_check.get("match") is False
    )

    audit_integrity_passed = bool(executed_snapshot_matches_approved and mock_gate and pilot_matched_mock
                                  and saved_numeric["passed"] and incident_consistent)

    # Deliberately fixed: the historical round010 source-freeze violation is
    # preserved as a failed gate even if a later live tree happens to be clean.
    historical_overall_gate = False
    return {
        "schema": AUDIT_SCHEMA,
        "source_round": source_round,
        "audited_scope": "approved map, mock_01/pilot_01 launch snapshots and receipts, live approved source files, source-freeze incident, and saved two-query probability JSON",
        "prohibited_reads": {"raw": "not read", "npz": "not read or re-hashed", "reference_csv": "not read", "checkpoint": "not loaded or re-hashed", "model_runtime": "not imported or run"},
        "protected_assets_not_reverified": excluded_assets + ([{
            "path": (approved.get("runtime_guards", {}).get("checkpoint", {}) or {}).get("path"),
            "reason": "checkpoint size/SHA are saved metadata only; checkpoint bytes were not accessed",
            "saved_bytes": (approved.get("runtime_guards", {}).get("checkpoint", {}) or {}).get("bytes"),
            "saved_sha256": (approved.get("runtime_guards", {}).get("checkpoint", {}) or {}).get("sha256"),
            "reverified": False,
        }] if (approved.get("runtime_guards", {}).get("checkpoint") or {}).get("path") else []),
        "executed_snapshot_matches_approved": executed_snapshot_matches_approved,
        "snapshot_receipts": snapshot_reports,
        "mock_gate_passed": mock_gate,
        "pilot_followed_matching_mock": pilot_matched_mock,
        "live_source_unchanged": live_source_unchanged,
        "current_source_gate": current_source_gate,
        "current_source_gate_scope": "approved launch snapshots plus currently rehashed non-prohibited source-map files; NPZ/checkpoint content excluded",
        "live_source_checks": live_checks,
        "wrapper_source_diff_and_branch_progress": wrapper_diff,
        "source_freeze_incident_consistent": incident_consistent,
        "source_freeze_incident": {key: incident.get(key) for key in (
            "mutation_at_utc", "approved_wrapper_sha", "running_receipt_wrapper_sha", "current_wrapper_sha", "new_execution_authorized"
        )},
        "saved_numeric_replay_passed": saved_numeric["passed"],
        "saved_numeric_replay": saved_numeric,
        "audit_integrity_passed": audit_integrity_passed,
        "audit_integrity_definition": {
            "passed_when": ["approved launch snapshots match", "saved numeric JSON checks pass", "mock-to-pilot receipt link is consistent", "source-freeze incident metadata matches the saved post-execution check"],
            "live_source_unchanged_is_reported_separately": True,
            "live_source_unchanged_is_not_required_for_audit_integrity": True,
        },
        "historical_overall_gate": historical_overall_gate,
        "historical_gate_evidence": {
            "manager_status": result.get("status"),
            "manager_all_execution_gates_passed": result.get("all_execution_gates_passed"),
            "manager_source_freeze_incident_recorded": result.get("source_freeze_incident_recorded"),
            "pilot_receipt_status": receipts["pilot_01"].get("status"),
            "pilot_receipt_wrapper_unchanged": receipts["pilot_01"].get("wrapper_unchanged"),
            "incident_consistent": incident_consistent,
            "historical_gate_is_never_recomputed_or_forgiven": True,
        },
        "limitations": [
            "NPZ and checkpoint files were explicitly excluded from reads and hashing; their saved manifest metadata is not reverified.",
            "Saved numeric replay checks use only probabilities and selected reference rows already recorded in pilot_result.json.",
            "A live-source clean result cannot rewrite the historical round010 source-freeze incident.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-round", required=True, choices=("round_010",))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", type=Path, help="workspace root (defaults to task-root cwd or an ancestor containing rounds/round_010)")
    args = parser.parse_args()
    starts = [args.root.resolve()] if args.root else [Path.cwd().resolve(), Path(__file__).resolve()]
    root = None
    for start in starts:
        candidates = [start, *start.parents]
        root = next((candidate for candidate in candidates if (candidate / "rounds" / args.source_round).is_dir()), None)
        if root is not None:
            break
    if root is None:
        parser.error("could not locate the task root; pass --root or run from the task-root working directory")
    report = audit_round(root, args.source_round)
    output = (args.output if args.output.is_absolute() else root / args.output).resolve()
    allowed_output_root = (root / "rounds" / "round_013").resolve()
    if not output.is_relative_to(allowed_output_root):
        parser.error("--output must resolve inside rounds/round_013")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "output": str(output),
        "executed_snapshot_matches_approved": report["executed_snapshot_matches_approved"],
        "live_source_unchanged": report["live_source_unchanged"],
        "current_source_gate": report["current_source_gate"],
        "saved_numeric_replay_passed": report["saved_numeric_replay_passed"],
        "audit_integrity_passed": report["audit_integrity_passed"],
        "historical_overall_gate": report["historical_overall_gate"],
    }, ensure_ascii=False))
    return 0 if report["audit_integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
