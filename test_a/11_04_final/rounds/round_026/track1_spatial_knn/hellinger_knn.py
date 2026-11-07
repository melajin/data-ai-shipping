from __future__ import annotations

"""Vessel-to-Vessel Multi-resolution Hellinger kNN Feature Extractor.

Features:
- D = 0.35*H001 + 0.35*H005 + 0.15*Hhour + 0.15*home_term (reduced to 0.85 when home is missing)
- D_spatial = 0.5*H001 + 0.5*H005
- K in [5, 15, 30] distance-weighted neighbor class probabilities smoothed with fold train prior
- D_spatial K=15 neighbor class probabilities smoothed with fold train prior
- Neighbor statistics: d_min, d_top5_mean, entropy, margin, radius_km_p50, radius_km_p90
Total: 22 features.
Strict leak-prevention: Leave-One-Out (diagonal/matching ID = inf), gallery restricted to fold FIT only.
"""

import gc
from pathlib import Path
from typing import Sequence
import numpy as np
import pandas as pd
import scipy.sparse as sp

SUMMARY_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\26_11_2\work\재식별_투트랙_001r1\s6_fingerprint_summary.parquet")
GRID_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\26_11_2\work\재식별_투트랙_001r1\s6_fingerprint_grid.parquet")
N_CLASSES = 4

KNN_FEATURE_NAMES = (
    # K=5 probs (4)
    *(f"knn_k05_prob_c{c}" for c in range(N_CLASSES)),
    # K=15 probs (4)
    *(f"knn_k15_prob_c{c}" for c in range(N_CLASSES)),
    # K=30 probs (4)
    *(f"knn_k30_prob_c{c}" for c in range(N_CLASSES)),
    # Pure spatial K=15 probs (4)
    *(f"knn_spatial_k15_prob_c{c}" for c in range(N_CLASSES)),
    # Summary & distance stats (6)
    "knn_d_min",
    "knn_d_top5_mean",
    "knn_entropy_k15",
    "knn_margin_k15",
    "knn_radius_km_p50",
    "knn_radius_km_p90",
)


def haversine_km(lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    r = 6371.0088
    lon1r, lat1r, lon2r, lat2r = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2r - lon1r
    dlat = lat2r - lat1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    return (2.0 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))).astype(np.float32)


