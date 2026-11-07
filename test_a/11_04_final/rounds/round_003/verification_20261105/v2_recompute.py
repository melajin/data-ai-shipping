"""Independent verification step 2: recompute the three decisions + metrics with sklearn."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_recall_fscore_support, confusion_matrix

PKG = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
ROUND = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_003")
VER = ROUND / "verification_20261105"
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)
L = [0, 1, 2, 3]
GRID = [1.0, 1.5, 2.0, 2.5, 3.0]
TOL = 1e-12
OLD = {0: 2.0, 1: 3.0, 2: 2.0}


def decide(P, factor):
    S = P.copy()
    S[:, 2] = S[:, 2] * factor
    return S.argmax(1)


def mets(y, yp):
    pr, rc, f1, sup = precision_recall_fscore_support(y, yp, labels=L, zero_division=0)
    return {"micro_f1": f1_score(y, yp, labels=L, average="micro", zero_division=0),
            "macro_f1": f1_score(y, yp, labels=L, average="macro", zero_division=0),
            "weighted_f1": f1_score(y, yp, labels=L, average="weighted", zero_division=0),
            "class_f1": f1.tolist(), "class_precision": pr.tolist(), "class_recall": rc.tolist(),
            "class_support": sup.astype(float).tolist(),
            "confusion_matrix": confusion_matrix(y, yp, labels=L).astype(float).tolist(),
            "correct": float((y == yp).sum()), "n": float(len(y))}


out = {"selection": {}, "old_rule_crosscheck": {}, "metrics": {}}

# ---------- INNER selection ----------
sel = {}
for s in SEEDS:
    for f in FOLDS:
        inn = pd.read_csv(PKG / f"evaluation/seed_{s}/fold_{f}/inner_predictions.csv", encoding="utf-8-sig")
        P = inn[["p0", "p1", "p2", "p3"]].to_numpy(float)
        y = inn.y_true.to_numpy(int)
        d = inn.observed_days.to_numpy(float)
        nat = (d >= 1) & (d <= 7)
        sup_full = [int((y == c).sum()) for c in L]
        sup_nat = [int((y[nat] == c).sum()) for c in L]
        fallback = (0 in sup_full) or (0 in sup_nat)
        base = mets(y, decide(P, 1.0))
        base_nat = mets(y[nat], decide(P[nat], 1.0))
        cands = []
        for g in GRID:
            m = mets(y, decide(P, g))
            mn = mets(y[nat], decide(P[nat], g))
            elig = (m["macro_f1"] >= base["macro_f1"] - TOL
                    and all(m["class_f1"][c] >= base["class_f1"][c] - 0.01 - TOL for c in L)
                    and mn["macro_f1"] >= base_nat["macro_f1"] - 0.01 - TOL)
            cands.append({"factor": g, "eligible": elig, "micro_f1": m["micro_f1"],
                          "macro_f1": m["macro_f1"], "class_f1": m["class_f1"],
                          "days_1_7_macro_f1": mn["macro_f1"], "correct": m["correct"], "n": m["n"]})
        if fallback:
            chosen = 1.0
        else:
            elig = [c for c in cands if c["eligible"]]
            best = max(c["micro_f1"] for c in elig)
            near = [c for c in elig if c["micro_f1"] >= best - TOL]
            near.sort(key=lambda c: (abs(c["factor"] - 1.0), c["factor"]))
            chosen = near[0]["factor"]
        sel[(s, f)] = chosen
        out["selection"][f"{s}/{f}"] = {"independent_factor": chosen, "support_fallback": fallback,
                                        "support_full_inner": sup_full, "support_natural_1_7_inner": sup_nat,
                                        "candidate_grid": cands}

# compare to saved frozen policy
pol = json.loads((ROUND / "artifacts" / "decision_policy_frozen.json").read_text(encoding="utf-8"))
for ch in pol["choices"]:
    k = str(ch["seed"]) + "/" + str(ch["fold"])
    o = out["selection"][k]
    o["saved_factor"] = ch["selected_factor"]
    o["factor_match"] = abs(ch["selected_factor"] - o["independent_factor"]) < 1e-12
    o["saved_support_fallback"] = ch["support_fallback"]
    o["support_match"] = (ch["support_full_inner"] == o["support_full_inner"]
                          and ch["support_natural_1_7_inner"] == o["support_natural_1_7_inner"])
    diffs = []
    for a, b in zip(ch["candidate_grid"], o["candidate_grid"]):
        diffs.append(max(abs(a["micro_f1"] - b["micro_f1"]), abs(a["macro_f1"] - b["macro_f1"]),
                         abs(a["days_1_7_macro_f1"] - b["days_1_7_macro_f1"]),
                         max(abs(x - y) for x, y in zip(a["class_f1"], b["class_f1"])),
                         (0.0 if a["eligible"] == b["eligible"] else 1.0)))
    o["grid_max_abs_diff"] = max(diffs)

# ---------- OUTER decisions ----------
frames = {}
for s in SEEDS:
    oof = pd.read_csv(PKG / f"evaluation/seed_{s}/original_oof_predictions.csv",
                      encoding="utf-8-sig").sort_values("rfid_id").reset_index(drop=True)
    P = oof[["p0", "p1", "p2", "p3"]].to_numpy(float)
    fold = oof.fold.to_numpy(int)
    A_raw = decide(P, 1.0)
    A_old = np.empty(len(oof), int)
    A_sel = np.empty(len(oof), int)
    for f in FOLDS:
        m = fold == f
        A_old[m] = decide(P[m], OLD[f])
        A_sel[m] = decide(P[m], sel[(s, f)])
    oof["A_raw"], oof["A_old"], oof["A_micro_select"] = A_raw, A_old, A_sel
    frames[s] = oof
    dec = pd.read_csv(PKG / f"evaluation/seed_{s}/oof_decisions.csv",
                      encoding="utf-8-sig").sort_values("rfid_id").reset_index(drop=True)
    out["old_rule_crosscheck"][str(s)] = {
        "ids_align": bool((dec.rfid_id.values == oof.rfid_id.values).all()),
        "selected_trap_factor_by_fold": {str(f): sorted(set(dec.selected_trap_factor[fold == f].tolist())) for f in FOLDS},
        "chosen_class_vs_my_A_old_mismatches": int((dec.chosen_class.values != A_old).sum()),
        "uncorrected_class_vs_my_A_raw_mismatches": int((dec.uncorrected_class.values != A_raw).sum()),
    }

# ---------- metrics all scopes ----------
def scopes(df):
    d = df.observed_days.to_numpy(float)
    yield "all", np.ones(len(df), bool)
    for f in FOLDS:
        yield "fold_" + str(f), df.fold.to_numpy(int) == f
    yield "days_1_7", (d >= 1) & (d <= 7)
    yield "days_8_30", (d >= 8) & (d <= 30)
    yield "days_31_90", (d >= 31) & (d <= 90)
    yield "days_91_plus", d >= 91
    yield "days_zero", d == 0
    yield "days_unsupported", (~np.isfinite(d)) | (d < 0)


recomp = {}
for s in SEEDS:
    df = frames[s]
    y = df.y_true.to_numpy(int)
    recomp[str(s)] = {}
    for name, mask in scopes(df):
        recomp[str(s)][name] = {}
        for meth in ("A_raw", "A_old", "A_micro_select"):
            if mask.sum() == 0:
                recomp[str(s)][name][meth] = None
            else:
                recomp[str(s)][name][meth] = mets(y[mask], df[meth].to_numpy(int)[mask])
out["metrics"] = recomp

# ---------- compare to saved result.json ----------
res = json.loads((ROUND / "artifacts" / "result.json").read_text(encoding="utf-8"))
cmpres = {"max_abs_diff": 0.0, "mismatches": [], "compared_fields": 0, "null_scopes": []}
for s in SEEDS:
    for name in recomp[str(s)]:
        for meth in ("A_raw", "A_old", "A_micro_select"):
            mine = recomp[str(s)][name][meth]
            try:
                saved = res["metrics"]["by_seed"][str(s)][name][meth]
            except KeyError:
                cmpres["mismatches"].append("missing saved " + str(s) + "/" + name + "/" + meth)
                continue
            if mine is None:
                cmpres["null_scopes"].append(str(s) + "/" + name + "/" + meth)
                for k in ("micro_f1", "macro_f1", "weighted_f1"):
                    if isinstance(saved, dict) and saved.get(k) is not None:
                        cmpres["mismatches"].append(str(s) + "/" + name + "/" + meth + "/" + k + " saved not null for empty scope")
                continue
            for k in ("micro_f1", "macro_f1", "weighted_f1"):
                cmpres["compared_fields"] += 1
                dd = abs(mine[k] - saved[k])
                cmpres["max_abs_diff"] = max(cmpres["max_abs_diff"], dd)
                if dd > 1e-12:
                    cmpres["mismatches"].append(str(s) + "/" + name + "/" + meth + "/" + k + " mine=" + repr(mine[k]) + " saved=" + repr(saved[k]))
            for k in ("class_f1", "class_precision", "class_recall", "class_support"):
                cmpres["compared_fields"] += 4
                dd = max(abs(a - b) for a, b in zip(mine[k], saved[k]))
                cmpres["max_abs_diff"] = max(cmpres["max_abs_diff"], dd)
                if dd > 1e-12:
                    cmpres["mismatches"].append(str(s) + "/" + name + "/" + meth + "/" + k)
            cmpres["compared_fields"] += 16
            if not np.array_equal(np.array(mine["confusion_matrix"]), np.array(saved["confusion_matrix"])):
                cmpres["mismatches"].append(str(s) + "/" + name + "/" + meth + "/confusion_matrix")
out["result_json_comparison"] = cmpres

mean_tab = {}
for meth in ("A_raw", "A_old", "A_micro_select"):
    mean_tab[meth] = {k: float(np.mean([recomp[str(s)]["all"][meth][k] for s in SEEDS]))
                      for k in ("micro_f1", "macro_f1", "weighted_f1")}
    mean_tab[meth]["correct_by_seed"] = [recomp[str(s)]["all"][meth]["correct"] for s in SEEDS]
out["headline_means_independent"] = mean_tab
out["headline_means_saved"] = {m: {k: res["metrics"]["arithmetic_mean_across_seeds"]["all"][m][k]
                                   for k in ("micro_f1", "macro_f1", "weighted_f1")}
                               for m in ("A_raw", "A_old", "A_micro_select")}

trans = {}
for a, b in (("A_old", "A_raw"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select")):
    trans[a + "_to_" + b] = {}
    for s in SEEDS:
        df = frames[s]
        y = df.y_true.to_numpy(int)
        ca = df[a].to_numpy(int) == y
        cb = df[b].to_numpy(int) == y
        trans[a + "_to_" + b][str(s)] = {"gain": int((~ca & cb).sum()), "loss": int((ca & ~cb).sum()),
                                         "net": int((~ca & cb).sum() - (ca & ~cb).sum())}
out["transitions_independent"] = trans
out["transitions_saved"] = {k: {s: {"gain": v2["gain_new_correct"], "loss": v2["loss_new_wrong"],
                                    "net": v2["net_correct"]}
                                for s, v2 in res["paired_transition_counts"][k]["by_seed"].items()}
                            for k in res["paired_transition_counts"]}
out["transitions_match"] = out["transitions_independent"] == out["transitions_saved"]

pred = pd.read_csv(ROUND / "artifacts" / "predictions.csv", encoding="utf-8-sig")
pc = {"rows": int(len(pred)), "columns": list(pred.columns), "mismatch_by_seed": {}}
for s in SEEDS:
    sub = pred[pred.seed == s].sort_values("rfid_id").reset_index(drop=True)
    df = frames[s]
    entry = {"ids_align": bool((sub.rfid_id.values == df.rfid_id.values).all()),
             "y_true": int((sub.y_true.values != df.y_true.values).sum())}
    for m in ("A_raw", "A_old", "A_micro_select"):
        if m in sub.columns:
            entry[m] = int((sub[m].values != df[m].values).sum())
    pc["mismatch_by_seed"][str(s)] = entry
out["predictions_csv_check"] = pc

VER.joinpath("v2_recompute.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
np.savez_compressed(VER / "v2_frames.npz",
                    **{("s" + str(s) + "_" + c): frames[s][c].to_numpy()
                       for s in SEEDS for c in ("rfid_id", "y_true", "observed_days", "fold", "A_raw", "A_old", "A_micro_select")},
                    **{("s" + str(s) + "_P"): frames[s][["p0", "p1", "p2", "p3"]].to_numpy() for s in SEEDS})

print("SELECTION")
for k, v in out["selection"].items():
    print(" ", k, "indep=", v["independent_factor"], "saved=", v["saved_factor"],
          "match=", v["factor_match"], "support_match=", v["support_match"],
          "grid_max_abs_diff=", "%.3e" % v["grid_max_abs_diff"])
print("OLD RULE CROSSCHECK")
print(json.dumps(out["old_rule_crosscheck"], ensure_ascii=False, indent=1))
print("RESULT.JSON COMPARISON")
print(json.dumps(cmpres, ensure_ascii=False, indent=1)[:3000])
print("HEADLINE indep")
print(json.dumps(out["headline_means_independent"], indent=1))
print("HEADLINE saved")
print(json.dumps(out["headline_means_saved"], indent=1))
print("TRANSITIONS indep")
print(json.dumps(trans, indent=1))
print("TRANSITIONS saved")
print(json.dumps(out["transitions_saved"], indent=1))
print("PREDICTIONS")
print(json.dumps(pc, ensure_ascii=False, indent=1))
