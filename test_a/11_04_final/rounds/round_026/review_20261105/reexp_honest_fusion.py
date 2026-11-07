# -*- coding: utf-8 -*-
"""Round 026 재실험: 결점 수정판 Grand Fusion.

수정 사항
  (1) alpha3 탐색 격자를 1.20~1.65 -> 1.00~3.00 으로 확장 (원본은 INNER 보호게이트가
      격자 밖에 있어 22개 후보 전부 게이트 미달 상태로 평가되었다)
  (2) INNER 확률이 존재하지 않는 Track2 혼합(w_t2>0)은 후보에서 제외
      (원본은 INNER에서 t2=0 행렬, OUTER에서 실제 t2 확률을 써서 검증 모델과
       적용 모델이 달랐다)
  (3) 혼합비·alpha·운영점(pooled/local) 선택을 전부 INNER OOF에서만 수행하고
      OUTER는 선택된 단 1개 후보에 한해 1회 평가
"""
import os, sys, json
from pathlib import Path
import numpy as np
from scipy.stats import binomtest

os.environ["OMP_NUM_THREADS"] = "1"
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

T3 = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble")
sys.path.insert(0, str(T3))
os.chdir(T3)
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

OUT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\review_20261105")

inner_records, outer_records = load_canonical_data()
inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)
outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

