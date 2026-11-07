#!/usr/bin/env python3
"""S5 — 모델 용량 상한 (진단용)

지시 011:
  - 각 fold에서 FIT으로 학습한 LightGBM으로 FIT 자신을 예측
  - 3개 시드 (42, 2026, 7) 확률 평균
  - FIT macro-F1/micro-F1(정확도)과 OUTER의 차이(일반화 갭) 진단
  - 통발 배수 w=1.5 및 w=1.0 각각 산출

출력: work/상한선_011/S5.json
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
UPPER_DIR = HERE.parent
WORK_DIR = UPPER_DIR.parent

ORIG_ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과")
for p in (str(ORIG_ROOT / "tools"), str(ORIG_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
import run_005_F156_merge_20261101 as m  # noqa: E402
import run_005_main_20261101 as main005  # noqa: E402

SEEDS = (42, 2026, 7)
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


def fit_lgbm(X, y, Xi, yi, seed, sw):
    import lightgbm as lgb
    mdl = lgb.LGBMClassifier(
        objective="multiclass", num_class=4, n_estimators=2000, learning_rate=0.03,
        num_leaves=31, min_child_samples=30, colsample_bytree=0.8, subsample=0.9,
        subsample_freq=1, reg_lambda=2.0, random_state=seed, n_jobs=3,
        verbosity=-1, metric="None"
    )
    mdl.fit(
        X, y, sample_weight=sw, eval_set=[(Xi, yi)], eval_metric=m.lgbm_macro_f1,
        callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)]
    )
    return mdl


def main():
    log("=== S5: 모델 용량 상한 진단 시작 ===")
    t0 = time.time()
    roles = m.load_dev_roles()
    labels = m.load_labels()
    fishing_mask = m._fishing_mask_global()

    fit_preds = []
    outer_preds = []
    y_fits = []
    y_outers = []

    for fold in m.FOLDS:
        t_f = time.time()
        fr = main005.fold_rows(fold, roles, labels)
        is_fit, is_inner, is_outer = (fr["role"] == "FIT"), (fr["role"] == "INNER"), (fr["role"] == "OUTER")
        fit_ids = [fr["rids"][i] for i in np.flatnonzero(is_fit)]
        fit_label_by_rid = {fr["rids"][i]: int(fr["y"][i]) for i in np.flatnonzero(is_fit)}
        fit_rid_label = [(r, fit_label_by_rid[r]) for r in fit_ids]

        main_dicts = m._build_t5_dicts(fit_rid_label, fishing_mask, month_filter=None)
        month_dicts = {mo: m._build_t5_dicts(fit_rid_label, fishing_mask, month_filter=mo)
                       for mo in range(1, 7)}
        extra = main005.build_extra_features(fr["rids"], "T5", None, None, fishing_mask,
                                             main_dicts, month_dicts, fit_label_by_rid)
        X = np.concatenate([fr["feat"].to_numpy(dtype=np.float64), extra], axis=1)

        sw = m.sqrt_weights(fr["y"][is_fit])

        p_fit_seeds = []
        p_outer_seeds = []
        for seed in SEEDS:
            mdl = fit_lgbm(X[is_fit], fr["y"][is_fit], X[is_inner], fr["y"][is_inner], seed, sw[fr["y"][is_fit]])
            p_fit_seeds.append(mdl.predict_proba(X[is_fit]))
            p_outer_seeds.append(mdl.predict_proba(X[is_outer]))
            del mdl
            gc.collect()

        fit_preds.append(np.mean(p_fit_seeds, axis=0))
        outer_preds.append(np.mean(p_outer_seeds, axis=0))
        y_fits.append(fr["y"][is_fit])
        y_outers.append(fr["y"][is_outer])
        log(f"Fold {fold} 완료 ({time.time()-t_f:.1f}초)")

    all_y_fit = np.concatenate(y_fits)
    all_y_outer = np.concatenate(y_outers)
    all_p_fit = np.concatenate(fit_preds, axis=0)
    all_p_outer = np.concatenate(outer_preds, axis=0)

    # 1. w=1.5 (macro용)
    fit_pred_w15 = (all_p_fit * [1.0, 1.0, 1.5, 1.0]).argmax(1)
    outer_pred_w15 = (all_p_outer * [1.0, 1.0, 1.5, 1.0]).argmax(1)

    fit_mf1_w15 = macro_f1_fast(all_y_fit, fit_pred_w15)
    fit_acc_w15 = acc_fast(all_y_fit, fit_pred_w15)
    outer_mf1_w15 = macro_f1_fast(all_y_outer, outer_pred_w15)
    outer_acc_w15 = acc_fast(all_y_outer, outer_pred_w15)

    # 2. w=1.0 (acc용)
    fit_pred_w10 = all_p_fit.argmax(1)
    outer_pred_w10 = all_p_outer.argmax(1)

    fit_mf1_w10 = macro_f1_fast(all_y_fit, fit_pred_w10)
    fit_acc_w10 = acc_fast(all_y_fit, fit_pred_w10)
    outer_mf1_w10 = macro_f1_fast(all_y_outer, outer_pred_w10)
    outer_acc_w10 = acc_fast(all_y_outer, outer_pred_w10)

    log(f"FIT 자기 예측 (w=1.5): macro-F1={fit_mf1_w15:.5f}, acc={fit_acc_w15:.5f}")
    log(f"OUTER 예측 (w=1.5): macro-F1={outer_mf1_w15:.5f}, acc={outer_acc_w15:.5f}")
    log(f"일반화 갭 (FIT - OUTER): Δmacro={fit_mf1_w15-outer_mf1_w15:+.5f}, Δacc={fit_acc_w15-outer_acc_w15:+.5f}")

    out_json = {
        "experiment": "S5_model_capacity",
        "description": "FIT 자기 예측과 OUTER 예측의 일반화 갭 비교 (진단용)",
        "interpretation": "FIT 점수 자체가 높지 않다면 모델 용량 부족(언더피팅), FIT은 매우 높은데 OUTER가 낮다면 일반화 한계(과적합/특징 중복/누락 정보).",
        "w_1.5_macro_mode": {
            "fit_macro_f1": round(fit_mf1_w15, 5),
            "fit_accuracy": round(fit_acc_w15, 5),
            "fit_class_f1": class_f1_fast(all_y_fit, fit_pred_w15),
            "outer_macro_f1": round(outer_mf1_w15, 5),
            "outer_accuracy": round(outer_acc_w15, 5),
            "outer_class_f1": class_f1_fast(all_y_outer, outer_pred_w15),
            "gap_macro_f1_fit_minus_outer": round(fit_mf1_w15 - outer_mf1_w15, 5),
            "gap_accuracy_fit_minus_outer": round(fit_acc_w15 - outer_acc_w15, 5)
        },
        "w_1.0_acc_mode": {
            "fit_macro_f1": round(fit_mf1_w10, 5),
            "fit_accuracy": round(fit_acc_w10, 5),
            "fit_class_f1": class_f1_fast(all_y_fit, fit_pred_w10),
            "outer_macro_f1": round(outer_mf1_w10, 5),
            "outer_accuracy": round(outer_acc_w10, 5),
            "outer_class_f1": class_f1_fast(all_y_outer, outer_pred_w10),
            "gap_macro_f1_fit_minus_outer": round(fit_mf1_w10 - outer_mf1_w10, 5),
            "gap_accuracy_fit_minus_outer": round(fit_acc_w10 - outer_acc_w10, 5)
        }
    }

    out_path = UPPER_DIR / "S5.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path} (총 소요 시간: {time.time()-t0:.1f}초)")


if __name__ == "__main__":
    main()
