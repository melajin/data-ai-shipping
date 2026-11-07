"""Frozen Round019 vessel-level evaluation; no fitting or threshold selection.

Run only after the parent approves implementation readiness.  The scorer must
finish successfully before this program will read vessel_peaks.csv.  All writes
are confined to this round's execution directory.  Synthetic tests never read
the fleet or the supplied provisional-linkage list.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats


ROUND_DIR = Path(__file__).resolve().parent
ROOT = ROUND_DIR.parents[2]
METRICS = (
    "peak_score", "p95_score", "median_score", "n_rows",
    "gap_total_h", "activity_radius_km",
)
CANDIDATES = tuple(m for m in METRICS if m != "n_rows")
SCORE_METRICS = METRICS[:3]
SEED = 19019
BOOTSTRAPS = 5000
PERMUTATIONS = 9999
CALIPER = math.log(1.10)
PREVALENCES = (0.0227, 0.10, 0.50, 1.00)
H = 0.0366
EXPECTED_EVENTS = 100
EXPECTED_POSITIVES = 82
EXPECTED_VESSELS = 7372
EXPECTED_ROWS = 3887065
PROTOCOL_SHA256 = "10fe34978e36774f7a63ed12c889871a2b2a0edeec77e9380d7f50b016645f0a"
MIB = 1024 ** 2


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_safe(value):
    """Represent unavailable values as JSON null, never NaN/Infinity."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, value):
    Path(path).write_text(
        json.dumps(json_safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def memory_snapshot():
    """One snapshot, with no polling and no process termination."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        processes = []
        for process in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = process.info
                processes.append({"pid": info["pid"], "name": info["name"],
                                  "rss_mib": info["memory_info"].rss / MIB})
            except (psutil.Error, AttributeError):
                continue
        processes.sort(key=lambda p: p["rss_mib"], reverse=True)
        return {"checked_at_utc": utc_now(), "available_mib": vm.available / MIB,
                "total_mib": vm.total / MIB, "top_processes": processes[:8],
                "source": "psutil.virtual_memory/process_iter"}
    except ImportError:
        if os.name != "nt":
            raise RuntimeError("psutil is required for the pre-evaluation RAM snapshot")
        script = (
            "$m=Get-CimInstance Win32_OperatingSystem;"
            "$p=@(Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 8 "
            "@{n='pid';e={$_.Id}},@{n='name';e={$_.ProcessName}},"
            "@{n='rss_mib';e={$_.WorkingSet64/1MB}});"
            "@{available_mib=$m.FreePhysicalMemory/1024;total_mib=$m.TotalVisibleMemorySize/1024;"
            "top_processes=$p}|ConvertTo-Json -Depth 4 -Compress"
        )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                capture_output=True, text=True, check=True)
        snapshot = json.loads(result.stdout)
        snapshot.update(checked_at_utc=utc_now(), source="Win32_OperatingSystem/Get-Process")
        return snapshot


def require_memory(output_dir):
    snapshot = memory_snapshot()
    snapshot.update(
        stage="before_evaluation", estimated_peak_mib=512, reserve_mib=640,
        estimate_basis=("7372 vessel rows; six sequential metrics; raw bootstrap uses one "
                        "rank-frequency vector per replicate; matched arrays <=9999x82; "
                        "no fleet-hour rows or 5000x7290 resampling matrix loaded"),
    )
    snapshot["sufficient"] = snapshot["available_mib"] >= 1152
    write_json(output_dir / "evaluation_memory.json", snapshot)
    if not snapshot["sufficient"]:
        raise RuntimeError("RAM insufficient: evaluation paused; rerun after a fresh task-stage check")
    return snapshot


def auc_greater(positive, negative):
    positive = np.asarray(positive, dtype=float)
    negative = np.asarray(negative, dtype=float)
    if not len(positive) or not len(negative):
        return None, None
    test = stats.mannwhitneyu(positive, negative, alternative="greater",
                              method="asymptotic", use_continuity=True)
    return float(test.statistic / (len(positive) * len(negative))), float(test.pvalue)


def raw_bootstrap_ci(positive, negative, rng, repetitions=BOOTSTRAPS):
    """Separate-label, vessel-resampling percentile CI with bounded memory.

    Frequency vectors retain the exact empirical bootstrap including ties;
    they are not a fitted distribution or a row-level bootstrap.
    """
    positive = np.asarray(positive, dtype=float)
    negative = np.asarray(negative, dtype=float)
    if not len(positive) or not len(negative):
        return None, None
    values, codes = np.unique(np.concatenate([positive, negative]), return_inverse=True)
    p_codes, n_codes = codes[:len(positive)], codes[len(positive):]
    samples = np.empty(repetitions)
    denominator = len(positive) * len(negative)
    for i in range(repetitions):
        pc = np.bincount(p_codes[rng.integers(len(positive), size=len(positive))], minlength=len(values))
        nc = np.bincount(n_codes[rng.integers(len(negative), size=len(negative))], minlength=len(values))
        samples[i] = np.dot(pc, np.cumsum(nc) - 0.5 * nc) / denominator
    return tuple(float(v) for v in np.quantile(samples, [0.025, 0.975], method="linear"))


def build_matches(frame, max_controls=5, caliper=CALIPER):
    """Greedy n_rows matching only; RFID is solely a deterministic tie-break."""
    positives = frame.loc[frame.is_provisional_linked].sort_values(["n_rows", "rfid_id"], kind="stable")
    controls = frame.loc[~frame.is_provisional_linked].sort_values("rfid_id", kind="stable")
    available = {str(row.rfid_id): (int(index), float(row.n_rows))
                 for index, row in controls.iterrows()}
    sets, edges, unmatched = [], [], []
    for positive_index, positive in positives.iterrows():
        candidates = []
        for rfid, (index, count) in available.items():
            distance = abs(math.log(count / float(positive.n_rows)))
            if distance <= caliper + 1e-14:
                candidates.append((distance, rfid, index, count))
        chosen = sorted(candidates)[:max_controls]
        if not chosen:
            unmatched.append(str(positive.rfid_id))
            continue
        set_id = len(sets)
        sets.append((int(positive_index), [item[2] for item in chosen]))
        for distance, rfid, index, count in chosen:
            edges.append({"set_id": set_id, "positive_rfid_id": str(positive.rfid_id),
                          "control_rfid_id": rfid, "positive_n_rows": int(positive.n_rows),
                          "control_n_rows": int(count), "control_positive_count_ratio": count / positive.n_rows,
                          "abs_log_count_ratio": distance, "control_weight_within_set": 1 / len(chosen)})
            del available[rfid]
    return sets, edges, unmatched


def finite_metric_sets(frame, base_sets, metric):
    values = frame[metric].to_numpy(dtype=float)
    result = []
    for positive, controls in base_sets:
        valid_controls = [c for c in controls if np.isfinite(values[c])]
        if np.isfinite(values[positive]) and valid_controls:
            result.append((positive, valid_controls))
    return result


def set_win_values(frame, sets, metric):
    values = frame[metric].to_numpy(dtype=float)
    result = []
    for positive, controls in sets:
        sample = values[[positive] + controls]
        result.append((stats.rankdata(sample, method="average") - 1) / (len(sample) - 1))
    return result


def matched_auc_and_inference(frame, sets, metric, rng,
                              bootstraps=BOOTSTRAPS, permutations=PERMUTATIONS):
    """Equal-set conditional AUC; set bootstrap and approximate label permutation."""
    wins = set_win_values(frame, sets, metric)
    if not wins:
        return {"auc": None, "ci_low": None, "ci_high": None, "p_greater": None,
                "n_sets": 0, "n_controls": 0}
    observed_wins = np.asarray([w[0] for w in wins])
    observed = float(observed_wins.mean())
    boot = np.empty(bootstraps)
    for i in range(bootstraps):
        boot[i] = observed_wins[rng.integers(len(wins), size=len(wins))].mean()
    ci_low, ci_high = np.quantile(boot, [0.025, 0.975], method="linear")
    null_sums = np.zeros(permutations)
    for win in wins:
        null_sums += win[rng.integers(len(win), size=permutations)]
    # Round-off tolerance counts algebraically identical mean statistics as ties.
    exceedances = int(np.count_nonzero(null_sums >= observed_wins.sum() - 1e-12))
    return {"auc": observed, "ci_low": float(ci_low), "ci_high": float(ci_high),
            "p_greater": (exceedances + 1) / (permutations + 1),
            "permutation_exceedances": exceedances,
            "n_sets": len(sets), "n_controls": sum(len(c) for _, c in sets)}


def holm_adjust(p_values):
    """Keep all predeclared hypotheses; unavailable p acts as 1 in the family."""
    clean = [1.0 if p is None or not np.isfinite(p) else float(p) for p in p_values]
    order = sorted(range(len(clean)), key=lambda i: (clean[i], i))
    adjusted, previous = [None] * len(clean), 0.0
    for rank, index in enumerate(order):
        previous = min(1.0, max(previous, (len(clean) - rank) * clean[index]))
        if p_values[index] is not None and np.isfinite(p_values[index]):
            adjusted[index] = previous
    return adjusted


def weighted_smd(positive, controls, control_weights):
    positive = np.asarray(positive, dtype=float)
    controls = np.asarray(controls, dtype=float)
    weights = np.asarray(control_weights, dtype=float)
    if not len(positive) or not len(controls):
        return None
    p_mean, c_mean = positive.mean(), np.average(controls, weights=weights)
    p_var = np.mean((positive - p_mean) ** 2)
    c_var = np.average((controls - c_mean) ** 2, weights=weights)
    denominator = math.sqrt((p_var + c_var) / 2)
    if denominator == 0:
        return 0.0 if p_mean == c_mean else None
    return float((p_mean - c_mean) / denominator)


def balance_summary(frame, sets, column="n_rows"):
    counts = frame[column].to_numpy(dtype=float)
    positives, controls, weights, ratios = [], [], [], []
    excluded_sets = 0
    for positive, matched in sets:
        selected = [c for c in matched if np.isfinite(counts[c]) and counts[c] > 0]
        if not np.isfinite(counts[positive]) or counts[positive] <= 0 or not selected:
            excluded_sets += 1
            continue
        positives.append(math.log(counts[positive]))
        controls.extend(np.log(counts[selected]))
        weights.extend([1 / len(selected)] * len(selected))
        ratios.extend(counts[selected] / counts[positive])
    return {"column": column, "log_count_smd": weighted_smd(positives, controls, weights),
            "smd_definition": "equal set weights; control 1/k weights; population variances",
            "n_sets": len(positives), "n_controls": len(controls), "excluded_nonpositive_or_nonfinite_sets": excluded_sets,
            "control_positive_ratio_min": float(np.min(ratios)) if ratios else None,
            "control_positive_ratio_median": float(np.median(ratios)) if ratios else None,
            "control_positive_ratio_max": float(np.max(ratios)) if ratios else None,
            "control_positive_ratio_weighted_mean": float(np.average(ratios, weights=weights)) if ratios else None}


def threshold_specs(metric, pooled):
    specs = [{"threshold_kind": "none", "threshold": None, "quantile": None, "representative": False},
             {"threshold_kind": "all", "threshold": None, "quantile": None, "representative": False}]
    if metric in SCORE_METRICS:
        for i in range(12):
            value = round(0.40 + 0.05 * i, 2)
            specs.append({"threshold_kind": "value", "threshold": value, "quantile": None,
                          "representative": value == 0.75})
    else:
        finite = pd.Series(np.asarray(pooled)[np.isfinite(pooled)])
        for q in (0.50, 0.75, 0.90, 0.95, 0.99):
            value = float(finite.quantile(q, interpolation="linear")) if len(finite) else None
            specs.append({"threshold_kind": "value", "threshold": value, "quantile": q,
                          "representative": q == 0.95})
    return specs


def selected_mask(values, spec):
    finite = np.isfinite(values)
    if spec["threshold_kind"] == "all":
        return finite
    if spec["threshold_kind"] == "none":
        return np.zeros(len(values), dtype=bool)
    if spec["threshold"] is None:
        return np.zeros(len(values), dtype=bool)
    return finite & (values >= spec["threshold"])


def threshold_rates(frame, sets, metric, spec):
    values = frame[metric].to_numpy(dtype=float)
    finite, selected = np.isfinite(values), selected_mask(values, spec)
    labels = frame.is_provisional_linked.to_numpy(dtype=bool)
    p_mask, n_mask = finite & labels, finite & ~labels
    n_p, n_n = int(p_mask.sum()), int(n_mask.sum())
    tp, fp = int((selected & p_mask).sum()), int((selected & n_mask).sum())
    undefined = spec["threshold_kind"] == "value" and spec["threshold"] is None
    raw = {"source": "raw_fleet_uncontrolled", "tpr": tp / n_p if n_p and not undefined else None,
           "fpr": fp / n_n if n_n and not undefined else None,
           "positive_denominator": n_p, "control_denominator": n_n,
           "tp": tp, "fp": fp, "fn": n_p - tp, "tn": n_n - fp,
           "positive_selected_weight": tp, "control_selected_weight": fp}
    p_selected = sum(int(selected[p]) for p, _ in sets)
    c_selected = sum(float(selected[controls].mean()) for _, controls in sets)
    matched = {"source": "matched_set_weighted", "tpr": p_selected / len(sets) if sets and not undefined else None,
               "fpr": c_selected / len(sets) if sets and not undefined else None,
               "positive_denominator": len(sets), "control_denominator": len(sets),
               "n_distinct_controls": sum(len(c) for _, c in sets),
               "tp": None, "fp": None, "fn": None, "tn": None,
               "positive_selected_weight": p_selected, "control_selected_weight": c_selected}
    return raw, matched


def expected_f1(a, b, prevalence, h=H):
    if not (0 < prevalence <= 1 and 0 <= h <= 1):
        raise ValueError("prevalence must be (0,1], h must be [0,1]")
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
        return {"k_per_100": None, "q": None, "expected_time_included_f1": None}
    if not (0 <= a <= 1 and 0 <= b <= 1):
        raise ValueError("TPR and FPR must be [0,1]")
    selected = prevalence * a + (1 - prevalence) * b
    denominator = prevalence * (1 + a) + (1 - prevalence) * b
    return {"k_per_100": 100 * selected,
            "q": prevalence * a / selected if selected else None,
            "expected_time_included_f1": 2 * prevalence * a * h / denominator}


def distribution_rows(frame):
    result = []
    for metric in METRICS:
        for group, mask in (("pooled_unlabeled_quantiles", np.ones(len(frame), dtype=bool)),
                            ("provisional_linked", frame.is_provisional_linked),
                            ("provisional_unlinked_comparator", ~frame.is_provisional_linked)):
            values = frame.loc[mask, metric].to_numpy(dtype=float)
            finite = pd.Series(values[np.isfinite(values)])
            row = {"metric": metric, "group": group, "n_total": len(values),
                   "n_finite": len(finite), "n_nonfinite": len(values) - len(finite),
                   "mean": finite.mean(), "std_population": finite.std(ddof=0),
                   "min": finite.min(), "max": finite.max()}
            row.update({name: finite.quantile(q, interpolation="linear") for name, q in
                        (("p05", .05), ("p25", .25), ("median", .50), ("p75", .75), ("p95", .95))})
            result.append(json_safe(row))
    return result


def validate_ready_metadata(metadata):
    expected = {"status": "complete", "stage": "finished", "source_checksums_match": True,
                "vessels": EXPECTED_VESSELS, "vessels_completed": EXPECTED_VESSELS,
                "rows": EXPECTED_ROWS, "rows_completed": EXPECTED_ROWS, "vessel_error_records": 0}
    differences = {k: {"expected": v, "actual": metadata.get(k)}
                   for k, v in expected.items() if metadata.get(k) != v}
    if differences:
        raise ValueError("Scoring is not completely successful; no score CSV read: " + json.dumps(differences))


def verify_score_artifact(scores_path, metadata):
    """Bind evaluation to the exact artifact certified by the completed scorer."""
    expected = metadata.get("output_sha256")
    if (not isinstance(expected, str) or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected.lower())):
        raise ValueError("Completed scorer metadata lacks a valid output_sha256; no score CSV parsed")
    actual = sha256(scores_path)
    if actual != expected.lower():
        raise ValueError("Score CSV SHA256 differs from completed scorer output_sha256; no score CSV parsed")
    return actual


def load_evaluation_frame(scores_path, positives_path):
    # Read only existing ID membership, never external identities or source events.
    positives = pd.read_csv(positives_path, usecols=["rfid_id"], dtype={"rfid_id": str}, keep_default_na=False)
    ids = set(positives.rfid_id)
    if len(positives) != EXPECTED_EVENTS or len(ids) != EXPECTED_POSITIVES or "" in ids:
        raise ValueError(f"Expected 100 supplied event rows/82 IDs, got {len(positives)}/{len(ids)}")
    frame = pd.read_csv(scores_path, dtype={"rfid_id": str}, keep_default_na=True)
    required = {"rfid_id", "n_finite_scores", *METRICS}
    if not required.issubset(frame.columns):
        raise ValueError("Missing score columns: " + repr(sorted(required - set(frame.columns))))
    if frame.rfid_id.isna().any() or frame.rfid_id.duplicated().any():
        raise ValueError("Scorer IDs must be nonmissing and unique")
    if len(frame) != EXPECTED_VESSELS or int(frame.n_rows.sum()) != EXPECTED_ROWS:
        raise ValueError("Scorer row/vessel totals do not match the frozen cohort")
    missing = sorted(ids - set(frame.rfid_id))
    if missing:
        raise ValueError("Supplied provisional-linked IDs absent from scorer: " + repr(missing))
    for column in (*METRICS, "n_finite_scores"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    for column in ("n_rows", "n_finite_scores"):
        values = frame[column].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < (1 if column == "n_rows" else 0)).any() or (values != np.floor(values)).any():
            raise ValueError(column + " must contain finite integer counts in its allowed range")
    if (frame.n_finite_scores > frame.n_rows).any():
        raise ValueError("n_finite_scores cannot exceed n_rows")
    frame["is_provisional_linked"] = frame.rfid_id.isin(ids)
    frame["label_status"] = np.where(frame.is_provisional_linked,
                                      "provisional_linked", "provisional_unlinked_comparator")
    return frame.reset_index(drop=True), len(positives)


def evaluate(frame, event_rows):
    rng = np.random.default_rng(SEED)
    base_sets, edges, unmatched = build_matches(frame)
    n_positive = int(frame.is_provisional_linked.sum())
    raw_results, matched_results, valid_sets = {}, {}, {}
    for metric in METRICS:
        values = frame[metric].to_numpy(dtype=float)
        labels = frame.is_provisional_linked.to_numpy(dtype=bool)
        positive = values[labels & np.isfinite(values)]
        negative = values[~labels & np.isfinite(values)]
        auc, p = auc_greater(positive, negative)
        low, high = raw_bootstrap_ci(positive, negative, rng)
        raw_results[metric] = {"auc": auc, "p_greater": p, "ci_low": low, "ci_high": high,
                               "n_positive_finite": len(positive), "n_control_finite": len(negative),
                               "n_positive_nonfinite": n_positive - len(positive),
                               "n_control_nonfinite": len(frame) - n_positive - len(negative),
                               "interpretation": "교란 미통제"}
        sets = finite_metric_sets(frame, base_sets, metric)
        valid_sets[metric] = sets
        matched = matched_auc_and_inference(frame, sets, metric, rng)
        matched.update(positive_coverage=len(sets) / n_positive if n_positive else 0,
                       log_n_rows_balance=balance_summary(frame, sets),
                       finite_score_exposure_balance=balance_summary(frame, sets, "n_finite_scores"))
        matched_results[metric] = matched
    adjusted = holm_adjust([matched_results[m]["p_greater"] for m in CANDIDATES])
    for metric, value in zip(CANDIDATES, adjusted):
        matched_results[metric]["p_holm"] = value
    auc_rows, passing = [], []
    for metric in METRICS:
        raw, matched = raw_results[metric], matched_results[metric]
        diagnostic = metric == "n_rows"
        checks = {
            "auc_at_least_060": matched["auc"] is not None and matched["auc"] >= .60,
            "ci_low_above_050": matched["ci_low"] is not None and matched["ci_low"] > .50,
            "holm_p_below_005": matched.get("p_holm") is not None and matched["p_holm"] < .05,
            "positive_coverage_at_least_090": matched["positive_coverage"] >= .90,
            "abs_log_count_smd_at_most_010": matched["log_n_rows_balance"]["log_count_smd"] is not None
                and abs(matched["log_n_rows_balance"]["log_count_smd"]) <= .10,
        }
        passed = not diagnostic and all(checks.values())
        if diagnostic:
            decision = "관측 편향 진단 전용; 판정 후보 제외"
        elif passed:
            decision = "잠정 연결과의 조건부 연관 기준 통과"
            passing.append(metric)
        elif matched["auc"] is not None and .45 <= matched["auc"] <= .55:
            decision = "판정 불가"
        else:
            decision = "판정력 입증 못함"
        matched.update(diagnostic_only=diagnostic, gate_checks=checks, gate_passed=passed, decision=decision)
        auc_rows.append({"metric": metric, "role": "diagnostic" if diagnostic else "candidate",
                         **{"raw_" + k: v for k, v in raw.items()},
                         **{"matched_" + k: v for k, v in matched.items() if not isinstance(v, dict)},
                         "matched_log_n_rows_smd": matched["log_n_rows_balance"]["log_count_smd"],
                         **{"gate_" + k: v for k, v in checks.items()}})
    sweep, scenarios = [], []
    for metric in METRICS:
        for spec in threshold_specs(metric, frame[metric].to_numpy(dtype=float)):
            for rates in threshold_rates(frame, valid_sets[metric], metric, spec):
                row = {"metric": metric, **spec, **rates,
                       "selection_rule": "finite_value >= threshold; all/none explicit",
                       "diagnostic_only": metric == "n_rows"}
                sweep.append(row)
                for prevalence in PREVALENCES:
                    scenarios.append({**row, "prevalence": prevalence, "h": H,
                                      "scenario": "fixed_h_sensitivity_not_official_F1",
                                      **expected_f1(rates["tpr"], rates["fpr"], prevalence)})
    mismatch = frame.n_finite_scores != frame.n_rows
    quality = {"n_vessels_finite_scores_differs_from_rows": int(mismatch.sum()),
               "n_linked_mismatch": int((mismatch & frame.is_provisional_linked).sum()),
               "n_comparator_mismatch": int((mismatch & ~frame.is_provisional_linked).sum()),
               "total_n_rows": int(frame.n_rows.sum()), "total_n_finite_scores": int(frame.n_finite_scores.sum()),
               "residual_exposure_confounding": bool(mismatch.any()),
               "interpretation": "If counts differ, n_rows matching leaves residual finite-score exposure confounding; no new candidate test."}
    distributions = distribution_rows(frame)
    summary = {
        "created_at_utc": utc_now(), "stage": "evaluation_complete", "seed": SEED,
        "metric_order": METRICS, "bootstrap_repetitions": BOOTSTRAPS, "permutation_repetitions": PERMUTATIONS,
        "cohort": {"vessels": len(frame), "rows": int(frame.n_rows.sum()), "supplied_event_rows": event_rows,
                   "provisional_linked_vessels": n_positive, "provisional_unlinked_comparators": len(frame) - n_positive},
        "label_caveats": ["Supplied linkage membership is provisional; absence is not confirmed nonaccident.",
                          "100 supplied event rows collapse to 82 IDs; the requested 167/7372 approximation is not measured prevalence.",
                          "Only existing supplied 2026 RFID membership is used; no new identity join or reidentification.",
                          "Only 82 linked vessels: wide intervals and failure to detect associations remain possible."],
        "matching": {"method": "greedy sorted positive(n_rows,rfid_id), nearest log-count controls, no reuse",
                     "max_controls": 5, "caliper_log": CALIPER, "coverage": len(base_sets) / n_positive,
                     "n_sets": len(base_sets), "n_controls": len(edges), "unmatched_positive_ids": unmatched,
                     "log_n_rows_balance": balance_summary(frame, base_sets),
                     "finite_score_exposure_balance": balance_summary(frame, base_sets, "n_finite_scores"),
                     "finite_metric_rule": "Drop nonfinite members only inside fixed base sets; retain finite positive with >=1 finite control; coverage denominator all82.",
                     "uncertainty_caveat": "Matched CI conditions on fixed matched sets, not uncertain linkage or matching selection; permutation is approximate under assumed near-match exchangeability."},
        "quality": quality, "distributions": distributions, "uncontrolled": raw_results,
        "controlled_conditional": matched_results,
        "holm": {"family": CANDIDATES, "family_size": 5, "diagnostic_excluded": "n_rows",
                 "missing_p_rule": "Unavailable tests retained as p=1 in family; reported adjusted p remains null."},
        "decision": {"passing_candidates": passing, "adopted_threshold": None,
                     "conclusion": "잠정 연결과의 조건부 연관 기준 통과 후보 있음" if passing else "채택 후보·임계값 없음; 판정력을 입증하지 못함",
                     "no_threshold_optimization": True,
                     "scope": "Conditional association with provisional linkage; not confirmed accident detection or external validation."},
        "expected_f1_assumptions": {"prevalences": PREVALENCES, "h": H, "per_100": True,
                                    "formula": "2*p*a*h / (p*(1+a)+(1-p)*b)",
                                    "k_formula": "100*(p*a+(1-p)*b)", "q_formula": "p*a/(p*a+(1-p)*b)",
                                    "perfect_selection_upper_bound": H, "p1_is_no_comparator_scenario": True,
                                    "interpretation": "Ratios of expected counts, not exact expected finite-sample F1; explanatory sensitivity, not official F1.",
                                    "transport_assumption": "Conditional score distributions and selected-vessel timing hit rate h would have to remain unchanged; unverified.",
                                    "matched_fpr_scope": "Standardized to linked-vessel observation-count distribution, not fleet FPR."},
    }
    return summary, edges, auc_rows, sweep, scenarios, distributions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROUND_DIR / "execution_001")
    parser.add_argument("--positives", type=Path,
                        default=ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv")
    args = parser.parse_args(argv)
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROUND_DIR):
        raise ValueError("Outputs must stay inside the owned Round019 directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_path = ROUND_DIR / "PROTOCOL.md"
    if sha256(protocol_path) != PROTOCOL_SHA256:
        raise ValueError("Frozen protocol SHA256 changed; request design review before evaluation")
    metadata_path = output_dir / "score_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    validate_ready_metadata(metadata)
    memory = require_memory(output_dir)
    scores_path = output_dir / "vessel_peaks.csv"
    paths = {"protocol": protocol_path, "scores": scores_path,
             "score_metadata": metadata_path, "supplied_positive_membership": args.positives.resolve(),
             "evaluation_code": Path(__file__).resolve()}
    before_hashes = {key: sha256(path) for key, path in paths.items() if key != "scores"}
    before_hashes["scores"] = verify_score_artifact(scores_path, metadata)
    frame, event_rows = load_evaluation_frame(scores_path, args.positives)
    summary, edges, auc_rows, sweep, scenarios, distributions = evaluate(frame, event_rows)
    after_hashes = {key: sha256(path) for key, path in paths.items()}
    if before_hashes != after_hashes:
        raise RuntimeError("Input or code checksum changed during evaluation; no final outputs written")
    summary.update(memory_before_evaluation=memory, provenance={"paths": paths,
                   "sha256_before": before_hashes, "sha256_after": after_hashes,
                   "checksums_match": True, "score_metadata": metadata})
    frame.to_csv(output_dir / "evaluation_vessels.csv", index=False, encoding="utf-8-sig")
    for name, rows in (("matched_sets.csv", edges), ("auc_results.csv", auc_rows),
                       ("threshold_sweep.csv", sweep), ("expected_f1.csv", scenarios),
                       ("distributions.csv", distributions)):
        pd.DataFrame(rows).to_csv(output_dir / name, index=False, encoding="utf-8-sig")
    write_json(output_dir / "summary.json", summary)
    print(json.dumps({"status": "complete", "summary": str(output_dir / "summary.json"),
                      "cohort": summary["cohort"], "decision": summary["decision"]}, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
