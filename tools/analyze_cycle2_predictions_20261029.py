#!/usr/bin/env python3
"""Answer the four questions the first pass could not, from stored predictions.

1. Additive-model residuals per cell. The audit proposed a tighter description
   than "the three factors are sub-additive": the baseline cell sits about 0.03
   below what an additive model predicts, and turning on any single factor
   removes that deficit. This fits the additive model and prints the residuals
   so the claim can be checked rather than asserted.
2. Where the weight contrast pays for the pot-trap recall it buys: per-class
   confusion deltas and predicted-class shares.
3. Pot-trap confusion rows and majority-class predicted share per cell, which
   is what the "one shared bias" hypothesis predicts a pattern in.
4. The sample contrast re-paired on the vessels both cells can score, removing
   the 878-vs-879 evaluation-set difference.

Reads stored predictions only. No fitting, no final holdout.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PREDICTIONS = ROOT / "outputs" / "cycle2_20261029" / "predictions"
DEFAULT_REPORT = ROOT / "outputs" / "cycle2_20261029" / "predictions_report.json"
DEFAULT_OUT = ROOT / "outputs" / "cycle2_20261029" / "prediction_analysis.json"
SAMPLE_LEVELS = ("s4", "all")
WEIGHT_LEVELS = ("none", "balanced")
FEATURE_LEVELS = ("dist36", "dist36_scale32")
FACTORS = ("sample", "weight", "features")
LEVELS = {"sample": SAMPLE_LEVELS, "weight": WEIGHT_LEVELS, "features": FEATURE_LEVELS}
SEEDS = (3201, 3202, 3203)
N_CLASSES = 4
POT_TRAP = 1
MAJORITY = 3


def load_cells(prediction_dir: Path) -> dict:
    cells = {}
    for sample, weight, features in itertools.product(
            SAMPLE_LEVELS, WEIGHT_LEVELS, FEATURE_LEVELS):
        key = (sample, weight, features)
        data = np.load(prediction_dir / f"{sample}_{weight}_{features}.npz",
                       allow_pickle=False)
        cells[key] = {seed: {
            "vessel_hash": data[f"{seed}_vessel_hash"],
            "y_true": data[f"{seed}_y_true"].astype(np.int64),
            "probabilities": data[f"{seed}_probabilities"].astype(np.float64),
            "abstain": data[f"{seed}_abstain"],
        } for seed in SEEDS}
    return cells


def macro_f1(y_true, predicted, scorable):
    """Macro F1 with the cycle-1 denominator: support + predicted count."""
    scores = []
    for cls in range(N_CLASSES):
        actual = (y_true == cls)
        guessed = (predicted == cls)
        true_positive = int(np.count_nonzero(actual & guessed))
        denominator = (int(np.count_nonzero(actual & scorable))
                       + int(np.count_nonzero(guessed)))
        scores.append(2 * true_positive / denominator if denominator else 0.0)
    return float(np.mean(scores)), scores


def cell_mean_f1(cell) -> float:
    values = []
    for seed in SEEDS:
        split = cell[seed]
        scorable = ~split["abstain"]
        predicted = split["probabilities"].argmax(axis=1)
        predicted[split["abstain"]] = -1
        values.append(macro_f1(split["y_true"], predicted, scorable)[0])
    return float(np.mean(values))


def additive_residuals(cells) -> dict:
    """Least-squares additive model on the eight cell means, then residuals.

    An additive model in the three factors has four parameters. With eight
    cells the residuals are what no additive description can absorb, so a
    single large negative residual on one cell is a different claim from
    "every pair interacts".
    """
    keys = list(cells)
    y = np.array([cell_mean_f1(cells[key]) for key in keys])
    design = np.column_stack([
        np.ones(len(keys)),
        [SAMPLE_LEVELS.index(key[0]) for key in keys],
        [WEIGHT_LEVELS.index(key[1]) for key in keys],
        [FEATURE_LEVELS.index(key[2]) for key in keys],
    ])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coefficients
    residuals = y - fitted
    order = np.argsort(residuals)
    return {
        "model": "macro_f1 ~ intercept + sample_on + weight_on + features_on",
        "coefficients": {
            "intercept": round(float(coefficients[0]), 5),
            "sample_on": round(float(coefficients[1]), 5),
            "weight_on": round(float(coefficients[2]), 5),
            "features_on": round(float(coefficients[3]), 5),
        },
        "residual_rms": round(float(np.sqrt(np.mean(residuals ** 2))), 5),
        "cells": [{
            "cell": "/".join(keys[i]),
            "factors_on": int(sum((SAMPLE_LEVELS.index(keys[i][0]),
                                   WEIGHT_LEVELS.index(keys[i][1]),
                                   FEATURE_LEVELS.index(keys[i][2])))),
            "observed": round(float(y[i]), 5),
            "additive_fit": round(float(fitted[i]), 5),
            "residual": round(float(residuals[i]), 5),
        } for i in order],
    }


def pairwise_interactions(cells) -> list:
    """Each two-factor interaction, split by the third factor's level."""
    out = []
    for first, second in itertools.combinations(FACTORS, 2):
        third = next(f for f in FACTORS if f not in (first, second))
        for third_level in LEVELS[third]:
            def key_for(a, b):
                mapping = {first: a, second: b, third: third_level}
                return (mapping["sample"], mapping["weight"], mapping["features"])
            low_low = cell_mean_f1(cells[key_for(LEVELS[first][0], LEVELS[second][0])])
            high_low = cell_mean_f1(cells[key_for(LEVELS[first][1], LEVELS[second][0])])
            low_high = cell_mean_f1(cells[key_for(LEVELS[first][0], LEVELS[second][1])])
            high_high = cell_mean_f1(cells[key_for(LEVELS[first][1], LEVELS[second][1])])
            out.append({
                "factors": f"{first} x {second}",
                "third_factor": f"{third}={third_level}",
                "third_is_on": third_level == LEVELS[third][1],
                "interaction": round(
                    float((high_high - low_high) - (high_low - low_low)), 5),
            })
    return out


