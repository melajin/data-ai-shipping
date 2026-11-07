# -*- coding: utf-8 -*-
"""Component 5: Automated Error Diagnostics Module.

Analyzes prediction failures into:
1. Voyage Misses (Wrong voyage selected)
2. Timing Misses (Correct voyage selected, but |t_pred - acc_ts| > 6h)
3. Hits (Accident localized within +-6h)
Provides actionable diagnostic guidance for the next hypothesis iteration.
"""
import numpy as np
import pandas as pd


def diagnose_errors(eval_detail_df):
    """Categorizes predictions and generates diagnostic summary."""
    t01_elig = eval_detail_df[(eval_detail_df["is_tier01"] == True) & (eval_detail_df["eligible_rem_ge_10"] == True)].copy()
    n_tot = len(t01_elig)
    
    hits = t01_elig[t01_elig["hit"] == True]
    timing_misses = t01_elig[(t01_elig["hit"] == False) & (t01_elig["is_acc_voy"] == True)].copy()
    voyage_misses = t01_elig[(t01_elig["hit"] == False) & (t01_elig["is_acc_voy"] == False)]
    
    timing_errors = []
    if len(timing_misses) > 0:
        timing_misses["error_hours"] = timing_misses["t_pred"] - timing_misses["acc_ts"]
        timing_errors = timing_misses["error_hours"].tolist()
        
    hits_by_type = hits["acc_type"].value_counts().to_dict()
    timing_miss_by_type = timing_misses["acc_type"].value_counts().to_dict() if len(timing_misses) else {}
    
    diagnostics = {
        "n_events": n_tot,
        "n_hits": len(hits),
        "hit_rate_pct": round(len(hits) / n_tot * 100, 2),
        "n_timing_misses": len(timing_misses),
        "timing_miss_pct": round(len(timing_misses) / n_tot * 100, 2),
        "n_voyage_misses": len(voyage_misses),
        "voyage_miss_pct": round(len(voyage_misses) / n_tot * 100, 2),
        "hits_by_accident_type": hits_by_type,
        "timing_miss_sample_errors_hours": timing_errors[:8],
        "primary_bottleneck": (
            "TIMING_LOCALIZATION" if len(timing_misses) >= len(hits)
            else "VOYAGE_SELECTION"
        ),
    }
    return diagnostics
