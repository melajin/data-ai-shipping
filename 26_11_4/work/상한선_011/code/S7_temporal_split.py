#!/usr/bin/env python3
"""S7 — 같은 배의 두 기간이 같은 업종으로 보이는가 (데이터 안정성 바닥)

지시 011:
  - 2026 선박마다 1~3월 (전반기) / 4~6월 (후반기) 분할
  - 각 반쪽에서 B69 특징 추출
  - 양쪽 반에 각각 관측 7일 이상 있는 선박만 사용 (척수 보고)
  - 3-fold FIT으로 학습한 B69 전용 LightGBM(06의 N1 설정)으로 전반기/후반기 각각 예측
  - 두 예측 일치율, 전반기만/후반기만/둘다맞음/둘다틀림 비율
  - 두 반쪽 B69 벡터의 코사인 유사도 분포

출력: work/상한선_011/S7.json
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

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

SRC_PARQUET = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\26_11_2\work\재식별_투트랙_001r1\s3_hourly.parquet")
SEEDS = (42, 2026, 7)
CLASS_NAMES = ["연안복합", "자망", "통발", "채낚기연승낚시"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fit_lgbm(X, y, Xi, yi, seed, sample_weight=None):
    import lightgbm as lgb
    mdl = lgb.LGBMClassifier(
        objective="multiclass", num_class=4, n_estimators=2000, learning_rate=0.03,
        num_leaves=31, min_child_samples=30, colsample_bytree=0.8, subsample=0.9,
        subsample_freq=1, reg_lambda=2.0, random_state=seed, n_jobs=3,
        verbosity=-1, metric="None"
    )
    mdl.fit(X, y, sample_weight=sample_weight, eval_set=[(Xi, yi)],
            eval_metric=m.lgbm_macro_f1,
            callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)])
    return mdl


def get_or_build_half_b69() -> tuple[pd.DataFrame, pd.DataFrame]:
    p1 = UPPER_DIR / "b69_2026_h1_jan_mar.parquet"
    p2 = UPPER_DIR / "b69_2026_h2_apr_jun.parquet"

    if p1.exists() and p2.exists():
        log(f"캐시된 B69 반기 파일 적재: {p1.name}, {p2.name}")
        b1 = pd.read_parquet(p1)
        b2 = pd.read_parquet(p2)
        if "rfid_id" in b1.columns:
            b1 = b1.set_index("rfid_id")
        if "rfid_id" in b2.columns:
            b2 = b2.set_index("rfid_id")
        return b1, b2

    log(f"시간별 집계 적재: {SRC_PARQUET}")
    sys.path.insert(0, str(DAY / "code"))
    import importlib
    b01 = importlib.import_module("01_build_behavior_features_20261104")

    table = pq.read_table(SRC_PARQUET, columns=b01.NEEDED)
    df = table.to_pandas()
    df2026 = df[df["year"] == 2026].copy()
    del df, table
    gc.collect()

    log("2026 전반기 (1~3월) B69 추출 시작")
    df_h1 = df2026[df2026["date"] < "2026-04-01"].copy()
    b1 = b01.build(df_h1)
    b1.to_parquet(p1)
    log(f"전반기 B69 저장: {p1} ({b1.shape})")

    log("2026 후반기 (4~6월) B69 추출 시작")
    df_h2 = df2026[df2026["date"] >= "2026-04-01"].copy()
    b2 = b01.build(df_h2)
    b2.to_parquet(p2)
    log(f"후반기 B69 저장: {p2} ({b2.shape})")

    del df2026, df_h1, df_h2
    gc.collect()
    return b1, b2


def main():
    log("=== S7: 같은 배 두 기간 예측 안정성 바닥 진단 시작 ===")
    t0 = time.time()

    b1, b2 = get_or_build_half_b69()
    b1.index = b1.index.astype(str)
    b2.index = b2.index.astype(str)

    # 양쪽 반 모두 7일 이상 관측 선박
    common_ids = b1.index.intersection(b2.index)
    b1_c = b1.loc[common_ids]
    b2_c = b2.loc[common_ids]
    valid_mask = (b1_c["obs_days"] >= 7) & (b2_c["obs_days"] >= 7)
    valid_ids = common_ids[valid_mask]
    log(f"공통 선박 {len(common_ids)}척 중 양쪽 반 모두 obs_days >= 7인 선박: {len(valid_ids)}척")

    # 전체 기간 B69 (FIT 학습용)
    b_full = pd.read_csv(DAY / "work" / "behavior_B50_train2026.csv")
    b_full["rfid_id"] = b_full["rfid_id"].astype(str)
    b_full = b_full.set_index("rfid_id").replace([np.inf, -np.inf], np.nan)
    feat_cols = [c for c in b_full.columns if c != "obs_days"]

    # 코사인 유사도 계산
    v1 = b1.loc[valid_ids, feat_cols].to_numpy(dtype=np.float64)
    v2 = b2.loc[valid_ids, feat_cols].to_numpy(dtype=np.float64)

    # 중앙값 대체
    v1 = np.where(np.isnan(v1), 0.0, v1)
    v2 = np.where(np.isnan(v2), 0.0, v2)
    norm1 = np.linalg.norm(v1, axis=1, keepdims=True)
    norm2 = np.linalg.norm(v2, axis=1, keepdims=True)
    norm1[norm1 < 1e-8] = 1.0
    norm2[norm2 < 1e-8] = 1.0
    cos_sim = np.sum((v1 / norm1) * (v2 / norm2), axis=1)

    roles = m.load_dev_roles()
    labels = m.load_labels()

    preds_h1_list = []
    preds_h2_list = []
    y_true_list = []
    outer_rids_list = []
    outer_days_list = []

    for fold in m.FOLDS:
        t_f = time.time()
        fr = main005.fold_rows(fold, roles, labels)
        is_fit = (fr["role"] == "FIT")
        is_inner = (fr["role"] == "INNER")
        is_outer = (fr["role"] == "OUTER")

        rids = [str(r) for r in fr["rids"]]
        y = fr["y"]

        # FIT은 전체 B69로 학습 (06의 N1 설정)
        B_fit = b_full.reindex([rids[i] for i in np.flatnonzero(is_fit)])[feat_cols].to_numpy(dtype=np.float64)
        y_fit = y[is_fit]
        B_inner = b_full.reindex([rids[i] for i in np.flatnonzero(is_inner)])[feat_cols].to_numpy(dtype=np.float64)
        y_inner = y[is_inner]

        # OUTER 중 valid_ids에 포함된 선박만 필터
        outer_indices = np.flatnonzero(is_outer)
        sel_outer_idx = [i for i in outer_indices if rids[i] in valid_ids]
        sel_rids = [rids[i] for i in sel_outer_idx]
        sel_y = y[sel_outer_idx]
        sel_days = b_full.loc[sel_rids, "obs_days"].to_numpy()

        X_h1 = b1.loc[sel_rids, feat_cols].to_numpy(dtype=np.float64)
        X_h2 = b2.loc[sel_rids, feat_cols].to_numpy(dtype=np.float64)

        sw = m.sqrt_weights(y_fit)

        p1_seeds, p2_seeds = [], []
        for seed in SEEDS:
            mdl = fit_lgbm(B_fit, y_fit, B_inner, y_inner, seed, sample_weight=sw[y_fit])
            p1_seeds.append(mdl.predict_proba(X_h1))
            p2_seeds.append(mdl.predict_proba(X_h2))
            del mdl
            gc.collect()

        pred_h1 = np.mean(p1_seeds, axis=0).argmax(1)
        pred_h2 = np.mean(p2_seeds, axis=0).argmax(1)

        preds_h1_list.append(pred_h1)
        preds_h2_list.append(pred_h2)
        y_true_list.append(sel_y)
        outer_rids_list.extend(sel_rids)
        outer_days_list.append(sel_days)

        log(f"Fold {fold} 완료: 대상 OUTER {len(sel_rids)}척 ({time.time()-t_f:.1f}초)")

    p1_all = np.concatenate(preds_h1_list)
    p2_all = np.concatenate(preds_h2_list)
    y_all = np.concatenate(y_true_list)
    days_all = np.concatenate(outer_days_list)
    n_eval = len(y_all)

    # 1. 두 예측 일치율
    agree_mask = (p1_all == p2_all)
    agree_overall = float(agree_mask.mean())

    agree_by_class = {}
    for c, name in enumerate(CLASS_NAMES):
        c_mask = (y_all == c)
        agree_by_class[name] = round(float(agree_mask[c_mask].mean()), 5) if c_mask.any() else 0.0

    # 2. 4-way 정확도 분해
    both_correct = float(((p1_all == y_all) & (p2_all == y_all)).mean())
    only_h1_correct = float(((p1_all == y_all) & (p2_all != y_all)).mean())
    only_h2_correct = float(((p1_all != y_all) & (p2_all == y_all)).mean())
    both_wrong = float(((p1_all != y_all) & (p2_all != y_all)).mean())

    acc_h1 = float((p1_all == y_all).mean())
    acc_h2 = float((p2_all == y_all).mean())

    log(f"전체 평가 선박 {n_eval}척:")
    log(f"  전반기-후반기 예측 일치율: {agree_overall*100:.2f}%")
    log(f"  전반기 정확도: {acc_h1:.4f}, 후반기 정확도: {acc_h2:.4f}")
    log(f"  둘 다 맞은 비율 (데이터 안정성 현실적 상한): {both_correct*100:.2f}%")
    log(f"  전반기만 맞음: {only_h1_correct*100:.2f}%, 후반기만 맞음: {only_h2_correct*100:.2f}%, 둘 다 틀림: {both_wrong*100:.2f}%")

    out_json = {
        "experiment": "S7_temporal_split_stability",
        "description": "동일 선박 1~3월(전반기) vs 4~6월(후반기) B69 예측 일치율 및 안정성 바닥 진단",
        "sample_counts": {
            "valid_ships_obs_days_ge_7_both_halves": int(len(valid_ids)),
            "evaluated_outer_ships": int(n_eval)
        },
        "cosine_similarity_distribution": {
            "mean": round(float(cos_sim.mean()), 4),
            "median": round(float(np.median(cos_sim)), 4),
            "p10": round(float(np.percentile(cos_sim, 10)), 4),
            "p25": round(float(np.percentile(cos_sim, 25)), 4),
            "p75": round(float(np.percentile(cos_sim, 75)), 4),
            "p90": round(float(np.percentile(cos_sim, 90)), 4)
        },
        "prediction_agreement": {
            "overall_agreement_ratio": round(agree_overall, 5),
            "agreement_by_class": agree_by_class
        },
        "accuracy_breakdown": {
            "h1_accuracy": round(acc_h1, 5),
            "h2_accuracy": round(acc_h2, 5),
            "both_correct_ratio": round(both_correct, 5),
            "only_h1_correct_ratio": round(only_h1_correct, 5),
            "only_h2_correct_ratio": round(only_h2_correct, 5),
            "both_wrong_ratio": round(both_wrong, 5),
            "interpretation": "'둘 다 맞은 비율'은 기간이 바뀌어도 모델이 동일하게 정답을 유지할 수 있는 데이터 자체의 안정적 상한을 의미함."
        },
        "limitation_note": "B69 행동 특징만으로 측정한 수치이므로 F156을 포함한 본 모델 전체의 상한이 아니며 데이터의 계절적 흔들림 방향성을 진단하기 위한 참고치임."
    }

    out_path = UPPER_DIR / "S7.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path} (총 소요 시간: {time.time()-t0:.1f}초)")


if __name__ == "__main__":
    main()
