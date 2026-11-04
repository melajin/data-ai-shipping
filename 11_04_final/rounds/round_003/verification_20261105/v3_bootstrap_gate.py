"""Independent verification step 3: bootstrap, probability diagnostics, progress gate, report tables."""
import json
from pathlib import Path
import numpy as np
from sklearn.metrics import log_loss

ROUND = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_003")
VER = ROUND / "verification_20261105"
SEEDS = (42, 2026)
METHODS = ("A_raw", "A_old", "A_micro_select")
PAIRS = (("A_old", "A_raw"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select"))
N = 5897

z = np.load(VER / "v2_frames.npz", allow_pickle=True)
data = {s: {"y": z["s%d_y_true" % s].astype(int), "days": z["s%d_observed_days" % s].astype(float),
            "fold": z["s%d_fold" % s].astype(int), "P": z["s%d_P" % s].astype(float),
            "pred": {m: z["s%d_%s" % (s, m)].astype(int) for m in METHODS}} for s in SEEDS}
res = json.loads((ROUND / "artifacts" / "result.json").read_text(encoding="utf-8"))
out = {}


def cm_from(y, p, w=None):
    code = y * 4 + p
    return np.bincount(code, weights=w, minlength=16).reshape(4, 4).astype(float)


def micro_macro(cm):
    tot = cm.sum()
    micro = cm.trace() / tot if tot else np.nan
    tp = np.diag(cm)
    fp = cm.sum(0) - tp
    fn = cm.sum(1) - tp
    den = 2 * tp + fp + fn
    f1 = np.where(den > 0, 2 * tp / np.where(den > 0, den, 1), 0.0)
    return micro, f1.mean(), f1


# ---------- 3a. recompute CI from the saved npz draws ----------
npz = np.load(ROUND / "artifacts" / "paired_bootstrap_draws.npz")
ci_from_saved = {}
for a, b in PAIRS:
    key = "%s_to_%s__all__" % (a, b)
    ci_from_saved["%s_to_%s" % (a, b)] = {}
    for metric in ("micro_f1", "macro_f1"):
        arr = npz[key + metric]
        pm = arr.mean(axis=1)
        ci = [float(np.percentile(pm, 2.5)), float(np.percentile(pm, 97.5))]
        saved = res["paired_bootstrap"]["by_comparison"]["%s_to_%s" % (a, b)]["all"][metric]["ci95_percentile_mean_across_seeds"]
        ci_from_saved["%s_to_%s" % (a, b)][metric] = {
            "shape": list(arr.shape), "ci_from_saved_draws": ci, "saved_summary_ci": saved,
            "max_abs_diff": max(abs(ci[0] - saved[0]), abs(ci[1] - saved[1])),
            "draw_mean": float(pm.mean()),
            "saved_bootstrap_mean": res["paired_bootstrap"]["by_comparison"]["%s_to_%s" % (a, b)]["all"][metric]["bootstrap_mean_delta_mean_across_seeds"],
            "point_delta_saved": res["paired_bootstrap"]["by_comparison"]["%s_to_%s" % (a, b)]["all"][metric]["point_delta_mean_across_seeds"],
        }
out["ci_recomputed_from_saved_draws"] = ci_from_saved
out["npz_keys"] = len(npz.files)

# ---------- 3b. exact re-run of the documented bootstrap scheme ----------
def run_bootstrap(seed_value, reps=5000, batch=40, exact_batching=True):
    rng = np.random.default_rng(seed_value)
    draws_out = {"%s_to_%s" % (a, b): {m: np.zeros((reps, 2)) for m in ("micro_f1", "macro_f1")}
                 for a, b in PAIRS}
    code = {s: {m: data[s]["y"] * 4 + data[s]["pred"][m] for m in METHODS} for s in SEEDS}
    step = batch if exact_batching else reps
    for start in range(0, reps, step):
        stop = min(start + step, reps)
        samples = rng.integers(0, N, size=(stop - start, N), endpoint=False)
        for r in range(stop - start):
            w = np.bincount(samples[r], minlength=N).astype(float)
            vals = {}
            for s in SEEDS:
                vals[s] = {}
                for m in METHODS:
                    cm = np.bincount(code[s][m], weights=w, minlength=16).reshape(4, 4)
                    mi, ma, _ = micro_macro(cm)
                    vals[s][m] = (mi, ma)
            for a, b in PAIRS:
                for si, s in enumerate(SEEDS):
                    draws_out["%s_to_%s" % (a, b)]["micro_f1"][start + r, si] = vals[s][b][0] - vals[s][a][0]
                    draws_out["%s_to_%s" % (a, b)]["macro_f1"][start + r, si] = vals[s][b][1] - vals[s][a][1]
    return draws_out


exact = run_bootstrap(20261105)
rep = {}
for a, b in PAIRS:
    k = "%s_to_%s" % (a, b)
    rep[k] = {}
    for metric in ("micro_f1", "macro_f1"):
        mine = exact[k][metric]
        saved = npz["%s__all__%s" % (k, metric)]
        pm = mine.mean(axis=1)
        ci = [float(np.percentile(pm, 2.5)), float(np.percentile(pm, 97.5))]
        saved_ci = res["paired_bootstrap"]["by_comparison"][k]["all"][metric]["ci95_percentile_mean_across_seeds"]
        rep[k][metric] = {"draw_max_abs_diff_vs_saved_npz": float(np.abs(mine - saved).max()),
                          "my_ci": ci, "saved_ci": saved_ci,
                          "ci_max_abs_diff": max(abs(ci[0] - saved_ci[0]), abs(ci[1] - saved_ci[1]))}
out["exact_rerun_seed_20261105"] = rep

# ---------- 3c. fresh independent bootstrap with a different seed ----------
fresh = run_bootstrap(777000777, reps=5000, batch=250)
fr = {}
for a, b in PAIRS:
    k = "%s_to_%s" % (a, b)
    fr[k] = {}
    for metric in ("micro_f1", "macro_f1"):
        pm = fresh[k][metric].mean(axis=1)
        fr[k][metric] = {"ci95": [float(np.percentile(pm, 2.5)), float(np.percentile(pm, 97.5))],
                         "mean": float(pm.mean()),
                         "p_draw_le_0": float((pm <= 0).mean())}
out["fresh_bootstrap_seed_777000777"] = fr

# ---------- 3d. probability diagnostics ----------
pq = {}
for s in SEEDS:
    P, y, pr = data[s]["P"], data[s]["y"], data[s]["pred"]["A_raw"]
    sel = np.clip(P[np.arange(len(y)), y], 1e-15, 1.0)
    onehot = np.eye(4)[y]
    conf = P.max(1)
    correct = pr == y
    b = np.minimum(np.floor(conf * 10).astype(int), 9)
    ece = 0.0
    for k in range(10):
        act = b == k
        if act.sum():
            ece += act.sum() / len(y) * abs(correct[act].mean() - conf[act].mean())
    mine = {"logloss": float(-np.log(sel).mean()),
            "logloss_sklearn": float(log_loss(y, P, labels=[0, 1, 2, 3])),
            "brier_sum_squared_mean": float(np.square(P - onehot).sum(1).mean()),
            "brier_divided_by_4": float(np.square(P - onehot).sum(1).mean() / 4),
            "ece_10_equal_width": float(ece),
            "high_conf_ge_0_9_errors": int(((conf >= 0.9) & (~correct)).sum()),
            "n_conf_ge_0_9": int((conf >= 0.9).sum())}
    saved = res["original_probability_quality_by_seed_and_scope"][str(s)]["all"]
    mine["saved"] = {k: saved.get(k) for k in ("logloss", "multiclass_brier_sum_squared_mean",
                                               "ece_10_equal_width", "high_confidence_raw_max_ge_0_9_errors", "n")}
    mine["match"] = (abs(mine["logloss"] - saved["logloss"]) < 1e-12
                     and abs(mine["brier_sum_squared_mean"] - saved["multiclass_brier_sum_squared_mean"]) < 1e-12
                     and abs(mine["ece_10_equal_width"] - saved["ece_10_equal_width"]) < 1e-12
                     and mine["high_conf_ge_0_9_errors"] == saved["high_confidence_raw_max_ge_0_9_errors"])
    pq[str(s)] = mine
out["probability_quality"] = pq

# ---------- 3e. progress gate ----------
v2 = json.loads((VER / "v2_recompute.json").read_text(encoding="utf-8"))
M = v2["metrics"]
micro_delta = {s: M[str(s)]["all"]["A_micro_select"]["micro_f1"] - M[str(s)]["all"]["A_raw"]["micro_f1"] for s in SEEDS}
macro_delta_mean = float(np.mean([M[str(s)]["all"]["A_micro_select"]["macro_f1"] - M[str(s)]["all"]["A_raw"]["macro_f1"] for s in SEEDS]))
class_delta = {s: [M[str(s)]["all"]["A_micro_select"]["class_f1"][c] - M[str(s)]["all"]["A_raw"]["class_f1"][c] for c in range(4)] for s in SEEDS}
nat_delta = {s: M[str(s)]["days_1_7"]["A_micro_select"]["macro_f1"] - M[str(s)]["days_1_7"]["A_raw"]["macro_f1"] for s in SEEDS}
ci_low = ci_from_saved["A_raw_to_A_micro_select"]["micro_f1"]["ci_from_saved_draws"][0]
gate = {
    "mean_micro_delta": float(np.mean(list(micro_delta.values()))),
    "mean_micro_delta_at_least_0_005": bool(np.mean(list(micro_delta.values())) >= 0.005),
    "both_seed_micro_deltas_positive": bool(all(v > 0 for v in micro_delta.values())),
    "paired_ci_lower_above_zero": bool(ci_low > 0),
    "mean_macro_not_lower": bool(macro_delta_mean >= 0),
    "each_seed_class_f1_drop_no_more_than_0_01": bool(all(min(class_delta[s]) >= -0.01 for s in SEEDS)),
    "each_seed_natural_1_7_macro_drop_no_more_than_0_01": bool(all(nat_delta[s] >= -0.01 for s in SEEDS)),
    "micro_delta_by_seed": {str(s): micro_delta[s] for s in SEEDS},
    "macro_delta_mean": macro_delta_mean,
    "class_f1_delta_by_seed": {str(s): class_delta[s] for s in SEEDS},
    "natural_1_7_macro_delta_by_seed": {str(s): nat_delta[s] for s in SEEDS},
}
gate["all_conditions"] = bool(gate["mean_micro_delta_at_least_0_005"] and gate["both_seed_micro_deltas_positive"]
                              and gate["paired_ci_lower_above_zero"] and gate["mean_macro_not_lower"]
                              and gate["each_seed_class_f1_drop_no_more_than_0_01"]
                              and gate["each_seed_natural_1_7_macro_drop_no_more_than_0_01"])
sg = res["selected_vs_raw_progress_gate"]
gate["saved_all_criteria_met"] = sg["all_criteria_met"]
gate["saved_criteria"] = sg["criteria"]
gate["agrees_with_saved"] = bool(
    gate["all_conditions"] == sg["all_criteria_met"]
    and gate["mean_micro_delta_at_least_0_005"] == sg["criteria"]["mean_micro_delta_at_least_0_005"]
    and gate["both_seed_micro_deltas_positive"] == sg["criteria"]["both_seed_micro_deltas_positive"]
    and gate["paired_ci_lower_above_zero"] == sg["criteria"]["paired_5000_vessel_bootstrap_ci_lower_above_zero"]
    and gate["mean_macro_not_lower"] == sg["criteria"]["mean_macro_f1_not_decreased"]
    and gate["each_seed_class_f1_drop_no_more_than_0_01"] == sg["criteria"]["each_seed_class_f1_drop_no_more_than_0_01"]
    and gate["each_seed_natural_1_7_macro_drop_no_more_than_0_01"] == sg["criteria"]["each_seed_natural_1_7_macro_f1_drop_no_more_than_0_01"])
out["progress_gate"] = gate

# ---------- 3f. report table numbers ----------
rep_tab = {}
for meth in METHODS:
    rep_tab[meth] = {"class_f1_mean_across_seeds": [float(np.mean([M[str(s)]["all"][meth]["class_f1"][c] for s in SEEDS])) for c in range(4)],
                     "micro_mean": float(np.mean([M[str(s)]["all"][meth]["micro_f1"] for s in SEEDS])),
                     "macro_mean": float(np.mean([M[str(s)]["all"][meth]["macro_f1"] for s in SEEDS]))}
rep_tab["macro_gap_old_minus_raw"] = rep_tab["A_old"]["macro_mean"] - rep_tab["A_raw"]["macro_mean"]
rep_tab["macro_gap_old_minus_selected"] = rep_tab["A_old"]["macro_mean"] - rep_tab["A_micro_select"]["macro_mean"]
out["report_tables"] = rep_tab

VER.joinpath("v3_bootstrap_gate.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
