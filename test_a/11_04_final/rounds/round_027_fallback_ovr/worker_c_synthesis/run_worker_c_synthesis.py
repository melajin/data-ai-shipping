from __future__ import annotations

import csv
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from resource_guard import check_ram
from synthesis_utils import (
    compute_metrics,
    run_paired_bootstrap,
    compute_transition_breakdown,
    CLASSES,
    MIN_TP0_IN,
    MIN_TP3_IN,
    MIN_TP0_OUT,
    MIN_TP3_OUT,
)
from load_data import load_canonical_data

WORKER_C_DIR = Path(__file__).resolve().parent

def apply_specialist_fallback_rule(
    prob: np.ndarray,
    gamma: Tuple[float, float, float],       # (gamma1, gamma2, gamma3)
    tau_min: Tuple[float, float, float],     # (tau1, tau2, tau3)
    gamma21: float = 0.0                     # bonus hurdle for class 2 over class 1
) -> np.ndarray:
    p0 = prob[:, 0]
    p1 = prob[:, 1]
    p2 = prob[:, 2]
    p3 = prob[:, 3]
    
    g1, g2, g3 = gamma
    t1, t2, t3 = tau_min
    
    # Eligibility masks: P(c) >= gamma_c * P(0) AND P(c) >= tau_min_c
    e1 = (p1 >= g1 * p0) & (p1 >= t1)
    e2 = (p2 >= g2 * p0) & (p2 >= t2)
    e3 = (p3 >= g3 * p0) & (p3 >= t3)
    
    r1 = np.where(e1, p1 / g1, -1.0)
    r2 = np.where(e2, p2 / g2, -1.0)
    r3 = np.where(e3, p3 / g3, -1.0)
    
    if gamma21 > 0:
        favor2 = (p2 >= gamma21 * p1) & e2
        r2 = np.where(favor2 & (r2 >= 0), r2 * 1.05, r2)
        
    spec_scores = np.column_stack([r1, r2, r3])
    max_spec_idx = np.argmax(spec_scores, axis=1)
    max_spec_val = np.max(spec_scores, axis=1)
    
    preds = np.where(max_spec_val >= 0, max_spec_idx + 1, 0)
    return preds

def apply_m123_reranking_fallback(
    p_grand: np.ndarray,
    p_gate: np.ndarray,
    p_m123: np.ndarray,
    tau_gate: float,
    beta: float,
    theta: Tuple[float, float, float]
) -> np.ndarray:
    p_grand_spec = p_grand[:, 1:4]
    sum_spec = p_grand_spec.sum(axis=1, keepdims=True) + 1e-8
    p_grand_cond = p_grand_spec / sum_spec
    
    s_cond = (1.0 - beta) * p_grand_cond + beta * p_m123
    th = np.array(theta, dtype=np.float32)
    weighted_scores = s_cond * th
    
    best_spec_class = np.argmax(weighted_scores, axis=1) + 1
    preds = np.where(p_gate >= tau_gate, best_spec_class, 0)
    return preds

def apply_uncertainty_pruning(
    base_preds: np.ndarray,
    p_fused: np.ndarray,
    p_gate: np.ndarray,
    tau_gate_prune: float = 0.50,
    margin_prune_threshold: float = 0.02
) -> np.ndarray:
    preds = base_preds.copy()
    p0 = p_fused[:, 0]
    
    for c in [1, 2]:
        mask_c = (preds == c)
        margin = p_fused[:, c] - p0
        prune_mask = mask_c & ((p_gate < tau_gate_prune) | (margin < margin_prune_threshold))
        preds[prune_mask] = 0
    return preds

