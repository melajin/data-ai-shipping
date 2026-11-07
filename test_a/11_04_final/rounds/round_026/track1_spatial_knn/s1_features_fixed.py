from __future__ import annotations

"""S1 spatial posterior features with Prior-Smoothing and Min-Vessels bug fixes.

Fixes the Round025 bug where uniform [0.25, 0.25, 0.25, 0.25] smoothing with alpha=5.0
and total > 1e-15 artificially inflated minority classes on sparse cells.
Replaces uniform smoothing with fold-local train prior:
    (adjusted + alpha * prior) / (total + alpha)
and enforces distinct_vessels >= min_vessels before accepting fine-grid posterior.
"""

import gc
import math
import sqlite3
import numpy as np
from pathlib import Path
from typing import Sequence

RESOLUTIONS = (0.01, 0.05, 0.10)
N_CLASSES = 4

FEATURE_NAMES_BASE = tuple(
    name
    for res in RESOLUTIONS
    for name in (
        *(f"s1_full_r{int(round(res * 100)):03d}_c{c}" for c in range(N_CLASSES)),
        *(f"s1_month_range_r{int(round(res * 100)):03d}_c{c}" for c in range(N_CLASSES)),
    )
)

FEATURE_NAMES_EXCESS = tuple(
    f"s1_excess_r{int(round(res * 100)):03d}_c{c}"
    for res in RESOLUTIONS
    for c in range(N_CLASSES)
)


class S1ProfileStore:
    """View over S1 profile SQLite cache."""

    def __init__(self, sqlite_path: Path):
        self.path = Path(sqlite_path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"S1 profile SQLite cache not found: {self.path}")
        with sqlite3.connect(str(self.path)) as connection:
            self.n_rows = int(connection.execute("SELECT MAX(vessel_idx) + 1 FROM profile_count").fetchone()[0])

    def period_profiles(self, month: int) -> list[list[dict[tuple[int, int], float]]]:
        if month not in (0, 1, 2, 3, 4, 5, 6):
            raise ValueError("Period must be full(0) or Jan-Jun(1..6)")
        profiles = [[{} for _ in range(self.n_rows)] for _ in RESOLUTIONS]
        totals = [np.zeros(self.n_rows, dtype=np.float64) for _ in RESOLUTIONS]
        with sqlite3.connect(str(self.path)) as connection:
            cursor = connection.execute(
                "SELECT vessel_idx,res_idx,cell_x,cell_y,observations FROM profile_count "
                "WHERE month=? ORDER BY res_idx,vessel_idx,cell_x,cell_y", (month,)
            )
            for vessel_idx, res_idx, cell_x, cell_y, observations in cursor:
                idx, resolution = int(vessel_idx), int(res_idx)
                cell = (int(cell_x), int(cell_y))
                count = float(observations)
                profiles[resolution][idx][cell] = count
                totals[resolution][idx] += count
        for res_idx in range(len(RESOLUTIONS)):
            for vessel_idx, cells in enumerate(profiles[res_idx]):
                total = totals[res_idx][vessel_idx]
                if total > 0:
                    for cell in list(cells):
                        cells[cell] /= total
        return profiles


def _build_counts(
    period_profiles: list[list[dict[tuple[int, int], float]]],
    train_indices: np.ndarray,
    train_labels: np.ndarray,
    res_idx: int,
) -> dict[tuple[int, int], list[float]]:
    counts: dict[tuple[int, int], list[float]] = {}
    for vessel_idx, cls in zip(train_indices.tolist(), train_labels.tolist()):
        profile = period_profiles[res_idx][int(vessel_idx)]
        for cell in profile:
            entry = counts.get(cell)
            if entry is None:
                entry = [0.0, 0.0, 0.0, 0.0]
                counts[cell] = entry
            entry[int(cls)] += 1.0
    return counts


def _posterior_for_cell(
    period_profiles: list[list[dict[tuple[int, int], float]]],
    counts_by_res: Sequence[dict[tuple[int, int], list[float]]],
    train_label_by_index: dict[int, int],
    prior: np.ndarray,
    query_idx: int,
    requested_res_idx: int,
    requested_cell: tuple[int, int],
    alpha: float,
    min_vessels: int,
) -> np.ndarray:
    query_is_fit = query_idx in train_label_by_index
    cell_x, cell_y = requested_cell
    res_idx = requested_res_idx
    while True:
        counts = counts_by_res[res_idx].get((cell_x, cell_y))
        adjusted = np.asarray(counts if counts is not None else [0.0] * N_CLASSES, dtype=np.float64)
        if query_is_fit:
            if period_profiles[res_idx][query_idx].get((cell_x, cell_y), 0.0) > 0:
                adjusted[train_label_by_index[query_idx]] -= 1.0
        adjusted = np.maximum(adjusted, 0.0)
        total = float(adjusted.sum())
        if total >= min_vessels:
            return (adjusted + alpha * prior) / (total + alpha)
        if res_idx >= len(RESOLUTIONS) - 1:
            if total > 0:
                return (adjusted + alpha * prior) / (total + alpha)
            return prior
        factor = int(round(RESOLUTIONS[res_idx + 1] / RESOLUTIONS[res_idx]))
        cell_x = math.floor(cell_x / factor)
        cell_y = math.floor(cell_y / factor)
        res_idx += 1


