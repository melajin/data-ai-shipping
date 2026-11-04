"""Independent verification step 5: confirm the recovered split identity, and check the
saved decision_score normalization claim (round_003 limitation #2)."""
import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

PKG = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
ROUND = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_003")
VER = ROUND / "verification_20261105"
OLD = {0: 2.0, 1: 3.0, 2: 2.0}
out = {}

splits = json.loads((PKG / "splits" / "splits_original.json").read_text(encoding="utf-8"))
roles = pd.read_csv(PKG / "splits/development_roles_long.csv", encoding="utf-8-sig")

# --- split identity now that the digest serialization is known
sid = {}
for fold in (0, 1, 2):
    f = next(x for x in splits["folds"] if x["fold"] == fold)
    sp = {k: set(int(v) for v in f[k]) for k in ("fit_ids", "inner_ids", "outer_ids")}
    rr = {r: set(roles[(roles.outer_fold == fold) & (roles.role == r)].rfid_id.astype(int))
          for r in ("FIT", "INNER", "OUTER")}
    inn = pd.read_csv(PKG / ("evaluation/seed_42/fold_%d/inner_predictions.csv" % fold), encoding="utf-8-sig")
    oof = pd.read_csv(PKG / "evaluation/seed_42/original_oof_predictions.csv", encoding="utf-8-sig")
    sid[str(fold)] = {
        "sizes": {k: len(v) for k, v in sp.items()},
        "fit_matches_roster": sp["fit_ids"] == rr["FIT"],
        "inner_matches_roster": sp["inner_ids"] == rr["INNER"],
        "outer_matches_roster": sp["outer_ids"] == rr["OUTER"],
        "inner_matches_inner_predictions_csv": sp["inner_ids"] == set(inn.rfid_id.astype(int)),
        "outer_matches_oof_fold_rows": sp["outer_ids"] == set(oof[oof.fold == fold].rfid_id.astype(int)),
        "fit_inner_overlap": len(sp["fit_ids"] & sp["inner_ids"]),
        "fit_outer_overlap": len(sp["fit_ids"] & sp["outer_ids"]),
        "inner_outer_overlap": len(sp["inner_ids"] & sp["outer_ids"]),
        "union_is_development": (sp["fit_ids"] | sp["inner_ids"] | sp["outer_ids"]) == set(int(v) for v in splits["development_ids"]),
    }
out["split_identity"] = sid
out["development_holdout_disjoint"] = len(set(splits["development_ids"]) & set(splits["holdout_ids"])) == 0
out["development_n"] = len(splits["development_ids"])
out["holdout_n"] = len(splits["holdout_ids"])

# --- decision score normalization check
ds = {}
for s in (42, 2026):
    dec = pd.read_csv(PKG / ("evaluation/seed_%d/oof_decisions.csv" % s), encoding="utf-8-sig")
    P = dec[["p0", "p1", "p2", "p3"]].to_numpy(float)
    S = dec[["decision_score0", "decision_score1", "decision_score2", "decision_score3"]].to_numpy(float)
    fac = dec.selected_trap_factor.to_numpy(float)
    scaled = P.copy()
    scaled[:, 2] = scaled[:, 2] * fac
    norm = scaled / scaled.sum(1, keepdims=True)
    ds[str(s)] = {
        "factor_matches_fold_map": bool((fac == dec.fold.map(OLD).to_numpy(float)).all()),
        "saved_scores_rowsum_max_err": float(np.abs(S.sum(1) - 1).max()),
        "max_abs_diff_vs_normalized_scaled": float(np.abs(S - norm).max()),
        "max_abs_diff_vs_unnormalized_scaled": float(np.abs(S - scaled).max()),
        "argmax_saved_scores_vs_argmax_unnormalized": int((S.argmax(1) != scaled.argmax(1)).sum()),
        "argmax_saved_scores_vs_chosen_class": int((S.argmax(1) != dec.chosen_class.to_numpy(int)).sum()),
        "chosen_class_prob_is_original_p": float(np.abs(
            dec.chosen_class_original_probability.to_numpy(float)
            - P[np.arange(len(P)), dec.chosen_class.to_numpy(int)]).max()),
        "uncorrected_class_prob_is_original_p": float(np.abs(
            dec.uncorrected_class_original_probability.to_numpy(float)
            - P[np.arange(len(P)), dec.uncorrected_class.to_numpy(int)]).max()),
        "saved_p_vs_original_oof_max_abs_diff": None,
    }
    oof = pd.read_csv(PKG / ("evaluation/seed_%d/original_oof_predictions.csv" % s), encoding="utf-8-sig")
    a = dec.sort_values("rfid_id")[["p0", "p1", "p2", "p3"]].to_numpy(float)
    b = oof.sort_values("rfid_id")[["p0", "p1", "p2", "p3"]].to_numpy(float)
    ds[str(s)]["saved_p_vs_original_oof_max_abs_diff"] = float(np.abs(a - b).max())
out["decision_scores"] = ds

VER.joinpath("v5_split_and_scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
