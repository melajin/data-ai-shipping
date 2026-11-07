"""Single owned stage; bounded runtime, source hashes, and memory evidence."""
import argparse, datetime, hashlib, json, os, subprocess, sys, time
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1]; ROOT=R.parents[1]
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--seconds',type=int,required=True);p.add_argument('--python',default=sys.executable);p.add_argument('--script',default=str(R/'code/run_gate.py'));p.add_argument('args',nargs=argparse.REMAINDER);a=p.parse_args()
assert a.stage.replace('_','').isalnum() and 0<a.seconds<=900
deadline=datetime.datetime.fromisoformat(json.loads((R/'manager/runtime_contract.json').read_text(encoding='utf-8'))['compute_deadline_utc'])
remaining=(deadline-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
assert remaining>0,'Compute cutoff reached'
limit=min(a.seconds,remaining)
log=R/'logs';claim=log/(a.stage+'.claim')
assert not claim.exists(),'Stage already attempted: inspect receipt; no blind retry'
env=os.environ.copy()
for k in ['TEMP','TMP','TMPDIR']:env[k]=str(R/'tmp')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(R/'tmp/pycache'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONUNBUFFERED='1')
extra=a.args[1:] if a.args[:1]==['--'] else a.args
script=Path(a.script).resolve();assert script.is_relative_to(R)
frozen=json.loads((R/'manager/snapshot_s1_gate/freeze.json').read_text(encoding='utf-8'))
for name,expected in frozen['source_hashes'].items():
    path=(ROOT/name).resolve();assert path.is_relative_to(ROOT)
    assert sha(path).lower()==expected.lower(),(name,'Source changed after freeze; do not execute')
argv=[a.python,'-B','-X','utf8',str(script)]+extra
sources=list((R/'code').glob('*.py'))+[R/'configs/experiment.json',R/'ROUND_PLAN.md',R/'manager/runtime_contract.json',Path(__file__).resolve()]
hashes={str(x.relative_to(ROOT)).replace('\\','/'):sha(x) for x in sources}
memory=psutil.virtual_memory();other=[]
# Windows venv python.exe is a bootstrap parent with the identical argv,
# not an independent computation. Exclude only that verified direct parent.
own_python_pids={os.getpid()}
parent=psutil.Process().parent()
if parent and 'python' in parent.name().lower() and parent.cmdline()==psutil.Process().cmdline():
    own_python_pids.add(parent.pid)
for proc in psutil.process_iter(['pid','name','cmdline','memory_info','create_time']):
    try:
        d=proc.info
        if d['pid'] not in own_python_pids and 'python' in (d['name'] or '').lower():
            other.append(dict(pid=d['pid'],cmdline=d['cmdline'],rss=d['memory_info'].rss,create_time=d['create_time']))
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
prior_seconds=sum(json.loads(x.read_text(encoding='utf-8'))['wall_seconds'] for x in log.glob('*_receipt.json'))
limit=min(limit,1800-prior_seconds);assert limit>0,'Compute budget exhausted'
pre=dict(utc=utc(),stage=a.stage,argv=argv,hashes=hashes,available_bytes=memory.available,expected_peak_bytes=int(0.5*2**30),estimate_basis='FIT3144 x304 float32 ~3.65MiB; candidate +24 ~0.29MiB; T5 closure released before S1; monthly sparse maps released; single-thread models released per fit. Expected0.5GiB is an estimate, not a measured full-run peak; hard owned RSS cap0.75GiB.',other_python=other,timeout_seconds=limit,compute_cutoff=deadline.isoformat(),prior_compute_seconds=prior_seconds)
save(log/(a.stage+'_preflight.json'),pre)
if memory.available<float(json.loads((R/'manager/runtime_contract.json').read_text(encoding='utf-8'))['minimum_entry_available_gib'])*2**30:raise RuntimeError('Entry RAM gate: defer before claim/job; do independent work then recheck')
if other:raise RuntimeError('Other Python process present: defer to preserve single-compute concurrency; do not terminate user processes')
claim.open('x').write(utc())
start=time.monotonic();stdout=log/(a.stage+'.stdout.txt');stderr=log/(a.stage+'.stderr.txt');stop=None;peak=0;minfree=memory.available;samples=0
with stdout.open('w',encoding='utf-8') as out,stderr.open('w',encoding='utf-8') as err:
    child=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0x00004000))
    owner=psutil.Process(child.pid)
    save(log/(a.stage+'_started.json'),dict(utc=utc(),pid=child.pid,launcher_pid=os.getpid(),argv=argv))
    while child.poll() is None:
        # Runtime safety sampling while owned job works, not polling to await RAM.
        try: family=[owner]+owner.children(recursive=True)
        except psutil.NoSuchProcess:family=[]
        rss=0
        for proc in family:
            try:rss+=proc.memory_info().rss
            except psutil.NoSuchProcess:pass
        free=psutil.virtual_memory().available;peak=max(peak,rss);minfree=min(minfree,free);samples+=1
        if rss>0.75*2**30 or free<.5*2**30:stop='memory_stop'
        elif time.monotonic()-start>limit:stop='deadline_stop'
        if stop:
            for proc in reversed(family):
                try:proc.kill()
                except psutil.NoSuchProcess:pass
            child.wait(timeout=10);break
        try:child.wait(timeout=1)
        except subprocess.TimeoutExpired:pass
    rc=child.wait(timeout=10)
# Only the owned preparation stage can create these temporary aggregate keys.
# Remove them after success, exception, deadline or owned-child memory stop.
cleanup=[]
if a.stage=='prepare_t5':
    for suffix in ('','-journal','-wal','-shm'):
        target=(R/'tmp'/('harbor_distinct.sqlite'+suffix)).resolve()
        assert target.parent==(R/'tmp').resolve()
        if target.exists():
            target.unlink();cleanup.append(str(target.relative_to(ROOT)))
receipt=dict(started_at_utc=pre['utc'],finished_at_utc=utc(),stage=a.stage,pid=child.pid,launcher_pid=os.getpid(),argv=argv,exit_code=rc,stop_reason=stop,wall_seconds=time.monotonic()-start,sampled_peak_family_rss_bytes=peak,sampled_min_available_bytes=minfree,memory_sample_count=samples,stdout=str(stdout),stderr=str(stderr),hashes_before=hashes,hashes_after={n:sha(ROOT/n) for n in hashes},owned_temporary_files_removed=cleanup,hardware_verified=False)
save(log/(a.stage+'_receipt.json'),receipt);print(json.dumps(receipt));sys.exit(rc if not stop else 2)
