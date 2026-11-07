"""Round020: one frozen-model, missing-hour conditional timing experiment.

This module imports no legacy runner and contains no fitting path.  Accident
times are read only by the post-seal evaluation entry point.
"""
from __future__ import annotations

import os
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import statistics
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "testB/final/round_018_pointwise_loov_20261106"
FLEET = ROOT / "testB/final/round_017_fleet_negatives_20261106/execution_001"
TRUTH = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
FILES = tuple(FLEET / f"hourly_{i:02d}.parquet" for i in range(1, 7))
OLD_ARTIFACTS = (OLD / "PROTOCOL.md", OLD / "evaluate.py", OLD / "freeze.json",
                 OLD / "execution_001/fold_audit.jsonl", OLD / "execution_001/predictions.csv",
                 OLD / "execution_001/predictions_sealed.json")
FEATURES = ("len_m", "bbox_m", "n_coords")
COLUMNS = ("rfid_id", "ts", "source_ordinal", *FEATURES)
RESERVE_MIB = 640
ESTIMATE_MIB = 768
RETAIN_CAP_BYTES = 128 * 2**20
LOWER_HOUR = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() // 3600)
UPPER_HOUR = int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp() // 3600)
PARITY_ATOL = 1e-10
PREDICTION_ARTIFACTS = ("predictions.csv", "hourly_scores.csv", "hourly_max_provenance.csv",
                        "fold_reuse_audit.jsonl", "old_top_reconstruction.json")
SCORE_FIELDS = ("rfid_id", "candidate_ts", "support_share", "observed_at_center",
                "nearby_observed_hours", "nearby_weight_sum", "normalization_weight_sum",
                "evidence_status", "selected")
HOUR_FIELDS = ("rfid_id", "ts", "max_logit", "source_ordinal", "row_index_in_sorted_vessel", "weight")
PREDICTION_FIELDS = ("rfid_id", "pred_ts", "prediction_status", "selected_support_share",
                     "observed_at_center", "nearby_observed_hours", "n_rows",
                     "n_unique_observed_hours", "n_candidate_hours", "n_maximizing_candidates",
                     "maximizing_candidate_hours_json", "zero_support_candidate_hours",
                     "zero_nearby_observed_candidate_hours", "nearby_observed_but_zero_weight_candidate_hours",
                     "max_hour_logit", "normalization_weight_sum", "old_top_ts", "old_source_ordinal",
                     "old_peak_logit", "old_n_candidate_hours", "changed_from_old_top")


def now():
    return datetime.now().astimezone().isoformat()


def console(value):
    """ASCII JSON also works on Windows consoles with a legacy code page."""
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def file_entry(path):
    return {"sha256": digest(path), "bytes": Path(path).stat().st_size}