class HellingerKnnFeatureExtractor:
    """Manages 2026 vessel fingerprints and extracts multi-resolution Hellinger kNN features."""

    def __init__(self, summary_path: Path = SUMMARY_PATH, grid_path: Path = GRID_PATH):
        # 1. Load 2026 full summary
        df_sum = pd.read_parquet(summary_path)
        df_sum = df_sum[(df_sum["year"] == 2026) & (df_sum["block"] == "full")].drop_duplicates("id").copy()
        df_sum["id"] = df_sum["id"].astype(str)
        self.summary_df = df_sum.set_index("id")

        # 2. Load 2026 full grid
        df_grid = pd.read_parquet(grid_path)
        df_grid = df_grid[(df_grid["year"] == 2026) & (df_grid["block"] == "full")].copy()
        df_grid["id"] = df_grid["id"].astype(str)
        self.grid_df = df_grid

        # 3. Build shared vocabulary for 0.01 and 0.05
        sub001 = self.grid_df[self.grid_df["res"] == 0.01]
        unique_cells_001 = sub001["cell"].unique()
        self.vocab001 = {c: i for i, c in enumerate(unique_cells_001)}
        self.n_cells001 = len(unique_cells_001)

        sub005 = self.grid_df[self.grid_df["res"] == 0.05]
        unique_cells_005 = sub005["cell"].unique()
        self.vocab005 = {c: i for i, c in enumerate(unique_cells_005)}
        self.n_cells005 = len(unique_cells_005)

        # Hour columns
        self.hour_cols = [f"hour_{h:02d}" for h in range(24)]

    def _build_sparse_grid(self, ids: Sequence[str], res: float, vocab: dict, n_cells: int) -> sp.csr_matrix:
        n = len(ids)
        idx_of = {v: i for i, v in enumerate(ids)}
        sub = self.grid_df[(self.grid_df["res"] == res) & (self.grid_df["id"].isin(idx_of))]
        if len(sub) == 0:
            return sp.csr_matrix((n, n_cells), dtype=np.float32)
        rows = sub["id"].map(idx_of).values.astype(np.int32)
        cols = sub["cell"].map(vocab).fillna(-1).values.astype(np.int32)
        valid = cols >= 0
        rows = rows[valid]
        cols = cols[valid]
        vals = np.sqrt(np.clip(sub["weight"].values[valid], 0.0, None)).astype(np.float32)
        return sp.csr_matrix((vals, (rows, cols)), shape=(n, n_cells), dtype=np.float32)

    def extract_features(
        self,
        query_ids: Sequence[str],
        gallery_ids: Sequence[str],
        gallery_labels: Sequence[int],
        is_leave_one_out: bool = True,
    ) -> np.ndarray:
        """Extract 22 kNN features for query_ids against gallery_ids."""
        q_ids = [str(v) for v in query_ids]
        g_ids = [str(v) for v in gallery_ids]
        g_y = np.asarray(gallery_labels, dtype=np.int64)

        if len(g_ids) != len(g_y):
            raise ValueError("Gallery IDs and labels length mismatch")

        n_query = len(q_ids)
        n_gallery = len(g_ids)

        # Prior distribution of gallery
        gallery_bincount = np.bincount(g_y, minlength=N_CLASSES).astype(np.float64)
        prior = gallery_bincount / gallery_bincount.sum() if gallery_bincount.sum() > 0 else np.full(4, 0.25)

        # 1. Hour distribution sqrt
        q_sum = self.summary_df.reindex(q_ids)
        g_sum = self.summary_df.reindex(g_ids)

        q_hour = q_sum[self.hour_cols].fillna(0.0).values.astype(np.float32)
        g_hour = g_sum[self.hour_cols].fillna(0.0).values.astype(np.float32)
        q_hour_sqrt = np.sqrt(np.clip(q_hour, 0.0, None))
        g_hour_sqrt = np.sqrt(np.clip(g_hour, 0.0, None))

        # 2. Grid sparse matrices
        q_g001 = self._build_sparse_grid(q_ids, 0.01, self.vocab001, self.n_cells001)
        g_g001 = self._build_sparse_grid(g_ids, 0.01, self.vocab001, self.n_cells001)

        q_g005 = self._build_sparse_grid(q_ids, 0.05, self.vocab005, self.n_cells005)
        g_g005 = self._build_sparse_grid(g_ids, 0.05, self.vocab005, self.n_cells005)

        # 3. Inner products & Hellinger distances
        IP001 = (q_g001 @ g_g001.T).toarray()
        H001 = np.sqrt(np.clip(1.0 - np.clip(IP001, 0.0, 1.0), 0.0, None)).astype(np.float32)
        del IP001, q_g001, g_g001
        gc.collect()

        IP005 = (q_g005 @ g_g005.T).toarray()
        H005 = np.sqrt(np.clip(1.0 - np.clip(IP005, 0.0, 1.0), 0.0, None)).astype(np.float32)
        del IP005, q_g005, g_g005
        gc.collect()

        IPhour = (q_hour_sqrt @ g_hour_sqrt.T).astype(np.float32)
        Hhour = np.sqrt(np.clip(1.0 - np.clip(IPhour, 0.0, 1.0), 0.0, None)).astype(np.float32)
        del IPhour, q_hour_sqrt, g_hour_sqrt
        gc.collect()

        # 4. Home distance
        q_lon = q_sum["home_lon"].fillna(0.0).values.astype(np.float32)
        q_lat = q_sum["home_lat"].fillna(0.0).values.astype(np.float32)
        q_has_home = q_sum["has_home"].fillna(False).values.astype(bool)

        g_lon = g_sum["home_lon"].fillna(0.0).values.astype(np.float32)
        g_lat = g_sum["home_lat"].fillna(0.0).values.astype(np.float32)
        g_has_home = g_sum["has_home"].fillna(False).values.astype(bool)

        home_km = haversine_km(q_lon[:, None], q_lat[:, None], g_lon[None, :], g_lat[None, :])
        home_valid = (q_has_home[:, None] & g_has_home[None, :])
        home_term = np.where(home_valid, np.minimum(home_km / 50.0, 1.0), 0.0).astype(np.float32)
        del home_km
        gc.collect()

        # 5. Combined distance D & pure spatial distance D_spatial
        full_formula = 0.35 * H001 + 0.35 * H005 + 0.15 * Hhour + 0.15 * home_term
        reduced_formula = (0.35 * H001 + 0.35 * H005 + 0.15 * Hhour) / 0.85
        D = np.where(home_valid, full_formula, reduced_formula).astype(np.float32)
        D_spatial = (0.5 * H001 + 0.5 * H005).astype(np.float32)
        del full_formula, reduced_formula, home_term, home_valid, H001, H005, Hhour
        gc.collect()

        # 6. Strict Leave-One-Out Masking: if query is in gallery, self distance = inf
        if is_leave_one_out:
            g_pos_map = {vid: j for j, vid in enumerate(g_ids)}
            for i, qid in enumerate(q_ids):
                j = g_pos_map.get(qid)
                if j is not None:
                    D[i, j] = np.inf
                    D_spatial[i, j] = np.inf

        # 7. Extract kNN features
        features = np.zeros((n_query, len(KNN_FEATURE_NAMES)), dtype=np.float32)

        # Sort indices for D
        sorted_idx_D = np.argsort(D, axis=1)
        sorted_D = np.take_along_axis(D, sorted_idx_D, axis=1)

        # (A) K in [5, 15, 30] for combined D
        for k_idx, K in enumerate([5, 15, 30]):
            top_idx = sorted_idx_D[:, :K]
            top_d = sorted_D[:, :K]
            weights = 1.0 / (top_d + 0.02) ** 2  # (n_query, K)
            # Normalize class weights
            sum_w_class = np.zeros((n_query, N_CLASSES), dtype=np.float32)
            for c in range(N_CLASSES):
                mask = (g_y[top_idx] == c)
                sum_w_class[:, c] = np.sum(weights * mask, axis=1)
            sum_w = np.sum(weights, axis=1, keepdims=True)
            # Smoothed with gallery prior: (sum_w_class + 1.0 * prior) / (sum_w + 1.0)
            p_k = (sum_w_class + 1.0 * prior) / (sum_w + 1.0)
            col_start = k_idx * 4
            features[:, col_start:col_start + 4] = p_k

        # (B) Pure spatial D_spatial for K=15
        sorted_idx_sp = np.argsort(D_spatial, axis=1)
        sorted_sp = np.take_along_axis(D_spatial, sorted_idx_sp, axis=1)
        top_sp_idx = sorted_idx_sp[:, :15]
        top_sp_d = sorted_sp[:, :15]
        sp_weights = 1.0 / (top_sp_d + 0.02) ** 2
        sum_sp_w_class = np.zeros((n_query, N_CLASSES), dtype=np.float32)
        for c in range(N_CLASSES):
            mask = (g_y[top_sp_idx] == c)
            sum_sp_w_class[:, c] = np.sum(sp_weights * mask, axis=1)
        sum_sp_w = np.sum(sp_weights, axis=1, keepdims=True)
        p_sp15 = (sum_sp_w_class + 1.0 * prior) / (sum_sp_w + 1.0)
        features[:, 12:16] = p_sp15
        del sorted_idx_sp, sorted_sp, top_sp_idx, top_sp_d, sp_weights, sum_sp_w_class, sum_sp_w
        gc.collect()

        # (C) Distance statistics & uncertainty
        d_min = sorted_D[:, 0]
        d_top5_mean = np.mean(sorted_D[:, :5], axis=1)

        p15 = features[:, 4:8]  # K=15 probs
        entropy = -np.sum(p15 * np.log(np.clip(p15, 1e-12, 1.0)), axis=1)

        sorted_p15 = np.sort(p15, axis=1)
        margin = sorted_p15[:, -1] - sorted_p15[:, -2]

        r50 = q_sum["radius_km_p50"].fillna(0.0).values.astype(np.float32)
        r90 = q_sum["radius_km_p90"].fillna(0.0).values.astype(np.float32)

        features[:, 16] = d_min
        features[:, 17] = d_top5_mean
        features[:, 18] = entropy
        features[:, 19] = margin
        features[:, 20] = r50
        features[:, 21] = r90

        del D, D_spatial, sorted_idx_D, sorted_D
        gc.collect()

        return features