def class_flow(cells) -> list:
    """Per-cell confusion detail: pot-trap row and predicted class shares."""
    out = []
    for key, cell in cells.items():
        confusion = np.zeros((N_CLASSES, N_CLASSES), dtype=np.int64)
        scorable_total = 0
        for seed in SEEDS:
            split = cell[seed]
            scorable = ~split["abstain"]
            predicted = split["probabilities"].argmax(axis=1)
            np.add.at(confusion,
                      (split["y_true"][scorable], predicted[scorable]), 1)
            scorable_total += int(scorable.sum())
        out.append({
            "cell": "/".join(key),
            "scorable": scorable_total,
            "pot_trap_row": confusion[POT_TRAP].tolist(),
            "pot_trap_support": int(confusion[POT_TRAP].sum()),
            "predicted_share": [round(float(v), 5) for v in
                                confusion.sum(axis=0) / max(scorable_total, 1)],
            "per_class_correct": np.diag(confusion).tolist(),
            "confusion": confusion.tolist(),
        })
    return out


def weight_cost(cells) -> list:
    """For each weight contrast, which class gains and which pays."""
    out = []
    for sample, features in itertools.product(SAMPLE_LEVELS, FEATURE_LEVELS):
        before = cells[(sample, "none", features)]
        after = cells[(sample, "balanced", features)]
        gained = np.zeros(N_CLASSES, dtype=np.int64)
        shares = np.zeros((2, N_CLASSES))
        scorable_total = 0
        for seed in SEEDS:
            # Same split, same validation roster, so vessels line up by index.
            common = (~before[seed]["abstain"]) & (~after[seed]["abstain"])
            y_true = before[seed]["y_true"][common]
            old = before[seed]["probabilities"][common].argmax(axis=1)
            new = after[seed]["probabilities"][common].argmax(axis=1)
            for cls in range(N_CLASSES):
                actual = (y_true == cls)
                gained[cls] += (int(np.count_nonzero(actual & (new == cls)))
                                - int(np.count_nonzero(actual & (old == cls))))
                shares[0, cls] += int(np.count_nonzero(old == cls))
                shares[1, cls] += int(np.count_nonzero(new == cls))
            scorable_total += int(common.sum())
        out.append({
            "contrast": f"{sample}/{features}: none -> balanced",
            "paired_scorable": scorable_total,
            "correct_change_per_class": gained.tolist(),
            "net_correct_change": int(gained.sum()),
            "predicted_share_before": [round(float(v), 5) for v in shares[0] / scorable_total],
            "predicted_share_after": [round(float(v), 5) for v in shares[1] / scorable_total],
        })
    return out


