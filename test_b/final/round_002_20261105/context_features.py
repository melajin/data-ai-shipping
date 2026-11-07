"""Context feature engineering module for Round 2.

Owned by Gemini.
Implements the contract v1 specification defined in CONTRACT.md and PROTOCOL.md:
- API: compute_features(frame: pandas.DataFrame) -> pandas.DataFrame
- Computes empirical two-tail rarity score U over rolling [t-720, t) history.
- Computes location-conditioned rarity score C over 0.05-degree cell history with 8-row fallback to U.
- Enforces strict history eligibility: n_history >= 24, distinct(ts // 24) >= 3, current geometry_valid.
- Preserves input columns, index, and row order without leakage of future rows, score, state, or accident info.
"""
from __future__ import annotations

import bisect
from collections import defaultdict, deque
import math
from typing import Any, Final

import numpy as np
import pandas as pd

WINDOW_HOURS: Final[int] = 720
MIN_HISTORY_ROWS: Final[int] = 24
MIN_HISTORY_DAYS: Final[int] = 3
MIN_CELL_HISTORY_ROWS: Final[int] = 8
CELL_SIZE_DEG: Final[float] = 0.05


def _is_geometry_valid(len_m: Any, bbox_m: Any) -> bool:
    """Return True if len_m and bbox_m are finite and >= 0."""
    if len_m is None or bbox_m is None:
        return False
    try:
        f_len = float(len_m)
        f_bbox = float(bbox_m)
    except (ValueError, TypeError):
        return False
    return (
        math.isfinite(f_len)
        and f_len >= 0.0
        and math.isfinite(f_bbox)
        and f_bbox >= 0.0
    )


def _is_location_valid(cen_lon: Any, cen_lat: Any) -> bool:
    """Return True if cen_lon and cen_lat are finite and within valid geographic bounds."""
    if cen_lon is None or cen_lat is None:
        return False
    try:
        f_lon = float(cen_lon)
        f_lat = float(cen_lat)
    except (ValueError, TypeError):
        return False
    return (
        math.isfinite(f_lon)
        and -180.0 <= f_lon <= 180.0
        and math.isfinite(f_lat)
        and -90.0 <= f_lat <= 90.0
    )


def _get_cell_key(cen_lon: float, cen_lat: float) -> tuple[int, int]:
    """Compute 0.05-degree grid cell coordinates (floor(lon / 0.05), floor(lat / 0.05))."""
    return (
        int(math.floor(float(cen_lon) / CELL_SIZE_DEG)),
        int(math.floor(float(cen_lat) / CELL_SIZE_DEG)),
    )