def memory_gate(stage, estimate_mib=ESTIMATE_MIB, basis=None, log=None):
    import psutil
    processes = []
    for process in psutil.process_iter(["name", "memory_info"]):
        try:
            processes.append({"pid": process.pid, "name": process.info["name"],
                              "rss_mib": round(process.info["memory_info"].rss / 2**20, 2)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            pass
    available = psutil.virtual_memory().available / 2**20
    record = {"stage": stage, "checked_at": now(), "available_mib": available,
              "estimated_peak_mib": estimate_mib, "reserve_mib": RESERVE_MIB,
              "estimate_basis": basis or ("Round018 measured about 209MiB; 32768-row batches, "
                  "128MiB retained-cohort cap, frozen small models, one-vessel score output; generous 768MiB"),
              "own_rss_mib": psutil.Process().memory_info().rss / 2**20,
              "top_running_processes": sorted(processes, key=lambda item: -item["rss_mib"])[:12],
              "python_processes": [item for item in processes if "python" in (item["name"] or "").lower()],
              "allowed": available >= estimate_mib + RESERVE_MIB}
    if log is not None:
        with Path(log).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    if not record["allowed"]:
        raise MemoryError(f"DEFERRED {stage}: {available:.1f} < {estimate_mib}+{RESERVE_MIB} MiB")
    return record


def frozen_paths():
    return (HERE / "PROTOCOL.md", HERE / "evaluate.py", HERE / "test_evaluate.py",
            *OLD_ARTIFACTS, TRUTH, *FILES)


def relative_key(path):
    return Path(path).relative_to(ROOT).as_posix()


def validate_paths():
    root = ROOT.resolve(strict=True)
    for path in frozen_paths():
        resolved = path.resolve(strict=True)
        expected = root / path.relative_to(ROOT)
        if not resolved.is_relative_to(root) or not resolved.is_file() or resolved != expected:
            raise ValueError(f"Input path is outside the exact authorized allowlist: {path.name}")


def normalized_manifest(files):
    if not isinstance(files, dict):
        raise ValueError("Manifest files must be a mapping")
    normalized = {}
    for key, value in files.items():
        canonical = str(key).replace("\\", "/")
        if canonical in normalized:
            raise ValueError("Duplicate normalized manifest path")
        normalized[canonical] = value
    return normalized


def check_entries(entries, paths):
    entries = normalized_manifest(entries)
    expected = {relative_key(path): path for path in paths}
    if set(entries) != set(expected):
        raise RuntimeError("Frozen manifest differs from exact input allowlist")
    actual = {}
    for key, path in expected.items():
        actual[key] = file_entry(path)
        if actual[key] != entries[key]:
            raise RuntimeError(f"Frozen hash or byte count changed: {key}")
    return actual


def verify_legacy_provenance():
    """Verify old code/protocol/sources and the old prediction seal, never metrics."""
    old_manifest = read_json(OLD / "freeze.json")
    old_inputs = (OLD / "PROTOCOL.md", OLD / "evaluate.py", TRUTH, *FILES)
    check_entries(old_manifest.get("files"), old_inputs)
    seal = read_json(OLD / "execution_001/predictions_sealed.json")
    if (seal.get("predictions") != 82 or seal.get("hit_metrics_evaluated") is not False
            or seal.get("sha256") != digest(OLD / "execution_001/predictions.csv")):
        raise RuntimeError("Round018 prediction seal failed")
    return {"checked_at": now(), "old_frozen_sources_match": True,
            "old_prediction_seal_matches": True, "old_prediction_sha256": seal["sha256"],
            "old_fold_audit_sha256": digest(OLD / "execution_001/fold_audit.jsonl"),
            "parity_absolute_logit_tolerance": PARITY_ATOL}


def check_frozen(record):
    validate_paths()
    if record.get("evaluation_count_authorized") != 1:
        raise RuntimeError("One-execution authorization missing")
    return check_entries(record.get("files"), frozen_paths())


def freeze():
    if (HERE / "freeze.json").exists() or (HERE / "execution_001").exists():
        raise RuntimeError("Freeze/execution already exists; no overwrites")
    gate = memory_gate("freeze", 128, "Sequential 1MiB hashes and small JSON; no scientific imports",
                       HERE / "memory_preflight.jsonl")
    validate_paths()
    lineage = verify_legacy_provenance()
    record = {"round": "Round020", "frozen_at": now(),
              "protocol": "frozen Round018 logits; inclusive +/-6h support share over full integer-hour grid v1",
              "evaluation_count_authorized": 1,
              "files": {relative_key(path): file_entry(path) for path in frozen_paths()},
              "legacy_provenance": lineage, "memory": gate,
              "baseline": {"hits": 3, "vessels": 82, "source": "user supplied fixed benchmark"},
              "new_training_authorized": False, "accident_times_read": False,
              "agents": [{"task": "/root/round020_design", "role": "astra_decision",
                          "requested_model": "gpt-6-astra", "requested_effort": "high"},
                         {"task": "/root/round020_boundary_review", "role": "sol_review",
                          "requested_model": "gpt-6.1-sol", "requested_effort": "high"},
                         {"task": "/root/round020_implementation", "role": "sol_complex",
                          "requested_model": "gpt-6.1-sol", "requested_effort": "max"}],
              "agent_evidence": "Parent reports spawn responses; provider internals not independently attested",
              "parent_model_changed": False}
    write_json(HERE / "freeze.json", record)
    console({"frozen_at": record["frozen_at"], "files": len(record["files"])})


def read_provided_ids(path=TRUTH, expected_vessels=82, expected_rows=100):
    """Read only the supplied grouping ID column; do not retain accident labels."""
    import pandas as pd
    frame = pd.read_csv(path, usecols=["rfid_id"], dtype={"rfid_id": str}, encoding="utf-8-sig",
                        keep_default_na=False)
    values = frame["rfid_id"].tolist()
    if len(values) != expected_rows or any(not value.strip() for value in values):
        raise ValueError("Provided-ID roster row contract failed")
    ids = set(values)
    if len(ids) != expected_vessels:
        raise ValueError("Provided-ID roster vessel cardinality failed")
    return ids


def finite_vector(value, length, name):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"Invalid frozen model {name} shape")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
           for item in value):
        raise ValueError(f"Invalid frozen model {name} values")
    return [float(item) for item in value]


def validate_model(fold, ids):
    if not isinstance(fold, dict):
        raise ValueError("Frozen fold must be a mapping")
    heldout = fold.get("heldout")
    training = fold.get("training_ids")
    if heldout not in ids or not isinstance(training, list) or any(not isinstance(key, str) for key in training):
        raise ValueError("Invalid frozen fold identity")
    if (len(training) != len(ids) - 1 or len(set(training)) != len(training)
            or set(training) != ids - {heldout} or fold.get("heldout_in_fit") is not False
            or fold.get("train_vessels") != len(ids) - 1 or fold.get("optimizer_success") is not True):
        raise ValueError("Frozen model training exclusion/provenance contract failed")
    center = finite_vector(fold.get("center"), 3, "center")
    scale = finite_vector(fold.get("scale"), 3, "scale")
    coefficients = finite_vector(fold.get("coefficients_intercept_first"), 10, "coefficients")
    if any(value <= 0 for value in scale):
        raise ValueError("Frozen model scale must be positive")
    return {"heldout": heldout, "training_ids": training[:], "center": center, "scale": scale,
            "coefficients_intercept_first": coefficients, "heldout_in_fit": False,
            "train_vessels": len(training), "optimizer_success": True}