def paired_sample_contrast(cells) -> list:
    """Sample contrast restricted to vessels both cells can score."""
    out = []
    for weight, features in itertools.product(WEIGHT_LEVELS, FEATURE_LEVELS):
        small = cells[("s4", weight, features)]
        large = cells[("all", weight, features)]
        per_split = []
        for seed in SEEDS:
            if not np.array_equal(small[seed]["vessel_hash"], large[seed]["vessel_hash"]):
                raise AssertionError("validation rosters differ; cannot pair by index")
            common = (~small[seed]["abstain"]) & (~large[seed]["abstain"])
            y_true = small[seed]["y_true"][common]
            small_pred = small[seed]["probabilities"][common].argmax(axis=1)
            large_pred = large[seed]["probabilities"][common].argmax(axis=1)
            keep = np.ones(common.sum(), dtype=bool)
            small_f1, _ = macro_f1(y_true, small_pred, keep)
            large_f1, _ = macro_f1(y_true, large_pred, keep)
            per_split.append({
                "seed": seed,
                "paired_scorable": int(common.sum()),
                "dropped_by_pairing": int(np.count_nonzero(~common)),
                "s4_macro_f1": round(small_f1, 5),
                "all_macro_f1": round(large_f1, 5),
                "delta_macro_f1": round(large_f1 - small_f1, 5),
                "delta_accuracy": round(
                    float(np.mean(large_pred == y_true) - np.mean(small_pred == y_true)), 5),
            })
        deltas = [item["delta_macro_f1"] for item in per_split]
        out.append({
            "contrast": f"{weight}/{features}: s4 -> all (paired on both-scorable)",
            "mean_delta_macro_f1": round(float(np.mean(deltas)), 5),
            "splits_positive": f"{sum(1 for d in deltas if d > 0)}/3",
            "range": [round(min(deltas), 5), round(max(deltas), 5)],
            "per_split": per_split,
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    cells = load_cells(args.predictions)
    stored = json.loads(args.report.read_text(encoding="utf-8"))
    probability_metrics = [{
        "cell": key,
        "nll_uncalibrated": round(value["means"]["nll_uncalibrated"], 5),
        "brier_uncalibrated": round(value["means"]["brier_uncalibrated"], 5),
        "macro_f1": round(value["means"]["macro_f1"], 5),
        "accuracy": round(value["means"]["accuracy"], 5),
    } for key, value in stored["cells"].items()]

    analysis = {
        "schema_version": "cycle2_prediction_analysis_v1",
        "source": str(args.predictions),
        "final_holdout_used": False,
        "additive_model": additive_residuals(cells),
        "pairwise_interactions": pairwise_interactions(cells),
        "class_flow": class_flow(cells),
        "weight_cost": weight_cost(cells),
        "paired_sample_contrast": paired_sample_contrast(cells),
        "probability_metrics": probability_metrics,
        "limitations": [
            "Validation metrics selected over eight cells; optimistically biased.",
            "Three splits share one population and are not independent repeats.",
            "NLL and Brier are uncalibrated, unlike the 2026-10-28 final values.",
            "Residuals and interactions are descriptive; no mechanism is proven.",
        ],
    }
    args.out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"analysis -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
