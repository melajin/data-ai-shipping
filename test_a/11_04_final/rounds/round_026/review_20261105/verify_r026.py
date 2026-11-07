# -*- coding: utf-8 -*-
"""Round 026 독립 검증: 0.60 돌파의 선택 편향 정량화."""
import os, sys, json
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

T3 = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble")
sys.path.insert(0, str(T3))
os.chdir(T3)
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

OUT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\review_20261105")

inner_records, outer_records = load_canonical_data()
inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
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


MIN_TP0_IN, MIN_TP3_IN = 958, 38

cands = {}
for name, r in mixes.items():
    w = tuple(r["weights"])
    p_out = blend(P_out, w)
    mean_a = np.array(r["mean_alpha"])
    fold_a = [np.array(a) for a in r["fold_alphas"]]
    pred_pool = (p_out * mean_a).argmax(1)
    pred_loc = np.zeros(len(outer_y), dtype=np.int64)
    for f in FOLDS:
        m = outer_folds == f
        pred_loc[m] = (p_out[m] * fold_a[f]).argmax(1)
    for mode, pred in (("pooled", pred_pool), ("local", pred_loc)):
        m = compute_metrics(outer_y, pred)
        cands[f"{name}|{mode}"] = {
            "pred": pred, "outer_correct": m["correct"], "outer_micro": m["micro_f1"],
            "outer_tp": m["tp"], "outer_pass": bool(m["tp"][0] >= 2389 and m["tp"][3] >= 92),
            "inner_correct": r["inner_metrics"]["correct"], "inner_tp": r["inner_metrics"]["tp"],
            "inner_pass": bool(r["inner_metrics"]["tp"][0] >= MIN_TP0_IN and r["inner_metrics"]["tp"][3] >= MIN_TP3_IN),
        }

print("=" * 118)
print("[1] 22개 Grand-Fusion 후보 재현 (INNER 선택 근거 vs OUTER 결과)")
print("=" * 118)
print(f"{'candidate':<36} {'INNER':>6} {'INNERpass':>10} {'OUTER':>6} {'micro':>9} {'TP3':>5} {'OUTERpass':>10}")
for k, v in sorted(cands.items(), key=lambda x: -x[1]["inner_correct"]):
    print(f"{k:<36} {v['inner_correct']:>6} {str(v['inner_pass']):>10} {v['outer_correct']:>6} "
          f"{v['outer_micro']:>9.6f} {v['outer_tp'][3]:>5} {str(v['outer_pass']):>10}")

n_inner_pass = sum(v["inner_pass"] for v in cands.values())
print(f"\nINNER 보호게이트(TP0>=958, TP3>=38) 통과 후보 수: {n_inner_pass} / {len(cands)}")

ic = np.array([v["inner_correct"] for v in cands.values()], float)
oc = np.array([v["outer_correct"] for v in cands.values()], float)


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    return float((ra * rb).sum() / np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))


print(f"\n[2] INNER correct vs OUTER correct  Pearson r = {np.corrcoef(ic, oc)[0,1]:+.3f}, "
      f"Spearman rho = {spearman(ic, oc):+.3f}  (n={len(ic)})")

pub_key = "Mix_Grand_BothTab_T1_w10|pooled"
honest_inner = max(cands.items(), key=lambda x: x[1]["inner_correct"])
outer_best = max(cands.items(), key=lambda x: x[1]["outer_correct"])
outer_best_pass = max([x for x in cands.items() if x[1]["outer_pass"]], key=lambda x: x[1]["outer_correct"])
print("\n[3] 선택 규칙별 귀결")
for label, (k, v) in [("논문 채택(공표)", (pub_key, cands[pub_key])),
                      ("INNER 최고(정직)", honest_inner),
                      ("OUTER 최고(완전 누수)", outer_best),
                      ("OUTER 최고+OUTER게이트", outer_best_pass)]:
    print(f"  {label:<24} {k:<36} INNER={v['inner_correct']:4d}  OUTER={v['outer_correct']:4d} ({v['outer_micro']:.6f})")

from scipy.stats import binomtest
base5 = P_out["lgb"].argmax(1)
base42 = outer_probs["LightGBM_seed42"].argmax(1)


def mcnemar(base, cand, label):
    b = (base == outer_y)
    c = (cand == outer_y)
    nb = int(np.count_nonzero(~b & c))
    ni = int(np.count_nonzero(b & ~c))
    p = binomtest(nb, nb + ni, 0.5).pvalue
    print(f"  {label:<34} +{nb} / -{ni} = net {nb-ni:+d}  McNemar exact p = {p:.4g}")
    return {"newly_correct": nb, "newly_incorrect": ni, "net": nb - ni, "p_exact": float(p)}


print("\n[4] McNemar 정확검정 (보고서의 'p<0.001' 주장 검증)")
mc5 = mcnemar(base5, cands[pub_key]["pred"], "GrandFusion vs LGB 5-seed")
mc42 = mcnemar(base42, cands[pub_key]["pred"], "GrandFusion vs LGB seed42")
mc_honest = mcnemar(base5, honest_inner[1]["pred"], "INNER-pick vs LGB 5-seed")

