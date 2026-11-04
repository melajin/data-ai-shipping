#!/usr/bin/env python3
"""S4 — 모델 선택 오라클: 여러 모델 중 맞는 걸 고를 수 있다면

지시 011:
  - 후보 6개: L_base, M_base, E_base, L_b69, K_base, TabICL_A
  - TabICL_A: seed 42와 seed 2026 평균 후 outer_rids 순서로 정렬 (y_true 전수 일치 확인)
  - 오라클 1 (모델 선택): 선박마다 6개 모델 중 하나라도 맞힌 모델이 있으면 정답 처리
  - 오라클 2 (가중합): 6개 확률의 가중합 가중치를 OUTER에서 직접 최적화 (좌표하강, 0~1 0.05 간격, w 함께)
  - 실현값 대조: 08의 전체가중합 (0.54307)
  - 맞힌 모델 수 분포 (0개 ~ 6개) 산출
  - macro-F1 및 micro-F1(정확도) 각각 최적화 및 5,000회 부트스트랩 평가

출력: work/상한선_011/S4.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
UPPER_DIR = HERE.parent
WORK_DIR = UPPER_DIR.parent
NPZ_PATH = WORK_DIR / "08_probs.npz"

ORIG_ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과")
for p in (str(ORIG_ROOT / "tools"), str(ORIG_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
import run_005_F156_merge_20261101 as m  # noqa: E402
import run_005_main_20261101 as main005  # noqa: E402

BOOT_SEED = 20261104
N_BOOT = 5000
BINS = [(1, 7), (8, 30), (31, 90), (91, 10 ** 9)]
CLASS_NAMES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
MEMBERS = ["L_base", "M_base", "E_base", "L_b69", "K_base", "TabICL_A"]


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


def optimize_weights_outer(P_dict: dict[str, np.ndarray], y: np.ndarray, metric_fn,
                           w_grid=(0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0), rounds=4):
    grid = np.arange(0.0, 1.01, 0.05)
    wt = {k: (1.0 if k == "L_base" else 0.0) for k in MEMBERS}

    def score(wt_, w_):
        tot = sum(wt_.values())
        if tot <= 0:
            return -1.0
        p = sum(wt_[k] * P_dict[k] for k in MEMBERS) / tot
        p_adj = p.copy()
        p_adj[:, 2] *= w_
        return metric_fn(y, p_adj.argmax(1))

    best_w = max(w_grid, key=lambda ww: score(wt, ww))
    best = score(wt, best_w)

    for r in range(rounds):
        improved = False
        for k in MEMBERS:
            cur = wt[k]
            for g in grid:
                if g == cur:
                    continue
                trial = dict(wt)
                trial[k] = g
                for ww in w_grid:
                    s = score(trial, ww)
                    if s > best + 1e-12:
                        best, wt, best_w, improved = s, trial, ww, True
        if not improved:
            break
    tot = sum(wt.values())
    norm_wt = {k: round(float(v / tot), 4) for k, v in wt.items()}
    return norm_wt, float(best_w), float(best)


def main():
    log("=== S4: 모델 선택 오라클 시작 ===")
    data = np.load(NPZ_PATH)
    outer_y = data["outer_y"]
    outer_days = data["outer_days"]

    # Load and align TabICL A
    roles = m.load_dev_roles()
    labels = m.load_labels()
    outer_rids = []
    for fold in m.FOLDS:
        fr = main005.fold_rows(fold, roles, labels)
        is_outer = (fr["role"] == "OUTER")
        outer_rids.extend([fr["rids"][i] for i in np.flatnonzero(is_outer)])

    T = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
    tab_42 = pd.read_csv(T / "evaluation" / "seed_42" / "OOF_probabilities_and_roles.csv")
    tab_2026 = pd.read_csv(T / "evaluation" / "seed_2026" / "OOF_probabilities_and_roles.csv")
    tab_42["rfid_id_str"] = tab_42["rfid_id"].astype(str)
    tab_2026["rfid_id_str"] = tab_2026["rfid_id"].astype(str)
    prob_cols = ["p0", "p1", "p2", "p3"]
    tab_avg = tab_42.copy()
    for col in prob_cols:
        tab_avg[col] = (tab_42[col] + tab_2026[col]) / 2.0
    tab_map = tab_avg.set_index("rfid_id_str")
    aligned_tab = tab_map.reindex([str(r) for r in outer_rids])
    assert (aligned_tab["y_true"].to_numpy() == outer_y).all(), "TabICL A y_true mismatch!"
    tab_outer = aligned_tab[prob_cols].to_numpy()

    P_outer = {
        "L_base": data["outer_L_base"],
        "M_base": data["outer_M_base"],
        "E_base": data["outer_E_base"],
        "L_b69": data["outer_L_b69"],
        "K_base": data["outer_K_base"],
        "TabICL_A": tab_outer
    }

    rng = np.random.default_rng(BOOT_SEED)
    base_pred_w15 = (P_outer["L_base"] * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    base_pred_w10 = P_outer["L_base"].argmax(1)
    eval_base_w15 = evaluate_full(outer_y, outer_days, base_pred_w15, base_pred_w15, rng)
    eval_base_w10 = evaluate_full(outer_y, outer_days, base_pred_w10, base_pred_w10, rng)

    # Individual model performance
    indiv_perf = {}
    preds = {}
    for k in MEMBERS:
        pred_k = P_outer[k].argmax(1)
        preds[k] = pred_k
        indiv_perf[k] = {
            "macro_f1": round(macro_f1_fast(outer_y, pred_k), 5),
            "accuracy": round(acc_fast(outer_y, pred_k), 5)
        }
    log(f"개별 모델 (w=1.0) 성능: {indiv_perf}")

    # 맞힌 모델 수 분포 (0개 ~ 6개)
    correct_masks = {k: (preds[k] == outer_y) for k in MEMBERS}
    n_correct = np.zeros(len(outer_y), dtype=int)
    for k in MEMBERS:
        n_correct += correct_masks[k].astype(int)

    counts_correct = [int(c) for c in np.bincount(n_correct, minlength=7)]
    distribution = {
        f"{i}_models_correct": {
            "count": counts_correct[i],
            "percentage": round(counts_correct[i] / len(outer_y) * 100, 2)
        }
        for i in range(7)
    }
    log(f"맞힌 모델 수 분포: {distribution}")

    # 1. 오라클 1 (모델 선택: 맞힌 모델이 하나라도 있으면 정답)
    any_correct = (n_correct > 0)
    # 모두 틀린 선박은 L_base의 오답을 그대로 둠
    pred_oracle_sel = np.where(any_correct, outer_y, preds["L_base"])
    eval_oracle_sel_vs_w15 = evaluate_full(outer_y, outer_days, pred_oracle_sel, base_pred_w15, rng)
    eval_oracle_sel_vs_w10 = evaluate_full(outer_y, outer_days, pred_oracle_sel, base_pred_w10, rng)
    log(f"오라클 1 (모델선택) -> macro-F1: {eval_oracle_sel_vs_w15['macro_f1']}, acc: {eval_oracle_sel_vs_w15['accuracy']}")

    # 2. 오라클 2 (가중합 직접 최적화)
    # (a) macro-F1 기준
    wt_macro, w_opt_macro, s_opt_macro = optimize_weights_outer(P_outer, outer_y, macro_f1_fast)
    p_wt_macro = sum(wt_macro[k] * P_outer[k] for k in MEMBERS)
    p_wt_macro[:, 2] *= w_opt_macro
    pred_oracle_wt_macro = p_wt_macro.argmax(1)
    eval_oracle_wt_macro = evaluate_full(outer_y, outer_days, pred_oracle_wt_macro, base_pred_w15, rng)
    log(f"오라클 2 (가중합 macro) wt: {wt_macro}, w: {w_opt_macro} -> macro-F1: {eval_oracle_wt_macro['macro_f1']}, acc: {eval_oracle_wt_macro['accuracy']}")

    # (b) accuracy 기준
    wt_acc, w_opt_acc, s_opt_acc = optimize_weights_outer(P_outer, outer_y, acc_fast)
    p_wt_acc = sum(wt_acc[k] * P_outer[k] for k in MEMBERS)
    p_wt_acc[:, 2] *= w_opt_acc
    pred_oracle_wt_acc = p_wt_acc.argmax(1)
    eval_oracle_wt_acc = evaluate_full(outer_y, outer_days, pred_oracle_wt_acc, base_pred_w10, rng)
    log(f"오라클 2 (가중합 acc) wt: {wt_acc}, w: {w_opt_acc} -> macro-F1: {eval_oracle_wt_acc['macro_f1']}, acc: {eval_oracle_wt_acc['accuracy']}")

    # 3. 실현값 대조 (08의 전체가중합 결과 불러오기)
    with open(WORK_DIR.parent / "results" / "08_final_ensemble.json", encoding="utf-8") as f:
        res08 = json.load(f)
    realized_08 = res08["results"]["전체가중합"]

    out_json = {
        "experiment": "S4_model_choice_oracle",
        "members": MEMBERS,
        "class_order": CLASS_NAMES,
        "individual_models_w_1.0": indiv_perf,
        "correct_models_distribution": distribution,
        "zero_correct_unreachable_ships": {
            "count": counts_correct[0],
            "percentage": round(counts_correct[0] / len(outer_y) * 100, 2),
            "interpretation": "현재 모델군(6종) 중 어떤 단일 모델도 맞히지 못한 선박으로, 앙상블로 도달 불가능한 영역"
        },
        "realized_08_ensemble": {
            "type": "실현(08 INNER 선택)",
            "weights": realized_08["weights"],
            "w": realized_08["w"],
            "outer_macro_f1": realized_08["outer_macro_f1"],
            "outer_class_f1": realized_08["outer_class_f1"],
            "diff_vs_L_base": realized_08["diff_vs_L_base"],
            "paired_95ci": realized_08["paired_95ci"]
        },
        "oracle_1_model_selection": {
            "type": "상한(가장 느슨한 오라클)",
            "description": "선박마다 6개 모델 중 하나라도 맞힌 모델이 있으면 정답 처리",
            "metrics_vs_w15": eval_oracle_sel_vs_w15,
            "metrics_vs_w10": eval_oracle_sel_vs_w10
        },
        "oracle_2_weighted_sum_macro": {
            "type": "상한(가중합 오라클_macro최적)",
            "weights": wt_macro,
            "w": w_opt_macro,
            "metrics_vs_w15": eval_oracle_wt_macro
        },
        "oracle_2_weighted_sum_acc": {
            "type": "상한(가중합 오라클_acc최적)",
            "weights": wt_acc,
            "w": w_opt_acc,
            "metrics_vs_w10": eval_oracle_wt_acc
        }
    }

    out_path = UPPER_DIR / "S4.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
