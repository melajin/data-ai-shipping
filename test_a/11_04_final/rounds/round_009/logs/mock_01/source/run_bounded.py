"""Round009 bounded synthetic-pair/pure-mock execution receipts; standard library only."""
import argparse
import csv
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / 'rounds' / 'round_009'
K = c.WinDLL('kernel32', use_last_error=True)
P = c.WinDLL('psapi', use_last_error=True)

class Memory(c.Structure):
    _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [(n, c.c_ulonglong) for n in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]

class ProcessEntry(c.Structure):
    _fields_ = [('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),('module',w.DWORD),('threads',w.DWORD),('ppid',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]

class Counters(c.Structure):
    _fields_ = [('cb',w.DWORD),('faults',w.DWORD)] + [(n,c.c_size_t) for n in ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]

K.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]; K.CreateToolhelp32Snapshot.restype=w.HANDLE
K.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(ProcessEntry)]; K.Process32NextW.argtypes=[w.HANDLE,c.POINTER(ProcessEntry)]
K.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; K.OpenProcess.restype=w.HANDLE
K.CloseHandle.argtypes=[w.HANDLE]
K.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]; K.WaitForSingleObject.restype=w.DWORD
P.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Counters),w.DWORD]
K.GetProcessTimes.argtypes=[w.HANDLE,c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME)]

def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
    tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(tmp,p)
def ram():
    m=Memory(); m.length=c.sizeof(m)
    if not K.GlobalMemoryStatusEx(c.byref(m)): raise c.WinError(c.get_last_error())
    return m.avail_phys / 2**30
def process_map():
    h=K.CreateToolhelp32Snapshot(2,0)
    if h == c.c_void_p(-1).value: raise c.WinError(c.get_last_error())
    result={}; e=ProcessEntry();e.size=c.sizeof(e)
    try:
        ok=K.Process32FirstW(h,c.byref(e))
        while ok:
            result[int(e.pid)]=int(e.ppid);ok=K.Process32NextW(h,c.byref(e))
    finally: K.CloseHandle(h)
    return result
def tree(root):
    mapping=process_map(); ids={root}; changed=True
    while changed:
        new={pid for pid,parent in mapping.items() if parent in ids}; changed=not new.issubset(ids);ids|=new
    return sorted(ids & mapping.keys())

def identity_from_handle(handle,pid):
    wait_state=K.WaitForSingleObject(handle,0)
    if wait_state==0xFFFFFFFF:return None
    a,b,k,u=w.FILETIME(),w.FILETIME(),w.FILETIME(),w.FILETIME()
    if not K.GetProcessTimes(handle,c.byref(a),c.byref(b),c.byref(k),c.byref(u)):return None
    return {'pid':pid,'creation_ticks':(a.dwHighDateTime<<32)+a.dwLowDateTime,
            'running':wait_state==258}

def terminate_popen_handle(proc,deadline):
    requested=False; error=None
    try:
        if proc.poll() is None:
            proc.terminate();requested=True
    except OSError as exc:error=repr(exc)
    remaining=deadline-time.monotonic()
    if proc.poll() is None and remaining>0:
        try:proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:error=error or 'Popen handle wait exceeded cleanup deadline'
    return {'terminate_requested':requested,'root_exit_confirmed':proc.poll() is not None,'error':error}

def counters(pid):
    h=K.OpenProcess(0x0400|0x0010|0x00100000,False,pid)
    if not h: return None
    try:
        wait_state=K.WaitForSingleObject(h,0)
        if wait_state==0xFFFFFFFF: raise c.WinError(c.get_last_error())
        running=wait_state==258
        a,b,k,u=w.FILETIME(),w.FILETIME(),w.FILETIME(),w.FILETIME()
        cpu=None
        if not K.GetProcessTimes(h,c.byref(a),c.byref(b),c.byref(k),c.byref(u)):return None
        cpu=((k.dwHighDateTime<<32)+k.dwLowDateTime+(u.dwHighDateTime<<32)+u.dwLowDateTime)/1e7
        m=Counters();m.cb=c.sizeof(m)
        memory_ok=bool(P.GetProcessMemoryInfo(h,c.byref(m),c.sizeof(m)))
        return {'pid':pid,'creation_ticks':(a.dwHighDateTime<<32)+a.dwLowDateTime,'running':running,
                'working_set_bytes':m.ws if memory_ok else None,
                'peak_working_set_bytes':m.peak_ws if memory_ok else None,
                'private_bytes':m.private if memory_ok else None,'memory_sampled':memory_ok,'cpu_seconds':cpu}
    finally:K.CloseHandle(h)

