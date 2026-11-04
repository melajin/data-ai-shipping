"""Independent verification step 1: input integrity + structural checks."""
import hashlib, json
from pathlib import Path
import pandas as pd
import numpy as np

PKG = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
ROUND = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_003")
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

out = {}

# --- 1. hash check against package manifest and round manifest
pkg_man = json.loads((PKG / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))
rnd_man = json.loads((ROUND / "artifacts" / "source_hash_manifest.json").read_text(encoding="utf-8"))
rnd_files = rnd_man["whitelisted_files"]

# normalise package manifest to {relpath: sha}
def flat(m):
    if isinstance(m, dict) and "files" in m:
        m = m["files"]
    d = {}
    for k, v in m.items():
        if isinstance(v, dict):
            s = v.get("sha256") or v.get("hash")
            if s: d[k.replace("\\", "/")] = s
        elif isinstance(v, str):
            d[k.replace("\\", "/")] = v
    return d
pkg_flat = flat(pkg_man)

targets = []
for s in SEEDS:
    targets += [f"evaluation/seed_{s}/original_oof_predictions.csv",
                f"evaluation/seed_{s}/oof_decisions.csv"]
    for f in FOLDS:
        targets += [f"evaluation/seed_{s}/fold_{f}/inner_predictions.csv",
                    f"evaluation/seed_{s}/fold_{f}/training.json"]
targets += ["splits/development_roles_long.csv", "evaluation/final_fixed_decision_rule.json",
            "evaluation/trap_factors.csv", "metadata/classes.json"]

hcheck = {}
for t in targets:
    p = PKG / t
    live = sha(p)
    hcheck[t] = {"live": live,
                 "pkg_manifest": pkg_flat.get(t),
                 "pkg_match": pkg_flat.get(t) == live if t in pkg_flat else None,
                 "round_manifest": rnd_files.get(t, {}).get("sha256") if isinstance(rnd_files.get(t), dict) else None}
    hcheck[t]["round_match"] = (hcheck[t]["round_manifest"] == live) if hcheck[t]["round_manifest"] else None
out["input_hashes"] = hcheck
out["input_hash_all_match_pkg"] = all(v["pkg_match"] for v in hcheck.values() if v["pkg_match"] is not None)
out["input_hash_all_match_round"] = all(v["round_match"] for v in hcheck.values() if v["round_match"] is not None)
out["input_hash_missing_from_round_manifest"] = [k for k, v in hcheck.items() if v["round_manifest"] is None]

# --- 2. frozen rule inner_predictions hash cross-check
rule = json.loads((PKG / "evaluation" / "final_fixed_decision_rule.json").read_text(encoding="utf-8"))
ic = {}
for ch in rule["inner_choices"]:
    s, f = ch["seed"], ch["fold"]
    live = sha(PKG / f"evaluation/seed_{s}/fold_{f}/inner_predictions.csv")
    ic[f"{s}/{f}"] = {"rule_sha": ch["inner_predictions_sha256"], "live": live,
                      "match": ch["inner_predictions_sha256"] == live,
                      "rule_trap_factor": ch["trap_factor"]}
out["frozen_rule_inner_hashes"] = ic

# --- 3. structure
roles = pd.read_csv(PKG / "splits/development_roles_long.csv", encoding="utf-8-sig")
out["roles"] = {"rows": int(len(roles)), "unique_vessels": int(roles.rfid_id.nunique()),
                "rows_expected_5897x3": int(len(roles)) == 5897 * 3,
                "role_counts": {str(k): int(v) for k, v in roles.groupby(["outer_fold", "role"]).size().items()}}

