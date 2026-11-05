"""Prepare Round025 from the exact frozen Round024 S1-gate sources.

This is a preparation tool only. It performs no training, data scan, scoring,
approval, or freeze. Run only after fresh RAM admission and source-state checks.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

import psutil

SOURCE_ROUND = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
ROUNDS = ROOT / "rounds"
SNAPSHOT = SOURCE_ROUND / "manager" / "snapshot_s1_gate"
APPROVAL = SOURCE_ROUND / "review" / "gate_approved_sources.json"
FREEZE = SNAPSHOT / "freeze.json"
DEST = ROUNDS / "round_025"
STAGING = ROUNDS / "round_025.preparing"
ENTRY_BYTES = int(1.5 * 2**30)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def normalized_arg(arg: str, cwd: str) -> str:
    try:
        path = Path(arg)
        if not path.is_absolute():
            path = Path(cwd) / path
        return os.path.normcase(str(path.resolve(strict=False)))
    except (OSError, ValueError):
        return arg


def resource_preflight() -> dict:
    """One-shot RAM/process check; ignore only an identical-argv Python parent."""
    own_script = Path(__file__).resolve()
    bootstrap_parent = None
    try:
        parent = psutil.Process(os.getppid())
        info = parent.as_dict(attrs=["pid", "name", "cmdline", "cwd"])
        name = info.get("name") or ""
        cmdline = info.get("cmdline") or []
        cwd = info.get("cwd") or str(ROOT)
        if "python" in name.lower():
            for index, arg in enumerate(cmdline):
                if normalized_arg(arg, cwd) == os.path.normcase(str(own_script)):
                    if cmdline[index + 1 :] == sys.argv[1:]:
                        bootstrap_parent = {"pid": int(info["pid"]), "name": name,
                                            "excluded_reason": "direct Python parent has identical script argv"}
                        break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    others = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            info = proc.info
            if int(info["pid"]) == os.getpid() or (bootstrap_parent and int(info["pid"]) == bootstrap_parent["pid"]):
                continue
            name = info.get("name") or ""
            if "python" in name.lower():
                others.append({"pid": int(info["pid"]), "name": name})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    memory = psutil.virtual_memory()
    available = int(memory.available)
    result = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "available_bytes": available,
        "available_gib": available / 2**30,
        "required_entry_bytes": ENTRY_BYTES,
        "required_entry_gib": 1.5,
        "other_python_processes": others,
        "identical_argv_bootstrap_parent_excluded": bootstrap_parent,
        "allowed": available >= ENTRY_BYTES and not others,
    }
    if not result["allowed"]:
        raise RuntimeError(
            f"Round025 preparation deferred: available={result['available_gib']:.4f} GiB "
            f"(required 1.5), other_python={len(others)}; do independent work and recheck once"
        )
    return result


def assert_round024_unstarted() -> dict:
    admission = read_json(SOURCE_ROUND / "manager" / "admission_deferred.json")
    recheck = read_json(SOURCE_ROUND / "manager" / "resource_recheck_after_independent_work.json")
    if (admission.get("decision") != "defer_before_training_launch_and_claim"
            or admission.get("training_launches") != 0 or admission.get("fits_started") != 0):
        raise RuntimeError("Round024 admission record does not confirm zero training launches/fits")
    if (float(recheck.get("available_gib", 99)) >= float(recheck.get("required_gib", 1.5))
            or recheck.get("other_python") not in ([], None)):
        raise RuntimeError("Round024 post-independent-work recheck differs from the recorded pre-admission shortage")

    logs = SOURCE_ROUND / "logs"
    for rel in ("s1_gate.claim", "s1_gate_started.json", "s1_gate_receipt.json",
                "s1_gate.stdout.txt", "s1_gate.stderr.txt"):
        if (logs / rel).exists():
            raise RuntimeError(f"Round024 has a stage launch artifact; refusing source-stage copy: logs/{rel}")
    gate_dir = SOURCE_ROUND / "artifacts" / "gate"
    if gate_dir.exists():
        raise RuntimeError("Round024 gate output directory exists; inspect the run instead of preparing a replay")
    return {
        "admission_record": "rounds/round_024/manager/admission_deferred.json",
        "resource_recheck_record": "rounds/round_024/manager/resource_recheck_after_independent_work.json",
        "recorded_training_launches": admission["training_launches"],
        "recorded_fits_started": admission["fits_started"],
        "recorded_recheck_available_gib": recheck["available_gib"],
        "recorded_recheck_required_gib": recheck["required_gib"],
        "recorded_other_python": recheck.get("other_python", []),
        "stage_claim_receipt_gate_result_models_absent": True,
    }


def verify_frozen_sources() -> tuple[dict, dict, str, str]:
    approval_bytes = APPROVAL.read_bytes()
    approval_hash = sha256_bytes(approval_bytes)
    approval = json.loads(approval_bytes.decode("utf-8-sig"))
    frozen_approval = SNAPSHOT / "approval.json"
    freeze = read_json(FREEZE)
    if approval.get("approved") is not True or approval.get("stage") != "s1_fit_internal_4fold_gate_only":
        raise RuntimeError("Round024 approval is absent or is not the approved S1 gate")
    source_hashes = approval.get("source_hashes")
    frozen_hashes = freeze.get("source_hashes")
    if not isinstance(source_hashes, dict) or len(source_hashes) != 22:
        raise RuntimeError("Expected the exact 22-source Round024 approval")
    normalized = {str(k).replace("\\", "/"): str(v).lower() for k, v in source_hashes.items()}
    frozen_normalized = {str(k).replace("\\", "/"): str(v).lower() for k, v in (frozen_hashes or {}).items()}
    if freeze.get("stage") != "s1_gate" or frozen_normalized != normalized:
        raise RuntimeError("Round024 snapshot freeze source map/stage differs from the approval")
    if (not frozen_approval.is_file() or sha256(frozen_approval).lower() != approval_hash
            or str(freeze.get("approval_sha256", "")).lower() != approval_hash):
        raise RuntimeError("Round024 snapshot approval bytes/hash differ from the current approval")
    if len({PurePosixPath(name).name for name in normalized}) != 22:
        raise RuntimeError("Round024 frozen snapshot has duplicate source basenames")

    checked = {}
    for rel, expected in normalized.items():
        parts = PurePosixPath(rel).parts
        if len(parts) < 3 or parts[:2] != ("rounds", "round_024"):
            raise RuntimeError(f"Approval path is outside Round024: {rel}")
        source = ROOT.joinpath(*parts).resolve()
        frozen = (SNAPSHOT / PurePosixPath(rel).name).resolve()
        if not is_within(source, SOURCE_ROUND) or not is_within(frozen, SNAPSHOT):
            raise RuntimeError(f"Approval path escapes its round/snapshot: {rel}")
        if not source.is_file() or not frozen.is_file():
            raise RuntimeError(f"Approved source or snapshot copy is missing: {rel}")
        source_hash, frozen_hash = sha256(source), sha256(frozen)
        if source_hash.lower() != expected or frozen_hash.lower() != expected:
            raise RuntimeError(f"Round024 approved/frozen hash mismatch: {rel}")
        checked[rel] = {"approved_sha256": expected, "current_source_sha256": source_hash,
                        "frozen_snapshot_sha256": frozen_hash}
    return approval, freeze, approval_hash, sha256(FREEZE)


def selected_sources(approved_hashes: dict) -> list[str]:
    rels = []
    for folder in ("code", "review"):
        rels.extend("rounds/round_024/" + p.relative_to(SOURCE_ROUND).as_posix()
                    for p in sorted((SOURCE_ROUND / folder).glob("*.py")))
    rels.extend([
        "rounds/round_024/configs/experiment.json",
        "rounds/round_024/artifacts/t5_fishing_profiles.npz",
        "rounds/round_024/artifacts/t5_fishing_profiles.manifest.json",
        "rounds/round_024/artifacts/t5_mask_equivalence.json",
        "rounds/round_024/tmp/s1_profiles.sqlite",
        "rounds/round_024/tmp/s1_profiles.sqlite.manifest.json",
        "rounds/round_024/code_author/supplement_metrics.py",
        "rounds/round_024/manager/launch.py",
        "rounds/round_024/manager/freeze_stage.py",
    ])
    rels = list(dict.fromkeys(rels))
    if not rels or any(rel not in approved_hashes for rel in rels):
        raise RuntimeError("A requested Round024 transfer file is not among the 22 approved/frozen sources")
    return rels


def make_runtime(now: dt.datetime) -> dict:
    return {
        "started_utc": now.isoformat(),
        "compute_deadline_utc": (now + dt.timedelta(minutes=40)).isoformat(),
        "manager_deadline_utc": (now + dt.timedelta(minutes=45)).isoformat(),
        "compute_seconds_max": 1800,
        "job_seconds_max": 900,
        "threads_max": 1,
        "concurrency": 1,
        "minimum_available_gib": 1.0,
        "minimum_entry_available_gib": 1.5,
        "expected_peak_gib": 0.5,
        "owned_rss_limit_gib": 0.75,
        "emergency_min_free_gib": 0.5,
        "below_normal_priority": True,
        "production_fits_max": 8,
        "retries": 0,
        "full3fold": 0,
        "s2": 0,
        "procedure": "One fixed Round025 replay of the Round024 S1 gate; no tuning, retry, raw rescan, full3fold, or S2",
    }


def make_round_plan(recheck: dict) -> str:
    return f"""# Round025 — fixed S1 gate after pre-admission resource deferral

