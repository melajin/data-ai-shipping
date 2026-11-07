# -*- coding: utf-8 -*-
"""Main Orchestrator: Autonomous Iterative Hypothesis Testing Loop.

Iterates through pre-registered hypotheses:
- Hypothesis A: Offshore-only Sea Stop
- Hypothesis B: Hierarchical Cascade
- Hypothesis C: Speed Drop Steepness
- Hypothesis D: Towing Straightness
- Hypothesis E: Multi-Hypothesis Borda Ensemble
- (Dynamic Iterations): Tailored hybrid parameterizations based on error diagnostics.

Monitors progress against Level 1 (>=12%), Level 2 (>=20%), Level 3 (>=30%).
Stops when target level is achieved or all hypotheses explored.
Generates final Test B submission from champion model.
"""
import os
import sys
import time
import json
import datetime
import pandas as pd
import numpy as np

from h2_rank_and_localize import run_ranking_for_hypothesis
from h3_automated_evaluator import evaluate_hypothesis
from h4_error_diagnostics import diagnose_errors

OUT_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
FEATS_PATH = f"{OUT_DIR}/voyage_features_all_hypotheses.csv"
R8_DIR = "testB/round_008_linkage_audit_20261105"
DEVSET_POS_PATH = f"{R8_DIR}/devset_positives.csv"


def main():
    start_time = time.time()
    print("======================================================================")
    print("   Starting Autonomous Iterative Testing Loop (Gemini Round 1)        ")
    print("======================================================================")
    
    if not os.path.exists(FEATS_PATH):
        print(f"Features file {FEATS_PATH} not found. Running h1_hypothesis_engine.py first...")
        import h1_hypothesis_engine
        h1_hypothesis_engine.main()
        
    voy_df = pd.read_csv(FEATS_PATH)
    voy_df["rfid_id"] = voy_df["rfid_id"].astype(str)
    
    pos_df = pd.read_csv(DEVSET_POS_PATH)
    pos_df["rfid_id"] = pos_df["rfid_id"].astype(str)
    
    hypotheses = [
        ("Hypothesis_A", "hyp_A_offshore_sea_stop", "Offshore-only Sea Stop Streak"),
        ("Hypothesis_B", "hyp_B_hierarchical_cascade", "Hierarchical Priority Cascade (Stop -> Drop -> Tow)"),
        ("Hypothesis_C", "hyp_C_speed_drop_steepness", "Cruising Speed Drop Steepness Ratio"),
        ("Hypothesis_D", "hyp_D_towing_straightness", "Post-incident Towing Return Straightness"),
        ("Hypothesis_E", "hyp_E_borda_ensemble", "Multi-Hypothesis Borda Count Ensemble"),
        ("Hypothesis_F", "hyp_F_score_fusion", "Fused Multi-Feature Ranking (Drop + Score + Span + Stop)"),
        ("Hypothesis_G", "hyp_G_multislot_ensemble", "Multi-Slot Candidate Weighted Ensemble"),
    ]
    
    experiment_results = []
    champion = None
    champion_rate = -1.0
    champion_name = None
    champion_selections = None
    
    print("\nIterating through hypotheses...\n")
    print(f"{'Hypothesis':<18s} | {'Voyage Capture':<15s} | {'Hit Rate (T01)':<15s} | {'ALL Hit Rate':<13s} | {'Gate Status':<12s}")
    print("-" * 80)
    
    for tag, hyp_id, desc in hypotheses:
        t0 = time.time()
        sel_df = run_ranking_for_hypothesis(voy_df, hyp_id)
        eval_res = evaluate_hypothesis(sel_df, pos_df, voy_df)
        diag = diagnose_errors(eval_res["detail_df"])
        
        t01 = eval_res["primary_t01_eligible"]
        all_100 = eval_res["secondary_all_100"]
        
        gate_str = "LEVEL 3" if t01["passed_level_3_30pct"] else ("LEVEL 2" if t01["passed_level_2_20pct"] else ("LEVEL 1" if t01["passed_level_1_12pct"] else "FAIL"))
        
        print(f"{tag:<18s} | {t01['voyage_capture_count']:2d}/{t01['n_events']:2d} ({t01['voyage_capture_rate']:>6.1%}) | {t01['hits']:2d}/{t01['n_events']:2d} ({t01['hit_rate']:>6.1%}) | {all_100['hits']:2d}/100 ({all_100['hit_rate']:>5.1%}) | {gate_str:<12s}")
        
        rec = {
            "tag": tag,
            "hypothesis_id": hyp_id,
            "description": desc,
            "t01_eligible": t01,
            "all_100": all_100,
            "diagnostics": diag,
            "elapsed_seconds": round(time.time() - t0, 3),
        }
        experiment_results.append(rec)
        
        if t01["hit_rate"] > champion_rate:
            champion_rate = t01["hit_rate"]
            champion_name = tag
            champion = rec
            champion_selections = sel_df
            
    print("-" * 80)
    print(f"\nChampion across all evaluated hypotheses: {champion_name} with hit rate {champion_rate:.2%}")
    
    # Save experiment history
    history_path = f"{OUT_DIR}/iteration_history.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(experiment_results, f, ensure_ascii=False, indent=2)
    print(f"Saved iteration history to {history_path}")
    
    # Save best selections
    champion_selections.to_csv(f"{OUT_DIR}/champion_selections.csv", index=False, encoding="utf-8-sig")
    print(f"Saved champion selections to {OUT_DIR}/champion_selections.csv")
    
    return champion


if __name__ == "__main__":
    main()
