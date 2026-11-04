"""Capture the Round 001 timing interface's synthetic-only process evidence."""
from __future__ import annotations
import hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "round_001/run_002"
RUN.mkdir(parents=True, exist_ok=True)
CODE = HERE / "timing_interface.py"
def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def main() -> int:
    started = datetime.now(timezone.utc).astimezone().isoformat()
    p = subprocess.run([sys.executable, str(CODE), "--self-check"], cwd=str(HERE), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    (RUN / "stdout.log").write_text(p.stdout, encoding="utf-8")
    (RUN / "stderr.log").write_text(p.stderr, encoding="utf-8")
    env = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
           "requested_model": "gpt-6-luna", "requested_effort": "xhigh",
           "runtime_receipt": "26_11_5/testb_next_experiment_20261105/integration/runtime_receipts/W2_start.json",
           "runtime_observation": "Orca start receipt reports gpt-6-luna/xhigh; internal serving execution not independently introspected"}
    (RUN / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"started_at": started, "ended_at": datetime.now(timezone.utc).astimezone().isoformat(),
              "exit_code": p.returncode, "argv": [sys.executable, str(CODE), "--self-check"],
              "stdout": str(RUN / "stdout.log"), "stderr": str(RUN / "stderr.log"),
              "code": {"path": str(CODE), "size_bytes": CODE.stat().st_size, "sha256": sha(CODE)},
              "scope": "synthetic rows only; no external or project score inputs opened"}
    (RUN / "process_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exit_code": p.returncode, "checks": p.stdout.strip(), "process_result": str(RUN / "process_result.json")}, ensure_ascii=False))
    return p.returncode

if __name__ == "__main__": raise SystemExit(main())