def _compute_rarity(sorted_vals: list[float], val: float) -> float:
    """Compute empirical two-tail rarity score:

    p = (count(< val) + 0.5 * count(== val)) / n
    r = 1.0 - 2.0 * min(p, 1.0 - p)
    Tied constant distribution returns exactly 0.0. Range is bounded in [0.0, 1.0].
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    count_lt = bisect.bisect_left(sorted_vals, val)
    count_le = bisect.bisect_right(sorted_vals, val)
    count_eq = count_le - count_lt
    p = (count_lt + 0.5 * count_eq) / n
    r = 1.0 - 2.0 * min(p, 1.0 - p)
    return max(0.0, min(1.0, r))


class _VesselRollingHistory:
    """Maintains bounded rolling [t-720, t) history for a single vessel.

    Guarantees:
    - O(log N) percentile rank queries and inserts.
    - O(1) distinct day tracking via frequency dictionary.
    - O(log N_cell) cell-conditioned history queries.
    - Inclusive left boundary (keeps ts >= t - 720).
    - Zero state leakage across vessel RFIDs.
    """

    __slots__ = (
        "deque",
        "sorted_lens",
        "sorted_bboxes",
        "day_counts",
        "cell_deques",
        "cell_sorted_lens",
        "cell_sorted_bboxes",
    )

    def __init__(self) -> None:
        self.deque: deque[tuple[int, float, float, bool, tuple[int, int] | None]] = deque()
        self.sorted_lens: list[float] = []
        self.sorted_bboxes: list[float] = []
        self.day_counts: dict[int, int] = defaultdict(int)
        self.cell_deques: dict[tuple[int, int], deque[tuple[int, float, float]]] = defaultdict(deque)
        self.cell_sorted_lens: dict[tuple[int, int], list[float]] = defaultdict(list)
        self.cell_sorted_bboxes: dict[tuple[int, int], list[float]] = defaultdict(list)

    def prune_before(self, min_ts: int) -> None:
        """Evict history rows strictly older than min_ts (keeps ts >= min_ts)."""
        d = self.deque
        lens = self.sorted_lens
        bboxes = self.sorted_bboxes
        day_counts = self.day_counts
        cell_deques = self.cell_deques
        cell_lens = self.cell_sorted_lens
        cell_bboxes = self.cell_sorted_bboxes

        while d and d[0][0] < min_ts:
            ts, log_l, log_b, has_cell, cell_key = d.popleft()

            # Evict from overall sorted lists
            idx_l = bisect.bisect_left(lens, log_l)
            del lens[idx_l]
            idx_b = bisect.bisect_left(bboxes, log_b)
            del bboxes[idx_b]

            # Evict from day counter
            day = ts // 24
            day_counts[day] -= 1
            if day_counts[day] == 0:
                del day_counts[day]

            # Evict from cell history
            if has_cell and cell_key is not None:
                cell_deques[cell_key].popleft()
                del cell_lens[cell_key][bisect.bisect_left(cell_lens[cell_key], log_l)]
                del cell_bboxes[cell_key][bisect.bisect_left(cell_bboxes[cell_key], log_b)]
                if not cell_deques[cell_key]:
                    del cell_deques[cell_key]
                    del cell_lens[cell_key]
                    del cell_bboxes[cell_key]

    def add(
        self,
        ts: int,
        log_l: float,
        log_b: float,
        has_cell: bool,
        cell_key: tuple[int, int] | None,
    ) -> None:
        """Append one geometry_valid representative row to history."""
        self.deque.append((ts, log_l, log_b, has_cell, cell_key))
        bisect.insort(self.sorted_lens, log_l)
        bisect.insort(self.sorted_bboxes, log_b)
        self.day_counts[ts // 24] += 1
        if has_cell and cell_key is not None:
            self.cell_deques[cell_key].append((ts, log_l, log_b))
            bisect.insort(self.cell_sorted_lens[cell_key], log_l)
            bisect.insort(self.cell_sorted_bboxes[cell_key], log_b)


def compute_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute context and history rarity features adhering to CONTRACT v1.

    Parameters
    ----------
    frame : pandas.DataFrame
        Input dataframe containing at minimum:
        ['rfid_id', 'ts', 'len_m', 'bbox_m', 'cen_lon', 'cen_lat'].
        Optionally contains 'source_ordinal' for intra-timestamp tie-breaking.

    Returns
    -------
    pandas.DataFrame
        Copy of input frame with original row order, index, and columns preserved,
        plus 7 additional columns:
        - n_history (int64)
        - history_days (int64)
        - history_eligible (bool)
        - n_cell_history (int64)
        - context_used (bool)
        - U (float64)
        - C (float64)
    """
    required_cols = {"rfid_id", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat"}
    missing = required_cols - set(frame.columns)
    if missing:
        raise ValueError(f"Input DataFrame is missing required columns: {sorted(missing)}")

    n_rows = len(frame)
    if n_rows == 0:
        res = frame.copy()
        res["n_history"] = np.array([], dtype="int64")
        res["history_days"] = np.array([], dtype="int64")
        res["history_eligible"] = np.array([], dtype="bool")
        res["n_cell_history"] = np.array([], dtype="int64")
        res["context_used"] = np.array([], dtype="bool")
        res["U"] = np.array([], dtype="float64")
        res["C"] = np.array([], dtype="float64")
        return res

    # Extract column arrays efficiently without pandas overhead
    rfid_arr = frame["rfid_id"].to_numpy()
    ts_arr = pd.to_numeric(frame["ts"], errors="raise").to_numpy(dtype=np.int64)
    len_arr = pd.to_numeric(frame["len_m"], errors="coerce").to_numpy(dtype=np.float64)
    bbox_arr = pd.to_numeric(frame["bbox_m"], errors="coerce").to_numpy(dtype=np.float64)
    lon_arr = pd.to_numeric(frame["cen_lon"], errors="coerce").to_numpy(dtype=np.float64)
    lat_arr = pd.to_numeric(frame["cen_lat"], errors="coerce").to_numpy(dtype=np.float64)

    if "source_ordinal" in frame.columns:
        ord_arr = pd.to_numeric(frame["source_ordinal"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
    else:
        ord_arr = np.zeros(n_rows, dtype=np.int64)

    # Preallocate output arrays in original row order
    out_n_history = np.zeros(n_rows, dtype=np.int64)
    out_history_days = np.zeros(n_rows, dtype=np.int64)
    out_history_eligible = np.zeros(n_rows, dtype=bool)
    out_n_cell_history = np.zeros(n_rows, dtype=np.int64)
    out_context_used = np.zeros(n_rows, dtype=bool)
    out_u = np.full(n_rows, np.nan, dtype=np.float64)
    out_c = np.full(n_rows, np.nan, dtype=np.float64)

    # Group row positions by RFID to guarantee strict vessel separation
    vessel_groups: dict[Any, list[int]] = defaultdict(list)
    for pos in range(n_rows):
        vessel_groups[rfid_arr[pos]].append(pos)

    # Process each vessel independently
    for _rfid, positions in vessel_groups.items():
        # Sort positions chronologically by ts, then source_ordinal, then original position
        positions.sort(key=lambda idx: (ts_arr[idx], ord_arr[idx], idx))

        history = _VesselRollingHistory()

        # Group positions by timestamp ts
        i = 0
        total_pos = len(positions)
        while i < total_pos:
            current_ts = ts_arr[positions[i]]
            group_indices: list[int] = []
            while i < total_pos and ts_arr[positions[i]] == current_ts:
                group_indices.append(positions[i])
                i += 1

            # 1. Prune history window to [current_ts - 720, current_ts)
            # Left bound is inclusive: keep rows where ts >= current_ts - 720
            history.prune_before(current_ts - WINDOW_HOURS)

            n_hist = len(history.deque)
            h_days = len(history.day_counts)

            # 2. Evaluate features for each row at current_ts against history
            # Current rows never see themselves or contemporaneous rows
            for pos in group_indices:
                l_val = len_arr[pos]
                b_val = bbox_arr[pos]
                lon_val = lon_arr[pos]
                lat_val = lat_arr[pos]

                geom_ok = _is_geometry_valid(l_val, b_val)
                loc_ok = _is_location_valid(lon_val, lat_val)

                cell_key: tuple[int, int] | None = None
                n_cell = 0
                if loc_ok:
                    cell_key = _get_cell_key(lon_val, lat_val)
                    if cell_key in history.cell_sorted_lens:
                        n_cell = len(history.cell_sorted_lens[cell_key])

                eligible = (n_hist >= MIN_HISTORY_ROWS) and (h_days >= MIN_HISTORY_DAYS) and geom_ok

                out_n_history[pos] = n_hist
                out_history_days[pos] = h_days
                out_history_eligible[pos] = eligible
                out_n_cell_history[pos] = n_cell

                if not eligible:
                    out_context_used[pos] = False
                    out_u[pos] = np.nan
                    out_c[pos] = np.nan
                else:
                    log_l = math.log1p(l_val)
                    log_b = math.log1p(b_val)

                    # Compute empirical two-tail U over general history
                    r_len = _compute_rarity(history.sorted_lens, log_l)
                    r_bbox = _compute_rarity(history.sorted_bboxes, log_b)
                    u_score = (r_len + r_bbox) / 2.0
                    out_u[pos] = u_score

                    # Compute conditional C if location valid and >= 8 cell history rows
                    if loc_ok and cell_key is not None and n_cell >= MIN_CELL_HISTORY_ROWS:
                        c_lens = history.cell_sorted_lens[cell_key]
                        c_bboxes = history.cell_sorted_bboxes[cell_key]
                        r_c_len = _compute_rarity(c_lens, log_l)
                        r_c_bbox = _compute_rarity(c_bboxes, log_b)
                        out_c[pos] = (r_c_len + r_c_bbox) / 2.0
                        out_context_used[pos] = True
                    else:
                        out_c[pos] = u_score
                        out_context_used[pos] = False

            # 3. History update: select the time-representative row for current_ts
            # Per contract: row with minimum source_ordinal represents current_ts
            # Because group_indices is already sorted by (ord_arr, idx), the first row is representative
            rep_pos = group_indices[0]
            rep_l = len_arr[rep_pos]
            rep_b = bbox_arr[rep_pos]

            if _is_geometry_valid(rep_l, rep_b):
                rep_lon = lon_arr[rep_pos]
                rep_lat = lat_arr[rep_pos]
                rep_loc_ok = _is_location_valid(rep_lon, rep_lat)
                rep_cell = _get_cell_key(rep_lon, rep_lat) if rep_loc_ok else None
                history.add(
                    current_ts,
                    math.log1p(rep_l),
                    math.log1p(rep_b),
                    rep_loc_ok,
                    rep_cell,
                )

    # Attach computed columns while preserving input DataFrame columns and index
    result = frame.copy()
    result["n_history"] = out_n_history
    result["history_days"] = out_history_days
    result["history_eligible"] = out_history_eligible
    result["n_cell_history"] = out_n_cell_history
    result["context_used"] = out_context_used
    result["U"] = out_u
    result["C"] = out_c

    return result
