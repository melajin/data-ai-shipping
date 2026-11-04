"""Bounded acquisition/execution. Manager-owned; only this task's children stopped."""
import argparse, ctypes, hashlib, json, os, pathlib, shutil, subprocess, sys, time
from datetime import datetime, timezone
ROOT=pathlib.Path(__file__).resolve().parents[3]
ROUND=ROOT/'rounds/round_004'
BASE=pathlib.Path('C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
VENV=ROOT/'environments/round_004_tabicl_cpu'
PY=VENV/'Scripts/python.exe'
WHEELS=ROUND/'environment/wheels'
def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x): pathlib.Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def env():
    e=os.environ.copy()
    for k,v in {'TEMP':'temp/round004','TMP':'temp/round004','TMPDIR':'temp/round004','PIP_CACHE_DIR':'cache/pip','HF_HOME':'cache/huggingface','TORCH_HOME':'cache/torch','MPLCONFIGDIR':'cache/matplotlib','XDG_CACHE_HOME':'cache/xdg'}.items():
        p=ROOT/v;p.mkdir(parents=True,exist_ok=True);e[k]=str(p)
    e.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',OMP_NUM_THREADS='3',MKL_NUM_THREADS='3',OPENBLAS_NUM_THREADS='3',NUMEXPR_NUM_THREADS='3',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PIP_DISABLE_PIP_VERSION_CHECK='1')
    return e
def free_ram():
    class M(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(x,ctypes.c_ulonglong) for x in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
    m=M();m.length=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)): raise OSError('Memory probe failed')
    return m.available/1024**3
def run(name,args,seconds,download_guard=False):
    log=ROUND/'logs'/name
    rec={'name':name,'command':list(map(str,args)),'cwd':str(ROOT),'started_utc':now(),'timeout_seconds':seconds,'wrapper_sha256':sha(__file__),'pid':None,'exit_code':None,'timed_out':False}
    t=time.monotonic()
    with open(str(log)+'.stdout.txt','wb') as out,open(str(log)+'.stderr.txt','wb') as err:
        p=subprocess.Popen(list(map(str,args)),cwd=ROOT,env=env(),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        rec['pid']=p.pid;save(str(log)+'.receipt.json',rec)
        peak_observed_bytes=0
        while p.poll() is None:
            exceeded=time.monotonic()-t>seconds
            # Conservative disk guard includes in-flight temp downloads; no pip cache is used.
            used=sum(f.stat().st_size for d in [WHEELS,ROOT/'temp/round004'] for f in d.rglob('*') if f.is_file()) if download_guard else 0
            peak_observed_bytes=max(peak_observed_bytes,used)
            if exceeded or used>1073741824:
                rec['timed_out']=exceeded;rec['download_guard_triggered']=used>1073741824
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=err,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                p.wait();break
            time.sleep(.5)
        if download_guard:
            final_bytes=sum(f.stat().st_size for d in [WHEELS,ROOT/'temp/round004'] for f in d.rglob('*') if f.is_file())
            rec.update(final_observed_download_disk_bytes=final_bytes,peak_observed_download_disk_bytes=max(peak_observed_bytes,final_bytes))
            if final_bytes>1073741824: rec['download_guard_triggered']=True
        elapsed=time.monotonic()-t
        if elapsed>seconds: rec['timed_out']=True
        rec.update(exit_code=p.returncode,elapsed_seconds=elapsed,finished_utc=now())
        save(str(log)+'.receipt.json',rec)
    print(json.dumps(rec),flush=True)
    if rec['exit_code']!=0 or rec.get('timed_out') or rec.get('download_guard_triggered'): raise RuntimeError('Step failed: '+name)
    return rec
def install():
    if VENV.exists(): raise RuntimeError('Environment exists; inspect before resuming, not overwrite')
    WHEELS.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();receipt={'started_utc':now(),'steps':[],'status':'running'}
    save(ROUND/'environment/install.json',receipt)
    def step(name,args,guard=False):
        remaining=900-(time.monotonic()-start)
        if remaining<=0: raise RuntimeError('900 second aggregate limit')
        receipt['steps'].append(run(name,args,remaining,guard));save(ROUND/'environment/install.json',receipt)
    try:
        step('01_venv',[BASE,'-m','venv',VENV])
        step('02_download_torch',[PY,'-m','pip','download','--no-cache-dir','--only-binary=:all:','--dest',WHEELS,'torch==2.6.0','--index-url','https://download.pytorch.org/whl/cpu'],True)
        constraint=ROUND/'configs/pins.txt';constraint.write_text('torch==2.6.0+cpu\nnumpy==2.3.5\nscikit-learn==1.7.2\ntabicl==2.2.0\n',encoding='utf-8')
        step('03_download_tabicl',[PY,'-m','pip','download','--no-cache-dir','--only-binary=:all:','--dest',WHEELS,'--find-links',WHEELS,'-c',constraint,'tabicl==2.2.0','numpy==2.3.5','scikit-learn==1.7.2','--index-url','https://pypi.org/simple'],True)
        wheels=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(WHEELS.glob('*.whl'))]
        save(ROUND/'environment/wheels.json',{'files':wheels,'total_bytes':sum(x['bytes'] for x in wheels)})
        step('04_install_offline',[PY,'-m','pip','install','--no-cache-dir','--no-index','--find-links',WHEELS,'--report',ROUND/'environment/pip_install_report.json','torch==2.6.0+cpu','tabicl==2.2.0','numpy==2.3.5','scikit-learn==1.7.2'])
        step('05_pip_check',[PY,'-m','pip','check'])
        step('06_pip_freeze',[PY,'-m','pip','freeze','--all'])
        receipt['status']='success'
    except Exception as e:
        receipt.update(status='failed',error=repr(e));raise
    finally:
        receipt.update(finished_utc=now(),elapsed_seconds=time.monotonic()-start)
        save(ROUND/'environment/install.json',receipt)
def smoke():
    attempts=list((ROUND/'logs').glob('smoke_*.receipt.json'))
    if len(attempts)>=2: raise RuntimeError('Smoke attempt cap')
    if attempts: raise RuntimeError('Second smoke requires separately documented API correction and reviewed launcher change')
    available=free_ram();save(ROUND/'artifacts/smoke_resource_gate.json',{'utc':now(),'free_ram_gib':available,'minimum':3})
    if available<3: raise RuntimeError('RAM gate <3GiB; no smoke started')
    script=ROUND/'code/probe_tabicl_runtime.py'
    checkpoint=ROOT/'model_cache/tabicl-classifier-v2-20260212.ckpt'
    if sha(checkpoint)!='bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0': raise RuntimeError('Unexpected checkpoint SHA256')
    save(ROUND/'artifacts/smoke_inputs.json',{'code_sha256':sha(script),'checkpoint_sha256':sha(checkpoint),'wrapper_sha256':sha(__file__)})
    run('smoke_01',[PY,script,'--checkpoint',checkpoint,'--output',ROUND/'artifacts/smoke.json'],180)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['install','smoke']);args=parser.parse_args()
    env()
    if args.mode=='install':install()
    else:smoke()
