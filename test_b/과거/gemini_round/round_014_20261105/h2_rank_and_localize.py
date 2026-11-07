# -*- coding: utf-8 -*-
"""Component 3: Hypothesis Ranking and Localization Module.

Supports executing different hypothesis configurations:
- 'hyp_A_offshore_sea_stop': Ranked by longest offshore sea stop streak.
- 'hyp_B_hierarchical_cascade': Priority cascade (Offshore stop >= 2h -> Cruising drop -> Towing -> Remainder).
- 'hyp_C_speed_drop_steepness': Ranked by offshore speed drop ratio and magnitude.
- 'hyp_D_towing_straightness': Ranked by post-incident towing straightness and speed uniformity.
- 'hyp_E_borda_ensemble': Borda count rank aggregation across A, B, C, D.
- 'hyp_F_score_fusion': Fused ranking (Drop + Top3 Anomaly Score + Span + Stop Streak) + Rule A localization.
- 'hyp_G_multislot_ensemble': Score & Drop weighted ensemble with localized candidate slots.
"""
import numpy as np
import pandas as pd
from scipy import stats


def rank_series(series):
    n = len(series)
    if n <= 1 or series.max() == series.min():
        return np.zeros(n, dtype=float)
    ranks = pd.Series(series).rank(method="average").to_numpy()
    return (ranks - 1.0) / (n - 1.0)