Round024 was deferred before launch: its recorded post-independent-work check was {float(recheck['recorded_recheck_available_gib']):.4f} GiB available RAM against the unchanged 1.5 GiB entry threshold, with no other Python process and 0 fits started. This was not an owned-RSS stop or a model result. Round025 preserves the same fixed mathematical comparison: FIT3144, internal stratified 4-fold CV, seed42, fold-local T5 from CV-train labels, S1 train-only profiles with FIT-query self exclusion, identical feature order/model settings, and the AND gate candidate>=1833 and candidate-matched-baseline>=16.

## Resource improvement evidence required

Round025 preparation itself records a fresh one-shot RAM snapshot and requires at least 1.5 GiB available with no other Python process (excluding only a direct Windows Python bootstrap parent whose script argv exactly matches this invocation). Preparation-time admission does not authorize training. Immediately before any future launch, the manager must record another qualifying snapshot. If the same experiment is considered after Round024's pre-admission shortfall, the manager must document concrete changed resource evidence or a reviewed execution-path improvement; elapsed time alone is not evidence. Do not lower the 1.5 GiB entry threshold.

The unchanged resource limits are one process/thread, OMP/OpenBLAS/MKL/NumExpr threads=1, BELOW_NORMAL_PRIORITY_CLASS, 1.0 GiB per-stage RAM guard, 0.5 GiB expected owned peak, 0.75 GiB owned RSS cap, and 0.5 GiB emergency available-RAM floor. The finite budget is at most 8 fits in one launch of at most 900 seconds, 1,800 total compute seconds, and zero retries. No full 3-fold, S2, tuning, or raw rescan.

