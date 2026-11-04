#!/usr/bin/env python3
"""Paired geometry checks on development TRAIN paths only; no fit or final data."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishing_demo.data import generate_dataset, validate_record
from fishing_demo.iteration_features import feature_matrix, feature_names
from fishing_demo.pipeline import save_json


def scaled_record(record, factor=2.6):
    row = copy.deepcopy(record)
    cloud = np.asarray([p for part in row["parts"] for p in part], dtype=float)
    center = cloud.mean(axis=0)
    row["parts"] = [((np.asarray(part) - center) * factor + center).tolist() for part in row["parts"]]
    validate_record(row)
    return row


def boundary_only_record(record, max_points=3):
    row = copy.deepcopy(record)
    new_parts, new_times = [], []
    for part, times in zip(row["parts"], row["sim_times"]):
        for start in range(0, len(part), max_points):
            new_parts.append(part[start:start + max_points])
            new_times.append(times[start:start + max_points])
    row["parts"], row["sim_times"] = new_parts, new_times
    row["quality"]["part_count"] = len(new_parts)
    assert [p for part in row["parts"] for p in part] == [p for part in record["parts"] for p in part]
    validate_record(row)
    return row


def analyze(out):
    out = Path(out)
    if not (out / "protocol.json").exists():
        raise ValueError("run the iterative experiment first; its protocol.json must exist")
    rows = [r for r in generate_dataset(seed=1101)["records"] if r["split"] == "train"][:60]
    transformed = {
        "scale_only_2_6": [scaled_record(r) for r in rows],
        "boundaries_only_max_3_points": [boundary_only_record(r) for r in rows],
    }
    findings = {}
    for family in ("original8", "shape7", "shape9", "shape15"):
        base = feature_matrix(rows, family)
        findings[family] = {}
        for kind, changed in transformed.items():
            values = feature_matrix(changed, family)
            common = np.isfinite(base) & np.isfinite(values)
            per_feature = []
            for i, name in enumerate(feature_names(family)):
                valid = common[:, i]
                deltas = abs(values[valid, i] - base[valid, i])
                per_feature.append({"name": name, "compared_pairs": int(valid.sum()),
                    "max_absolute_change": float(deltas.max()) if len(deltas) else None,
                    "mean_absolute_change": float(deltas.mean()) if len(deltas) else None,
                    "missing_state_changes": int(np.sum(np.isnan(base[:, i]) != np.isnan(values[:, i])))})
            findings[family][kind] = per_feature
    tolerance = 1e-8
    scale_checks = {}
    for family in ("shape7", "shape9", "shape15"):
        base = feature_matrix(rows, family)
        changed = feature_matrix(transformed["scale_only_2_6"], family)
        np.testing.assert_allclose(base, changed, atol=tolerance, rtol=0, equal_nan=True)
        scale_checks[family] = True
    before = feature_matrix(rows, "shape9")[:, -2:]
    after = feature_matrix(transformed["boundaries_only_max_3_points"], "shape9")[:, -2:]
    np.testing.assert_allclose(before, after, atol=tolerance, rtol=0, equal_nan=True)
    result = {
        "source_type": "synthetic", "data_role": "development_train_only",
        "generator_seed": 1101, "sample_selection": "first 60 train rows in generator order",
        "n_pairs_per_condition": len(rows), "fit_performed": False,
        "final_data_generated_or_read": False, "conditions": {
            "scale_only_2_6": "Same observed points and parts scaled by 2.6 about their centroid; no noise/dropout change.",
            "boundaries_only_max_3_points": "Same observed coordinates and order; each part divided into chunks of at most three points. No connecting segments added."},
        "feature_differences": findings,
        "checks": {"dimensionless_families_scale_invariant": scale_checks,
            "global_cloud_features_boundary_invariant": True,
            "numerical_tolerance": tolerance},
        "interpretation": [
            "Original log length responds to scale by construction; removing it eliminates this direct feature dependence.",
            "Part-summary features can change when the same coordinate cloud is split more finely; global cloud features remain fixed.",
            "These are feature-sensitivity checks, not accident experiments or proof of each mechanism's contribution to prediction error.",
            "Class labels are retained as a synthetic transformation assumption; no label or metadata enters feature calculation."],
    }
    save_json(out / "feature_sensitivity.json", result)
    print("60 paired development-train paths: scale and boundary-only checks passed.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/iterative_models_20261026")
    args = parser.parse_args()
    analyze(args.out)


if __name__ == "__main__":
    main()
