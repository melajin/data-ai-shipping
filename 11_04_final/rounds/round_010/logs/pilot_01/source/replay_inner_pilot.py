from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np
from column_chunk import CHUNK_COLUMNS, install_column_chunk_adapter
from row_chunk import CHUNK_ROWS, install_row_chunk_adapter
from icl_observer import install_icl_call_observer, verify_full_context


ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final")
ROUND = ROOT / "rounds" / "round_010"
P = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
CHECKPOINT_SHA256 = "bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0"
CHECKPOINT_BYTES = 110368038
CONTRACT_PATH = ROOT / "rounds" / "round_004" / "runtime_author" / "replay_contract.json"
EXPECTED_CONTRACT_SHA256 = "819e60fd2f05a655a86dc1cdaa5e52f5a4fd0486e78fdd5dc5a4ab140ad7e2f5"
ADAPTER_SHA256 = "bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded"
ROW_ADAPTER_SHA256 = "d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b"
EXPECTED_CONTEXT_SHA256 = "9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5"
EXPECTED_FREEZE_SHA256 = "6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef"
EXPECTED_QUERY_IDS = ["36001915", "31703435"]
EXPECTED_QUERY_IDS_DIGEST = "7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969"
TOLERANCE = 1e-4
ROW_SUM_TOLERANCE = 1e-5
SETTINGS = {
    "package": "tabicl==2.2.0",
    "seed": 42,
    "fold": 0,
    "device": "cpu",
    "n_estimators": 8,
    "batch_size": 1,
    "n_jobs": 3,
    "fit_rows": 3144,
    "query_rows": 2,
    "feature_count": 312,
    "checkpoint_fit_calls": 1,
    "context_fit_calls": 1,
    "threads_environment": {"OMP_NUM_THREADS": "3", "MKL_NUM_THREADS": "3",
                            "OPENBLAS_NUM_THREADS": "3", "NUMEXPR_NUM_THREADS": "3"},
    "use_amp": False,
    "use_fa3": False,
    "model_path": "explicit pinned local checkpoint",
    "allow_auto_download": False,
    "checkpoint_version": "tabicl-classifier-v2-20260212.ckpt",
    "offload_mode": "auto",
    "disk_offload_dir": "round_010 pilot attempt directory/offload",
    "norm_methods": {"value": None, "origin": "TabICL 2.2.0 default; fit expands to none,power"},
    "feat_shuffle_method": {"value": "latin", "origin": "TabICL 2.2.0 constructor default"},
    "class_shuffle_method": {"value": "shift", "origin": "TabICL 2.2.0 constructor default"},
    "softmax_temperature": {"value": 0.9, "origin": "TabICL 2.2.0 constructor default"},
    "average_logits": {"value": True, "origin": "TabICL 2.2.0 constructor default"},
    "outlier_threshold": {"value": 4.0, "origin": "TabICL 2.2.0 constructor default"},
    "support_many_classes": {"value": True, "origin": "TabICL 2.2.0 constructor default"},
    "kv_cache": {"value": False, "origin": "TabICL 2.2.0 constructor default"},
    "verbose": {"value": False, "origin": "TabICL 2.2.0 constructor default"},
    "predict_proba_calls": 1,
    "row_chunk_rows": 8,
    "column_chunk_columns": 16,
    "f1_computations": 0,
    "inner_labels_used": False,
    "outer_inference": False,
    "weight_training": False,
    "hyperparameter_search": False,
}
SOURCE_AT_LAUNCH_SHA256 = None
SOURCE_AT_LAUNCH_UTC = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_digest(value) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def safe_digest(value) -> str:
    def convert(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, dict):
            return {str(k): convert(v) for k, v in sorted(obj.items(), key=lambda pair: str(pair[0]))}
        if isinstance(obj, (tuple, list)):
            return [convert(v) for v in obj]
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return repr(obj)
    return json_digest(convert(value))


def verify_inside_round(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROUND.resolve()):
        raise ValueError(f"{label} must be inside rounds/round_010")
    return resolved


def array_fingerprint(value: np.ndarray) -> dict:
    array = np.asarray(value)
    contiguous = np.ascontiguousarray(array)
    byte_view = contiguous.view(np.uint8).reshape(-1)
    digest = hashlib.sha256()
    for start in range(0, byte_view.size, 1024 * 1024):
        digest.update(memoryview(byte_view[start:start + 1024 * 1024]))
    return {"shape": list(array.shape), "dtype": str(array.dtype),
            "sha256_c_order_bytes": digest.hexdigest(), "c_contiguous_before_hash": bool(array.flags.c_contiguous)}


def input_fingerprints(fit_x: np.ndarray, fit_y: np.ndarray, query_x: np.ndarray) -> dict:
    return {"X_fit": array_fingerprint(fit_x), "y_fit": array_fingerprint(fit_y),
            "X_query": array_fingerprint(query_x)}


def runtime_manager_state(manager: object, expected_enc_name: str) -> dict:
    device_type = getattr(getattr(manager, "exe_device", None), "type", None)
    offload = getattr(manager, "offload_mode", None)
    state = {"enc_name": getattr(manager, "enc_name", None),
             "configured": getattr(manager, "_is_configured", False) is True,
             "device_type": device_type,
             "use_amp": getattr(manager, "use_amp", None),
             "use_fa3": getattr(manager, "use_fa3", None),
             "offload_mode": getattr(offload, "name", str(offload) if offload is not None else None)}
    if (state["enc_name"] != expected_enc_name or not state["configured"] or device_type != "cpu"
            or state["use_amp"] is not False or state["use_fa3"] is not False):
        raise RuntimeError(f"{expected_enc_name} manager is not resolved to configured CPU FP32: {state}")
    return state