The Round024 approval and its 22-source snapshot freeze are checked exactly before copying. Approval/freeze files are not copied or inherited: a separate Luna reviewer must inspect Round025 sources and issue a fresh approval before any freeze or training. No Round025 approval, freeze, launch, or result is created by this preparation tool.

Technical goal: complete and independently verify the fixed 8-fit FIT gate under the resource limits. Learning goal: distinguish pre-admission resource shortage from an in-run memory stop and explain how sequential lifetime management affects peak RSS.
"""


def apply_round_specific_patches(path: Path, rel: str) -> dict:
    original = path.read_bytes()
    before_hash = sha256_bytes(original)
    if rel == "review/reinfer_saved.py":
        old = b'ROUND.name != "round_024"'
        new = b'ROUND.name != "round_025"'
    elif rel == "review/verify_gate_result.py":
        old = b'root / "rounds" / "round_024"'
        new = b'root / "rounds" / "round_025"'
    else:
        return {"destination_before_patch_sha256": before_hash, "patches": []}
    count = original.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one round-specific code guard in {rel}, found {count}")
    patched = original.replace(old, new, 1)
    path.write_bytes(patched)
    text = patched.decode("utf-8-sig")
    doc_refs = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if any(token in line for token in ("round_024", "Round024", "round024")):
            doc_refs.append({"line": line_no, "text": line.strip()})
    return {
        "destination_before_patch_sha256": before_hash,
        "patches": [{"kind": "exact code guard path adaptation", "old": old.decode(), "new": new.decode()}],
        "unpatched_round024_text_references": doc_refs,
    }


def main() -> int:
    if SOURCE_ROUND.name != "round_024" or not is_within(SOURCE_ROUND, ROUNDS):
        raise RuntimeError("Run this preparation tool only from rounds/round_024/code_author")
    if DEST.exists() or STAGING.exists():
        raise FileExistsError("round_025 or round_025.preparing already exists; refusing overwrite")

    resource = resource_preflight()
    zero_fit = assert_round024_unstarted()
    approval, freeze, approval_hash, freeze_hash = verify_frozen_sources()
    approved_hashes = {str(k).replace("\\", "/"): str(v).lower()
                       for k, v in approval["source_hashes"].items()}
    transfer = selected_sources(approved_hashes)
    now = dt.datetime.now(dt.timezone.utc)
    round_runtime = make_runtime(now)

    staging_dirs = ("code", "configs", "artifacts", "tmp", "review", "code_author", "manager", "logs")
    STAGING.mkdir(exist_ok=False)
    for name in staging_dirs:
        (STAGING / name).mkdir()

    copied = []
    for rel in transfer:
        source_name = str(PurePosixPath(rel).relative_to("rounds/round_024"))
        frozen_path = SNAPSHOT / PurePosixPath(rel).name
        destination = STAGING.joinpath(*PurePosixPath(source_name).parts)
        shutil.copyfile(frozen_path, destination)
        patch_info = apply_round_specific_patches(destination, source_name)
        copied.append({
            "source_relative_path": rel,
            "frozen_snapshot_relative_path": "rounds/round_024/manager/snapshot_s1_gate/" + frozen_path.name,
            "approved_source_sha256": approved_hashes[rel],
            "destination_relative_path": source_name,
            "destination_sha256": sha256(destination),
            **patch_info,
        })

    write_json(STAGING / "manager" / "runtime_contract.json", round_runtime)
    (STAGING / "ROUND_PLAN.md").write_text(make_round_plan(zero_fit), encoding="utf-8")
    transfer_record = {
        "status": "prepared_unreviewed_not_frozen_not_launched",
        "created_utc": now.isoformat(),
        "source_round": "round_024",
        "destination_round": "round_025",
        "source_approval": {"path": "rounds/round_024/review/gate_approved_sources.json",
                             "sha256": approval_hash, "approved_source_count": 22},
        "source_freeze": {"path": "rounds/round_024/manager/snapshot_s1_gate/freeze.json",
                           "sha256": freeze_hash, "stage": freeze.get("stage"),
                           "approval_sha256": freeze.get("approval_sha256")},
        "round024_zero_fit_evidence": zero_fit,
        "preparation_resource_preflight": resource,
        "copied_files": copied,
        "intended_patches": [
            {"file": "review/reinfer_saved.py", "scope": "only the ROUND.name guard changed to round_025"},
            {"file": "review/verify_gate_result.py", "scope": "only the expected_round code path changed to round_025"},
            {"scope": "remaining simple usage/error/documentation strings mentioning round_024 are recorded per file and line, not broadly replaced"},
        ],
        "approval_or_freeze_copied": False,
        "training_or_calculation_run": False,
    }
    write_json(STAGING / "manager" / "source_transfer.json", transfer_record)
    for entry in copied:
        target = STAGING / entry["destination_relative_path"]
        if sha256(target).lower() != entry["destination_sha256"].lower():
            raise RuntimeError(f"Destination hash changed during Round025 preparation: {target.name}")
    STAGING.rename(DEST)
    print(json.dumps({"status": "prepared_unreviewed_not_frozen_not_launched",
                      "round": str(DEST.relative_to(ROOT)), "copied_files": len(copied),
                      "entry_available_gib": resource["available_gib"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
