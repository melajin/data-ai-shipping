from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROUND = Path(__file__).resolve().parents[1]
ROOT = ROUND.parents[1]
PYTHON = ROOT / "environments" / "round_002_catboost" / "Scripts" / "python.exe"
RUNNER = ROUND / "code" / "run_round002_resume.py"
LOGS = ROUND / "logs"
STDOUT, STDERR = LOGS / "stdout_attempt03.log", LOGS / "stderr_attempt03.log"
RECEIPT = LOGS / "execution_attempt03_launch_receipt.json"

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
        "reviewed_runner_sha256":"b8113bea3887402fb5703c79b29136d5036df73b68a1ccaaf1503016cf28deed",
        "config_sha256":"04993014836b851bf6b7b933287e16fcd21b9ecbc232bbf6936fc2655e115c94",
        "manager_cutoff_utc":"2026-11-04T15:25:00Z","attempt1_exit_code":"unavailable","attempt2_exit_code":1}
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