def read_frozen_reference(path: Path, query_ids: list[str]) -> tuple[np.ndarray, str, dict]:
    """Read only the header and first two ordered INNER prediction rows; never scan/search later rows."""
    if len(query_ids) != 2:
        raise ValueError("exactly two frozen query IDs are required")
    with path.open("rb") as stream:
        lines = [stream.readline(), stream.readline(), stream.readline()]
    if any(not line for line in lines):
        raise ValueError("reference CSV has fewer than two data rows")
    required = ["rfid_id", "p0", "p1", "p2", "p3"]
    header = lines[0].decode("utf-8-sig").strip("\r\n").split(",")
    if header[:5] != required:
        raise ValueError("reference CSV lacks rfid_id or p0..p3 columns")
    selected_values = []
    for line in lines[1:]:
        first = line.rstrip(b"\r\n").split(b",", 4)
        if len(first) != 5:
            raise ValueError("reference CSV first five columns are not plain comma-delimited fields")
        p3 = first[4].split(b",", 1)[0]
        selected_values.append([cell.decode("utf-8-sig") for cell in first[:4]] + [p3.decode("utf-8-sig")])
    actual_ids = [row[0] for row in selected_values]
    if actual_ids != query_ids:
        raise ValueError("first two historical INNER rows do not equal the already-frozen query IDs; no search/reorder allowed")
    probabilities = np.asarray([[float(value) for value in row[1:5]] for row in selected_values], dtype=np.float64)
    selected = [{"rfid_id": actual_ids[i], "p0_p3": probabilities[i].tolist()} for i in range(2)]
    digest = json_digest(selected)
    evidence = {"source_path": str(path), "source_row_order": "first two data rows only; must equal frozen query ID order",
                "rows_read": 2, "fields_used": required, "labels_used": False,
                "label_fields_accessed": False, "source_row_bytes_may_contain_unparsed_other_columns": True,
                "selected_reference_probabilities_sha256": digest,
                "selected_reference_probability_rows": selected,
                "finite": bool(np.isfinite(probabilities).all()),
                "min_probability": float(probabilities.min()), "max_probability": float(probabilities.max()),
                "max_abs_row_sum_error": float(np.max(np.abs(probabilities.sum(axis=1) - 1.0)))}
    if (not np.isfinite(probabilities).all() or np.any(probabilities < 0.0) or np.any(probabilities > 1.0)
            or evidence["max_abs_row_sum_error"] > ROW_SUM_TOLERANCE):
        raise ValueError("selected historical probability rows fail finite/range/row-sum checks")
    return probabilities, digest, evidence


def actual_shuffle_state(model) -> dict:
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


def resolved_inference_state(model) -> dict:
    config = getattr(model, "inference_config_", None)
    stages = {}
    for key in ("COL_CONFIG", "ROW_CONFIG", "ICL_CONFIG"):
        stage = getattr(config, key, None) if config is not None else None
        if isinstance(stage, dict):
            source = stage
        elif stage is not None and callable(getattr(stage, "items", None)):
            source = dict(stage.items())
        else:
            source = None
        if source is not None:
            values = {name: source.get(name) for name in
                      ("device", "use_amp", "use_fa3", "offload", "disk_offload_dir", "verbose")}
            stages[key] = {name: value if isinstance(value, (str, int, float, bool)) or value is None else str(value)
                           for name, value in values.items()}
        else:
            stages[key] = repr(stage)
    return stages


def validate_resolved_inference_state(model) -> dict:
    stages = resolved_inference_state(model)
    if set(stages) != {"COL_CONFIG", "ROW_CONFIG", "ICL_CONFIG"}:
        raise RuntimeError("TabICL did not expose all three resolved inference stages")
    for name, config in stages.items():
        if not isinstance(config, dict):
            raise RuntimeError(f"resolved {name} configuration is not inspectable")
        if config.get("device") != "cpu" or config.get("use_amp") is not False or config.get("use_fa3") is not False:
            raise RuntimeError(f"resolved {name} device/AMP/FA3 differs from the fixed CPU FP32 contract")
    if stages["COL_CONFIG"].get("offload") != "auto":
        raise RuntimeError("resolved column offload mode is not 'auto'")
    if stages["ROW_CONFIG"].get("offload") is not False or stages["ICL_CONFIG"].get("offload") is not False:
        raise RuntimeError("resolved row/ICL offload modes differ from the TabICL 2.2.0 defaults")
    cache_mode_present = hasattr(model, "cache_mode_")
    cache_mode = getattr(model, "cache_mode_", None)
    model_kv_cache_present = hasattr(model, "model_kv_cache_")
    model_kv_cache = getattr(model, "model_kv_cache_", None)
    offload_mode = getattr(model, "offload_mode", None)
    kv_cache = getattr(model, "kv_cache", None)
    if (offload_mode != "auto" or kv_cache is not False or not model_kv_cache_present
            or model_kv_cache is not None or (cache_mode_present and cache_mode is not None)):
        raise RuntimeError("estimator offload/KV-cache settings differ from the fixed contract")
    stages["estimator_scope"] = {"offload_mode": offload_mode, "kv_cache": kv_cache,
                                 "model_kv_cache_present": model_kv_cache_present,
                                 "model_kv_cache_is_none": model_kv_cache is None,
                                 "cache_mode_present": cache_mode_present,
                                 "cache_mode": cache_mode}
    return stages