def build_fixed_features(
    store: S1ProfileStore,
    query_indices: Sequence[int],
    train_indices: Sequence[int],
    train_labels: Sequence[int],
    alpha: float = 2.0,
    min_vessels: int = 3,
    include_excess: bool = False,
) -> np.ndarray:
    query_indices = np.asarray(query_indices, dtype=np.int64)
    train_indices = np.asarray(train_indices, dtype=np.int64)
    train_labels = np.asarray(train_labels, dtype=np.int64)

    train_label_by_index = {int(i): int(y) for i, y in zip(train_indices.tolist(), train_labels.tolist())}
    global_counts = np.bincount(train_labels, minlength=N_CLASSES).astype(np.float64)

    feature_dim = 24 + (12 if include_excess else 0)
    output = np.full((len(query_indices), feature_dim), np.nan, dtype=np.float32)
    query_position = {int(v): pos for pos, v in enumerate(query_indices.tolist())}

    periods: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    month_min: dict[tuple[int, int], np.ndarray] = {}
    month_max: dict[tuple[int, int], np.ndarray] = {}

    for month in periods:
        period_profiles = store.period_profiles(month)
        counts_by_res = [_build_counts(period_profiles, train_indices, train_labels, r) for r in range(len(RESOLUTIONS))]

        for res_idx in range(len(RESOLUTIONS)):
            full_feature_start = res_idx * 8
            if month == 0:
                for query_idx in query_indices.tolist():
                    profile = period_profiles[res_idx][int(query_idx)]
                    if not profile:
                        continue
                    prior_counts = global_counts.copy()
                    if query_idx in train_label_by_index:
                        prior_counts[train_label_by_index[query_idx]] -= 1.0
                    prior = prior_counts / prior_counts.sum() if prior_counts.sum() > 0 else np.full(4, 0.25)

                    value = np.zeros(N_CLASSES, dtype=np.float64)
                    for cell, weight in profile.items():
                        post = _posterior_for_cell(
                            period_profiles, counts_by_res, train_label_by_index,
                            prior, int(query_idx), res_idx, cell, alpha, min_vessels
                        )
                        value += weight * post
                    pos = query_position[int(query_idx)]
                    output[pos, full_feature_start:full_feature_start + 4] = value.astype(np.float32)
                    if include_excess:
                        excess_start = 24 + res_idx * 4
                        output[pos, excess_start:excess_start + 4] = (value - prior).astype(np.float32)
            else:
                month_values: dict[int, np.ndarray] = {}
                for query_idx in query_indices.tolist():
                    profile = period_profiles[res_idx][int(query_idx)]
                    if not profile:
                        continue
                    prior_counts = global_counts.copy()
                    if query_idx in train_label_by_index:
                        prior_counts[train_label_by_index[query_idx]] -= 1.0
                    prior = prior_counts / prior_counts.sum() if prior_counts.sum() > 0 else np.full(4, 0.25)

                    value = np.zeros(N_CLASSES, dtype=np.float64)
                    for cell, weight in profile.items():
                        post = _posterior_for_cell(
                            period_profiles, counts_by_res, train_label_by_index,
                            prior, int(query_idx), res_idx, cell, alpha, min_vessels
                        )
                        value += weight * post
                    month_values[int(query_idx)] = value

                for query_idx, value in month_values.items():
                    old_min = month_min.setdefault((res_idx, query_idx), value.copy())
                    old_max = month_max.setdefault((res_idx, query_idx), value.copy())
                    np.minimum(old_min, value, out=old_min)
                    np.maximum(old_max, value, out=old_max)

        if month > 0:
            del month_values
        del period_profiles, counts_by_res
        gc.collect()

    for res_idx in range(len(RESOLUTIONS)):
        start = res_idx * 8 + 4
        for query_idx in query_indices.tolist():
            low = month_min.get((res_idx, int(query_idx)))
            high = month_max.get((res_idx, int(query_idx)))
            if low is not None and high is not None:
                output[query_position[int(query_idx)], start:start + 4] = (high - low).astype(np.float32)

    return output
