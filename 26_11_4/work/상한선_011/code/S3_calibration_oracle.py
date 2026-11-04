#!/usr/bin/env python3
"""S3 — 확률 보정 오라클: 순위는 그대로, 값만 완벽하게

지시 011:
  - 업종 c마다 1-vs-rest로 P[:, c]에 대해 IsotonicRegression(out_of_bounds="clip") 적합
  - OUTER 라벨로 직접 적합 (오라클 상한)
  - INNER에서 적합해 OUTER에 적용 (실제 채택 가능 대조군)
  - 행 합 1 정규화 후 argmax
  - macro-F1 / micro-F1(정확도) 및 부트스트랩 95% 구간 산출

출력: work/상한선_011/S3.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
UPPER_DIR = HERE.parent
WORK_DIR = UPPER_DIR.parent
NPZ_PATH = WORK_DIR / "08_probs.npz"

BOOT_SEED = 20261104
N_BOOT = 5000
BINS = [(1, 7), (8, 30), (31, 90), (91, 10 ** 9)]
CLASS_NAMES = ["연안복합", "자망", "통발", "채낚기연승낚시"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def macro_f1_fast(y: np.ndarray, pred: np.ndarray) -> float:
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.float64)
    denom = cm.sum(0) + cm.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(denom > 0, 2 * tp / denom, 0.0)
    return float(f1.mean())


def class_f1_fast(y: np.ndarray, pred: np.ndarray) -> list[float]:
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.float64)
    denom = cm.sum(0) + cm.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(denom > 0, 2 * tp / denom, 0.0)
    return [round(float(v), 5) for v in f1]


def acc_fast(y: np.ndarray, pred: np.ndarray) -> float:
    return float((y == pred).mean())


def bootstrap_ci(y: np.ndarray, pred_base: np.ndarray, pred_cand: np.ndarray,
                 metric_fn, rng: np.random.Generator) -> tuple[float, list[float], float]:
    n = len(y)
    diffs = np.empty(N_BOOT, dtype=np.float64)
    for b in range(N_BOOT):
        idx = rng.integers(0, n, size=n)
        s_cand = metric_fn(y[idx], pred_cand[idx])
        s_base = metric_fn(y[idx], pred_base[idx])
        diffs[b] = s_cand - s_base
    low, high = np.percentile(diffs, [2.5, 97.5])
    p_gt_0 = float((diffs > 0).mean())
    return float(diffs.mean()), [round(float(low), 6), round(float(high), 6)], round(p_gt_0, 4)


def evaluate_full(y: np.ndarray, days: np.ndarray, pred: np.ndarray,
                  base_pred: np.ndarray, rng: np.random.Generator) -> dict:
    mf1 = macro_f1_fast(y, pred)
    acc = acc_fast(y, pred)
    cf1 = class_f1_fast(y, pred)
    counts = [int(c) for c in np.bincount(pred, minlength=4)]

    by_days = {}
    for lo, hi in BINS:
        tag = f"{lo}-{hi if hi < 10**8 else '+'}"
        mask = (days >= lo) & (days <= hi)
        if mask.any():
            by_days[tag] = {
                "n": int(mask.sum()),
                "macro_f1": round(macro_f1_fast(y[mask], pred[mask]), 5),
                "accuracy": round(acc_fast(y[mask], pred[mask]), 5)
            }

    d_mf1, ci_mf1, p_mf1 = bootstrap_ci(y, base_pred, pred, macro_f1_fast, rng)
    d_acc, ci_acc, p_acc = bootstrap_ci(y, base_pred, pred, acc_fast, rng)

    return {
        "macro_f1": round(mf1, 5),
        "accuracy": round(acc, 5),
        "class_f1": cf1,
        "pred_counts": counts,
        "by_days": by_days,
        "diff_macro_f1": round(mf1 - macro_f1_fast(y, base_pred), 6),
        "ci_macro_f1": ci_mf1,
        "p_macro_gt_0": p_mf1,
        "diff_accuracy": round(acc - acc_fast(y, base_pred), 6),
        "ci_accuracy": ci_acc,
        "p_acc_gt_0": p_acc
    }


def calibrate_probs(P_train: np.ndarray, y_train: np.ndarray, P_test: np.ndarray) -> np.ndarray:
    P_cal = np.zeros_like(P_test)
    for c in range(4):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(P_train[:, c], (y_train == c).astype(np.float64))
        P_cal[:, c] = iso.predict(P_test[:, c])
    denom = P_cal.sum(axis=1, keepdims=True)
    denom = np.where(denom <= 0, 1.0, denom)
    return P_cal / denom


def main():
    log("=== S3: 확률 보정 오라클 시작 ===")
    data = np.load(NPZ_PATH)
    inner_P = data["inner_L_base"]
    inner_y = data["inner_y"]
    outer_P = data["outer_L_base"]
    outer_y = data["outer_y"]
    outer_days = data["outer_days"]

    rng = np.random.default_rng(BOOT_SEED)

    # 기준선 (통발 w=1.5, w=1.0)
    base_pred_w15 = (outer_P * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    base_pred_w10 = outer_P.argmax(1)

    eval_base_w15 = evaluate_full(outer_y, outer_days, base_pred_w15, base_pred_w15, rng)
    eval_base_w10 = evaluate_full(outer_y, outer_days, base_pred_w10, base_pred_w10, rng)

    # 1. INNER 보정 -> OUTER 적용 (실현 후보)
    outer_cal_in = calibrate_probs(inner_P, inner_y, outer_P)
    pred_in = outer_cal_in.argmax(1)
    eval_in_vs_w15 = evaluate_full(outer_y, outer_days, pred_in, base_pred_w15, rng)
    eval_in_vs_w10 = evaluate_full(outer_y, outer_days, pred_in, base_pred_w10, rng)
    log(f"INNER 보정 적용 -> OUTER macro-F1: {eval_in_vs_w15['macro_f1']}, acc: {eval_in_vs_w15['accuracy']}")

    # 2. OUTER 직접 보정 (오라클 상한)
    outer_cal_oracle = calibrate_probs(outer_P, outer_y, outer_P)
    pred_oracle = outer_cal_oracle.argmax(1)
    eval_oracle_vs_w15 = evaluate_full(outer_y, outer_days, pred_oracle, base_pred_w15, rng)
    eval_oracle_vs_w10 = evaluate_full(outer_y, outer_days, pred_oracle, base_pred_w10, rng)
    log(f"OUTER 오라클 보정 -> OUTER macro-F1: {eval_oracle_vs_w15['macro_f1']}, acc: {eval_oracle_vs_w15['accuracy']}")

    out_json = {
        "experiment": "S3_calibration_oracle",
        "class_order": CLASS_NAMES,
        "baseline_w_1.5": {
            "type": "실현(현재방식_macro용)",
            "metrics": eval_base_w15
        },
        "baseline_w_1.0": {
            "type": "실현(현재방식_acc용)",
            "metrics": eval_base_w10
        },
        "inner_calibrated": {
            "type": "실현(후보)",
            "metrics_vs_w15": eval_in_vs_w15,
            "metrics_vs_w10": eval_in_vs_w10
        },
        "outer_oracle": {
            "type": "상한(오라클)",
            "metrics_vs_w15": eval_oracle_vs_w15,
            "metrics_vs_w10": eval_oracle_vs_w10
        }
    }

    out_path = UPPER_DIR / "S3.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
