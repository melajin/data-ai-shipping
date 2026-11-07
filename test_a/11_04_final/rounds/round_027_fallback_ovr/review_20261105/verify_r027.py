# -*- coding: utf-8 -*-
"""Round 027 독립 검증: Specialist-then-Fallback이 통발/자망을 실제로 개선했는가."""
import os, sys, json
from pathlib import Path
import numpy as np
from scipy.stats import binomtest

os.environ["OMP_NUM_THREADS"] = "1"
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

R27 = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_027_fallback_ovr")
OUT = R27 / "review_20261105"
NAMES = ["연안복합", "자망", "통발", "채낚기"]


def metrics(y, pred):
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4).astype(float)
    tp = np.diag(cm); sup = cm.sum(1); prd = cm.sum(0)
    rec = tp / sup
    prec = np.divide(tp, prd, out=np.zeros(4), where=prd > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros(4), where=(prec + rec) > 0)
    return {"correct": int(tp.sum()), "micro": tp.sum() / sup.sum(), "macro": float(f1.mean()),
            "tp": tp.astype(int).tolist(), "f1": f1.tolist(), "rec": rec.tolist(), "prec": prec.tolist(),
            "cm": cm.astype(int).tolist()}


# ---- 후보 수집 ----
zc = np.load(R27 / "worker_c_synthesis" / "worker_c_probabilities.npz")
zb = np.load(R27 / "worker_b_fallback_rules" / "worker_b_fallback_predictions.npz")
za = np.load(R27 / "worker_a_ovr_models" / "worker_a_probabilities.npz")
y_out = zc["y_outer"]; y_in = zc["y_inner"]
assert (zb["outer_y_true"] == y_out).all() and (za["y_outer"] == y_out).all()

cands = {}   # name -> (pred_in or None, pred_out)
for c in ["c1", "c2", "c3", "c4"]:
    cands[f"C{c[1]}"] = (zc[f"pred_{c}_in"], zc[f"pred_{c}_out"])
for k in zb.files:
    if k.startswith("pred_b") and k.endswith("_outer"):
        base = k[:-6]
        ik = base + "_inner"
        cands["B0:" + base[8:]] = (zb[ik] if ik in zb.files else None, zb[k])
    if k.startswith("pred_b") and k.endswith("_outer_pooled"):
        base = k[:-13]
        ik = base + "_inner_oof"
        cands[base[5:] + "|pooled"] = (zb[ik] if ik in zb.files else None, zb[k])
    if k.startswith("pred_b") and k.endswith("_outer_local"):
        base = k[:-12]
        ik = base + "_inner_oof"
        cands[base[5:] + "|local"] = (zb[ik] if ik in zb.files else None, zb[k])
for key, lbl in [("p_hierarchical_std_out", "A:hier326_std_argmax"), ("p_hierarchical_sqrt_out", "A:hier326_sqrt_argmax"),
                 ("p_ovr_4class_norm_out", "A:ovr_norm"), ("p_lgb_knn_std_out", "A:lgb_knn_std"),
                 ("p_lgb_knn_sqrt_out", "A:lgb_knn_sqrt")]:
    ik = key.replace("_out", "_in")
    cands[lbl] = (za[ik].argmax(1) if ik in za.files else None, za[key].argmax(1))
zp = np.load(R27 / "worker_c_synthesis" / "pure_304_probabilities.npz")
for key, lbl in [("p_base_304_out", "C:base304_argmax"), ("p_hier_304_std_out", "C:hier304_std_argmax")]:
    cands[lbl] = (zp[key.replace("_out", "_in")].argmax(1), zp[key])
cands["C:base304_argmax"] = (zp["p_base_304_in"].argmax(1), zp["p_base_304_out"].argmax(1))
cands["C:hier304_std_argmax"] = (zp["p_hier_304_std_in"].argmax(1), zp["p_hier_304_std_out"].argmax(1))