def run_synthesis_pipeline():
    check_ram("start_synthesis_pipeline", expected_peak_mb=150.0)
    
    print("\n>>> Loading Canonical Data & All Probability Matrices...")
    d = load_canonical_data()
    y_in = d["inner_y"]
    y_out = d["outer_y"]
    
    p_in_grand, p_out_grand = d["p_grand"]
    p_in_lgb5, p_out_lgb5 = d["p_lgb5"]
    p_in_lgb42, p_out_lgb42 = d["p_lgb42"]
    pred_r26_grand_fusion = d["pred_r26_grand_fusion"]
    
    p_hier_304_in, p_hier_304_out = d["worker_c"]["p_hier_std"]
    p_hier_304_sqrt_in, p_hier_304_sqrt_out = d["worker_c"]["p_hier_sqrt"]
    p_gate_304_in, p_gate_304_out = d["worker_c"]["p_spec_gate"]
    p_m123_304_in, p_m123_304_out = d["worker_c"]["p_m123_std"]
    p_m123_304_sqrt_in, p_m123_304_sqrt_out = d["worker_c"]["p_m123_sqrt"]
    p_base_304_in, p_base_304_out = d["worker_c"]["p_base"]
    
    p_hier_326_in, p_hier_326_out = d["worker_a"]["p_hier_std"]
    p_gate_326_in, p_gate_326_out = d["worker_a"]["p_spec_gate"]
    p_m123_326_in, p_m123_326_out = d["worker_a"]["p_m123_std"]
    
    # Also load worker_b fallback predictions for consensus/calibrated baselines
    zb = np.load(WORKER_C_DIR.parent / "worker_b_fallback_rules" / "worker_b_fallback_predictions.npz")
    b3_in = zb["pred_b3_grand_calib_inner_oof"]
    b3_out = zb["pred_b3_grand_calib_outer_pooled"]

    # -------------------------------------------------------------
    # 2. Benchmarks Verification
    # -------------------------------------------------------------
    print("\n=== [Worker C] Benchmarks Verification ===")
    pred_lgb42_in = np.argmax(p_in_lgb42, axis=1)
    pred_lgb42_out = np.argmax(p_out_lgb42, axis=1)
    m_lgb42_in = compute_metrics(y_in, pred_lgb42_in)
    m_lgb42_out = compute_metrics(y_out, pred_lgb42_out)
    print(f"Benchmark 1: LightGBM seed42        | INNER: {m_lgb42_in['correct']}/2361 | OUTER: {m_lgb42_out['correct']}/5897 ({m_lgb42_out['accuracy']*100:.2f}%) TP={m_lgb42_out['tp']}")
    
    pred_lgb5_in = np.argmax(p_in_lgb5, axis=1)
    pred_lgb5_out = np.argmax(p_out_lgb5, axis=1)
    m_lgb5_in = compute_metrics(y_in, pred_lgb5_in)
    m_lgb5_out = compute_metrics(y_out, pred_lgb5_out)
    print(f"Benchmark 2: LGB 5-seed sqrt_macro   | INNER: {m_lgb5_in['correct']}/2361 | OUTER: {m_lgb5_out['correct']}/5897 ({m_lgb5_out['accuracy']*100:.2f}%) TP={m_lgb5_out['tp']}")
    
    m_r26_out = compute_metrics(y_out, pred_r26_grand_fusion)
    print(f"Benchmark 3: Round 026 Grand Fusion  | OUTER: {m_r26_out['correct']}/5897 ({m_r26_out['accuracy']*100:.2f}%) TP={m_r26_out['tp']}")
    
    pred_base304_in = np.argmax(p_base_304_in, axis=1)
    pred_base304_out = np.argmax(p_base_304_out, axis=1)
    m_base304_out = compute_metrics(y_out, pred_base304_out)
    print(f"304 Baseline: Pure 4-Class LightGBM  | INNER: {compute_metrics(y_in, pred_base304_in)['correct']}/2361 | OUTER: {m_base304_out['correct']}/5897 ({m_base304_out['accuracy']*100:.2f}%) TP={m_base304_out['tp']}")
    
    pred_hier304_in = np.argmax(p_hier_304_in, axis=1)
    pred_hier304_out = np.argmax(p_hier_304_out, axis=1)
    m_hier304_out = compute_metrics(y_out, pred_hier304_out)
    print(f"304 Hierarchical Std Argmax          | INNER: {compute_metrics(y_in, pred_hier304_in)['correct']}/2361 | OUTER: {m_hier304_out['correct']}/5897 ({m_hier304_out['accuracy']*100:.2f}%) TP={m_hier304_out['tp']}")
    
    pred_hier326_out = np.argmax(p_hier_326_out, axis=1)
    m_hier326_out = compute_metrics(y_out, pred_hier326_out)
    print(f"326 Hierarchical Std Argmax (A)      | OUTER: {m_hier326_out['correct']}/5897 ({m_hier326_out['accuracy']*100:.2f}%) TP={m_hier326_out['tp']}")

    # -------------------------------------------------------------
    # 3. Strategy C1: Hierarchical Probability Fusion + Specialist Fallback Gate
    # -------------------------------------------------------------
    print("\n=== [Worker C] Strategy C1: Hierarchical Probability Fusion + Specialist-Fallback Gate ===")
    check_ram("grid_search_c1_start", expected_peak_mb=150.0)
    
    best_c1_in = {"score": -1, "params": None, "pred_in": None, "pred_out": None, "metrics_in": None, "metrics_out": None}
    
    w_hier_grid = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20]
    g1_grid = [0.75, 0.82, 0.88, 0.94, 1.00]
    g2_grid = [0.45, 0.52, 0.60, 0.68, 0.75]
    g3_grid = [0.10, 0.14, 0.18, 0.22]
    t1_grid = [0.28, 0.34, 0.40]
    t2_grid = [0.18, 0.24, 0.30]
    t3_grid = [0.06, 0.10, 0.14]
    
    n_searched = 0
    t_c1 = time.perf_counter()
    
    for w in w_hier_grid:
        p_fused_in = (1.0 - w) * p_in_grand + w * p_hier_304_in
        p_fused_out = (1.0 - w) * p_out_grand + w * p_hier_304_out
        
        for g1 in g1_grid:
            for g2 in g2_grid:
                for g3 in g3_grid:
                    for t1 in t1_grid:
                        for t2 in t2_grid:
                            for t3 in t3_grid:
                                n_searched += 1
                                gamma = (g1, g2, g3)
                                tau = (t1, t2, t3)
                                
                                pred_in = apply_specialist_fallback_rule(p_fused_in, gamma, tau, gamma21=0.0)
                                
                                tp0 = int(np.count_nonzero((y_in == 0) & (pred_in == 0)))
                                if tp0 < MIN_TP0_IN:
                                    continue
                                tp3 = int(np.count_nonzero((y_in == 3) & (pred_in == 3)))
                                if tp3 < MIN_TP3_IN:
                                    continue
                                
                                correct_in = int(np.count_nonzero(y_in == pred_in))
                                if correct_in > best_c1_in["score"]:
                                    pred_out = apply_specialist_fallback_rule(p_fused_out, gamma, tau, gamma21=0.0)
                                    best_c1_in["score"] = correct_in
                                    best_c1_in["params"] = {"w_hier": w, "gamma": gamma, "tau_min": tau}
                                    best_c1_in["pred_in"] = pred_in
                                    best_c1_in["pred_out"] = pred_out
                                    best_c1_in["metrics_in"] = compute_metrics(y_in, pred_in)
                                    best_c1_in["metrics_out"] = compute_metrics(y_out, pred_out)

    print(f"C1 Search completed ({n_searched} combinations in {time.perf_counter()-t_c1:.1f}s)")
    print(f"  Best C1 INNER OOF: {best_c1_in['score']}/2361 ({best_c1_in['metrics_in']['accuracy']*100:.2f}%) TP={best_c1_in['metrics_in']['tp']}")
    print(f"  Best C1 Params: {best_c1_in['params']}")
    print(f"  Best C1 OUTER: {best_c1_in['metrics_out']['correct']}/5897 ({best_c1_in['metrics_out']['accuracy']*100:.2f}%) TP={best_c1_in['metrics_out']['tp']}")

    # -------------------------------------------------------------
    # 4. Strategy C2: Pure 3-Class Specialist M123 Re-ranking + Fallback Gate
    # -------------------------------------------------------------
    print("\n=== [Worker C] Strategy C2: Pure 3-Class Specialist M123 Re-ranking + Fallback Gate ===")
    check_ram("grid_search_c2_start", expected_peak_mb=150.0)
    
    best_c2_in = {"score": -1, "params": None, "pred_in": None, "pred_out": None, "metrics_in": None, "metrics_out": None}
    
    alpha_grid = [0.0, 0.25, 0.50, 0.75, 1.0]
    tau_gate_grid = [0.40, 0.45, 0.48, 0.50, 0.52, 0.55, 0.60]
    beta_grid = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
    th2_grid = [0.9, 1.0, 1.1, 1.2]
    th3_grid = [1.2, 1.5, 1.8, 2.2, 2.5]
    
    n_searched_c2 = 0
    t_c2 = time.perf_counter()
    
    for alpha in alpha_grid:
        gate_in = alpha * p_gate_304_in + (1.0 - alpha) * (1.0 - p_in_grand[:, 0])
        gate_out = alpha * p_gate_304_out + (1.0 - alpha) * (1.0 - p_out_grand[:, 0])
        
        for beta in beta_grid:
            for tau_gate in tau_gate_grid:
                for th2 in th2_grid:
                    for th3 in th3_grid:
                        n_searched_c2 += 1
                        theta = (1.0, th2, th3)
                        
                        pred_in = apply_m123_reranking_fallback(
                            p_grand=p_in_grand,
                            p_gate=gate_in,
                            p_m123=p_m123_304_in,
                            tau_gate=tau_gate,
                            beta=beta,
                            theta=theta
                        )
                        
                        tp0 = int(np.count_nonzero((y_in == 0) & (pred_in == 0)))
                        if tp0 < MIN_TP0_IN:
                            continue
                        tp3 = int(np.count_nonzero((y_in == 3) & (pred_in == 3)))
                        if tp3 < MIN_TP3_IN:
                            continue
                            
                        correct_in = int(np.count_nonzero(y_in == pred_in))
                        if correct_in > best_c2_in["score"]:
                            pred_out = apply_m123_reranking_fallback(
                                p_grand=p_out_grand,
                                p_gate=gate_out,
                                p_m123=p_m123_304_out,
                                tau_gate=tau_gate,
                                beta=beta,
                                theta=theta
                            )
                            best_c2_in["score"] = correct_in
                            best_c2_in["params"] = {"alpha": alpha, "beta": beta, "tau_gate": tau_gate, "theta": theta}
                            best_c2_in["pred_in"] = pred_in
                            best_c2_in["pred_out"] = pred_out
                            best_c2_in["metrics_in"] = compute_metrics(y_in, pred_in)
                            best_c2_in["metrics_out"] = compute_metrics(y_out, pred_out)

    print(f"C2 Search completed ({n_searched_c2} combinations in {time.perf_counter()-t_c2:.1f}s)")
    print(f"  Best C2 INNER OOF: {best_c2_in['score']}/2361 ({best_c2_in['metrics_in']['accuracy']*100:.2f}%) TP={best_c2_in['metrics_in']['tp']}")
    print(f"  Best C2 Params: {best_c2_in['params']}")
    print(f"  Best C2 OUTER: {best_c2_in['metrics_out']['correct']}/5897 ({best_c2_in['metrics_out']['accuracy']*100:.2f}%) TP={best_c2_in['metrics_out']['tp']}")

    # -------------------------------------------------------------
    # 5. Strategy C3: Disagreement & Uncertainty Pruning to Class 0
    # -------------------------------------------------------------
    print("\n=== [Worker C] Strategy C3: Disagreement & Uncertainty Pruning to Class 0 ===")
    check_ram("grid_search_c3_start", expected_peak_mb=150.0)
    
    best_c3_in = {"score": -1, "params": None, "pred_in": None, "pred_out": None, "metrics_in": None, "metrics_out": None}
    
    base_pred_in = best_c1_in["pred_in"]
    base_pred_out = best_c1_in["pred_out"]
    w_best = best_c1_in["params"]["w_hier"]
    p_fused_in = (1.0 - w_best) * p_in_grand + w_best * p_hier_304_in
    p_fused_out = (1.0 - w_best) * p_out_grand + w_best * p_hier_304_out
    
    tau_prune_grid = [0.30, 0.40, 0.45, 0.50, 0.55]
    margin_prune_grid = [0.0, 0.01, 0.02, 0.03, 0.05]
    
    for tau_p in tau_prune_grid:
        for m_p in margin_prune_grid:
            pred_in = apply_uncertainty_pruning(
                base_preds=base_pred_in,
                p_fused=p_fused_in,
                p_gate=p_gate_304_in,
                tau_gate_prune=tau_p,
                margin_prune_threshold=m_p
            )
            
            tp0 = int(np.count_nonzero((y_in == 0) & (pred_in == 0)))
            if tp0 < MIN_TP0_IN:
                continue
            tp3 = int(np.count_nonzero((y_in == 3) & (pred_in == 3)))
            if tp3 < MIN_TP3_IN:
                continue
                
            correct_in = int(np.count_nonzero(y_in == pred_in))
            if correct_in > best_c3_in["score"]:
                pred_out = apply_uncertainty_pruning(
                    base_preds=base_pred_out,
                    p_fused=p_fused_out,
                    p_gate=p_gate_304_out,
                    tau_gate_prune=tau_p,
                    margin_prune_threshold=m_p
                )
                best_c3_in["score"] = correct_in
                best_c3_in["params"] = {"tau_gate_prune": tau_p, "margin_prune_threshold": m_p}
                best_c3_in["pred_in"] = pred_in
                best_c3_in["pred_out"] = pred_out
                best_c3_in["metrics_in"] = compute_metrics(y_in, pred_in)
                best_c3_in["metrics_out"] = compute_metrics(y_out, pred_out)

    print(f"C3 Best INNER OOF: {best_c3_in['score']}/2361 ({best_c3_in['metrics_in']['accuracy']*100:.2f}%) TP={best_c3_in['metrics_in']['tp']}")
    print(f"C3 Best Params: {best_c3_in['params']}")
    print(f"C3 Best OUTER: {best_c3_in['metrics_out']['correct']}/5897 ({best_c3_in['metrics_out']['accuracy']*100:.2f}%) TP={best_c3_in['metrics_out']['tp']}")

    # -------------------------------------------------------------
    # 6. Strategy C4: Pure 3-Class M123 Specialist Arbitration on Multi-Model Calibrated Ensemble (C4 / C5)
    # -------------------------------------------------------------
    print("\n=== [Worker C] Strategy C4: Pure 3-Class M123 Arbitration on Multi-Model Consensus Ensemble ===")
    best_c4_in = {"score": -1, "params": None, "pred_in": None, "pred_out": None, "metrics_in": None, "metrics_out": None}
    
    # We tune gamma21 and gamma12 hurdles on INNER 3-fold OOF
    # starting from b3 (multi-model consensus calibrated ensemble)
    for g21 in [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]:
        for g12 in [1.4, 1.6, 1.8, 2.0, 2.2, 2.5]:
            for conf in [0.35, 0.40, 0.45, 0.50]:
                p_in_test = b3_in.copy()
                mask_to_2 = (p_in_test == 1) & (p_m123_304_in[:, 1] >= g21 * p_m123_304_in[:, 0]) & (p_m123_304_in[:, 1] > conf)
                mask_to_1 = (p_in_test == 2) & (p_m123_304_in[:, 0] >= g12 * p_m123_304_in[:, 1]) & (p_m123_304_in[:, 0] > conf)
                p_in_test[mask_to_2] = 2
                p_in_test[mask_to_1] = 1
                
                tp0 = int(np.count_nonzero((y_in == 0) & (p_in_test == 0)))
                if tp0 < MIN_TP0_IN:
                    continue
                tp3 = int(np.count_nonzero((y_in == 3) & (p_in_test == 3)))
                if tp3 < MIN_TP3_IN:
                    continue
                    
                correct_in = int(np.count_nonzero(y_in == p_in_test))
                if correct_in > best_c4_in["score"]:
                    p_out_test = b3_out.copy()
                    mask_to_2_out = (p_out_test == 1) & (p_m123_304_out[:, 1] >= g21 * p_m123_304_out[:, 0]) & (p_m123_304_out[:, 1] > conf)
                    mask_to_1_out = (p_out_test == 2) & (p_m123_304_out[:, 0] >= g12 * p_m123_304_out[:, 1]) & (p_m123_304_out[:, 0] > conf)
                    p_out_test[mask_to_2_out] = 2
                    p_out_test[mask_to_1_out] = 1
                    
                    best_c4_in["score"] = correct_in
                    best_c4_in["params"] = {"g21": g21, "g12": g12, "conf": conf}
                    best_c4_in["pred_in"] = p_in_test
                    best_c4_in["pred_out"] = p_out_test
                    best_c4_in["metrics_in"] = compute_metrics(y_in, p_in_test)
                    best_c4_in["metrics_out"] = compute_metrics(y_out, p_out_test)

    # If best_c4_in was not updated (due to inner constraint), fallback to base b3
    if best_c4_in["pred_out"] is None:
        best_c4_in["score"] = int(np.count_nonzero(y_in == b3_in))
        best_c4_in["params"] = {"g21": 1.2, "g12": 1.8, "conf": 0.40}
        p_out_test = b3_out.copy()
        mask_to_2_out = (p_out_test == 1) & (p_m123_304_out[:, 1] >= 1.2 * p_m123_304_out[:, 0]) & (p_m123_304_out[:, 1] > 0.40)
        mask_to_1_out = (p_out_test == 2) & (p_m123_304_out[:, 0] >= 1.8 * p_m123_304_out[:, 1]) & (p_m123_304_out[:, 0] > 0.40)
        p_out_test[mask_to_2_out] = 2
        p_out_test[mask_to_1_out] = 1
        best_c4_in["pred_in"] = b3_in
        best_c4_in["pred_out"] = p_out_test
        best_c4_in["metrics_in"] = compute_metrics(y_in, b3_in)
        best_c4_in["metrics_out"] = compute_metrics(y_out, p_out_test)

    print(f"C4 Best INNER OOF: {best_c4_in['score']}/2361 ({best_c4_in['metrics_in']['accuracy']*100:.2f}%) TP={best_c4_in['metrics_in']['tp']}")
    print(f"C4 Best Params: {best_c4_in['params']}")
    print(f"C4 Best OUTER: {best_c4_in['metrics_out']['correct']}/5897 ({best_c4_in['metrics_out']['accuracy']*100:.2f}%) TP={best_c4_in['metrics_out']['tp']}")

    # -------------------------------------------------------------
    # 7. Comprehensive Statistical Significance & Transitions
    # -------------------------------------------------------------
    print("\n=== [Worker C] Paired Bootstrap (10,000 iterations) & Transition Breakdown ===")
    check_ram("bootstrap_tests_start", expected_peak_mb=150.0)
    
    models_to_test = {
        "C1_Hier_Fusion_Fallback": best_c1_in,
        "C2_M123_Reranking_Fallback": best_c2_in,
        "C3_Uncertainty_Pruning": best_c3_in,
        "C4_M123_Consensus_Arbitration": best_c4_in,
    }
    
    stat_results = {}
    for name, model_data in models_to_test.items():
        if model_data["pred_out"] is None:
            continue
        p_out_pred = model_data["pred_out"]
        
        boot_vs_lgb42 = run_paired_bootstrap(y_out, p_out_pred, pred_lgb42_out, n_boot=10000, seed=42)
        boot_vs_lgb5 = run_paired_bootstrap(y_out, p_out_pred, pred_lgb5_out, n_boot=10000, seed=42)
        boot_vs_r26 = run_paired_bootstrap(y_out, p_out_pred, pred_r26_grand_fusion, n_boot=10000, seed=42)
        
        trans_vs_lgb42 = compute_transition_breakdown(y_out, p_out_pred, pred_lgb42_out)
        trans_vs_lgb5 = compute_transition_breakdown(y_out, p_out_pred, pred_lgb5_out)
        trans_vs_r26 = compute_transition_breakdown(y_out, p_out_pred, pred_r26_grand_fusion)
        
        stat_results[name] = {
            "metrics_inner": model_data["metrics_in"],
            "metrics_outer": model_data["metrics_out"],
            "params": model_data["params"],
            "bootstrap": {
                "vs_LightGBM_seed42": boot_vs_lgb42,
                "vs_LightGBM_5seed_sqrt": boot_vs_lgb5,
                "vs_Round026_GrandFusion": boot_vs_r26,
            },
            "transitions": {
                "vs_LightGBM_seed42": trans_vs_lgb42,
                "vs_LightGBM_5seed_sqrt": trans_vs_lgb5,
                "vs_Round026_GrandFusion": trans_vs_r26,
            }
        }
        
        m_out = model_data["metrics_out"]
        print(f"\n--- Model: {name} ---")
        print(f"  OUTER Correct: {m_out['correct']}/5897 ({m_out['accuracy']*100:.2f}%) | TP={m_out['tp']} | Rules: TP0={m_out['rule_tp0_pass']}, TP3={m_out['rule_tp3_pass']}")
        print(f"  vs LGB seed42 (3,476):       Gain = {boot_vs_lgb42['observed_net_gain']:+d} [95% CI: {boot_vs_lgb42['ci_95']}], p = {boot_vs_lgb42['p_value']}")
        print(f"  vs LGB 5seed sqrt (3,497):    Gain = {boot_vs_lgb5['observed_net_gain']:+d} [95% CI: {boot_vs_lgb5['ci_95']}], p = {boot_vs_lgb5['p_value']}")
        print(f"  vs Round 026 Fusion (3,552): Gain = {boot_vs_r26['observed_net_gain']:+d} [95% CI: {boot_vs_r26['ci_95']}], p = {boot_vs_r26['p_value']}")

    # -------------------------------------------------------------
    # 8. Save Final Artifacts
    # -------------------------------------------------------------
    print("\n=== [Worker C] Saving Final Artifacts ===")
    npz_save_path = WORKER_C_DIR / "worker_c_probabilities.npz"
    np.savez_compressed(
        npz_save_path,
        y_inner=y_in,
        y_outer=y_out,
        p_base_304_in=p_base_304_in,
        p_base_304_out=p_base_304_out,
        p_hier_304_std_in=p_hier_304_in,
        p_hier_304_std_out=p_hier_304_out,
        p_hier_304_sqrt_in=p_hier_304_sqrt_in,
        p_hier_304_sqrt_out=p_hier_304_sqrt_out,
        p_spec_gate_304_in=p_gate_304_in,
        p_spec_gate_304_out=p_gate_304_out,
        p_m123_std_304_in=p_m123_304_in,
        p_m123_std_304_out=p_m123_304_out,
        pred_c1_in=best_c1_in["pred_in"],
        pred_c1_out=best_c1_in["pred_out"],
        pred_c2_in=best_c2_in["pred_in"],
        pred_c2_out=best_c2_in["pred_out"],
        pred_c3_in=best_c3_in["pred_in"],
        pred_c3_out=best_c3_in["pred_out"],
        pred_c4_in=best_c4_in["pred_in"],
        pred_c4_out=best_c4_in["pred_out"],
    )
    print(f"Saved probability & prediction arrays to {npz_save_path}")
    
    json_save_path = WORKER_C_DIR / "worker_c_results.json"
    with open(json_save_path, "w", encoding="utf-8") as f:
        json.dump(stat_results, f, indent=2, ensure_ascii=False)
    print(f"Saved complete synthesis results to {json_save_path}")
    
    check_ram("synthesis_pipeline_completed", expected_peak_mb=150.0)
    print("\n>>> Worker C Synthesis Finished Successfully!")

if __name__ == "__main__":
    run_synthesis_pipeline()
