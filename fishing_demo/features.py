"""Eight geometry-only descriptors without linking separate trajectory parts."""

from __future__ import annotations

import math

import numpy as np

from .data import validate_record

FEATURE_NAMES = (
    "log1p_total_length_m", "mean_part_straightness", "mean_abs_turn_rad",
    "turn_direction_concentration", "std_turn_rad", "max_abs_turn_rad",
    "mean_part_spread_ratio", "mean_part_chord_deviation_ratio",
)
FEATURE_UNITS = (
    "ln(1 + length / 1 m)", "dimensionless", "rad", "dimensionless", "rad", "rad",
    "dimensionless", "dimensionless",
)


def extract_features(record: dict) -> dict:
    validate_record(record)
    parts_summary, straightnesses, spreads, deviations, turns = [], [], [], [], []
    usable_parts = 0
    for part in record["parts"]:
        points = np.asarray(part, dtype=float).reshape((-1, 2))
        segments = np.diff(points, axis=0)
        lengths = np.hypot(segments[:, 0], segments[:, 1])
        length = float(lengths.sum())
        displacement = float(np.linalg.norm(points[-1] - points[0])) if len(points) > 1 else 0.0
        straightness = displacement / length if length > 0 else None
        parts_summary.append({"length_m": length, "displacement_m": displacement,
                              "straightness": straightness})
        if length <= 0:
            continue
        usable_parts += 1
        straightnesses.append(straightness)
        # Repeated coordinates do not define a heading; remove only zero segments.
        vectors = segments[lengths > 0]
        if len(vectors) > 1:
            before, after = vectors[:-1], vectors[1:]
            cross = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
            dot = np.sum(before * after, axis=1)
            turns.extend(np.arctan2(cross, dot).tolist())
        centered = points - points.mean(axis=0)
        eigenvalues = np.linalg.eigvalsh(centered.T @ centered / len(points))
        spreads.append(math.sqrt(max(float(eigenvalues[0]), 0.0) / float(eigenvalues[1]))
                       if eigenvalues[1] > 0 else 0.0)
        chord = points[-1] - points[0]
        if displacement > 0:
            relative = points - points[0]
            cross_distances = abs(relative[:, 0] * chord[1] - relative[:, 1] * chord[0]) / displacement
            deviations.append(float(cross_distances.max()) / length)
        else:
            # A closed part has no unique chord direction, so this feature is missing.
            deviations.append(None)
    total_length = sum(part["length_m"] for part in parts_summary)
    quality = dict(record["quality"])
    quality.update({"observed_points": sum(map(len, record["parts"])),
                    "part_count": len(record["parts"]), "usable_part_count": usable_parts,
                    "turn_count": len(turns)})
    if not usable_parts or total_length <= 0:
        return {"values": [None] * len(FEATURE_NAMES), "valid": False,
                "reason": "no_positive_length_parts", "parts": parts_summary, "quality": quality}
    angles = np.asarray(turns, dtype=float)
    absolute = np.abs(angles)
    total_turn = float(absolute.sum())
    available_deviations = [value for value in deviations if value is not None]
    values = [math.log1p(total_length), float(np.mean(straightnesses)),
              float(absolute.mean()) if len(angles) else None,
              abs(float(angles.sum())) / total_turn if total_turn > 0 else (0.0 if len(angles) else None),
              float(angles.std()) if len(angles) else None,
              float(absolute.max()) if len(angles) else None,
              float(np.mean(spreads)),
              float(np.mean(available_deviations)) if available_deviations else None]
    if any(value is not None and not math.isfinite(value) for value in values):
        return {"values": [None] * len(FEATURE_NAMES), "valid": False,
                "reason": "nonfinite_geometry", "parts": parts_summary, "quality": quality}
    return {"values": values, "valid": True, "reason": None,
            "parts": parts_summary, "quality": quality}


def feature_matrix(records: list[dict]) -> tuple[np.ndarray, list[dict]]:
    extracted = [extract_features(record) for record in records]
    values = [[np.nan if value is None else value for value in item["values"]] for item in extracted]
    return np.asarray(values, dtype=float).reshape((len(records), len(FEATURE_NAMES))), extracted