def rank_and_localize_vessel(group, hypothesis_name):
    """Selects top-1 voyage and localized timestamp for a single vessel group."""
    n_voy = len(group)
    group = group.sort_values("voy").reset_index(drop=True)
    
    # ----------------- Hypothesis A: Offshore Sea Stop -----------------
    if hypothesis_name == "hyp_A_offshore_sea_stop":
        score = group["f1_offshore_stop_streak"].to_numpy()
        best_idx = int(np.argmax(score))
        top = group.iloc[best_idx]
        
        t_stop = top["t_offshore_stop_start"]
        t_pred = int(t_stop) if pd.notna(t_stop) and top["f1_offshore_stop_streak"] > 0 else int(top["t_mid"])
        method = "offshore_stop" if pd.notna(t_stop) and top["f1_offshore_stop_streak"] > 0 else "midpoint"
        return int(top["voy"]), float(score[best_idx]), t_pred, method, bool(top["is_accident_related"])

    # ----------------- Hypothesis B: Hierarchical Cascade -----------------
    elif hypothesis_name == "hyp_B_hierarchical_cascade":
        mask_t1 = group["f1_offshore_stop_streak"] >= 2.0
        mask_t2 = group["f2_offshore_speed_drop"] >= 2000.0
        mask_t3 = group["f3_straightness"] >= 0.5
        
        if np.any(mask_t1):
            sub = group[mask_t1]
            best_idx = sub["f1_offshore_stop_streak"].idxmax()
            top = group.loc[best_idx]
            t_pred = int(top["t_offshore_stop_start"]) if pd.notna(top["t_offshore_stop_start"]) else int(top["t_mid"])
            method = "cascade_t1_sea_stop"
        elif np.any(mask_t2):
            sub = group[mask_t2]
            best_idx = sub["f2_offshore_speed_drop"].idxmax()
            top = group.loc[best_idx]
            t_pred = int(top["t_offshore_drop"]) if pd.notna(top["t_offshore_drop"]) else int(top["t_mid"])
            method = "cascade_t2_speed_drop"
        elif np.any(mask_t3):
            sub = group[mask_t3]
            best_idx = sub["f3_straightness"].idxmax()
            top = group.loc[best_idx]
            t_pred = int(top["t_mid"])
            method = "cascade_t3_towing"
        else:
            best_idx = group["f1_any_stop_streak"].idxmax()
            top = group.loc[best_idx]
            t_pred = int(top["t_mid"])
            method = "cascade_fallback"
            
        return int(top["voy"]), 1.0, t_pred, method, bool(top["is_accident_related"])

    # ----------------- Hypothesis C: Speed Drop Steepness Ratio -----------------
    elif hypothesis_name == "hyp_C_speed_drop_steepness":
        r_drop = rank_series(group["f2_offshore_speed_drop"].to_numpy())
        r_ratio = rank_series(group["f2_speed_drop_ratio"].to_numpy())
        score = 0.6 * r_drop + 0.4 * r_ratio
        best_idx = int(np.argmax(score))
        top = group.iloc[best_idx]
        
        t_drop = top["t_offshore_drop"]
        t_pred = int(t_drop) if pd.notna(t_drop) and top["f2_offshore_speed_drop"] > 0 else int(top["t_mid"])
        method = "speed_drop_steepness" if pd.notna(t_drop) and top["f2_offshore_speed_drop"] > 0 else "midpoint"
        return int(top["voy"]), float(score[best_idx]), t_pred, method, bool(top["is_accident_related"])

    # ----------------- Hypothesis D: Towing Straightness -----------------
    elif hypothesis_name == "hyp_D_towing_straightness":
        r_str = rank_series(group["f3_straightness"].to_numpy())
        score = r_str
        best_idx = int(np.argmax(score))
        top = group.iloc[best_idx]
        
        t_pred = int(top["t_mid"])
        method = "towing_straightness_mid"
        return int(top["voy"]), float(score[best_idx]), t_pred, method, bool(top["is_accident_related"])

    # ----------------- Hypothesis E: Multi-Hypothesis Borda Ensemble -----------------
    elif hypothesis_name == "hyp_E_borda_ensemble":
        r_a = rank_series(group["f1_offshore_stop_streak"].to_numpy())
        r_b_t1 = (group["f1_offshore_stop_streak"] >= 2.0).astype(float).to_numpy()
        r_c = rank_series(group["f2_offshore_speed_drop"].to_numpy())
        r_d = rank_series(group["f3_straightness"].to_numpy())
        
        score = 0.35 * r_a + 0.25 * r_b_t1 + 0.25 * r_c + 0.15 * r_d
        best_idx = int(np.argmax(score))
        top = group.iloc[best_idx]
        
        t_stop = top["t_offshore_stop_start"]
        t_drop = top["t_offshore_drop"]
        if pd.notna(t_stop) and top["f1_offshore_stop_streak"] >= 2.0:
            t_pred = int(t_stop)
            method = "borda_stop"
        elif pd.notna(t_drop) and top["f2_offshore_speed_drop"] >= 1500.0:
            t_pred = int(t_drop)
            method = "borda_drop"
        else:
            t_pred = int(top["t_mid"])
            method = "borda_mid"
            
        return int(top["voy"]), float(score[best_idx]), t_pred, method, bool(top["is_accident_related"])

    # ----------------- Hypothesis F: Multi-Feature Score Fusion -----------------
    elif hypothesis_name == "hyp_F_score_fusion":
        r_drop = rank_series(group["f2_offshore_speed_drop"].to_numpy())
        r_ratio = rank_series(group["f2_speed_drop_ratio"].to_numpy())
        r_sc = rank_series(group["top3_score"].to_numpy()) if "top3_score" in group.columns else np.zeros(n_voy)
        r_span = rank_series(group["voy_span"].to_numpy())
        r_stop = rank_series(group["f1_any_stop_streak"].to_numpy())
        
        score = 0.40 * r_drop + 0.10 * r_ratio + 0.20 * r_sc + 0.20 * r_span + 0.10 * r_stop
        best_idx = int(np.argmax(score))
        top = group.iloc[best_idx]
        
        t_drop = top["t_offshore_drop"]
        t_stop = top["t_offshore_stop_start"]
        span = int(top["voy_span"])
        
        if span <= 12:
            t_pred = int(top["t_mid"])
            method = "fusion_span_le_12"
        elif pd.notna(t_drop) and top["f2_offshore_speed_drop"] >= 2000.0:
            t_pred = int(t_drop)
            method = "fusion_offshore_drop"
        elif pd.notna(t_stop) and top["f1_offshore_stop_streak"] >= 2.0:
            t_pred = int(t_stop)
            method = "fusion_offshore_stop"
        else:
            t_pred = int(top["t_mid"])
            method = "fusion_mid"
            
        return int(top["voy"]), float(score[best_idx]), t_pred, method, bool(top["is_accident_related"])

    # ----------------- Hypothesis G: Multi-Slot Candidate Ensemble -----------------
    elif hypothesis_name == "hyp_G_multislot_ensemble":
        r_drop = rank_series(group["f2_offshore_speed_drop"].to_numpy())
        r_ratio = rank_series(group["f2_speed_drop_ratio"].to_numpy())
        r_sc = rank_series(group["top3_score"].to_numpy()) if "top3_score" in group.columns else np.zeros(n_voy)
        r_span = rank_series(group["voy_span"].to_numpy())
        r_stop = rank_series(group["f1_any_stop_streak"].to_numpy())
        
        score = 0.35 * r_drop + 0.15 * r_ratio + 0.25 * r_sc + 0.15 * r_span + 0.10 * r_stop
        best_idx = int(np.argmax(score))
        top = group.iloc[best_idx]
        
        t_drop = top["t_offshore_drop"]
        t_stop = top["t_offshore_stop_start"]
        span = int(top["voy_span"])
        
        if span <= 12:
            t_pred = int(top["t_mid"])
            method = "multislot_short_mid"
        elif pd.notna(t_drop) and top["f2_offshore_speed_drop"] >= 2000.0:
            t_pred = int(t_drop)
            method = "multislot_drop"
        elif pd.notna(t_stop) and top["f1_offshore_stop_streak"] >= 2.0:
            t_pred = int(t_stop)
            method = "multislot_stop"
        else:
            t_pred = int(top["t_mid"])
            method = "multislot_mid"
            
        return int(top["voy"]), float(score[best_idx]), t_pred, method, bool(top["is_accident_related"])

    else:
        raise ValueError(f"Unknown hypothesis: {hypothesis_name}")


def run_ranking_for_hypothesis(df_voyages, hypothesis_name):
    """Runs ranking across all vessels for a given hypothesis."""
    results = []
    for vid, group in df_voyages.groupby("rfid_id"):
        top_voy, score, t_pred, method, is_acc = rank_and_localize_vessel(group, hypothesis_name)
        results.append({
            "rfid_id": vid,
            "top_voy": top_voy,
            "score": score,
            "t_pred": t_pred,
            "pred_method": method,
            "is_accident_related": is_acc,
        })
    return pd.DataFrame(results)