def owned_alive(identities):
    return [pid for pid,ticks in identities.items() if (s:=counters(pid)) and s['creation_ticks']==ticks and ticks>0 and s['running']]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['mock','synthetic_pair'],required=True);ap.add_argument('--run-id',required=True);ap.add_argument('--script',type=Path);ap.add_argument('args',nargs=argparse.REMAINDER);a=ap.parse_args()
    if not a.run_id.replace('_','').isalnum():raise ValueError('invalid run id')
    if a.kind=='synthetic_pair' and a.run_id!='pair_01':raise ValueError('the single synthetic-pair run id is pair_01')
    if a.kind=='mock' and a.run_id not in ('mock_01','mock_02'):raise ValueError('pure mock run id must be mock_01 or mock_02')
    default_script=ROUND/'code'/('test_row_chunk.py' if a.kind=='mock' else 'synthetic_pair.py')
    script=(a.script or default_script).resolve()
    if not script.is_relative_to(ROUND) or not script.is_file():raise ValueError('script outside this round')
    expected_script=default_script.resolve()
    if script != expected_script:raise ValueError('script does not match the fixed script for this run kind')
    limit=180 if a.kind=='synthetic_pair' else 30
    cleanup_seconds=10 if a.kind=='synthetic_pair' else 2
    compute_limit=limit-cleanup_seconds
    approved=json.loads((ROUND/'review'/'approved_sources.json').read_text(encoding='utf-8-sig'))
    if approved.get('schema')!='round009_approved_sources.v1':raise ValueError('unexpected round009 source manifest schema')
    if not isinstance(approved.get('sha256'),dict):raise ValueError('source manifest has no SHA-256 map')
    for name, expected in approved['sha256'].items():
        if sha(ROOT/name)!=expected: raise ValueError('Approved source hash changed: '+name)
    if str(script.relative_to(ROOT)).replace('\\','/') not in approved['sha256']: raise ValueError('Unapproved script')
    run=ROUND/'logs'/a.run_id;run.mkdir(parents=True,exist_ok=False)
    receipt={'schema':'round009_bounded_receipt.v1','kind':a.kind,'run_id':a.run_id,'started_utc':now(),'status':'preparing','timeout_seconds':limit,'compute_timeout_seconds':compute_limit,'cleanup_max_seconds':cleanup_seconds,'script':str(script),'source_sha256':sha(script),'wrapper_sha256':sha(__file__),'pid':None,'exit_code':None,'launched':False,'stop_reason':None}
    source=run/'source';source.mkdir()
    for name, expected in approved['sha256'].items():
        original=ROOT/name
        if original.parent == ROUND/'code' and original.suffix == '.py':
            shutil.copy2(original,source/original.name)
            if sha(source/original.name)!=expected: raise ValueError('Snapshot hash mismatch')
    adapter_names=('rounds/round_009/code/column_chunk.py','rounds/round_009/code/row_chunk.py')
    adapter_expected={name:approved['sha256'].get(name) for name in adapter_names}
    if any(value is None for value in adapter_expected.values()):
        raise ValueError('Approved source manifest must include column_chunk.py and row_chunk.py')
    if any(sha(source/Path(name).name)!=expected for name,expected in adapter_expected.items()):
        raise ValueError('Approved adapter source snapshot hash mismatch')
    script_key=str(script.relative_to(ROOT)).replace('\\','/')
    snapshot=source/script.name
    if script_key not in approved['sha256'] or sha(snapshot)!=approved['sha256'][script_key]:
        raise ValueError('Approved script snapshot is missing or has a SHA mismatch')
    shutil.copy2(__file__,source/'run_bounded.py')
    receipt['approved_sources']=approved
    receipt['source_snapshot']={name:str(source/Path(name).name) for name in approved['sha256']
                                if name.startswith('rounds/round_009/code/') and Path(name).suffix=='.py'}
    receipt_path=run/'receipt.json';save(receipt_path,receipt)
    env=os.environ.copy();cache=ROUND/'temp'/a.run_id;cache.mkdir(parents=True,exist_ok=False)
    for key in ['TEMP','TMP','TMPDIR','PYTHONPYCACHEPREFIX','HF_HOME','TORCH_HOME','XDG_CACHE_HOME','JOBLIB_TEMP_FOLDER','MPLCONFIGDIR']:env[key]=str(cache)
    for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:env[key]='3'
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    childargs=a.args[1:] if a.args[:1]==['--'] else a.args
    if sha(snapshot)!=receipt['source_sha256']:raise ValueError('source changed while copying snapshot')
    receipt['executed_source_snapshot']=str(snapshot)
    cmd=[str(ROOT/'environments'/'round_004_tabicl_cpu'/'Scripts'/'python.exe'),'-B',str(snapshot),*childargs]
    receipt['command']=cmd;receipt['environment_overrides']={k:env[k] for k in env if k in ['TEMP','TMP','TMPDIR','PYTHONPYCACHEPREFIX','HF_HOME','TORCH_HOME','XDG_CACHE_HOME','JOBLIB_TEMP_FOLDER','MPLCONFIGDIR','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS','PYTHONDONTWRITEBYTECODE','PYTHONUTF8','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE']}
    minimum=3.0 if a.kind=='synthetic_pair' else 1.5
    free=ram();receipt['preflight_available_ram_gib']=free;receipt['minimum_start_ram_gib']=minimum
    if free<minimum:
        receipt.update(status='not_launched_ram_gate',finished_utc=now());save(receipt_path,receipt);print(json.dumps(receipt));return 3
    if a.kind=='synthetic_pair':
        passed_mock=None
        for mock_id in ('mock_02','mock_01'):
            prior_path=ROUND/'logs'/mock_id/'receipt.json'
            if not prior_path.is_file():continue
            try: prior=json.loads(prior_path.read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):continue
            prior_approved=prior.get('approved_sources',{})
            if (prior.get('kind')=='mock' and prior.get('status')=='completed'
                    and prior.get('exit_code')==0 and prior.get('stop_reason') is None
                    and prior.get('owned_tree_remaining')==[]
                    and prior.get('source_unchanged') is True
                    and prior.get('source_snapshot_unchanged') is True
                    and prior.get('wrapper_sha256')==sha(__file__)
                    and prior_approved.get('sha256')==approved.get('sha256')):
                passed_mock=mock_id;break
        if passed_mock is None:
            receipt.update(status='not_launched_mock_gate',finished_utc=now(),
                           mock_gate='no completed pure mock for the exact approved source set')
            save(receipt_path,receipt);print(json.dumps(receipt));return 6
        receipt['passed_mock_run_id']=passed_mock
        claim_path=ROUND/'manager'/'synthetic_pair.claim'
        try:
            with claim_path.open('x',encoding='utf-8') as f:f.write(json.dumps({'claimed_utc':now(),'run_id':a.run_id,'script_sha256':receipt['source_sha256']})+'\n')
        except FileExistsError:
            receipt.update(status='not_launched_synthetic_pair_already_claimed',finished_utc=now(),synthetic_pair_claim=str(claim_path));save(receipt_path,receipt);print(json.dumps(receipt));return 5
        receipt['synthetic_pair_claim']=str(claim_path);save(receipt_path,receipt)
    else:
        claim_path=ROUND/'manager'/f'{a.run_id}.claim'
        if a.run_id=='mock_02' and not (ROUND/'manager'/'mock_01.claim').is_file():
            receipt.update(status='not_launched_mock_retry_requires_mock_01',finished_utc=now());save(receipt_path,receipt);print(json.dumps(receipt));return 5
        try:
            with claim_path.open('x',encoding='utf-8') as f:f.write(json.dumps({'claimed_utc':now(),'run_id':a.run_id,'script_sha256':receipt['source_sha256']})+'\n')
        except FileExistsError:
            receipt.update(status='not_launched_mock_attempt_already_claimed',finished_utc=now(),mock_attempt_claim=str(claim_path));save(receipt_path,receipt);print(json.dumps(receipt));return 5
        receipt['mock_attempt_claim']=str(claim_path);save(receipt_path,receipt)
    proc=None;t0=time.monotonic();cpu_max={};peak_ws={};peak_tree=0;min_ram=free;observed=set();identities={}
    uninspectable_pids=set();resource_sampling_complete=True
    try:
        with (run/'stdout.txt').open('wb') as out,(run/'stderr.txt').open('wb') as err,(run/'resource_curve.csv').open('w',newline='',encoding='utf-8') as curve:
            writer=csv.DictWriter(curve,fieldnames=['elapsed_seconds','available_ram_gib','tree_working_set_bytes','processes']);writer.writeheader();curve.flush()
            t0=time.monotonic();receipt['process_creation_started_utc']=now()
            proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            root_stats=counters(proc.pid)
            if root_stats is None:
                try: root_identity=identity_from_handle(w.HANDLE(int(proc._handle)),proc.pid)
                except (AttributeError,TypeError,ValueError,OSError): root_identity=None
                if root_identity is None:
                    receipt.update(pid=proc.pid,launched=True,root_identity_capture_failed=True,
                                   root_identity_capture_method='Popen process handle fallback failed')
                    deadline=min(t0+limit,time.monotonic()+cleanup_seconds)
                    receipt['popen_handle_fallback']=terminate_popen_handle(proc,deadline)
                    receipt.update(status='root_identity_capture_failed',
                                   owned_tree_status='unverified_after_root_identity_failure',
                                   owned_tree_remaining={'root_exit_confirmed':receipt['popen_handle_fallback']['root_exit_confirmed'],
                                                         'unverified_descendants':'unknown'},
                                   finished_utc=now(),elapsed_seconds=time.monotonic()-t0)
                    save(receipt_path,receipt);print(json.dumps(receipt,ensure_ascii=False));return 7
                root_stats={**root_identity,'working_set_bytes':None,'peak_working_set_bytes':None,
                            'private_bytes':None,'memory_sampled':False,'cpu_seconds':None}
                receipt['root_resource_counters_unavailable']=True
                resource_sampling_complete=False
            identities[proc.pid]=root_stats['creation_ticks'];observed.add(proc.pid)
            cpu_max[str(proc.pid)]=root_stats['cpu_seconds'] or 0
            if root_stats['peak_working_set_bytes'] is not None:peak_ws[str(proc.pid)]=root_stats['peak_working_set_bytes']
            receipt.update(pid=proc.pid,launched=True,status='running');save(receipt_path,receipt)
            while True:
                elapsed=time.monotonic()-t0;free=ram();min_ram=min(min_ram,free)
                ids=tree(proc.pid);observed.update(ids);stats=[]
                for pid in ids:
                    sample=counters(pid)
                    if sample is None:
                        if pid==proc.pid and pid in identities:
                            resource_sampling_complete=False
                            stats.append({'pid':pid,'creation_ticks':identities[pid],'running':proc.poll() is None,
                                          'working_set_bytes':None,'peak_working_set_bytes':None,
                                          'private_bytes':None,'memory_sampled':False,'cpu_seconds':None})
                            continue
                        uninspectable_pids.add(pid)
                        resource_sampling_complete=False
                        continue
                    stats.append(sample)
                    if not sample['memory_sampled']:resource_sampling_complete=False
                if uninspectable_pids:receipt['uninspectable_tree_pids']=sorted(uninspectable_pids)
                total=sum(s['working_set_bytes'] or 0 for s in stats)
                if stats and all(s['memory_sampled'] for s in stats):peak_tree=max(peak_tree,total)
                for s in stats:
                    identities[s['pid']]=s['creation_ticks']
                    pid=str(s['pid']);cpu_max[pid]=max(cpu_max.get(pid,0),s['cpu_seconds'] or 0)
                    if s['peak_working_set_bytes'] is not None:peak_ws[pid]=max(peak_ws.get(pid,0),s['peak_working_set_bytes'])
                writer.writerow({'elapsed_seconds':elapsed,'available_ram_gib':free,'tree_working_set_bytes':total,'processes':json.dumps(stats,separators=(',',':'))});curve.flush()
                rc=proc.poll()
                descendants=[pid for pid in owned_alive(identities) if pid!=proc.pid]
                if rc is not None and not descendants:break
                reason='timeout' if elapsed>=compute_limit else ('available_ram_below_1_5_gib' if free<1.5 else None)
                if reason:
                    receipt['stop_reason']=reason;save(receipt_path,receipt)
                    receipt['termination_requested_utc']=now()
                    cleanup_deadline=min(t0+limit,time.monotonic()+cleanup_seconds)
                    targets=[proc.pid] if rc is None else descendants
                    for target in targets:
                        if target not in owned_alive(identities): continue
                        remaining_seconds=cleanup_deadline-time.monotonic()
                        if remaining_seconds<=0: break
                        killed=subprocess.run(['taskkill','/PID',str(target),'/T','/F'],capture_output=True,timeout=remaining_seconds,creationflags=subprocess.CREATE_NO_WINDOW)
                        (run/f'termination_{target}.stdout.txt').write_bytes(killed.stdout);(run/f'termination_{target}.stderr.txt').write_bytes(killed.stderr)
                        receipt.setdefault('termination_exit_codes',{})[str(target)]=killed.returncode
                    while owned_alive(identities) and time.monotonic()<cleanup_deadline:
                        time.sleep(min(.1,max(0,cleanup_deadline-time.monotonic())))
                    proc.poll()
                    receipt['termination_checked_utc']=now()
                    receipt['termination_confirmed']=not owned_alive(identities) and not uninspectable_pids
                    break
                time.sleep(min(.25,max(.01,compute_limit-elapsed)))
            receipt['exit_code']=proc.returncode
        elapsed=time.monotonic()-t0
        remaining=owned_alive(identities)
        source_unchanged=sha(script)==receipt['source_sha256']
        adapter_source_unchanged=all(sha(ROOT/name)==expected for name,expected in adapter_expected.items())
        source_snapshot_unchanged=sha(snapshot)==receipt['source_sha256'] and all(
            sha(source/Path(name).name)==expected for name,expected in adapter_expected.items())
        completed=bool(proc.returncode==0 and not receipt['stop_reason'] and elapsed<=limit and not remaining
                      and not uninspectable_pids and source_unchanged and adapter_source_unchanged and source_snapshot_unchanged)
        receipt.update(status='completed' if completed else 'failed_or_stopped',elapsed_seconds=elapsed,finished_utc=now(),postexit_within_timeout=elapsed<=limit,minimum_observed_available_ram_gib=min_ram,peak_sampled_tree_working_set_bytes=peak_tree,process_peak_working_set_bytes=peak_ws,sampled_cpu_seconds_by_pid=cpu_max,observed_owned_pids=sorted(observed),owned_process_creation_ticks=identities,owned_tree_remaining=remaining,source_unchanged=source_unchanged,adapter_source_unchanged=adapter_source_unchanged,source_snapshot_unchanged=source_snapshot_unchanged)
        receipt['uninspectable_tree_pids']=sorted(uninspectable_pids)
        receipt['resource_sampling_complete']=resource_sampling_complete
        receipt['owned_tree_status']='unverified_uninspectable_pids' if uninspectable_pids else ('clear' if not remaining else 'verified_owned_processes_remaining')
        save(receipt_path,receipt);print(json.dumps(receipt,ensure_ascii=False));return 0 if receipt['status']=='completed' else 4
    except BaseException as e:
        if proc:
            receipt['exception_cleanup_started_utc']=now()
            cleanup_deadline=min(t0+limit,time.monotonic()+cleanup_seconds)
            alive_owned=owned_alive(identities)
            if proc.poll() is None and proc.pid not in alive_owned:
                receipt['root_identity_capture_failed']=True
                receipt['popen_handle_fallback']=terminate_popen_handle(proc,cleanup_deadline)
            for target in alive_owned:
                if target==proc.pid and receipt.get('popen_handle_fallback'):continue
                remaining_seconds=cleanup_deadline-time.monotonic()
                if remaining_seconds<=0: break
                try:
                    killed=subprocess.run(['taskkill','/PID',str(target),'/T','/F'],capture_output=True,timeout=remaining_seconds,creationflags=subprocess.CREATE_NO_WINDOW)
                    (run/f'exception_termination_{target}.stdout.txt').write_bytes(killed.stdout)
                    (run/f'exception_termination_{target}.stderr.txt').write_bytes(killed.stderr)
                except subprocess.TimeoutExpired: break
            while owned_alive(identities) and time.monotonic()<cleanup_deadline:
                time.sleep(min(.1,max(0,cleanup_deadline-time.monotonic())))
            proc.poll()
            verified_remaining=owned_alive(identities)
            receipt['uninspectable_tree_pids']=sorted(uninspectable_pids)
            if receipt.get('root_identity_capture_failed'):
                receipt['owned_tree_status']='unverified_after_root_identity_failure'
                receipt['owned_tree_remaining']={'verified_owned_pids':verified_remaining,
                                                 'root_exit_confirmed':proc.poll() is not None,
                                                 'unverified_descendants':'unknown'}
            elif uninspectable_pids:
                receipt['owned_tree_status']='unverified_uninspectable_pids'
                receipt['owned_tree_remaining']={'verified_owned_pids':verified_remaining,
                                                 'uninspectable_pids':sorted(uninspectable_pids)}
            else:
                receipt['owned_tree_status']='clear' if not verified_remaining else 'verified_owned_processes_remaining'
                receipt['owned_tree_remaining']=verified_remaining
            receipt['termination_confirmed']=bool(
                not verified_remaining and not uninspectable_pids and not receipt.get('root_identity_capture_failed'))
            receipt['termination_checked_utc']=now()
        receipt.update(status='wrapper_error',error=repr(e),finished_utc=now(),elapsed_seconds=time.monotonic()-t0,exit_code=proc.returncode if proc else None);save(receipt_path,receipt);raise

if __name__=='__main__':sys.exit(main())