# 비교 기준: round 026 정직 모델
r26 = json.load(open(Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\review_20261105\reexp_honest_fusion_results.json"), encoding="utf-8"))
cm26 = np.array(r26["outer_single_eval"]["cm"], float)
tp26 = np.diag(cm26); sup26 = cm26.sum(1); prd26 = cm26.sum(0)
rec26 = tp26 / sup26; prec26 = tp26 / prd26
f126 = 2 * prec26 * rec26 / (prec26 + rec26)

print("=" * 112)
print("[1] Round 027 전 후보 — 클래스별 F1 (OUTER 5,897)")
print("=" * 112)
print(f"{'후보':<34}{'INNER':>6}{'OUTER':>6}{'micro':>9}{'macro':>8}" + "".join(f"{n+'F1':>11}" for n in NAMES))
rows = []
for name, (pi, po) in cands.items():
    m = metrics(y_out, po)
    inn = int((pi == y_in).sum()) if pi is not None else -1
    rows.append((name, inn, m))
for name, inn, m in sorted(rows, key=lambda r: -r[2]["macro"]):
    f = m["f1"]
    print(f"{name:<34}{inn if inn>0 else 0:>6}{m['correct']:>6}{m['micro']:>9.4f}{m['macro']:>8.4f}"
          + "".join(f"{x:>11.4f}" for x in f))

print()
print(f"{'[기준] R026 정직모델':<34}{1415:>6}{3538:>6}{0.599966:>9.4f}{f126.mean():>8.4f}"
      + "".join(f"{x:>11.4f}" for x in f126))

# ---- C1~C4 전략 선택 검증 ----
print("\n" + "=" * 112)
print("[2] 전략 선택 검증 — INNER 순위 vs OUTER 순위")
print("=" * 112)
res = json.load(open(R27 / "worker_c_synthesis" / "worker_c_results.json", encoding="utf-8"))
MIN_TP0_IN, MIN_TP3_IN = 958, 38
for k, v in res.items():
    mi, mo = v["metrics_inner"], v["metrics_outer"]
    gate = mi["tp0"] >= MIN_TP0_IN and mi["tp3"] >= MIN_TP3_IN
    print(f"  {k:<32} INNER={mi['correct']:4d} (TP0={mi['tp0']},TP3={mi['tp3']}) 게이트={gate!s:<5} "
          f"OUTER={mo['correct']:4d} ({mo['micro_f1']:.6f}) macro={mo['macro_f1']:.4f} params={v['params']}")
inner_best = max(res.items(), key=lambda x: x[1]["metrics_inner"]["correct"])
outer_best = max(res.items(), key=lambda x: x[1]["metrics_outer"]["correct"])
gate_pass = {k: v for k, v in res.items() if v["metrics_inner"]["tp0"] >= MIN_TP0_IN and v["metrics_inner"]["tp3"] >= MIN_TP3_IN}
inner_best_gated = max(gate_pass.items(), key=lambda x: x[1]["metrics_inner"]["correct"])
print(f"\n  INNER 최고            : {inner_best[0]} -> OUTER {inner_best[1]['metrics_outer']['correct']}")
print(f"  INNER 최고(게이트 통과): {inner_best_gated[0]} -> OUTER {inner_best_gated[1]['metrics_outer']['correct']}")
print(f"  OUTER 최고(공표 챔피언): {outer_best[0]} -> INNER {outer_best[1]['metrics_inner']['correct']} "
      f"(게이트 {outer_best[1]['metrics_inner']['tp3'] >= MIN_TP3_IN})")

# ---- McNemar ----
print("\n" + "=" * 112)
print("[3] McNemar 정확검정 (보고서의 bootstrap p 검증)")
print("=" * 112)
import sys as _s
T3 = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble")
_s.path.insert(0, str(T3)); os.chdir(T3)
from experiment_3a_inventory import load_canonical_data, load_all_models
ir, orr = load_canonical_data()
iy, oy, ip, op = load_all_models(ir, orr)
assert (oy == y_out).all()
base42 = op["LightGBM_seed42"].argmax(1)
base5 = op["LightGBM_5seed_sqrt_macro"].argmax(1)
r26pred = np.load(Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble\probabilities_track3.npz"))["pred_grand_fusion"]


def mc(base, cand, lbl):
    b, c = base == y_out, cand == y_out
    nb, ni = int(((~b) & c).sum()), int((b & (~c)).sum())
    p = binomtest(nb, nb + ni, 0.5).pvalue if nb + ni else 1.0
    print(f"  {lbl:<46} +{nb:3d}/-{ni:3d} net {nb-ni:+4d}  p = {p:.4g}")
    return {"plus": nb, "minus": ni, "net": nb - ni, "p": float(p)}


mcres = {}
for cname, lbl in [("C4", "C4 챔피언"), ("C2", "C2 (INNER 최고)"), ("C1", "C1 (통발/채낚기 특화)")]:
    pred = cands[cname][1]
    mcres[cname] = {
        "vs_seed42": mc(base42, pred, f"{lbl} vs LGB seed42"),
        "vs_5seed": mc(base5, pred, f"{lbl} vs LGB 5-seed"),
        "vs_r026": mc(r26pred, pred, f"{lbl} vs R026 Grand Fusion"),
    }
    print()

# ---- 통발/자망 실제 개선 여부 ----
print("=" * 112)
print("[4] 핵심 질문 — 통발/자망이 실제로 개선되었는가 (R026 정직모델 대비)")
print("=" * 112)
print(f"{'모델':<30}{'통발TP':>8}{'통발재현':>9}{'통발F1':>9}{'자망TP':>8}{'자망재현':>9}{'자망F1':>9}{'micro':>9}{'macro':>8}")
print(f"{'R026 정직 (기준)':<30}{int(tp26[2]):>8}{rec26[2]:>9.3f}{f126[2]:>9.4f}{int(tp26[1]):>8}{rec26[1]:>9.3f}{f126[1]:>9.4f}{0.599966:>9.4f}{f126.mean():>8.4f}")
for cname in ["C4", "C2", "C1", "C3"]:
    m = metrics(y_out, cands[cname][1])
    print(f"{cname:<30}{m['tp'][2]:>8}{m['rec'][2]:>9.3f}{m['f1'][2]:>9.4f}{m['tp'][1]:>8}{m['rec'][1]:>9.3f}{m['f1'][1]:>9.4f}{m['micro']:>9.4f}{m['macro']:>8.4f}")

json.dump({"candidates": {n: {"inner": i, **{k: v for k, v in m.items() if k != "cm"}} for n, i, m in rows},
           "strategy_selection": {"inner_best": inner_best[0], "inner_best_gated": inner_best_gated[0],
                                  "outer_best": outer_best[0]},
           "mcnemar": mcres,
           "r026_honest_reference": {"f1": f126.tolist(), "macro": float(f126.mean())}},
          open(OUT / "verify_r027_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nsaved ->", OUT / "verify_r027_results.json")
