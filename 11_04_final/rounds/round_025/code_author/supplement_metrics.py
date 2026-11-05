"""Read-only paired diagnostics for a completed 4-fold FIT gate.

The script intentionally reads only row_index/y_true/y_pred from gate
prediction archives and rfid_ids/roles/obs_days from the original fold0 NPZ.
It never loads the fold0 feature matrix or labels, trains a model, or emits IDs.
Run only after the manager reports a completed eight-fit gate, the independent
saved-result checker passes, and the manager approves analysis. The hash scope
is limited to the fold0 NPZ bytes and ordered FIT ID sequence; this script does
not claim full source/code/cache/checker verification. Output is
supplemental_metrics.json under the supplied gate dir.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FOLD0_NPZ = Path(
    r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_0_features.npz"
)
CLASS_NAMES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
OBSERVATION_BINS = (("1-7", 1.0, 7.0), ("8-30", 8.0, 30.0),
                    ("31-90", 31.0, 90.0), ("91+", 91.0, float("inf")))
BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_SEED = 20261105
MINIMUM_AVAILABLE_BYTES = 1 * 2**30
EXPECTED_PEAK_BYTES = 128 * 2**20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_ordered_ids(ids: list[str]) -> str:
    digest = hashlib.sha256()
    for value in ids:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def require_workspace_path(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"{label} must be inside the project workspace") from exc
    return resolved


def load_gate_variant(gate_dir: Path, variant: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = gate_dir / f"predictions_{variant}.npz"
    with np.load(path, allow_pickle=False) as archive:
        required = {"row_index", "y_true", "y_pred"}
        if not required.issubset(archive.files):
            raise ValueError(f"{variant} prediction archive lacks required arrays")
        row_index = np.asarray(archive["row_index"], dtype=np.int64)
        y_true = np.asarray(archive["y_true"], dtype=np.int64)
        y_pred = np.asarray(archive["y_pred"], dtype=np.int64)
    if row_index.shape != (3144,) or not np.array_equal(row_index, np.arange(3144)):
        raise ValueError(f"{variant} row order is not the frozen FIT roster order")
    if y_true.shape != (3144,) or y_pred.shape != (3144,):
        raise ValueError(f"{variant} prediction dimensions differ from the 3,144-row FIT gate")
    if np.any((y_true < 0) | (y_true > 3)) or np.any((y_pred < 0) | (y_pred > 3)):
        raise ValueError(f"{variant} labels or predictions fall outside the frozen four classes")
    return row_index, y_true, y_pred


def metric_summary(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    if len(y_true) == 0:
        return {"n": 0, "correct": 0, "micro_f1": None, "confusion": [[0] * 4 for _ in range(4)],
                "classes": [{"class_id": c, "class_name": CLASS_NAMES[c], "support": 0,
                             "tp": 0, "fp": 0, "fn": 0, "precision": None,
                             "recall": None, "f1": None} for c in range(4)]}
    confusion = np.bincount(y_true * 4 + y_pred, minlength=16).reshape(4, 4)
    support = confusion.sum(axis=1)
    predicted = confusion.sum(axis=0)
    tp = np.diag(confusion)
    fp = predicted - tp
    fn = support - tp
    classes = []
    for c in range(4):
        precision = float(tp[c] / predicted[c]) if predicted[c] else 0.0
        recall = float(tp[c] / support[c]) if support[c] else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
        classes.append({"class_id": c, "class_name": CLASS_NAMES[c], "support": int(support[c]),
                        "tp": int(tp[c]), "fp": int(fp[c]), "fn": int(fn[c]),
                        "precision": precision, "recall": recall, "f1": f1})
    return {"n": int(len(y_true)), "correct": int(tp.sum()),
            "micro_f1": float(tp.sum() / len(y_true)), "confusion": confusion.tolist(),
            "classes": classes}


def paired_summary(y_true: np.ndarray, base: np.ndarray, candidate: np.ndarray) -> dict:
    base_correct = base == y_true
    candidate_correct = candidate == y_true
    gains = candidate_correct & ~base_correct
    losses = base_correct & ~candidate_correct
    by_class = []
    for c in range(4):
        true_class = y_true == c
        gain = int(np.count_nonzero(gains & true_class))
        loss = int(np.count_nonzero(losses & true_class))
        by_class.append({"class_id": c, "class_name": CLASS_NAMES[c],
                         "baseline_tp": int(np.count_nonzero(true_class & base_correct)),
                         "candidate_tp": int(np.count_nonzero(true_class & candidate_correct)),
                         "gain": gain, "loss": loss, "net": gain - loss})
    return {"gain": int(gains.sum()), "loss": int(losses.sum()),
            "net": int(gains.sum() - losses.sum()), "by_true_class": by_class}


def transition_diagnostics(y_true: np.ndarray, base: np.ndarray, candidate: np.ndarray) -> dict:
    per_true_class = []
    fp_sources = []
    for true_class in range(4):
        mask = y_true == true_class
        transitions = np.bincount(base[mask] * 4 + candidate[mask], minlength=16).reshape(4, 4)
        per_true_class.append({"true_class_id": true_class, "true_class_name": CLASS_NAMES[true_class],
                               "baseline_prediction_to_candidate_prediction": transitions.tolist()})
    for predicted_class in range(4):
        sources = {}
        deltas = {}
        for true_class in range(4):
            if true_class == predicted_class:
                continue
            source_key = f"{true_class}:{CLASS_NAMES[true_class]}"
            base_count = int(np.count_nonzero((y_true == true_class) & (base == predicted_class)))
            candidate_count = int(np.count_nonzero((y_true == true_class) & (candidate == predicted_class)))
            sources[source_key] = {"baseline": base_count, "candidate": candidate_count}
            deltas[source_key] = candidate_count - base_count
        fp_sources.append({"predicted_class_id": predicted_class,
                           "predicted_class_name": CLASS_NAMES[predicted_class],
                           "source_counts": sources, "candidate_minus_baseline": deltas})
    return {"per_true_class_prediction_transitions": per_true_class,
            "false_positive_sources_by_predicted_class": fp_sources}


def observation_bin_diagnostics(obs_days: np.ndarray, y_true: np.ndarray,
                               base: np.ndarray, candidate: np.ndarray) -> dict:
    bins = {}
    assigned = np.zeros(len(obs_days), dtype=bool)
    for name, low, high in OBSERVATION_BINS:
        mask = np.isfinite(obs_days) & (obs_days >= low) & (obs_days <= high)
        assigned |= mask
        bins[name] = {"n_vessels": int(mask.sum()),
                      "baseline": metric_summary(y_true[mask], base[mask]),
                      "candidate": metric_summary(y_true[mask], candidate[mask]),
                      "paired_gain_loss_net": paired_summary(y_true[mask], base[mask], candidate[mask])}
    return {"bins": bins,
            "unbinned_vessels": int((~assigned).sum()),
            "unbinned_reason": "obs_days is non-finite, below 1, or outside the declared positive-day bins"}


def bootstrap_paired(y_true: np.ndarray, base: np.ndarray, candidate: np.ndarray) -> dict:
    n = len(y_true)
    if n != 3144:
        raise ValueError("vessel bootstrap requires the exact 3,144-vessel FIT roster")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    base_correct = base == y_true
    candidate_correct = candidate == y_true
    net_samples = np.empty((BOOTSTRAP_REPLICATES, 5), dtype=np.int32)
    for replicate in range(BOOTSTRAP_REPLICATES):
        sampled = rng.integers(0, n, size=n, dtype=np.int32)
        ys = y_true[sampled]
        bc = base_correct[sampled]
        cc = candidate_correct[sampled]
        net_samples[replicate, 0] = int(cc.sum() - bc.sum())
        for c in range(4):
            class_mask = ys == c
            net_samples[replicate, c + 1] = int(np.count_nonzero(class_mask & cc)
                                                 - np.count_nonzero(class_mask & bc))
    def interval(values: np.ndarray) -> dict:
        low, median, high = np.percentile(values, [2.5, 50, 97.5])
        return {"percentile_95_ci": [float(low), float(high)], "median": float(median)}
    return {"unit": "FIT vessel; paired baseline/candidate row kept together",
            "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
            "interval_method": "percentile 2.5th and 97.5th percentiles",
            "net_correct_count": interval(net_samples[:, 0]),
            "net_tp_by_true_class": {CLASS_NAMES[c]: interval(net_samples[:, c + 1]) for c in range(4)},
            "scope_note": "resampling uncertainty within this diagnostic FIT roster; not independent-data or OUTER performance"}


def load_exact_fit_roster(source_npz: Path, gate_result: dict) -> tuple[list[str], np.ndarray, dict]:
    expected_source_hash = gate_result.get("input_hashes", {}).get("fold0_features_npz")
    if not expected_source_hash:
        raise ValueError("gate result lacks the original fold0 source hash")
    actual_source_hash = sha256_file(source_npz)
    if actual_source_hash.upper() != str(expected_source_hash).upper():
        raise ValueError("original fold0 NPZ hash differs from the completed gate provenance")
    with np.load(source_npz, allow_pickle=False) as archive:
        required = {"rfid_ids", "roles", "obs_days"}
        if not required.issubset(archive.files):
            raise ValueError("original fold0 NPZ lacks FIT roster or observation-day arrays")
        # Deliberately do not access X, y, or feature_names.
        all_ids = np.asarray(archive["rfid_ids"]).astype(str)
        roles = np.asarray(archive["roles"]).astype(str)
        all_obs_days = np.asarray(archive["obs_days"], dtype=np.float64)
    if all_ids.shape != roles.shape or all_ids.shape != all_obs_days.shape:
        raise ValueError("original fold0 roster arrays have inconsistent dimensions")
    fit_mask = roles == "FIT"
    ids = all_ids[fit_mask].tolist()
    obs_days = all_obs_days[fit_mask]
    if len(ids) != 3144 or len(set(ids)) != 3144:
        raise ValueError("original fold0 FIT roster is not the exact 3,144 unique vessels")
    roster_hash = hash_ordered_ids(ids)
    if roster_hash != gate_result.get("ordered_fit_roster_sha256"):
        raise ValueError("original fold0 FIT roster/order differs from the completed gate")
    if np.any(np.isfinite(obs_days) & (obs_days > 0) & (obs_days != np.floor(obs_days))):
        raise ValueError("positive obs_days values are not whole-day counts")
    provenance = {"fold0_features_npz_sha256": actual_source_hash,
                  "ordered_fit_roster_sha256": roster_hash,
                  "hash_scope": ["fold0_features_npz bytes", "ordered FIT vessel ID sequence"],
                  "full_source_code_cache_checker_hashes_verified": False,
                  "fit_roster_rows": len(ids),
                  "observation_day_values_read": True,
                  "other_arrays_read_from_fold0_npz": ["rfid_ids", "roles", "obs_days"]}
    return ids, obs_days, provenance


def resource_snapshot() -> dict:
    import psutil
    memory = psutil.virtual_memory()
    return {"timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "available_bytes": int(memory.available),
            "minimum_available_bytes": MINIMUM_AVAILABLE_BYTES,
            "expected_peak_bytes": EXPECTED_PEAK_BYTES,
            "allowed": bool(memory.available >= MINIMUM_AVAILABLE_BYTES)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate_output_dir", type=Path,
                        help="completed gate output directory, e.g. rounds/round_024/artifacts/gate")
    parser.add_argument("--fold0-npz", type=Path, default=DEFAULT_FOLD0_NPZ,
                        help="original fold0 features archive used by the gate")
    args = parser.parse_args()
    gate_dir = require_workspace_path(args.gate_output_dir, "gate output directory")
    out_path = gate_dir / "supplemental_metrics.json"
    if out_path.exists():
        raise FileExistsError("supplemental_metrics.json already exists; refusing to overwrite")
    source_npz = args.fold0_npz.expanduser().resolve()
    if not source_npz.is_file():
        raise FileNotFoundError("original fold0 NPZ is unavailable")
    memory = resource_snapshot()
    if not memory["allowed"]:
        raise MemoryError("available RAM is below the 1 GiB supplemental-analysis threshold; defer and recheck after independent work")
    global np
    import numpy as np

    result_path = gate_dir / "gate_result.json"
    progress_path = gate_dir / "fit_progress.json"
    if not result_path.is_file() or not progress_path.is_file():
        raise FileNotFoundError("completed gate result and progress records are required")
    gate_result = json.loads(result_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    if (progress.get("status") != "complete" or progress.get("fit_attempts_started") != 8
            or progress.get("fits_completed") != 8 or len(gate_result.get("fit_records", [])) != 8):
        raise ValueError("supplement requires exactly eight completed gate fits")
    if gate_result.get("full_3fold_execution_allowed") is not False or gate_result.get("official_score") is not None:
        raise ValueError("gate result overstates its authorized scope")
    _, y_base, p_base = load_gate_variant(gate_dir, "baseline")
    _, y_candidate, p_candidate = load_gate_variant(gate_dir, "candidate")
    if not np.array_equal(y_base, y_candidate):
        raise ValueError("baseline and candidate saved FIT labels differ")
    ids, obs_days, roster_provenance = load_exact_fit_roster(source_npz, gate_result)
    if len(ids) != len(y_base) or obs_days.shape != y_base.shape:
        raise ValueError("prediction rows and exact FIT roster dimensions differ")
    paired = paired_summary(y_base, p_base, p_candidate)
    output = {"status": "complete",
              "scope": "saved-output analysis of the completed fold0 FIT internal 4-fold diagnostic only",
              "source_provenance": roster_provenance,
              "diagnostic_only": True,
              "independent_data_evaluation": False,
              "official_score": None,
              "fit_vessels": len(ids),
              "class_order": CLASS_NAMES,
              "baseline_metrics": metric_summary(y_base, p_base),
              "candidate_metrics": metric_summary(y_base, p_candidate),
              "paired_gain_loss_net": paired,
              "class_transition_and_false_positive_sources": transition_diagnostics(y_base, p_base, p_candidate),
              "observation_days": observation_bin_diagnostics(obs_days, y_base, p_base, p_candidate),
              "vessel_bootstrap": bootstrap_paired(y_base, p_base, p_candidate),
              "verification_memory": memory,
              "protection_gate_note": "FIT diagnostic counts do not adjudicate OUTER or final 5-seed protections"}
    with out_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": output["status"], "fit_vessels": len(ids),
                      "bootstrap_replicates": BOOTSTRAP_REPLICATES,
                      "output": str(out_path.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
