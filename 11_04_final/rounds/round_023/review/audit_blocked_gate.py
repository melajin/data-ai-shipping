"""Independent read-only audit of round023's RAM-blocked attempt.

This does not load the feature arrays, train or reload models, or invoke the
gate checker. It verifies the recorded zero-fit stop, source/freeze/execution
hash chain, copied inputs, and whether the owned launcher is still present.
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import re
from pathlib import Path

import psutil

ROUND = Path(__file__).resolve().parents[1]
ROOT = ROUND.parents[1]
GATE = ROUND / "artifacts" / "gate"
LOGS = ROUND / "logs"
REVIEW = ROUND / "review"
OUT = REVIEW / "blocked_gate_audit.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    approval_path = REVIEW / "gate_approved_sources.json"
    approval = read_json(approval_path)
    freeze = read_json(ROUND / "manager" / "snapshot_s1_fit_internal_4fold_gate_only" / "freeze.json")
    preflight = read_json(LOGS / "s1_gate_preflight.json")
    receipt = read_json(LOGS / "s1_gate_receipt.json")
    copied = read_json(ROUND / "manager" / "copied_inputs.json")
    blocked = read_json(GATE / "gate_blocked.json")
    progress = read_json(GATE / "fit_progress.json")

    execution_before = receipt.get("hashes_before", {})
    execution_after = receipt.get("hashes_after", {})
    approved_sources = approval.get("source_hashes", {})
    frozen_sources = freeze.get("source_hashes", {})
    source_audit = []
    for rel, expected in approved_sources.items():
        path = ROOT / Path(rel)
        current = sha256(path) if path.is_file() else None
        before = execution_before.get(rel)
        after = execution_after.get(rel)
        frozen = frozen_sources.get(rel)
        source_audit.append({
            "path": rel,
            "approved_sha256": expected,
            "current_sha256": current,
            "frozen_sha256": frozen,
            "execution_before_sha256": before,
            "execution_after_sha256": after,
            "approved_matches_current": current == expected,
            "approved_matches_freeze": frozen == expected,
            "execution_hashes_match_approval": (before == expected and after == expected) if before is not None or after is not None else None,
        })

    contract_rel = "rounds/round_023/manager/runtime_contract.json"
    contract_hash = sha256(ROOT / contract_rel)
    contract_approved_hash = approved_sources.get(contract_rel)
    contract_frozen_hash = frozen_sources.get(contract_rel)
    runtime_contract = read_json(ROOT / contract_rel)
    contract_execution_link_matches = preflight.get("compute_cutoff") == runtime_contract.get("compute_deadline_utc")
    next_resource_contract = read_json(ROUND / "manager" / "next_resource_contract.json")

    copied_audit = []
    for rel, expected in copied.get("copied_sha256", {}).items():
        path = ROUND / Path(rel)
        current = sha256(path) if path.is_file() else None
        copied_audit.append({
            "path": rel,
            "copied_sha256": expected,
            "current_sha256": current,
            "matches": current == expected,
        })

    # The only authorized copied-file difference is the checker path fix.
    checker_rel = "review/verify_gate_result.py"
    old_checker = ROOT / "rounds" / "round_022" / "review" / "verify_gate_result.py"
    new_checker = ROUND / checker_rel
    checker_diff = list(difflib.unified_diff(
        old_checker.read_text(encoding="utf-8").splitlines(),
        new_checker.read_text(encoding="utf-8").splitlines(),
        fromfile="round022/verify_gate_result.py",
        tofile="round023/verify_gate_result.py",
        lineterm="",
    ))
    checker_change_lines = [line for line in checker_diff if line.startswith(("-", "+")) and not line.startswith(("---", "+++"))]
    expected_checker_change = [
        '-    round_dir = root / "rounds" / "round_022"',
        '+    round_dir = out.parents[1]',
    ]

    # Resolve the runner's declared feature input without importing NumPy.
    runner_text = (ROUND / "code" / "run_gate.py").read_text(encoding="utf-8")
    match = re.search(r'DEFAULT_FEATURE_NPZ\s*=\s*Path\(\s*r"([^"]+)"', runner_text)
    feature_path = Path(match.group(1)) if match else None
    feature_hash = sha256(feature_path) if feature_path and feature_path.is_file() else None

    model_dir = GATE / "models"
    evidence_dir = GATE / "feature_evidence"
    model_files = sorted(p.name for p in model_dir.iterdir() if p.is_file()) if model_dir.is_dir() else []
    evidence_files = sorted(p.name for p in evidence_dir.iterdir() if p.is_file()) if evidence_dir.is_dir() else []
    expected_outputs = [GATE / "gate_result.json", GATE / "predictions_baseline.npz", GATE / "predictions_candidate.npz"]
    missing_fit_outputs = [str(p.relative_to(ROOT)).replace("\\", "/") for p in expected_outputs if not p.is_file()]

    active_round023_processes = []
    known_pids = {receipt.get("pid"), receipt.get("launcher_pid")}
    known_pid_matches = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            info = proc.info
            cmdline = info.get("cmdline") or []
            command = " ".join(str(v) for v in cmdline)
            if info["pid"] != psutil.Process().pid and "python" in (info.get("name") or "").lower():
                if "rounds/round_023/manager/launch.py" in command or "round_023\\manager\\launch.py" in command or "round_023/code/run_gate.py" in command or "round_023\\code\\run_gate.py" in command:
                    active_round023_processes.append({"pid": info["pid"], "name": info.get("name"), "cmdline": cmdline})
            if info["pid"] in known_pids:
                known_pid_matches.append({"pid": info["pid"], "name": info.get("name"), "cmdline": cmdline})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    memory = psutil.virtual_memory()
    preflight_checks = blocked.get("resource_checks", [])
    second_check = preflight_checks[1] if len(preflight_checks) > 1 else {}
    normal_guard = int(second_check.get("minimum_free_bytes", 0))
    second_free = int(second_check.get("available_bytes", 0))
    checks = {
        "approval_hash_matches_freeze": freeze.get("approval_sha256") == sha256(approval_path),
        "all_approved_sources_match_current_freeze_and_execution_records": all(
            x["approved_matches_current"] and x["approved_matches_freeze"]
            and (x["execution_hashes_match_approval"] is True
                 or (x["execution_hashes_match_approval"] is None
                     and x["path"] == contract_rel and contract_execution_link_matches))
            for x in source_audit
        ),
        "runtime_contract_unchanged_since_freeze": contract_hash == contract_approved_hash == contract_frozen_hash,
        "copied_inputs_match_except_authorized_checker_edit": all(x["matches"] for x in copied_audit if x["path"] != checker_rel),
        "checker_diff_is_exactly_authorized_path_fix": checker_change_lines == expected_checker_change,
        "fold0_feature_hash_matches_blocked_record": feature_hash is not None and feature_hash == blocked.get("fold0_feature_sha256"),
        "blocked_record_confirms_zero_fit": blocked.get("status") == "blocked_before_fit" and blocked.get("training_fits_started") == 0 and blocked.get("fits_completed") == 0,
        "progress_and_outputs_confirm_zero_models": progress.get("fit_attempts_started") == 0 and progress.get("fits_completed") == 0 and not model_files and not evidence_files and not any(p.is_file() for p in expected_outputs),
        "launcher_exit_code_is_blocked_exit": receipt.get("exit_code") == 3 and receipt.get("stop_reason") is None,
        "normal_ram_guard_failed_at_cv0_feature_precheck": bool(second_check) and second_free < normal_guard and second_check.get("stage") == "cv0_s1_feature_build",
        "owned_round023_launcher_not_still_running": not active_round023_processes,
    }

    # Existing saved-output checker cannot run without gate_result.json. Its
    # round022-specific approval key mapping also skips all five round023 source
    # keys matching its code/config filter; this audit checked them directly.
    checker_hash_skips = 0
    for rel in approved_sources:
        if "/code/" in rel or rel.endswith("/configs/experiment.json"):
            key = {"code/t5_rebuild.py": "t5_rebuild_code", "code/s1_features.py": "s1_feature_code",
                   "code/run_gate.py": "run_gate_code", "configs/experiment.json": "config"}.get(rel.split("round_022/")[-1])
            if key is None:
                checker_hash_skips += 1

    no_fit_confirmed = all(checks.values())
    report = {
        "status": "pass_zero_fit_block_confirmed" if no_fit_confirmed else "fail_audit_inconsistency",
        "audited_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "round": "round_023",
        "execution": {"stage": receipt.get("stage"), "started_at_utc": receipt.get("started_at_utc"),
                      "finished_at_utc": receipt.get("finished_at_utc"), "exit_code": receipt.get("exit_code"),
                      "stop_reason": receipt.get("stop_reason"), "wall_seconds": receipt.get("wall_seconds"),
                      "sampled_peak_family_rss_bytes": receipt.get("sampled_peak_family_rss_bytes"),
                      "sampled_min_available_bytes": receipt.get("sampled_min_available_bytes")},
        "resource_boundary": {"first_available_bytes": preflight.get("available_bytes"),
                              "prefit_second_check_available_bytes": second_free,
                              "required_free_bytes": normal_guard,
                              "shortfall_bytes": max(0, normal_guard - second_free),
                              "reported_expected_peak_bytes": second_check.get("expected_peak_bytes"),
                              "current_audit_available_bytes": int(memory.available),
                              "audit_expected_peak_bytes": 64 * 2**20,
                              "next_round_entry_threshold_gib": next_resource_contract.get("minimum_entry_available_gib"),
                              "round023_full_fit_peak_measured": False,
                              "active_round023_processes": active_round023_processes,
                              "known_owner_pid_matches": known_pid_matches},
        "fit_state": {"gate_blocked_status": blocked.get("status"), "training_fits_started": blocked.get("training_fits_started"),
                      "fits_completed": blocked.get("fits_completed"), "progress_status": progress.get("status"),
                      "progress_fit_attempts_started": progress.get("fit_attempts_started"),
                      "progress_fits_completed": progress.get("fits_completed"), "model_file_count": len(model_files),
                      "feature_evidence_file_count": len(evidence_files), "missing_fit_outputs": missing_fit_outputs,
                      "existing_checker_run": False, "full_model_reinference_possible": False},
        "source_audit": {"approval_sha256": sha256(approval_path), "freeze_approval_sha256": freeze.get("approval_sha256"),
                         "audit_script_sha256": sha256(Path(__file__).resolve()),
                         "sources": source_audit,
                         "runtime_contract": {"path": contract_rel, "current_sha256": contract_hash,
                                              "approved_sha256": contract_approved_hash, "frozen_sha256": contract_frozen_hash,
                                              "execution_deadline_matches_contract": contract_execution_link_matches,
                                              "receipt_hashes_contract": contract_rel in execution_before and contract_rel in execution_after},
                         "copied_inputs": copied_audit,
                         "checker_authorized_diff": checker_change_lines,
                         "checker_approval_hash_mapping_skipped_keys": checker_hash_skips,
                         "fold0_feature_sha256": feature_hash},
        "checks": checks,
        "findings": [
            {"severity": "note", "finding": "Progress file status remains 'running' even though gate_blocked.json and launch receipt document a zero-fit exit-3 RAM block; its two fit counters remain zero."},
            {"severity": "limitation", "finding": "The saved-output checker was not invoked because gate_result.json and model/prediction artifacts do not exist."},
            {"severity": "limitation", "finding": f"The saved-output checker approval-key mapping skips {checker_hash_skips} round023 source keys; this audit verifies their hashes against the approval, freeze and execution records directly."},
            {"severity": "limitation", "finding": "No model was fitted or serialized, so saved-model reload, prediction-probability and argmax reinference checks cannot be performed for round023."},
            {"severity": "limitation", "finding": "The launcher receipt does not hash manager/runtime_contract.json; this audit verifies its current and frozen hashes and confirms the recorded compute cutoff equals its approved deadline, but the receipt does not contain a direct contract hash."},
        ],
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks, "report": str(OUT.relative_to(ROOT)).replace("\\", "/")}, sort_keys=True))
    return 0 if no_fit_confirmed else 2


if __name__ == "__main__":
    raise SystemExit(main())