print("\n[5] 이득의 fold별 분해 (일관성 점검)")
b = (base5 == outer_y)
c = (cands[pub_key]["pred"] == outer_y)
fold_rows = []
for f in FOLDS:
    m = outer_folds == f
    row = {"fold": int(f), "n": int(m.sum()), "base": int(b[m].sum()), "cand": int(c[m].sum()),
           "delta": int(c[m].sum() - b[m].sum())}
    fold_rows.append(row)
    print(f"  fold {f}: n={row['n']}  base={row['base']}  cand={row['cand']}  delta={row['delta']:+d}")

print("\n[6] OUTER 반분 시뮬레이션: A에서 고르고 B에서 평가 (선택 편향 크기)")
rng = np.random.default_rng(20261105)
keys = list(cands.keys())
corr = np.stack([(cands[k]["pred"] == outer_y) for k in keys])
tp0 = np.stack([((outer_y == 0) & (cands[k]["pred"] == 0)) for k in keys])
tp3 = np.stack([((outer_y == 3) & (cands[k]["pred"] == 3)) for k in keys])
n = len(outer_y)
reps = 400
sel_B, optimism, oracle_B, inner_pick_B = [], [], [], []
hk = keys.index(honest_inner[0])
for _ in range(reps):
    idx = rng.permutation(n)
    A, B = idx[:n // 2], idx[n // 2:]
    gate = (tp0[:, A].sum(1) >= 2389 * len(A) / n) & (tp3[:, A].sum(1) >= 92 * len(A) / n)
    scoreA = corr[:, A].sum(1).astype(float)
    scoreA[~gate] = -1
    pick = int(scoreA.argmax())
    sel_B.append(corr[pick, B].mean())
    inner_pick_B.append(corr[hk, B].mean())
    oracle_B.append(corr[:, B].mean(1).max())
    optimism.append(corr[pick, A].mean() - corr[pick, B].mean())
print(f"  A에서 선택한 후보의 B 성능      : {np.mean(sel_B):.6f} (sd {np.std(sel_B):.6f})")
print(f"  INNER로 고른 후보의 B 성능      : {np.mean(inner_pick_B):.6f}")
print(f"  B에서의 사후 최적(oracle)       : {np.mean(oracle_B):.6f}")
print(f"  선택면 A - 검증면 B 낙폭(평균)  : {np.mean(optimism):+.6f}  ({np.mean(optimism)*n:+.1f}척 상당)")

print("\n[7] Track1(10%) 기여: INNER과 OUTER의 방향 일치 여부")
t1_rows = []
for nm in ["Mix_Trio_BothTab", "Mix_Grand_BothTab_T1_w05", "Mix_Grand_BothTab_T1_w10", "Mix_Grand_BothTab_T1_w15"]:
    v = cands[f"{nm}|pooled"]
    t1_rows.append({"mix": nm, "inner": v["inner_correct"], "outer": v["outer_correct"]})
    print(f"  {nm:<28} INNER={v['inner_correct']:4d}  OUTER={v['outer_correct']:4d}")

print("\n[8] ROUND_REPORT 4.2 혼동행렬 vs 실제 재현값")
cm_act = np.bincount(outer_y * 4 + cands[pub_key]["pred"], minlength=16).reshape(4, 4)
cm_rep = np.array([[2541, 329, 40, 10], [1114, 814, 60, 28], [563, 148, 105, 19], [18, 12, 4, 92]])
print("  실제:\n", cm_act)
print("  보고서:\n", cm_rep)
print("  차이(보고서-실제):\n", cm_rep - cm_act)

json.dump({
    "candidates": {k: {kk: vv for kk, vv in v.items() if kk != "pred"} for k, v in cands.items()},
    "inner_gate_pass_count": int(n_inner_pass),
    "pearson_inner_outer": float(np.corrcoef(ic, oc)[0, 1]),
    "spearman_inner_outer": spearman(ic, oc),
    "published": {"key": pub_key, **{k: v for k, v in cands[pub_key].items() if k != "pred"}},
    "honest_inner_pick": {"key": honest_inner[0], **{k: v for k, v in honest_inner[1].items() if k != "pred"}},
    "outer_best": {"key": outer_best[0], "outer_correct": outer_best[1]["outer_correct"]},
    "mcnemar": {"vs_lgb5": mc5, "vs_seed42": mc42, "honest_vs_lgb5": mc_honest},
    "fold_decomposition": fold_rows,
    "track1_ablation": t1_rows,
    "split_half": {"selected_on_A_eval_B": float(np.mean(sel_B)), "inner_pick_eval_B": float(np.mean(inner_pick_B)),
                   "oracle_B": float(np.mean(oracle_B)), "optimism_A_minus_B": float(np.mean(optimism)), "reps": reps},
    "report_cm_mismatch": (cm_rep - cm_act).tolist(),
}, open(OUT / "verify_r026_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nsaved ->", OUT / "verify_r026_results.json")
