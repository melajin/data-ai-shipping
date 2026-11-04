#!/usr/bin/env python3
"""S4 — 모델 선택 오라클: 여러 모델 중 맞는 걸 고를 수 있다면

지시 011:
  - 후보 6개 모델:
    1) L_base (LightGBM F156+T5)
    2) M_base (MLP F156+T5)
    3) E_base (ExtraTrees F156+T5)
    4) L_b69  (LightGBM F156+T5+B69)
    5) K_base (kNN F156+T5)
    6) TabICL_A (TabICLv2 seed 42 & 2026 평균)
  - 오라클 1 (모델 선택): 선박마다 맞힌 모델이 하나라도 있으면 정답 처리
  - 오라클 2 (가중합): 6개 확률 가중합 가중치를 OUTER에서 직접 최적화 (격자 0~1 0.05 간격, 배수 포함)
  - 실현값 대조: 같은 가중치를 INNER에서 최적화 후 OUTER 적용
  - 0개~6개 모델이 맞힌 선박 분포 분석 (6개 모두 틀린 선박 규명)
  - 5,000회 부트스트랩 95% 신뢰구간 산출

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

import run_005_F156_merge_20261101 as m
import run_005_main_20261101 as main005

TABICL_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")

BOOT_SEED = 20261104
N_BOOT = 5000
BINS = [(1, 7), (8, 30), (31, 90), (91, 10 ** 9)]
CLASS_NAMES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
W_GRID = (1.0, 1.25, 1.5, 1.75, 2.0)


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


def coord_descent_ensemble(P_dict: dict[str, np.ndarray], y: np.ndarray,
                           grid: np.ndarray, rounds: int = 5) -> tuple[dict[str, float], float, float]:
    names = list(P_dict.keys())
    weights = {k: (1.0 if k == "L_base" else 0.0) for k in names}

    def eval_wt(wt, w_val):
        tot = sum(wt.values())
        if tot <= 0:
            return -1.0
        p_mix = sum(wt[k] * P_dict[k] for k in names) / tot
        pred = (p_mix * [1.0, 1.0, w_val, 1.0]).argmax(1)
        return macro_f1_fast(y, pred)

    best_w = max(W_GRID, key=lambda ww: eval_wt(weights, ww))
    best_score = eval_wt(weights, best_w)

    for r in range(rounds):
        improved = False
        for k in names:
            cur = weights[k]
            for g in grid:
                if g == cur:
                    continue
                trial = dict(weights)
                trial[k] = g
                for ww in W_GRID:
                    s = eval_wt(trial, ww)
                    if s > best_score + 1e-12:
                        best_score = s
                        weights = trial
                        best_w = ww
                        improved = True
        if not improved:
            break

    tot = sum(weights.values())
    norm_wt = {k: round(v / tot, 4) for k, v in weights.items()}
    return norm_wt, best_w, float(best_score)


def main():
    log("=== S4: 모델 선택 및 가중합 오라클 시작 ===")
    npz = np.load(NPZ_PATH)
    outer_y = npz["outer_y"]
    inner_y = npz["inner_y"]
    outer_days = npz["outer_days"]

    # 1. TabICLv2 로드 및 정렬
    log("TabICLv2 데이터 로드 및 fold 순서 정렬 중...")
    roles = m.load_dev_roles()
    labels = m.load_labels()
    outer_rids = []
    inner_rids = []
    for fold in m.FOLDS:
        fr = main005.fold_rows(fold, roles, labels)
        outer_rids.extend([fr["rids"][i] for i in np.flatnonzero(fr["role"] == "OUTER")])
        inner_rids.extend([fr["rids"][i] for i in np.flatnonzero(fr["role"] == "INNER")])

    df42 = pd.read_csv(TABICL_DIR / "seed_42" / "OOF_probabilities_and_roles.csv")
    df2026 = pd.read_csv(TABICL_DIR / "seed_2026" / "OOF_probabilities_and_roles.csv")
    df42["rfid_id"] = df42["rfid_id"].astype(str)
    df2026["rfid_id"] = df2026["rfid_id"].astype(str)
    df42 = df42.set_index("rfid_id")
    df2026 = df2026.set_index("rfid_id")

    # 순서 검증
    tab_out_y = df42.loc[outer_rids, "y_true"].to_numpy()
    assert np.array_equal(tab_out_y, outer_y), "TabICL OUTER y_true 불일치!"
    tab_in_y = df42.loc[inner_rids, "y_true"].to_numpy()
    assert np.array_equal(tab_in_y, inner_y), "TabICL INNER y_true 불일치!"

    p_cols = ["p0", "p1", "p2", "p3"]
    tab_out_p = (df42.loc[outer_rids, p_cols].to_numpy() + df2026.loc[outer_rids, p_cols].to_numpy()) / 2.0
    tab_in_p = (df42.loc[inner_rids, p_cols].to_numpy() + df2026.loc[inner_rids, p_cols].to_numpy()) / 2.0

    # 6개 모델 딕셔너리 구축
    outer_models = {
        "L_base": npz["outer_L_base"],
        "M_base": npz["outer_M_base"],
        "E_base": npz["outer_E_base"],
        "L_b69": npz["outer_L_b69"],
        "K_base": npz["outer_K_base"],
        "TabICL_A": tab_out_p
    }

    inner_models = {
        "L_base": npz["inner_L_base"],
        "M_base": npz["inner_M_base"],
        "E_base": npz["inner_E_base"],
        "L_b69": npz["inner_L_b69"],
        "K_base": npz["inner_K_base"],
        "TabICL_A": tab_in_p
    }

    rng = np.random.default_rng(BOOT_SEED)

    # 기준선 (L_base w=1.5)
    base_pred = (outer_models["L_base"] * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    base_eval = evaluate_full(outer_y, outer_days, base_pred, base_pred, rng)
    log(f"기준선 L_base (w=1.5): macro-F1={base_eval['macro_f1']}, acc={base_eval['accuracy']}")

    # 2. 개별 모델 성능 및 예측 수집 (통발 w=1.5 적용)
    preds_per_model = {}
    correct_masks = []
    for name, P in outer_models.items():
        w_apply = [1.0, 1.0, 1.5, 1.0]
        pr = (P * w_apply).argmax(1)
        preds_per_model[name] = pr
        c_mask = (pr == outer_y)
        correct_masks.append(c_mask)
        mf1 = macro_f1_fast(outer_y, pr)
        acc = acc_fast(outer_y, pr)
        log(f"단독 {name:10s} (w=1.5) -> macro-F1: {mf1:.5f}, acc: {acc:.5f}")

    correct_matrix = np.array(correct_masks)  # shape (6, 5897)
    num_correct_per_ship = correct_matrix.sum(axis=0)  # shape (5897,)

    # 정답 맞힌 모델 수 분포
    dist_counts = {int(k): int((num_correct_per_ship == k).sum()) for k in range(7)}
    log(f"모델 적중 수 분포 (0~6개): {dist_counts}")

    # 3. 오라클 1: 모델 선택 오라클 (하나라도 맞히면 정답)
    # 어떤 모델도 못 맞힌 선박은 기준선(L_base)의 예측값을 유지
    oracle1_pred = base_pred.copy()
    any_correct = (num_correct_per_ship > 0)
    oracle1_pred[any_correct] = outer_y[any_correct]

    oracle1_eval = evaluate_full(outer_y, outer_days, oracle1_pred, base_pred, rng)
    log(f"오라클 1 (모델 선택 상한): macro-F1={oracle1_eval['macro_f1']}, acc={oracle1_eval['accuracy']}")

    # 4. 오라클 2 & 실현값: 6개 모델 가중합 최적화
    grid = np.arange(0.0, 1.01, 0.05)

    # (a) INNER에서 최적화 (실현 후보)
    log("INNER에서 6개 모델 가중합 최적화 중...")
    in_weights, in_w, in_score = coord_descent_ensemble(inner_models, inner_y, grid)
    p_in_mix = sum(in_weights[k] * outer_models[k] for k in outer_models)
    pred_in_ens = (p_in_mix * [1.0, 1.0, in_w, 1.0]).argmax(1)
    eval_in_ens = evaluate_full(outer_y, outer_days, pred_in_ens, base_pred, rng)
    log(f"INNER 최적화 가중치: {in_weights}, w={in_w} -> OUTER macro-F1={eval_in_ens['macro_f1']}, acc={eval_in_ens['accuracy']}")

    # (b) OUTER에서 직접 최적화 (오라클 상한)
    log("OUTER에서 6개 모델 가중합 오라클 최적화 중...")
    out_weights, out_w, out_score = coord_descent_ensemble(outer_models, outer_y, grid)
    p_out_mix = sum(out_weights[k] * outer_models[k] for k in outer_models)
    pred_out_ens = (p_out_mix * [1.0, 1.0, out_w, 1.0]).argmax(1)
    eval_out_ens = evaluate_full(outer_y, outer_days, pred_out_ens, base_pred, rng)
    log(f"OUTER 오라클 가중치: {out_weights}, w={out_w} -> OUTER macro-F1={eval_out_ens['macro_f1']}, acc={eval_out_ens['accuracy']}")

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

    adoption_in_ens = check_adoption(
        eval_in_ens, base_eval["macro_f1"], base_eval["class_f1"],
        base_eval["by_days"]["1-7"]["macro_f1"]
    )

    out_json = {
        "experiment": "S4_model_oracle",
        "models": list(outer_models.keys()),
        "distribution_num_correct_models": dist_counts,
        "blind_spot_all_wrong_ships": dist_counts[0],
        "blind_spot_all_wrong_ratio": round(dist_counts[0] / len(outer_y), 4),
        "baseline_L_base": {
            "type": "실현(기준선)",
            "metrics": base_eval
        },
        "inner_selected_ensemble_6m": {
            "type": "실현(채택후보)",
            "weights": in_weights,
            "w": in_w,
            "inner_macro_f1": round(in_score, 5),
            "metrics": eval_in_ens,
            "adoption_check": adoption_in_ens
        },
        "outer_oracle_weighted_ensemble": {
            "type": "상한(오라클_가중합)",
            "weights": out_weights,
            "w": out_w,
            "outer_score": round(out_score, 5),
            "metrics": eval_out_ens
        },
        "outer_oracle_model_selection": {
            "type": "상한(가장느슨_모델선택오라클)",
            "description": "선박마다 6개 모델 중 하나라도 맞히면 정답 처리",
            "metrics": oracle1_eval
        }
    }

    out_path = UPPER_DIR / "S4.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
