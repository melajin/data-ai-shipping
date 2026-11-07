"""Explicit frozen Test B baseline, preserved without training or source imports.

Provenance is recorded in model/provenance.json: source SHA256 and original
line ranges. Original run_008_testB_20261101.py constants/scorer/helpers and
run_remeasure_20261031.py scalar haversine are copied explicitly. Changes only:
remeasure.haversine_m -> local haversine_m, remeasure.EARTH_R -> local EARTH_R.
No raw points are connected and centroid separation is never called speed.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_R = 6_371_000.0
GRID_HARBOR = 0.005
GRID_FINE = 0.01
GRID_COARSE = 0.05
T5_MIN_VESSELS = 3
MIN_HIST_FOR_CHANGE = 24
STOP_LEN_M = 50.0
STOP_BBOX_M = 100.0
HARBOR_NEAR_M = 1000.0
MOORING_NEAR_M = 1000.0
SEA_STOP_FAR_M = 2000.0
MOVE_LEN_M = 3000.0
MOVE_STRAIGHT = 0.6
NIGHT_HOURS = (20, 21, 22, 23, 0, 1, 2, 3)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def haversine_vec(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def build_quantile_normalizer(values: np.ndarray):
    ref = np.sort(np.asarray(values, dtype=float))
    ref = ref[~np.isnan(ref)]

    def norm(v):
        v = np.asarray(v, dtype=float)
        out = np.searchsorted(ref, v, side="right") / max(1, len(ref))
        return np.clip(out, 0.0, 1.0)
    return norm, {"n_ref": int(len(ref)), "p50": float(np.median(ref)) if len(ref) else None}


def lookup_density(lon, lat, dens_map01, dens_map05):
    c01 = (int(math.floor(lon / GRID_FINE)), int(math.floor(lat / GRID_FINE)))
    if c01 in dens_map01 and dens_map01[c01] >= T5_MIN_VESSELS:
        return dens_map01[c01]
    c05 = (int(math.floor(lon / GRID_COARSE)), int(math.floor(lat / GRID_COARSE)))
    if c05 in dens_map05:
        return dens_map05[c05]
    return 0.0


def robust_z(x, hist):
    hist = hist[~np.isnan(hist)]
    if len(hist) == 0:
        return np.nan
    med = np.median(hist)
    iqr = np.percentile(hist, 75) - np.percentile(hist, 25)
    scale = iqr / 1.349 if iqr > 0 else (np.std(hist) if np.std(hist) > 0 else 1.0)
    return abs(x - med) / scale if scale > 0 else 0.0


def squash(z):
    if z is None or (isinstance(z, float) and np.isnan(z)):
        return np.nan
    return float(1.0 - math.exp(-abs(z) / 2.0))


def score_vessel(sub: pd.DataFrame, nearest_harbor_m, own_moorings_train_lookup_unused,
                 dens_map01, dens_map05, norm_gap, norm_jump, norm_dist_cap_km=20.0):
    """The original fixed scorer; sub is one vessel in timestamp/source order."""
    n = len(sub)
    lon = sub["cen_lon"].to_numpy()
    lat = sub["cen_lat"].to_numpy()
    len_m = sub["len_m"].to_numpy()
    bbox_m = sub["bbox_m"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        straight = np.where(len_m > 0, bbox_m / len_m, np.nan)
    ts = sub["ts"].to_numpy()
    rtime = sub["rfid_time"].to_numpy()
    stop = (len_m <= STOP_LEN_M) & (bbox_m <= STOP_BBOX_M)
    harbor_dist = nearest_harbor_m(lon, lat)

    visited = set()
    own_night_stop_cells: dict = {}
    s_zone = np.full(n, np.nan)
    s_change = np.full(n, np.nan)
    s_gap = np.full(n, np.nan)
    state = np.full(n, "", dtype=object)
    hist_len_m, hist_straight, hist_state = [], [], []

    for i in range(n):
        mooring_pts = sorted(own_night_stop_cells.items(), key=lambda kv: -kv[1])[:3]
        mooring_dist_i = min((haversine_m(lon[i], lat[i],
                             (c[0] + 0.5) * GRID_HARBOR, (c[1] + 0.5) * GRID_HARBOR)
                             for c, _ in mooring_pts), default=math.inf)
        if stop[i]:
            near = (harbor_dist[i] <= HARBOR_NEAR_M) or (mooring_dist_i <= MOORING_NEAR_M)
            far = (harbor_dist[i] >= SEA_STOP_FAR_M) and (mooring_dist_i >= SEA_STOP_FAR_M)
            state[i] = "정박정지" if near else ("해상정지" if far else "연안정지")
        else:
            if (len_m[i] > MOVE_LEN_M) and (not np.isnan(straight[i])) and (straight[i] >= MOVE_STRAIGHT):
                state[i] = "이동"
            else:
                state[i] = "저속굴곡"

        cell = (int(math.floor(lon[i] / GRID_FINE)), int(math.floor(lat[i] / GRID_FINE)))
        if cell in visited:
            dist_km = 0.0
        elif visited:
            dmin = min(haversine_m(lon[i], lat[i], (c[0] + 0.5) * GRID_FINE,
                                  (c[1] + 0.5) * GRID_FINE) for c in visited)
            dist_km = dmin / 1000.0
        else:
            dist_km = 0.0
        comp_a = min(dist_km / norm_dist_cap_km, 1.0)
        density = lookup_density(lon[i], lat[i], dens_map01, dens_map05)
        comp_b = 1.0 - min(density / 3.0, 1.0) if density else 1.0
        s_zone[i] = 0.5 * comp_a + 0.5 * comp_b

        if len(hist_len_m) >= MIN_HIST_FOR_CHANGE:
            z1 = robust_z(len_m[i], np.array(hist_len_m))
            z2 = robust_z(straight[i], np.array(hist_straight)) if not np.isnan(straight[i]) else np.nan
            prior_freq = float(np.mean(np.array(hist_state) == state[i]))
            surprise = 1.0 - prior_freq
            parts = [p for p in (squash(z1), squash(z2), surprise)
                     if not (isinstance(p, float) and np.isnan(p))]
            s_change[i] = float(np.mean(parts)) if parts else np.nan

        if i > 0:
            gap_h = float(ts[i] - ts[i - 1])
            jump_m = haversine_m(lon[i - 1], lat[i - 1], lon[i], lat[i])
            s_gap[i] = float(0.5 * norm_gap(gap_h) + 0.5 * norm_jump(jump_m))

        visited.add(cell)
        if stop[i] and rtime[i] in NIGHT_HOURS:
            mc = (int(math.floor(lon[i] / GRID_HARBOR)), int(math.floor(lat[i] / GRID_HARBOR)))
            own_night_stop_cells[mc] = own_night_stop_cells.get(mc, 0) + 1
        hist_len_m.append(len_m[i])
        hist_straight.append(straight[i])
        hist_state.append(state[i])

    out = sub.copy()
    out["state"] = state
    out["s_zone"] = s_zone
    out["s_change"] = s_change
    out["s_gap"] = s_gap
    comps = np.vstack([s_zone, s_change, s_gap])
    with np.errstate(invalid="ignore"):
        score = np.nanmean(comps, axis=0)
    all_missing = np.all(np.isnan(comps), axis=0)
    score[all_missing] = np.nan
    score[~all_missing] = np.clip(score[~all_missing], 1e-6, 1.0)
    out["score"] = score
    return out


def load_references(directory: Path):
    """Load trusted portable snapshots only; no pickle or training at runtime."""
    harbor = json.loads((directory / "harbors.json").read_text(encoding="utf-8"))
    points = np.asarray(harbor["points"], dtype=float)
    mx = 111320.0 * np.cos(np.radians(harbor["meta"]["ref_lat"]))
    my = 110540.0
    tree = cKDTree(points * np.array([mx, my])) if len(points) else None

    def nearest(lons, lats):
        lons, lats = np.asarray(lons, dtype=float), np.asarray(lats, dtype=float)
        if tree is None or not len(lons):
            return np.full(len(lons), np.inf)
        _, idx = tree.query(np.column_stack([lons * mx, lats * my]), k=1)
        selected = points[idx]
        return haversine_vec(lons, lats, selected[:, 0], selected[:, 1])

    density = json.loads((directory / "density.json").read_text(encoding="utf-8"))
    fine = {(int(x), int(y)): float(n) for x, y, n in density["fine"]}
    coarse = {(int(x), int(y)): float(n) for x, y, n in density["coarse"]}
    norm_gap, gap_meta = build_quantile_normalizer(np.load(directory / "gap_reference.npy", allow_pickle=False))
    norm_jump, jump_meta = build_quantile_normalizer(np.load(directory / "jump_reference.npy", allow_pickle=False))
    return nearest, fine, coarse, norm_gap, norm_jump, {"gap": gap_meta, "jump": jump_meta,
                                                      "harbor_count": len(points)}
