# -*- coding: utf-8 -*-
"""Round013 ?6 only: fixed per-vessel argmin selection and rank confidence."""
from __future__ import annotations
import csv, hashlib, json, math, sys, time, ctypes, platform
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
R8=ROOT/'testB/round_008_linkage_audit_20261105'
R11=ROOT/'testB/round_011_20261105'
R12=ROOT/'testB/round_012_20261105'
TRACKS=[R8/'dev_hourly_scores.parquet',R8/'additional_hourly_scores.parquet']
EVENTS=R8/'devset_positives.csv'
G4=HERE/'g4_voyage_local_collapse.csv'
G5=HERE/'g5_confound_summary.json'
BATCH=65536
WINDOWS=(3,7)


def utc_now(): return datetime.now().astimezone().isoformat(timespec='seconds')

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def source_manifest():
    paths=[*TRACKS,EVENTS,G4,G5,ROOT/'AGENTS.md',ROOT/'.codex/agents/luna_worker.toml',
           R11/'PROTOCOL.md',R12/'g_gate_v2.py',HERE/'PROTOCOL.md',HERE/'SUPERVISOR_TASK_01.md',HERE/'SUPERVISOR_TASK_02.md',
           HERE/'run_round013.py',HERE/'g6_selection_and_confidence.py']
    return {str(x.relative_to(ROOT)):{'bytes':x.stat().st_size,'sha256':sha(x)} for x in paths}

def ram_snapshot(stage,peak=250):
    class M(ctypes.Structure):
        _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),
        ('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
        ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
    m=M();m.dwLength=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)): raise OSError('GlobalMemoryStatusEx failed')
    procs=[]
    try:
        import psutil
        for p in psutil.process_iter(['pid','name','memory_info']):
            try:
                x=p.info;procs.append({'pid':x['pid'],'name':x['name'],'working_set_mib':round(x['memory_info'].rss/1048576,1)})
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    except ImportError: procs=[{'note':'psutil unavailable'}]
    return {'stage':stage,'checked_at':datetime.now().astimezone().isoformat(timespec='seconds'),
            'available_ram_mib':round(m.ullAvailPhys/1048576,1),'total_ram_mib':round(m.ullTotalPhys/1048576,1),
            'estimated_additional_peak_mib':peak,
            'peak_estimate_basis':'Arrow 65,536-row batches reading ID/ts only; at most 145,427 small input pairs (approx. 20 MiB Python tuples+hash map), sorted unique rows (approx. 20 MiB), event/voyage tables <10 MiB and imports/buffers <150 MiB; conservative 250 MiB; one process.',
            'processes':procs}

def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def write_csv(path,rows,columns=None):
    rows=list(rows)
    if columns is None: columns=list(rows[0]) if rows else []
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)

def finite_score(x):
    if x is None or str(x).strip()=='': return None
    try: y=float(x)
    except (ValueError,TypeError): return None
    return y if math.isfinite(y) else None

def load_track_id_ts(target_ids):
    rows=[]; sequence=0; source_counts={}
    for path in TRACKS:
        pf=pq.ParquetFile(path); matched=0
        for batch in pf.iter_batches(batch_size=BATCH,columns=['rfid_id_int','ts']):
            ids=batch.column('rfid_id_int').to_pylist();ts=batch.column('ts').to_pylist()
            for i,(vid,t) in enumerate(zip(ids,ts)):
                key=str(int(vid))
                if key in target_ids:
                    if t is None or int(t)!=t: raise ValueError(f'noninteger ts for {key}: {t}')
                    rows.append((key,int(t),sequence+i,path.name));matched+=1
            sequence+=len(ids)
        source_counts[path.name]={'row_groups':pf.metadata.num_row_groups,'rows_total':pf.metadata.num_rows,'rows_target':matched}
    return rows,source_counts

def split_dedup(rows):
    first={};duplicate_extra=0
    for vid,t,order,source in rows:
        k=(vid,t)
        if k in first: duplicate_extra+=1
        else:first[k]=(vid,t,order,source)
    by=defaultdict(list)
    for rec in first.values(): by[rec[0]].append(rec)
    voyages=[]; vessel_raw_counts={}
    for vid in sorted(by):
        seq=sorted(by[vid],key=lambda r:(r[1],r[2]))
        groups=[];current=[]
        for r in seq:
            if current and r[1]-current[-1][1]>=6: groups.append(current);current=[]
            current.append(r)
        if current:groups.append(current)
        vessel_raw_counts[vid]=len(groups)
        for no,group in enumerate(groups,1):
            times=[r[1] for r in group]
            voyages.append({'rfid_id':vid,'voyage_no':no,'t_start':times[0],'t_end':times[-1],
                            'n_rows':len(times),'t_mid':observed_midpoint(times)})
    return voyages,vessel_raw_counts,duplicate_extra,len(first)

