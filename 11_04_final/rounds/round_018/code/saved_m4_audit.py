#!/usr/bin/env python3
"""Bounded MODEL-ZERO audit of the saved Round015 M4 evidence.

Only the Python standard library is used.  The two .pt files are read as opaque
bytes for size/SHA-256 only; this module never imports or deserializes them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from datetime import datetime, timezone


PYTHON = Path("C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
SOURCE_PATHS = (
    "rounds/round_018/code/saved_m4_audit.py",
    "rounds/round_018/code/run_saved_m4_audit.ps1",
)
RUN_IDS = {"smoke": "smoke_01", "mock": "mock_01", "audit": "audit_01"}
HISTORICAL_SOURCES = {
    "rounds/round_015/code/m4_synthetic.py": "ac6a12e44bc82fa8a20f2be5a2fd404851e5fd7900d99c5c75a7269069e3dfa0",
    "rounds/round_015/code/test_m4_mock.py": "5d65af83347d68db27525e15f0e94270d25b27f3e7efc8ed71a2d6618d161847",
    "rounds/round_015/code/run_m4.ps1": "678fe8462575375c4bb36e3c474a66629eb46e23963e02e230c97dc90dc31aa4",
}
FIXED_INPUTS = {
    "rounds/round_015/artifacts/m4_synthetic_result.json": (64851, "365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105"),
    "rounds/round_015/artifacts/m4_a_head.pt": (42422, "c33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0"),
    "rounds/round_015/artifacts/m4_b_merged_head.pt": (42464, "8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36"),
    "rounds/round_015/review/approved_sources.json": (1204, "2cede678cba53e4a92832c663bf4968b75ee63b5c1287ad25804aaf3dce59dd4"),
    "rounds/round_015/logs/smoke_01/receipt.json": (13360, "4f9608e11d51bd70e5508ed82f746eb3c03e3319fc5e6f8da1782eff36dd9ad2"),
    "rounds/round_015/logs/mock_01/receipt.json": (11386, "61595d02a9297711dc47ab16569247aea0558906b7c23c58964d0e722976b2bf"),
    "rounds/round_015/logs/synthetic_01/receipt.json": (24542, "c6f9bc8861ffb14629cfa8ccdc84c8a0da55d3f224dc7a0ec430904b39c8affa"),
    "rounds/round_010/manager/summary_stdout.json": None,
}
LIMITS = {"backward": 4, "checkpoint_load": 1, "context_fit": 1, "full_forward": 4, "head_evaluation": 12, "predict_proba": 1}
COMPARISON_NAMES = (
    "M4-a initial copy vs source",
    "M4-b B=0 initialization vs source",
    "native public probability reconstruction",
    "M4-a trained head vs head-only reload",
    "M4-b unmerged vs single merged head",
    "M4-b merged head vs head-only reload",
)
PERMUTATION = [[1, 2, 3, 0], [0, 1, 2, 3], [2, 3, 0, 1], [3, 0, 1, 2]]


class AuditError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fail(message: str) -> None:
    raise AuditError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    fail(f"non-finite JSON constant: {value}")


def contained(root: Path, relative_or_absolute: str) -> Path:
    candidate = Path(relative_or_absolute)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError:
        fail(f"input path escaped task root: {relative_or_absolute}")
    if not resolved.is_file():
        fail(f"input is not a regular file: {relative_or_absolute}")
    return resolved


def sha256_file(path: Path, max_bytes: int | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                fail(f"file exceeds bounded read limit: {path}")
            digest.update(chunk)
    return size, digest.hexdigest()


def strict_json(root: Path, relative: str, max_bytes: int) -> tuple[object, dict[str, object]]:
    path = contained(root, relative)
    stat_size = path.stat().st_size
    if stat_size > max_bytes:
        fail(f"file exceeds bounded JSON input limit: {relative}")
    try:
        raw = path.read_bytes()
        if len(raw) != stat_size:
            fail(f"input changed while read: {relative}")
        value = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid strict UTF-8 JSON in {relative}: {exc}")
    return value, {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def obj(value: object, where: str) -> dict[str, object]:
    if type(value) is not dict:
        fail(f"{where} must be an object")
    return value


def arr(value: object, where: str, length: int | None = None) -> list[object]:
    if type(value) is not list or (length is not None and len(value) != length):
        fail(f"{where} must be an array" + (f" of length {length}" if length is not None else ""))
    return value


def req(mapping: dict[str, object], key: str, expected: type, where: str) -> object:
    if key not in mapping:
        fail(f"missing required field {where}.{key}")
    value = mapping[key]
    if expected is bool:
        if type(value) is not bool:
            fail(f"{where}.{key} must be boolean")
    elif expected is int:
        if type(value) is not int:
            fail(f"{where}.{key} must be integer")
    elif expected is float:
        if type(value) not in (int, float) or type(value) is bool or not math.isfinite(float(value)):
            fail(f"{where}.{key} must be finite number")
    elif type(value) is not expected:
        fail(f"{where}.{key} must be {expected.__name__}")
    return value


def true(mapping: dict[str, object], key: str, where: str) -> None:
    if req(mapping, key, bool, where) is not True:
        fail(f"{where}.{key} must be true")


def false(mapping: dict[str, object], key: str, where: str) -> None:
    if req(mapping, key, bool, where) is not False:
        fail(f"{where}.{key} must be false")


def finite_number(value: object, where: str) -> float:
    if type(value) not in (int, float) or type(value) is bool or not math.isfinite(float(value)):
        fail(f"{where} must be a finite JSON number")
    return float(value)


def assert_case_safe_keys(summary: dict[str, object]) -> None:
    keys = list(summary)
    if any(type(key) is not str or not key for key in keys):
        fail("projected summary keys must be non-empty strings")
    folded = [key.casefold() for key in keys]
    if len(folded) != len(set(folded)):
        fail("case-insensitive summary-key collision")


def load_map(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    value, metadata = strict_json(root, "rounds/round_018/review/approved_sources.json", 64 * 1024)
    approved = obj(value, "approved_sources")
    if approved.get("schema") != "round018_approved_sources.v1" or approved.get("round") != "round_018":
        fail("approved source map schema/round mismatch")
    hashes = obj(approved.get("sha256"), "approved_sources.sha256")
    if set(hashes) != set(SOURCE_PATHS):
        fail("approved-source map must enumerate the exact two frozen source paths")
    for relative in SOURCE_PATHS:
        value_hash = hashes[relative]
        if type(value_hash) is not str or len(value_hash) != 64 or any(ch not in "0123456789abcdef" for ch in value_hash):
            fail(f"invalid approved SHA-256 for {relative}")
    manifest_value, manifest_meta = strict_json(root, "rounds/round_018/code/candidate_sources.json", 64 * 1024)
    manifest = obj(manifest_value, "candidate_sources")
    if manifest.get("schema") != "round018_candidate_sources.v1" or manifest.get("round") != "round_018":
        fail("candidate manifest schema/round mismatch")
    source_hashes = obj(manifest.get("source_files_sha256"), "candidate_sources.source_files_sha256")
    if set(source_hashes) != set(SOURCE_PATHS):
        fail("candidate manifest must enumerate the exact two frozen source paths")
    ack_value, ack_meta = strict_json(root, "rounds/round_018/code/author_freeze_ack.json", 64 * 1024)
    ack = obj(ack_value, "author_freeze_ack")
    if ack.get("schema") != "round018_author_freeze_ack.v1" or ack.get("write_freeze") is not True:
        fail("author write-stop ACK missing or invalid")
    if ack.get("candidate_manifest_sha256") != manifest_meta["sha256"]:
        fail("author ACK does not bind the direct candidate-manifest hash")
    ack_hashes = obj(ack.get("source_files_sha256"), "author_freeze_ack.source_files_sha256")
    for relative in SOURCE_PATHS:
        current_path = contained(root, relative)
        current_size, current_sha = sha256_file(current_path, 2 * 1024 * 1024)
        if source_hashes.get(relative) != current_sha or ack_hashes.get(relative) != current_sha or hashes.get(relative) != current_sha:
            fail(f"live source, candidate, ACK and approved map disagree: {relative}")
    if approved.get("candidate_manifest_sha256") != manifest_meta["sha256"]:
        fail("approved map candidate-manifest hash mismatch")
    if approved.get("candidate_freeze_ack_sha256") != ack_meta["sha256"]:
        fail("approved map author-ACK hash mismatch")
    return approved, {
        "approved_map": metadata,
        "candidate_manifest": manifest_meta,
        "author_freeze_ack": ack_meta,
        "source_hashes": {path: hashes[path] for path in SOURCE_PATHS},
    }


def write_json_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def prepare_run(root: Path, mode: str) -> tuple[Path, dict[str, object], dict[str, object]]:
    approved, attest = load_map(root)
    run_id = RUN_IDS[mode]
    run_dir = root / "rounds" / "round_018" / "logs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    claim_path = run_dir / "execution.claim"
    receipt_path = run_dir / "receipt.json"
    if receipt_path.exists() or not claim_path.is_file():
        fail(f"wrapper execution claim missing or duplicate {mode} run forbidden")
    claim_value, _ = strict_json(root, claim_path.relative_to(root).as_posix(), 64 * 1024)
    claim = obj(claim_value, "execution_claim")
    if (claim.get("schema") != "round018_execution_claim.v1" or claim.get("run_id") != run_id
            or claim.get("mode") != mode
            or claim.get("approved_map_sha256") != attest["approved_map"]["sha256"]
            or claim.get("source_hashes") != attest["source_hashes"]):
        fail("wrapper execution claim does not bind this approved source set and mode")
    snapshot_dir = run_dir / "source"
    snapshot_dir.mkdir(exist_ok=False)
    snapshots = []
    for relative in SOURCE_PATHS:
        source = contained(root, relative)
        destination = snapshot_dir / Path(relative).name
        with source.open("rb") as src, destination.open("xb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        _, snapshot_sha = sha256_file(destination, 2 * 1024 * 1024)
        expected = attest["source_hashes"][relative]
        snapshots.append({"path": relative, "snapshot_path": str(destination), "expected_sha256": expected,
                          "snapshot_sha256": snapshot_sha, "match": snapshot_sha == expected})
    if any(item["match"] is not True for item in snapshots):
        fail("source snapshot hash mismatch")
    attest["snapshots"] = snapshots
    return run_dir, approved, attest


def check_saved_source_map(root: Path, receipt: dict[str, object], expected_map_sha: str, mode: str) -> None:
    where = f"round015.{mode}_receipt"
    for field in ("approval_map_sha256_before", "approval_map_sha256_after"):
        if req(receipt, field, str, where) != expected_map_sha:
            fail(f"{where}.{field} differs from fixed historical map")
    true(receipt, "approval_map_unchanged", where)
    for name in ("live_precheck", "live_postcheck"):
        checks = arr(receipt.get(name), f"{where}.{name}", len(HISTORICAL_SOURCES))
        got = {}
        for i, item in enumerate(checks):
            entry = obj(item, f"{where}.{name}[{i}]")
            path = req(entry, "path", str, f"{where}.{name}[{i}]")
            if path in got:
                fail(f"duplicate path in {where}.{name}")
            got[path] = entry
        if set(got) != set(HISTORICAL_SOURCES):
            fail(f"{where}.{name} source set mismatch")
        for path, expected in HISTORICAL_SOURCES.items():
            entry = got[path]
            if req(entry, "expected_sha256", str, f"{where}.{name}.{path}") != expected:
                fail(f"{where}.{name} expected SHA mismatch for {path}")
            if req(entry, "actual_sha256", str, f"{where}.{name}.{path}") != expected:
                fail(f"{where}.{name} actual SHA mismatch for {path}")
            true(entry, "match", f"{where}.{name}.{path}")
    snapshots = arr(receipt.get("snapshots"), f"{where}.snapshots", len(HISTORICAL_SOURCES))
    seen = set()
    for i, item in enumerate(snapshots):
        entry = obj(item, f"{where}.snapshots[{i}]")
        path = req(entry, "path", str, f"{where}.snapshots[{i}]")
        if path not in HISTORICAL_SOURCES or path in seen:
            fail(f"unexpected/duplicate snapshot path in {where}: {path}")
        seen.add(path)
        expected = HISTORICAL_SOURCES[path]
        if req(entry, "expected_sha256", str, f"{where}.snapshots[{i}]") != expected or req(entry, "snapshot_sha256", str, f"{where}.snapshots[{i}]") != expected:
            fail(f"snapshot digest mismatch in {where}: {path}")
        true(entry, "match", f"{where}.snapshots[{i}]")
        snapshot_path = contained(root, req(entry, "snapshot_path", str, f"{where}.snapshots[{i}]"))
        size, digest = sha256_file(snapshot_path, 4 * 1024 * 1024)
        if digest != expected:
            fail(f"actual snapshot bytes differ from frozen digest: {path}")
    if seen != set(HISTORICAL_SOURCES):
        fail(f"snapshot source set mismatch in {where}")
    post = arr(receipt.get("snapshot_postcheck"), f"{where}.snapshot_postcheck", len(HISTORICAL_SOURCES))
    post_seen = set()
    for i, item in enumerate(post):
        entry = obj(item, f"{where}.snapshot_postcheck[{i}]")
        path = req(entry, "path", str, f"{where}.snapshot_postcheck[{i}]")
        if path not in HISTORICAL_SOURCES or path in post_seen or req(entry, "snapshot_sha256", str, f"{where}.snapshot_postcheck[{i}]") != HISTORICAL_SOURCES[path]:
            fail(f"snapshot postcheck mismatch in {where}: {path}")
        post_seen.add(path)
        true(entry, "match", f"{where}.snapshot_postcheck[{i}]")
    if post_seen != set(HISTORICAL_SOURCES):
        fail(f"snapshot postcheck source set mismatch in {where}")


def require_completed_receipt(receipt: dict[str, object], mode: str) -> None:
    where = f"round015.{mode}_receipt"
    if req(receipt, "schema", str, where) != "round015_process_receipt.v1" or req(receipt, "mode", str, where) != mode:
        fail(f"{where} schema/mode mismatch")
    true(receipt, "completed", where)
    true(receipt, "launched", where)
    if req(receipt, "exit_code", int, where) != 0:
        fail(f"{where}.exit_code must be zero")
    true(receipt, "owned_process_exited", where)
    true(receipt, "owned_tree_clear", where)
    true(receipt, "stdout_stderr_drained", where)
    if receipt.get("error") is not None:
        fail(f"{where} must have null error")


def synthetic_wrapper_valid(receipt: dict[str, object]) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != "round015_process_receipt.v1" or receipt.get("mode") != "synthetic":
        return False
    if receipt.get("completed") is not True:
        return False
    process = receipt.get("process")
    if type(process) is not dict:
        return False
    return (process.get("exit_code") == 0 and process.get("exit_confirmed") is True
            and process.get("timed_out") is False and process.get("memory_stop") is False
            and process.get("owned_tree_clear") is True and process.get("stdout_stderr_drained") is True)


def numeric_saved_checks(result: dict[str, object]) -> dict[str, object]:
    if req(result, "schema", str, "result") != "round015_m4_synthetic_result.v1" or req(result, "status", str, "result") != "completed":
        fail("saved M4 result schema/status mismatch")
    if req(result, "scope", str, "result") != "synthetic-only external-head mechanics; no project data, F1, performance selection, or hardware validation":
        fail("saved result scope does not match the bounded synthetic contract")
    synth = obj(result.get("synthetic"), "result.synthetic")
    if req(synth, "seed", int, "result.synthetic") != 20261112:
        fail("synthetic seed mismatch")
    if arr(synth.get("context_shape"), "result.synthetic.context_shape", 2) != [16, 8] or arr(synth.get("target_shape"), "result.synthetic.target_shape", 2) != [4, 8]:
        fail("synthetic context/target shape mismatch")
    true(synth, "features_are_standard_normal", "result.synthetic")
    true(synth, "target_labels_created_after_predict_proba", "result.synthetic")
    false(synth, "target_labels_passed_to_fit_or_predict_proba", "result.synthetic")
    if synth.get("context_labels") != [0, 1, 2, 3] * 4 or synth.get("target_labels") != [0, 1, 2, 3]:
        fail("synthetic labels/order mismatch")

    runtime = obj(result.get("runtime"), "result.runtime")
    runtime_expect = {"amp": False, "auto_download": False, "average_logits": True, "batch_size": 1, "class_shuffle": "shift",
                      "device": "cpu", "fa3": False, "feature_shuffle": "none", "kv_cache": False, "n_estimators": 4,
                      "norm_methods": ["none"], "tabicl": "2.2.0", "temperature": 0.9, "torch": "2.6.0+cpu", "torch_dtype": "float32"}
    for key, expected in runtime_expect.items():
        if runtime.get(key) != expected or (type(expected) is bool and type(runtime.get(key)) is not bool):
            fail(f"saved runtime config mismatch: {key}")
    threads = obj(runtime.get("torch_threads"), "result.runtime.torch_threads")
    if req(threads, "intra_op", int, "result.runtime.torch_threads") != 3 or req(threads, "interop", int, "result.runtime.torch_threads") != 1:
        fail("torch thread count mismatch")
    checkpoint = obj(runtime.get("checkpoint"), "result.runtime.checkpoint")
    if req(checkpoint, "bytes", int, "result.runtime.checkpoint") != 110368038 or req(checkpoint, "sha256", str, "result.runtime.checkpoint") != "bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0":
        fail("saved checkpoint metadata mismatch (metadata only; checkpoint not read)")
    if req(checkpoint, "path", str, "result.runtime.checkpoint").replace("\\", "/").split("/")[-1] != "tabicl-classifier-v2-20260212.ckpt":
        fail("checkpoint basename mismatch")

    calls = obj(result.get("call_counts"), "result.call_counts")
    for name, expected in (("limits", LIMITS), ("observed", LIMITS)):
        values = obj(calls.get(name), f"result.call_counts.{name}")
        if values != expected or any(type(v) is not int for v in values.values()):
            fail(f"saved call counts differ from fixed contract: {name}")

    comparisons = arr(result.get("comparisons"), "result.comparisons", 6)
    comparison_summary = []
    for index, item in enumerate(comparisons):
        entry = obj(item, f"result.comparisons[{index}]")
        where = f"result.comparisons[{index}]"
        if req(entry, "name", str, where) != COMPARISON_NAMES[index]:
            fail(f"comparison order/name mismatch at index {index}")
        true(entry, "all_checks_pass", where)
        true(entry, "argmax_equal", where)
        logit_delta = finite_number(entry.get("max_abs_logit_difference"), f"{where}.max_abs_logit_difference")
        prob_delta = finite_number(entry.get("max_abs_probability_difference"), f"{where}.max_abs_probability_difference")
        if logit_delta > 1e-5 or prob_delta > 1e-6:
            fail(f"saved comparison exceeds fixed numeric tolerance: {where}")
        for check_name in ("baseline_probability_checks", "candidate_probability_checks"):
            checks = obj(entry.get(check_name), f"{where}.{check_name}")
            true(checks, "finite", f"{where}.{check_name}")
            true(checks, "range_0_1", f"{where}.{check_name}")
            row_error = finite_number(checks.get("max_abs_row_sum_error"), f"{where}.{check_name}.max_abs_row_sum_error")
            if row_error > 1e-6:
                fail(f"row-sum error exceeds tolerance: {where}.{check_name}")
        comparison_summary.append({"name": COMPARISON_NAMES[index], "logit_delta": logit_delta, "probability_delta": prob_delta, "argmax_equal": True})

    capture = obj(result.get("readout_capture"), "result.readout_capture")
    if arr(capture.get("weight_shape"), "result.readout_capture.weight_shape", 2) != [10, 1024] or arr(capture.get("bias_shape"), "result.readout_capture.bias_shape", 1) != [10]:
        fail("saved readout head shapes mismatch")
    if arr(capture.get("cached_hidden_shape"), "result.readout_capture.cached_hidden_shape", 3) != [4, 4, 1024] or arr(capture.get("cached_logits_shape"), "result.readout_capture.cached_logits_shape", 3) != [4, 4, 10]:
        fail("saved target cache shapes mismatch")
    true(capture, "cached_target_only", "result.readout_capture")
    if arr(capture.get("observed_full_hook_rows"), "result.readout_capture.observed_full_hook_rows", 2) != [16, 4]:
        fail("hook row counts mismatch")
    if capture.get("class_shuffle_order") != PERMUTATION:
        fail("class permutation mismatch")
    if req(capture, "canonical_restore", str, "result.readout_capture") != "member output[..., p]" or req(capture, "member_targets", str, "result.readout_capture") != "p[y_target]":
        fail("class permutation contract mismatch")
    source_recalc = obj(capture.get("source_head_recalculation"), "result.readout_capture.source_head_recalculation")
    true(source_recalc, "exact_equal", "result.readout_capture.source_head_recalculation")
    true(source_recalc, "within_1e_5", "result.readout_capture.source_head_recalculation")
    if finite_number(source_recalc.get("max_abs_first4_logit_difference"), "source_head_recalculation.max_abs_first4_logit_difference") > 1e-5:
        fail("source head recalculation exceeds raw-logit tolerance")
    public = obj(capture.get("public_probability_reconstruction"), "result.readout_capture.public_probability_reconstruction")
    true(public, "argmax_equal", "public_probability_reconstruction")
    if req(public, "exact_equal", bool, "public_probability_reconstruction") is not False:
        fail("recorded public probability reconstruction should preserve its non-exact comparison")
    public_delta = finite_number(public.get("max_abs_probability_difference"), "public_probability_reconstruction.max_abs_probability_difference")
    if public_delta > 1e-6:
        fail("public probability reconstruction exceeds tolerance")
    probabilities = obj(public.get("probabilities"), "public_probability_reconstruction.probabilities")
    true(probabilities, "finite", "public probabilities")
    true(probabilities, "range_0_1", "public probabilities")
    true(probabilities, "row_sum_within_1e_6", "public probabilities")
    if arr(probabilities.get("shape"), "public probabilities.shape", 2) != [4, 4]:
        fail("public probability shape mismatch")
    rows = arr(probabilities.get("values"), "public probabilities.values", 4)
    row_errors = []
    for row_index, row_value in enumerate(rows):
        row = arr(row_value, f"public probabilities.values[{row_index}]", 4)
        values = [finite_number(v, f"public probabilities.values[{row_index}]") for v in row]
        if any(v < 0.0 or v > 1.0 for v in values):
            fail("public probability outside [0,1]")
        error = abs(sum(values) - 1.0)
        row_errors.append(error)
        if error > 1e-6:
            fail("public probability row sum exceeds tolerance")
    stated_row_error = finite_number(probabilities.get("max_abs_row_sum_error"), "public probabilities.max_abs_row_sum_error")
    if stated_row_error > 1e-6 or abs(max(row_errors) - stated_row_error) > 1e-6:
        fail("stated public row-sum error is inconsistent with saved probabilities")

    a = obj(result.get("m4_a"), "result.m4_a")
    true(a, "bias_exactly_unchanged", "result.m4_a")
    true(a, "inactive_six_weight_rows_exactly_unchanged", "result.m4_a")
    true(a, "reload_weight_exact", "result.m4_a")
    true(a, "reload_bias_exact", "result.m4_a")
    if req(a, "trainable", str, "result.m4_a") != "copied W only; original bias fixed":
        fail("M4-a trainable contract mismatch")
    optimizer_a = obj(a.get("optimizer"), "result.m4_a.optimizer")
    _check_optimizer(optimizer_a, "result.m4_a.optimizer")
    a_grads = arr(a.get("gradient_checks"), "result.m4_a.gradient_checks", 2)
    for step, item in enumerate(a_grads, 1):
        grad = obj(item, f"result.m4_a.gradient_checks[{step - 1}]")
        if req(grad, "step", int, f"result.m4_a.gradient_checks[{step - 1}]") != step:
            fail("M4-a gradient step order mismatch")
        true(grad, "weight_grad_finite_nonzero", f"result.m4_a.gradient_checks[{step - 1}]")
        true(grad, "inactive_rows_gradient_exact_zero", f"result.m4_a.gradient_checks[{step - 1}]")
    true(obj(a.get("reload_comparison"), "result.m4_a.reload_comparison"), "all_checks_pass", "result.m4_a.reload_comparison")

    b = obj(result.get("m4_b"), "result.m4_b")
    true(b, "bias_exactly_unchanged", "result.m4_b")
    true(b, "inactive_six_B_rows_exactly_unchanged", "result.m4_b")
    true(b, "duplicate_merge_rejected", "result.m4_b")
    true(b, "reload_weight_exact", "result.m4_b")
    true(b, "reload_bias_exact", "result.m4_b")
    if req(b, "merge_count", int, "result.m4_b") != 1 or req(b, "merge_formula", str, "result.m4_b") != "W_eff = W0 + B @ A":
        fail("M4-b merge contract mismatch")
    if req(b, "trainable", str, "result.m4_b") != "A[2,1024], B[10,2]; W0 and bias fixed":
        fail("M4-b trainable contract mismatch")
    _check_optimizer(obj(b.get("optimizer"), "result.m4_b.optimizer"), "result.m4_b.optimizer")
    initialization = obj(b.get("initialization"), "result.m4_b.initialization")
    if req(initialization, "seed", int, "result.m4_b.initialization") != 20261113 or initialization.get("A") != "normal(0,0.01)" or initialization.get("B") != "zeros":
        fail("M4-b initialization mismatch")
    b_grads = arr(b.get("gradient_checks"), "result.m4_b.gradient_checks", 2)
    grad1, grad2 = (obj(b_grads[0], "result.m4_b.gradient_checks[0]"), obj(b_grads[1], "result.m4_b.gradient_checks[1]"))
    if req(grad1, "step", int, "result.m4_b.gradient_checks[0]") != 1 or req(grad2, "step", int, "result.m4_b.gradient_checks[1]") != 2:
        fail("M4-b gradient step order mismatch")
    true(grad1, "A_grad_exact_zero_at_B_zero", "result.m4_b.gradient_checks[0]")
    true(grad1, "B_grad_finite_nonzero", "result.m4_b.gradient_checks[0]")
    true(grad2, "A_grad_finite_nonzero", "result.m4_b.gradient_checks[1]")
    true(grad2, "B_grad_finite_nonzero", "result.m4_b.gradient_checks[1]")
    for index, grad in enumerate((grad1, grad2)):
        true(grad, "inactive_B_rows_gradient_exact_zero", f"result.m4_b.gradient_checks[{index}]")
    true(obj(b.get("merge_comparison"), "result.m4_b.merge_comparison"), "all_checks_pass", "result.m4_b.merge_comparison")
    true(obj(b.get("reload_comparison"), "result.m4_b.reload_comparison"), "all_checks_pass", "result.m4_b.reload_comparison")

    upstream = obj(result.get("upstream_model"), "result.upstream_model")
    true(upstream, "unchanged_after_capture_and_head_training", "result.upstream_model")
    true(upstream, "hooks_restored", "result.upstream_model")
    module_states = obj(upstream.get("module_training_before_after"), "result.upstream_model.module_training_before_after")
    if "" not in module_states or type(module_states[""]) is not bool or module_states[""] is not False:
        fail("empty root module key missing/invalid")
    if not module_states or any(type(value) is not bool or value is not False for value in module_states.values()):
        fail("upstream module training states must all remain false")
    for key in ("buffer_sha256_before_after", "gradient_state_sha256_before_after"):
        value = req(upstream, key, str, "result.upstream_model")
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            fail(f"invalid upstream provenance digest: {key}")

    claims = obj(result.get("claims"), "result.claims")
    for key in ("f1_computed", "full_modified_model_save_reload_tested", "performance_selected", "project_data_opened", "real_hardware_tested"):
        false(claims, key, "result.claims")
    return {
        "numeric_saved_checks_pass": True,
        "comparison_count": len(comparisons),
        "comparisons": comparison_summary,
        "raw_tolerance": 1e-5,
        "probability_tolerance": 1e-6,
        "row_sum_tolerance": 1e-6,
        "max_saved_probability_delta": max(item["probability_delta"] for item in comparison_summary),
        "max_observed_public_row_sum_error_recomputed_from_saved_values": max(row_errors),
        "call_counts": LIMITS,
        "empty_root_module_key_preserved": True,
        "tensor_recalculation_performed": False,
    }


def _check_optimizer(value: dict[str, object], where: str) -> None:
    expected = {"name": "SGD", "steps": 2, "lr": 0.001, "momentum": 0.0, "weight_decay": 0.0}
    for key, exp in expected.items():
        got = value.get(key)
        if type(exp) is float:
            if finite_number(got, f"{where}.{key}") != exp:
                fail(f"{where}.{key} mismatch")
        elif type(got) is not type(exp) or got != exp:
            fail(f"{where}.{key} mismatch")


def process_smoke(root: Path) -> dict[str, object]:
    value, metadata = strict_json(root, "rounds/round_018/logs/smoke_01/probe_receipt.json", 128 * 1024)
    batch = obj(value, "probe_receipt")
    if req(batch, "schema", str, "probe_receipt") != "round018_process_probe_batch.v1":
        fail("probe receipt schema mismatch")
    true(batch, "completed", "probe_receipt")
    probes = arr(batch.get("probes"), "probe_receipt.probes", 4)
    labels = ["immediate_exit_0", "immediate_exit_7", "monitored_success", "deadline_timeout"]
    expected_codes = [0, 7, 0]
    for index, label in enumerate(labels):
        row = obj(probes[index], f"probe_receipt.probes[{index}]")
        if req(row, "label", str, f"probe[{index}]") != label:
            fail("probe order mismatch")
        true(row, "exit_confirmed", f"probe[{index}]")
        true(row, "stdout_stderr_drained", f"probe[{index}]")
        true(row, "owned_tree_clear", f"probe[{index}]")
        if req(row, "exit_observed", bool, f"probe[{index}]") is not True:
            fail(f"process exit was not observed: {label}")
        observed_at = finite_number(row.get("exit_observed_elapsed_seconds"), f"probe[{index}].exit_observed_elapsed_seconds")
        deadline = finite_number(row.get("wait_deadline_seconds"), f"probe[{index}].wait_deadline_seconds")
        if index < 3:
            if req(row, "exit_code", int, f"probe[{index}]") != expected_codes[index]:
                fail(f"normal probe exit mismatch: {label}")
            if observed_at >= deadline or req(row, "classification", str, f"probe[{index}]") != ("nonzero_exit" if index == 1 else "completed"):
                fail(f"normal exit lacks monotonic pre-deadline evidence: {label}")
            false(row, "actual_wait_deadline_reached", f"probe[{index}]")
            false(row, "timed_out", f"probe[{index}]")
            false(row, "memory_stop", f"probe[{index}]")
        else:
            true(row, "actual_wait_deadline_reached", f"probe[{index}]")
            true(row, "timed_out", f"probe[{index}]")
            if req(row, "classification", str, f"probe[{index}]") != "deadline_timeout":
                fail("timeout classification mismatch")
            if req(row, "wait_returned", bool, f"probe[{index}]"):
                fail("deadline probe unexpectedly returned before timeout")
            if finite_number(row.get("wait_returned_elapsed_seconds"), f"probe[{index}].wait_returned_elapsed_seconds") < deadline:
                fail("deadline probe lacks monotonic timeout-wait evidence")
            false(row, "memory_stop", f"probe[{index}]")
            true(row, "kill_attempted", f"probe[{index}]")
            req(row, "exit_code", int, f"probe[{index}]")
    return {"process_control_probe_pass": True, "probe_count": 4, "probes": probes,
            "probe_receipt": metadata, "wait_false_alone_created_timeout": False,
            "owned_children_all_exit_confirmed": all(obj(row, "probe").get("exit_confirmed") is True for row in probes)}


def mock_contract(root: Path, approved_sha: str) -> dict[str, object]:
    cases = []
    def record(name: str, condition: bool) -> None:
        if not condition:
            fail(f"negative mock failed: {name}")
        cases.append({"case": name, "passed": True})

    classifier_value, classifier_metadata = strict_json(
        root, "rounds/round_018/logs/mock_01/classifier_cases.json", 32 * 1024)
    classifier = obj(classifier_value, "classifier_cases")
    if req(classifier, "schema", str, "classifier_cases") != "round018_classifier_cases.v1":
        fail("classifier mock schema mismatch")
    if req(classifier, "production_function", str, "classifier_cases") != "Get-ProcessClassification":
        fail("classifier mock was not produced by the live PowerShell classifier")
    classifier_cases = arr(classifier.get("cases"), "classifier_cases.cases", 4)
    expected_classifier = {
        "deadline_before": "completed",
        "deadline_after": "deadline_timeout",
        "deadline_boundary": "indeterminate",
        "memory_stop": "memory_stop",
    }
    for row_value in classifier_cases:
        row = obj(row_value, "classifier case")
        name = req(row, "case", str, "classifier case")
        if name not in expected_classifier or req(row, "actual", str, "classifier case") != expected_classifier[name]:
            fail(f"production classifier counterexample failed: {name}")
        true(row, "passed", f"classifier case {name}")
        del expected_classifier[name]
    if expected_classifier:
        fail(f"production classifier cases missing: {sorted(expected_classifier)}")
    record("production deadline-before/after/boundary and memory-stop cases", True)

    empty_key_fixture = json.loads('{"":false,"child":false}', object_pairs_hook=unique_object, parse_constant=reject_constant)
    record("empty root module key retained", type(empty_key_fixture) is dict and "" in empty_key_fixture and empty_key_fixture[""] is False)
    for label, text in (
        ("duplicate key", '{"a":1,"a":2}'),
        ("NaN", '{"a":NaN}'),
        ("Infinity", '{"a":Infinity}'),
    ):
        rejected = False
        try:
            json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
        except AuditError:
            rejected = True
        record(f"reject {label}", rejected)
    def mock_result_schema(value: object) -> None:
        fixture = obj(value, "mock_result")
        req(fixture, "status", str, "mock_result")
        obj(fixture.get("claims"), "mock_result.claims")
        arr(fixture.get("comparisons"), "mock_result.comparisons")
    rejected = False
    try:
        mock_result_schema({"status": "completed", "claims": {}})
    except AuditError:
        rejected = True
    record("reject missing field", rejected)
    rejected = False
    try:
        mock_result_schema({"status": "completed", "claims": [], "comparisons": []})
    except AuditError:
        rejected = True
    record("reject wrong type", rejected)
    fake_completed = {"schema": "round015_process_receipt.v1", "mode": "synthetic", "completed": True,
                      "process": {"exit_code": 0, "exit_confirmed": True, "timed_out": True,
                                  "memory_stop": False, "owned_tree_clear": True, "stdout_stderr_drained": True}}
    record("reject completed claim with timeout", not synthetic_wrapper_valid(fake_completed))
    historical_false = dict(fake_completed, completed=False)
    record("preserve historical wrapper failure", not synthetic_wrapper_valid(historical_false))
    record("approved map sha bound", len(approved_sha) == 64)
    return {"stdlib_negative_mock_pass": True, "production_classifier_cases": classifier_metadata,
            "case_count": len(cases), "cases": cases,
            "model_execution": False, "checkpoint_access": False, "tensor_replay": False}


def validate_historical_receipts(root: Path, metadata: dict[str, dict[str, object]]) -> dict[str, object]:
    map_path = contained(root, "rounds/round_015/review/approved_sources.json")
    fixed_map_sha = FIXED_INPUTS["rounds/round_015/review/approved_sources.json"][1]
    for path, (expected_size, expected_sha) in FIXED_INPUTS.items():
        resolved = contained(root, path)
        if path.endswith(".pt"):
            size, digest = sha256_file(resolved, 2 * 1024 * 1024)
        else:
            limit = 128 * 1024 if path.endswith("summary_stdout.json") else 256 * 1024
            size, digest = sha256_file(resolved, limit)
        if expected_size is not None and size != expected_size:
            fail(f"fixed input size mismatch: {path}")
        if expected_sha is not None and digest != expected_sha:
            fail(f"fixed input SHA-256 mismatch: {path}")
        metadata[path] = {"path": path, "bytes": size, "sha256": digest,
                          "fixed_digest_required": expected_sha is not None,
                          "interpretation": "opaque bytes; no deserialization" if path.endswith(".pt") else "strict JSON evidence" if path.endswith(".json") else ""}

    historical_map, _ = strict_json(root, "rounds/round_015/review/approved_sources.json", 64 * 1024)
    historical_map = obj(historical_map, "round015.approved_sources")
    if historical_map.get("schema") != "round015_approved_sources.v1" or historical_map.get("round") != "round_015":
        fail("Round015 approved-source map schema mismatch")
    historical_hashes = historical_map.get("source_sha256", historical_map.get("sha256"))
    historical_hashes = obj(historical_hashes, "round015.approved_sources.source_hashes")
    if historical_hashes != HISTORICAL_SOURCES:
        fail("Round015 approved-source map does not match fixed source set/hashes")
    for relative, expected in HISTORICAL_SOURCES.items():
        live = contained(root, relative)
        if sha256_file(live, 4 * 1024 * 1024)[1] != expected:
            fail(f"current Round015 source drift: {relative}")

    saved = {}
    for mode, relative in (("smoke", "rounds/round_015/logs/smoke_01/receipt.json"),
                           ("mock", "rounds/round_015/logs/mock_01/receipt.json"),
                           ("synthetic", "rounds/round_015/logs/synthetic_01/receipt.json")):
        value, _ = strict_json(root, relative, 64 * 1024)
        saved[mode] = obj(value, f"round015.{mode}_receipt")
        check_saved_source_map(root, saved[mode], fixed_map_sha, mode)

    require_completed_receipt(saved["smoke"], "smoke")
    children = arr(saved["smoke"].get("children"), "round015.smoke_receipt.children", 2)
    for index, expected in enumerate((0, 7)):
        child = obj(children[index], f"round015.smoke_receipt.children[{index}]")
        if req(child, "expected_exit_code", int, f"smoke child {index}") != expected or req(child, "exit_code", int, f"smoke child {index}") != expected:
            fail("historical smoke child exit mismatch")
        true(child, "completed", f"smoke child {index}")
        true(child, "stdout_stderr_drained", f"smoke child {index}")
        true(child, "owned_tree_clear", f"smoke child {index}")
    require_completed_receipt(saved["mock"], "mock")

    synthetic = saved["synthetic"]
    where = "round015.synthetic_receipt"
    if req(synthetic, "schema", str, where) != "round015_process_receipt.v1" or req(synthetic, "mode", str, where) != "synthetic":
        fail("historical synthetic receipt schema/mode mismatch")
    false(synthetic, "completed", where)
    process = obj(synthetic.get("process"), f"{where}.process")
    if req(process, "exit_code", int, f"{where}.process") != 0:
        fail("historical child exit was not zero")
    true(process, "exit_confirmed", f"{where}.process")
    true(process, "owned_process_exited", f"{where}.process")
    true(process, "owned_tree_clear", f"{where}.process")
    true(process, "stdout_stderr_drained", f"{where}.process")
    true(process, "timed_out", f"{where}.process")
    false(process, "memory_stop", f"{where}.process")
    false(process, "kill_attempted", f"{where}.process")
    if req(process, "wait_finished", bool, f"{where}.process") is not False:
        fail("historical wait_finished expected false")
    elapsed = finite_number(process.get("elapsed_seconds"), f"{where}.process.elapsed_seconds")
    timeout = finite_number(process.get("wait_timeout_seconds"), f"{where}.process.wait_timeout_seconds")
    if elapsed >= timeout:
        fail("saved Round015 evidence does not establish pre-deadline wait inconsistency")
    if not isinstance(process.get("stdout"), str) or '"status": "completed"' not in process["stdout"]:
        fail("historical child stdout lacks completed marker")
    result_value, _ = strict_json(root, "rounds/round_015/artifacts/m4_synthetic_result.json", 128 * 1024)
    result_obj = obj(result_value, "round015.saved_result")
    if req(result_obj, "status", str, "round015.saved_result") != "completed":
        fail("saved historical M4 result status is not completed")

    summary_value, _ = strict_json(root, "rounds/round_010/manager/summary_stdout.json", 128 * 1024)
    round010 = obj(summary_value, "round010.manager_summary")
    false(round010, "all_execution_gates_passed", "round010.manager_summary")
    gates = obj(round010.get("gates"), "round010.manager_summary.gates")
    false(gates, "wrapper_completed", "round010.manager_summary.gates")
    false(gates, "sources_unchanged", "round010.manager_summary.gates")
    return {
        "saved_provenance_audit_pass": True,
        "current_round015_source_matches": True,
        "historical_round015_wrapper_gate": False,
        "historical_round010_gate": False,
        "round015_historical_receipt_facts": {
            "smoke_completed": True, "mock_completed": True,
            "synthetic_child_exit_code": 0, "synthetic_child_result_status": "completed",
            "synthetic_wrapper_completed": False, "synthetic_wrapper_timed_out": True,
            "synthetic_elapsed_seconds": elapsed, "configured_wait_timeout_seconds": timeout,
            "deadline_status": "not recorded; saved elapsed is below configured wait timeout",
            "elapsed_less_than_configured_timeout": True,
        },
    }


def audit_saved(root: Path, attest: dict[str, object]) -> dict[str, object]:
    metadata: dict[str, dict[str, object]] = {}
    provenance = validate_historical_receipts(root, metadata)
    result_value, result_metadata = strict_json(root, "rounds/round_015/artifacts/m4_synthetic_result.json", 128 * 1024)
    result = obj(result_value, "round015.saved_result")
    metadata["rounds/round_015/artifacts/m4_synthetic_result.json"] = result_metadata
    numeric = numeric_saved_checks(result)
    claims = obj(result.get("claims"), "round015.saved_result.claims")
    summary: dict[str, object] = {
        "schema": "round018_saved_m4_audit.v1",
        "generated_utc": utc_now(),
        **provenance,
        **numeric,
        "round018_execution_model": "MODEL-ZERO",
        "model_execution_this_round": False,
        "torch_numpy_tabicl_imported": False,
        "checkpoint_read_hashed_or_loaded": False,
        "pt_deserialization": False,
        "head_artifacts_opaque_byte_hash_only": True,
        "f1_computed_this_round": False,
        "f1_from_saved_result": claims["f1_computed"],
        "project_data_opened_this_round": False,
        "real_hardware_tested": claims["real_hardware_tested"],
        "actual_saved_inputs": metadata,
        "provenance": attest,
        "claims": {
            "full_modified_model_save_reload_tested": claims["full_modified_model_save_reload_tested"],
            "performance_selected": claims["performance_selected"],
            "project_data_opened": claims["project_data_opened"],
        },
    }
    assert_case_safe_keys(summary)
    return summary


def execute(root: Path, mode: str) -> int:
    run_dir, approved, attest = prepare_run(root, mode)
    map_sha = attest["approved_map"]["sha256"]
    receipt: dict[str, object] = {
        "schema": "round018_execution_receipt.v1",
        "mode": mode,
        "run_id": RUN_IDS[mode],
        "started_utc": utc_now(),
        "completed": False,
        "approved_map_sha256": map_sha,
        "candidate_manifest_sha256": attest["candidate_manifest"]["sha256"],
        "author_freeze_ack_sha256": attest["author_freeze_ack"]["sha256"],
        "source_hashes": attest["source_hashes"],
        "snapshots": attest["snapshots"],
        "model_execution": False,
        "checkpoint_access": False,
        "project_data_opened": False,
        "error": None,
    }
    try:
        if mode == "smoke":
            gate = process_smoke(root)
        elif mode == "mock":
            smoke_value, _ = strict_json(root, "rounds/round_018/logs/smoke_01/receipt.json", 64 * 1024)
            smoke = obj(smoke_value, "round016.smoke_receipt")
            if smoke.get("completed") is not True or smoke.get("approved_map_sha256") != map_sha:
                fail("same-map successful smoke required before mock")
            gate = mock_contract(root, map_sha)
        else:
            for prerequisite in ("smoke", "mock"):
                prerequisite_value, _ = strict_json(root, f"rounds/round_018/logs/{RUN_IDS[prerequisite]}/receipt.json", 64 * 1024)
                prerequisite_receipt = obj(prerequisite_value, f"round016.{prerequisite}_receipt")
                if prerequisite_receipt.get("completed") is not True or prerequisite_receipt.get("approved_map_sha256") != map_sha:
                    fail(f"same-map successful {prerequisite} required before saved audit")
            gate = audit_saved(root, attest)
            output = root / "rounds" / "round_018" / "artifacts" / "saved_m4_audit.json"
            write_json_new(output, gate)
            receipt["audit_output"] = str(output)
            receipt["audit_output_sha256"] = sha256_file(output, 256 * 1024)[1]
        approved_after, attest_after = load_map(root)
        if approved_after != approved or attest_after["approved_map"]["sha256"] != map_sha or attest_after["source_hashes"] != attest["source_hashes"]:
            fail("post-run approval-map/source hash check changed")
        for snapshot in attest["snapshots"]:
            snapshot_path = contained(root, snapshot["snapshot_path"])
            if sha256_file(snapshot_path, 2 * 1024 * 1024)[1] != snapshot["expected_sha256"]:
                fail(f"post-run source snapshot changed: {snapshot['path']}")
        receipt["approved_map_sha256_after"] = attest_after["approved_map"]["sha256"]
        receipt["source_hashes_after"] = attest_after["source_hashes"]
        receipt["snapshot_postcheck"] = attest["snapshots"]
        receipt["result"] = gate
        receipt["completed"] = True
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["completed"] = False
    receipt["finished_utc"] = utc_now()
    write_json_new(run_dir / "receipt.json", receipt)
    out = {"mode": mode, "run_id": RUN_IDS[mode], "completed": receipt["completed"],
           "receipt": str(run_dir / "receipt.json"), "approved_map_sha256": map_sha,
           "error": receipt["error"]}
    print(json.dumps(out, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0 if receipt["completed"] else 4


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=tuple(RUN_IDS), required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=True)
    if not root.is_dir():
        fail("root must be a directory")
    return execute(root, args.mode)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(json.dumps({"completed": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(4)
