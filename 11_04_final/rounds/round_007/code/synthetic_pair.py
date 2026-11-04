"""One bounded synthetic baseline/column-chunk pair for round 007.

Only deterministic synthetic arrays are created. No project data is opened.
The manager owns the process budget and invokes this copied source snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from column_chunk import install_column_chunk_adapter


CHECKPOINT_NAME = "tabicl-classifier-v2-20260212.ckpt"
CHECKPOINT_SHA256 = "bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0"
TOLERANCE = 1e-5
ROW_SUM_TOLERANCE = 1e-5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "STATUS.json").is_file() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("could not find project root containing STATUS.json and AGENTS.md")


def json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False, default=json_safe)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def array_sha(array: np.ndarray) -> str:
    return sha_bytes(np.ascontiguousarray(array).tobytes(order="C"))


def input_fingerprints(fit_x: np.ndarray, fit_y: np.ndarray, query_x: np.ndarray) -> dict:
    return {
        "X_fit": {"shape": list(fit_x.shape), "dtype": str(fit_x.dtype), "sha256_c_order_bytes": array_sha(fit_x)},
        "y_fit": {"shape": list(fit_y.shape), "dtype": str(fit_y.dtype), "sha256_c_order_bytes": array_sha(fit_y)},
        "X_query": {"shape": list(query_x.shape), "dtype": str(query_x.dtype), "sha256_c_order_bytes": array_sha(query_x)},
    }


def safe_digest(value: Any) -> str:
    def convert(obj: Any) -> Any:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, dict):
            return {str(key): convert(item) for key, item in sorted(obj.items(), key=lambda pair: str(pair[0]))}
        if isinstance(obj, (tuple, list)):
            return [convert(item) for item in obj]
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return repr(obj)
    return sha_bytes(json.dumps(convert(value), sort_keys=True, ensure_ascii=False).encode("utf-8"))


def actual_shuffle_state(model: Any) -> dict:
    generator = model.ensemble_generator_
    feature = getattr(generator, "feature_shuffles_", {})
    classes = getattr(generator, "class_shuffles_", {})
    return {
        "norm_methods_fit": list(getattr(generator, "norm_methods_", [])),
        "feature_shuffle_method": getattr(generator, "feat_shuffle_method", None),
        "class_shuffle_method": getattr(generator, "class_shuffle_method", None),
        "feature_shuffle_keys": [str(key) for key in feature.keys()],
        "class_shuffle_keys": [str(key) for key in classes.keys()],
        "feature_shuffle_state_sha256": safe_digest(feature),
        "class_shuffle_state_sha256": safe_digest(classes),
        "configured_random_state": getattr(generator, "random_state", None),
    }


def resolved_inference_settings(estimator: Any) -> dict:
    config = getattr(estimator, "inference_config_", None)
    result = {}
    for name in ("COL_CONFIG", "ROW_CONFIG", "ICL_CONFIG"):
        value = getattr(config, name, None) if config is not None else None
        if isinstance(value, dict):
            source = value
        elif value is not None and callable(getattr(value, "items", None)):
            source = dict(value.items())
        else:
            source = None
        if source is None:
            result[name] = repr(value)
            continue
        selected = {key: source.get(key) for key in
                    ("device", "use_amp", "use_fa3", "offload", "disk_offload_dir", "verbose")}
        result[name] = {
            key: item if isinstance(item, (str, int, float, bool)) or item is None else str(item)
            for key, item in selected.items()
        }
    return result


def validate_resolved_inference_state(estimator: Any) -> dict:
    stages = resolved_inference_settings(estimator)
    if set(stages) != {"COL_CONFIG", "ROW_CONFIG", "ICL_CONFIG"}:
        raise RuntimeError("TabICL estimator did not expose all three resolved inference stages")
    for name, config in stages.items():
        if not isinstance(config, dict):
            raise RuntimeError(f"resolved {name} configuration is not inspectable")
        if (config.get("device") != "cpu" or config.get("use_amp") is not False
                or config.get("use_fa3") is not False):
            raise RuntimeError(f"resolved {name} device/AMP/FA3 differs from the fixed CPU FP32 contract")
    if stages["COL_CONFIG"].get("offload") != "auto":
        raise RuntimeError("resolved column offload mode is not 'auto'")
    if stages["ROW_CONFIG"].get("offload") is not False or stages["ICL_CONFIG"].get("offload") is not False:
        raise RuntimeError("resolved row/ICL offload modes differ from the pinned defaults")
    cache_mode_present = hasattr(estimator, "cache_mode_")
    cache_mode = getattr(estimator, "cache_mode_", None)
    model_kv_cache_present = hasattr(estimator, "model_kv_cache_")
    model_kv_cache = getattr(estimator, "model_kv_cache_", None)
    offload_mode = getattr(estimator, "offload_mode", None)
    kv_cache = getattr(estimator, "kv_cache", None)
    if (offload_mode != "auto" or kv_cache is not False or not model_kv_cache_present
            or model_kv_cache is not None or (cache_mode_present and cache_mode is not None)):
        raise RuntimeError("estimator offload/KV-cache settings differ from the fixed CPU contract")
    stages["estimator_scope"] = {
        "offload_mode": offload_mode,
        "kv_cache": kv_cache,
        "model_kv_cache_present": model_kv_cache_present,
        "model_kv_cache_is_none": model_kv_cache is None,
        "cache_mode_present": cache_mode_present,
        "cache_mode": cache_mode,
    }
    return stages


def validate_model_storage(model: Any, torch: Any) -> dict:
    parameters = list(model.parameters())
    buffers = list(model.buffers())
    parameter_devices = sorted({str(parameter.device) for parameter in parameters})
    parameter_dtypes = sorted({str(parameter.dtype) for parameter in parameters})
    floating_parameter_dtypes = sorted(
        {str(parameter.dtype) for parameter in parameters if parameter.dtype.is_floating_point}
    )
    buffer_devices = sorted({str(buffer.device) for buffer in buffers})
    buffer_dtypes = sorted({str(buffer.dtype) for buffer in buffers})
    floating_buffer_dtypes = sorted(
        {str(buffer.dtype) for buffer in buffers if buffer.dtype.is_floating_point}
    )
    if parameter_devices != ["cpu"] or any(device != "cpu" for device in buffer_devices):
        raise RuntimeError("loaded synthetic checkpoint parameters/buffers are not all on CPU")
    if floating_parameter_dtypes != ["torch.float32"]:
        raise RuntimeError("loaded synthetic checkpoint floating parameters are not FP32")
    if any(dtype != "torch.float32" for dtype in floating_buffer_dtypes):
        raise RuntimeError("loaded synthetic checkpoint floating buffers are not FP32")
    return {
        "parameter_count": sum(int(parameter.numel()) for parameter in parameters),
        "buffer_count": sum(int(buffer.numel()) for buffer in buffers),
        "parameter_devices": parameter_devices,
        "parameter_dtypes": parameter_dtypes,
        "floating_parameter_dtypes": floating_parameter_dtypes,
        "buffer_devices": buffer_devices,
        "buffer_dtypes": buffer_dtypes,
        "floating_buffer_dtypes": floating_buffer_dtypes,
    }


def validate_runtime_managers(estimator: Any, col_manager_override: Any = None) -> dict:
    model = estimator.model_
    manager_specs = (
        ("COL", col_manager_override if col_manager_override is not None
         else model.col_embedder.inference_mgr, "tf_col", "AUTO"),
        ("ROW", model.row_interactor.inference_mgr, "tf_row", "GPU"),
        ("ICL", model.icl_predictor.inference_mgr, "tf_icl", "GPU"),
    )
    resolved = {}
    for stage_name, manager, enc_name, expected_offload in manager_specs:
        if getattr(manager, "enc_name", None) != enc_name:
            raise RuntimeError(f"{stage_name} inference manager has an unexpected encoder name")
        if getattr(manager, "_is_configured", False) is not True:
            raise RuntimeError(f"{stage_name} inference manager has not been configured")
        device = getattr(getattr(manager, "exe_device", None), "type", None)
        use_amp = getattr(manager, "use_amp", None)
        use_fa3 = getattr(manager, "use_fa3", None)
        offload_value = getattr(manager, "offload_mode", None)
        offload_name = getattr(offload_value, "name", str(offload_value))
        if device != "cpu" or use_amp is not False or use_fa3 is not False:
            raise RuntimeError(f"{stage_name} manager resolved away from CPU FP32/AMP=false/FA3=false")
        if offload_name != expected_offload:
            raise RuntimeError(
                f"{stage_name} manager offload resolved to {offload_name!r}, expected {expected_offload!r}"
            )
        resolved[stage_name] = {
            "enc_name": enc_name,
            "configured": True,
            "device_type": device,
            "use_amp": use_amp,
            "use_fa3": use_fa3,
            "offload_mode": offload_name,
        }
    return resolved


def probability_summary(raw: Any, name: str) -> dict:
    values = np.asarray(raw)
    shape_ok = values.shape == (2, 4)
    finite = bool(np.isfinite(values).all()) if values.size else False
    in_range = bool(np.all((values >= 0.0) & (values <= 1.0))) if finite else False
    row_sum_error = float(np.max(np.abs(values.sum(axis=1) - 1.0))) if shape_ok and finite else None
    return {
        "name": name,
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "finite": finite,
        "within_0_1": in_range,
        "max_abs_row_sum_error": row_sum_error,
        "row_sum_gate_pass": row_sum_error is not None and row_sum_error <= ROW_SUM_TOLERANCE,
        "values": values.astype(np.float64).tolist() if finite else None,
        "gate_pass": bool(shape_ok and finite and in_range and row_sum_error is not None
                           and row_sum_error <= ROW_SUM_TOLERANCE),
    }


def save_synthetic_outputs(path: Path, fit_x: np.ndarray, fit_y: np.ndarray, query_x: np.ndarray,
                           baseline: np.ndarray, chunked: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            np.savez(stream, X_fit=fit_x, y_fit=fit_y, X_query=query_x,
                     baseline_probabilities=baseline, chunked_probabilities=chunked)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    root = find_project_root()
    round_dir = root / "rounds" / "round_007"
    result_path = round_dir / "artifacts" / "synthetic_pair_result.json"
    outputs_path = round_dir / "artifacts" / "synthetic_pair_outputs.npz"
    checkpoint_path = root / "model_cache" / CHECKPOINT_NAME
    offload_dir = round_dir / "temp" / "synthetic_pair_offload"
    if result_path.exists() or outputs_path.exists():
        raise FileExistsError("round-007 synthetic pair output already exists; do not rerun this comparison")

    started = time.perf_counter()
    source_path = Path(__file__).resolve()
    record = {
        "schema": "round007_synthetic_pair_result.v1",
        "status": "STARTED",
        "stage": "process_entry",
        "started_utc": utc_now(),
        "pid": os.getpid(),
        "source_path": str(source_path),
        "source_at_entry_sha256": sha_file(source_path),
        "scope": "synthetic only; no project data arrays, probabilities, raw rows, holdout, or F1",
        "checkpoint_fit_invocation_count": 0,
        "fit_attempted_count": 0,
        "fit_completed_count": 0,
        "predict_proba_attempted_count": 0,
        "predict_proba_completed_count": 0,
        "adapter_installed": False,
        "adapter_restored": False,
        "adapter_events": [],
        "stages": [],
    }

    def persist() -> None:
        atomic_json(result_path, record)

    def stage(name: str, **fields: Any) -> None:
        marker = {"stage": name, "utc": utc_now(), **json_safe(fields)}
        record["stage"] = name
        record["stages"].append(marker)
        record.update(json_safe(fields))
        persist()
        print(json.dumps({"event": "stage", **marker}, ensure_ascii=False, allow_nan=False), flush=True)

    persist()
    installation = None
    try:
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"pinned checkpoint is missing: {checkpoint_path}")
        checkpoint_hash = sha_file(checkpoint_path)
        if checkpoint_hash != CHECKPOINT_SHA256:
            raise ValueError("pinned checkpoint SHA-256 does not match the round004 contract")
        stage("checkpoint_source_verified", checkpoint_path=str(checkpoint_path),
              checkpoint_sha256=checkpoint_hash)

        rng = np.random.default_rng(20261105)
        fit_x = rng.normal(0.0, 1.0, size=(32, 312)).astype(np.float32)
        query_x = rng.normal(0.0, 1.0, size=(2, 312)).astype(np.float32)
        fit_y = np.tile(np.arange(4), 8)
        if fit_x.shape != (32, 312) or query_x.shape != (2, 312) or fit_y.shape != (32,):
            raise AssertionError("synthetic pair dimensions changed from the fixed contract")
        record["inputs"] = {
            "rng": "numpy.default_rng(20261105)",
            "distribution": "standard normal (loc=0.0, scale=1.0)",
            "X_fit": {"shape": list(fit_x.shape), "dtype": str(fit_x.dtype), "sha256_c_order_bytes": array_sha(fit_x)},
            "y_fit": {"shape": list(fit_y.shape), "dtype": str(fit_y.dtype), "sha256_c_order_bytes": array_sha(fit_y),
                      "values": fit_y.tolist()},
            "X_query": {"shape": list(query_x.shape), "dtype": str(query_x.dtype),
                        "sha256_c_order_bytes": array_sha(query_x)},
            "same_input_arrays_and_order_for_both_paths": True,
        }
        stage("synthetic_inputs_created", inputs=record["inputs"])

        if os.environ.get("OMP_NUM_THREADS") != "3" or os.environ.get("MKL_NUM_THREADS") != "3":
            raise ValueError("bounded runner must set OMP_NUM_THREADS=3 and MKL_NUM_THREADS=3")
        os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ["TABICL_PATH"] = str(checkpoint_path)
        os.environ["TABICL_CHECKPOINT"] = CHECKPOINT_NAME
        offload_dir.mkdir(parents=True, exist_ok=True)

        stage("package_import_pending", requested_versions={"tabicl": "2.2.0", "torch": "2.6.0+cpu"})
        from importlib.metadata import version
        if version("tabicl") != "2.2.0":
            raise RuntimeError("installed TabICL package is not version 2.2.0")
        import torch
        torch.set_num_threads(3)
        torch.set_num_interop_threads(1)
        from tabicl import TabICLClassifier
        if not torch.__version__.startswith("2.6.0") or torch.cuda.is_available():
            raise RuntimeError("runtime is not the pinned Torch 2.6.0 CPU environment")
        stage("package_imported", package_versions={"tabicl": version("tabicl"), "torch": torch.__version__,
                                                     "numpy": np.__version__},
              torch_threads={"intra_op": torch.get_num_threads(), "interop": torch.get_num_interop_threads()})

        settings = {
            "n_estimators": 8,
            "batch_size": 1,
            "model_path": str(checkpoint_path),
            "allow_auto_download": False,
            "checkpoint_version": CHECKPOINT_NAME,
            "device": "cpu",
            "use_amp": False,
            "use_fa3": False,
            "offload_mode": "auto",
            "disk_offload_dir": str(offload_dir),
            "random_state": 42,
            "n_jobs": 3,
            "norm_methods": {"value": None, "origin": "TabICL 2.2.0 default; fit expands to none,power"},
            "feature_shuffle_method": {"value": "latin", "origin": "TabICL 2.2.0 constructor default"},
            "class_shuffle_method": {"value": "shift", "origin": "TabICL 2.2.0 constructor default"},
            "softmax_temperature": {"value": 0.9, "origin": "TabICL 2.2.0 constructor default"},
            "average_logits": {"value": True, "origin": "TabICL 2.2.0 constructor default"},
            "outlier_threshold": {"value": 4.0, "origin": "TabICL 2.2.0 constructor default"},
            "support_many_classes": {"value": True, "origin": "TabICL 2.2.0 constructor default"},
            "kv_cache": {"value": False, "origin": "TabICL 2.2.0 constructor default"},
        }
        record["estimator_settings"] = settings
        estimator = TabICLClassifier(
            n_estimators=8,
            batch_size=1,
            model_path=str(checkpoint_path),
            allow_auto_download=False,
            checkpoint_version=CHECKPOINT_NAME,
            device="cpu",
            use_amp=False,
            use_fa3=False,
            offload_mode="auto",
            disk_offload_dir=str(offload_dir),
            random_state=42,
            n_jobs=3,
        )
        record["checkpoint_fit_invocation_count"] = 1
        record["fit_attempted_count"] = 1
        stage("fit_start", estimator_settings=settings, fit_input_rows=32, fit_feature_count=312,
              fit_label_values=sorted(int(value) for value in np.unique(fit_y)))
        estimator.fit(fit_x, fit_y)
        record["fit_completed_count"] = 1
        if str(getattr(estimator, "device_", "unknown")) != "cpu":
            raise RuntimeError("estimator resolved to a non-CPU device")
        if [int(value) for value in estimator.classes_] != [0, 1, 2, 3]:
            raise RuntimeError("synthetic fit did not preserve canonical class order [0,1,2,3]")
        record["resolved_inference_settings"] = validate_resolved_inference_state(estimator)
        record["model_storage"] = validate_model_storage(estimator.model_, torch)
        record["resolved_shuffle_state"] = actual_shuffle_state(estimator)
        stage("fit_complete", fit_completed_count=1, resolved_device=str(estimator.device_),
              class_order=[int(value) for value in estimator.classes_],
              resolved_inference_settings=record["resolved_inference_settings"],
              model_storage=record["model_storage"],
              resolved_shuffle_state=record["resolved_shuffle_state"])

        baseline_pre_inputs = input_fingerprints(fit_x, fit_y, query_x)
        baseline_pre_shuffle = actual_shuffle_state(estimator)
        if baseline_pre_inputs != {key: record["inputs"][key] for key in ("X_fit", "y_fit", "X_query")}:
            raise RuntimeError("synthetic arrays changed between creation/fit and baseline prediction")
        if baseline_pre_shuffle != record["resolved_shuffle_state"]:
            raise RuntimeError("ensemble shuffle state changed between fit and baseline prediction")
        record["predict_proba_attempted_count"] = 1
        stage("baseline_predict_proba_start", predict_proba_attempted_count=1,
              predict_proba_completed_count=0, baseline_pre_call_input_fingerprints=baseline_pre_inputs,
              baseline_pre_call_shuffle_state=baseline_pre_shuffle)
        baseline_raw = estimator.predict_proba(query_x)
        record["predict_proba_completed_count"] = 1
        baseline = np.asarray(baseline_raw)
        baseline_post_inputs = input_fingerprints(fit_x, fit_y, query_x)
        baseline_post_shuffle = actual_shuffle_state(estimator)
        baseline_state_unchanged = bool(baseline_post_inputs == baseline_pre_inputs
                                        and baseline_post_shuffle == baseline_pre_shuffle)
        record["baseline_post_call_input_fingerprints"] = baseline_post_inputs
        record["baseline_post_call_shuffle_state"] = baseline_post_shuffle
        record["baseline_input_and_shuffle_state_unchanged"] = baseline_state_unchanged
        record["baseline_probability_check"] = probability_summary(baseline, "baseline")
        stage("baseline_predict_proba_complete", predict_proba_completed_count=1,
              baseline_probability_check=record["baseline_probability_check"],
              baseline_post_call_input_fingerprints=baseline_post_inputs,
              baseline_post_call_shuffle_state=baseline_post_shuffle,
              baseline_input_and_shuffle_state_unchanged=baseline_state_unchanged)
        if not baseline_state_unchanged:
            raise RuntimeError("baseline prediction mutated synthetic inputs or fitted shuffle state")
        baseline_manager_state = validate_runtime_managers(estimator)
        record["baseline_runtime_manager_state"] = baseline_manager_state
        stage("runtime_managers_verified_after_baseline", runtime_manager_state=baseline_manager_state,
              estimator_kv_cache=getattr(estimator, "kv_cache", None),
              model_kv_cache_is_none=getattr(estimator, "model_kv_cache_", None) is None)

        def on_adapter_event(event: dict) -> None:
            record["adapter_events"].append(json_safe(event))
            record["latest_adapter_event"] = json_safe(event)
            persist()

        installation = install_column_chunk_adapter(estimator, on_event=on_adapter_event)
        record["adapter_installed"] = True
        stage("column_adapter_installed", target="estimator.model_.col_embedder.inference_mgr",
              wrapper="round_007.code.column_chunk.ColumnChunkManager",
              chunk_columns=16, row_and_icl_managers_modified=False)
        chunked_raw = None
        try:
            chunked_pre_inputs = input_fingerprints(fit_x, fit_y, query_x)
            chunked_pre_shuffle = actual_shuffle_state(estimator)
            if chunked_pre_inputs != baseline_pre_inputs:
                raise RuntimeError("synthetic arrays differ before the adapted prediction")
            if chunked_pre_shuffle != baseline_pre_shuffle:
                raise RuntimeError("ensemble shuffle state differs before the adapted prediction")
            record["predict_proba_attempted_count"] = 2
            stage("chunked_predict_proba_start", predict_proba_attempted_count=2,
                  predict_proba_completed_count=1, chunked_pre_call_input_fingerprints=chunked_pre_inputs,
                  chunked_pre_call_shuffle_state=chunked_pre_shuffle)
            chunked_raw = estimator.predict_proba(query_x)
            record["predict_proba_completed_count"] = 2
            chunked = np.asarray(chunked_raw)
            chunked_post_inputs = input_fingerprints(fit_x, fit_y, query_x)
            chunked_post_shuffle = actual_shuffle_state(estimator)
            chunked_state_unchanged = bool(chunked_post_inputs == chunked_pre_inputs
                                           and chunked_post_shuffle == chunked_pre_shuffle)
            chunked_manager_state = validate_runtime_managers(
                estimator, col_manager_override=installation.original_manager
            )
            chunked_manager_state_unchanged = chunked_manager_state == baseline_manager_state
            record["chunked_post_call_input_fingerprints"] = chunked_post_inputs
            record["chunked_post_call_shuffle_state"] = chunked_post_shuffle
            record["chunked_input_and_shuffle_state_unchanged"] = chunked_state_unchanged
            record["chunked_runtime_manager_state"] = chunked_manager_state
            record["chunked_runtime_manager_state_unchanged"] = chunked_manager_state_unchanged
            record["chunked_probability_check"] = probability_summary(chunked, "column_chunked")
            stage("chunked_predict_proba_complete", predict_proba_completed_count=2,
                  chunked_probability_check=record["chunked_probability_check"],
                  chunked_post_call_input_fingerprints=chunked_post_inputs,
                  chunked_post_call_shuffle_state=chunked_post_shuffle,
                  chunked_input_and_shuffle_state_unchanged=chunked_state_unchanged,
                  chunked_runtime_manager_state=chunked_manager_state,
                  chunked_runtime_manager_state_unchanged=chunked_manager_state_unchanged)
            if not chunked_state_unchanged:
                raise RuntimeError("adapted prediction mutated synthetic inputs or fitted shuffle state")
            if not chunked_manager_state_unchanged:
                raise RuntimeError("runtime manager settings changed during adapted prediction")
        finally:
            installation.restore()
            record["adapter_installed"] = False
            record["adapter_restored"] = True
            stage("column_adapter_restored", restored=True,
                  original_manager_reinstated=(estimator.model_.col_embedder.inference_mgr
                                               is installation.original_manager))

        baseline = np.asarray(baseline_raw)
        chunked = np.asarray(chunked_raw)
        comparison = {
            "scope": "two synthetic query rows only; same fitted estimator and inputs; no F1",
            "tolerance": TOLERANCE,
            "baseline_probability_gate_pass": record["baseline_probability_check"]["gate_pass"],
            "chunked_probability_gate_pass": record["chunked_probability_check"]["gate_pass"],
            "max_abs_probability_difference": None,
            "exact_numeric_equal": False,
            "argmax_equal": False,
            "argmax_baseline": None,
            "argmax_chunked": None,
            "within_tolerance_and_argmax_gate_pass": False,
        }
        if baseline.shape == (2, 4) and chunked.shape == (2, 4) and np.isfinite(baseline).all() and np.isfinite(chunked).all():
            baseline64 = baseline.astype(np.float64)
            chunked64 = chunked.astype(np.float64)
            difference = np.abs(baseline64 - chunked64)
            comparison.update({
                "max_abs_probability_difference": float(difference.max()),
                "exact_numeric_equal": bool(np.array_equal(baseline64, chunked64)),
                "argmax_equal": bool(np.array_equal(np.argmax(baseline64, axis=1), np.argmax(chunked64, axis=1))),
                "argmax_baseline": np.argmax(baseline64, axis=1).astype(int).tolist(),
                "argmax_chunked": np.argmax(chunked64, axis=1).astype(int).tolist(),
            })
            comparison["within_tolerance_and_argmax_gate_pass"] = bool(
                difference.max() <= TOLERANCE and comparison["argmax_equal"]
            )
        gate = bool(comparison["baseline_probability_gate_pass"]
                    and comparison["chunked_probability_gate_pass"]
                    and comparison["within_tolerance_and_argmax_gate_pass"])
        record["comparison"] = comparison
        save_synthetic_outputs(outputs_path, fit_x, fit_y, query_x, baseline, chunked)
        record["outputs_path"] = str(outputs_path)
        record["outputs_sha256"] = sha_file(outputs_path)
        stage("comparison_complete", comparison=comparison, outputs_path=str(outputs_path),
              outputs_sha256=record["outputs_sha256"], is_performance_or_f1_claim=False)
        record["status"] = "SYNTHETIC_PAIR_COMPLETE" if gate else "SYNTHETIC_PAIR_GATE_FAILED"
        record["finished_utc"] = utc_now()
        record["elapsed_seconds"] = time.perf_counter() - started
        persist()
        print(json.dumps({"status": record["status"], "comparison": comparison,
                          "predict_proba_attempted_count": record["predict_proba_attempted_count"],
                          "predict_proba_completed_count": record["predict_proba_completed_count"],
                          "elapsed_seconds": record["elapsed_seconds"]}, ensure_ascii=False,
                         allow_nan=False, default=json_safe), flush=True)
        return 0 if gate else 1
    except Exception as exc:
        record.update({"status": "FAILED", "stage": "exception", "error_type": type(exc).__name__,
                       "error": str(exc), "traceback": traceback.format_exc(),
                       "finished_utc": utc_now(), "elapsed_seconds": time.perf_counter() - started})
        persist()
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)},
                         ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