def load_frozen_models(ids):
    models = {}
    with (OLD / "execution_001/fold_audit.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            model = validate_model(json.loads(line), ids)
            if model["heldout"] in models:
                raise ValueError("Duplicate frozen heldout model")
            models[model["heldout"]] = model
    if set(models) != ids:
        raise ValueError("Frozen model roster differs from all provided IDs")
    return models


def integer_field(value, name):
    try:
        result = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid integer {name}") from exc
    if str(result) != str(value).strip():
        raise ValueError(f"Noncanonical integer {name}")
    return result


def load_old_predictions(ids):
    predictions = {}
    with (OLD / "execution_001/predictions.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["rfid_id", "pred_ts", "source_ordinal", "peak_logit", "n_rows", "prediction_status"]:
            raise ValueError("Round018 prediction schema changed")
        for row in reader:
            key = row["rfid_id"]
            if key not in ids or key in predictions:
                raise ValueError("Invalid old prediction roster")
            count = integer_field(row["n_rows"], "old n_rows")
            if row["prediction_status"] == "predicted" and count > 0:
                guess = integer_field(row["pred_ts"], "old pred_ts")
                ordinal = integer_field(row["source_ordinal"], "old source_ordinal")
                logit = float(row["peak_logit"])
                if not math.isfinite(logit):
                    raise ValueError("Nonfinite old prediction logit")
            elif row["prediction_status"] == "no_candidates" and count == 0:
                if any(row[name] for name in ("pred_ts", "source_ordinal", "peak_logit")):
                    raise ValueError("Old missing prediction contains a fabricated value")
                guess, ordinal, logit = None, None, None
            else:
                raise ValueError("Old prediction status/count mismatch")
            predictions[key] = {"rfid_id": key, "pred_ts": guess, "source_ordinal": ordinal,
                                "peak_logit": logit, "n_rows": count,
                                "prediction_status": row["prediction_status"]}
    if set(predictions) != ids:
        raise ValueError("Old predictions omit provided IDs")
    return predictions


def load_cohort(ids, out):
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq
    frames, fleet_ids, file_counts = [], set(), {}
    kept_bytes = 0
    expected_types = {"rfid_id": "string", "ts": "int64", "source_ordinal": "int64",
                      "len_m": "double", "bbox_m": "double", "n_coords": "int64"}
    for path in FILES:
        total = 0
        parquet = pq.ParquetFile(path)
        if any(str(parquet.schema_arrow.field(name).type) != kind for name, kind in expected_types.items()):
            raise ValueError("Parquet key/geometry schema contract changed")
        for batch in parquet.iter_batches(batch_size=32768, columns=list(COLUMNS), use_threads=False):
            frame = batch.to_pandas()
            total += len(frame)
            if frame[list(COLUMNS)].isna().any().any():
                raise ValueError("Missing required geometry/key input; no rows may be discarded")
            if (frame["rfid_id"].str.len() == 0).any():
                raise ValueError("Empty supplied vessel ID")
            fleet_ids.update(frame.rfid_id.unique())
            geometry = frame[list(FEATURES)].to_numpy(dtype=float)
            if not np.isfinite(geometry).all() or (geometry < 0).any():
                raise ValueError("Nonfinite or negative geometry; no rows may be discarded")
            if not ((frame.ts >= LOWER_HOUR) & (frame.ts < UPPER_HOUR)).all():
                raise ValueError("Fleet time outside Jan-Jun 2026")
            if (frame.source_ordinal < 0).any():
                raise ValueError("Negative source ordinal")
            selected = frame.loc[frame.rfid_id.isin(ids), list(COLUMNS)].copy()
            if len(selected):
                kept_bytes += int(selected.memory_usage(deep=True).sum())
                if kept_bytes > RETAIN_CAP_BYTES:
                    raise MemoryError("DEFERRED retained-cohort cap 128MiB exceeded")
                frames.append(selected)
        if total != parquet.metadata.num_rows:
            raise ValueError("Parquet row-count mismatch")
        file_counts[path.name] = total
        console({"scanned": path.name, "rows": total, "retained_mib": kept_bytes / 2**20,
                 "hit_metrics_evaluated": False})
    if sum(file_counts.values()) != 3887065 or len(fleet_ids) != 7372:
        raise ValueError("Fleet cardinality differs from 3887065 rows / 7372 vessels")
    cohort = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(COLUMNS))
    groups = {}
    for key in sorted(ids):
        one = cohort.loc[cohort.rfid_id == key].sort_values(["ts", "source_ordinal"], kind="stable")
        groups[key] = {"ts": one.ts.to_numpy(dtype=np.int64),
                       "source_ordinal": one.source_ordinal.to_numpy(dtype=np.int64),
                       "log_geometry": np.log1p(one[list(FEATURES)].to_numpy(dtype=float))}
    array_bytes = sum(value.nbytes for group in groups.values() for value in group.values())
    if array_bytes > RETAIN_CAP_BYTES:
        raise MemoryError("DEFERRED retained-cohort arrays exceed 128MiB cap")
    audit = {"files": file_counts, "fleet_rows": sum(file_counts.values()), "fleet_vessels": len(fleet_ids),
             "provided_vessels": len(ids), "cohort_rows": len(cohort),
             "retained_dataframe_mib": kept_bytes / 2**20, "retained_array_mib": array_bytes / 2**20,
             "geometry_contract_passed": True, "batch_rows": 32768,
             "time_contract": "naive integer epoch hours; no timezone conversion",
             "model_features": list(FEATURES), "new_identity_mapping": False,
             "regional_prior_used": False, "new_training_performed": False,
             "accident_times_read": False, "noncohort_vessels_retained": False}
    write_json(out / "input_audit.json", audit)
    return groups, audit


def basis(log_values, center, scale):
    import numpy as np
    z = np.clip((log_values - np.asarray(center)) / np.asarray(scale), -5.0, 5.0)
    return np.column_stack([z, z * z, z[:, 0] * z[:, 1], z[:, 0] * z[:, 2], z[:, 1] * z[:, 2]])


def score_rows(group, model):
    import numpy as np
    coefficients = np.asarray(model["coefficients_intercept_first"], dtype=float)
    scores = coefficients[0] + basis(group["log_geometry"], model["center"], model["scale"]) @ coefficients[1:]
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite frozen-model row prediction")
    return scores


def reconstruct_old_top(key, group, scores, stored):
    import numpy as np
    if len(scores):
        index = int(np.lexsort((group["ts"], group["source_ordinal"], -scores))[0])
        reconstructed = {"rfid_id": key, "pred_ts": int(group["ts"][index]),
                         "source_ordinal": int(group["source_ordinal"][index]),
                         "peak_logit": float(scores[index]), "n_rows": len(scores),
                         "prediction_status": "predicted"}
    else:
        reconstructed = {"rfid_id": key, "pred_ts": None, "source_ordinal": None,
                         "peak_logit": None, "n_rows": 0, "prediction_status": "no_candidates"}
    for name in ("rfid_id", "pred_ts", "source_ordinal", "n_rows", "prediction_status"):
        if reconstructed[name] != stored[name]:
            raise RuntimeError(f"Round018 original-top reconstruction mismatch: {key}, {name}")
    difference = abs(reconstructed["peak_logit"] - stored["peak_logit"]) if len(scores) else 0.0
    if not math.isfinite(difference) or difference > PARITY_ATOL:
        raise RuntimeError(f"Round018 original-top logit parity failed: {key}")
    return {**reconstructed, "absolute_logit_difference": difference, "passed": True}


def aggregate_hours(ts, source_ordinal, scores):
    """One maximum per hour; exact row ties use the lowest supplied ordinal."""
    if not (len(ts) == len(source_ordinal) == len(scores)):
        raise ValueError("Row score/key length mismatch")
    selected = {}
    for index, (hour, ordinal, score) in enumerate(zip(ts, source_ordinal, scores)):
        if not math.isfinite(float(score)):
            raise ValueError("Nonfinite row logit")
        record = {"ts": int(hour), "source_ordinal": int(ordinal), "max_logit": float(score),
                  "row_index_in_sorted_vessel": index}
        previous = selected.get(record["ts"])
        if (previous is None or record["max_logit"] > previous["max_logit"]
                or (record["max_logit"] == previous["max_logit"]
                    and record["source_ordinal"] < previous["source_ordinal"])):
            selected[record["ts"]] = record
    return [selected[hour] for hour in sorted(selected)]


def select_timing(hours):
    """Label-free selector. Every numerator is a local ascending-time fsum."""
    if not hours:
        return {"pred_ts": None, "prediction_status": "no_candidates", "selected_support_share": None,
                "observed_at_center": None, "nearby_observed_hours": 0, "n_unique_observed_hours": 0,
                "n_candidate_hours": 0, "n_maximizing_candidates": 0,
                "maximizing_candidate_hours_json": "[]", "zero_support_candidate_hours": 0,
                "zero_nearby_observed_candidate_hours": 0,
                "nearby_observed_but_zero_weight_candidate_hours": 0,
                "max_hour_logit": None, "normalization_weight_sum": None}, [], []
    timestamps = [record["ts"] for record in hours]
    if timestamps != sorted(set(timestamps)) or any(type(hour) is not int for hour in timestamps):
        raise ValueError("Hourly logits must have unique, sorted integer timestamps")
    logits = [float(record["max_logit"]) for record in hours]
    if not all(math.isfinite(value) for value in logits):
        raise ValueError("Nonfinite hourly logit")
    max_logit = max(logits)
    weights = [math.exp(value - max_logit) for value in logits]
    normalizer = math.fsum(weights)
    if not math.isfinite(normalizer) or normalizer <= 0:
        raise ValueError("Invalid stable exponential normalizer")
    observed = set(timestamps)
    rows, maximizers = [], []
    left = right = 0
    maximum = -1.0
    for candidate in range(timestamps[0], timestamps[-1] + 1):
        while left < len(timestamps) and timestamps[left] < candidate - 6:
            left += 1
        while right < len(timestamps) and timestamps[right] <= candidate + 6:
            right += 1
        count = right - left
        if not 0 <= count <= 13:
            raise ValueError("Local window exceeds thirteen unique integer hours")
        local_weight = math.fsum(weights[left:right])
        share = local_weight / normalizer
        rows.append({"candidate_ts": candidate, "support_share": share,
                     "observed_at_center": candidate in observed, "nearby_observed_hours": count,
                     "nearby_weight_sum": local_weight, "normalization_weight_sum": normalizer,
                     "evidence_status": "model_support" if share > 0 else "no_evidence", "selected": False})
        if share > maximum:
            maximum, maximizers = share, [candidate]
        elif share == maximum:
            maximizers.append(candidate)
    chosen = maximizers[(len(maximizers) - 1) // 2]
    chosen_row = rows[chosen - timestamps[0]]
    chosen_row["selected"] = True
    result = {"pred_ts": chosen, "prediction_status": "predicted",
              "selected_support_share": maximum, "observed_at_center": chosen_row["observed_at_center"],
              "nearby_observed_hours": chosen_row["nearby_observed_hours"],
              "n_unique_observed_hours": len(hours), "n_candidate_hours": len(rows),
              "n_maximizing_candidates": len(maximizers),
              "maximizing_candidate_hours_json": json.dumps(maximizers, separators=(",", ":")),
              "zero_support_candidate_hours": sum(row["support_share"] == 0 for row in rows),
              "zero_nearby_observed_candidate_hours": sum(row["nearby_observed_hours"] == 0 for row in rows),
              "nearby_observed_but_zero_weight_candidate_hours": sum(
                  row["nearby_observed_hours"] > 0 and row["support_share"] == 0 for row in rows),
              "max_hour_logit": max_logit, "normalization_weight_sum": normalizer}
    provenance = [{**record, "weight": weight} for record, weight in zip(hours, weights)]
    return result, rows, provenance


def predict_vessel(key, group, model, old_prediction):
    if model["heldout"] != key or key in model["training_ids"]:
        raise ValueError("Heldout model lookup failed")
    scores = score_rows(group, model)
    old_audit = reconstruct_old_top(key, group, scores, old_prediction)
    hours = aggregate_hours(group["ts"], group["source_ordinal"], scores)
    selected, rows, provenance = select_timing(hours)
    prediction = {"rfid_id": key, **selected, "n_rows": len(scores),
                  "old_top_ts": old_audit["pred_ts"], "old_source_ordinal": old_audit["source_ordinal"],
                  "old_peak_logit": old_audit["peak_logit"], "old_n_candidate_hours": len(hours),
                  "changed_from_old_top": selected["pred_ts"] != old_audit["pred_ts"]}
    return prediction, rows, provenance, old_audit


def csv_writer(handle, fields):
    writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    return writer


def seal_predictions(out, predictions):
    if len(predictions) != 82 or len({row["rfid_id"] for row in predictions}) != 82:
        raise ValueError("All 82 predictions must be persisted before sealing")
    artifacts = {name: file_entry(out / name) for name in PREDICTION_ARTIFACTS}
    seal = {"saved_at": now(), "predictions": 82, "hit_metrics_evaluated": False,
            "accident_times_read": False, "sha256": artifacts["predictions.csv"]["sha256"],
            "artifacts": artifacts, "score_semantics": "relative model support share; not calibrated accident probability"}
    write_json(out / "predictions_sealed.json", seal)
    return seal


def verify_prediction_seal(out):
    seal = read_json(out / "predictions_sealed.json")
    if (seal.get("predictions") != 82 or seal.get("hit_metrics_evaluated") is not False
            or seal.get("accident_times_read") is not False
            or set(seal.get("artifacts", {})) != set(PREDICTION_ARTIFACTS)):
        raise RuntimeError("Round020 prediction seal contract failed")
    for name, entry in seal["artifacts"].items():
        if file_entry(out / name) != entry:
            raise RuntimeError(f"Sealed prediction artifact changed: {name}")
    if seal.get("sha256") != seal["artifacts"]["predictions.csv"]["sha256"]:
        raise RuntimeError("Prediction SHA differs within seal")
    return seal


def window_mask(ts, accidents):
    return [any(abs(int(hour) - int(accident)) <= 6 for accident in accidents) for hour in ts]


def candidate_chance(first, last, accidents):
    """Uniform full candidate grid, with all event windows unioned exactly."""
    if first is None or last is None:
        return 0, 0, 0.0
    if type(first) is not int or type(last) is not int or first > last:
        raise ValueError("Invalid candidate-grid endpoints")
    intervals = sorted((max(first, int(accident) - 6), min(last, int(accident) + 6)) for accident in accidents)
    merged = []
    for left, right in intervals:
        if left > right:
            continue
        if merged and left <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    eligible = sum(right - left + 1 for left, right in merged)
    count = last - first + 1
    return eligible, count, eligible / count


def worst_overlap(hits, baseline=3, n=82):
    if type(hits) is not int or not 0 <= hits <= n or not 0 <= baseline <= n:
        raise ValueError("Invalid hit cardinality")
    cases = []
    for overlap in range(max(0, hits + baseline - n), min(hits, baseline) + 1):
        gains, losses = hits - overlap, baseline - overlap
        discordant = gains + losses
        probability = (math.fsum(math.comb(discordant, k) for k in range(gains, discordant + 1))
                       / 2**discordant) if discordant else 1.0
        cases.append({"overlap": overlap, "gains": gains, "losses": losses, "one_sided_p": probability})
    return {"worst_one_sided_p": max(case["one_sided_p"] for case in cases), "possible_overlaps": cases}


def poisson_binomial(probabilities, hits):
    values = list(probabilities)
    if type(hits) is not int or not 0 <= hits <= len(values):
        raise ValueError("Invalid Poisson-binomial hit count")
    pmf = [1.0]
    for probability in values:
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Invalid chance probability")
        previous = pmf
        pmf = [math.fsum(((previous[k] * (1 - probability)) if k < len(previous) else 0.0,
                          (previous[k - 1] * probability) if k > 0 else 0.0))
               for k in range(len(previous) + 1)]
    return min(1.0, max(0.0, math.fsum(pmf[hits:]))), pmf


def classify_result(hits, expected_rate, denominator=82):
    """User-authorized screening criteria; p-values are descriptive only."""
    if type(hits) is not int or not 0 <= hits <= denominator or denominator <= 0:
        raise ValueError("Invalid decision hit cardinality")
    if not math.isfinite(expected_rate) or not 0 <= expected_rate <= 1:
        raise ValueError("Invalid decision chance rate")
    above_chance = hits / denominator > expected_rate
    if above_chance and hits >= 5:
        decision, label = "개선 후보", "improvement_candidate"
    elif above_chance and hits == 4:
        decision, label = "보류", "hold"
    else:
        decision, label = "기각", "rejected"
    return {"decision": decision, "decision_label": label,
            "improvement_candidate": label == "improvement_candidate",
            "above_full_grid_chance": above_chance,
            "statistical_significance_required_for_decision": False,
            "confirmed_statistical_improvement": False}


def read_events(ids):
    """Called only after verify_prediction_seal has passed."""
    events, event_ids = [], set()
    with TRUTH.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["rfid_id"] not in ids or not row["acc_id"] or row["acc_id"] in event_ids:
                raise ValueError("Truth event identity contract failed")
            accident = integer_field(row["acc_ts"], "acc_ts")
            if not LOWER_HOUR <= accident < UPPER_HOUR:
                raise ValueError("Truth event outside Jan-Jun 2026")
            event_ids.add(row["acc_id"])
            events.append({"acc_id": row["acc_id"], "rfid_id": row["rfid_id"],
                           "tier": row["tier"], "acc_ts": accident})
    if len(events) != 100 or {row["rfid_id"] for row in events} != ids:
        raise ValueError("Truth cardinality differs from 100 events / 82 vessels")
    return events


def evaluate_predictions(out, ids, groups, predictions):
    seal = verify_prediction_seal(out)
    events = read_events(ids)
    pred = {row["rfid_id"]: row for row in predictions}
    if len(predictions) != 82 or set(pred) != ids or set(groups) != ids:
        raise ValueError("Evaluation must preserve all 82 provided vessels")
    by_vessel = {key: [] for key in ids}
    for event in events:
        by_vessel[event["rfid_id"]].append(event)
    vessels, event_rows = [], []
    for key in sorted(ids):
        prediction = pred[key]
        accidents = [event["acc_ts"] for event in by_vessel[key]]
        guess = prediction["pred_ts"]
        error = min(abs(guess - accident) for accident in accidents) if guess is not None else math.inf
        ts = groups[key]["ts"]
        first, last = (int(ts[0]), int(ts[-1])) if len(ts) else (None, None)
        eligible, count, probability = candidate_chance(first, last, accidents)
        if count != prediction["n_candidate_hours"]:
            raise RuntimeError("Evaluated candidate space differs from sealed selector grid")
        vessel = {**prediction, "n_events": len(accidents), "eligible_candidate_hours": eligible,
                  "chance_full_grid": probability, "min_abs_error_h": error if math.isfinite(error) else None,
                  "error_is_infinite": not math.isfinite(error), "hit_pm6h": error <= 6}
        vessels.append(vessel)
        for event in by_vessel[key]:
            event_error = abs(guess - event["acc_ts"]) if guess is not None else math.inf
            event_rows.append({**event, "pred_ts": guess,
                               "abs_error_h": event_error if math.isfinite(event_error) else None,
                               "error_is_infinite": not math.isfinite(event_error),
                               "event_hit_pm6h": event_error <= 6,
                               "vessel_min_abs_error_h": vessel["min_abs_error_h"],
                               "vessel_error_is_infinite": vessel["error_is_infinite"],
                               "vessel_hit_pm6h": vessel["hit_pm6h"], "vessel_n_events": len(accidents),
                               "prediction_status": prediction["prediction_status"]})
    if len(vessels) != 82 or len(event_rows) != 100:
        raise RuntimeError("Post-seal evaluation output cardinality failed")
    return vessels, event_rows, seal


def write_csv(path, rows):
    if not rows:
        raise ValueError("Cannot infer empty output schema")
    with Path(path).open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv_writer(handle, rows[0].keys())
        writer.writerows(rows)


def run():
    out = HERE / "execution_001"
    if out.exists():
        raise RuntimeError("execution_001 exists; no rerun or overwrite is allowed")
    # Admission precedes mkdir and all scientific imports / data loading.
    admission = memory_gate("admission", log=HERE / "memory_preflight.jsonl")
    frozen = read_json(HERE / "freeze.json")
    before = check_frozen(frozen)
    lineage = verify_legacy_provenance()
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    write_json(out / "started.json", {"started_at": now(), "frozen_at": frozen["frozen_at"],
                                      "admission_memory": admission, "evaluation_count": 1,
                                      "input_hashes_before": before, "legacy_provenance": lineage,
                                      "new_training_performed": False, "accident_times_read": False})
    try:
        memory_gate("imports_and_load", log=out / "memory_gates.jsonl")
        import numpy as np
        import pandas as pd
        import pyarrow
        import psutil
        ids = read_provided_ids()
        models = load_frozen_models(ids)
        old_predictions = load_old_predictions(ids)
        groups, input_audit = load_cohort(ids, out)
        memory_gate("prediction", log=out / "memory_gates.jsonl")
        predictions, reconstruction = [], []
        with (out / "hourly_scores.csv").open("x", encoding="utf-8-sig", newline="") as score_file, \
                (out / "hourly_max_provenance.csv").open("x", encoding="utf-8-sig", newline="") as hour_file, \
                (out / "fold_reuse_audit.jsonl").open("x", encoding="utf-8") as model_file:
            score_writer = csv_writer(score_file, SCORE_FIELDS)
            hour_writer = csv_writer(hour_file, HOUR_FIELDS)
            for index, key in enumerate(sorted(ids), 1):
                prediction, rows, provenance, old_audit = predict_vessel(
                    key, groups[key], models[key], old_predictions[key])
                predictions.append(prediction)
                reconstruction.append(old_audit)
                score_writer.writerows({"rfid_id": key, **row} for row in rows)
                hour_writer.writerows({"rfid_id": key, **row} for row in provenance)
                model_file.write(json.dumps({**models[key], "source_fold_audit_sha256": lineage["old_fold_audit_sha256"],
                    "model_refitted": False, "old_top_verified": True}, ensure_ascii=False, allow_nan=False) + "\n")
                if index % 10 == 0 or index == 82:
                    console({"predicted_vessels": index, "total": 82, "hit_metrics_evaluated": False})
        write_json(out / "old_top_reconstruction.json", {"checked_at": now(), "vessels": len(reconstruction),
            "absolute_logit_tolerance": PARITY_ATOL, "all_passed": True,
            "max_absolute_logit_difference": max(row["absolute_logit_difference"] for row in reconstruction),
            "records": reconstruction, "purpose": "integrity only; no old hit metrics recomputed"})
        with (out / "predictions.csv").open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv_writer(handle, PREDICTION_FIELDS)
            writer.writerows(predictions)
        seal_predictions(out, predictions)
        # No new hit metric or accident timestamp has been used above this line.
        vessels, events, seal = evaluate_predictions(out, ids, groups, predictions)
        write_csv(out / "vessel_results.csv", vessels)
        write_csv(out / "event_results.csv", events)
        hits = sum(row["hit_pm6h"] for row in vessels)
        probabilities = [row["chance_full_grid"] for row in vessels]
        chance_p, pmf = poisson_binomial(probabilities, hits)
        comparison = worst_overlap(hits)
        errors = [math.inf if row["error_is_infinite"] else row["min_abs_error_h"] for row in vessels]
        median = statistics.median(errors)
        after = check_frozen(frozen)
        verify_legacy_provenance()
        verify_prediction_seal(out)
        write_json(out / "integrity.json", {"checked_at": now(), "all_frozen_hashes_match": before == after,
            "input_hashes_before": before, "input_hashes_after": after,
            "sealed_prediction_artifacts_match": True, "old_top_reconstruction_passed": True,
            "legacy_source_and_prediction_seal_match": True, "prediction_sha256": seal["sha256"]})
        decision = classify_result(hits, math.fsum(probabilities) / 82)
        memory = psutil.Process().memory_info()
        old_counts = {row["rfid_id"]: row["old_n_candidate_hours"] for row in predictions}
        new_counts = {row["rfid_id"]: row["n_candidate_hours"] for row in predictions}
        summary = {"round": "Round020", "status": "complete", **decision,
            "evaluation_count": 1, "frozen_at": frozen["frozen_at"],
            "predictions_saved_at": seal["saved_at"], "completed_at": now(),
            "metric": "conditional vessel timing top-1 within inclusive +/-6h; not official F1",
            "score_semantics": "relative model support share; not calibrated accident probability",
            "decision_reasons": {"hits_at_least_5": hits >= 5, "hits_equal_4": hits == 4,
                "above_full_grid_chance": decision["above_full_grid_chance"],
                "p_values_report_only": True,
                "contracts_lineage_parity_and_hashes_passed": True},
            "primary": {"hits": hits, "denominator": 82, "rate": hits / 82,
                "baseline_hits": 3, "baseline_rate": 3 / 82, "delta_rate": (hits - 3) / 82,
                "median_abs_error_h": median if math.isfinite(median) else None,
                "median_error_is_infinite": not math.isfinite(median),
                "missing_predictions": sum(row["pred_ts"] is None for row in predictions)},
            "events_secondary": {"hits": sum(row["event_hit_pm6h"] for row in events), "denominator": 100,
                                  "not_primary_denominator": True},
            "chance": {"null": "uniform full integer-hour candidate grid; union of all vessel event windows",
                       "expected_hits": math.fsum(probabilities), "expected_rate": math.fsum(probabilities) / 82,
                       "one_sided_p": chance_p, "pmf": pmf},
            "baseline_comparison": comparison,
            "diagnostics": {"new_unobserved_predictions": sum(row["pred_ts"] is not None and not row["observed_at_center"]
                                                               for row in predictions),
                "selected_zero_support_count": sum(row["selected_support_share"] == 0 for row in predictions),
                "zero_support_candidate_hours": sum(row["zero_support_candidate_hours"] for row in predictions),
                "zero_nearby_observed_candidate_hours": sum(row["zero_nearby_observed_candidate_hours"] for row in predictions),
                "nearby_observed_but_zero_weight_candidate_hours": sum(
                    row["nearby_observed_but_zero_weight_candidate_hours"] for row in predictions),
                "changed_from_old_top": sum(row["changed_from_old_top"] for row in predictions),
                "old_observed_candidate_counts": old_counts, "new_grid_candidate_counts": new_counts,
                "total_old_observed_candidate_hours": sum(old_counts.values()),
                "total_new_grid_candidate_hours": sum(new_counts.values()),
                "median_old_observed_candidate_hours": statistics.median(old_counts.values()),
                "median_new_grid_candidate_hours": statistics.median(new_counts.values()),
                "oracle_support_vessels": sum(row["eligible_candidate_hours"] > 0 for row in vessels)},
            "input": {**input_audit, "truth_events": 100, "truth_vessels": 82,
                      "multi_accident_vessels": sum(row["n_events"] > 1 for row in vessels)},
            "models": {"source": relative_key(OLD / "execution_001/fold_audit.jsonl"),
                       "frozen_models": 82, "all_training_ids_exact_other_81": True,
                       "new_training_performed": False, "old_top_reconstruction_passed": True},
            "limitations": ["Reused provisional development labels and overlapping LOOV fits; nominal p-values only",
                            "Conditional timing on provided vessels, not a joint accident classifier",
                            "Whole-period retrospective input, not real-time performance",
                            "Support aggregation is sensitive to observation density and is not a latent accident probability"],
            "elapsed_seconds": time.perf_counter() - started,
            "peak_process_mib": getattr(memory, "peak_wset", memory.rss) / 2**20,
            "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                         "pyarrow": pyarrow.__version__, "psutil": psutil.__version__}}
        write_json(out / "summary.json", summary)
        console({"decision": summary["decision"], "hits": hits, "denominator": 82,
                 "median_error_h": summary["primary"]["median_abs_error_h"],
                 "chance_expected_hits": summary["chance"]["expected_hits"],
                 "baseline_worst_p": comparison["worst_one_sided_p"], "chance_p": chance_p})
    except Exception as exc:
        write_json(out / "failure.json", {"at": now(), "status": "deferred" if isinstance(exc, MemoryError) else "invalid",
            "type": type(exc).__name__, "message": str(exc), "retuning_allowed": False,
            "partial_outputs_preserved": True, "evaluation_complete": False})
        raise


def selftest():
    result_path = HERE / "synthetic_checks.json"
    if result_path.exists():
        raise RuntimeError("synthetic_checks.json exists; no overwrite")
    gate = memory_gate("synthetic_checks", 384, "Small synthetic arrays and scientific library imports; no real inputs",
                       HERE / "memory_preflight.jsonl")
    import importlib.util
    # Use this module object even when this file is invoked as __main__.
    name = "round020_evaluate_under_test"
    sys.modules[name] = sys.modules[__name__]
    specification = importlib.util.spec_from_file_location("round020_synthetic_tests", HERE / "test_evaluate.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    stream = io.StringIO()
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    record = {"checked_at": now(), "kind": "synthetic code tests only; no actual-data prediction or evaluation",
              "tests_run": result.testsRun, "passed": result.wasSuccessful(), "failures": len(result.failures),
              "errors": len(result.errors), "output": stream.getvalue(), "memory": gate,
              "elapsed_seconds": time.perf_counter() - started,
              "code_sha256": digest(HERE / "evaluate.py"), "tests_sha256": digest(HERE / "test_evaluate.py")}
    write_json(result_path, record)
    console({"synthetic_tests_run": result.testsRun, "passed": result.wasSuccessful(), "result": result_path.name})
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--selftest", action="store_true")
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--run", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.selftest:
            selftest()
        elif arguments.freeze:
            freeze()
        else:
            run()
    except Exception as error:
        console({"status": "deferred" if isinstance(error, MemoryError) else "invalid",
                 "error_type": type(error).__name__, "message": str(error)})
        raise SystemExit(2)
