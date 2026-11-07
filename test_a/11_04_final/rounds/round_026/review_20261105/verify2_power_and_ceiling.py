# -*- coding: utf-8 -*-
"""Round 026 검증 2단계: INNER 선택의 검정력, 보호게이트 실현가능성, 정직한 점추정."""
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
t2 = np.load(Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\probabilities_track2.npz"))
t2_map = {v: t2["cand_outer_probs_sqrt"][i] for i, v in enumerate(t2["vessel_ids"].astype(str))}
p_t2_out = np.array([t2_map[r[2]] for r in outer_records], dtype=np.float64)

P_in = {"lgb": inner_probs["LightGBM_5seed_sqrt_macro"], "t42": inner_probs["TabICL_seed42"],
        "t26": inner_probs["TabICL_seed2026"], "cat": inner_probs["CatBoost"], "t1": p_t1_in,
        "t2": np.zeros_like(p_t1_in)}
P_out = {"lgb": outer_probs["LightGBM_5seed_sqrt_macro"], "t42": outer_probs["TabICL_seed42"],
         "t26": outer_probs["TabICL_seed2026"], "cat": outer_probs["CatBoost"], "t1": p_t1_out,
         "t2": p_t2_out}
gf = json.load(open(T3 / "grand_fusion_results.json", encoding="utf-8"))
mixes = {r["mix_name"]: r for r in gf["inner_search"]}


def blend(P, w):
    wl, w42, w26, wc, w1, w2 = w
    return wl * P["lgb"] + w42 * P["t42"] + w26 * P["t26"] + wc * P["cat"] + w1 * P["t1"] + w2 * P["t2"]


print("[A] INNER 집단 구성 및 보호게이트 실현 가능성")
cnt_in = np.bincount(inner_y, minlength=4)
cnt_out = np.bincount(outer_y, minlength=4)
print(f"  INNER 클래스 분포 {cnt_in.tolist()} (N={len(inner_y)})")
print(f"  OUTER 클래스 분포 {cnt_out.tolist()} (N={len(outer_y)})")
print(f"  INNER 게이트 TP3>=38 → class3 재현율 {38/cnt_in[3]:.1%} 필요")
print(f"  OUTER 게이트 TP3>=92 → class3 재현율 {92/cnt_out[3]:.1%} 필요")

# 공표 혼합의 INNER OOF에서 alpha3를 올리며 TP3 상한 탐색
pub_w = tuple(mixes["Mix_Grand_BothTab_T1_w10"]["weights"])
p_in = blend(P_in, pub_w)
p_out = blend(P_out, pub_w)
print("\n[B] 공표 혼합의 alpha3 스윕 — INNER OOF TP3 천장 vs OUTER TP3 (a0=1.033 고정)")
rows = []
for a3 in [1.0, 1.2, 1.425, 1.6, 1.8, 2.0, 2.5, 3.0, 4.0]:
    a = np.array([1.033, 1.0, 1.0, a3])
    mi = compute_metrics(inner_y, (p_in * a).argmax(1))
    mo = compute_metrics(outer_y, (p_out * a).argmax(1))
    rows.append({"a3": a3, "inner_correct": mi["correct"], "inner_tp3": mi["tp"][3], "inner_tp0": mi["tp"][0],
                 "outer_correct": mo["correct"], "outer_tp3": mo["tp"][3], "outer_tp0": mo["tp"][0]})
    print(f"  a3={a3:<5} INNER {mi['correct']:4d}/2361 TP0={mi['tp'][0]:4d} TP3={mi['tp'][3]:3d} | "
          f"OUTER {mo['correct']:4d}/5897 TP0={mo['tp'][0]:4d} TP3={mo['tp'][3]:3d}")

# INNER 선택의 검정력: 후보 간 INNER 차이가 유의한가
print("\n[C] INNER 선택의 검정력 — 후보 간 INNER OOF 차이의 McNemar")
inner_preds = {}
for name, r in mixes.items():
    pi = blend(P_in, tuple(r["weights"]))
    oof = np.zeros(len(inner_y), dtype=np.int64)
    for f in FOLDS:
        m = inner_folds == f
        oof[m] = (pi[m] * np.array(r["fold_alphas"][f])).argmax(1)
    inner_preds[name] = oof
best_name = "Mix_Grand_BothTab_T1_T2"
pub_name = "Mix_Grand_BothTab_T1_w10"
pwr = []
for other in [pub_name, "Mix_Trio_Base", "Mix_Trio_BothTab"]:
    b = inner_preds[other] == inner_y
    c = inner_preds[best_name] == inner_y
    nb = int(np.count_nonzero(~b & c)); ni = int(np.count_nonzero(b & ~c))
    p = binomtest(nb, nb + ni, 0.5).pvalue if nb + ni else 1.0
    pwr.append({"vs": other, "plus": nb, "minus": ni, "net": nb - ni, "p": float(p)})
    print(f"  {best_name} vs {other:<26} +{nb}/-{ni} net {nb-ni:+d}  p={p:.3f}")

# 정직한 점추정: INNER이 식별력이 없다면 기대 OUTER는 후보 평균
print("\n[D] 정직한 점추정 (INNER 식별력 없음 가정 → 후보 평균)")
res = json.load(open(OUT / "verify_r026_results.json", encoding="utf-8"))
oc = np.array([v["outer_correct"] for v in res["candidates"].values()], float)
print(f"  22개 후보 OUTER 정답수: 평균 {oc.mean():.1f}, sd {oc.std(ddof=1):.1f}, 범위 [{oc.min():.0f}, {oc.max():.0f}]")
print(f"  → micro-F1 평균 {oc.mean()/5897:.6f} / 공표값 0.602340 / INNER정직선택 0.599797")

# 보호 임계값의 기원
print("\n[E] 보호 임계값의 기원 점검")
tp0_42 = compute_metrics(outer_y, outer_probs["LightGBM_seed42"].argmax(1))["tp"]
tp0_5 = compute_metrics(outer_y, P_out["lgb"].argmax(1))["tp"]
print(f"  seed42 OUTER TP = {tp0_42}  (TP0=2389 → 보호하한 2389와 동일: {tp0_42[0]==2389})")
print(f"  5-seed OUTER TP = {tp0_5}  (TP3=92  → 보호하한 92와 동일: {tp0_5[3]==92})")

json.dump({"inner_class_counts": cnt_in.tolist(), "outer_class_counts": cnt_out.tolist(),
           "alpha3_sweep": rows, "inner_power": pwr,
           "candidate_outer_mean": float(oc.mean()), "candidate_outer_sd": float(oc.std(ddof=1)),
           "protection_floor_origin": {"seed42_outer_tp": tp0_42, "lgb5_outer_tp": tp0_5}},
          open(OUT / "verify2_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nsaved ->", OUT / "verify2_results.json")
