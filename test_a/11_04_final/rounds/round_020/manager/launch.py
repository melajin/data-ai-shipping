"""Small owned-process launcher: bounded run, log capture, sampled memory guard."""
import argparse,datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1]; ROOT=R.parents[1]
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=argparse.ArgumentParser();p.add_argument('--mode',choices=['prepare','run'],required=True);a=p.parse_args()
mode=a.mode; log=R/'logs'; stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
compute_deadline=datetime.datetime(2026,11,4,23,58,9,tzinfo=datetime.timezone.utc)
limit=min(600 if mode=='run' else 120,(compute_deadline-datetime.datetime.now(datetime.timezone.utc)).total_seconds())
if limit<=0:raise RuntimeError('Manager compute cutoff reached; preserve final five minutes')
claim=log/f'{mode}.claim'
if claim.exists():raise RuntimeError('Existing execution claim; inspect receipt, never blindly repeat')
env=os.environ.copy()
for k in ['TEMP','TMP','TMPDIR']:env[k]=str(R/'tmp')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(R/'tmp/pycache'),OMP_NUM_THREADS='3',OPENBLAS_NUM_THREADS='3',MKL_NUM_THREADS='3',NUMEXPR_NUM_THREADS='3')
runner=R/'code/run_performance.py';config=R/'configs/experiment.json'
argv=[sys.executable,'-B','-X','utf8',str(runner),'--config',str(config),'--'+mode]
hashes={str(x.relative_to(ROOT)):sha(x) for x in [runner,config,R/'ROUND_PLAN.md',R/'manager/ROUND021_FIXED_BRANCH.md',R/'manager/USER_PROTECTION_AMENDMENT.md']}
if mode=='run':
    approval=json.loads((R/'review/approved_sources.json').read_text(encoding='utf-8-sig'))
    freeze=json.loads((R/'manager/execution_freeze.json').read_text(encoding='utf-8-sig'))
    assert approval['approved'] is True,'Independent review not approved'
    for source in [runner,config,Path(__file__).resolve()]:
        name=str(source.relative_to(ROOT)).replace('\\','/')
        assert approval['hashes'][name]==sha(source),'Independent approval hash mismatch: '+name
    assert freeze['hashes']==hashes,'Frozen source/config/plan changed'
    assert freeze['review_approved'] is True
memory=psutil.virtual_memory(); other=[]
for proc in psutil.process_iter(['pid','name','cmdline','memory_info','create_time']):
    try:
        d=proc.info
        if d['pid']!=os.getpid() and 'python' in (d['name'] or '').lower():
            other.append({'pid':d['pid'],'cmdline':d['cmdline'],'rss':d['memory_info'].rss,'create_time':d['create_time']})
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
pre=dict(utc=utc(),mode=mode,argv=argv,hashes=hashes,available_bytes=memory.available,expected_peak_bytes=2**30,estimate_basis='~10000x12 numeric values plus sklearn/library reserve',other_python=other,timeout_seconds=limit,manager_compute_cutoff_utc=compute_deadline.isoformat())
save(log/f'{mode}_preflight.json',pre)
if memory.available<2*2**30:raise RuntimeError('Insufficient start RAM; no child process started')
claim.open('x').write(utc())
start=time.monotonic(); stdout=log/f'{mode}_{stamp}.stdout.txt';stderr=log/f'{mode}_{stamp}.stderr.txt'; stop=None;peak=0;minfree=memory.available;samples=0
with stdout.open('w',encoding='utf-8') as out,stderr.open('w',encoding='utf-8') as err:
    child=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    owned=psutil.Process(child.pid)
    save(log/f'{mode}_started.json',dict(utc=utc(),pid=child.pid,launcher_pid=os.getpid(),argv=argv))
    while child.poll() is None:
        # Runtime safety sampling, never a loop waiting for RAM to become available.
        try:rss=owned.memory_info().rss
        except psutil.NoSuchProcess:rss=0
        free=psutil.virtual_memory().available;peak=max(peak,rss);minfree=min(minfree,free);samples+=1
        if rss>2**30 or free<.5*2**30:stop='memory_stop'
        elif time.monotonic()-start>limit:stop='deadline_stop'
        if stop:child.kill();child.wait(timeout=10);break
        try:child.wait(timeout=1)
        except subprocess.TimeoutExpired:pass
    rc=child.wait(timeout=10)
receipt=dict(started_at_utc=pre['utc'],finished_at_utc=utc(),mode=mode,pid=child.pid,launcher_pid=os.getpid(),argv=argv,exit_code=rc,stop_reason=stop,wall_seconds=time.monotonic()-start,sampled_peak_rss_bytes=peak,sampled_min_available_bytes=minfree,memory_sample_count=samples,stdout=str(stdout),stderr=str(stderr),hashes_before=hashes,hashes_after={n:sha(ROOT/n) for n in hashes},hardware_verified=False)
save(log/f'{mode}_receipt.json',receipt);print(json.dumps(receipt));sys.exit(rc if not stop else 2)
