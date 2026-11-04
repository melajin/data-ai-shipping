#!/usr/bin/env python3
"""S6 — 용량을 풀어 준 모델의 정직한 성능

지시 011:
  - 특징: F156 + T5 + B69(69) + 지역상대(70) = 305열
  - LightGBM: n_estimators=8000, learning_rate=0.01, num_leaves=127,
              min_child_samples=10, colsample_bytree=0.6, subsample=0.8, reg_lambda=1.0
  - 조기 종료: INNER, patience 200
  - 5개 시드 (42, 2026, 7, 1, 2024) 확률 평균
  - 통발 배수는 INNER에서 선택 (W_GRID), OUTER 1회 공정 평가
  - 채택 기준 (Δ ≥ +0.005 and 95% 하한 > 0) 판정

출력: work/상한선_011/S6.json
"""
from __future__ import annotations

import gc
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
DAY = WORK_DIR.parent

ORIG_ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과")
for p in (str(ORIG_ROOT / "tools"), str(ORIG_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
import run_005_F156_merge_20261101 as m  # noqa: E402
import run_005_main_20261101 as main005  # noqa: E402

SEEDS = (42, 2026, 7, 1, 2024)
W_GRID = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
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


def fit_large_lgbm(X, y, Xi, yi, seed, sw):
    import lightgbm as lgb
    mdl = lgb.LGBMClassifier(
        objective="multiclass", num_class=4, n_estimators=8000, learning_rate=0.01,
        num_leaves=127, min_child_samples=10, colsample_bytree=0.6, subsample=0.8,
        subsample_freq=1, reg_lambda=1.0, random_state=seed, n_jobs=3,
        verbosity=-1, metric="None"
    )
    mdl.fit(
        X, y, sample_weight=sw, eval_set=[(Xi, yi)], eval_metric=m.lgbm_macro_f1,
        callbacks=[lgb.early_stopping(200, first_metric_only=True, verbose=False)]
    )
    return mdl


def main():
    log("=== S6: 대용량 모델 실현 성능 시작 ===")
    t0 = time.time()
    roles = m.load_dev_roles()
    labels = m.load_labels()
    fishing_mask = m._fishing_mask_global()

    # 특징 적재
    log("B69 및 local_rel 적재")
    b69 = pd.read_csv(DAY / "work" / "behavior_B50_train2026.csv")
    b69["rfid_id"] = b69["rfid_id"].astype(str)
    b69 = b69.set_index("rfid_id").replace([np.inf, -np.inf], np.nan)
    b69_feat_cols = [c for c in b69.columns if c != "obs_days"]

    lrel = pd.read_csv(DAY / "work" / "local_rel_train2026.csv")
    lrel["rfid_id"] = lrel["rfid_id"].astype(str)
    lrel = lrel.set_index("rfid_id").replace([np.inf, -np.inf], np.nan)
    lrel_feat_cols = [c for c in lrel.columns]

    inner_preds = []
    outer_preds = []
    inner_y_list = []
    outer_y_list = []
    outer_days_list = []
    trees_per_seed = []

    for fold in m.FOLDS:
        t_f = time.time()
        fr = main005.fold_rows(fold, roles, labels)
        is_fit, is_inner, is_outer = (fr["role"] == "FIT"), (fr["role"] == "INNER"), (fr["role"] == "OUTER")
        rids = [str(r) for r in fr["rids"]]
        y = fr["y"]

        fit_ids = [fr["rids"][i] for i in np.flatnonzero(is_fit)]
        fit_label_by_rid = {fr["rids"][i]: int(fr["y"][i]) for i in np.flatnonzero(is_fit)}
        fit_rid_label = [(r, fit_label_by_rid[r]) for r in fit_ids]

        main_dicts = m._build_t5_dicts(fit_rid_label, fishing_mask, month_filter=None)
        month_dicts = {mo: m._build_t5_dicts(fit_rid_label, fishing_mask, month_filter=mo)
                       for mo in range(1, 7)}
        extra = main005.build_extra_features(fr["rids"], "T5", None, None, fishing_mask,
                                             main_dicts, month_dicts, fit_label_by_rid)
        X_base = np.concatenate([fr["feat"].to_numpy(dtype=np.float64), extra], axis=1)

        B = b69.reindex(rids)[b69_feat_cols].to_numpy(dtype=np.float64)
        L = lrel.reindex(rids)[lrel_feat_cols].to_numpy(dtype=np.float64)
        X_all = np.concatenate([X_base, B, L], axis=1)
        obs_days = b69.loc[rids, "obs_days"].to_numpy()

        log(f"Fold {fold} 305열 구성 완료: shape {X_all.shape}")

        sw = m.sqrt_weights(y[is_fit])

        p_in_seeds = []
        p_out_seeds = []
        for seed in SEEDS:
            t_s = time.time()
            mdl = fit_large_lgbm(X_all[is_fit], y[is_fit], X_all[is_inner], y[is_inner],
                                 seed, sw[y[is_fit]])
            p_in_seeds.append(mdl.predict_proba(X_all[is_inner]))
            p_out_seeds.append(mdl.predict_proba(X_all[is_outer]))
            trees_per_seed.append(int(mdl.best_iteration_ if mdl.best_iteration_ else mdl.n_estimators))
            log(f"  fold={fold} seed={seed} 완료: {trees_per_seed[-1]}트리 ({time.time()-t_s:.1f}초)")
            del mdl
            gc.collect()

        inner_preds.append(np.mean(p_in_seeds, axis=0))
        outer_preds.append(np.mean(p_out_seeds, axis=0))
        inner_y_list.append(y[is_inner])
        outer_y_list.append(y[is_outer])
        outer_days_list.append(obs_days[is_outer])
        log(f"Fold {fold} 전체 완료 ({time.time()-t_f:.1f}초)")

    inner_y_all = np.concatenate(inner_y_list)
    outer_y_all = np.concatenate(outer_y_list)
    inner_P_all = np.concatenate(inner_preds, axis=0)
    outer_P_all = np.concatenate(outer_preds, axis=0)
    outer_days_all = np.concatenate(outer_days_list)

    # 1. 통발 배수 w 선택 (INNER에서 선택)
    def eval_inner(w):
        p = inner_P_all.copy()
        p[:, 2] *= w
        return macro_f1_fast(inner_y_all, p.argmax(1))

    best_w = max(W_GRID, key=eval_inner)
    inner_score = eval_inner(best_w)
    log(f"INNER 통발 배수 선택: w={best_w} (INNER macro-F1: {inner_score:.5f})")

    # 2. OUTER 평가 (w 적용)
    outer_P_w = outer_P_all.copy()
    outer_P_w[:, 2] *= best_w
    pred_s6_macro = outer_P_w.argmax(1)

    # 정확도 최적 (w=1.0)
    pred_s6_acc = outer_P_all.argmax(1)

    # 기준선 (08 probs L_base)
    base_data = np.load(WORK_DIR / "08_probs.npz")
    base_pred_w15 = (base_data["outer_L_base"] * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    base_pred_w10 = base_data["outer_L_base"].argmax(1)

    rng = np.random.default_rng(BOOT_SEED)
    d_mf1, ci_mf1, p_mf1 = bootstrap_ci(outer_y_all, base_pred_w15, pred_s6_macro, macro_f1_fast, rng)
    d_acc, ci_acc, p_acc = bootstrap_ci(outer_y_all, base_pred_w10, pred_s6_acc, acc_fast, rng)

    s6_mf1 = macro_f1_fast(outer_y_all, pred_s6_macro)
    s6_acc = acc_fast(outer_y_all, pred_s6_macro)
    base_mf1 = macro_f1_fast(outer_y_all, base_pred_w15)
    base_acc = acc_fast(outer_y_all, base_pred_w15)
    base_cf1 = class_f1_fast(outer_y_all, base_pred_w15)
    s6_cf1 = class_f1_fast(outer_y_all, pred_s6_macro)

    log(f"S6 OUTER 결과 (w={best_w}): macro-F1={s6_mf1:.5f} (Δ {s6_mf1-base_mf1:+.5f}, 95% CI {ci_mf1}), acc={s6_acc:.5f}")
    log(f"S6 OUTER 정확도 모드 (w=1.0): acc={acc_fast(outer_y_all, pred_s6_acc):.5f} (Δ {acc_fast(outer_y_all, pred_s6_acc)-acc_fast(outer_y_all, base_pred_w10):+.5f}, 95% CI {ci_acc})")

    # 채택 기준 점검
    delta = s6_mf1 - base_mf1
    ci_ok = ci_mf1[0] > 0
    cf1_drop = max(base_cf1[i] - s6_cf1[i] for i in range(4))
    passed = (delta >= 0.005) and ci_ok and (cf1_drop <= 0.01)

    adoption_result = {
        "passed": bool(passed),
        "delta": round(delta, 5),
        "ci_lower_gt_0": bool(ci_ok),
        "ci_95": ci_mf1,
        "max_class_f1_drop": round(cf1_drop, 5)
    }

    out_json = {
        "experiment": "S6_large_capacity_model",
        "description": "305개 전체 특징 및 num_leaves=127, lr=0.01 대형 LightGBM 모델의 공정 평가 (선택은 INNER)",
        "features_count": 305,
        "seeds": list(SEEDS),
        "avg_trees_used": round(float(np.mean(trees_per_seed)), 1),
        "inner_selected_w": best_w,
        "inner_score": round(inner_score, 5),
        "macro_mode_w_selected": {
            "outer_macro_f1": round(s6_mf1, 5),
            "outer_accuracy": round(s6_acc, 5),
            "outer_class_f1": s6_cf1,
            "diff_vs_baseline_w15": round(s6_mf1 - base_mf1, 5),
            "ci_95": ci_mf1,
            "p_gt_0": p_mf1,
            "adoption_candidate_check": adoption_result
        },
        "acc_mode_w_1.0": {
            "outer_accuracy": round(acc_fast(outer_y_all, pred_s6_acc), 5),
            "outer_macro_f1": round(macro_f1_fast(outer_y_all, pred_s6_acc), 5),
            "outer_class_f1": class_f1_fast(outer_y_all, pred_s6_acc),
            "diff_vs_baseline_w10": round(acc_fast(outer_y_all, pred_s6_acc) - acc_fast(outer_y_all, base_pred_w10), 5),
            "ci_95": ci_acc,
            "p_gt_0": p_acc
        }
    }

    out_path = UPPER_DIR / "S6.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path} (총 소요 시간: {time.time()-t0:.1f}초)")


if __name__ == "__main__":
    main()
