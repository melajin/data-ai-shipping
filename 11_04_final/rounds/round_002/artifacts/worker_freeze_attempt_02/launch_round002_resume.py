from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROUND = Path(__file__).resolve().parents[1]
ROOT = ROUND.parents[1]
PYTHON = ROOT / "environments" / "round_002_catboost" / "Scripts" / "python.exe"
RUNNER = ROUND / "code" / "run_round002_resume.py"
LOGS = ROUND / "logs"
STDOUT, STDERR = LOGS / "stdout_attempt02.log", LOGS / "stderr_attempt02.log"
RECEIPT = LOGS / "execution_attempt02_launch_receipt.json"

def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def save(value):
    tmp = RECEIPT.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RECEIPT)

def main():
    env = os.environ.copy()
    env.update({"PYTHONDONTWRITEBYTECODE":"1", "PYTHONPYCACHEPREFIX":str(LOGS/".pycache"),
        "TEMP":str(LOGS/"temp"), "TMP":str(LOGS/"temp"), "OMP_NUM_THREADS":"3",
        "OPENBLAS_NUM_THREADS":"1", "MKL_NUM_THREADS":"1", "NUMEXPR_NUM_THREADS":"1"})
    (LOGS/".pycache").mkdir(parents=True, exist_ok=True); (LOGS/"temp").mkdir(parents=True, exist_ok=True)
    rec={"status":"starting","started_at_utc":utc(),"python":str(PYTHON),"runner":str(RUNNER),
        "working_directory":str(ROUND),"stdout":str(STDOUT),"stderr":str(STDERR),
        "reviewed_runner_sha256":"23362d1fca269485ded3f13a46127675dd261c8b3cc011a95e6a105a3fa9bd63",
        "config_sha256":"f7240e3eb5adb8bc130979b7aa891762ef840993b7e6ccf39aae8e52c85cb214",
        "manager_cutoff_utc":"2026-11-04T15:14:00Z","attempt1_exit_code":"unavailable"}
    save(rec)
    with STDOUT.open("w",encoding="utf-8",buffering=1) as out, STDERR.open("w",encoding="utf-8",buffering=1) as err:
        proc=subprocess.Popen([str(PYTHON),"-B","-u",str(RUNNER)],cwd=str(ROUND),env=env,stdout=out,stderr=err,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        rec.update({"status":"running","pid":proc.pid,"started_at_utc":utc()}); save(rec)
        code=proc.wait()
    rec.update({"status":"completed" if code==0 else "failed","finished_at_utc":utc(),"exit_code":int(code)})
    save(rec)
    return code

if __name__=="__main__":
    raise SystemExit(main())
