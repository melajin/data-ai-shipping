# -*- coding: utf-8 -*-
"""Component 1: Harbor / Anchorage Geofence Masking.

Identifies home ports, anchorages, and harbor boundaries per vessel
using historical '정박정지' and '연안정지' coordinates.
Tags each observation row as 'in_harbor_zone' or 'is_offshore'.
"""
import os
import time
import json
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

HARBOR_RADIUS_KM = 2.0  # 2.0 km radius around any known mooring point


def latlon_to_cartesian(lat, lon):
    R = 6371.0  # km
    lat_r = np.radians(lat)
    lon_r = np.radians(lon)
    x = R * np.cos(lat_r) * np.cos(lon_r)
    y = R * np.cos(lat_r) * np.sin(lon_r)
    z = R * np.sin(lat_r)
    return np.column_stack([x, y, z])


def build_vessel_harbor_trees(df_all):
    """Builds a spatial KDTree of mooring locations for each vessel."""
    mooring_mask = df_all["state"].isin(["정박정지", "연안정지"]) & np.isfinite(df_all["cen_lat"]) & np.isfinite(df_all["cen_lon"])
    df_mooring = df_all[mooring_mask]
    
    vessel_trees = {}
    for vid, group in df_mooring.groupby("rfid_id"):
        coords = group[["cen_lat", "cen_lon"]].drop_duplicates().to_numpy()
        if len(coords) > 0:
            cart = latlon_to_cartesian(coords[:, 0], coords[:, 1])
            vessel_trees[vid] = cKDTree(cart)
            
    return vessel_trees


def tag_offshore_rows(df, vessel_trees, radius_km=HARBOR_RADIUS_KM):
    """Tags each row with distance to nearest harbor and is_offshore flag."""
    df["dist_to_mooring_km"] = np.nan
    df["is_offshore"] = True
    
    for vid, group in df.groupby("rfid_id"):
        tree = vessel_trees.get(vid)
        if tree is None:
            # If no mooring points known, fallback to state
            df.loc[group.index, "is_offshore"] = ~group["state"].isin(["정박정지", "연안정지"])
            continue
            
        valid_coords = np.isfinite(group["cen_lat"]) & np.isfinite(group["cen_lon"])
        sub = group[valid_coords]
        if len(sub) == 0:
            continue
            
        cart = latlon_to_cartesian(sub["cen_lat"].to_numpy(), sub["cen_lon"].to_numpy())
        dists, _ = tree.query(cart, k=1)
        
        idx = sub.index
        df.loc[idx, "dist_to_mooring_km"] = dists
        # Offshore if distance > radius and state is not mooring
        df.loc[idx, "is_offshore"] = (dists > radius_km) & (~sub["state"].isin(["정박정지", "연안정지"]))
        
    return df
