"""Independent verification step 6: round bookkeeping self-consistency."""
import hashlib, json, os
from pathlib import Path

WORK = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final")
ROUND = WORK / "rounds" / "round_003"
VER = ROUND / "verification_20261105"
out = {}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# completion manifest
cm = json.loads((ROUND / "completion_manifest.json").read_text(encoding="utf-8"))
rows = {}
for rel, exp in cm["files"].items():
    p = WORK / rel.replace("\\", os.sep)
    rows[rel] = {"exists": p.exists(), "expected": exp,
                 "actual": sha(p) if p.exists() else None}
    rows[rel]["match"] = rows[rel]["actual"] == exp
out["completion_manifest"] = rows
out["completion_manifest_all_match"] = all(v["match"] for v in rows.values())

# artifacts referenced inside result.json
res = json.loads((ROUND / "artifacts" / "result.json").read_text(encoding="utf-8"))
pol_obj = json.loads((ROUND / "artifacts" / "decision_policy_frozen.json").read_text(encoding="utf-8"))
pol_embedded_hash = pol_obj.pop("policy_sha256_before_hash_field", None)
pol_canonical_sha = hashlib.sha256(
    json.dumps(pol_obj, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
).hexdigest()
ref = {
    "predictions.csv": (ROUND / "artifacts" / "predictions.csv", res["prediction_artifact"]["sha256"]),
    "paired_bootstrap_draws.npz": (ROUND / "artifacts" / "paired_bootstrap_draws.npz",
                                   res["paired_bootstrap"]["raw_numeric_draws_artifact"]["sha256"]),
    "run_round003.py": (ROUND / "code" / "run_round003.py", res["runner_sha256"]),
    "experiment.json": (ROUND / "configs" / "experiment.json", res["config_sha256"]),
    "source_hash_manifest.json": (ROUND / "artifacts" / "source_hash_manifest.json",
                                  res["source_hash_manifest_sha256"]),
    "review/precheck.json": (ROUND / "review" / "precheck.json", res["reviewer_precheck"]["sha256"]),
}
rr = {}
for k, (p, exp) in ref.items():
    rr[k] = {"exists": p.exists(), "expected": exp, "actual": sha(p) if p.exists() else None}
    rr[k]["match"] = rr[k]["actual"] == exp
rr["decision_policy_frozen.json"] = {
    "exists": (ROUND / "artifacts" / "decision_policy_frozen.json").exists(),
    "expected_canonical_pre_hash": res["policy_sha256"],
    "embedded_pre_hash": pol_embedded_hash,
    "recomputed_canonical_pre_hash": pol_canonical_sha,
    "raw_file_sha256": sha(ROUND / "artifacts" / "decision_policy_frozen.json"),
    "match": (pol_canonical_sha == res["policy_sha256"] == pol_embedded_hash),
}
out["result_json_referenced_artifacts"] = rr
out["result_json_refs_all_match"] = all(v["match"] for v in rr.values())

# plan hash recorded in source manifest / review
shm = json.loads((ROUND / "artifacts" / "source_hash_manifest.json").read_text(encoding="utf-8"))
out["plan_hash"] = {"recorded": shm["local"]["plan"]["sha256"], "actual": sha(ROUND / "ROUND_PLAN.md")}
out["plan_hash"]["match"] = out["plan_hash"]["recorded"] == out["plan_hash"]["actual"]
out["launcher_hash"] = {"recorded": shm["local"]["launcher"]["sha256"],
                        "actual": sha(ROUND / "code" / "launch_round003.ps1")}
out["launcher_hash"]["match"] = out["launcher_hash"]["recorded"] == out["launcher_hash"]["actual"]

# run snapshots vs live code
snaps = sorted((ROUND / "artifacts").glob("run_snapshot_*"))
sn = {}
for s in snaps:
    sn[s.name] = {
        "run_round003.py": sha(s / "run_round003.py") == sha(ROUND / "code" / "run_round003.py"),
        "launch_round003.ps1": sha(s / "launch_round003.ps1") == sha(ROUND / "code" / "launch_round003.ps1"),
        "experiment.json": sha(s / "experiment.json") == sha(ROUND / "configs" / "experiment.json"),
        "ROUND_PLAN.md": sha(s / "ROUND_PLAN.md") == sha(ROUND / "ROUND_PLAN.md"),
    }
out["run_snapshots_identical_to_live"] = sn

# pid consistency
rec = json.loads((ROUND / "logs" / "launch_receipt_score_20261104T163427781Z.json").read_text(encoding="utf-8-sig"))
rt = json.loads((ROUND / "logs" / "runner_runtime_score.json").read_text(encoding="utf-8-sig"))
out["score_run_evidence"] = {
    "receipt_runner_pid": rec["runner_pid"], "runner_self_reported_pid": rt["pid"],
    "pid_agrees": rec["runner_pid"] == rt["pid"],
    "receipt_elapsed_s": rec["elapsed_seconds"], "runner_elapsed_s": rt["elapsed_seconds"],
    "receipt_exit": rec["exit_code"], "runner_exit": rt["exit_code"],
    "timed_out": rec["timed_out"],
    "score_receipts_found": len(list((ROUND / "logs").glob("launch_receipt_score_*.json"))),
    "stderr_bytes": (ROUND / "logs" / "stderr_score_20261104T163427781Z.log").stat().st_size,
}

# ledger / status alignment
led = (WORK / "EXPERIMENT_LEDGER.csv").read_text(encoding="utf-8-sig").strip().splitlines()
out["ledger_last_rows"] = led[-2:]
st = json.loads((WORK / "STATUS.json").read_text(encoding="utf-8-sig"))
out["status_round"] = {k: st.get(k) for k in ("current_round", "round_status", "goal_status")}
out["status_scores_keys"] = list(st.get("scores", {}).keys())
sc = st.get("scores", {})
out["status_round_003"] = sc.get("round_003")

VER.joinpath("v6_manifest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
