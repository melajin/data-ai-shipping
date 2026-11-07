#!/usr/bin/env python3
"""S3 — 확률 보정 오라클: 순위는 그대로, 값만 완벽하게

지시 011:
  - 업종 c마다 1-vs-rest로 보고, P[:, c]에 대해
    sklearn.isotonic.IsotonicRegression(out_of_bounds="clip")을
    OUTER 라벨로 직접 적합 (오라클).
  - 보정된 네 값을 행 합 1로 정규화하고 argmax.
  - macro-F1 / micro-F1(정확도) 산출.
  - 대조군: 같은 isotonic을 INNER에서 적합해 OUTER에 적용한 값 (실제 채택 후보).
  - 통발 배수(w=1.5) 및 임계값 결합 효과도 함께 산출.

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


def fit_isotonic_4class(P_fit: np.ndarray, y_fit: np.ndarray) -> list[IsotonicRegression]:
    models = []
    for c in range(4):
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        target = (y_fit == c).astype(np.float64)
        iso.fit(P_fit[:, c], target)
        models.append(iso)
    return models


def predict_isotonic_4class(models: list[IsotonicRegression], P: np.ndarray) -> np.ndarray:
    P_cal = np.empty_like(P)
    for c in range(4):
        P_cal[:, c] = models[c].predict(P[:, c])
    # 행 합 1로 정규화 (합이 0인 경우 균등 할당)
    row_sums = P_cal.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    return P_cal / row_sums


def main():
    log("=== S3: 확률 보정 오라클 시작 ===")
    data = np.load(NPZ_PATH)
    inner_P = data["inner_L_base"]
    inner_y = data["inner_y"]
    outer_P = data["outer_L_base"]
    outer_y = data["outer_y"]
    outer_days = data["outer_days"]

    rng = np.random.default_rng(BOOT_SEED)

    # 기준선 (통발 w=1.5)
    base_pred_macro = (outer_P * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    base_eval = evaluate_full(outer_y, outer_days, base_pred_macro, base_pred_macro, rng)
    log(f"기준선 L_base (w=1.5): macro-F1={base_eval['macro_f1']}, acc={base_eval['accuracy']}")

    # 1. 대조군: INNER 적합 IsotonicRegression
    iso_inner = fit_isotonic_4class(inner_P, inner_y)
    P_cal_inner = predict_isotonic_4class(iso_inner, outer_P)

    # (a) 순수 argmax
    pred_in_raw = P_cal_inner.argmax(1)
    eval_in_raw = evaluate_full(outer_y, outer_days, pred_in_raw, base_pred_macro, rng)
    log(f"INNER 보정 (순수 argmax): macro-F1={eval_in_raw['macro_f1']}, acc={eval_in_raw['accuracy']}")

    # (b) 통발 w=1.5 적용
    pred_in_w15 = (P_cal_inner * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    eval_in_w15 = evaluate_full(outer_y, outer_days, pred_in_w15, base_pred_macro, rng)
    log(f"INNER 보정 (통발 w=1.5): macro-F1={eval_in_w15['macro_f1']}, acc={eval_in_w15['accuracy']}")

    # 2. 오라클: OUTER 적합 IsotonicRegression
    iso_outer = fit_isotonic_4class(outer_P, outer_y)
    P_cal_outer = predict_isotonic_4class(iso_outer, outer_P)

    # (a) 순수 argmax (오라클)
    pred_out_raw = P_cal_outer.argmax(1)
    eval_out_raw = evaluate_full(outer_y, outer_days, pred_out_raw, base_pred_macro, rng)
    log(f"OUTER 오라클 보정 (순수 argmax): macro-F1={eval_out_raw['macro_f1']}, acc={eval_out_raw['accuracy']}")

    # (b) 통발 w=1.5 적용 (오라클)
    pred_out_w15 = (P_cal_outer * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    eval_out_w15 = evaluate_full(outer_y, outer_days, pred_out_w15, base_pred_macro, rng)
    log(f"OUTER 오라클 보정 (통발 w=1.5): macro-F1={eval_out_w15['macro_f1']}, acc={eval_out_w15['accuracy']}")

    # 채택 기준 점검
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

    adoption_in_raw = check_adoption(
        eval_in_raw, base_eval["macro_f1"], base_eval["class_f1"],
        base_eval["by_days"]["1-7"]["macro_f1"]
    )
    adoption_in_w15 = check_adoption(
        eval_in_w15, base_eval["macro_f1"], base_eval["class_f1"],
        base_eval["by_days"]["1-7"]["macro_f1"]
    )

    out_json = {
        "experiment": "S3_isotonic_oracle",
        "description": "1-vs-rest IsotonicRegression 확률 보정 오라클 vs INNER 실현",
        "baseline_w_1.5": {
            "type": "실현(현재방식)",
            "metrics": base_eval
        },
        "inner_calibrated_raw": {
            "type": "실현(후보_순수argmax)",
            "metrics": eval_in_raw,
            "adoption_check": adoption_in_raw
        },
        "inner_calibrated_w15": {
            "type": "실현(후보_w1.5)",
            "metrics": eval_in_w15,
            "adoption_check": adoption_in_w15
        },
        "outer_oracle_raw": {
            "type": "상한(오라클_순수argmax)",
            "metrics": eval_out_raw
        },
        "outer_oracle_w15": {
            "type": "상한(오라클_w1.5)",
            "metrics": eval_out_w15
        },
        "gap_analysis": {
            "s3_raw_oracle_vs_baseline": round(eval_out_raw["macro_f1"] - base_eval["macro_f1"], 5),
            "s3_w15_oracle_vs_baseline": round(eval_out_w15["macro_f1"] - base_eval["macro_f1"], 5),
            "explanation": "S3(보정 오라클)과 S2(판정 오라클)의 차이가 확률값의 형상을 고쳐 얻는 몫이며, 1.0과의 차이가 순위 자체가 틀려서 못 고치는 원리적 한계이다."
        }
    }

    out_path = UPPER_DIR / "S3.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