t1 = np.load(Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz"))
t1_map = {v: t1["outer_probs"][i] for i, v in enumerate(t1["vessel_ids"].astype(str))}
p_t1_out = np.array([t1_map[r[2]] for r in outer_records], dtype=np.float64)
exp01 = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
t1_in_by_fid = {}
for f in FOLDS:
    with np.load(exp01 / f"fold_{f}_features.npz") as zf:
        f_ids = zf["rfid_ids"].astype(str)[zf["roles"].astype(str) == "INNER"]
    pf = t1[f"inner_probs_fold{f}"]
    for j, vid in enumerate(f_ids):
        t1_in_by_fid[(f, vid)] = pf[j]
p_t1_in = np.array([t1_in_by_fid[(r[0], r[2])] for r in inner_records], dtype=np.float64)

P_in = {"lgb": inner_probs["LightGBM_5seed_sqrt_macro"], "t42": inner_probs["TabICL_seed42"],
        "t26": inner_probs["TabICL_seed2026"], "cat": inner_probs["CatBoost"], "t1": p_t1_in}
P_out = {"lgb": outer_probs["LightGBM_5seed_sqrt_macro"], "t42": outer_probs["TabICL_seed42"],
         "t26": outer_probs["TabICL_seed2026"], "cat": outer_probs["CatBoost"], "t1": p_t1_out}

MIX = {
    "Trio_Base":        (0.45, 0.45, 0.00, 0.10, 0.00),
    "Trio_BothTab":     (0.40, 0.25, 0.25, 0.10, 0.00),
    "T1_w05":           (0.40, 0.45, 0.00, 0.10, 0.05),
    "T1_w10":           (0.35, 0.45, 0.00, 0.10, 0.10),
    "T1_w15":           (0.30, 0.45, 0.00, 0.10, 0.15),
    "T1_w20":           (0.30, 0.40, 0.00, 0.10, 0.20),
    "BothTab_T1_w05":   (0.35, 0.25, 0.25, 0.10, 0.05),
    "BothTab_T1_w10":   (0.35, 0.225, 0.225, 0.10, 0.10),
    "BothTab_T1_w15":   (0.30, 0.225, 0.225, 0.10, 0.15),
}
MIN_TP0_IN, MIN_TP3_IN = 958, 38
A0 = [1.00, 1.02, 1.04, 1.06]
A2 = [0.95, 1.00, 1.05]
A3 = np.linspace(1.00, 3.00, 41)


def blend(P, w):
    wl, w42, w26, wc, w1 = w
    return wl * P["lgb"] + w42 * P["t42"] + w26 * P["t26"] + wc * P["cat"] + w1 * P["t1"]


def fit_alpha(y, p, min_tp0, min_tp3):
    best, best_score = None, -1
    for a0 in A0:
        for a2 in A2:
            for a3 in A3:
                a = np.array([a0, 1.0, a2, a3])
                cm = np.bincount(y * 4 + (p * a).argmax(1), minlength=16).reshape(4, 4)
                if cm[0, 0] >= min_tp0 and cm[3, 3] >= min_tp3:
                    s = int(np.trace(cm))
                    if s > best_score:
                        best_score, best = s, a
    return best


print("=" * 104)
print("[재실험] INNER-전용 선택 (alpha3 격자 1.00~3.00, Track2 혼합 제외)")
print("=" * 104)
results = []
for name, w in MIX.items():
    p_in = blend(P_in, w)
    for mode in ("pooled", "local"):
        oof = np.zeros(len(inner_y), dtype=np.int64)
        alphas, feasible = [], True
        for vf in FOLDS:
            tr, va = inner_folds != vf, inner_folds == vf
            scale = tr.sum() / len(inner_y)
            a = fit_alpha(inner_y[tr], p_in[tr], int(round(MIN_TP0_IN * scale)), int(round(MIN_TP3_IN * scale)))
            if a is None:
                feasible = False
                a = np.array([1.033, 1.0, 1.0, 1.8])
            alphas.append(a)
        if mode == "pooled":
            a_use = np.mean(alphas, axis=0)
            oof = (p_in * a_use).argmax(1)
            # pooled 운영점도 OOF로 평가해야 하므로 fold별로 "타 fold 평균 alpha" 사용
            oof = np.zeros(len(inner_y), dtype=np.int64)
            for vf in FOLDS:
                va = inner_folds == vf
                a_oof = np.mean([alphas[f] for f in FOLDS if f != vf], axis=0)
                oof[va] = (p_in[va] * a_oof).argmax(1)
        else:
            for vf in FOLDS:
                va = inner_folds == vf
                oof[va] = (p_in[va] * alphas[vf]).argmax(1)
        m = compute_metrics(inner_y, oof)
        gate = m["tp"][0] >= MIN_TP0_IN and m["tp"][3] >= MIN_TP3_IN
        results.append({"mix": name, "mode": mode, "weights": w, "alphas": [a.tolist() for a in alphas],
                        "inner": m["correct"], "inner_micro": m["micro_f1"], "inner_tp": m["tp"],
                        "inner_gate": bool(gate), "fold_feasible": feasible})
        print(f"  {name:<16} {mode:<7} INNER={m['correct']:4d}/2361 ({m['micro_f1']:.6f}) "
              f"TP={m['tp']} gate={gate}")

passed = [r for r in results if r["inner_gate"]]
pool = passed if passed else results
win = max(pool, key=lambda r: r["inner"])
print(f"\nINNER 게이트 통과 후보: {len(passed)}/{len(results)}")
print(f"선택된 단일 후보: {win['mix']} / {win['mode']}  INNER={win['inner']} TP={win['inner_tp']}")

# ---- OUTER 단 1회 평가 ----
p_out = blend(P_out, tuple(win["weights"]))
alphas = [np.array(a) for a in win["alphas"]]
if win["mode"] == "pooled":
    pred = (p_out * np.mean(alphas, axis=0)).argmax(1)
else:
    pred = np.zeros(len(outer_y), dtype=np.int64)
    for f in FOLDS:
        m = outer_folds == f
        pred[m] = (p_out[m] * alphas[f]).argmax(1)
mo = compute_metrics(outer_y, pred)
base5 = P_out["lgb"].argmax(1)
b, c = (base5 == outer_y), (pred == outer_y)
nb, ni = int(np.count_nonzero(~b & c)), int(np.count_nonzero(b & ~c))
pv = binomtest(nb, nb + ni, 0.5).pvalue
print("\n" + "=" * 104)
print("[재실험 결과] OUTER 5,897 단 1회 평가")
print("=" * 104)
print(f"  정답 {mo['correct']}/5897  micro-F1 {mo['micro_f1']:.6f}  macro-F1 {mo['macro_f1']:.6f}")
print(f"  TP {mo['tp']}  (OUTER 보호 TP0>=2389: {mo['tp'][0]>=2389}, TP3>=92: {mo['tp'][3]>=92})")
print(f"  vs LGB 5-seed(3497): {mo['correct']-3497:+d}척  (+{nb}/-{ni}, McNemar p={pv:.4g})")
print(f"  공표값 3552 (0.602340) 대비: {mo['correct']-3552:+d}척")
for f in FOLDS:
    m = outer_folds == f
    print(f"    fold {f}: base={b[m].sum()} cand={c[m].sum()} delta={c[m].sum()-b[m].sum():+d}")

json.dump({"inner_search": results, "selected": win,
           "outer_single_eval": {"correct": mo["correct"], "micro_f1": mo["micro_f1"], "macro_f1": mo["macro_f1"],
                                 "tp": mo["tp"], "cm": mo["confusion_matrix"],
                                 "vs_lgb5_net": mo["correct"] - 3497, "newly_correct": nb,
                                 "newly_incorrect": ni, "mcnemar_p": float(pv),
                                 "protection_tp0_pass": bool(mo["tp"][0] >= 2389),
                                 "protection_tp3_pass": bool(mo["tp"][3] >= 92)}},
          open(OUT / "reexp_honest_fusion_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nsaved ->", OUT / "reexp_honest_fusion_results.json")
