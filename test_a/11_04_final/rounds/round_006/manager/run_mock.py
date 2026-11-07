"""Bounded pure-standard-library diagnostic test, without model imports."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / 'rounds' / 'round_006'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pilot-sha', required=True)
    ap.add_argument('--test-sha', required=True)
    a = ap.parse_args()
    pilot = ROUND / 'code' / 'replay_inner_pilot.py'
    test = ROUND / 'code' / 'test_validate_resolved_inference_state.py'
    assert sha(pilot) == a.pilot_sha.lower(), 'pilot source changed'
    assert sha(test) == a.test_sha.lower(), 'test source changed'
    run = ROUND / 'logs' / 'mock_01'
    run.mkdir(exist_ok=False)
    src = run / 'source'
    src.mkdir()
    for path in (pilot, test):
        shutil.copy2(path, src / path.name)
        assert sha(src / path.name) == sha(path)
    env = os.environ.copy()
    temp = ROUND / 'temp' / 'mock_01'
    temp.mkdir(exist_ok=False)
    for key in ('TEMP', 'TMP', 'TMPDIR', 'PYTHONPYCACHEPREFIX'):
        env[key] = str(temp)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    # The pure stdlib test needs no venv packages. Direct base Python avoids
    # the Windows venv launcher process, so timeout kills the sole child.
    command = [sys._base_executable, '-B', str(src / test.name), '-v']
    record = {'started_utc': datetime.now(timezone.utc).isoformat(),
              'command': command, 'source_sha256': sha(pilot),
              'test_sha256': sha(test), 'timeout_seconds': 30,
              'model_imports': False, 'checkpoint_loads': 0,
              'scope': 'diagnostic fake objects, not model inference'}
    t0 = time.monotonic()
    with (run / 'stdout.txt').open('wb') as out, (run / 'stderr.txt').open('wb') as err:
        try:
            p = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=err,
                               timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            record.update(exit_code=p.returncode, status='PASS' if p.returncode == 0 else 'FAIL')
        except subprocess.TimeoutExpired:
            record.update(exit_code=None, status='TIMEOUT')
    record.update(elapsed_seconds=time.monotonic()-t0,
                  finished_utc=datetime.now(timezone.utc).isoformat())
    (run / 'receipt.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record))
    return 0 if record['status']=='PASS' else 1

if __name__ == '__main__':
    sys.exit(main())
