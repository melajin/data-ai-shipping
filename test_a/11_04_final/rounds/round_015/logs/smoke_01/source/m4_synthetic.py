"""Bounded synthetic-only M4 readout mechanics for round015.

Top-level definitions use only the Python standard library so test_m4_mock.py
can validate shared guards under `python -B -S`. NumPy, PyTorch, and TabICL are
imported only by execute_synthetic after explicit runtime-path checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


ROUND = "round_015"
SEED = 20261112
TARGET_SEED = 20261113
TRAIN_SIZE = 16
TEST_SIZE = 4
FEATURES = 8
N_CLASSES = 4
HIDDEN = 1024
HEAD_OUTPUTS = 10
TEMPERATURE = 0.9
CHECKPOINT_RELATIVE = "model_cache/tabicl-classifier-v2-20260212.ckpt"
CHECKPOINT_BYTES = 110368038
CHECKPOINT_SHA256 = "bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0"
SITE_PACKAGES_RELATIVE = "environments/round_004_tabicl_cpu/Lib/site-packages"
RUNTIME_SOURCE_SHA256 = {
    "environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/learning.py":
        "7549dff09c3796a3cb0b55ea03e249342392fa601a681526f7b1efb6a6f1eef2",
    "environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/tabicl.py":
        "583786e5ffd70b9eb425bca8e52aed415dadcdf4254c908b3b6fa52026a56491",
    "environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/inference.py":
        "f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc",
    "environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_sklearn/classifier.py":
        "64f5ef7ef88a920a3f7a5f6e2d9d8dc08769ec343e931f910acc2d9c4eaa5534",
    "environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_sklearn/preprocessing.py":
        "2163a3bf6754127365a7aedac854d99a6f565545cc1ea7e63c68a596081b2976",
}
CALL_LIMITS = {
    "checkpoint_load": 1,
    "context_fit": 1,
    "predict_proba": 1,
    "full_forward": 4,
    "head_evaluation": 12,
    "backward": 4,
}
REQUIRED_CALLS = {
    "checkpoint_load": 1,
    "context_fit": 1,
    "predict_proba": 1,
    "full_forward": 4,
    "backward": 4,
}


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class CallBudget:
    """Small stdlib-only call ledger shared by the mock and actual runner."""

    def __init__(self, limits: dict[str, int] | None = None) -> None:
        self.limits = dict(CALL_LIMITS if limits is None else limits)
        self.counts = {name: 0 for name in self.limits}

    def record(self, name: str, amount: int = 1) -> int:
        if name not in self.limits:
            raise ValueError(f"Unknown bounded call category: {name}")
        if not isinstance(amount, int) or amount < 0:
            raise ValueError("Call-budget increments must be nonnegative integers")
        next_value = self.counts[name] + amount
        if next_value > self.limits[name]:
            raise RuntimeError(f"Call ceiling exceeded for {name}: {next_value}>{self.limits[name]}")
        self.counts[name] = next_value
        return next_value

    def verify_required(self, required: dict[str, int] | None = None) -> None:
        for name, expected in (REQUIRED_CALLS if required is None else required).items():
            actual = self.counts.get(name)
            if actual != expected:
                raise RuntimeError(f"Unexpected {name} count: got {actual}, expected {expected}")
        for name, actual in self.counts.items():
            if actual > self.limits[name]:
                raise RuntimeError(f"Call ceiling violated for {name}")


def validate_permutation(permutation: Sequence[int], n_classes: int = N_CLASSES) -> list[int]:
    values = [int(value) for value in permutation]
    if len(values) != n_classes or sorted(values) != list(range(n_classes)):
        raise ValueError(f"Expected a class permutation of 0..{n_classes - 1}: {values}")
    return values


def member_target_labels(target_labels: Sequence[int], permutation: Sequence[int]) -> list[int]:
    """Encode canonical labels for one ensemble member with the source p[y] rule."""
    p = validate_permutation(permutation)
    labels = [int(value) for value in target_labels]
    if any(value < 0 or value >= N_CLASSES for value in labels):
        raise ValueError("Target labels must be canonical class indices 0..3")
    return [p[value] for value in labels]


def _list_gather_last(values: Any, permutation: Sequence[int]) -> Any:
    if not isinstance(values, (list, tuple)):
        raise TypeError("The stdlib mock expects nested list/tuple logits")
    if values and isinstance(values[0], (list, tuple)):
        return [_list_gather_last(value, permutation) for value in values]
    if len(values) != len(permutation):
        raise ValueError("The final logits dimension does not match the class permutation")
    return [values[index] for index in permutation]


def canonicalize_member_logits(logits: Any, permutation: Sequence[int], torch_module: Any = None) -> Any:
    """Restore canonical order by gathering `out[..., p]`, never argsort(p)."""
    p = validate_permutation(permutation)
    if torch_module is not None:
        indices = torch_module.tensor(p, dtype=torch_module.long, device=logits.device)
        return logits.index_select(-1, indices)
    return _list_gather_last(logits, p)


def capture_target_only(hidden: Any, raw_logits: Any, train_size: int,
                        expected_total_rows: int, torch_module: Any = None) -> tuple[Any, Any]:
    """Validate full decoder hook shape, then retain only target rows."""
    if train_size < 0 or expected_total_rows <= train_size:
        raise ValueError("Invalid support/target row boundary")
    if torch_module is not None:
        if hidden.ndim != 3 or raw_logits.ndim != 3:
            raise ValueError("Decoder hooks must see rank-three batched tensors")
        if hidden.shape[1] != expected_total_rows or raw_logits.shape[1] != expected_total_rows:
            raise ValueError("Decoder hook row count differs from context plus target")
        if hidden.shape[0] != raw_logits.shape[0]:
            raise ValueError("Decoder hook batch dimensions differ")
        with torch_module.inference_mode(False), torch_module.no_grad():
            target_hidden = hidden[:, train_size:, :].detach().clone()
            target_logits = raw_logits[:, train_size:, :].detach().clone()
        if torch_module.is_inference(target_hidden) or torch_module.is_inference(target_logits):
            raise RuntimeError("Captured target tensors must be normal tensors outside inference mode")
        return target_hidden, target_logits

    if not isinstance(hidden, (list, tuple)) or not isinstance(raw_logits, (list, tuple)):
        raise TypeError("The stdlib mock expects nested list/tuple hook tensors")
    if len(hidden) != len(raw_logits):
        raise ValueError("Decoder hook batch dimensions differ")
    target_hidden = []
    target_logits = []
    for hidden_rows, logit_rows in zip(hidden, raw_logits):
        if len(hidden_rows) != expected_total_rows or len(logit_rows) != expected_total_rows:
            raise ValueError("Decoder hook row count differs from context plus target")
        target_hidden.append([list(row) for row in hidden_rows[train_size:]])
        target_logits.append([list(row) for row in logit_rows[train_size:]])
    return target_hidden, target_logits


class MergeGuard:
    """Permit one in-place-semantics merge operation for a candidate head."""

    def __init__(self) -> None:
        self.merged = False

    def merge_once(self, base_weight: Any, delta: Any) -> Any:
        if self.merged:
            raise RuntimeError("Low-rank head merge was already applied")
        self.merged = True
        return base_weight + delta


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_progress(path: Path, stage: str, **details: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at_utc": _utc_now(), "stage": stage, **details}
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _prepare_runtime_paths(root: Path) -> tuple[Path, list[Any]]:
    site_packages = root / SITE_PACKAGES_RELATIVE
    torch_lib = site_packages / "torch" / "lib"
    ensure(site_packages.is_dir(), f"Existing site-packages path is missing: {site_packages}")
    ensure(torch_lib.is_dir(), f"Torch DLL directory is missing: {torch_lib}")
    ensure((site_packages / "tabicl").is_dir(), "Pinned TabICL package directory is missing")
    ensure((site_packages / "numpy").is_dir(), "Pinned NumPy package directory is missing")

    checkpoint_path = root / CHECKPOINT_RELATIVE
    ensure(checkpoint_path.is_file(), f"Pinned local checkpoint is missing: {checkpoint_path}")
    ensure(checkpoint_path.name == "tabicl-classifier-v2-20260212.ckpt", "Unexpected checkpoint basename")
    ensure(checkpoint_path.stat().st_size == CHECKPOINT_BYTES, "Pinned checkpoint byte count differs")
    checkpoint_sha = _sha256_file(checkpoint_path)
    ensure(checkpoint_sha == CHECKPOINT_SHA256, "Pinned checkpoint SHA-256 differs")

    for relative, expected_sha in RUNTIME_SOURCE_SHA256.items():
        source_path = root / relative
        ensure(source_path.is_file(), f"Pinned runtime source is missing: {relative}")
        actual_sha = _sha256_file(source_path)
        ensure(actual_sha == expected_sha, f"Pinned runtime source SHA-256 differs: {relative}")

    handles: list[Any] = []
    dll_directories = [torch_lib]
    dll_directories.extend(path for path in site_packages.glob("*.libs") if path.is_dir())
    for directory in dll_directories:
        handles.append(os.add_dll_directory(str(directory)))
    sys.path.insert(0, str(site_packages))
    os.environ["TABICL_PATH"] = str(checkpoint_path)
    os.environ["TABICL_CHECKPOINT"] = checkpoint_path.name
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return checkpoint_path, handles


def _hash_tensor(tensor: Any, torch_module: Any) -> str:
    raw = tensor.detach().cpu().contiguous().reshape(-1).view(torch_module.uint8).numpy()
    view = memoryview(raw).cast("B")
    digest = hashlib.sha256()
    step = 1024 * 1024
    for start in range(0, len(view), step):
        digest.update(view[start:start + step])
    return digest.hexdigest()


def _module_hook_keys(model: Any) -> dict[str, dict[str, list[int]]]:
    result = {}
    for name, module in model.named_modules():
        result[name] = {
            "forward_pre": sorted(int(key) for key in module._forward_pre_hooks.keys()),
            "forward": sorted(int(key) for key in module._forward_hooks.keys()),
        }
    return result


def _source_signature(model: Any, torch_module: Any) -> dict[str, Any]:
    parameter_hash = hashlib.sha256()
    buffer_hash = hashlib.sha256()
    grad_hash = hashlib.sha256()
    params = list(model.named_parameters())
    buffers = list(model.named_buffers())
    for name, tensor in params:
        description = f"{name}|{tuple(tensor.shape)}|{tensor.dtype}|{tensor.requires_grad}|".encode("utf-8")
        parameter_hash.update(description)
        parameter_hash.update(_hash_tensor(tensor, torch_module).encode("ascii"))
        if tensor.grad is None:
            grad_hash.update(f"{name}|none|".encode("utf-8"))
        else:
            grad_hash.update(f"{name}|{tuple(tensor.grad.shape)}|{tensor.grad.dtype}|".encode("utf-8"))
            grad_hash.update(_hash_tensor(tensor.grad, torch_module).encode("ascii"))
    for name, tensor in buffers:
        buffer_hash.update(f"{name}|{tuple(tensor.shape)}|{tensor.dtype}|".encode("utf-8"))
        buffer_hash.update(_hash_tensor(tensor, torch_module).encode("ascii"))
    module_modes = {name: bool(module.training) for name, module in model.named_modules()}
    flags = {name: bool(parameter.requires_grad) for name, parameter in params}
    return {
        "parameter_count": len(params),
        "parameter_numel": int(sum(parameter.numel() for _, parameter in params)),
        "buffer_count": len(buffers),
        "parameter_sha256": parameter_hash.hexdigest(),
        "buffer_sha256": buffer_hash.hexdigest(),
        "gradient_state_sha256": grad_hash.hexdigest(),
        "requires_grad": flags,
        "module_training": module_modes,
        "hook_keys": _module_hook_keys(model),
    }


def _finite_nonzero(tensor: Any, torch_module: Any) -> bool:
    return bool(torch_module.isfinite(tensor).all().item() and torch_module.count_nonzero(tensor).item() > 0)


def _exact_zero(tensor: Any, torch_module: Any) -> bool:
    return bool(torch_module.count_nonzero(tensor).item() == 0)


def _allclose_finite(left: Any, right: Any, torch_module: Any) -> tuple[float, bool]:
    ensure(bool(torch_module.isfinite(left).all().item()), "Left tensor contains nonfinite values")
    ensure(bool(torch_module.isfinite(right).all().item()), "Right tensor contains nonfinite values")
    maximum = float((left - right).abs().max().item()) if left.numel() else 0.0
    return maximum, bool(torch_module.equal(left, right))


def _probability_summary(values: Any, torch_module: Any) -> dict[str, Any]:
    ensure(bool(torch_module.isfinite(values).all().item()), "Probability tensor contains nonfinite values")
    ensure(bool(((values >= 0.0) & (values <= 1.0)).all().item()), "Probability lies outside [0,1]")
    sums = values.sum(dim=1)
    row_sum_error = float((sums - 1.0).abs().max().item())
    return {
        "shape": list(values.shape),
        "finite": True,
        "range_0_1": True,
        "max_abs_row_sum_error": row_sum_error,
        "row_sum_within_1e_6": row_sum_error <= 1e-6,
        "values": values.detach().cpu().tolist(),
    }


def _comparison(name: str, baseline_logits: Any, candidate_logits: Any,
                baseline_probabilities: Any, candidate_probabilities: Any,
                torch_module: Any) -> dict[str, Any]:
    logit_difference, logits_exact = _allclose_finite(baseline_logits, candidate_logits, torch_module)
    probability_difference, probabilities_exact = _allclose_finite(
        baseline_probabilities, candidate_probabilities, torch_module
    )
    baseline_probability_check = _probability_summary(baseline_probabilities, torch_module)
    candidate_probability_check = _probability_summary(candidate_probabilities, torch_module)
    baseline_argmax = baseline_probabilities.argmax(dim=1)
    candidate_argmax = candidate_probabilities.argmax(dim=1)
    argmax_equal = bool(torch_module.equal(baseline_argmax, candidate_argmax))
    return {
        "name": name,
        "max_abs_logit_difference": logit_difference,
        "logit_exact_equal": logits_exact,
        "max_abs_probability_difference": probability_difference,
        "probability_exact_equal": probabilities_exact,
        "baseline_probability_checks": {
            "finite": baseline_probability_check["finite"],
            "range_0_1": baseline_probability_check["range_0_1"],
            "max_abs_row_sum_error": baseline_probability_check["max_abs_row_sum_error"],
        },
        "candidate_probability_checks": {
            "finite": candidate_probability_check["finite"],
            "range_0_1": candidate_probability_check["range_0_1"],
            "max_abs_row_sum_error": candidate_probability_check["max_abs_row_sum_error"],
        },
        "argmax_equal": argmax_equal,
        "all_checks_pass": bool(
            logit_difference <= 1e-5 and probability_difference <= 1e-6 and argmax_equal
            and baseline_probability_check["finite"] and candidate_probability_check["finite"]
            and baseline_probability_check["range_0_1"] and candidate_probability_check["range_0_1"]
            and baseline_probability_check["max_abs_row_sum_error"] <= 1e-6
            and candidate_probability_check["max_abs_row_sum_error"] <= 1e-6
        ),
    }


def _softmax_probabilities(logits: Any, temperature: float, torch_module: Any) -> Any:
    probabilities = torch_module.softmax(logits / temperature, dim=-1)
    denominator = probabilities.sum(dim=-1, keepdim=True)
    ensure(bool(torch_module.isfinite(probabilities).all().item()), "Softmax produced nonfinite values")
    ensure(bool((denominator > 0).all().item()), "Softmax probability row has a nonpositive sum")
    # Match classifier.predict_proba, which divides the averaged softmax rows by
    # their row sums after member aggregation.
    return probabilities / denominator


def _mean_canonical_logits(member_logits: Any, permutations: list[list[int]], torch_module: Any) -> Any:
    ensure(member_logits.shape[0] == len(permutations), "Member logits and permutation counts differ")
    restored = [canonicalize_member_logits(member_logits[index], p, torch_module) for index, p in enumerate(permutations)]
    return torch_module.stack(restored, dim=0).mean(dim=0)


def _head_logits(head_output: Any, hidden: Any, torch_module: Any, budget: CallBudget) -> Any:
    budget.record("head_evaluation")
    return head_output(hidden)


def _head_loss(logits: Any, target_labels: list[int], permutations: list[list[int]], torch_module: Any,
               functional: Any) -> Any:
    targets = [torch_module.tensor(member_target_labels(target_labels, p), dtype=torch_module.long)
               for p in permutations]
    per_view = [functional.cross_entropy(logits[index, :, :N_CLASSES], targets[index])
                for index in range(len(permutations))]
    return torch_module.stack(per_view).mean()


def _torch_state_dict(module: Any) -> dict[str, Any]:
    return {name: tensor.detach().cpu().clone() for name, tensor in module.state_dict().items()}


def _write_torch_state(torch_module: Any, path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch_module.save(state, str(temporary))
    temporary.replace(path)


def execute_synthetic(root: Path, result_path: Path, progress_path: Path, temp_path: Path) -> dict[str, Any]:
    root = root.resolve()
    result_path = result_path.resolve()
    progress_path = progress_path.resolve()
    temp_path = temp_path.resolve()
    round_root = root / "rounds" / ROUND
    ensure(result_path.is_relative_to(round_root), "Result path must remain inside round015")
    ensure(progress_path.is_relative_to(round_root), "Progress path must remain inside round015")
    ensure(temp_path.is_relative_to(round_root), "Temporary path must remain inside round015")
    ensure(not result_path.exists(), f"Refusing to overwrite a prior result: {result_path}")
    ensure(not (round_root / "artifacts" / "m4_a_head.pt").exists(), "M4-a artifact already exists; retry forbidden")
    ensure(not (round_root / "artifacts" / "m4_b_merged_head.pt").exists(), "M4-b artifact already exists; retry forbidden")

    ensure(sys.version_info[:2] == (3, 12), f"Expected Python 3.12, got {sys.version_info[:3]}")
    ensure(os.environ.get("OMP_NUM_THREADS") == "3" and os.environ.get("MKL_NUM_THREADS") == "3",
           "Runner must set OMP_NUM_THREADS and MKL_NUM_THREADS to 3")
    checkpoint_path, dll_handles = _prepare_runtime_paths(root)
    _append_progress(progress_path, "runtime_sources_and_checkpoint_verified",
                     checkpoint_bytes=CHECKPOINT_BYTES, checkpoint_sha256=CHECKPOINT_SHA256,
                     runtime_source_sha256=RUNTIME_SOURCE_SHA256,
                     dll_directories=[getattr(handle, "_name", "registered") for handle in dll_handles])

    # These imports are intentionally delayed until after path, DLL, and source checks.
    import numpy as np
    import torch
    import torch.nn.functional as F
    from importlib.metadata import version
    from tabicl import TabICLClassifier

    ensure(version("tabicl") == "2.2.0", f"Unexpected TabICL version: {version('tabicl')}")
    ensure(torch.__version__ == "2.6.0+cpu", f"Unexpected PyTorch build: {torch.__version__}")
    ensure(np.__version__ == "2.3.5", f"Unexpected NumPy version: {np.__version__}")
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    ensure(torch.get_num_threads() == 3 and torch.get_num_interop_threads() == 1,
           "Unexpected PyTorch CPU thread settings")

    budget = CallBudget()
    rng = np.random.default_rng(SEED)
    context_x = rng.standard_normal((TRAIN_SIZE, FEATURES), dtype=np.float32)
    target_x = rng.standard_normal((TEST_SIZE, FEATURES), dtype=np.float32)
    context_y = np.tile(np.arange(N_CLASSES, dtype=np.int64), TRAIN_SIZE // N_CLASSES)
    ensure(context_x.dtype == np.float32 and target_x.dtype == np.float32, "Synthetic inputs must be FP32")
    ensure(context_x.shape == (16, 8) and target_x.shape == (4, 8), "Unexpected synthetic input shape")
    ensure(context_y.tolist() == [0, 1, 2, 3] * 4, "Unexpected context labels")
    ensure(np.isfinite(context_x).all() and np.isfinite(target_x).all(), "Synthetic inputs must be finite")

    estimator = TabICLClassifier(
        n_estimators=4,
        norm_methods=["none"],
        feat_shuffle_method="none",
        class_shuffle_method="shift",
        softmax_temperature=TEMPERATURE,
        average_logits=True,
        batch_size=1,
        kv_cache=False,
        model_path=str(checkpoint_path),
        allow_auto_download=False,
        checkpoint_version="tabicl-classifier-v2-20260212.ckpt",
        device="cpu",
        use_amp=False,
        use_fa3=False,
        random_state=SEED,
        n_jobs=3,
        verbose=False,
    )

    original_load_model = estimator._load_model
    def counted_load_model() -> Any:
        budget.record("checkpoint_load")
        return original_load_model()
    estimator._load_model = counted_load_model
    budget.record("context_fit")
    fit_return = estimator.fit(context_x, context_y)
    ensure(fit_return is estimator, "Context fit did not return the fitted estimator")
    ensure(budget.counts["checkpoint_load"] == 1, "Checkpoint must be loaded exactly once")
    ensure(budget.counts["context_fit"] == 1, "Context fit must occur exactly once")
    ensure(not estimator.kv_cache, "KV cache must remain disabled")

    model = estimator.model_
    model.eval()
    for parameter in model.parameters():
        ensure(parameter.grad is None, "Unexpected upstream gradient before freezing")
        parameter.requires_grad_(False)
    pre_signature = _source_signature(model, torch)
    ensure(not any(pre_signature["requires_grad"].values()), "Upstream model was not frozen after setup")
    ensure(not any(pre_signature["module_training"].values()), "Upstream model was not in eval mode after setup")

    decoder = model.icl_predictor.decoder
    ensure(len(decoder) > 2, "ICL decoder has no final Linear at index 2")
    final_linear = decoder[2]
    ensure(isinstance(final_linear, torch.nn.Linear), "decoder[2] is not a Linear layer")
    ensure(tuple(final_linear.weight.shape) == (HEAD_OUTPUTS, HIDDEN), "decoder[2] weight shape mismatch")
    ensure(final_linear.bias is not None and tuple(final_linear.bias.shape) == (HEAD_OUTPUTS,),
           "decoder[2] bias shape mismatch")
    ensure(final_linear.weight.dtype == torch.float32 and final_linear.bias.dtype == torch.float32,
           "Readout weights must be FP32")

    captured_hidden: list[Any] = []
    captured_logits: list[Any] = []
    expected_rows = TRAIN_SIZE + TEST_SIZE

    def capture_final_readout(module: Any, inputs: tuple[Any, ...], output: Any) -> None:
        budget.record("full_forward")
        ensure(len(inputs) == 1, "Unexpected final Linear input signature")
        hidden = inputs[0]
        ensure(tuple(hidden.shape) == (1, expected_rows, HIDDEN),
               f"Expected one member with context+target hidden rows, got {tuple(hidden.shape)}")
        ensure(tuple(output.shape) == (1, expected_rows, HEAD_OUTPUTS),
               f"Expected one member with 10 readout outputs, got {tuple(output.shape)}")
        target_hidden, target_logits = capture_target_only(
            hidden, output, TRAIN_SIZE, expected_rows, torch_module=torch
        )
        ensure(tuple(target_hidden.shape) == (1, TEST_SIZE, HIDDEN), "Target hidden cache shape mismatch")
        ensure(tuple(target_logits.shape) == (1, TEST_SIZE, HEAD_OUTPUTS), "Target logit cache shape mismatch")
        captured_hidden.append(target_hidden[0])
        captured_logits.append(target_logits[0])

    preexisting_hook_keys = _module_hook_keys(model)
    handle = final_linear.register_forward_hook(capture_final_readout)
    native_probabilities_np = None
    try:
        budget.record("predict_proba")
        # Target labels do not exist until after inference has returned.
        native_probabilities_np = estimator.predict_proba(target_x)
    finally:
        handle.remove()
    ensure(_module_hook_keys(model) == preexisting_hook_keys, "Temporary readout hook was not fully removed")
    ensure(native_probabilities_np is not None, "predict_proba produced no result")
    ensure(len(captured_hidden) == 4 and len(captured_logits) == 4,
           f"Expected four ensemble readout captures, got {len(captured_hidden)}")
    ensure(budget.counts["full_forward"] == 4, "Expected exactly four native full forwards")
    hidden_cache = torch.stack(captured_hidden, dim=0).detach().clone()
    hook_logits = torch.stack(captured_logits, dim=0).detach().clone()
    ensure(not torch.is_inference(hidden_cache) and not torch.is_inference(hook_logits),
           "Readout cache must be detached normal tensors outside inference mode")
    ensure(tuple(hidden_cache.shape) == (4, 4, HIDDEN), "Final hidden cache must be target-only [4,4,1024]")
    ensure(tuple(hook_logits.shape) == (4, 4, HEAD_OUTPUTS), "Final logits cache must be target-only [4,4,10]")
    ensure(not hidden_cache.requires_grad and not hook_logits.requires_grad, "Readout cache must be detached")

    class_shuffles = estimator.ensemble_generator_.class_shuffles_
    norm_keys = list(class_shuffles.keys())
    ensure(norm_keys == ["none"], f"Expected exactly one normalization view, got {norm_keys}")
    raw_permutations = list(class_shuffles["none"])
    permutations = [validate_permutation(pattern.tolist() if hasattr(pattern, "tolist") else pattern)
                    for pattern in raw_permutations]
    ensure(len(permutations) == 4, "Expected exactly four recorded class-shuffle permutations")

    # This boundary is deliberate: target labels are created only after the sole
    # predict_proba call and are used by external readout losses, never by TabICL.
    target_y = np.arange(N_CLASSES, dtype=np.int64)
    ensure(target_y.tolist() == [0, 1, 2, 3], "Unexpected synthetic target labels")
    ensure(budget.counts["predict_proba"] == 1, "predict_proba must occur exactly once")

    W0 = final_linear.weight.detach().clone()
    b0 = final_linear.bias.detach().clone()
    original_member_logits = _head_logits(lambda value: F.linear(value, W0, b0), hidden_cache, torch, budget)
    base_head_difference, base_head_exact = _allclose_finite(original_member_logits, hook_logits, torch)
    ensure(base_head_difference <= 1e-5, "Copied original head does not reproduce captured member logits")

    baseline_member_logits = original_member_logits[:, :, :N_CLASSES]
    baseline_logits = _mean_canonical_logits(baseline_member_logits, permutations, torch)
    baseline_probabilities = _softmax_probabilities(baseline_logits, TEMPERATURE, torch)
    native_probabilities = torch.as_tensor(native_probabilities_np, dtype=torch.float32)
    ensure(tuple(native_probabilities.shape) == (TEST_SIZE, N_CLASSES), "Unexpected public probability shape")
    native_probability_difference, native_probability_exact = _allclose_finite(
        baseline_probabilities, native_probabilities, torch
    )
    ensure(native_probability_difference <= 1e-6, "Canonical hook probability reconstruction differs from public output")
    ensure(bool(torch.equal(baseline_probabilities.argmax(dim=1), native_probabilities.argmax(dim=1))),
           "Canonical hook reconstruction changed public argmax")

    target_labels_list = [int(value) for value in target_y.tolist()]
    # M4-a: train only a copied W; the original bias is a fixed tensor.
    Wa = torch.nn.Parameter(W0.detach().clone())
    fixed_bias_a = b0.detach().clone()
    a_optimizer = torch.optim.SGD([Wa], lr=0.001, momentum=0.0, weight_decay=0.0)
    a_initial_logits = _head_logits(lambda value: F.linear(value, Wa, fixed_bias_a), hidden_cache, torch, budget)
    a_initial_loss = float(_head_loss(a_initial_logits, target_labels_list, permutations, torch, F).detach().item())
    a_initial_canonical = _mean_canonical_logits(a_initial_logits[:, :, :N_CLASSES], permutations, torch)
    a_initial_probabilities = _softmax_probabilities(a_initial_canonical, TEMPERATURE, torch)

    # M4-b: W0/b0 fixed, rank-two A initialized normal(0,0.01), B initialized 0.
    generator = torch.Generator(device="cpu").manual_seed(TARGET_SEED)
    A = torch.nn.Parameter(torch.randn((2, HIDDEN), generator=generator, dtype=torch.float32) * 0.01)
    B = torch.nn.Parameter(torch.zeros((HEAD_OUTPUTS, 2), dtype=torch.float32))
    fixed_bias_b = b0.detach().clone()
    inactive_B_before = B.detach()[N_CLASSES:].clone()
    inactive_W0_before = W0.detach()[N_CLASSES:].clone()
    b_optimizer = torch.optim.SGD([A, B], lr=0.001, momentum=0.0, weight_decay=0.0)
    b_initial_logits = _head_logits(
        lambda value: F.linear(value, W0 + B @ A, fixed_bias_b), hidden_cache, torch, budget
    )
    b_initial_loss = float(_head_loss(b_initial_logits, target_labels_list, permutations, torch, F).detach().item())
    b_initial_canonical = _mean_canonical_logits(b_initial_logits[:, :, :N_CLASSES], permutations, torch)
    b_initial_probabilities = _softmax_probabilities(b_initial_canonical, TEMPERATURE, torch)
    a_initial_check = _comparison("M4-a initial copy vs source", original_member_logits, a_initial_logits,
                                  baseline_probabilities, a_initial_probabilities, torch)
    b_initial_check = _comparison("M4-b B=0 initialization vs source", original_member_logits, b_initial_logits,
                                  baseline_probabilities, b_initial_probabilities, torch)
    ensure(a_initial_check["all_checks_pass"], "M4-a initial copy changed the frozen head output")
    ensure(b_initial_check["all_checks_pass"], "M4-b zero-B initialization changed the frozen head output")

    a_step_losses: list[float] = []
    a_gradient_checks: list[dict[str, Any]] = []
    for step_index in range(2):
        a_optimizer.zero_grad(set_to_none=True)
        step_logits = _head_logits(lambda value: F.linear(value, Wa, fixed_bias_a), hidden_cache, torch, budget)
        loss = _head_loss(step_logits, target_labels_list, permutations, torch, F)
        budget.record("backward")
        loss.backward()
        ensure(Wa.grad is not None and bool(torch.isfinite(Wa.grad).all().item()), "M4-a gradient is missing/nonfinite")
        ensure(_finite_nonzero(Wa.grad, torch), "M4-a gradient must be nonzero")
        ensure(_exact_zero(Wa.grad[N_CLASSES:], torch), "M4-a inactive output rows must have exact zero gradient")
        a_gradient_checks.append({
            "step": step_index + 1,
            "weight_grad_finite_nonzero": True,
            "inactive_rows_gradient_exact_zero": True,
        })
        a_step_losses.append(float(loss.detach().item()))
        a_optimizer.step()

    b_step_losses: list[float] = []
    b_gradient_checks: list[dict[str, Any]] = []
    for step_index in range(2):
        b_optimizer.zero_grad(set_to_none=True)
        step_logits = _head_logits(
            lambda value: F.linear(value, W0 + B @ A, fixed_bias_b), hidden_cache, torch, budget
        )
        loss = _head_loss(step_logits, target_labels_list, permutations, torch, F)
        budget.record("backward")
        loss.backward()
        ensure(A.grad is not None and B.grad is not None, "M4-b low-rank gradients are missing")
        ensure(bool(torch.isfinite(A.grad).all().item()) and bool(torch.isfinite(B.grad).all().item()),
               "M4-b gradients must remain finite")
        ensure(_exact_zero(B.grad[N_CLASSES:], torch), "M4-b inactive B rows must have exact zero gradient")
        if step_index == 0:
            ensure(_finite_nonzero(B.grad, torch), "M4-b first B gradient must be nonzero")
            ensure(_exact_zero(A.grad, torch), "M4-b first A gradient must be exactly zero when B=0")
            b_gradient_checks.append({
                "step": 1,
                "B_grad_finite_nonzero": True,
                "A_grad_exact_zero_at_B_zero": True,
                "inactive_B_rows_gradient_exact_zero": True,
            })
        else:
            ensure(_finite_nonzero(A.grad, torch), "M4-b second A gradient must become nonzero")
            ensure(_finite_nonzero(B.grad, torch), "M4-b second B gradient must remain nonzero")
            b_gradient_checks.append({
                "step": 2,
                "A_grad_finite_nonzero": True,
                "B_grad_finite_nonzero": True,
                "inactive_B_rows_gradient_exact_zero": True,
            })
        b_step_losses.append(float(loss.detach().item()))
        b_optimizer.step()

    ensure(torch.equal(Wa.detach()[N_CLASSES:], W0[N_CLASSES:]), "M4-a inactive six weight rows changed")
    ensure(torch.equal(fixed_bias_a, b0) and torch.equal(fixed_bias_b, b0), "Candidate bias changed")
    ensure(torch.equal(B.detach()[N_CLASSES:], inactive_B_before), "M4-b inactive six B rows changed")
    ensure(torch.equal(W0.detach()[N_CLASSES:], inactive_W0_before), "Frozen base inactive weight rows changed")

    # M4-a post-update output is captured before saving, then compared to a fresh reload.
    a_trained_logits = _head_logits(lambda value: F.linear(value, Wa, fixed_bias_a), hidden_cache, torch, budget)
    a_trained_canonical = _mean_canonical_logits(a_trained_logits[:, :, :N_CLASSES], permutations, torch)
    a_trained_probabilities = _softmax_probabilities(a_trained_canonical, TEMPERATURE, torch)
    a_state = {"weight": Wa.detach().cpu().clone(), "bias": fixed_bias_a.detach().cpu().clone()}
    a_artifact = round_root / "artifacts" / "m4_a_head.pt"
    _write_torch_state(torch, a_artifact, a_state)
    a_reloaded_state = torch.load(str(a_artifact), map_location="cpu", weights_only=True)
    a_reloaded_head = torch.nn.Linear(HIDDEN, HEAD_OUTPUTS, bias=True, dtype=torch.float32)
    a_reloaded_head.load_state_dict(a_reloaded_state, strict=True)
    a_reloaded_head.eval()
    a_reload_logits = _head_logits(lambda value: F.linear(value, a_reloaded_head.weight, a_reloaded_head.bias),
                                   hidden_cache, torch, budget)
    a_reload_canonical = _mean_canonical_logits(a_reload_logits[:, :, :N_CLASSES], permutations, torch)
    a_reload_probabilities = _softmax_probabilities(a_reload_canonical, TEMPERATURE, torch)
    a_reload_check = _comparison("M4-a trained head vs head-only reload", a_trained_logits, a_reload_logits,
                                 a_trained_probabilities, a_reload_probabilities, torch)
    a_reload_weight_exact = bool(torch.equal(a_reloaded_head.weight.detach(), Wa.detach()))
    a_reload_bias_exact = bool(torch.equal(a_reloaded_head.bias.detach(), b0))
    ensure(a_reload_weight_exact and a_reload_bias_exact, "M4-a head-only reload changed saved tensors")

    # M4-b unmerged output is evaluated once, then merged exactly once into W0.
    b_unmerged_logits = _head_logits(
        lambda value: F.linear(value, W0 + B @ A, fixed_bias_b), hidden_cache, torch, budget
    )
    b_unmerged_canonical = _mean_canonical_logits(b_unmerged_logits[:, :, :N_CLASSES], permutations, torch)
    b_unmerged_probabilities = _softmax_probabilities(b_unmerged_canonical, TEMPERATURE, torch)
    merge_guard = MergeGuard()
    with torch.no_grad():
        b_merged_weight = merge_guard.merge_once(W0.detach().clone(), (B @ A).detach().clone())
    ensure(merge_guard.merged, "M4-b merge guard did not record its merge")
    b_merged_logits = _head_logits(lambda value: F.linear(value, b_merged_weight, fixed_bias_b),
                                   hidden_cache, torch, budget)
    b_merged_canonical = _mean_canonical_logits(b_merged_logits[:, :, :N_CLASSES], permutations, torch)
    b_merged_probabilities = _softmax_probabilities(b_merged_canonical, TEMPERATURE, torch)
    b_merge_check = _comparison("M4-b unmerged vs single merged head", b_unmerged_logits, b_merged_logits,
                                b_unmerged_probabilities, b_merged_probabilities, torch)
    ensure(b_merge_check["all_checks_pass"], "M4-b merged output differs from unmerged output")
    duplicate_merge_rejected = False
    try:
        with torch.no_grad():
            merge_guard.merge_once(b_merged_weight, (B @ A).detach())
    except RuntimeError:
        duplicate_merge_rejected = True
    ensure(duplicate_merge_rejected, "M4-b duplicate merge was not rejected")

    b_artifact = round_root / "artifacts" / "m4_b_merged_head.pt"
    b_state = {"weight": b_merged_weight.detach().cpu().clone(), "bias": fixed_bias_b.detach().cpu().clone()}
    _write_torch_state(torch, b_artifact, b_state)
    b_reloaded_state = torch.load(str(b_artifact), map_location="cpu", weights_only=True)
    b_reloaded_head = torch.nn.Linear(HIDDEN, HEAD_OUTPUTS, bias=True, dtype=torch.float32)
    b_reloaded_head.load_state_dict(b_reloaded_state, strict=True)
    b_reloaded_head.eval()
    b_reload_logits = _head_logits(lambda value: F.linear(value, b_reloaded_head.weight, b_reloaded_head.bias),
                                   hidden_cache, torch, budget)
    b_reload_canonical = _mean_canonical_logits(b_reload_logits[:, :, :N_CLASSES], permutations, torch)
    b_reload_probabilities = _softmax_probabilities(b_reload_canonical, TEMPERATURE, torch)
    b_reload_check = _comparison("M4-b merged head vs head-only reload", b_merged_logits, b_reload_logits,
                                 b_merged_probabilities, b_reload_probabilities, torch)
    ensure(b_reload_check["all_checks_pass"], "M4-b merged head-only reload output differs")
    ensure(torch.equal(b_reloaded_head.bias.detach(), b0), "M4-b head-only reload changed fixed bias")
    ensure(torch.equal(b_reloaded_head.weight.detach(), b_merged_weight), "M4-b head-only reload changed merged weight")

    comparisons = [
        a_initial_check,
        b_initial_check,
        _comparison("native public probability reconstruction", original_member_logits, hook_logits,
                    baseline_probabilities, native_probabilities, torch),
        a_reload_check,
        b_merge_check,
        b_reload_check,
    ]
    ensure(all(item["all_checks_pass"] for item in comparisons), "One or more fixed-tolerance comparisons failed")
    ensure(budget.counts["head_evaluation"] <= 12, "External head evaluation ceiling exceeded")
    budget.verify_required()
    ensure(budget.counts["head_evaluation"] == 12,
           f"Expected 12 planned external head evaluations, got {budget.counts['head_evaluation']}")

    post_signature = _source_signature(model, torch)
    ensure(post_signature == pre_signature,
           "Frozen source model parameters/buffers/grads/mode/hooks changed during readout experiment")

    result = {
        "schema": "round015_m4_synthetic_result.v1",
        "status": "completed",
        "scope": "synthetic-only external-head mechanics; no project data, F1, performance selection, or hardware validation",
        "started_utc": None,
        "completed_utc": _utc_now(),
        "synthetic": {
            "seed": SEED,
            "context_shape": [TRAIN_SIZE, FEATURES],
            "target_shape": [TEST_SIZE, FEATURES],
            "dtype": "float32",
            "context_labels": context_y.tolist(),
            "target_labels": target_labels_list,
            "target_labels_created_after_predict_proba": True,
            "target_labels_passed_to_fit_or_predict_proba": False,
            "features_are_standard_normal": True,
        },
        "runtime": {
            "python": sys.version,
            "tabicl": version("tabicl"),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "device": "cpu",
            "torch_dtype": "float32",
            "torch_threads": {"intra_op": torch.get_num_threads(), "interop": torch.get_num_interop_threads()},
            "amp": False,
            "fa3": False,
            "kv_cache": False,
            "auto_download": False,
            "n_estimators": 4,
            "batch_size": 1,
            "norm_methods": ["none"],
            "feature_shuffle": "none",
            "class_shuffle": "shift",
            "temperature": TEMPERATURE,
            "average_logits": True,
            "checkpoint": {
                "path": str(checkpoint_path),
                "bytes": CHECKPOINT_BYTES,
                "sha256": CHECKPOINT_SHA256,
            },
            "runtime_source_sha256": RUNTIME_SOURCE_SHA256,
        },
        "readout_capture": {
            "module": "model_.icl_predictor.decoder[2]",
            "weight_shape": list(final_linear.weight.shape),
            "bias_shape": list(final_linear.bias.shape),
            "observed_full_hook_rows": [TRAIN_SIZE, TEST_SIZE],
            "cached_hidden_shape": list(hidden_cache.shape),
            "cached_logits_shape": list(hook_logits.shape),
            "cached_target_only": True,
            "class_shuffle_order": permutations,
            "canonical_restore": "member output[..., p]",
            "member_targets": "p[y_target]",
            "source_head_recalculation": {
                "max_abs_first4_logit_difference": base_head_difference,
                "exact_equal": base_head_exact,
                "within_1e_5": base_head_difference <= 1e-5,
            },
            "public_probability_reconstruction": {
                "max_abs_probability_difference": native_probability_difference,
                "exact_equal": native_probability_exact,
                "argmax_equal": bool(torch.equal(baseline_probabilities.argmax(dim=1),
                                                  native_probabilities.argmax(dim=1))),
                "probabilities": _probability_summary(baseline_probabilities, torch),
            },
        },
        "m4_a": {
            "trainable": "copied W only; original bias fixed",
            "optimizer": {"name": "SGD", "lr": 0.001, "momentum": 0.0, "weight_decay": 0.0, "steps": 2},
            "initial_mean_cross_entropy_diagnostic": a_initial_loss,
            "step_mean_cross_entropy_diagnostics": a_step_losses,
            "gradient_checks": a_gradient_checks,
            "inactive_six_weight_rows_exactly_unchanged": True,
            "bias_exactly_unchanged": True,
            "head_only_artifact": str(a_artifact.relative_to(root)),
            "reload_weight_exact": a_reload_weight_exact,
            "reload_bias_exact": a_reload_bias_exact,
            "reload_comparison": a_reload_check,
        },
        "m4_b": {
            "trainable": "A[2,1024], B[10,2]; W0 and bias fixed",
            "initialization": {"A": "normal(0,0.01)", "B": "zeros", "seed": TARGET_SEED},
            "optimizer": {"name": "SGD", "lr": 0.001, "momentum": 0.0, "weight_decay": 0.0, "steps": 2},
            "initial_mean_cross_entropy_diagnostic": b_initial_loss,
            "step_mean_cross_entropy_diagnostics": b_step_losses,
            "gradient_checks": b_gradient_checks,
            "inactive_six_B_rows_exactly_unchanged": True,
            "bias_exactly_unchanged": True,
            "merge_formula": "W_eff = W0 + B @ A",
            "merge_count": 1,
            "duplicate_merge_rejected": duplicate_merge_rejected,
            "head_only_artifact": str(b_artifact.relative_to(root)),
            "reload_weight_exact": bool(torch.equal(b_reloaded_head.weight.detach(), b_merged_weight)),
            "reload_bias_exact": bool(torch.equal(b_reloaded_head.bias.detach(), b0)),
            "merge_comparison": b_merge_check,
            "reload_comparison": b_reload_check,
        },
        "call_counts": {"limits": CALL_LIMITS, "observed": budget.counts},
        "comparisons": comparisons,
        "upstream_model": {
            "deliberate_setup": "model.eval(); every source parameter requires_grad=False; prior gradients required None",
            "unchanged_after_capture_and_head_training": True,
            "parameter_count": pre_signature["parameter_count"],
            "parameter_numel": pre_signature["parameter_numel"],
            "buffer_count": pre_signature["buffer_count"],
            "parameter_sha256_before_after": pre_signature["parameter_sha256"],
            "buffer_sha256_before_after": pre_signature["buffer_sha256"],
            "gradient_state_sha256_before_after": pre_signature["gradient_state_sha256"],
            "requires_grad_before_after": pre_signature["requires_grad"],
            "module_training_before_after": pre_signature["module_training"],
            "hooks_restored": True,
        },
        "claims": {
            "f1_computed": False,
            "project_data_opened": False,
            "performance_selected": False,
            "full_modified_model_save_reload_tested": False,
            "real_hardware_tested": False,
        },
    }
    return result


def _validated_cli_paths(root_value: str, result_value: str, progress_value: str,
                         temp_value: str) -> tuple[Path, Path, Path, Path]:
    root = Path(root_value).resolve()
    frozen_script = Path(__file__).resolve()
    ensure(len(frozen_script.parents) > 5, "Frozen runner snapshot path is too shallow")
    frozen_root = frozen_script.parents[5]
    ensure(root == frozen_root.resolve(), "Project root must match the frozen round015 snapshot location")
    round_root = root / "rounds" / ROUND
    result_path = Path(result_value).resolve()
    progress_path = Path(progress_value).resolve()
    temp_path = Path(temp_value).resolve()
    expected_result = round_root / "artifacts" / "m4_synthetic_result.json"
    expected_progress = round_root / "logs" / "synthetic_01" / "progress.jsonl"
    expected_temp = round_root / "temp" / "synthetic_01"
    ensure(result_path == expected_result.resolve(), "Result path must be the fixed round015 artifact path")
    ensure(progress_path == expected_progress.resolve(), "Progress path must be the fixed round015 synthetic log")
    ensure(temp_path == expected_temp.resolve(), "Temporary path must be the fixed round015 synthetic temp directory")
    ensure(root.is_dir(), f"Project root does not exist: {root}")
    ensure(not result_path.exists(), "A synthetic result already exists; retry is forbidden")
    ensure(not progress_path.exists(), "A synthetic progress log already exists; retry is forbidden")
    ensure(not (round_root / "artifacts" / "m4_a_head.pt").exists(), "M4-a artifact exists; retry is forbidden")
    ensure(not (round_root / "artifacts" / "m4_b_merged_head.pt").exists(), "M4-b artifact exists; retry is forbidden")
    return root, result_path, progress_path, temp_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--progress", required=True)
    parser.add_argument("--temp", required=True)
    args = parser.parse_args(argv)
    try:
        root, result_path, progress_path, temp_path = _validated_cli_paths(
            args.root, args.result, args.progress, args.temp
        )
    except Exception as exc:
        print(f"Unsafe or duplicate round015 paths: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    started = _utc_now()
    _append_progress(progress_path, "synthetic_process_started", root=str(root))
    try:
        result = execute_synthetic(root, result_path, progress_path, temp_path)
        result["started_utc"] = started
        _write_json(result_path, result)
        _append_progress(progress_path, "synthetic_completed", call_counts=result["call_counts"]["observed"])
        print(json.dumps({"status": "completed", "result": str(result_path), "call_counts": result["call_counts"]["observed"]},
                         sort_keys=True))
        return 0
    except Exception as exc:
        failure = {
            "schema": "round015_m4_synthetic_result.v1",
            "status": "failed",
            "started_utc": started,
            "completed_utc": _utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "scope": "failed bounded synthetic-only attempt; do not retry in round015",
        }
        try:
            _write_json(result_path, failure)
            _append_progress(progress_path, "synthetic_failed", error_type=type(exc).__name__, error=str(exc))
        except Exception:
            pass
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
