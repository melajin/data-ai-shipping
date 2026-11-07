"""Independent Round 003 selector and metric recomputation.

Run only after the manager authorizes the frozen Round 003 scoring step. This
script reads only the allowlisted development OOF/INNER probabilities, role
roster and rule metadata. It performs no fit, model load or model inference.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


DATA = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료"
)
OUT = Path(__file__).resolve().parent / "independent_recompute.json"
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)
POLICIES = ("A_raw", "A_old", "A_micro_select")
CLASS_ORDER = ["연안복합", "자망", "통발", "채낚기연승낚시"]
GRID = (1.0, 1.5, 2.0, 2.5, 3.0)
OLD_FACTOR = {0: 2.0, 1: 3.0, 2: 2.0}
TOL = 1e-12
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20261105
PCOLS = ["p0", "p1", "p2", "p3"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(rel: str):
    with (DATA / rel).open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(rel: str):
    return json.loads((DATA / rel).read_text(encoding="utf-8-sig"))


def confmat(y, pred):
    flat = np.asarray(y, dtype=np.int64) * 4 + np.asarray(pred, dtype=np.int64)
    return np.bincount(flat, minlength=16).reshape(4, 4)


def metrics_from_cm(cm):
    cm = np.asarray(cm, dtype=np.int64)
    support = cm.sum(axis=1)
    pred_support = cm.sum(axis=0)
    tp = np.diag(cm)
    precision = np.divide(tp, pred_support, out=np.zeros(4, float), where=pred_support > 0)
    recall = np.divide(tp, support, out=np.zeros(4, float), where=support > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros(4, float), where=denom > 0)
    n = int(cm.sum())
    micro = float(tp.sum() / n) if n else 0.0
    macro = float(f1.mean())
    weighted = float(np.average(f1, weights=support)) if n else 0.0
    return {
        "n": n,
        "correct": int(tp.sum()),
        "micro_f1": micro,
        "macro_f1": macro,
        "weighted_f1": weighted,
        "classes": [
            {
                "index": i,
                "name": CLASS_ORDER[i],
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
                "predicted_support": int(pred_support[i]),
            }
            for i in range(4)
        ],
        "confusion_matrix_true_rows_predicted_columns": cm.tolist(),
    }


def predict(p, factor):
    scores = np.asarray(p, dtype=float).copy()
    scores[:, 2] *= float(factor)
    return scores.argmax(axis=1)


def day_masks(days):
    days = np.asarray(days, dtype=float)
    finite = np.isfinite(days)
    integer = finite & (days == np.floor(days))
    regular = (
        (integer & (days == 0))
        | (integer & (days >= 1) & (days <= 7))
        | (integer & (days >= 8) & (days <= 30))
        | (integer & (days >= 31) & (days <= 90))
        | (integer & (days > 90))
    )
    return {
        "1-7": integer & (days >= 1) & (days <= 7),
        "8-30": integer & (days >= 8) & (days <= 30),
        "31-90": integer & (days >= 31) & (days <= 90),
        "91+": integer & (days >= 91),
        "0": integer & (days == 0),
        "unsupported_or_missing": (~finite) | (~regular),
    }


def safe_days(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def choose_factor(inner_rows):
    p = np.asarray([[float(row[c]) for c in PCOLS] for row in inner_rows], dtype=float)
    y = np.asarray([int(row["y_true"]) for row in inner_rows], dtype=np.int64)
    days = np.asarray([safe_days(row.get("observed_days")) for row in inner_rows], dtype=float)
    raw_pred = p.argmax(axis=1)
    raw_metrics = metrics_from_cm(confmat(y, raw_pred))
    natural = np.isfinite(days) & (days == np.floor(days)) & (days >= 1) & (days <= 7)
    raw_natural = metrics_from_cm(confmat(y[natural], raw_pred[natural]))
    true_support = np.bincount(y, minlength=4)
    natural_support = np.bincount(y[natural], minlength=4)
    if np.any(true_support == 0) or np.any(natural_support == 0):
        return 1.0, {
            "fallback": "raw",
            "fallback_reason": "true class absent in full INNER or natural 1-7 INNER support",
            "inner_support": true_support.tolist(),
            "natural_1_7_support": natural_support.tolist(),
            "raw_inner": raw_metrics,
            "raw_natural_1_7": raw_natural,
            "grid": [],
        }
    candidates = []
    grid_rows = []
    for factor in GRID:
        pred = predict(p, factor)
        m = metrics_from_cm(confmat(y, pred))
        natural_m = metrics_from_cm(confmat(y[natural], pred[natural]))
        eligible = (
            m["macro_f1"] >= raw_metrics["macro_f1"] - TOL
            and all(cls["f1"] >= raw_metrics["classes"][i]["f1"] - 0.01 - TOL
                    for i, cls in enumerate(m["classes"]))
            and natural_m["macro_f1"] >= raw_natural["macro_f1"] - 0.01 - TOL
        )
        row = {
            "factor": factor,
            "eligible": bool(eligible),
            "inner_micro_f1": m["micro_f1"],
            "inner_macro_f1": m["macro_f1"],
            "class_f1": [x["f1"] for x in m["classes"]],
            "natural_1_7_macro_f1": natural_m["macro_f1"],
        }
        grid_rows.append(row)
        if eligible:
            candidates.append((factor, m["micro_f1"]))
    if not candidates:
        # Raw is always eligible by definition; reaching this indicates code/data error.
        raise ValueError("Raw factor 1.0 was not eligible despite complete support")
    best_micro = max(score for _, score in candidates)
    tied = [factor for factor, score in candidates if best_micro - score <= TOL]
    selected = min(tied, key=lambda factor: (abs(factor - 1.0), factor))
    return selected, {
        "fallback": None,
        "fallback_reason": None,
        "inner_support": true_support.tolist(),
        "natural_1_7_support": natural_support.tolist(),
        "raw_inner": raw_metrics,
        "raw_natural_1_7": raw_natural,
        "grid": grid_rows,
        "tie_break_candidates_within_1e-12": tied,
    }


def load_inputs():
    roster = read_csv("splits/development_roles_long.csv")
    role_map = {(int(r["outer_fold"]), str(r["rfid_id"])): str(r["role"]).upper() for r in roster}
    arrays = {}
    input_hashes = {}
    for seed in SEEDS:
        rel = f"evaluation/seed_{seed}/original_oof_predictions.csv"
        rows = read_csv(rel)
        input_hashes[rel] = sha256_file(DATA / rel)
        rows.sort(key=lambda row: str(row["rfid_id"]))
        ids = [str(row["rfid_id"]) for row in rows]
        if len(ids) != 5897 or len(set(ids)) != 5897:
            raise ValueError(f"seed {seed} OOF ID count/uniqueness check failed")
        y = np.asarray([int(row["y_true"]) for row in rows], dtype=np.int64)
        p = np.asarray([[float(row[c]) for c in PCOLS] for row in rows], dtype=float)
        days = np.asarray([safe_days(row.get("observed_days")) for row in rows], dtype=float)
        folds = np.asarray([int(row["fold"]) for row in rows], dtype=np.int64)
        if not np.isfinite(p).all() or np.max(np.abs(p.sum(axis=1) - 1.0)) > TOL:
            raise ValueError(f"seed {seed} OOF probability integrity check failed")
        for i, (vessel, fold) in enumerate(zip(ids, folds)):
            if role_map.get((int(fold), vessel)) != "OUTER":
                raise ValueError(f"seed {seed} OOF role mismatch")
        arrays[seed] = {"ids": ids, "y": y, "p": p, "days": days, "fold": folds}

    if arrays[42]["ids"] != arrays[2026]["ids"]:
        raise ValueError("seed OOF vessel order differs")
    for field in ("y", "days", "fold"):
        if not np.array_equal(arrays[42][field], arrays[2026][field], equal_nan=True):
            raise ValueError(f"seed OOF {field} differs by vessel")

    factors = {}
    for row in read_csv("evaluation/trap_factors.csv"):
        key = (int(row["seed"]), int(row["outer_fold"]))
        factors[key] = float(row["trap_factor"])
    if any(factors.get((seed, fold)) != OLD_FACTOR[fold] for seed in SEEDS for fold in FOLDS):
        raise ValueError("frozen A_old factors do not match 2/3/2")

    inner = {}
    for seed in SEEDS:
        for fold in FOLDS:
            rel = f"evaluation/seed_{seed}/fold_{fold}/inner_predictions.csv"
            rows = read_csv(rel)
            input_hashes[rel] = sha256_file(DATA / rel)
            if len(rows) != 787 or len({str(r["rfid_id"]) for r in rows}) != 787:
                raise ValueError(f"seed {seed} fold {fold} INNER roster size failed")
            if any(role_map.get((fold, str(r["rfid_id"]))) != "INNER" for r in rows):
                raise ValueError(f"seed {seed} fold {fold} INNER membership failed")
            inner[(seed, fold)] = rows
    return arrays, inner, factors, input_hashes


def summarize_predictions(y, p, days, fold, policy, factors):
    if policy == "A_raw":
        pred = p.argmax(axis=1)
    else:
        pred = np.empty(len(y), dtype=np.int64)
        for fold_id in FOLDS:
            mask = fold == fold_id
            pred[mask] = predict(p[mask], factors[fold_id])
    overall = metrics_from_cm(confmat(y, pred))
    by_fold = {}
    for fold_id in FOLDS:
        mask = fold == fold_id
        by_fold[str(fold_id)] = metrics_from_cm(confmat(y[mask], pred[mask]))
    by_days = {}
    for name, mask in day_masks(days).items():
        by_days[name] = metrics_from_cm(confmat(y[mask], pred[mask])) if np.any(mask) else {
            "n": 0, "correct": 0, "micro_f1": None, "macro_f1": None, "weighted_f1": None,
            "classes": [], "confusion_matrix_true_rows_predicted_columns": [[0] * 4 for _ in range(4)],
        }
    return pred, {"overall": overall, "by_fold": by_fold, "by_observed_days": by_days}


def pair_counts(y, pred_from, pred_to):
    correct_from = pred_from == y
    correct_to = pred_to == y
    gain = int(np.sum(~correct_from & correct_to))
    loss = int(np.sum(correct_from & ~correct_to))
    return {
        "from_correct": int(correct_from.sum()),
        "to_correct": int(correct_to.sum()),
        "gain_from_errors": gain,
        "loss_new_errors": loss,
        "net_correct": int(correct_to.sum() - correct_from.sum()),
        "changed_predictions": int(np.sum(pred_from != pred_to)),
        "prediction_transition_matrix_from_rows_to_columns": confmat(pred_from, pred_to).tolist(),
    }


def paired_bootstrap(arrays, predictions):
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(arrays[SEEDS[0]]["y"])
    pairs = (("A_raw", "A_old"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select"))
    samples = {(a, b, metric): np.empty(BOOTSTRAP_REPS, dtype=float)
               for a, b in pairs for metric in ("micro_f1", "macro_f1")}
    for rep in range(BOOTSTRAP_REPS):
        index = rng.integers(0, n, size=n)
        for a, b in pairs:
            seed_deltas = {"micro_f1": [], "macro_f1": []}
            for seed in SEEDS:
                y = arrays[seed]["y"][index]
                ca = metrics_from_cm(confmat(y, predictions[seed][a][index]))
                cb = metrics_from_cm(confmat(y, predictions[seed][b][index]))
                for metric in seed_deltas:
                    seed_deltas[metric].append(cb[metric] - ca[metric])
            for metric, delta_values in seed_deltas.items():
                samples[(a, b, metric)][rep] = float(np.mean(delta_values))
    out = {}
    for a, b in pairs:
        key = f"{a}_to_{b}"
        out[key] = {}
        for metric in ("micro_f1", "macro_f1"):
            point = np.mean([
                metrics_from_cm(confmat(arrays[seed]["y"], predictions[seed][b]))[metric]
                - metrics_from_cm(confmat(arrays[seed]["y"], predictions[seed][a]))[metric]
                for seed in SEEDS
            ])
            values = samples[(a, b, metric)]
            out[key][metric] = {
                "point_delta_mean_across_seeds": float(point),
                "percentile_95_ci": [float(x) for x in np.quantile(values, [0.025, 0.975])],
                "bootstrap_mean": float(values.mean()),
            }
    return {
        "unit": "vessel; one sampled index vector jointly applied to both seeds",
        "repetitions": BOOTSTRAP_REPS,
        "seed": BOOTSTRAP_SEED,
        "selection_or_geographic_bias_removed": False,
        "pairs": out,
    }


def probability_diagnostics(y, p):
    eps = 1e-15
    one_hot = np.eye(4, dtype=float)[y]
    logloss = -np.log(np.maximum(p[np.arange(len(y)), y], eps)).mean()
    brier = np.square(p - one_hot).sum(axis=1).mean()
    conf = p.max(axis=1)
    correct = p.argmax(axis=1) == y
    ece = 0.0
    bins = []
    bin_index = np.minimum(np.floor(conf * 10).astype(int), 9)
    for b in range(10):
        mask = bin_index == b
        count = int(mask.sum())
        if count:
            avg_conf = float(conf[mask].mean())
            avg_acc = float(correct[mask].mean())
            ece += count / len(y) * abs(avg_acc - avg_conf)
            bins.append({"bin": b, "n": count, "mean_confidence": avg_conf, "accuracy": avg_acc})
    return {
        "log_loss_original_probabilities": float(logloss),
        "multiclass_brier_sum_per_row": float(brier),
        "ece_10_equal_width_bins": float(ece),
        "high_confidence_errors_max_probability_ge_0_9": int(np.sum((conf >= 0.9) & ~correct)),
        "bins": bins,
        "decision_changes_do_not_modify_these_probabilities": True,
    }


def main():
    arrays, inner, old_factors, input_hashes = load_inputs()
    selection = {}
    factors_by_seed = {seed: {"A_old": dict(OLD_FACTOR), "A_micro_select": {}} for seed in SEEDS}
    for seed in SEEDS:
        selection[str(seed)] = {}
        for fold in FOLDS:
            factor, detail = choose_factor(inner[(seed, fold)])
            factors_by_seed[seed]["A_micro_select"][fold] = factor
            selection[str(seed)][str(fold)] = {"factor": factor, **detail}

    results = {"per_seed": {}, "predictions": {}, "mean_across_seeds": {}}
    probability = {}
    for seed in SEEDS:
        data = arrays[seed]
        results["per_seed"][str(seed)] = {}
        results["predictions"][seed] = {}
        for policy in POLICIES:
            factor_map = factors_by_seed[seed].get(policy, {})
            pred, summary = summarize_predictions(data["y"], data["p"], data["days"], data["fold"], policy, factor_map)
            results["per_seed"][str(seed)][policy] = summary
            results["predictions"][seed][policy] = pred
        probability[str(seed)] = probability_diagnostics(data["y"], data["p"])
        pairwise = {}
        for a, b in (("A_old", "A_raw"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select")):
            pc = pair_counts(data["y"], results["predictions"][seed][a], results["predictions"][seed][b])
            if (a, b) == ("A_old", "A_raw"):
                names = {0: "연안복합", 1: "자망", 2: "통발"}
                changes = {}
                for c1, c2 in ((0, 1), (1, 0), (0, 2), (2, 0)):
                    changes[f"{names[c1]}_to_{names[c2]}"] = int(pc["prediction_transition_matrix_from_rows_to_columns"][c1][c2])
                pc["targeted_old_to_raw_prediction_changes"] = changes
            pairwise[f"{a}_to_{b}"] = pc
        results["per_seed"][str(seed)]["pairwise"] = pairwise

    for policy in POLICIES:
        mean = {}
        for metric in ("micro_f1", "macro_f1", "weighted_f1"):
            mean[metric] = float(np.mean([
                results["per_seed"][str(seed)][policy]["overall"][metric] for seed in SEEDS
            ]))
        mean["correct_count_mean"] = float(np.mean([
            results["per_seed"][str(seed)][policy]["overall"]["correct"] for seed in SEEDS
        ]))
        results["mean_across_seeds"][policy] = mean

    bootstrap = paired_bootstrap(arrays, results["predictions"])
    primary = bootstrap["pairs"]["A_raw_to_A_micro_select"]
    select_micro_deltas = [
        results["per_seed"][str(seed)]["A_micro_select"]["overall"]["micro_f1"]
        - results["per_seed"][str(seed)]["A_raw"]["overall"]["micro_f1"]
        for seed in SEEDS
    ]
    select_macro_deltas = [
        results["per_seed"][str(seed)]["A_micro_select"]["overall"]["macro_f1"]
        - results["per_seed"][str(seed)]["A_raw"]["overall"]["macro_f1"]
        for seed in SEEDS
    ]
    select_group_ok = all(
        results["per_seed"][str(seed)]["A_micro_select"]["by_observed_days"]["1-7"]["macro_f1"]
        >= results["per_seed"][str(seed)]["A_raw"]["by_observed_days"]["1-7"]["macro_f1"] - 0.01 - TOL
        for seed in SEEDS
    )
    select_class_ok = all(
        results["per_seed"][str(seed)]["A_micro_select"]["overall"]["classes"][i]["f1"]
        >= results["per_seed"][str(seed)]["A_raw"]["overall"]["classes"][i]["f1"] - 0.01 - TOL
        for seed in SEEDS for i in range(4)
    )
    acceptance = {
        "mean_micro_delta_at_least_0_005": float(np.mean(select_micro_deltas)) >= 0.005 - TOL,
        "both_seed_micro_deltas_positive": all(delta > 0 for delta in select_micro_deltas),
        "paired_micro_ci_lower_above_zero": primary["micro_f1"]["percentile_95_ci"][0] > 0,
        "mean_macro_not_lower": float(np.mean(select_macro_deltas)) >= -TOL,
        "each_seed_class_f1_drop_no_more_than_0_01": select_class_ok,
        "each_seed_natural_1_7_macro_drop_no_more_than_0_01": select_group_ok,
    }
    acceptance["all_conditions"] = all(acceptance.values())

    output = {
        "reviewer_scope": "independent recomputation from saved, exposed development probabilities; no new model inference",
        "data_scope": {
            "development_oof_vessels": 5897,
            "seeds": list(SEEDS),
            "folds": list(FOLDS),
            "holdout_individual_rows_read": 0,
            "full7372_f156_or_labels_rows_read": 0,
            "test2025_rows_read": 0,
            "raw_rows_read": 0,
            "feature_rows_read": 0,
            "fit_or_model_inference": False,
            "independent_validation": False,
        },
        "input_sha256": input_hashes,
        "policy_factors": {str(seed): factors_by_seed[seed] for seed in SEEDS},
        "selection": selection,
        "probability_diagnostics_by_seed": probability,
        "results": results,
        "paired_bootstrap": bootstrap,
        "selected_vs_raw_acceptance_gate": acceptance,
        "selection_warning": "Development OUTER is previously exposed; paired bootstrap does not remove adaptive selection or geographic dependence.",
        "probability_warning": "Trap-factor decision scores are not calibrated probabilities; original p0-p3 remain unchanged.",
    }
    # Numpy arrays are used only internally and excluded from the saved report.
    for seed in SEEDS:
        del output["results"]["predictions"][seed]
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "output": str(OUT),
        "micro_deltas_selected_vs_raw": select_micro_deltas,
        "macro_deltas_selected_vs_raw": select_macro_deltas,
        "paired_micro_ci_selected_vs_raw": primary["micro_f1"]["percentile_95_ci"],
        "acceptance": acceptance,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
