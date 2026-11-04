"""Create the manager-gate receipt for the frozen Round 003 runner/config."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / "rounds" / "round_003"
REVIEW = ROUND / "review"
DATA = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료"
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    preflight = json.loads((REVIEW / "preflight_audit.json").read_text(encoding="utf-8"))
    if preflight.get("preflight_status") != "PASS":
        raise SystemExit("Reviewer input preflight has not passed")
    validation_path = ROUND / "artifacts" / "preflight_validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or validation.get("no_oof_metrics_computed") is not True:
        raise SystemExit("Author no-metric preflight has not passed")
    input_hashes = dict(preflight["input_hashes"])
    input_hashes["MANIFEST_SHA256.json"] = digest(DATA / "MANIFEST_SHA256.json")
    input_hashes["SOURCE_SHA256.json"] = digest(DATA / "SOURCE_SHA256.json")
    receipt = {
        "precheck_status": "PASS",
        "review_decision": "PASS_FOR_FROZEN_SCORE_STEP",
        "reviewed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runner_sha256": digest(ROUND / "code" / "run_round003.py"),
        "launcher_sha256": digest(ROUND / "code" / "launch_round003.ps1"),
        "config_sha256": digest(ROUND / "configs" / "experiment.json"),
        "plan_sha256": digest(ROUND / "ROUND_PLAN.md"),
        "preflight_validation_sha256": digest(validation_path),
        "preflight_audit_sha256": digest(REVIEW / "preflight_audit.json"),
        "reviewer_preflight_code_sha256": digest(REVIEW / "preflight_audit.py"),
        "independent_recompute_code_sha256": digest(REVIEW / "independent_recompute.py"),
        "package_manifest_sha256": input_hashes["MANIFEST_SHA256.json"],
        "source_manifest_sha256": input_hashes["SOURCE_SHA256.json"],
        "source_hashes": preflight["source_hashes"],
        "input_hashes": input_hashes,
        "checks": {
            "saved_input_preflight": "PASS",
            "archived_tabicl_source_and_six_training_metadata_confirm_fit_only_inner_unused": "PASS",
            "oof_and_inner_manifest_and_role_checks": "PASS",
            "old_class_decision_replays_from_original_probabilities_and_2_3_2_factor": "PASS",
            "saved_decision_score_normalized_representation": "verified independently; not used as probabilities",
            "holdout_full7372_f156_test2025_raw_rows_read": 0,
            "model_fit_or_inference": False,
            "classification_metrics_computed_by_reviewer_preflight": False,
        },
        "limitations": preflight["limitations"],
        "execution_gate": "Scoring still requires manager authorization token and launcher score mode; this receipt binds only the reviewed frozen runner/config.",
    }
    out = REVIEW / "precheck.json"
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "path": str(out),
        "precheck_status": receipt["precheck_status"],
        "runner_sha256": receipt["runner_sha256"],
        "launcher_sha256": receipt["launcher_sha256"],
        "config_sha256": receipt["config_sha256"],
        "plan_sha256": receipt["plan_sha256"],
        "preflight_validation_sha256": receipt["preflight_validation_sha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
