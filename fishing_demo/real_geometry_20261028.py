"""Geometry-only shape9 features for real longitude/latitude line parts.

This module intentionally accepts no timestamps or synthetic-record metadata.
Coordinates are X=longitude, Y=latitude based on the competition attachment;
the exact datum/EPSG remains unconfirmed. Returned geometry is angular and is
not a metric distance or speed measurement.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


FEATURE_NAMES = (
    "mean_part_straightness",
    "mean_abs_turn_rad",
    "turn_direction_concentration",
    "std_turn_rad",
    "max_abs_turn_rad",
    "mean_part_spread_ratio",
    "mean_part_chord_deviation_ratio",
    "cloud_spread_ratio",
    "cloud_radial_fourth_moment_ratio",
)

_PROJECTIONS = ("local_tangent", "degree_control")
_MAX_SPAN_DEG = 20.0


def _coordinate_assumption(projection: str) -> dict:
    if projection == "local_tangent":
        return {
            "projection": projection,
            "coordinate_order": "[longitude, latitude]",
            "origin": "arithmetic mean of all observed points in this record",
            "formula": "x=(lon-lon0)*pi/180*cos(lat0*pi/180); y=(lat-lat0)*pi/180",
            "units": "angular tangent coordinates; Earth radius omitted",
            "datum_epsg": "unconfirmed",
            "metric_distance_or_speed": False,
        }
    return {
        "projection": projection,
        "coordinate_order": "[longitude, latitude]",
        "origin": "arithmetic mean of all observed points in this record",
        "formula": "x=lon-lon0; y=lat-lat0",
        "units": "degrees",
        "datum_epsg": "unconfirmed",
        "metric_distance_or_speed": False,
    }


def _result(valid: bool, reason: str | None, values: list[float | None], projection: str) -> dict:
    return {
        "valid": valid,
        "reason": reason,
        "values": values,
        "feature_names": FEATURE_NAMES,
        "coordinate_assumption": _coordinate_assumption(projection),
    }


def _abstain(reason: str, projection: str) -> dict:
    return _result(False, reason, [None] * len(FEATURE_NAMES), projection)


def _shape9_from_projected_parts(parts: Sequence[np.ndarray]) -> dict:
    """Compute shape9 from already-projected XY parts; never joins part edges."""
    straightnesses: list[float] = []
    spreads: list[float] = []
    deviations: list[float | None] = []
    turns: list[float] = []
    observed = [part for part in parts if len(part)]
    if not observed:
        return {"valid": False, "reason": "empty", "values": [None] * 9}

    usable_parts = 0
    for points in observed:
        if len(points) < 2:
            return {"valid": False, "reason": "part_too_short", "values": [None] * 9}
        segments = np.diff(points, axis=0)
        lengths = np.hypot(segments[:, 0], segments[:, 1])
        total_length = float(lengths.sum())
        if total_length <= 0:
            continue
        usable_parts += 1
        displacement = float(np.linalg.norm(points[-1] - points[0]))
        straightnesses.append(displacement / total_length)

        vectors = segments[lengths > 0]
        if len(vectors) > 1:
            before, after = vectors[:-1], vectors[1:]
            cross = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
            dot = np.sum(before * after, axis=1)
            turns.extend(np.arctan2(cross, dot).tolist())

        centered = points - points.mean(axis=0)
        eigenvalues = np.linalg.eigvalsh(centered.T @ centered / len(points))
        spreads.append(
            math.sqrt(max(float(eigenvalues[0]), 0.0) / float(eigenvalues[1]))
            if eigenvalues[1] > 0 else 0.0
        )
        if displacement > 0:
            chord = points[-1] - points[0]
            relative = points - points[0]
            cross_distances = np.abs(relative[:, 0] * chord[1] - relative[:, 1] * chord[0]) / displacement
            deviations.append(float(cross_distances.max()) / total_length)
        else:
            deviations.append(None)

    if not usable_parts:
        return {"valid": False, "reason": "no_positive_length", "values": [None] * 9}

    angles = np.asarray(turns, dtype=np.float64)
    absolute = np.abs(angles)
    total_turn = float(absolute.sum())
    available_deviations = [value for value in deviations if value is not None]
    values: list[float | None] = [
        float(np.mean(straightnesses)),
        float(absolute.mean()) if len(angles) else None,
        abs(float(angles.sum())) / total_turn if total_turn > 0 else (0.0 if len(angles) else None),
        float(angles.std()) if len(angles) else None,
        float(absolute.max()) if len(angles) else None,
        float(np.mean(spreads)),
        float(np.mean(available_deviations)) if available_deviations else None,
    ]

    # Cloud statistics use observed points only. Concatenating point sets does
    # not create a path segment between separate parts.
    points = np.concatenate(observed, axis=0)
    centered = points - points.mean(axis=0)
    magnitude = float(np.max(np.abs(centered)))
    if magnitude == 0:
        values.extend([None, None])
    else:
        normalized = centered / magnitude
        covariance = normalized.T @ normalized / len(normalized)
        eigenvalues = np.linalg.eigvalsh(covariance)
        if eigenvalues[-1] <= 0:
            values.extend([None, None])
        else:
            spread = math.sqrt(max(float(eigenvalues[0]), 0.0) / float(eigenvalues[-1]))
            radius_squared = np.sum(normalized ** 2, axis=1)
            second_moment = float(np.mean(radius_squared))
            fourth_ratio = float(np.mean(radius_squared ** 2)) / second_moment ** 2
            values.extend([spread, fourth_ratio])

    if any(value is not None and not math.isfinite(value) for value in values):
        return {"valid": False, "reason": "nonfinite_geometry", "values": [None] * 9}
    return {"valid": True, "reason": None, "values": values}


def geometry_features(parts: list, projection: str = "local_tangent") -> dict:
    """Return real-trajectory shape9 from ``parts: [part: [[lon, lat], ...]]``.

    ``degree_control`` preserves raw degree geometry for a development
    sensitivity comparison. Spatial spans over 20 degrees and mean latitude
    beyond 85 degrees abstain by design; these are explicit research bounds,
    not geodetic guarantees.
    """
    if projection not in _PROJECTIONS:
        raise ValueError(f"projection must be one of {_PROJECTIONS}")
    if not isinstance(parts, list):
        return _abstain("invalid_parts", projection)
    if not parts or not any(isinstance(part, list) and len(part) > 0 for part in parts):
        return _abstain("empty", projection)

    arrays: list[np.ndarray] = []
    for part in parts:
        if not isinstance(part, list):
            return _abstain("invalid_part", projection)
        if len(part) == 0:
            arrays.append(np.empty((0, 2), dtype=np.float64))
            continue
        try:
            points = np.asarray(part, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            return _abstain("invalid_coordinate", projection)
        if points.ndim != 2 or points.shape[1] != 2:
            return _abstain("invalid_coordinate_shape", projection)
        if not np.isfinite(points).all():
            return _abstain("nonfinite_coordinate", projection)
        if np.any(points[:, 0] < -180) or np.any(points[:, 0] > 180):
            return _abstain("longitude_out_of_range", projection)
        if np.any(points[:, 1] < -90) or np.any(points[:, 1] > 90):
            return _abstain("latitude_out_of_range", projection)
        arrays.append(points)

    # A one-point line is malformed structure even if another part is usable.
    if any(0 < len(part) < 2 for part in arrays):
        return _abstain("part_too_short", projection)
    observed = [part for part in arrays if len(part)]
    if not observed:
        return _abstain("empty", projection)
    all_points = np.concatenate(observed, axis=0)
    lon_span = float(np.ptp(all_points[:, 0]))
    lat_span = float(np.ptp(all_points[:, 1]))
    lon0, lat0 = (float(value) for value in all_points.mean(axis=0))
    if lon_span > _MAX_SPAN_DEG or lat_span > _MAX_SPAN_DEG:
        return _abstain("spatial_span_exceeds_20_degrees", projection)
    if abs(lat0) > 85:
        return _abstain("mean_latitude_exceeds_85_degrees", projection)

    lon_factor = math.pi / 180.0 if projection == "local_tangent" else 1.0
    lat_factor = math.pi / 180.0 if projection == "local_tangent" else 1.0
    x_scale = math.cos(math.radians(lat0)) if projection == "local_tangent" else 1.0
    projected = [
        np.column_stack(((part[:, 0] - lon0) * lon_factor * x_scale,
                         (part[:, 1] - lat0) * lat_factor))
        if len(part) else np.empty((0, 2), dtype=np.float64)
        for part in arrays
    ]
    result = _shape9_from_projected_parts(projected)
    return _result(result["valid"], result["reason"], result["values"], projection)