def execute(context_path: Path, freeze_path: Path, reference_path: Path, checkpoint_path: Path,
            output_path: Path, offload_dir: Path) -> dict:
    context_path = verify_inside_round(context_path, "context")
    freeze_path = verify_inside_round(freeze_path, "query freeze")
    output_path = verify_inside_round(output_path, "output")
    offload_dir = verify_inside_round(offload_dir, "offload directory")
    if checkpoint_path.resolve() != (ROOT / "model_cache" / "tabicl-classifier-v2-20260212.ckpt").resolve():
        raise ValueError("checkpoint path must be the pinned project-local checkpoint")
    if reference_path.resolve() != (P / "evaluation" / "seed_42" / "fold_0" / "inner_predictions.csv").resolve():
        raise ValueError("reference path differs from the approved seed42/fold0 INNER probability source")
    if not context_path.is_file() or not freeze_path.is_file() or not reference_path.is_file() or not checkpoint_path.is_file():
        raise FileNotFoundError("one or more approved pilot inputs are missing")

    source_path = Path(__file__).resolve()
    source_sha = SOURCE_AT_LAUNCH_SHA256 or sha_file(source_path)
    started_utc = SOURCE_AT_LAUNCH_UTC or utc_now()
    start_clock = time.perf_counter()
    contract_sha = sha_file(CONTRACT_PATH)
    if contract_sha != EXPECTED_CONTRACT_SHA256:
        raise ValueError("pinned runtime contract SHA-256 differs from the reviewed source")
    context_sha = sha_file(context_path)
    freeze_sha = sha_file(freeze_path)
    checkpoint_sha = sha_file(checkpoint_path)
    adapter_path = Path(__file__).resolve().parent / "column_chunk.py"
    adapter_sha = sha_file(adapter_path)
    if adapter_sha != ADAPTER_SHA256:
        raise ValueError("round007 column adapter SHA-256 differs from the reviewed chunk-16 source")
    row_adapter_path = Path(__file__).resolve().parent / "row_chunk.py"
    row_adapter_sha = sha_file(row_adapter_path)
    if row_adapter_sha != ROW_ADAPTER_SHA256:
        raise ValueError("round009 row adapter SHA-256 differs from the reviewed chunk-8 source")
    if context_sha != EXPECTED_CONTEXT_SHA256 or freeze_sha != EXPECTED_FREEZE_SHA256:
        raise ValueError("round010 copied context or query-freeze SHA-256 differs from the predeclared frozen input")
    if checkpoint_sha != CHECKPOINT_SHA256 or checkpoint_path.stat().st_size != CHECKPOINT_BYTES:
        raise ValueError("local checkpoint size/SHA256 does not match approved source")
    actual_settings = dict(SETTINGS)
    actual_settings["disk_offload_dir"] = str(offload_dir)
    settings_sha = json_digest(actual_settings)

    record = {
        "schema": "round010_inner_pilot_result.v1",
        "status": "STARTED",
        "stage": "verify_frozen_query_and_context",
        "started_utc": started_utc,
        "pid": os.getpid(),
        "source": {"path": str(source_path), "source_at_launch_sha256": source_sha,
                   "adapter_path": str(adapter_path), "adapter_sha256": adapter_sha,
                   "row_adapter_path": str(Path(__file__).resolve().parent / "row_chunk.py"),
                   "row_adapter_sha256": sha_file(Path(__file__).resolve().parent / "row_chunk.py"),
                   "icl_observer_path": str(Path(__file__).resolve().parent / "icl_observer.py"),
                   "icl_observer_sha256": sha_file(Path(__file__).resolve().parent / "icl_observer.py"),
                   "settings_sha256": settings_sha, "runtime_contract_sha256": contract_sha},
        "inputs": {"context_npz": {"path": str(context_path), "sha256": context_sha,
                                    "bytes": context_path.stat().st_size},
                    "query_freeze": {"path": str(freeze_path), "sha256": freeze_sha,
                                     "bytes": freeze_path.stat().st_size},
                    "checkpoint": {"path": str(checkpoint_path), "sha256": checkpoint_sha,
                                   "bytes": checkpoint_path.stat().st_size},
                    "reference_csv": {"path": str(reference_path),
                                      "selection": "only first two ordered rows after frozen query ID verification"}},
        "settings": actual_settings,
        "progress": [],
        "progress_journal": str(output_path.with_name("progress.jsonl")),
        "adapter_event_counts": {},
        "latest_adapter_event": None,
        "latest_row_chunk": None,
        "current_row_chunk": None,
        "last_completed_row_chunk": None,
        "icl_forward_attempted_count": 0,
        "icl_forward_completed_count": 0,
        "adapter_installed": False,
        "adapter_restored": False,
        "row_adapter_installed": False,
        "row_adapter_restored": False,
        "icl_observer_installed": False,
        "icl_observer_restored": False,
        "current_chunk": None,
        "last_completed_column_chunk": None,
        "probabilities": None,
        "comparison": None,
        "inner_labels_loaded_or_used": False,
        "f1_computed": False,
        "training_performed": False,
        "checkpoint_fit_invocation_count": 0,
        "checkpoint_fit_completed_count": 0,
        "context_fit_attempted_count": 0,
        "context_fit_completed_count": 0,
        "predict_proba_attempted_count": 0,
        "predict_proba_completed_count": 0,
    }

    def append_progress(event: dict) -> None:
        journal_path = Path(record["progress_journal"])
        if not journal_path.exists():
            with journal_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
            return
        with journal_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()

    def stage(name: str, **fields) -> None:
        if "source" in fields:
            raise ValueError("diagnostic field 'source' is reserved; use configure_source")
        record["stage"] = name
        record["current_stage"] = name
        record["progress"].append({"stage": name, "elapsed_seconds": time.perf_counter() - start_clock,
                                   "utc": utc_now()})
        record.update(fields)
        atomic_json(output_path, record)
        append_progress({"event": "stage", "stage": name,
                         "elapsed_seconds": record["progress"][-1]["elapsed_seconds"],
                         "utc": record["progress"][-1]["utc"]})
        print(json.dumps({"stage": name, "elapsed_seconds": record["progress"][-1]["elapsed_seconds"]}), flush=True)

    stage("inputs_hashed_and_query_freeze_ready")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if (freeze.get("schema") != "round005_frozen_inner_queries.v1" or freeze.get("fold") != 0
            or freeze.get("seed") != 42 or freeze.get("reference_probability_rows_read") != 0
            or freeze.get("context_npz_sha256") != context_sha):
        raise ValueError("query-freeze metadata does not bind the context or expected round scope")
    query_ids = freeze.get("query_ids")
    if query_ids != EXPECTED_QUERY_IDS or json_digest(query_ids) != EXPECTED_QUERY_IDS_DIGEST:
        raise ValueError("query IDs/digest differ from the fixed frozen order; do not search or reorder")
    if freeze.get("query_ids_digest_json_sha256") != EXPECTED_QUERY_IDS_DIGEST:
        raise ValueError("stored frozen query-ID digest differs from the fixed query digest")

    # Load only the FIT arrays, ordered INNER IDs and the first two INNER feature rows.
    # Deliberately do not access y_inner or any INNER label in the NPZ.
    with np.load(context_path, allow_pickle=False) as bundle:
        fit_x = bundle["X_fit"]
        fit_y = bundle["y_fit"].astype(np.int64, copy=False)
        inner_ids = bundle["ids_inner"].astype(str).tolist()
        query_x = bundle["X_inner"][:2]
        class_names = bundle["class_names"].astype(str).tolist()
        feature_names = bundle["feature_names"].astype(str).tolist()
    if (len(inner_ids) != 787 or inner_ids[:2] != EXPECTED_QUERY_IDS or fit_x.shape != (3144, 312)
            or query_x.shape != (2, 312) or fit_x.dtype != np.float32 or query_x.dtype != np.float32
            or fit_y.shape != (3144,) or np.any(fit_y < 0) or np.any(fit_y > 3)
            or class_names != ["연안복합", "자망", "통발", "채낚기연승낚시"]
            or len(feature_names) != 312 or not np.isfinite(fit_x).all() or not np.isfinite(query_x).all()):
        raise ValueError("context shape, dtype, class order, finite-value or frozen-query validation failed")
    stage("context_validated", fit_rows=int(fit_x.shape[0]), query_rows=int(query_x.shape[0]),
          fit_shape=list(fit_x.shape), query_shape=list(query_x.shape), feature_count=len(feature_names),
          fit_label_values=sorted(int(value) for value in np.unique(fit_y)),
          query_ids=query_ids, query_ids_digest_json_sha256=freeze["query_ids_digest_json_sha256"])

    # Only now open/read p0..p3 for the fixed IDs. The reader consumes the CSV header and first two rows only.
    reference_p, reference_sha, reference_evidence = read_frozen_reference(reference_path, query_ids)
    stage("fixed_reference_rows_verified", reference_evidence=reference_evidence,
          selected_reference_probabilities_sha256=reference_sha)

    if os.environ.get("OMP_NUM_THREADS") != "3" or os.environ.get("MKL_NUM_THREADS") != "3":
        raise ValueError("runner must provide fixed OMP_NUM_THREADS=3 and MKL_NUM_THREADS=3")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ["TABICL_PATH"] = str(checkpoint_path)
    os.environ["TABICL_CHECKPOINT"] = "tabicl-classifier-v2-20260212.ckpt"
    offload_dir.mkdir(parents=True, exist_ok=True)
    stage("package_import_pending")
    from importlib.metadata import version
    if version("tabicl") != "2.2.0":
        raise RuntimeError("installed TabICL package is not version 2.2.0")
    import torch
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    from tabicl import TabICLClassifier
    stage("package_imported", package_versions={"tabicl": version("tabicl"), "torch": torch.__version__,
                                                  "numpy": np.__version__},
          torch_threads={"intra_op": torch.get_num_threads(), "interop": torch.get_num_interop_threads()})

    estimator = TabICLClassifier(
        n_estimators=8,
        batch_size=1,
        model_path=str(checkpoint_path),
        allow_auto_download=False,
        checkpoint_version="tabicl-classifier-v2-20260212.ckpt",
        device="cpu",
        use_amp=False,
        use_fa3=False,
        offload_mode="auto",
        disk_offload_dir=str(offload_dir),
        random_state=42,
        n_jobs=3,
    )
    record["checkpoint_fit_invocation_count"] = 1
    record["context_fit_attempted_count"] = 1
    stage("checkpoint_fit_context_bind_start", checkpoint_fit_invocation_count=1,
          context_fit_attempted_count=1, weight_training_performed=False)
    estimator.fit(fit_x, fit_y)
    record["checkpoint_fit_completed_count"] = 1
    record["context_fit_completed_count"] = 1
    stage("fit_returned", fit_returned=True, fit_rows=int(fit_x.shape[0]),
          checkpoint_fit_completed_count=1, context_fit_completed_count=1)
    col_embedder = estimator.model_.col_embedder
    row_interactor = estimator.model_.row_interactor
    icl_predictor = estimator.model_.icl_predictor
    original_col_manager = col_embedder.inference_mgr
    original_row_manager = row_interactor.inference_mgr
    original_icl_manager = icl_predictor.inference_mgr
    col_config = estimator.inference_config_.COL_CONFIG
    row_config = estimator.inference_config_.ROW_CONFIG
    col_config_snapshot = {str(key): value if isinstance(value, (str, int, float, bool)) or value is None
                           else str(value) for key, value in col_config.items()}
    row_config_snapshot = {str(key): value if isinstance(value, (str, int, float, bool)) or value is None
                           else str(value) for key, value in row_config.items()}
    stage("configure_original_col_row_start",
          configure_targets=["estimator.model_.col_embedder.inference_mgr",
                             "estimator.model_.row_interactor.inference_mgr"],
          configure_source={"COL": "estimator.inference_config_.COL_CONFIG",
                            "ROW": "estimator.inference_config_.ROW_CONFIG"},
          exact_config={"COL": col_config_snapshot, "ROW": row_config_snapshot},
          adapters_installed=False)
    original_col_manager.configure(**col_config)
    original_row_manager.configure(**row_config)
    configured_col_state = runtime_manager_state(original_col_manager, "tf_col")
    configured_row_state = runtime_manager_state(original_row_manager, "tf_row")
    if configured_col_state["offload_mode"] != "AUTO":
        raise RuntimeError("configured column manager did not resolve offload='auto'")
    if configured_row_state["offload_mode"] != "GPU":
        raise RuntimeError("configured row manager did not resolve the pinned GPU offload enum")
    stage("original_col_row_configured_before_adapter_install",
          resolved_manager_states={"COL": configured_col_state, "ROW": configured_row_state},
          exact_config={"COL": col_config_snapshot, "ROW": row_config_snapshot},
          adapters_installed=False)
    device_value = str(getattr(estimator, "device_", "unknown"))
    if device_value != "cpu":
        raise RuntimeError(f"estimator resolved to unexpected device {device_value}")
    parameters = list(estimator.model_.parameters())
    buffers = list(estimator.model_.buffers())
    parameter_devices = sorted({str(parameter.device) for parameter in parameters})
    parameter_dtypes = sorted({str(parameter.dtype) for parameter in parameters})
    floating_parameter_dtypes = sorted({str(parameter.dtype) for parameter in parameters if parameter.dtype.is_floating_point})
    buffer_devices = sorted({str(buffer.device) for buffer in buffers})
    buffer_dtypes = sorted({str(buffer.dtype) for buffer in buffers})
    floating_buffer_dtypes = sorted({str(buffer.dtype) for buffer in buffers if buffer.dtype.is_floating_point})
    if parameter_devices != ["cpu"] or any(device != "cpu" for device in buffer_devices):
        raise RuntimeError("loaded checkpoint parameters are not all on CPU")
    if floating_parameter_dtypes != ["torch.float32"]:
        raise RuntimeError("loaded checkpoint floating parameters are not all FP32")
    if any(device != "cpu" for device in buffer_devices):
        raise RuntimeError("loaded checkpoint buffers are not all on CPU")
    if any(dtype != "torch.float32" for dtype in floating_buffer_dtypes):
        raise RuntimeError("loaded checkpoint floating buffers are not all FP32")
    resolved_settings = validate_resolved_inference_state(estimator)
    stage("checkpoint_fit_context_bind_complete", resolved_device=device_value,
          checkpoint_model_path=str(getattr(estimator, "model_path_", checkpoint_path)),
          model_input_shape=[int(estimator.n_samples_in_), int(estimator.n_features_in_)],
          class_order=[int(value) for value in estimator.classes_],
          parameter_devices=parameter_devices, parameter_dtypes=parameter_dtypes,
          floating_parameter_dtypes=floating_parameter_dtypes,
          buffer_devices=buffer_devices, buffer_dtypes=buffer_dtypes,
          floating_buffer_dtypes=floating_buffer_dtypes,
          resolved_inference_settings=resolved_settings,
          ensemble_shuffle_state=actual_shuffle_state(estimator))
    if list(estimator.classes_) != [0, 1, 2, 3]:
        raise RuntimeError("estimator class order is not canonical [0,1,2,3]")

    row_installation = None
    column_installation = None
    icl_observer_installation = None
    probabilities64 = None

    def adapter_event(kind: str, event: dict) -> None:
        event = dict(event)
        event["adapter"] = kind
        counts = record["adapter_event_counts"]
        event_name = str(event.get("event", "unknown"))
        counts[f"{kind}:{event_name}"] = counts.get(f"{kind}:{event_name}", 0) + 1
        record["latest_adapter_event"] = event
        if kind == "ROW" and event_name == "row_chunk_started":
            record["current_row_chunk"] = {key: event.get(key) for key in
                                             ("call_id", "chunk_index", "chunk_count", "row_start",
                                              "row_stop_exclusive", "input_shape")}
        elif kind == "ROW" and event_name == "row_chunk_completed":
            record["last_completed_row_chunk"] = {key: event.get(key) for key in
                                                    ("call_id", "chunk_index", "chunk_count", "row_start",
                                                     "row_stop_exclusive", "input_shape", "output_shape")}
            record["current_row_chunk"] = None
        elif kind == "COL" and event_name == "column_chunk_started":
            record["current_chunk"] = {key: event.get(key) for key in
                                         ("call_id", "chunk_index", "chunk_count", "column_start",
                                          "column_stop_exclusive", "feature_shape", "target_shape")}
        elif kind == "COL" and event_name == "column_chunk_completed":
            record["last_completed_column_chunk"] = {key: event.get(key) for key in
                                                       ("call_id", "chunk_index", "chunk_count", "column_start",
                                                        "column_stop_exclusive", "feature_shape", "target_shape",
                                                        "output_shape")}
            record["current_chunk"] = None
        append_progress({"event": "adapter_progress", **event})
        if kind == "ROW" and event_name == "row_chunk_call_started":
            stage("row_forward_enter", call_id=event.get("call_id"), input_shape=event.get("input_shape"),
                  row_count=event.get("row_count"), chunk_rows=CHUNK_ROWS,
                  feature_class_sequence_preserved=event.get("feature_class_sequence_preserved"),
                  embedding_width_preserved=event.get("embedding_width_preserved"))
        elif kind == "ROW" and event_name == "row_chunk_call_completed":
            stage("row_forward_complete", call_id=event.get("call_id"), output_shape=event.get("output_shape"),
                  chunk_count=event.get("chunk_count"),
                  feature_class_sequence_preserved=event.get("feature_class_sequence_preserved"),
                  embedding_width_preserved=event.get("embedding_width_preserved"))
        elif kind == "COL" and event_name == "column_chunk_call_started":
            stage("column_forward_enter", call_id=event.get("call_id"), input_shape=event.get("feature_shape"),
                  column_count=event.get("column_count"), chunk_columns=CHUNK_COLUMNS)
        elif kind == "COL" and event_name == "column_chunk_call_completed":
            stage("column_forward_complete", call_id=event.get("call_id"), output_shape=event.get("output_shape"),
                  chunk_count=event.get("chunk_count"))

    def on_icl_event(event: dict) -> None:
        event = dict(event)
        event["adapter"] = "ICL_OBSERVER"
        event_name = event.get("event")
        record["latest_adapter_event"] = event
        if event_name == "icl_forward_enter":
            record["icl_forward_attempted_count"] += 1
            expected_total_rows = SETTINGS["fit_rows"] + SETTINGS["query_rows"]
            context_check = verify_full_context(event.get("inputs", []), expected_total_rows,
                                                SETTINGS["fit_rows"])
            event.update(context_check)
            record["full_icl_context_verified"] = True
            record["icl_context_verified_call_count"] = record.get("icl_context_verified_call_count", 0) + 1
            append_progress({"event": "adapter_progress", **event})
            stage("icl_forward_enter", call_id=event.get("call_id"), inputs=event.get("inputs"),
                  expected_total_rows=expected_total_rows, expected_train_size=SETTINGS["fit_rows"],
                  full_context_preserved=True, context_truncated=False)
        elif event_name == "icl_forward_complete":
            if event.get("completed"):
                record["icl_forward_completed_count"] += 1
            append_progress({"event": "adapter_progress", **event})
            stage("icl_forward_complete", call_id=event.get("call_id"),
                  completed=event.get("completed"), output_shape=event.get("output_shape"),
                  error_type=event.get("error_type"), error=event.get("error"),
                  full_context_preserved=True, context_truncated=False)
        else:
            append_progress({"event": "adapter_progress", **event})

    try:
        stage("column_and_row_adapter_install_start", chunk_columns=CHUNK_COLUMNS,
              chunk_rows=CHUNK_ROWS, original_col_row_already_configured=True)
        column_installation = install_column_chunk_adapter(
            estimator, on_event=lambda event: adapter_event("COL", event))
        record["adapter_installed"] = True
        row_installation = install_row_chunk_adapter(
            estimator, on_event=lambda event: adapter_event("ROW", event))
        record["row_adapter_installed"] = True
        icl_observer_installation = install_icl_call_observer(estimator, on_icl_event)
        record["icl_observer_installed"] = True
        stage("column_and_row_adapters_installed", targets=[
                  "estimator.model_.col_embedder.inference_mgr",
                  "estimator.model_.row_interactor.inference_mgr"],
              column_adapter_type=type(column_installation.adapter).__name__,
              row_adapter_type=type(row_installation.adapter).__name__,
              icl_observer_type=type(icl_observer_installation.observer).__name__,
              icl_context_unchanged=True)

        pre_inputs = input_fingerprints(fit_x, fit_y, query_x)
        pre_shuffle = actual_shuffle_state(estimator)
        record["predict_proba_attempted_count"] = 1
        stage("predict_proba_start", predict_proba_attempted_count=1, predict_proba_completed_count=0,
              input_fingerprints_before_call=pre_inputs, ensemble_shuffle_state_before_call=pre_shuffle,
              column_adapter_installed=True, row_adapter_installed=True, icl_observer_installed=True)
        raw_output = estimator.predict_proba(query_x)
        record["predict_proba_completed_count"] = 1
        probabilities = np.asarray(raw_output)
        if probabilities.shape != (2, 4) or not np.isfinite(probabilities).all():
            raise ValueError("model output is not a finite 2x4 probability matrix")
        if np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
            raise ValueError("model output probability outside [0,1]")
        row_sum_error = float(np.max(np.abs(probabilities.sum(axis=1) - 1.0)))
        if row_sum_error > ROW_SUM_TOLERANCE:
            raise ValueError("model output row sums exceed the fixed tolerance")
        probabilities64 = np.asarray(probabilities, dtype=np.float64)
        model_prob_sha = sha_bytes(np.ascontiguousarray(probabilities64).tobytes(order="C"))
        record["probabilities"] = {"query_ids": query_ids, "class_order": [0, 1, 2, 3],
                                   "values": probabilities64.tolist(), "original_dtype": str(probabilities.dtype),
                                   "shape": list(probabilities.shape), "float64_c_order_sha256": model_prob_sha,
                                   "finite": True, "min": float(probabilities.min()), "max": float(probabilities.max()),
                                   "max_abs_row_sum_error": row_sum_error}
        if list(estimator.classes_) != [0, 1, 2, 3]:
            raise RuntimeError("model class order changed during prediction")
        gradients_present = any(parameter.grad is not None for parameter in estimator.model_.parameters())
        if gradients_present:
            raise RuntimeError("gradients are present after inference")
        post_inputs = input_fingerprints(fit_x, fit_y, query_x)
        post_shuffle = actual_shuffle_state(estimator)
        input_and_shuffle_unchanged = bool(post_inputs == pre_inputs and post_shuffle == pre_shuffle)
        record["input_fingerprints_after_call"] = post_inputs
        record["ensemble_shuffle_state_after_call"] = post_shuffle
        record["input_and_shuffle_state_unchanged"] = input_and_shuffle_unchanged
        if not input_and_shuffle_unchanged:
            raise RuntimeError("prediction mutated frozen input arrays or fitted ensemble shuffle state")
        current_col_manager = col_embedder.inference_mgr
        current_row_manager = row_interactor.inference_mgr
        current_icl_manager = icl_predictor.inference_mgr
        if (current_col_manager is not column_installation.adapter
                or current_row_manager is not row_installation.adapter
                or current_icl_manager is not icl_observer_installation.observer):
            raise RuntimeError("a wrapped inference manager identity changed during prediction")
        col_state_after = runtime_manager_state(original_col_manager, "tf_col")
        row_state_after = runtime_manager_state(original_row_manager, "tf_row")
        icl_state_after = runtime_manager_state(original_icl_manager, "tf_icl")
        if (col_state_after["offload_mode"] != "AUTO" or row_state_after["offload_mode"] != "GPU"
                or icl_state_after["offload_mode"] != "GPU"):
            raise RuntimeError("COL/ROW/ICL resolved offload state differs from the pinned CPU contract")
        record["runtime_managers_after_prediction"] = {
            "COL": col_state_after, "ROW": row_state_after, "ICL": icl_state_after,
            "column_adapter_identity_preserved": current_col_manager is column_installation.adapter,
            "row_adapter_identity_preserved": current_row_manager is row_installation.adapter,
            "icl_observer_identity_preserved": current_icl_manager is icl_observer_installation.observer,
        }
        row_chunk_started = record["adapter_event_counts"].get("ROW:row_chunk_started", 0)
        row_chunk_completed = record["adapter_event_counts"].get("ROW:row_chunk_completed", 0)
        row_call_count = record["adapter_event_counts"].get("ROW:row_chunk_call_completed", 0)
        column_chunk_started = record["adapter_event_counts"].get("COL:column_chunk_started", 0)
        column_chunk_completed = record["adapter_event_counts"].get("COL:column_chunk_completed", 0)
        column_call_count = record["adapter_event_counts"].get("COL:column_chunk_call_completed", 0)
        if (row_chunk_started < 1 or row_chunk_started != row_chunk_completed or row_call_count < 1
                or column_chunk_started < 1 or column_chunk_started != column_chunk_completed
                or column_call_count < 1):
            raise RuntimeError("prediction returned without complete column/row chunk event sequences")
        if row_installation.adapter.calls != row_call_count:
            raise RuntimeError("ROW adapter call-completion diagnostics disagree with adapter state")
        if icl_observer_installation.observer.calls != record["icl_forward_attempted_count"]:
            raise RuntimeError("ICL observer call-entry diagnostics disagree with observer state")
        if (record["icl_forward_attempted_count"] < 1
                or record["icl_forward_completed_count"] != record["icl_forward_attempted_count"]
                or record.get("icl_context_verified_call_count", 0) != record["icl_forward_attempted_count"]):
            raise RuntimeError("ICL call lifecycle or full-context verification is incomplete")
        record["chunk_progress_summary"] = {
            "column_call_count": column_call_count,
            "column_chunk_started_count": column_chunk_started,
            "column_chunk_completed_count": column_chunk_completed,
            "last_completed_column_chunk": record["last_completed_column_chunk"],
            "row_call_count": row_call_count,
            "row_chunk_started_count": row_chunk_started,
            "row_chunk_completed_count": row_chunk_completed,
            "last_completed_row_chunk": record["last_completed_row_chunk"],
            "icl_forward_attempted_count": record["icl_forward_attempted_count"],
            "icl_forward_completed_count": record["icl_forward_completed_count"],
            "full_context_preserved": True,
            "runtime_manager_states": record["runtime_managers_after_prediction"],
        }
        stage("predict_proba_complete", predict_proba_attempted_count=1, predict_proba_completed_count=1,
              gradients_present=gradients_present, input_fingerprints_after_call=post_inputs,
              ensemble_shuffle_state_after_call=post_shuffle,
              input_and_shuffle_state_unchanged=input_and_shuffle_unchanged,
              chunk_progress_summary=record["chunk_progress_summary"])
    finally:
        restoration_errors = []
        for label, installation, flag_installed, flag_restored in (
                ("ICL_OBSERVER", icl_observer_installation, "icl_observer_installed", "icl_observer_restored"),
                ("ROW", row_installation, "row_adapter_installed", "row_adapter_restored"),
                ("COL", column_installation, "adapter_installed", "adapter_restored")):
            if installation is None:
                continue
            try:
                installation.restore()
                record[flag_installed] = False
                record[flag_restored] = True
            except Exception as restore_exc:
                restoration_errors.append({"manager": label, "error": repr(restore_exc)})
        record["adapter_restoration_errors"] = restoration_errors
        record["all_managers_restored"] = not restoration_errors and all(
            record[key] for key in ("adapter_restored", "row_adapter_restored", "icl_observer_restored"))
        # All installed managers are restored before final restoration diagnostics are written.
        stage("managers_restored", all_managers_restored=record["all_managers_restored"],
              original_col_manager_reinstated=(col_embedder.inference_mgr is original_col_manager),
              original_row_manager_reinstated=(row_interactor.inference_mgr is original_row_manager),
              original_icl_manager_reinstated=(icl_predictor.inference_mgr is original_icl_manager),
              restoration_errors=restoration_errors)
        if restoration_errors:
            raise RuntimeError(f"manager restoration failed: {restoration_errors!r}")
        if not record["all_managers_restored"]:
            raise RuntimeError("one or more wrapped managers were not restored")

    difference = np.abs(probabilities64 - reference_p)
    max_difference = float(difference.max())
    argmax_equal = bool(np.array_equal(np.argmax(probabilities64, axis=1), np.argmax(reference_p, axis=1)))
    exact_numeric_equal = bool(np.array_equal(probabilities64, reference_p))
    within_tolerance = bool(max_difference <= TOLERANCE and argmax_equal)
    per_query = []
    for index, query_id in enumerate(query_ids):
        per_query.append({"query_id": query_id,
                          "max_abs_probability_difference": float(difference[index].max()),
                          "model_argmax": int(np.argmax(probabilities64[index])),
                          "reference_argmax": int(np.argmax(reference_p[index])),
                          "argmax_equal": bool(np.argmax(probabilities64[index]) == np.argmax(reference_p[index]))})
    record["comparison"] = {
        "scope": "only two frozen original INNER rows; four original saved raw p0..p3 columns; no decision score/weighting/F1",
        "reference_probability_sha256": reference_sha,
        "max_abs_probability_difference": max_difference,
        "absolute_tolerance": TOLERANCE,
        "per_query": per_query,
        "exact_numeric_equal_after_float64_parse": exact_numeric_equal,
        "within_1e_4_absolute_tolerance": max_difference <= TOLERANCE,
        "argmax_equal": argmax_equal,
        "small_replay_gate_pass": within_tolerance,
        "all_managers_restored": record.get("all_managers_restored", False),
        "full_icl_context_preserved": record.get("full_icl_context_verified", False),
        "input_and_shuffle_state_unchanged": record.get("input_and_shuffle_state_unchanged", False),
        "predict_proba_attempted_count": record["predict_proba_attempted_count"],
        "predict_proba_completed_count": record["predict_proba_completed_count"],
        "checkpoint_fit_invocation_count": record["checkpoint_fit_invocation_count"],
        "context_fit_attempted_count": record["context_fit_attempted_count"],
        "context_fit_completed_count": record["context_fit_completed_count"],
        "is_performance_or_F1_claim": False,
    }
    gate_pass = bool(within_tolerance and record.get("all_managers_restored", False)
                     and record.get("input_and_shuffle_state_unchanged", False)
                     and record["predict_proba_attempted_count"] == 1
                     and record["predict_proba_completed_count"] == 1
                     and record["checkpoint_fit_invocation_count"] == 1
                     and record["checkpoint_fit_completed_count"] == 1
                     and record["context_fit_attempted_count"] == 1
                     and record["context_fit_completed_count"] == 1
                     and record.get("full_icl_context_verified", False))
    record["status"] = "PILOT_COMPLETE" if gate_pass else "PILOT_GATE_FAILED"
    record["stage"] = "comparison_complete"
    record["finished_utc"] = utc_now()
    record["elapsed_seconds"] = time.perf_counter() - start_clock
    atomic_json(output_path, record)
    print(json.dumps({"status": record["status"], "max_abs_difference": max_difference,
                      "argmax_equal": argmax_equal, "small_replay_gate_pass": within_tolerance,
                      "elapsed_seconds": record["elapsed_seconds"]}, ensure_ascii=False), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path,
                        default=ROUND / "artifacts" / "context_export_attempt_001" / "fold0_seed42_context.npz")
    parser.add_argument("--query-freeze", type=Path,
                        default=ROUND / "artifacts" / "context_export_attempt_001" / "query_freeze.json")
    parser.add_argument("--reference", type=Path,
                        default=P / "evaluation" / "seed_42" / "fold_0" / "inner_predictions.csv")
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / "model_cache" / "tabicl-classifier-v2-20260212.ckpt")
    parser.add_argument("--output", type=Path,
                        default=ROUND / "artifacts" / "pilot_01" / "pilot_result.json")
    parser.add_argument("--offload-dir", type=Path,
                        default=ROUND / "artifacts" / "pilot_01" / "offload")
    args = parser.parse_args()
    output_path = verify_inside_round(args.output, "output")
    if output_path.exists() or output_path.with_name("progress.jsonl").exists():
        raise FileExistsError("pilot output or progress journal already exists; the one pilot cannot be repeated")
    source_path = Path(__file__).resolve()
    started_utc = SOURCE_AT_LAUNCH_UTC or utc_now()
    source_sha = SOURCE_AT_LAUNCH_SHA256 or sha_file(source_path)
    start = time.perf_counter()
    # Stage a recovery record before imports, checkpoint load, fit, or inference.
    initial = {"schema": "round010_inner_pilot_result.v1", "status": "STARTED", "stage": "process_entry",
               "started_utc": started_utc, "pid": os.getpid(), "source_at_launch_sha256": source_sha,
               "source_path": str(source_path), "predict_proba_attempted_count": 0,
               "predict_proba_completed_count": 0,
               "adapter_sha256": sha_file(Path(__file__).resolve().parent / "column_chunk.py"),
               "row_adapter_sha256": sha_file(Path(__file__).resolve().parent / "row_chunk.py"),
               "icl_observer_sha256": sha_file(Path(__file__).resolve().parent / "icl_observer.py"),
               "progress_journal": str(output_path.with_name("progress.jsonl")),
               "adapter_event_counts": {}, "latest_adapter_event": None,
               "checkpoint_fit_invocation_count": 0, "checkpoint_fit_completed_count": 0,
               "context_fit_attempted_count": 0, "context_fit_completed_count": 0,
               "adapter_installed": False, "adapter_restored": False,
               "row_adapter_installed": False, "row_adapter_restored": False,
               "icl_observer_installed": False, "icl_observer_restored": False,
               "current_stage": "process_entry", "current_chunk": None,
               "last_completed_column_chunk": None,
               "inner_labels_loaded_or_used": False, "f1_computed": False, "training_performed": False}
    atomic_json(output_path, initial)
    try:
        result = execute(args.context, args.query_freeze, args.reference, args.checkpoint,
                         output_path, args.offload_dir)
        return 0 if result["status"] == "PILOT_COMPLETE" else 1
    except Exception as exc:
        try:
            failure = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            failure = dict(initial)
        failure.update({"status": "FAILED", "stage": "exception",
                   "error_type": type(exc).__name__, "error": str(exc),
                   "traceback": traceback.format_exc(), "finished_utc": utc_now(),
                   "elapsed_seconds": time.perf_counter() - start})
        atomic_json(output_path, failure)
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)},
                         ensure_ascii=False), file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    SOURCE_AT_LAUNCH_SHA256 = sha_file(Path(__file__).resolve())
    SOURCE_AT_LAUNCH_UTC = utc_now()
    main()