inner_ids = {}
struct = {}
for s in SEEDS:
    oof = pd.read_csv(PKG / f"evaluation/seed_{s}/original_oof_predictions.csv", encoding="utf-8-sig")
    P = oof[["p0", "p1", "p2", "p3"]].to_numpy(float)
    struct[s] = {
        "rows": int(len(oof)),
        "unique_vessels": int(oof.rfid_id.nunique()),
        "fold_counts": {str(k): int(v) for k, v in oof.fold.value_counts().sort_index().items()},
        "y_true_values": sorted(int(x) for x in oof.y_true.unique()),
        "prob_finite": bool(np.isfinite(P).all()),
        "prob_min": float(P.min()), "prob_max": float(P.max()),
        "max_rowsum_err": float(np.abs(P.sum(1) - 1).max()),
    }
    for f in FOLDS:
        inn = pd.read_csv(PKG / f"evaluation/seed_{s}/fold_{f}/inner_predictions.csv", encoding="utf-8-sig")
        inner_ids[(s, f)] = set(inn.rfid_id)
        struct[s][f"inner_{f}_rows"] = int(len(inn))
        struct[s][f"inner_{f}_class_support"] = [int((inn.y_true == c).sum()) for c in range(4)]
out["oof_structure"] = {str(k): v for k, v in struct.items()}

# INNER set identity across folds / seeds
out["inner_set_relations"] = {
    "fold0_eq_fold1_seed42": inner_ids[(42, 0)] == inner_ids[(42, 1)],
    "fold0_eq_fold2_seed42": inner_ids[(42, 0)] == inner_ids[(42, 2)],
    "fold1_eq_fold2_seed42": inner_ids[(42, 1)] == inner_ids[(42, 2)],
    "seed42_eq_seed2026_per_fold": {str(f): inner_ids[(42, f)] == inner_ids[(2026, f)] for f in FOLDS},
    "pairwise_overlap_seed42": {f"{a}&{b}": len(inner_ids[(42, a)] & inner_ids[(42, b)])
                                for a in FOLDS for b in FOLDS if a < b},
}

# INNER vs roles roster agreement, and OUTER/INNER disjointness
rel = {}
for f in FOLDS:
    roster_inner = set(roles[(roles.outer_fold == f) & (roles.role == "INNER")].rfid_id)
    roster_outer = set(roles[(roles.outer_fold == f) & (roles.role == "OUTER")].rfid_id)
    rel[str(f)] = {
        "roster_inner_n": len(roster_inner),
        "roster_outer_n": len(roster_outer),
        "inner_file_matches_roster": inner_ids[(42, f)] == roster_inner,
        "inner_outer_overlap": len(inner_ids[(42, f)] & roster_outer),
    }
out["inner_roster_relation"] = rel

# seed agreement on ids/labels/days
o42 = pd.read_csv(PKG / "evaluation/seed_42/original_oof_predictions.csv", encoding="utf-8-sig").sort_values("rfid_id").reset_index(drop=True)
o26 = pd.read_csv(PKG / "evaluation/seed_2026/original_oof_predictions.csv", encoding="utf-8-sig").sort_values("rfid_id").reset_index(drop=True)
out["seed_alignment"] = {
    "ids_equal": bool((o42.rfid_id.values == o26.rfid_id.values).all()),
    "y_true_equal": bool((o42.y_true.values == o26.y_true.values).all()),
    "observed_days_equal": bool((o42.observed_days.values == o26.observed_days.values).all()),
    "fold_equal": bool((o42.fold.values == o26.fold.values).all()),
    "probs_identical": bool(np.allclose(o42[["p0","p1","p2","p3"]].values, o26[["p0","p1","p2","p3"]].values)),
}
# observed_days distribution
d = o42.observed_days
out["observed_days"] = {"min": float(d.min()), "max": float(d.max()),
                        "zero": int((d == 0).sum()), "negative": int((d < 0).sum()),
                        "nonfinite": int((~np.isfinite(d.astype(float))).sum()),
                        "d1_7": int(((d >= 1) & (d <= 7)).sum()),
                        "d8_30": int(((d >= 8) & (d <= 30)).sum()),
                        "d31_90": int(((d >= 31) & (d <= 90)).sum()),
                        "d91p": int((d >= 91).sum())}

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
(ROUND / "verification_20261105" / "v1_integrity.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
