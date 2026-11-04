"""Geometry-only feature families for the separate S0 iteration experiment.

Public contract: ``feature_matrix(records, family)`` returns a float64 array
of shape (len(records), len(feature_names(family))). Column order and units
come from ``feature_names`` and ``feature_units``. Missing values are NaN.
Record validity is *exactly* ``features.extract_features(record)['valid']``;
an invalid record produces an all-NaN row in every family. Callers must retain
that existing validity mask, including valid rows missing optional turns.

``original8`` is unchanged. ``shape7`` drops only absolute log length.
``shape9`` appends two dimensionless statistics of all observed points, without
creating any connecting segment. ``shape15`` appends six within-part turning
statistics at 8/16 normalized arc-length locations, maximized over eligible
parts. Only consecutive duplicate coordinates are removed for resampling;
revisits such as A -> B -> A remain part of the path. Optional new features
never change record validity, and no metadata supplies a feature value.
"""
from __future__ import annotations

import numpy as np

from .features import FEATURE_NAMES, FEATURE_UNITS, extract_features


FAMILIES = ("original8", "shape7", "shape9", "shape15")
_CLOUD_NAMES = ("cloud_spread_ratio", "cloud_radial_fourth_moment_ratio")
_ARC_NAMES = tuple(f"max_part_arc{count}_{summary}_rad"
                   for count in (8, 16)
                   for summary in ("total_abs_turn", "abs_net_turn", "cumulative_turn_range"))
_NAMES = {
    "original8": tuple(FEATURE_NAMES),
    "shape7": tuple(FEATURE_NAMES[1:]),
    "shape9": tuple(FEATURE_NAMES[1:]) + _CLOUD_NAMES,
    "shape15": tuple(FEATURE_NAMES[1:]) + _CLOUD_NAMES + _ARC_NAMES,
}
_UNITS = {
    "original8": tuple(FEATURE_UNITS),
    "shape7": tuple(FEATURE_UNITS[1:]),
    "shape9": tuple(FEATURE_UNITS[1:]) + ("dimensionless",) * 2,
    "shape15": tuple(FEATURE_UNITS[1:]) + ("dimensionless",) * 2 + ("rad",) * 6,
}


def _check_family(family):
    if not isinstance(family, str) or family not in FAMILIES:
        raise ValueError(f"unknown feature family; choose one of {', '.join(FAMILIES)}")


def feature_names(family: str) -> tuple[str, ...]:
    """Return immutable column names in the exact matrix order."""
    _check_family(family)
    return _NAMES[family]


def feature_units(family: str) -> tuple[str, ...]:
    """Return units aligned one-to-one with ``feature_names(family)``."""
    _check_family(family)
    return _UNITS[family]


def _cloud_features(parts):
    # Concatenating a point set adds no edges, interpolation or path length.
    observed = [np.asarray(part, dtype=np.float64).reshape((-1, 2))
                for part in parts if part]
    if not observed:
        return [np.nan, np.nan]
    points = np.concatenate(observed, axis=0)
    centered = points - points.mean(axis=0)
    magnitude = float(np.max(np.abs(centered)))
    if not np.isfinite(magnitude):
        raise ValueError("nonfinite cloud centering in iteration features")
    if magnitude == 0:
        return [np.nan, np.nan]
    # Normalizing before powers protects the dimensionless ratios from scale
    # overflow. This does not fit or learn a normalization from other records.
    normalized = centered / magnitude
    covariance = normalized.T @ normalized / len(normalized)
    eigenvalues = np.linalg.eigvalsh(covariance)
    if not np.isfinite(eigenvalues).all():
        raise ValueError("nonfinite cloud covariance in iteration features")
    if eigenvalues[-1] <= 0:
        return [np.nan, np.nan]
    spread = np.sqrt(max(float(eigenvalues[0]), 0.0) / float(eigenvalues[-1]))
    radius_squared = np.sum(normalized ** 2, axis=1)
    second_moment = float(np.mean(radius_squared))
    fourth_ratio = float(np.mean(radius_squared ** 2)) / second_moment ** 2
    return [float(spread), fourth_ratio]


def _resampled_turns(part, count):
    points = np.asarray(part, dtype=np.float64).reshape((-1, 2))
    if len(points) < 3:
        return None
    # Consecutive zeros have no direction. Removing later revisits would erase
    # reversals and loops, so they are intentionally retained.
    keep = np.r_[True, np.any(points[1:] != points[:-1], axis=1)]
    points = points[keep]
    if len(points) < 3:
        return None
    relative = points - points[0]
    magnitude = float(np.max(np.abs(relative)))
    if not np.isfinite(magnitude):
        raise ValueError("nonfinite within-part centering in iteration features")
    if magnitude == 0:
        return None
    normalized = relative / magnitude
    edges = np.diff(normalized, axis=0)
    lengths = np.hypot(edges[:, 0], edges[:, 1])
    cumulative = np.r_[0.0, np.cumsum(lengths)]
    total = float(cumulative[-1])
    if not np.isfinite(total):
        raise ValueError("nonfinite within-part arc length in iteration features")
    if total <= 0:
        return None
    position = cumulative / total
    locations = np.linspace(0.0, 1.0, count)
    samples = np.column_stack([np.interp(locations, position, normalized[:, axis])
                               for axis in range(2)])
    vectors = np.diff(samples, axis=0)
    vectors = vectors[np.hypot(vectors[:, 0], vectors[:, 1]) > 0]
    if len(vectors) < 2:
        return None
    before, after = vectors[:-1], vectors[1:]
    cross = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
    dot = np.sum(before * after, axis=1)
    angles = np.arctan2(cross, dot)
    signed_cumulative = np.r_[0.0, np.cumsum(angles)]
    values = np.asarray([np.abs(angles).sum(), abs(float(angles.sum())),
                         np.ptp(signed_cumulative)], dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite resampled turns in iteration features")
    return values


def _arc_features(parts):
    values = []
    for count in (8, 16):
        eligible = [_resampled_turns(part, count) for part in parts]
        eligible = [summary for summary in eligible if summary is not None]
        # Each summary gets its own maximum. No short-part denominator dilutes
        # the turning signal and no signed turn is summed across boundaries.
        values.extend(np.max(eligible, axis=0).tolist() if eligible else [np.nan] * 3)
    return values


def feature_matrix(records: list[dict], family: str) -> np.ndarray:
    """Extract an N by D geometry matrix without fitting or mutating records.

    Input validation and base validity are delegated to the original extractor.
    Every family therefore uses the same evaluable records. New NaNs only mark
    missing optional statistics and must be handled by train-only imputation.
    """
    names = feature_names(family)
    rows = []
    for record in records:
        original = extract_features(record)
        if not original["valid"]:
            rows.append([np.nan] * len(names))
            continue
        base = [np.nan if value is None else value for value in original["values"]]
        if family == "original8":
            values = base
        else:
            values = base[1:]
            if family in ("shape9", "shape15"):
                values += _cloud_features(record["parts"])
            if family == "shape15":
                values += _arc_features(record["parts"])
        rows.append(values)
    return np.asarray(rows, dtype=np.float64).reshape((len(rows), len(names)))
