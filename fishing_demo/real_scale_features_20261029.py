#!/usr/bin/env python3
"""Scale features for real trajectories, 2026-10-29 cycle 2.

shape9 is scale invariant: every one of its nine values is a ratio, so two
records with identical form and a thousandfold size difference are
indistinguishable to it. This module records the size that shape9 discards.

Lengths are local-tangent polyline geometry in kilometres. They are not
distance travelled per unit time: the source gives no per-point timestamp, so
no speed or acceleration is derived here. ``rfid_time`` is an hour band, not a
coordinate timestamp. Separate MultiLineString parts are never joined.
"""
from __future__ import annotations

import math

import numpy as np

FEATURE_NAMES = (
    "log1p_total_length_km",
    "log1p_max_part_length_km",
    "log1p_mean_part_length_km",
    "log1p_bbox_diagonal_km",
    "log1p_radius_of_gyration_km",
    "log1p_mean_point_spacing_km",
    "log1p_part_count",
    "log1p_point_count",
)

_EARTH_RADIUS_KM = 6371.0088
_MAX_SPAN_DEG = 20.0


def _abstain(reason: str) -> dict:
    return {"valid": False, "reason": reason, "values": [None] * len(FEATURE_NAMES)}


def scale_features(parts: list) -> dict:
    """Return size statistics for ``parts: [part: [[lon, lat], ...]]``.

    Validity uses the same gate as shape9 so the two blocks share one mask:
    structurally sound parts with at least one positive-length polyline.
    """
    if not isinstance(parts, list) or not parts:
        return _abstain("empty")

    arrays: list[np.ndarray] = []
    for part in parts:
        if not isinstance(part, list) or len(part) == 0:
            return _abstain("invalid_part")
        try:
            points = np.asarray(part, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            return _abstain("invalid_coordinate")
        if points.ndim != 2 or points.shape[1] != 2:
            return _abstain("invalid_coordinate_shape")
        if not np.isfinite(points).all():
            return _abstain("nonfinite_coordinate")
        if np.any(np.abs(points[:, 0]) > 180) or np.any(np.abs(points[:, 1]) > 90):
            return _abstain("coordinate_out_of_range")
        if len(points) < 2:
            return _abstain("part_too_short")
        arrays.append(points)

    all_points = np.concatenate(arrays, axis=0)
    lon_span = float(np.ptp(all_points[:, 0]))
    lat_span = float(np.ptp(all_points[:, 1]))
    if lon_span > _MAX_SPAN_DEG or lat_span > _MAX_SPAN_DEG:
        return _abstain("spatial_span_exceeds_20_degrees")
    lon0, lat0 = (float(value) for value in all_points.mean(axis=0))
    if abs(lat0) > 85:
        return _abstain("mean_latitude_exceeds_85_degrees")

    # Same local tangent plane as shape9, then scaled to kilometres.
    x_scale = math.cos(math.radians(lat0)) * math.pi / 180.0 * _EARTH_RADIUS_KM
    y_scale = math.pi / 180.0 * _EARTH_RADIUS_KM
    projected = [
        np.column_stack(((part[:, 0] - lon0) * x_scale, (part[:, 1] - lat0) * y_scale))
        for part in arrays
    ]

    part_lengths = []
    segment_count = 0
    for points in projected:
        segments = np.diff(points, axis=0)
        part_lengths.append(float(np.hypot(segments[:, 0], segments[:, 1]).sum()))
        segment_count += len(segments)
    total_length = float(sum(part_lengths))
    if total_length <= 0:
        return _abstain("no_positive_length")

    cloud = np.concatenate(projected, axis=0)
    centered = cloud - cloud.mean(axis=0)
    gyration = math.sqrt(float(np.mean(np.sum(centered ** 2, axis=1))))
    diagonal = math.hypot(float(np.ptp(cloud[:, 0])), float(np.ptp(cloud[:, 1])))

    values = [
        math.log1p(total_length),
        math.log1p(max(part_lengths)),
        math.log1p(total_length / len(part_lengths)),
        math.log1p(diagonal),
        math.log1p(gyration),
        math.log1p(total_length / segment_count),
        math.log1p(len(part_lengths)),
        math.log1p(len(cloud)),
    ]
    if any(not math.isfinite(value) for value in values):
        return _abstain("nonfinite_scale")
    return {"valid": True, "reason": None, "values": values}
