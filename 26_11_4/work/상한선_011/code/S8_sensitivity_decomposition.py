#!/usr/bin/env python3
"""S8 — 업종 하나/쌍을 완벽히 맞히면 macro-F1 / micro-F1이 얼마나 오르나

지시 011:
  - 기준 예측: 08의 전체가중합 OUTER 예측 (w=1.75 및 w=1.0)
  - 단일 업종 완벽 분류 가정 (실제 c는 전부 c로 맞추고, 다른 업종인데 c로 오예측한 것은 실제 라벨로 교정)
  - 쌍 단위 완벽 분리 가정 (연안복합-자망, 연안복합-통발, 자망-통발 간 상호 혼동 완전 해소)
  - 채낚기(126척) F1 ±0.05 변동 시 macro-F1 vs micro-F1 민감도 비교

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


def main():
    log("=== S8: 업종 완벽 분류 민감도 분해 시작 ===")
    data = np.load(NPZ_PATH)
    outer_y = data["outer_y"]

    # 08 전체가중합 재구성
    wt = {"L_base": 0.1667, "M_base": 0.0833, "E_base": 0.0, "L_b69": 0.6667, "K_base": 0.0833}
    P_ens = (wt["L_base"] * data["outer_L_base"] +
             wt["M_base"] * data["outer_M_base"] +
             wt["E_base"] * data["outer_E_base"] +
             wt["L_b69"] * data["outer_L_b69"] +
             wt["K_base"] * data["outer_K_base"])

    P_w175 = P_ens.copy()
    P_w175[:, 2] *= 1.75
    base_pred = P_w175.argmax(1)

    rng = np.random.default_rng(BOOT_SEED)
    base_mf1 = macro_f1_fast(outer_y, base_pred)
    base_acc = acc_fast(outer_y, base_pred)
    base_cf1 = class_f1_fast(outer_y, base_pred)
    log(f"08 전체가중합 기준 (w=1.75): macro-F1={base_mf1:.5f}, acc={base_acc:.5f}, class_f1={base_cf1}")

    # 1. 단일 업종 완벽 분류
    single_class_results = {}
    for c, name in enumerate(CLASS_NAMES):
        p = base_pred.copy()
        # 실제 c인 배는 전부 c로
        p[outer_y == c] = c
        # 실제 c가 아닌데 c로 오예측한 것은 실제 라벨로 교정
        p[(outer_y != c) & (base_pred == c)] = outer_y[(outer_y != c) & (base_pred == c)]

        mf1 = macro_f1_fast(outer_y, p)
        acc = acc_fast(outer_y, p)
        cf1 = class_f1_fast(outer_y, p)
        d_mf1, ci_mf1, p_mf1 = bootstrap_ci(outer_y, base_pred, p, macro_f1_fast, rng)
        d_acc, ci_acc, p_acc = bootstrap_ci(outer_y, base_pred, p, acc_fast, rng)

        single_class_results[name] = {
            "class_idx": c,
            "true_count": int((outer_y == c).sum()),
            "macro_f1": round(mf1, 5),
            "accuracy": round(acc, 5),
            "class_f1": cf1,
            "diff_macro_f1": round(mf1 - base_mf1, 5),
            "ci_macro_f1": ci_mf1,
            "diff_accuracy": round(acc - base_acc, 5),
            "ci_accuracy": ci_acc
        }
        log(f"단일 완벽 {name:8s} -> macro-F1: {mf1:.5f} (Δ {mf1-base_mf1:+.5f}), acc: {acc:.5f} (Δ {acc-base_acc:+.5f})")

    # 2. 어려운 세 쌍 완벽 분리
    pair_candidates = [
        (0, 1, "연안복합_vs_자망"),
        (0, 2, "연안복합_vs_통발"),
        (1, 2, "자망_vs_통발")
    ]
    pair_results = {}
    for c1, c2, name in pair_candidates:
        p = base_pred.copy()
        mask1 = (outer_y == c1) & (base_pred == c2)
        mask2 = (outer_y == c2) & (base_pred == c1)
        p[mask1] = c1
        p[mask2] = c2

        mf1 = macro_f1_fast(outer_y, p)
        acc = acc_fast(outer_y, p)
        cf1 = class_f1_fast(outer_y, p)
        d_mf1, ci_mf1, p_mf1 = bootstrap_ci(outer_y, base_pred, p, macro_f1_fast, rng)
        d_acc, ci_acc, p_acc = bootstrap_ci(outer_y, base_pred, p, acc_fast, rng)

        pair_results[name] = {
            "pair": [c1, c2],
            "corrected_confused_ships": int(mask1.sum() + mask2.sum()),
            "macro_f1": round(mf1, 5),
            "accuracy": round(acc, 5),
            "class_f1": cf1,
            "diff_macro_f1": round(mf1 - base_mf1, 5),
            "ci_macro_f1": ci_mf1,
            "diff_accuracy": round(acc - base_acc, 5),
            "ci_accuracy": ci_acc
        }
        log(f"쌍 완벽 분리 {name:15s} (교정 {mask1.sum()+mask2.sum()}척) -> macro-F1: {mf1:.5f} (Δ {mf1-base_mf1:+.5f}), acc: {acc:.5f} (Δ {acc-base_acc:+.5f})")

    # 3. 채낚기 126척 표본 크기 민감도
    squid_n = int((outer_y == 3).sum())
    total_n = len(outer_y)
    squid_share = round(squid_n / total_n * 100, 2)
    sensitivity = {
        "squid_count": squid_n,
        "total_count": total_n,
        "squid_share_pct": squid_share,
        "delta_squid_f1_0.05": {
            "macro_f1_impact": round(0.05 / 4.0, 5),
            "micro_f1_accuracy_impact_approx": round(0.05 * (squid_n / total_n), 5),
            "sensitivity_ratio_macro_vs_micro": round((0.05 / 4.0) / (0.05 * (squid_n / total_n)), 2),
            "explanation": "채낚기 F1이 ±0.05 흔들릴 때 macro-F1은 ±0.0125 변하지만, 대회 지표인 micro-F1(정확도)은 ±0.00107만 변함 (macro가 11.7배 민감)"
        }
    }
    log(f"채낚기 민감도: macro는 {sensitivity['delta_squid_f1_0.05']['macro_f1_impact']}, micro는 {sensitivity['delta_squid_f1_0.05']['micro_f1_accuracy_impact_approx']}")

    out_json = {
        "experiment": "S8_sensitivity_decomposition",
        "baseline_08_ensemble": {
            "type": "실현(08 전체가중합)",
            "w": 1.75,
            "macro_f1": round(base_mf1, 5),
            "accuracy": round(base_acc, 5),
            "class_f1": base_cf1
        },
        "single_class_perfect_oracle": single_class_results,
        "pairwise_perfect_oracle": pair_results,
        "minority_class_sensitivity": sensitivity
    }

    out_path = UPPER_DIR / "S8.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