def observed_midpoint(sorted_times):
    return int(sorted_times[len(sorted_times)//2]) if sorted_times else None

def eligibility_reason(raw_n,n_valid):
    if raw_n<11: return 'raw_history_insufficient'
    if n_valid==0: return 'no_valid_voyage'
    if n_valid<11: return 'valid_history_insufficient'
    return 'eligible'

def select_minimum(valid,score_key='_score'):
    if not valid: return None
    m=min(v[score_key] for v in valid)
    tied=[v for v in valid if v[score_key]==m]
    return min(tied,key=lambda r:(int(r['t_start']),int(r['voyage_no'])))

def rank_confidence(selected,reference_scores):
    n=len(reference_scores)
    if n==0: raise ValueError('At least one reference is required')
    less=sum(x<selected for x in reference_scores)
    equal=sum(x==selected for x in reference_scores)
    p=(less+0.5*equal)/n
    return {'less':less,'equal':equal,'n_reference':n,'rank_percentile':p,'confidence':1.0-p}

def event_csv():
    out=[]
    for r in read_csv(EVENTS):
        out.append({'acc_id':int(r['acc_id']),'rfid_id':str(r['rfid_id']).strip(),'tier':int(r['tier']),'acc_ts':int(r['acc_ts'])})
    return out

def run():
    t0=time.time(); external=HERE/'g6_preflight.json'
    log={'started_at':utc_now(),'command':'python -B testB/round_013_20261105/g6_selection_and_confidence.py',
         'scope':'?6 only; no ?7 metrics, model fitting, 2025 scoring or submission',
         'requested_model':'GPT-6 Luna xhigh as dispatched by supervisor task',
         'actual_model_telemetry':'not exposed by Python process; dispatch/task request and repository worker profile are documented separately',
         'external_preflight':json.loads(external.read_text(encoding='utf-8-sig')) if external.exists() else None,
         'python':sys.version,'platform':platform.platform(),'memory_checks':[],'source_hashes_before':source_manifest()}
    snap=ram_snapshot('before_g6_streamed_id_ts_and_selection')
    log['memory_checks'].append(snap)
    if snap['available_ram_mib']<768 or snap['available_ram_mib']<snap['estimated_additional_peak_mib']:
        (HERE/'g6_execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError('RAM below threshold/estimated peak; g6 calculation deferred')

    stored=read_csv(G4)
    targets={r['rfid_id'] for r in stored}
    raw,source_counts=load_track_id_ts(targets)
    track_voyages,raw_count,dup_extra,unique_rows=split_dedup(raw)
    actual={(r['rfid_id'],r['voyage_no']):r for r in track_voyages}
    g4={(r['rfid_id'],int(r['voyage_no'])):r for r in stored}
    if len(actual)!=len(g4): raise AssertionError(f'Voyage key count differs: parquet={len(actual)} g4={len(g4)}')
    for key,a in actual.items():
        b=g4[key]
        for field in ('t_start','t_end','n_rows'):
            if int(b[field])!=int(a[field]): raise AssertionError(f'Voyage split mismatch {key} {field}: {a[field]} != {b[field]}')
        if int(b['raw_voyage_count_for_vessel'])!=raw_count[key[0]]: raise AssertionError(f'Raw voyage count mismatch {key[0]}')
    events=event_csv(); events_by=defaultdict(list)
    for e in events: events_by[e['rfid_id']].append(e)
    vessel_ids=sorted({e['rfid_id'] for e in events})
    if len(vessel_ids)!=82 or len(events)!=100: raise AssertionError('Unexpected fixed dev linkage dimensions')

    by_vessel=defaultdict(list)
    for r in stored: by_vessel[r['rfid_id']].append(r)
    status_rows=[]; confidence=[]; selections={}
    for w in WINDOWS:
        field=f'lin_min_w{w}'
        for vid in vessel_ids:
            vr=by_vessel.get(vid,[])
            raw_n=raw_count.get(vid,0)
            valid=[]
            for r in vr:
                score=finite_score(r.get(field))
                if score is not None:
                    v=dict(r);v['_score']=score;valid.append(v)
            nvalid=len(valid)
            reason=eligibility_reason(raw_n,nvalid)
            evs=events_by.get(vid,[]); evs01=[e for e in evs if e['tier']<=1]
            status_rows.append({'w':w,'rfid_id':vid,'raw_voyages':raw_n,'raw_other_voyages':max(0,raw_n-1),
                'raw_history_eligible':raw_n>=11,'valid_voyages':nvalid,'valid_other_voyages_if_selected':max(0,nvalid-1),
                'status':reason,'n_events_all':len(evs),'n_events_tier01':len(evs01),
                'eligible_events_all':len(evs) if reason=='eligible' else 0,
                'eligible_events_tier01':len(evs01) if reason=='eligible' else 0})
            if reason!='eligible': continue
            chosen=select_minimum(valid)
            min_score=chosen['_score']
            ref=[v for v in valid if not (v['rfid_id']==chosen['rfid_id'] and int(v['voyage_no'])==int(chosen['voyage_no']))]
            rank=rank_confidence(min_score,[v['_score'] for v in ref])
            less,equal,p,conf=rank['less'],rank['equal'],rank['rank_percentile'],rank['confidence']
            a=actual[(vid,int(chosen['voyage_no']))]
            selection={'w':w,'rfid_id':vid,'voyage_no':int(chosen['voyage_no']),'lin_min':min_score,
                't_start':int(chosen['t_start']),'t_end':int(chosen['t_end']),'n_rows':int(chosen['n_rows']),
                't_collapse':int(chosen[f't_collapse_w{w}']),'t_mid':int(a['t_mid']),
                'valid_voyages':nvalid,'n_reference':rank['n_reference'],'less':less,'equal':equal,
                'rank_percentile':p,'confidence':conf,'tied_minimum_candidates':equal+1}
            selections[(w,vid)]=selection
            confidence.append(selection.copy())
    status_by={(r['w'],r['rfid_id']):r for r in status_rows}

    event_rows=[]
    for w in WINDOWS:
        for e in sorted(events,key=lambda x:x['acc_id']):
            s=status_by[(w,e['rfid_id'])]
            rec={'w':w,'acc_id':e['acc_id'],'rfid_id':e['rfid_id'],'tier':e['tier'],'acc_ts':e['acc_ts'],
                 'status':s['status'],'prediction_available':s['status']=='eligible'}
            sel=selections.get((w,e['rfid_id']))
            if sel:
                for key,val in sel.items():
                    if key not in ('w','rfid_id'):rec[key]=val
            else:
                for key in ('voyage_no','lin_min','t_start','t_end','n_rows','t_collapse','t_mid','valid_voyages',
                            'n_reference','less','equal','rank_percentile','confidence','tied_minimum_candidates'):
                    rec[key]=None
            event_rows.append(rec)
    write_csv(HERE/'g6_vessel_status.csv',status_rows)
    write_csv(HERE/'g3_confidence.csv',confidence)
    write_csv(HERE/'g6_event_results.csv',event_rows)
    # Preserve the exact timing reconstruction and parity check for independent audit.
    selected_timing=[]
    for sel in selections.values():
        selected_timing.append({k:sel[k] for k in ('w','rfid_id','voyage_no','t_start','t_end','n_rows','t_mid','t_collapse')})
    write_csv(HERE/'g6_selected_voyage_timing.csv',selected_timing)
    if external.exists(): external_doc=json.loads(external.read_text(encoding='utf-8-sig'))
    else: external_doc=None
    log.update({'ended_at':utc_now(),'elapsed_seconds':round(time.time()-t0,3),'stream':{'batch_size':BATCH,'columns':['rfid_id_int','ts'],
        'sources':source_counts,'raw_rows_for_82_vessels':len(raw),'unique_rows_after_first_key_dedup':unique_rows,
        'duplicate_extra_rows_first_retained':dup_extra,'source_file_order':'dev_hourly_scores.parquet then additional_hourly_scores.parquet; first duplicate key retained'},
        'dimensions':{'events':len(events),'vessels':len(vessel_ids),'g4_voyages':len(stored),'reconstructed_voyages':len(track_voyages),
          'selected_vessels_w3':sum(k[0]==3 for k in selections),'selected_vessels_w7':sum(k[0]==7 for k in selections),
          'event_rows':len(event_rows)},
        'external_preflight':external_doc,'source_hashes_after':source_manifest(),
        'outputs':['g6_vessel_status.csv','g3_confidence.csv','g6_event_results.csv','g6_selected_voyage_timing.csv']})
    (HERE/'g6_execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
    if log['source_hashes_before']!=log['source_hashes_after']:raise AssertionError('Source hash changed during g6')
    print(json.dumps({'dimensions':log['dimensions'],'stream':log['stream'],'status_counts':{
        str(w):{name:sum(r['w']==w and r['status']==name for r in status_rows) for name in ('eligible','raw_history_insufficient','valid_history_insufficient','no_valid_voyage')} for w in WINDOWS}},ensure_ascii=False,indent=2))

if __name__=='__main__':run()
