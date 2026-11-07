#!/usr/bin/env python3
"""S8 — 업종 하나를 완벽히 맞히면 macro-F1이 얼마나 오르나

지시 011:
  - 기준 예측: 08 전체가중합 OUTER 예측 (macro-F1 = 0.54307)
  - 업종별 완벽 분류 가상 실험 (c in {0:연안복합, 1:자망, 2:통발, 3:채낚기}):
    실제가 c인 배는 전부 c로 맞추고, 실제가 c가 아닌데 c로 예측한 배는 올바른 정답으로 교정
  - 쌍별 완벽 분리 가상 실험:
    어려운 세 쌍 (0-1: 연안복합-자망, 0-2: 연안복합-통발, 1-2: 자망-통발)
  - 채낚기(126척) 표본 감도 분석: F1 +-0.05 변동 시 macro-F1 영향도
  - macro-F1 및 micro-F1(정확도) 동시 산출

출력: work/상한선_011/S8.json
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


def main():
    log("=== S8: 업종 완벽 분류 민감도 분해 시작 ===")
    npz = np.load(NPZ_PATH)
    outer_y = npz["outer_y"]

    # 08 전체가중합 가중치 및 예측 생성
    # L_base: 0.1667, M_base: 0.0833, E_base: 0.0, L_b69: 0.6667, K_base: 0.0833, w=1.75
    w_08 = {
        "L_base": 0.1667,
        "M_base": 0.0833,
        "L_b69": 0.6667,
        "K_base": 0.0833
    }
    p_mix = sum(w_08[k] * npz[f"outer_{k}"] for k in w_08)
    base_pred = (p_mix * [1.0, 1.0, 1.75, 1.0]).argmax(1)

    base_mf1 = macro_f1_fast(outer_y, base_pred)
    base_acc = acc_fast(outer_y, base_pred)
    base_cf1 = class_f1_fast(outer_y, base_pred)

    log(f"08 전체가중합 기준선: macro-F1={base_mf1:.5f}, acc={base_acc:.5f}, class_f1={base_cf1}")

    rng = np.random.default_rng(BOOT_SEED)

    # 1. 단일 업종 완벽 분류 오라클
    single_class_results = {}
    for c, cname in enumerate(CLASS_NAMES):
        # 가상 예측 생성:
        # 실제가 c인 배 -> c로 맞춤
        # 실제가 c가 아닌데 c로 잘못 예측한 배 -> 정답으로 교정
        hypo_pred = base_pred.copy()
        mask_true_c = (outer_y == c)
        mask_pred_c_false = (base_pred == c) & (outer_y != c)

        hypo_pred[mask_true_c] = c
        hypo_pred[mask_pred_c_false] = outer_y[mask_pred_c_false]

        mf1 = macro_f1_fast(outer_y, hypo_pred)
        acc = acc_fast(outer_y, hypo_pred)
        cf1 = class_f1_fast(outer_y, hypo_pred)
        d_mf1, ci_mf1, _ = bootstrap_ci(outer_y, base_pred, hypo_pred, macro_f1_fast, rng)
        d_acc, ci_acc, _ = bootstrap_ci(outer_y, base_pred, hypo_pred, acc_fast, rng)

        single_class_results[cname] = {
            "class_id": c,
            "target_n_vessels": int(mask_true_c.sum()),
            "macro_f1": round(mf1, 5),
            "delta_macro_f1": round(mf1 - base_mf1, 5),
            "ci_macro_f1": ci_mf1,
            "accuracy": round(acc, 5),
            "delta_accuracy": round(acc - base_acc, 5),
            "ci_accuracy": ci_acc,
            "class_f1": cf1
        }
        log(f"단일 완벽 [{cname:7s} ({int(mask_true_c.sum()):4d}척)]: macro-F1={mf1:.5f} (Δ+{mf1 - base_mf1:.5f}), acc={acc:.5f} (Δ+{acc - base_acc:.5f})")

    # 2. 어려운 세 쌍 완벽 분리 오라클
    pairs = [
        (0, 1, "연안복합-자망"),
        (0, 2, "연안복합-통발"),
        (1, 2, "자망-통발")
    ]
    pair_results = {}
    for c1, c2, pair_name in pairs:
        # 가상 예측: c1과 c2 사이의 혼동만 완전 해소
        # y_true in {c1, c2} 이고 pred in {c1, c2} 인 경우 정답으로 교정
        hypo_pred = base_pred.copy()
        mask_confusion = np.isin(outer_y, [c1, c2]) & np.isin(base_pred, [c1, c2])
        hypo_pred[mask_confusion] = outer_y[mask_confusion]

        mf1 = macro_f1_fast(outer_y, hypo_pred)
        acc = acc_fast(outer_y, hypo_pred)
        cf1 = class_f1_fast(outer_y, hypo_pred)
        d_mf1, ci_mf1, _ = bootstrap_ci(outer_y, base_pred, hypo_pred, macro_f1_fast, rng)
        d_acc, ci_acc, _ = bootstrap_ci(outer_y, base_pred, hypo_pred, acc_fast, rng)

        resolved_count = int((mask_confusion & (base_pred != outer_y)).sum())
        pair_results[pair_name] = {
            "pair": [c1, c2],
            "resolved_errors": resolved_count,
            "macro_f1": round(mf1, 5),
            "delta_macro_f1": round(mf1 - base_mf1, 5),
            "ci_macro_f1": ci_mf1,
            "accuracy": round(acc, 5),
            "delta_accuracy": round(acc - base_acc, 5),
            "ci_accuracy": ci_acc,
            "class_f1": cf1
        }
        log(f"쌍 분리 [{pair_name:10s} (교정 {resolved_count:4d}척)]: macro-F1={mf1:.5f} (Δ+{mf1 - base_mf1:.5f}), acc={acc:.5f} (Δ+{acc - base_acc:.5f})")

    # 3. 채낚기 표본 크기 및 민감도 분석
    n_chaenak = int((outer_y == 3).sum())
    chaenak_sensitivity = {
        "cohort_size": n_chaenak,
        "total_outer_ships": len(outer_y),
        "cohort_ratio": round(n_chaenak / len(outer_y), 4),
        "f1_weight_in_macro": 0.25,
        "theoretical_macro_impact_per_0.05_f1": 0.05 / 4.0,  # 0.0125
        "single_ship_f1_impact_approx": round((1.0 / n_chaenak) / 4.0, 5),
        "note": "채낚기는 126척(전체의 2.1%)에 불과하지만 macro-F1에서는 동일한 25% 가중치를 가지므로 단 1척의 오류가 macro-F1 약 0.002에 해당하는 강한 레버리지를 가짐."
    }

    out_json = {
        "experiment": "S8_class_sensitivity",
        "baseline_08_ensemble": {
            "macro_f1": round(base_mf1, 5),
            "accuracy": round(base_acc, 5),
            "class_f1": base_cf1
        },
        "single_class_perfect_oracle": single_class_results,
        "pair_perfect_separation_oracle": pair_results,
        "chaenak_sample_sensitivity": chaenak_sensitivity
    }

    out_path = UPPER_DIR / "S8.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
