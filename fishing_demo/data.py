"""Explicit synthetic trajectory contract; no original data or fishing-code labels."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = "fishing_sample_v1"
GENERATOR_VERSION = "1.0.0"
CLASS_NAMES = ["straight", "sweep", "turn"]
SPLITS = ("train", "validation", "calibration", "test", "stress")
DEFAULT_GROUP_COUNTS = dict(zip(SPLITS, (36, 12, 12, 12, 12)))
# Fixed before model selection; these changes preserve the path-type label.
STRESS_SHIFT = {
    "scale_multiplier": 2.6,
    "noise_multiplier": 5.0,
    "point_drop_probability": 0.24,
    "part_break_probability": 0.07,
}


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite JSON number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be a finite JSON number") from error
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite JSON number")
    return converted


def _json_values(value: Any, name: str) -> None:
    """Reject non-JSON values and non-finite numbers even in optional metadata."""
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        _number(value, name)
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _json_values(item, f"{name}[{index}]")
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for key, item in value.items():
            _json_values(item, f"{name}.{key}")
        return
    raise ValueError(f"{name} must contain JSON-compatible values")


def validate_record(record: dict) -> None:
    """Validate a record at the JSON boundary, retaining empty/zero paths for abstention."""
    if type(record) is not dict:
        raise ValueError("record must be an object")
    required = {"sample_id", "vessel_id", "split", "label", "parts", "sim_times", "scenario", "quality"}
    if not required <= record.keys():
        raise ValueError(f"record missing keys: {sorted(required - record.keys())}")
    for key in ("sample_id", "vessel_id"):
        if type(record[key]) is not str or not record[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    if type(record["split"]) is not str or record["split"] not in SPLITS:
        raise ValueError("unknown split")
    label = record["label"]
    if label is not None and (type(label) is not int or label not in (0, 1, 2)):
        raise ValueError("label must be 0, 1, 2, or null; booleans are not labels")
    if type(record["scenario"]) is not str or record["scenario"] not in ("base", "shift"):
        raise ValueError("scenario must be base or shift")
    expected_scenario = "shift" if record["split"] == "stress" else "base"
    if record["scenario"] != expected_scenario:
        raise ValueError("scenario does not match split")
    parts, times = record["parts"], record["sim_times"]
    if type(parts) is not list or type(times) is not list or len(parts) != len(times):
        raise ValueError("parts and sim_times must be aligned lists")
    previous_time = None
    observed_points = 0
    for part_index, (part, part_times) in enumerate(zip(parts, times)):
        if type(part) is not list or type(part_times) is not list or len(part) != len(part_times):
            raise ValueError(f"part {part_index} point/time lengths differ")
        for point_index, (point, instant) in enumerate(zip(part, part_times)):
            if type(point) is not list or len(point) != 2:
                raise ValueError(f"part {part_index} point {point_index} must be [x, y]")
            _number(point[0], "x")
            _number(point[1], "y")
            instant = _number(instant, "sim_time")
            if instant < 0 or (previous_time is not None and instant <= previous_time):
                raise ValueError("sim_times must be nonnegative and strictly increasing across parts")
            previous_time = instant
            observed_points += 1
    quality = record["quality"]
    if type(quality) is not dict:
        raise ValueError("quality must be an object")
    _json_values(record, "record")
    for key in ("original_points", "observed_points", "missing_points", "part_count"):
        if key in quality:
            _integer(quality[key], f"quality.{key}")
    if "observed_points" in quality and quality["observed_points"] != observed_points:
        raise ValueError("quality.observed_points disagrees with parts")
    if "part_count" in quality and quality["part_count"] != len(parts):
        raise ValueError("quality.part_count disagrees with parts")
    if "original_points" in quality:
        original = quality["original_points"]
        if original < observed_points:
            raise ValueError("original_points cannot be smaller than observed_points")
        missing = original - observed_points
        if "missing_points" in quality and quality["missing_points"] != missing:
            raise ValueError("quality.missing_points disagrees with original_points")
        if "missing_ratio" in quality:
            ratio = _number(quality["missing_ratio"], "quality.missing_ratio")
            expected = missing / original if original else 0.0
            if not math.isclose(ratio, expected, abs_tol=1e-12):
                raise ValueError("quality.missing_ratio disagrees with point counts")
    for key in ("missing_ratio", "point_drop_probability", "part_break_probability"):
        if key in quality and not 0 <= _number(quality[key], f"quality.{key}") <= 1:
            raise ValueError(f"quality.{key} must be in [0, 1]")


def validate_dataset(dataset: dict) -> None:
    if type(dataset) is not dict or "metadata" not in dataset or "records" not in dataset:
        raise ValueError("dataset must contain metadata and records")
    metadata, records = dataset["metadata"], dataset["records"]
    if type(metadata) is not dict or type(records) is not list:
        raise ValueError("metadata must be an object and records a list")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "source_type": "synthetic",
        "coordinate_system": "local_xy_m",
        "class_names": CLASS_NAMES,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"metadata.{key} must be {value!r}")
    _integer(metadata.get("seed"), "metadata.seed")
    if type(metadata.get("generator_version")) is not str or not metadata["generator_version"]:
        raise ValueError("metadata.generator_version is required")
    if type(metadata.get("assumptions")) is not dict:
        raise ValueError("metadata.assumptions is required")
    counts = metadata.get("split_group_counts")
    if type(counts) is not dict or set(counts) != set(SPLITS):
        raise ValueError("split_group_counts must declare all five splits")
    for split in SPLITS:
        _integer(counts[split], f"split_group_counts.{split}", 1)
    _json_values(metadata, "metadata")
    sample_ids, vessel_splits = set(), {}
    groups = {split: set() for split in SPLITS}
    for record in records:
        validate_record(record)
        sample_id, vessel_id, split = record["sample_id"], record["vessel_id"], record["split"]
        if sample_id in sample_ids:
            raise ValueError(f"duplicate sample_id: {sample_id}")
        sample_ids.add(sample_id)
        if vessel_id in vessel_splits and vessel_splits[vessel_id] != split:
            raise ValueError(f"vessel appears in multiple splits: {vessel_id}")
        vessel_splits[vessel_id] = split
        groups[split].add(vessel_id)
    for split in SPLITS:
        # Prediction may read a subset of the declared generation. Training
        # coverage belongs to the pipeline gate, not to the input validator.
        if len(groups[split]) > counts[split]:
            raise ValueError(f"{split} vessel count exceeds metadata")


def _path(label: int, rng: np.random.Generator, count: int) -> np.ndarray:
    """Path families deliberately overlap; classes describe geometry, not operations."""
    u = np.linspace(0.0, 1.0, count)
    sign = rng.choice((-1.0, 1.0))
    if label == 0:
        angle = sign * rng.uniform(0.0, 1.0)
        heading = angle * (u - 0.5) + rng.uniform(0.0, 0.18) * np.sin(2 * np.pi * u)
    elif label == 1:
        amplitude = rng.uniform(0.25, 1.3)
        cycles = rng.uniform(0.7, 1.6)
        phase = rng.uniform(-0.5, 0.5)
        heading = sign * amplitude * np.sin(2 * np.pi * cycles * u + phase)
    else:
        angle = sign * rng.uniform(0.75, 3.6)
        heading = angle * (u - 0.5) + rng.uniform(0.0, 0.12) * np.sin(2 * np.pi * u)
    steps = np.column_stack((np.cos(heading[:-1]), np.sin(heading[:-1])))
    return np.vstack((np.zeros(2), np.cumsum(steps, axis=0))) / (count - 1)


def generate_dataset(seed: int = 42, groups_per_split: dict | None = None, samples_per_class: int = 4) -> dict:
    _integer(seed, "seed")
    _integer(samples_per_class, "samples_per_class", 1)
    counts = DEFAULT_GROUP_COUNTS.copy() if groups_per_split is None else dict(groups_per_split)
    if set(counts) != set(SPLITS):
        raise ValueError("groups_per_split must contain all five split names")
    for split in SPLITS:
        _integer(counts[split], f"groups_per_split.{split}", 1)
    records = []
    group_seeds = iter(np.random.SeedSequence(seed).spawn(sum(counts.values())))
    for split in SPLITS:
        for group_index in range(counts[split]):
            group_seed = next(group_seeds)
            group_rng = np.random.default_rng(group_seed.spawn(1)[0])
            # All nuisance parameters are sampled once per vessel, before labels.
            group_scale = float(np.exp(group_rng.normal(0.0, 0.25)))
            group_orientation = group_rng.uniform(-np.pi, np.pi)
            group_noise = float(group_rng.uniform(0.18, 0.55))
            group_point_drop = float(group_rng.uniform(0.01, 0.06))
            group_part_break = float(group_rng.uniform(0.005, 0.025))
            origin = group_rng.uniform(-4000.0, 4000.0, 2)
            sample_seeds = iter(group_seed.spawn(3 * samples_per_class))
            vessel_id = f"S0-{split}-{group_index:03d}"
            for label in range(3):
                for sample_index in range(samples_per_class):
                    rng = np.random.default_rng(next(sample_seeds))
                    point_count = int(rng.integers(55, 86))
                    length = float(rng.uniform(800.0, 1600.0) * group_scale)
                    noise = group_noise
                    drop, part_break = group_point_drop, group_part_break
                    if split == "stress":
                        length *= STRESS_SHIFT["scale_multiplier"]
                        noise *= STRESS_SHIFT["noise_multiplier"]
                        drop = STRESS_SHIFT["point_drop_probability"]
                        part_break = STRESS_SHIFT["part_break_probability"]
                    orientation = group_orientation + rng.normal(0.0, 0.18)
                    rotation = np.array([[np.cos(orientation), -np.sin(orientation)],
                                         [np.sin(orientation), np.cos(orientation)]])
                    coordinates = _path(label, rng, point_count) * length
                    coordinates = coordinates @ rotation.T + origin
                    coordinates += rng.normal(0.0, noise, coordinates.shape)
                    # A missing observation creates a boundary: never bridge its gap.
                    keep = rng.random(point_count) >= drop
                    breaks = rng.random(point_count) < part_break
                    dt = float(rng.uniform(3.0, 8.0))  # simulation seconds, not sensor timestamps
                    parts, sim_times = [], []
                    current_points, current_times = [], []
                    for index in range(point_count):
                        if not keep[index] or (breaks[index] and current_points):
                            if current_points:
                                parts.append(current_points)
                                sim_times.append(current_times)
                                current_points, current_times = [], []
                        if keep[index]:
                            current_points.append(coordinates[index].tolist())
                            current_times.append(float(index * dt))
                    if current_points:
                        parts.append(current_points)
                        sim_times.append(current_times)
                    observed = int(keep.sum())
                    records.append({
                        "sample_id": f"{vessel_id}-{CLASS_NAMES[label]}-{sample_index:02d}",
                        "vessel_id": vessel_id, "split": split, "label": label,
                        "parts": parts, "sim_times": sim_times,
                        "scenario": "shift" if split == "stress" else "base",
                        "quality": {"original_points": point_count, "observed_points": observed,
                                    "missing_points": point_count - observed,
                                    "missing_ratio": (point_count - observed) / point_count,
                                    "part_count": len(parts), "point_drop_probability": drop,
                                    "part_break_probability": part_break},
                    })
    dataset = {"metadata": {
        "schema_version": SCHEMA_VERSION, "source_type": "synthetic",
        "coordinate_system": "local_xy_m", "class_names": CLASS_NAMES.copy(),
        "seed": seed, "generator_version": GENERATOR_VERSION,
        "split_group_counts": counts, "samples_per_class": samples_per_class,
        "assumptions": {
            "purpose": "S0 geometry learning demonstration; no official fishing labels or accident truth",
            "coordinates": "synthetic local XY metres",
            "time": "simulated seconds; no actual speed or acceleration is inferred",
            "group_nuisance": "scale, orientation, translation, noise, missingness and breaks are label-independent",
            "class_overlap": "straight turning span 0..1 rad, turn span 0.75..3.6 rad; sweep amplitude 0.25..1.3 rad",
            "parts": "missing observations and explicit breaks create distinct parts; no joining",
            "stress_shift": STRESS_SHIFT.copy(),
            "stress_label": "shift preserves the generating path family; no anomaly/accident label",
        },
    }, "records": records}
    validate_dataset(dataset)
    return dataset


def write_dataset(dataset: dict, path: str | Path) -> None:
    validate_dataset(dataset)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dataset, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_dataset(path: str | Path) -> dict:
    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON constant: {token}")

    dataset = json.loads(Path(path).read_text(encoding="utf-8-sig"),
                         object_pairs_hook=_unique_object, parse_constant=reject_constant)
    validate_dataset(dataset)
    return dataset
