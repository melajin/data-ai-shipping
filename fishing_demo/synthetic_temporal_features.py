"""Simulation-only within-part timing features for a separate educational study.

The S0 timestamps are randomly generated seconds, not real observations.
This module accepts only a valid S0 synthetic dataset and never joins parts.
It does not modify the established geometry-only feature or model contracts.
"""
from __future__ import annotations

import numpy as np

from .data import validate_dataset
from .iteration_features import feature_matrix as geometry_matrix, feature_names as geometry_names, feature_units as geometry_units


TEMPORAL_NAMES = ("mean_within_part_dt_sim_s", "mean_within_part_speed_sim_m_per_s",
                  "speed_variance_sim_m2_per_s2", "speed_cv_sim")
GEOMETRY_CONTROL_NAMES = ("mean_within_part_edge_length_m", "edge_length_variance_m2",
                          "edge_length_cv")
TEMPORAL_UNITS = ("sim_s", "m/sim_s", "m^2/sim_s^2", "dimensionless")
GEOMETRY_CONTROL_UNITS = ("m", "m^2", "dimensionless")


def feature_names(family):
    suffixes = {"shape9_simtime4": TEMPORAL_NAMES, "shape9_edge3": GEOMETRY_CONTROL_NAMES,
                "shape9_dt_only": TEMPORAL_NAMES[:1]}
    if family not in suffixes:
        raise ValueError("unknown synthetic temporal feature family")
    return geometry_names("shape9") + suffixes[family]


def feature_units(family):
    suffixes = {"shape9_simtime4": TEMPORAL_UNITS, "shape9_edge3": GEOMETRY_CONTROL_UNITS,
                "shape9_dt_only": TEMPORAL_UNITS[:1]}
    if family not in suffixes:
        raise ValueError("unknown synthetic temporal feature family")
    return geometry_units("shape9") + suffixes[family]


def _cv(values):
    mean = float(np.mean(values))
    return float(np.std(values, ddof=0) / mean) if mean > 0 else np.nan


def compute_matrices(dataset):
    """Return (simulated timing N×4, within-part geometry control N×3).

    Coordinates and times from each part are differenced separately. A row
    without an eligible segment has NaN in every new field; zero mean segment
    length gives an undefined CV, not a fabricated zero. No fitting occurs.
    """
    validate_dataset(dataset)  # Requires source_type=synthetic/local_xy_m.
    times_out, geometry_out = [], []
    for row in dataset["records"]:
        intervals, lengths = [], []
        for part, part_times in zip(row["parts"], row["sim_times"]):
            if len(part) < 2:
                continue
            points = np.asarray(part, dtype=float)
            dt = np.diff(np.asarray(part_times, dtype=float))
            distance = np.linalg.norm(np.diff(points, axis=0), axis=1)
            intervals.extend(dt.tolist())
            lengths.extend(distance.tolist())
        if not intervals:
            times_out.append([np.nan] * 4)
            geometry_out.append([np.nan] * 3)
            continue
        intervals, lengths = np.asarray(intervals), np.asarray(lengths)
        speeds = lengths / intervals
        times_out.append([float(np.mean(intervals)), float(np.mean(speeds)),
                          float(np.var(speeds, ddof=0)), _cv(speeds)])
        geometry_out.append([float(np.mean(lengths)), float(np.var(lengths, ddof=0)), _cv(lengths)])
    return (np.asarray(times_out, dtype=float).reshape((-1, 4)),
            np.asarray(geometry_out, dtype=float).reshape((-1, 3)))


def feature_matrix(dataset, family):
    """Return shape9 plus one fixed timing/control bundle for S0 only."""
    temporal, geometric = compute_matrices(dataset)
    base = geometry_matrix(dataset["records"], "shape9")
    if family == "shape9_simtime4":
        return np.column_stack((base, temporal))
    if family == "shape9_edge3":
        return np.column_stack((base, geometric))
    if family == "shape9_dt_only":
        return np.column_stack((base, temporal[:, :1]))
    raise ValueError("unknown synthetic temporal feature family")
