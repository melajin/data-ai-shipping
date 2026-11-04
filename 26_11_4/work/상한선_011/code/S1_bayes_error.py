#!/usr/bin/env python3
"""S1 — 특징공간 중복도에서 오는 원리적 바닥 (Bayes 오차 추정)

지시 011:
  - 특징: F156 + T5 (166차원)
  - 각 fold의 FIT 중앙값 대체, FIT 기준 평균·표준편차 표준화
  - 두 공간:
    (a) 원본 166차원
    (b) FIT에서 적합한 PCA 분산 95% 축소 공간
  - k in {1, 3, 5, 10, 20} 유클리드 최근접 이웃 (FIT 선박 중)
  - e_1NN (전체 / 업종별), e_kNN 다수결 오차
  - 이웃 k개가 전원 다른 업종인 비율, 이웃 엔트로피 분포
  - Cover-Hart 부등식 (M=4): e* <= e_1NN <= e* * (2 - 4/3*e*) 수치해로 e* 하한 추정
  - 부트스트랩 5,000회 신뢰구간
  - 가장 유리한 혼동 구조 가정으로 macro-F1 상한 환산

출력: work/상한선_011/S1.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.stats import entropy
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

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

BOOT_SEED = 20261104
N_BOOT = 5000
CLASS_NAMES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
KS = [1, 3, 5, 10, 20]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def solve_cover_hart_bayes(e1: float, M: float = 4.0) -> float:
    """Cover-Hart 부등식의 우변 e* * (2 - M/(M-1)*e*) = e1 을 풀어 e*의 하한을 구함."""
    if e1 <= 0.0:
        return 0.0
    max_e = (M - 1.0) / M  # 0.75
    if e1 >= max_e:
        return max_e
    def f(e):
        return e * (2.0 - (M / (M - 1.0)) * e) - e1
    try:
        return float(brentq(f, 0.0, max_e))
    except Exception:
        # 닫힌 형식 해
        val = max(0.0, 1.0 - (4.0 / 3.0) * e1)
        return float((3.0 / 4.0) * (1.0 - np.sqrt(val)))


def convert_bayes_to_macro_f1(e_star_per_class: list[float]) -> dict:
    """업종별 Bayes 오차 e*_c를 불가피한 오차로 보고, 가장 유리한 혼동 구조(FP=0)를 가정해 F1 상한 도출."""
    class_f1_upper = []
    for e_c in e_star_per_class:
        # TP = (1 - e_c)*N, FN = e_c*N, FP = 0 (가장 유리한 가정)
        # Precision = 1.0, Recall = 1 - e_c
        # F1 = 2 * (1 - e_c) / (2 - e_c)
        rec = 1.0 - e_c
        f1 = (2.0 * rec) / (1.0 + rec) if (1.0 + rec) > 0 else 0.0
        class_f1_upper.append(round(float(f1), 5))
    macro_upper = round(float(np.mean(class_f1_upper)), 5)
    return {
        "macro_f1_upper_bound": macro_upper,
        "class_f1_upper_bounds": class_f1_upper,
        "assumption": "가장 유리한 혼동 구조(FP=0, Precision=1.0)를 가정한 느슨한 상한 (진짜 상한보다 높게 도출됨)"
    }


def analyze_space(space_name: str, folds_data: list[dict], rng: np.random.Generator) -> dict:
    log(f"--- 분석 공간: {space_name} ---")
    all_outer_y = []
    all_nn_labels = {k: [] for k in KS}

    for fd in folds_data:
        X_fit = fd[f"{space_name}_fit"]
        y_fit = fd["y_fit"]
        X_outer = fd[f"{space_name}_outer"]
        y_outer = fd["y_outer"]

        all_outer_y.append(y_outer)

        nn = NearestNeighbors(n_neighbors=max(KS), metric="euclidean", n_jobs=3)
        nn.fit(X_fit)
        _, indices = nn.kneighbors(X_outer)

        for k in KS:
            # outer_n x k neighbor labels
            k_labels = y_fit[indices[:, :k]]
            all_nn_labels[k].append(k_labels)

    outer_y = np.concatenate(all_outer_y)
    n_total = len(outer_y)

    results = {}
    for k in KS:
        k_labels = np.concatenate(all_nn_labels[k], axis=0)

        # 1-NN 오차 (k=1인 경우 또는 첫번째 이웃)
        if k == 1:
            first_neighbor = k_labels[:, 0]
            e_1nn_mask = (first_neighbor != outer_y)
            e_1nn_overall = float(e_1nn_mask.mean())

            e_1nn_per_class = []
            for c in range(4):
                c_mask = (outer_y == c)
                e_c = float(e_1nn_mask[c_mask].mean()) if c_mask.any() else 0.0
                e_1nn_per_class.append(round(e_c, 5))

            # Bayes 오차 Cover-Hart 하한
            bayes_lower = solve_cover_hart_bayes(e_1nn_overall)
            bayes_lower_per_class = [round(solve_cover_hart_bayes(e_c), 5) for e_c in e_1nn_per_class]

            # 5,000회 부트스트랩 신뢰구간
            b_e1 = np.empty(N_BOOT, dtype=np.float64)
            b_bayes = np.empty(N_BOOT, dtype=np.float64)
            for b in range(N_BOOT):
                idx = rng.integers(0, n_total, size=n_total)
                e1_sample = float(e_1nn_mask[idx].mean())
                b_e1[b] = e1_sample
                b_bayes[b] = solve_cover_hart_bayes(e1_sample)

            ci_e1 = [round(float(x), 5) for x in np.percentile(b_e1, [2.5, 97.5])]
            ci_bayes = [round(float(x), 5) for x in np.percentile(b_bayes, [2.5, 97.5])]

            macro_conversion = convert_bayes_to_macro_f1(bayes_lower_per_class)

            results["k_1"] = {
                "e_1nn_overall": round(e_1nn_overall, 5),
                "e_1nn_ci_95": ci_e1,
                "e_1nn_per_class": e_1nn_per_class,
                "bayes_error_lower_bound": round(bayes_lower, 5),
                "bayes_error_ci_95": ci_bayes,
                "bayes_error_lower_per_class": bayes_lower_per_class,
                "macro_f1_conversion": macro_conversion
            }
            log(f"  k=1 e_1NN: {e_1nn_overall:.4f} (95% CI {ci_e1}) -> Bayes 오차 하한: {bayes_lower:.4f} (CI {ci_bayes})")
            log(f"  Bayes 환산 macro-F1 상한: {macro_conversion['macro_f1_upper_bound']}")

        # k-NN 다수결 오차
        # 각 행마다 빈도 최빈값
        pred_maj = np.empty(n_total, dtype=int)
        all_diff_count = 0
        entropies = np.empty(n_total, dtype=np.float64)

        for i in range(n_total):
            row_labels = k_labels[i]
            bcounts = np.bincount(row_labels, minlength=4)
            pred_maj[i] = int(bcounts.argmax())
            # 이웃 중 정답 업종이 하나도 없는 경우
            if bcounts[outer_y[i]] == 0:
                all_diff_count += 1
            # 라벨 엔트로피
            p = bcounts / float(k)
            entropies[i] = entropy(p, base=2)

        e_knn = float((pred_maj != outer_y).mean())
        all_diff_ratio = float(all_diff_count / n_total)
        ent_mean = float(entropies.mean())
        ent_quantiles = [round(float(q), 4) for q in np.percentile(entropies, [25, 50, 75, 90])]

        results[f"k_{k}"] = {
            "e_knn_majority_error": round(e_knn, 5),
            "all_neighbors_different_class_ratio": round(all_diff_ratio, 5),
            "all_neighbors_different_class_count": int(all_diff_count),
            "label_entropy_mean": round(ent_mean, 4),
            "label_entropy_quantiles_25_50_75_90": ent_quantiles
        }
        if k > 1:
            log(f"  k={k:2d} 다수결 오차: {e_knn:.4f}, 전원 불일치(구조적불가): {all_diff_ratio*100:.2f}% ({all_diff_count}척), 엔트로피 평균: {ent_mean:.3f}")

    return results


def main():
    log("=== S1: 특징공간 중복도 Bayes 오차 하한 추정 시작 ===")
    t0 = time.time()
    roles = m.load_dev_roles()
    labels = m.load_labels()
    fishing_mask = m._fishing_mask_global()

    folds_data = []

    for fold in m.FOLDS:
        t_f = time.time()
        fr = main005.fold_rows(fold, roles, labels)
        is_fit, is_outer = (fr["role"] == "FIT"), (fr["role"] == "OUTER")
        fit_ids = [fr["rids"][i] for i in np.flatnonzero(is_fit)]
        fit_label_by_rid = {fr["rids"][i]: int(fr["y"][i]) for i in np.flatnonzero(is_fit)}
        fit_rid_label = [(r, fit_label_by_rid[r]) for r in fit_ids]

        main_dicts = m._build_t5_dicts(fit_rid_label, fishing_mask, month_filter=None)
        month_dicts = {mo: m._build_t5_dicts(fit_rid_label, fishing_mask, month_filter=mo)
                       for mo in range(1, 7)}
        extra = main005.build_extra_features(fr["rids"], "T5", None, None, fishing_mask,
                                             main_dicts, month_dicts, fit_label_by_rid)
        X = np.concatenate([fr["feat"].to_numpy(dtype=np.float64), extra], axis=1)

        # 1. FIT 중앙값 대체 (OUTER 누수 방지)
        fit_med = np.nanmedian(X[is_fit], axis=0)
        fit_med = np.nan_to_num(fit_med, nan=0.0)
        X_imp = np.where(np.isnan(X), fit_med, X)

        # 2. FIT 표준화
        fit_mean = X_imp[is_fit].mean(axis=0)
        fit_std = X_imp[is_fit].std(axis=0)
        fit_std[fit_std < 1e-8] = 1.0
        X_std = (X_imp - fit_mean) / fit_std

        # 3. PCA 95% 분산 공간
        pca = PCA(n_components=0.95, random_state=BOOT_SEED)
        pca.fit(X_std[is_fit])
        X_pca = pca.transform(X_std)

        folds_data.append({
            "fold": fold,
            "raw_fit": X_std[is_fit],
            "raw_outer": X_std[is_outer],
            "pca_fit": X_pca[is_fit],
            "pca_outer": X_pca[is_outer],
            "y_fit": fr["y"][is_fit],
            "y_outer": fr["y"][is_outer],
            "pca_n_components": int(pca.n_components_)
        })
        log(f"Fold {fold} 특징 추출 및 PCA(축소 {pca.n_components_}차원) 완료 ({time.time()-t_f:.1f}초)")

    rng = np.random.default_rng(BOOT_SEED)

    # (a) 원본 166차원 공간 분석
    raw_results = analyze_space("raw", folds_data, rng)

    # (b) PCA 95% 분산 축소 공간 분석
    pca_results = analyze_space("pca", folds_data, rng)

    out_json = {
        "experiment": "S1_bayes_error_bound",
        "description": "F156+T5 특징공간 중복도에서 오는 원리적 바닥 (Bayes 오차 Cover-Hart 하한)",
        "limitation_warning": "유클리드 거리는 '특징이 같다'의 한 정의일 뿐이며 실제 결정트리가 학습하는 비선형 분할면과 다름. 따라서 이 상한은 매우 느슨한(높게 나오는) 이론적 상한선임.",
        "class_order": CLASS_NAMES,
        "n_outer_ships": int(sum(len(fd["y_outer"]) for fd in folds_data)),
        "pca_dimensions_per_fold": [fd["pca_n_components"] for fd in folds_data],
        "spaces": {
            "raw_166d": raw_results,
            "pca_95pct_variance": pca_results
        }
    }

    out_path = UPPER_DIR / "S1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    log(f"Saved: {out_path} (총 소요 시간: {time.time()-t0:.1f}초)")


if __name__ == "__main__":
    main()
