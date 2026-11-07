"""Capture actual child exit codes and logs without PowerShell array wrapping."""
import sys,json,subprocess,os
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent
script=P/sys.argv[1];args=sys.argv[2:]
assert script.parent==P and script.suffix=='.py'
started=datetime.now().astimezone().isoformat();stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
log=P/(script.stem+'_'+stamp+'.log')
env=dict(os.environ,PYTHONIOENCODING='utf-8')
with log.open('wb') as f:result=subprocess.run([sys.executable,'-B','-u',str(script),*args],stdout=f,stderr=subprocess.STDOUT,env=env)
receipt=P/'phase_execution.json';history=json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else []
record={'script':script.name,'args':args,'started_at':started,'ended_at':datetime.now().astimezone().isoformat(),'actual_exit_code':result.returncode,'log_path':str(log)}
history.append(record);receipt.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8')
print(log.read_text(encoding='utf-8')[-4500:]);print('ACTUAL_CHILD_EXIT_CODE='+str(result.returncode));sys.exit(result.returncode)
