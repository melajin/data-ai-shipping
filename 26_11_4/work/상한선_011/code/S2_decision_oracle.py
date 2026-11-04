#!/usr/bin/env python3
"""S2 — 판정 규칙 오라클: 확률은 그대로, 임계값만 완벽하게

지시 011:
  - 배수 벡터 c = (1.0, c1, c2, c3)
  - 격자 0.2 ~ 5.0 로그 등간격 40점
  - 6라운드 또는 수렴까지 좌표하강
  - 세 가지 비교:
    1) 현재 방식 (통발 배수만, INNER에서 선택)
    2) 4차원 배수, INNER에서 선택 (실제 채택 후보)
    3) 4차원 배수, OUTER 오라클 (상한)
  - macro-F1 및 micro-F1(정확도) 각각 최적화 및 평가
  - 5,000회 부트스트랩 95% 구간 산출

출력: work/상한선_011/S2.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

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


def coordinate_descent(P: np.ndarray, y: np.ndarray, metric_fn,
                       grid: np.ndarray, rounds: int = 6) -> tuple[list[float], float]:
    c = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float64)
    best_score = metric_fn(y, (P * c).argmax(1))
    for r in range(rounds):
        improved = False
        for idx in [1, 2, 3]:
            best_val = c[idx]
            for g in grid:
                trial = c.copy()
                trial[idx] = g
                pred = (P * trial).argmax(1)
                score = metric_fn(y, pred)
                if score > best_score + 1e-12:
                    best_score = score
                    best_val = g
                    improved = True
            c[idx] = best_val
        if not improved:
            break
    return [round(float(x), 4) for x in c], float(best_score)


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

    # by days
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

    # paired bootstrap vs base
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


def main():
    log("=== S2: 판정 규칙 오라클 시작 ===")
    data = np.load(NPZ_PATH)
    inner_P = data["inner_L_base"]
    inner_y = data["inner_y"]
    outer_P = data["outer_L_base"]
    outer_y = data["outer_y"]
    outer_days = data["outer_days"]

    grid = np.geomspace(0.2, 5.0, 40)
    rng = np.random.default_rng(BOOT_SEED)

    # 1. 기준선 (현재 방식: 통발 배수 w=1.5)
    base_c_macro = [1.0, 1.0, 1.5, 1.0]
    base_pred_macro = (outer_P * base_c_macro).argmax(1)

    # 기준선 (정확도용: w=1.0)
    base_c_acc = [1.0, 1.0, 1.0, 1.0]
    base_pred_acc = (outer_P * base_c_acc).argmax(1)

    log(f"기준선 L_base (w=1.5) outer macro-F1: {macro_f1_fast(outer_y, base_pred_macro):.5f}, acc: {acc_fast(outer_y, base_pred_macro):.5f}")
    log(f"기준선 L_base (w=1.0) outer macro-F1: {macro_f1_fast(outer_y, base_pred_acc):.5f}, acc: {acc_fast(outer_y, base_pred_acc):.5f}")

    # 2. 최적화 실행
    # (a) INNER에서 macro-F1 최적화
    c_in_macro, score_in_macro = coordinate_descent(inner_P, inner_y, macro_f1_fast, grid)
    pred_in_macro = (outer_P * c_in_macro).argmax(1)
    eval_in_macro = evaluate_full(outer_y, outer_days, pred_in_macro, base_pred_macro, rng)
    log(f"INNER macro 선택 c: {c_in_macro} -> OUTER macro-F1: {eval_in_macro['macro_f1']}, acc: {eval_in_macro['accuracy']}")

    # (b) OUTER 오라클 macro-F1 최적화
    c_out_macro, score_out_macro = coordinate_descent(outer_P, outer_y, macro_f1_fast, grid)
    pred_out_macro = (outer_P * c_out_macro).argmax(1)
    eval_out_macro = evaluate_full(outer_y, outer_days, pred_out_macro, base_pred_macro, rng)
    log(f"OUTER 오라클 macro c: {c_out_macro} -> OUTER macro-F1: {eval_out_macro['macro_f1']}, acc: {eval_out_macro['accuracy']}")

    # (c) INNER에서 accuracy 최적화
    c_in_acc, score_in_acc = coordinate_descent(inner_P, inner_y, acc_fast, grid)
    pred_in_acc = (outer_P * c_in_acc).argmax(1)
    eval_in_acc = evaluate_full(outer_y, outer_days, pred_in_acc, base_pred_acc, rng)
    log(f"INNER acc 선택 c: {c_in_acc} -> OUTER macro-F1: {eval_in_acc['macro_f1']}, acc: {eval_in_acc['accuracy']}")

    # (d) OUTER 오라클 accuracy 최적화
    c_out_acc, score_out_acc = coordinate_descent(outer_P, outer_y, acc_fast, grid)
    pred_out_acc = (outer_P * c_out_acc).argmax(1)
    eval_out_acc = evaluate_full(outer_y, outer_days, pred_out_acc, base_pred_acc, rng)
    log(f"OUTER 오라클 acc c: {c_out_acc} -> OUTER macro-F1: {eval_out_acc['macro_f1']}, acc: {eval_out_acc['accuracy']}")

    # 채택 기준 점검 (INNER 선택 모델)
    def check_adoption(ev, base_mf1, base_cf1, base_days_mf1):
        delta = ev["macro_f1"] - base_mf1
        ci_ok = ev["ci_macro_f1"][0] > 0
        cf1_drop = max(base_cf1[i] - ev["class_f1"][i] for i in range(4))
        day17_drop = base_days_mf1 - ev["by_days"]["1-7"]["macro_f1"]
        passed = (delta >= 0.005) and ci_ok and (cf1_drop <= 0.01) and (day17_drop <= 0.01)
        return {
            "passed": bool(passed),
            "delta": round(delta, 5),
            "ci_lower_gt_0": bool(ci_ok),
            "max_class_f1_drop": round(cf1_drop, 5),
            "day17_macro_drop": round(day17_drop, 5)
        }

    base_eval_macro = evaluate_full(outer_y, outer_days, base_pred_macro, base_pred_macro, rng)
    base_eval_acc = evaluate_full(outer_y, outer_days, base_pred_acc, base_pred_acc, rng)

    adoption_in_macro = check_adoption(
        eval_in_macro, base_eval_macro["macro_f1"],
        base_eval_macro["class_f1"], base_eval_macro["by_days"]["1-7"]["macro_f1"]
    )

    out_json = {
        "experiment": "S2_decision_oracle",
        "class_order": CLASS_NAMES,
        "grid_points": 40,
        "rounds": 6,
        "macro_optimization": {
            "baseline_w_1.5": {
                "type": "실현(현재방식)",
                "c": base_c_macro,
                "metrics": base_eval_macro
            },
            "inner_selected_4d": {
                "type": "실현(후보)",
                "c": c_in_macro,
                "inner_score": round(score_in_macro, 5),
                "metrics": eval_in_macro,
                "adoption_check": adoption_in_macro
            },
            "outer_oracle_4d": {
                "type": "상한(오라클)",
                "c": c_out_macro,
                "outer_score": round(score_out_macro, 5),
                "metrics": eval_out_macro
            }
        },
        "accuracy_optimization": {
            "baseline_w_1.0": {
                "type": "실현(현재방식)",
                "c": base_c_acc,
                "metrics": base_eval_acc
            },
            "inner_selected_4d": {
                "type": "실현(후보)",
                "c": c_in_acc,
                "inner_score": round(score_in_acc, 5),
                "metrics": eval_in_acc
            },
            "outer_oracle_4d": {
                "type": "상한(오라클)",
                "c": c_out_acc,
                "outer_score": round(score_out_acc, 5),
                "metrics": eval_out_acc
            }
        }
    }

    out_path = UPPER_DIR / "S2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
