"""Run only synthetic checks and read-only inherited-baseline table preparation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = Path(r"D:/repos/fishing-track-classification")
RECEIPTS = ROOT / "26_11_5/testb_next_experiment_20261105/integration/runtime_receipts"
RUN = HERE / "run_001"
RUN.mkdir(exist_ok=True)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    started = datetime.now(timezone.utc).astimezone().isoformat()
    env = {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "requested_model": "gpt-6-luna",
        "requested_effort": "xhigh",
        "runtime_receipt": str(RECEIPTS / "W2_start.json"),
        "runtime_observation": "W2_start.json reports model=gpt-6-luna, effort=xhigh; provider-internal runtime not independently measurable here",
    }
    (RUN / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    steps = [
        ("synthetic_self_check", HERE / "timing_interface.py", ["--self-check"]),
        ("inherited_baseline_table", HERE / "build_inherited_comparison.py", []),
    ]
    results = []
    for name, script, args in steps:
        proc = subprocess.run([sys.executable, str(script), *args], cwd=str(ROOT),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        (RUN / f"{name}.stdout.log").write_text(proc.stdout, encoding="utf-8")
        (RUN / f"{name}.stderr.log").write_text(proc.stderr, encoding="utf-8")
        results.append({"name": name, "command": [sys.executable, str(script), *args],
                        "exit_code": proc.returncode,
                        "stdout_path": str(RUN / f"{name}.stdout.log"),
                        "stderr_path": str(RUN / f"{name}.stderr.log")})
        if proc.returncode != 0:
            break
    ended = datetime.now(timezone.utc).astimezone().isoformat()
    files = [
        HERE / "timing_interface.py", HERE / "build_inherited_comparison.py", HERE / "run_preparation.py",
        REPO / "code/tools/run_008_testB_20261101.py",
        REPO / "results/work_008/scores_meta.json", REPO / "results/work_008/scored_rows.pkl",
        REPO / "results/submission_20261101/testB_submission.csv",
        RECEIPTS / "W2_start.json", RECEIPTS / "W2_process.json",
    ]
    inputs = [{"path": str(p), "exists": p.exists(), "size_bytes": p.stat().st_size if p.exists() else None,
               "sha256": sha(p) if p.is_file() else None} for p in files]
    result = {"started_at": started, "ended_at": ended, "exit_code": next((s["exit_code"] for s in results if s["exit_code"] != 0), 0),
              "steps": results, "environment_path": str(RUN / "environment.json"), "input_code_hashes": inputs,
              "scope": "synthetic checks + read-only copy of inherited A fields; no actual 2026 score/B/C/threshold/performance work"}
    (RUN / "process_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exit_code": result["exit_code"], "steps": results, "process_result": str(RUN / "process_result.json")}, ensure_ascii=False))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
