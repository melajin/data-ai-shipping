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

WORKER_C_DIR = Path(__file__).resolve().parent
WORKER_A_DIR = WORKER_C_DIR.parent / "worker_a_ovr_models"
WORKER_B_DIR = WORKER_C_DIR.parent / "worker_b_fallback_rules"
R2_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
TAB_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")
RANK1_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts")
T1_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
T3_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble\probabilities_track3.npz")

FOLDS = (0, 1, 2)
CLASSES = ["연안복합(0)", "자망(1)", "통발(2)", "채낚기(3)"]

MIN_TP0_IN = 958
MIN_TP3_IN = 38
MIN_TP0_OUT = 2389
MIN_TP3_OUT = 92

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    cm = np.bincount(y_true * 4 + y_pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.int64)
    support = cm.sum(axis=1).astype(np.int64)
    predicted = cm.sum(axis=0).astype(np.int64)
    
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros(4, dtype=np.float64), where=predicted > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros(4, dtype=np.float64), where=denom > 0)
    
    correct = int(np.count_nonzero(y_true == y_pred))
    n = len(y_true)
    
    is_outer = n > 3000
    rule_tp0_pass = bool(tp[0] >= (MIN_TP0_OUT if is_outer else MIN_TP0_IN))
    rule_tp3_pass = bool(tp[3] >= (MIN_TP3_OUT if is_outer else MIN_TP3_IN))
    rule_all_pass = rule_tp0_pass and rule_tp3_pass
    
    return {
        "n": n,
        "correct": correct,
        "accuracy": float(correct / n) if n > 0 else 0.0,
        "micro_f1": float(correct / n) if n > 0 else 0.0,
        "macro_f1": float(f1.mean()),
        "tp": tp.tolist(),
        "tp0": int(tp[0]),
        "tp1": int(tp[1]),
        "tp2": int(tp[2]),
        "tp3": int(tp[3]),
        "support": support.tolist(),
        "predicted": predicted.tolist(),
        "precision": [round(float(x), 4) for x in precision],
        "recall": [round(float(x), 4) for x in recall],
        "class_f1": [round(float(x), 4) for x in f1],
        "confusion_matrix": cm.tolist(),
        "rule_tp0_pass": rule_tp0_pass,
        "rule_tp3_pass": rule_tp3_pass,
        "rule_all_pass": rule_all_pass,
    }

def run_paired_bootstrap(
    y_true: np.ndarray,
    pred_cand: np.ndarray,
    pred_base: np.ndarray,
    n_boot: int = 10000,
    seed: int = 42
) -> Dict[str, Any]:
    rng = np.random.RandomState(seed)
    n = len(y_true)
    correct_cand = (y_true == pred_cand).astype(np.int32)
    correct_base = (y_true == pred_base).astype(np.int32)
    diff = correct_cand - correct_base
    observed_diff = int(diff.sum())
    
    # Vectorized bootstrap in chunks to save memory
    chunk_size = 2000
    boot_diffs = []
    for _ in range(n_boot // chunk_size):
        idx = rng.randint(0, n, size=(chunk_size, n))
        boot_diffs.append(diff[idx].sum(axis=1))
    boot_diffs = np.concatenate(boot_diffs)
    
    ci_lower = float(np.percentile(boot_diffs, 2.5))
    ci_upper = float(np.percentile(boot_diffs, 97.5))
    
    # Two-sided empirical p-value
    if observed_diff > 0:
        p_val = 2.0 * float(np.mean(boot_diffs <= 0))
    elif observed_diff < 0:
        p_val = 2.0 * float(np.mean(boot_diffs >= 0))
    else:
        p_val = 1.0
    p_val = min(1.0, max(0.0, p_val))
    
    return {
        "observed_net_gain": observed_diff,
        "ci_95": [round(ci_lower, 1), round(ci_upper, 1)],
        "p_value": round(p_val, 4),
        "mean_boot_diff": round(float(boot_diffs.mean()), 2),
    }

def compute_transition_breakdown(
    y_true: np.ndarray,
    pred_cand: np.ndarray,
    pred_base: np.ndarray
) -> Dict[str, Any]:
    breakdown = {}
    total_gain = int(np.sum(pred_cand == y_true) - np.sum(pred_base == y_true))
    
    for c in range(4):
        mask_c = (y_true == c)
        cand_corr = (pred_cand == c) & mask_c
        base_corr = (pred_base == c) & mask_c
        
        newly_correct = int(np.sum(cand_corr & (~base_corr)))
        newly_wrong = int(np.sum((~cand_corr) & base_corr))
        net_c = newly_correct - newly_wrong
        
        breakdown[f"class_{c}"] = {
            "support": int(mask_c.sum()),
            "newly_correct": newly_correct,
            "newly_wrong": newly_wrong,
            "net_gain": net_c,
        }
        
    breakdown["total_net_gain"] = total_gain
    return breakdown
