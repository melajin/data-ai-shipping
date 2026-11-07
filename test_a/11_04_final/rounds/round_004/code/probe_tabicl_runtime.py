"""Bounded, synthetic-only TabICL v2.2.0 CPU runtime probe.

This script deliberately does not open project datasets. It loads one explicitly
provided checkpoint into one classifier instance, then evaluates 4 synthetic query
rows against a 16-row synthetic in-context FIT set.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SEED = 20261105
EXPECTED_TABICL_VERSION = "2.2.0"
EXPECTED_CHECKPOINT_NAME = "tabicl-classifier-v2-20260212.ckpt"
HISTORICAL_REFERENCE = {
    "parameter_count": 27_552_258,
    "output_head_linear_dimensions": [[512, 1024], [1024, 10]],
    "note": "Round 004 NEXT_SESSION historical reference for the output head, not the full model's Linear layer list.",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return repr(value)


def _write_staged_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist the current stage and any captured failure details."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _windows_memory_snapshot() -> dict[str, int] | None:
    """Return current and lifetime peak working set on Windows without extra packages."""
    if os.name != "nt":
        return None

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    try:
        counters = ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_memory_info = psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCountersEx), ctypes.c_ulong]
        get_memory_info.restype = ctypes.c_int
        ok = get_memory_info(get_current_process(), ctypes.byref(counters), counters.cb)
        if not ok:
            return None
        return {
            "current_working_set_bytes": int(counters.WorkingSetSize),
            "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
            "private_bytes": int(counters.PrivateUsage),
        }
    except Exception:
        return None


def _memory_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {"windows_process_memory": _windows_memory_snapshot()}
    try:
        import psutil

        process = psutil.Process(os.getpid())
        snapshot["rss_bytes"] = int(process.memory_info().rss)
        snapshot["available_system_ram_bytes"] = int(psutil.virtual_memory().available)
    except Exception as exc:
        snapshot["psutil_error"] = f"{type(exc).__name__}: {exc}"
    return snapshot


def _timed_phase(
    record: dict[str, Any],
    name: str,
    function: Callable[[], Any],
    write_record: Callable[[], None],
) -> Any:
    record["stage"] = name
    record.setdefault("memory_snapshots", {})[name + "_before"] = _memory_snapshot()
    write_record()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        return function()
    finally:
        record.setdefault("timings", {})[name] = {
            "wall_seconds": time.perf_counter() - wall_start,
            "process_cpu_seconds": time.process_time() - cpu_start,
        }
        record["memory_snapshots"][name + "_after"] = _memory_snapshot()
        write_record()


def _safe_output_path(path: Path) -> Path:
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"--output must resolve inside project root: {root}") from exc
    return resolved


def _resolve_project_argument(path: Path) -> Path:
    """Resolve relative CLI paths from the project root, independent of cwd."""
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded synthetic-only TabICL 2.2.0 CPU checkpoint smoke."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=PROJECT_ROOT / "model_cache" / EXPECTED_CHECKPOINT_NAME,
        help="Explicit local classifier checkpoint; auto-download is disabled.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "rounds" / "round_004" / "artifacts" / "smoke.json",
        help="JSON output path (must resolve inside the project root).",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    requested_output_path = _resolve_project_argument(args.output)
    output_validation_error: str | None = None
    try:
        output_path = _safe_output_path(requested_output_path)
    except ValueError as exc:
        # Keep a failure record in a known-safe project location.
        output_path = PROJECT_ROOT / "rounds" / "round_004" / "artifacts" / "smoke.json"
        output_validation_error = str(exc)
    checkpoint_path = _resolve_project_argument(args.checkpoint)
    record: dict[str, Any] = {
        "schema": "tabicl_runtime_probe.v1",
        "status": "running",
        "stage": "startup",
        "started_at_utc": _utc_now(),
        "scope": "synthetic_only; no project dataset inputs; no training; no F1/accuracy metrics",
        "project_root": str(PROJECT_ROOT),
        "cli": {
            "checkpoint": str(checkpoint_path),
            "requested_output": str(requested_output_path),
            "staged_output": str(output_path),
        },
        "expected": {
            "tabicl_version": EXPECTED_TABICL_VERSION,
            "checkpoint_name": EXPECTED_CHECKPOINT_NAME,
            "seed": SEED,
            "fit_rows": 16,
            "query_rows": 4,
            "features": 312,
            "dtype": "float32",
            "classes": [0, 1, 2, 3],
            "n_estimators": 1,
            "batch_size": 1,
            "device": "cpu",
            "use_amp": False,
            "use_fa3": False,
            "allow_auto_download": False,
            "threads": 3,
        },
        "sources": {
            "version_pinned_classifier": "https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/classifier.py",
            "version_pinned_base": "https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/base.py",
            "version_pinned_model": "https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_model/tabicl.py",
            "version_pinned_learning": "https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_model/learning.py",
        },
        "versions": {
            "python": sys.version,
            "platform": platform.platform(),
            "tabicl": _package_version("tabicl"),
            "torch": _package_version("torch"),
            "numpy": _package_version("numpy"),
            "scikit_learn": _package_version("scikit-learn"),
        },
        "historical_reference": HISTORICAL_REFERENCE,
    }
    current_stage = "startup"

    def write_record() -> None:
        record["updated_at_utc"] = _utc_now()
        _write_staged_json(output_path, record)

    try:
        write_record()
        if output_validation_error is not None:
            raise ValueError(output_validation_error)
        if checkpoint_path.name != EXPECTED_CHECKPOINT_NAME:
            raise ValueError(
                f"Expected checkpoint basename {EXPECTED_CHECKPOINT_NAME!r}; received {checkpoint_path.name!r}."
            )
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Explicit checkpoint does not exist: {checkpoint_path}")
        record["checkpoint"] = {
            "path": str(checkpoint_path),
            "bytes": checkpoint_path.stat().st_size,
            "sha256": _sha256(checkpoint_path),
        }
        record["stage"] = "checkpoint_verified"
        write_record()

        # Bound BLAS/OpenMP and PyTorch worker counts before importing numerical libraries.
        for variable in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            os.environ[variable] = "3"

        current_stage = "import_runtime"
        record["stage"] = current_stage
        write_record()
        import numpy as np
        import torch
        from tabicl import TabICLClassifier

        actual_tabicl_version = _package_version("tabicl")
        if actual_tabicl_version != EXPECTED_TABICL_VERSION:
            raise RuntimeError(
                f"Required tabicl=={EXPECTED_TABICL_VERSION}, found {actual_tabicl_version!r}."
            )
        torch.set_num_threads(3)
        torch.set_num_interop_threads(3)
        torch.manual_seed(SEED)
        record["runtime_settings"] = {
            "torch_num_threads": torch.get_num_threads(),
            "torch_num_interop_threads": torch.get_num_interop_threads(),
        }
        record["api_signatures"] = {
            "TabICLClassifier.__init__": str(inspect.signature(TabICLClassifier.__init__)),
            "TabICLClassifier.fit": str(inspect.signature(TabICLClassifier.fit)),
            "TabICLClassifier.predict_proba": str(inspect.signature(TabICLClassifier.predict_proba)),
            "TabICLClassifier.predict": str(inspect.signature(TabICLClassifier.predict)),
        }
        required_constructor_parameters = {
            "n_estimators",
            "batch_size",
            "model_path",
            "allow_auto_download",
            "device",
            "use_amp",
            "use_fa3",
        }
        constructor_parameters = set(inspect.signature(TabICLClassifier.__init__).parameters)
        missing_parameters = sorted(required_constructor_parameters - constructor_parameters)
        if missing_parameters:
            raise RuntimeError(f"Installed API lacks required parameters: {missing_parameters}")
        record["stage"] = "runtime_ready"
        write_record()

        current_stage = "synthetic_input"
        rng = np.random.default_rng(SEED)
        synthetic_x = rng.standard_normal((20, 312)).astype(np.float32)
        x_fit = np.ascontiguousarray(synthetic_x[:16], dtype=np.float32)
        x_query = np.ascontiguousarray(synthetic_x[16:], dtype=np.float32)
        y_fit = np.tile(np.arange(4, dtype=np.int64), 4)
        if x_fit.shape != (16, 312) or x_query.shape != (4, 312):
            raise AssertionError("Synthetic input shapes do not match the fixed smoke contract.")
        if x_fit.dtype != np.float32 or x_query.dtype != np.float32:
            raise AssertionError("Synthetic feature arrays must be float32.")
        if set(y_fit.tolist()) != {0, 1, 2, 3}:
            raise AssertionError("Synthetic FIT labels do not include all four classes.")
        record["synthetic_input"] = {
            "fit_shape": list(x_fit.shape),
            "query_shape": list(x_query.shape),
            "fit_dtype": str(x_fit.dtype),
            "query_dtype": str(x_query.dtype),
            "fit_label_counts": {str(label): int(count) for label, count in zip(*np.unique(y_fit, return_counts=True))},
            "feature_sha256": hashlib.sha256(synthetic_x.tobytes(order="C")).hexdigest(),
            "label_sha256": hashlib.sha256(y_fit.tobytes(order="C")).hexdigest(),
        }
        record["stage"] = "synthetic_input_ready"
        write_record()

        current_stage = "estimator_fit_context"
        estimator = TabICLClassifier(
            n_estimators=1,
            batch_size=1,
            model_path=str(checkpoint_path),
            allow_auto_download=False,
            device="cpu",
            use_amp=False,
            use_fa3=False,
            random_state=SEED,
            n_jobs=1,
            verbose=False,
        )
        _timed_phase(record, "fit_context_and_checkpoint_load", lambda: estimator.fit(x_fit, y_fit), write_record)
        # TabICL fit binds the synthetic context and loads pretrained weights; it is not gradient training.
        if not hasattr(estimator, "model_"):
            raise AssertionError("fit did not expose the loaded model_ instance.")
        resolved_device = str(estimator.device_)
        if torch.device(estimator.device_).type != "cpu":
            raise AssertionError(f"Estimator resolved to non-CPU device: {resolved_device}")
        record["fit_semantics"] = {
            "interpretation": "synthetic in-context binding and checkpoint loading; pretrained model weights are not trained",
            "model_training_requested": False,
            "fit_rows": int(x_fit.shape[0]),
            "resolved_estimator_device": resolved_device,
        }

        current_stage = "inspect_model"
        model = estimator.model_
        linear_layers: list[dict[str, Any]] = []
        for module_name, module in model.named_modules():
            if isinstance(module, torch.nn.Linear):
                parameter_count = sum(parameter.numel() for parameter in module.parameters(recurse=False))
                linear_layers.append(
                    {
                        "name": module_name,
                        "in_features": int(module.in_features),
                        "out_features": int(module.out_features),
                        "weight_shape": list(module.weight.shape),
                        "has_bias": module.bias is not None,
                        "parameter_count": int(parameter_count),
                    }
                )
        model_parameters = list(model.parameters())
        model_buffers = list(model.buffers())
        total_parameters = sum(parameter.numel() for parameter in model_parameters)
        trainable_parameters = sum(parameter.numel() for parameter in model_parameters if parameter.requires_grad)
        parameter_devices = sorted({str(parameter.device) for parameter in model_parameters})
        parameter_device_types = sorted({parameter.device.type for parameter in model_parameters})
        floating_parameter_dtypes = sorted(
            {str(parameter.dtype) for parameter in model_parameters if parameter.is_floating_point()}
        )
        buffer_devices = sorted({str(buffer.device) for buffer in model_buffers})
        buffer_dtypes = sorted({str(buffer.dtype) for buffer in model_buffers})
        if parameter_device_types != ["cpu"] or buffer_devices and any(
            torch.device(device).type != "cpu" for device in buffer_devices
        ):
            raise AssertionError(
                f"Loaded model is not entirely on CPU: parameters={parameter_devices}, buffers={buffer_devices}"
            )
        if floating_parameter_dtypes != ["torch.float32"]:
            raise AssertionError(f"Expected FP32 model parameters, found {floating_parameter_dtypes}")
        registered_linear_dimensions = [
            [layer["in_features"], layer["out_features"]] for layer in linear_layers
        ]
        output_head_layers = [
            layer
            for layer in linear_layers
            if layer["name"].startswith("icl_predictor.decoder.")
        ]
        output_head_dimensions = [
            [layer["in_features"], layer["out_features"]] for layer in output_head_layers
        ]
        record["model"] = {
            "class": f"{type(model).__module__}.{type(model).__qualname__}",
            "config": getattr(estimator, "model_config_", None),
            "repr": repr(model)[:20000],
            "parameter_count": int(total_parameters),
            "trainable_parameter_count": int(trainable_parameters),
            "registered_linear_layer_count": len(linear_layers),
            "registered_linear_layers": linear_layers,
            "last_registered_linear": linear_layers[-1] if linear_layers else None,
            "output_head_path": "icl_predictor.decoder (TabICL v2.2.0 ICLearning decoder)",
            "output_head_linear_layers": output_head_layers,
            "output_head_parameter_count": int(sum(layer["parameter_count"] for layer in output_head_layers)),
            "output_head_final_linear": output_head_layers[-1] if output_head_layers else None,
            "parameter_devices": parameter_devices,
            "parameter_device_types": parameter_device_types,
            "floating_parameter_dtypes": floating_parameter_dtypes,
            "buffer_devices": buffer_devices,
            "buffer_dtypes": buffer_dtypes,
            "historical_comparison": {
                "parameter_count_matches": total_parameters == HISTORICAL_REFERENCE["parameter_count"],
                "output_head_dimensions_match_reference": (
                    output_head_dimensions == HISTORICAL_REFERENCE["output_head_linear_dimensions"]
                ),
                "actual_registered_linear_dimensions": registered_linear_dimensions,
                "actual_output_head_linear_dimensions": output_head_dimensions,
            },
        }
        record["stage"] = "model_inspected"
        write_record()

        current_stage = "predict_proba_first"
        proba_first = _timed_phase(
            record,
            "predict_proba_first",
            lambda: estimator.predict_proba(x_query),
            write_record,
        )
        record.setdefault("probability_outputs", {})["first_call"] = {
            "dtype": str(np.asarray(proba_first).dtype),
            "values": np.asarray(proba_first).tolist(),
        }
        write_record()
        current_stage = "predict_proba_repeat"
        proba_repeat = _timed_phase(
            record,
            "predict_proba_repeat",
            lambda: estimator.predict_proba(x_query),
            write_record,
        )
        record["probability_outputs"]["repeat_call"] = {
            "dtype": str(np.asarray(proba_repeat).dtype),
            "values": np.asarray(proba_repeat).tolist(),
        }
        write_record()
        current_stage = "predict_labels"
        predicted_labels = _timed_phase(
            record,
            "predict_labels",
            lambda: estimator.predict(x_query),
            write_record,
        )

        classes = np.asarray(estimator.classes_)
        if proba_first.shape != (4, 4) or proba_repeat.shape != (4, 4):
            raise AssertionError(
                f"Expected each probability result to have shape (4, 4); got {proba_first.shape} and {proba_repeat.shape}."
            )
        finite = bool(np.isfinite(proba_first).all() and np.isfinite(proba_repeat).all())
        if not finite:
            raise AssertionError("Probability output contains NaN or infinity.")
        row_sums = proba_first.sum(axis=1)
        row_sums_valid = bool(np.allclose(row_sums, 1.0, rtol=0.0, atol=1e-5))
        if not row_sums_valid:
            raise AssertionError(f"Probability rows do not sum to one within 1e-5: {row_sums.tolist()}")
        classes_valid = bool(np.array_equal(classes, np.array([0, 1, 2, 3])))
        if not classes_valid:
            raise AssertionError(f"Unexpected inverse class order: {classes.tolist()}")
        argmax_inverse = classes[np.argmax(proba_first, axis=1)]
        class_inverse_valid = bool(np.array_equal(argmax_inverse, predicted_labels))
        if not class_inverse_valid:
            raise AssertionError("predict labels do not match inverse-transformed probability argmax classes.")
        repeat_delta = float(np.max(np.abs(proba_first - proba_repeat)))
        repeat_equal = bool(np.allclose(proba_first, proba_repeat, rtol=0.0, atol=1e-7))
        parameters_have_grad = any(parameter.grad is not None for parameter in model_parameters)
        output_has_gradient = bool(getattr(proba_first, "requires_grad", False))
        if parameters_have_grad or output_has_gradient:
            raise AssertionError("A gradient was attached or accumulated during the inference smoke.")
        if not repeat_equal:
            raise AssertionError(f"Repeated predictions changed by max absolute delta {repeat_delta}.")

        record["checks"] = {
            "probability_shape": list(proba_first.shape),
            "probability_dtype": str(proba_first.dtype),
            "probabilities_finite": finite,
            "probability_row_sums": [float(value) for value in row_sums],
            "probability_row_sums_close_to_one_atol_1e-5": row_sums_valid,
            "classes": classes.tolist(),
            "class_inverse_mapping_valid": class_inverse_valid,
            "predicted_labels": np.asarray(predicted_labels).tolist(),
            "repeat_max_absolute_probability_delta": repeat_delta,
            "repeat_equal_atol_1e-7": repeat_equal,
            "probability_first": proba_first.tolist(),
            "probability_repeat": proba_repeat.tolist(),
            "parameter_gradients_present": parameters_have_grad,
            "numpy_output_has_gradient": output_has_gradient,
        }
        record["stage"] = "checks_passed"
        write_record()

        record["status"] = "completed"
        record["stage"] = "complete"
        record["finished_at_utc"] = _utc_now()
        record["final_memory_snapshot"] = _memory_snapshot()
        write_record()
        print(json.dumps(record, ensure_ascii=False, indent=2, default=_json_default))
        return 0
    except Exception as exc:
        record["status"] = "failed"
        record["stage"] = current_stage
        record["failed_at_utc"] = _utc_now()
        record["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        try:
            write_record()
        except Exception as write_exc:
            record["error"]["staged_json_write_error"] = f"{type(write_exc).__name__}: {write_exc}"
        print(json.dumps(record, ensure_ascii=False, indent=2, default=_json_default))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
