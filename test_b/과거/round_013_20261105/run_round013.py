# -*- coding: utf-8 -*-
"""Round013 ?3-5 execution only. Streaming input; never computes ?6-7 outcomes."""
from __future__ import annotations
import csv, hashlib, json, math, os, platform, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
R8 = ROOT / 'testB/round_008_linkage_audit_20261105'
R11 = ROOT / 'testB/round_011_20261105'
R12 = ROOT / 'testB/round_012_20261105'
DEV_FILES = [R8/'dev_hourly_scores.parquet', R8/'additional_hourly_scores.parquet']
TESTB_FILE = ROOT / 'testB/first_results/hourly_scores.parquet'
POS_FILE = R8 / 'devset_positives.csv'
BATCH = 65536
WINDOWS = (3, 7)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_manifest():
    inputs = [*DEV_FILES, TESTB_FILE, POS_FILE]
    context = [ROOT/'AGENTS.md', ROOT/'.codex/agents/luna_worker.toml', R12/'g_gate_v2.py', R11/'PROTOCOL.md', HERE/'PROTOCOL.md', HERE/'SUPERVISOR_TASK_01.md', HERE/'run_round013.py', HERE/'validate_round013.py']
    return {str(p.relative_to(ROOT)): {'bytes':p.stat().st_size,'sha256':sha256(p)} for p in inputs+context}


def memory_snapshot(stage):
    import ctypes
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),
                    ('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),
                    ('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
                    ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
    m=MEMORYSTATUSEX(); m.dwLength=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError('GlobalMemoryStatusEx failed')
    processes=[]
    try:
        import psutil
        for proc in psutil.process_iter(['pid','name','memory_info']):
            try:
                x=proc.info
                processes.append({'pid':x['pid'],'name':x['name'],'working_set_mib':round(x['memory_info'].rss/1048576,1)})
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    except ImportError:
        processes=[{'note':'psutil unavailable; process list recorded externally'}]
    return {'stage':stage,'checked_at_local':datetime.now().astimezone().isoformat(timespec='seconds'),
            'available_ram_mib':round(m.ullAvailPhys/1048576,1),'total_ram_mib':round(m.ullTotalPhys/1048576,1),
            'estimated_additional_peak_mib':350,
            'peak_estimate_basis':'Selected parquet columns only, 65,536-row batches; at most 99,677 retained dev rows as Python records (~80 MiB estimated), sorted working copy (~40 MiB), Arrow/NumPy/pandas/SciPy import+buffers (~200 MiB); conservative rounded upper estimate 350 MiB. One process, vessel-sequential calculations.',
            'processes':processes}


def get_events():
    d=pd.read_csv(POS_FILE,dtype={'rfid_id':str})
    d['rfid_id']=d['rfid_id'].str.strip()
    d['acc_ts_num']=pd.to_numeric(d['acc_ts'],errors='coerce')
    bad=d['acc_ts_num'].isna() | (d['acc_ts_num'] % 1 != 0)
    if bad.any(): raise ValueError(f'Non-integer/non-finite acc_ts rows: {int(bad.sum())}')
    d['acc_ts_int']=d['acc_ts_num'].astype('int64')
    return d


def normalize(x):
    if x is None: return float('nan')
    return x


def stream_records(paths, id_col, target_ids=None, fields=()):
    """Keep only selected columns; target filtering happens per Arrow batch."""
    out=[]; seq=0
    wanted=[id_col,'ts',*fields]
    for path in paths:
        pf=pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=BATCH,columns=wanted):
            cols={n:batch.column(n).to_pylist() for n in wanted}
            ids=cols[id_col]
            if target_ids is None:
                keep=range(len(ids))
            else:
                keep=(i for i,x in enumerate(ids) if (str(x).strip() if isinstance(x,str) else str(int(x))) in target_ids)
            for i in keep:
                vid=cols[id_col][i]
                vid=str(vid).strip() if isinstance(vid,str) else str(int(vid))
                row={'rfid_id':vid,'ts':normalize(cols['ts'][i]),'_order':seq+i,'_source':path.name}
                for f in fields: row[f]=normalize(cols[f][i])
                out.append(row)
            seq+=len(ids)
    return out


def isfinite_num(v):
    try: return math.isfinite(float(v))
    except (TypeError,ValueError,OverflowError): return False


def equal_value(a,b):
    if a is None or b is None: return a is b
    if isinstance(a,(int,float,np.number)) and isinstance(b,(int,float,np.number)):
        if not isfinite_num(a) and not isfinite_num(b): return True
        return float(a)==float(b)
    return a==b


def audit_deduplicate(rows, fields):
    per={}
    for r in rows:
        ts=r['ts']
        try: key=(r['rfid_id'],float(ts) if ts is not None else None)
        except (TypeError,ValueError): key=(r['rfid_id'],str(ts))
        if key not in per: per[key]=r
    # Since rows are yielded in concatenated file/input order, first entry is the Round012 keeper.
    duplicate_groups=Counter(); conflict_groups=set(); conflict_rows=0
    for r in rows:
        ts=r['ts']
        try: key=(r['rfid_id'],float(ts) if ts is not None else None)
        except (TypeError,ValueError): key=(r['rfid_id'],str(ts))
        first=per[key]
        if r is first: continue
        duplicate_groups[key]+=1
        if any(not equal_value(r.get(f),first.get(f)) for f in fields):
            conflict_groups.add(key); conflict_rows+=1
    # Distinguish NaN key edge from valid time; key dedup semantics match pandas on ordinary finite ts.
    kept=list(per.values())
    return kept, {'raw_rows':len(rows),'unique_rows':len(kept),'duplicate_extra_rows':len(rows)-len(kept),
                  'duplicate_key_groups':sum(1 for n in duplicate_groups.values()),
                  'conflicting_duplicate_groups':len(conflict_groups),'conflicting_duplicate_rows':conflict_rows}


def input_quality(rows, fields):
    report={'input_rows':len(rows),'timestamp':{'nonfinite':0,'negative':0,'noninteger':0}}
    for f in fields: report[f]={'nonfinite':0,'negative':0}
    for r in rows:
        t=r.get('ts')
        if not isfinite_num(t): report['timestamp']['nonfinite']+=1
        else:
            tf=float(t)
            if tf<0: report['timestamp']['negative']+=1
            if tf%1!=0: report['timestamp']['noninteger']+=1
        for f in fields:
            v=r.get(f)
            if not isfinite_num(v): report[f]['nonfinite']+=1
            elif float(v)<0: report[f]['negative']+=1
    return report


def split_voyages(rows):
    by=defaultdict(list)
    for r in rows: by[r['rfid_id']].append(r)
    result=[]
    for vid in sorted(by):
        g=sorted(by[vid],key=lambda r:(float(r['ts']),r['_order']))
        # Parquet schemas are integer epoch hours; preserve exact int and audit that contract.
        segments=[]; cur=[]
        for r in g:
            t=float(r['ts'])
            if not math.isfinite(t) or t%1: raise ValueError(f'Invalid ts after audit: {vid}/{r["ts"]}')
            r['_ts_int']=int(t)
            if cur and r['_ts_int']-cur[-1]['_ts_int']>=6:
                segments.append(cur); cur=[]
            cur.append(r)
        if cur: segments.append(cur)
        for no,seg in enumerate(segments,1):
            result.append({'rfid_id':vid,'voyage_no':no,'t_start':seg[0]['_ts_int'],'t_end':seg[-1]['_ts_int'],
                           'n_rows':len(seg),'_rows':seg})
    return result


def compute_local(voy,w):
    rows=voy['_rows']; start=voy['t_start']; end=voy['t_end']
    by_ts={r['_ts_int']:r for r in rows}
    minval=None; minhour=None; valid_count=0
    finite_required, good_required=((2,2) if w==3 else (4,3))
    # h ranges over every integer epoch hour, including unobserved hours.
    for h in range(start+w-1,end+1):
        window=[by_ts[t] for t in range(h-w+1,h+1) if t in by_ts]
        finite=[r for r in window if isfinite_num(r.get('len_m')) and isfinite_num(r.get('bbox_m'))]
        good=[r for r in finite if float(r['len_m'])>=1]
        if len(finite)<finite_required or len(good)<good_required: continue
        den=sum(float(r['len_m']) for r in good); num=sum(float(r['bbox_m']) for r in good)
        val=num/den
        if not math.isfinite(val): continue
        valid_count+=1
        if minval is None or val<minval: minval,minhour=val,h
    return minval,minhour,valid_count


def direct_window_audit(voy,w):
    """Deliberately direct row scan, independent of the timestamp-index calculation above."""
    rows=voy['_rows']; values=[]
    minval=None; minhour=None
    a,b=((2,2) if w==3 else (4,3))
    for h in range(voy['t_start']+w-1,voy['t_end']+1):
        finite=[]; good=[]
        for r in rows:
            if h-w+1 <= r['_ts_int'] <= h and isfinite_num(r.get('len_m')) and isfinite_num(r.get('bbox_m')):
                finite.append(r)
                if float(r['len_m'])>=1: good.append(r)
        if len(finite)>=a and len(good)>=b:
            value=sum(float(r['bbox_m']) for r in good)/sum(float(r['len_m']) for r in good)
            values.append((h,value))
            if minval is None or value<minval: minval,minhour=value,h
    return minval,minhour,len(values)


def write_csv(path,rows,columns=None):
    rows=list(rows)
    if columns is None: columns=list(rows[0]) if rows else []
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def hour_bucket(hour):
    h=int(hour)%24
    return 'day_06_18' if 6<=h<18 else 'night_18_06'


def main():
    started=time.time(); preflight=HERE/'run_preflight.json'; log={'started_at':utc_now(),'pre_data_recovery_note':'Initial attempts: first exited before parquet reads due a UTF-8 BOM in PowerShell preflight JSON (reader corrected to utf-8-sig); second completed calculations and wrote outputs but exited 1 on a final console-summary key typo (corrected before this full rerun). No source rows were processed in the first attempt.','external_preflight':json.loads(preflight.read_text(encoding='utf-8-sig')) if preflight.exists() else None,'requested_model':'GPT-6 Luna xhigh (supervisor assignment)',
       'model_assignment_evidence':'dispatch explicitly specified GPT-6 Luna xhigh; repository .codex/agents/luna_worker.toml specifies gpt-6-luna/xhigh',
       'actual_model':'not independently exposed by the Python/OS runtime; do not infer runtime identity from project defaults',
       'scope':'PROTOCOL ??3-5 only; no ?6-7 calculations, 2025 features/scores/inference, model training, external collection, or submission',
       'python':sys.version,'platform':platform.platform(),'parameters':{'gap_hours':6,'windows':[3,7],'batch_size':BATCH,'required_free_ram_mib':768},
       'source_hashes_before':source_manifest(),'memory_checks':[]}
    log['memory_checks'].append(memory_snapshot('pre_dev_scan_and_calculation'))
    if log['memory_checks'][-1]['available_ram_mib']<768:
        (HERE/'execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError('RAM below 768 MiB; execution deferred')

    events=get_events(); ids=set(events.rfid_id)
    id_ints={str(int(x)) for x in ids}
    dev_raw=stream_records(DEV_FILES,'rfid_id_int',id_ints,('len_m','bbox_m','cen_lon','cen_lat','state'))
    qa=input_quality(dev_raw,('len_m','bbox_m'))
    (HERE/'input_quality_dev.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    if qa['bbox_m']['negative']:
        log['stop_reason']=f"negative bbox_m observed: {qa['bbox_m']['negative']} raw rows; stopped per supervisor instruction"
        log['dev_input_quality']=qa; log['source_hashes_after']=source_manifest(); log['ended_at']=utc_now()
        (HERE/'execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError(log['stop_reason'])
    if qa['timestamp']['nonfinite'] or qa['timestamp']['noninteger']:
        log['stop_reason']='timestamp is not finite integer epoch-hour; requires supervisor interpretation'
        log['dev_input_quality']=qa; log['source_hashes_after']=source_manifest(); log['ended_at']=utc_now()
        (HERE/'execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError(log['stop_reason'])
    dev_kept,dev_dup=audit_deduplicate(dev_raw,('len_m','bbox_m','cen_lon','cen_lat','state'))
    voyages=split_voyages(dev_kept)
    by_vessel=defaultdict(list)
    for v in voyages: by_vessel[v['rfid_id']].append(v)
    raw_voy_count={k:len(v) for k,v in by_vessel.items()}
    for v in voyages:
        for w in WINDOWS:
            val,h,n=compute_local(v,w)
            v[f'lin_min_w{w}']=val; v[f't_collapse_w{w}']=h; v[f'valid_windows_w{w}']=n
    # Independent direct summation audit: first 30 deterministic voyage rows per w.
    direct=[]
    for w in WINDOWS:
        for v in voyages[:30]:
            fast=(v[f'lin_min_w{w}'],v[f't_collapse_w{w}'],v[f'valid_windows_w{w}'])
            slow=direct_window_audit(v,w)
            ok=(fast[2]==slow[2] and (fast[0] is None and slow[0] is None or fast[0] is not None and slow[0] is not None and math.isclose(fast[0],slow[0],rel_tol=1e-12,abs_tol=1e-12)) and fast[1]==slow[1])
            direct.append({'rfid_id':v['rfid_id'],'voyage_no':v['voyage_no'],'w':w,'optimized_min':fast[0],'direct_min':slow[0],
                           'optimized_hour':fast[1],'direct_hour':slow[1],'optimized_valid_windows':fast[2],
                           'direct_valid_windows':slow[2],'match':ok})
    write_csv(HERE/'real_direct_sum_audit.csv',direct)
    if not all(x['match'] for x in direct): raise AssertionError('Direct sum audit mismatch')
    # Deterministic, vessel-sequential stage transition; record fresh RAM before 2025 ID/ts-only aggregate.
    log['memory_checks'].append(memory_snapshot('before_2025_id_ts_voyage_count_coverage'))
    if log['memory_checks'][-1]['available_ram_mib']<768:
        log['dev_completed']=True; log['testb_deferred']='RAM below 768 MiB at stage transition'
        log['source_hashes_after']=source_manifest(); log['ended_at']=utc_now()
        (HERE/'execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
        raise RuntimeError('2025 voyage-count coverage deferred: RAM below 768 MiB')

    # 2025: only id and ts are read, and only voyage counts are produced.
    t_raw=stream_records([TESTB_FILE],'rfid_id',None,())
    tqa=input_quality(t_raw,())
    if tqa['timestamp']['nonfinite'] or tqa['timestamp']['noninteger']:
        raise ValueError('2025 timestamp is not finite integer epoch-hour')
    test_kept,test_dup=audit_deduplicate(t_raw,())
    test_voyages=split_voyages(test_kept)
    test_counts=Counter(v['rfid_id'] for v in test_voyages)

    event_by=defaultdict(list)
    tier01_ids=set(events.loc[events.tier<=1,'rfid_id'])
    for _,e in events.iterrows(): event_by[e.rfid_id].append({'acc_id':int(e.acc_id),'acc_ts':int(e.acc_ts_int),'tier':int(e.tier)})
    # Each voyage receives one mutually exclusive descriptive label; controls are not asserted normal.
    for v in voyages:
        matches=[e for e in event_by.get(v['rfid_id'],[]) if v['t_start']-6<=e['acc_ts']<=v['t_end']+6]
        v['related_acc_ids']=';'.join(str(e['acc_id']) for e in matches)
        v['accident_related']=bool(matches)
        v['contrast_label']='accident_related' if matches else 'control_not_confirmed_normal'
        for w in WINDOWS:
            h=v[f't_collapse_w{w}']
            v[f'collapse_hour_w{w}']=None if h is None else int(h)%24
            v[f'collapse_bucket_w{w}']=None if h is None else hour_bucket(h)
            v[f'same_bucket_effective_voyages_w{w}']=None
            v[f'same_bucket_other_effective_refs_w{w}']=None
            v[f'same_bucket_loo_ge10_w{w}']=None
    # Bucket-effective reference counts retained for a later approved conditional branch.
    for w in WINDOWS:
        groups=defaultdict(list)
        for v in voyages:
            bucket=v[f'collapse_bucket_w{w}']
            if bucket is not None: groups[(v['rfid_id'],bucket)].append(v)
        for (vid,bucket),members in groups.items():
            for v in members:
                n=len(members); v[f'same_bucket_effective_voyages_w{w}']=n
                v[f'same_bucket_other_effective_refs_w{w}']=n-1
                v[f'same_bucket_loo_ge10_w{w}']=bool(n-1>=10)

    # ?3 coverage: table's <10 category is retained separately from actual n-1>=10 qualification.
    ev_count=events.groupby('rfid_id').size().to_dict()
    t01_count=events[events.tier<=1].groupby('rfid_id').size().to_dict()
    coverage=[]
    for vid in sorted(ids):
        vv=by_vessel.get(vid,[]); total=raw_voy_count.get(vid,0)
        row={'dataset':'dev','rfid_id':vid,'events':int(ev_count.get(vid,0)),'tier01_events':int(t01_count.get(vid,0)),
             'raw_rows':sum(1 for r in dev_raw if r['rfid_id']==vid),'raw_voyages':total,
             'protocol_table_voyages_lt10':bool(total<10),
             'table_category_voyages_lt5':bool(total<5),
             'eligible_raw_leave_one_out_other_voyages_ge10':bool(total>=11),
             'raw_other_voyages_for_target':max(0,total-1),
             'unique_rows':sum(v['n_rows'] for v in vv),'duplicate_extra_rows':sum(1 for r in dev_raw if r['rfid_id']==vid)-sum(v['n_rows'] for v in vv),
             'raw_leave_one_out_other_count':max(0,total-1),'raw_eligibility_reason':('eligible_other_voyages_ge10' if total>=11 else ('insufficient_history_other_voyages_lt10' if total>0 else 'no_history')),
             'dev_duplicate_extra_rows':dev_dup['duplicate_extra_rows']}
        for w in WINDOWS:
            n=sum(v[f'lin_min_w{w}'] is not None for v in vv)
            row[f'w{w}_effective_voyages']=n
            row[f'w{w}_effective_leave_one_out_other_ge10']=bool(n>=11)
            row[f'w{w}_effective_target_voyages_with_other_ge10']=n if n>=11 else 0
            for bucket in ('day_06_18','night_18_06'):
                nb=sum(v[f'collapse_bucket_w{w}']==bucket for v in vv)
                row[f'w{w}_{bucket}_effective_voyages']=nb
                row[f'w{w}_{bucket}_leave_one_out_other_ge10']=bool(nb>=11)
                row[f'w{w}_{bucket}_target_voyages_with_other_ge10']=nb if nb>=11 else 0
        coverage.append(row)
    for vid in sorted(test_counts):
        total=test_counts[vid]
        coverage.append({'dataset':'2025_Test_B','rfid_id':vid,'events':None,'tier01_events':None,
                         'raw_rows':sum(1 for r in t_raw if r['rfid_id']==vid),'unique_rows':sum(1 for r in test_kept if r['rfid_id']==vid),
                         'duplicate_extra_rows':sum(1 for r in t_raw if r['rfid_id']==vid)-sum(1 for r in test_kept if r['rfid_id']==vid),'raw_voyages':total,
                         'protocol_table_voyages_lt10':bool(total<10),'table_category_voyages_lt5':bool(total<5),
                         'eligible_raw_leave_one_out_other_voyages_ge10':bool(total>=11),
                         'raw_other_voyages_for_target':max(0,total-1),'dev_duplicate_extra_rows':None,
                         'raw_leave_one_out_other_count':max(0,total-1),'raw_eligibility_reason':('eligible_other_voyages_ge10' if total>=11 else ('insufficient_history_other_voyages_lt10' if total>0 else 'no_history')),
                         'w3_effective_voyages':None,'w3_effective_leave_one_out_other_ge10':None,
                         'w3_effective_target_voyages_with_other_ge10':None,
                         'w7_effective_voyages':None,'w7_effective_leave_one_out_other_ge10':None,
                         'w7_effective_target_voyages_with_other_ge10':None})
    write_csv(HERE/'g3_voyage_count_coverage.csv',coverage)
    coverage_summary={}
    for dataset in ('dev','2025_Test_B'):
        subset=[r for r in coverage if r['dataset']==dataset]
        ns=[int(r['raw_voyages']) for r in subset]
        coverage_summary[dataset]={'vessels':len(ns),'median_voyages':float(np.median(ns)) if ns else None,
            'min_voyages':min(ns) if ns else None,'protocol_table_voyages_lt10_n':sum(n<10 for n in ns),
            'protocol_table_voyages_lt10_fraction':(sum(n<10 for n in ns)/len(ns) if ns else None),
            'voyages_lt5_n':sum(n<5 for n in ns),'voyages_lt5_fraction':(sum(n<5 for n in ns)/len(ns) if ns else None),
            'raw_leave_one_out_other_ge10_eligible_n':sum(n>=11 for n in ns),
            'raw_leave_one_out_other_ge10_eligible_fraction':(sum(n>=11 for n in ns)/len(ns) if ns else None),
            'exactly_10_voyages_nonqualifying_n':sum(n==10 for n in ns)}
    (HERE/'g3_coverage_summary.json').write_text(json.dumps(coverage_summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (HERE/'input_quality_2025.json').write_text(json.dumps(tqa,ensure_ascii=False,indent=2),encoding='utf-8')

    # ?4 voyage-level output; no ?6 selection, no ?7 event scoring.
    voyage_out=[]
    for v in voyages:
        row={k:v[k] for k in ('rfid_id','voyage_no','t_start','t_end','n_rows','related_acc_ids','accident_related','contrast_label')}
        row['raw_voyage_count_for_vessel']=raw_voy_count[v['rfid_id']]
        row['raw_leave_one_out_other_count']=raw_voy_count[v['rfid_id']]-1
        for w in WINDOWS:
            for k in (f'lin_min_w{w}',f't_collapse_w{w}',f'valid_windows_w{w}',f'collapse_hour_w{w}',f'collapse_bucket_w{w}',
                      f'same_bucket_effective_voyages_w{w}',f'same_bucket_other_effective_refs_w{w}',f'same_bucket_loo_ge10_w{w}'):
                row[k]=v[k]
        voyage_out.append(row)
    write_csv(HERE/'g4_voyage_local_collapse.csv',voyage_out)

    # ?5 ALL-population KS (one per w); Tier0-1 only descriptive.
    g5={'population':'ALL dev vessels; each unique voyage counted once','hour_definition':'stored integer epoch-hour modulo 24, not asserted local time',
        'day_bucket':'[06,18)','night_bucket':'[18,06)','accident_related_definition':'same vessel has >=1 acc_ts in [t_start-6,t_end+6]',
        'control_definition':'all remaining voyages; not confirmed normal','ks_test':'two-sided two-sample KS on collapse_hour modulo 24',
        'family_size':2,'bonferroni_alpha':0.05,'windows':{},'hour_distributions':[]}
    for w in WINDOWS:
        valid=[v for v in voyages if v[f'lin_min_w{w}'] is not None]
        for pop_name,subset in [('ALL',valid),('Tier0-1_vessels',[v for v in valid if v['rfid_id'] in tier01_ids])]:
            rho=float('nan'); rp=float('nan')
            if len(subset)>=2:
                rr=stats.spearmanr([v[f'lin_min_w{w}'] for v in subset],[v[f'collapse_hour_w{w}'] for v in subset])
                rho=float(rr.statistic); rp=float(rr.pvalue)
            g5['windows'].setdefault(str(w),{})[pop_name]={'n_valid_voyages':len(subset),'n_vessels':len({v['rfid_id'] for v in subset}),
                'spearman_rho_min_lin_vs_collapse_hour':rho,'spearman_p_descriptive':rp,
                'confound_rho_abs_ge_0_2':bool(math.isfinite(rho) and abs(rho)>=0.2)}
            counts=Counter(v[f'collapse_hour_w{w}'] for v in subset)
            for hour in range(24):
                g5['hour_distributions'].append({'w':w,'population':pop_name,'hour_mod24':hour,'voyage_count':counts.get(hour,0),
                    'fraction':(counts.get(hour,0)/len(subset) if subset else None)})
        incident=[v[f'collapse_hour_w{w}'] for v in valid if v['accident_related']]
        control=[v[f'collapse_hour_w{w}'] for v in valid if not v['accident_related']]
        if incident and control:
            ks=stats.ks_2samp(incident,control,alternative='two-sided',method='auto')
            raw=float(ks.pvalue); corrected=min(1.0,2*raw)
        else: ks=None; raw=None; corrected=None
        g5['windows'][str(w)]['accident_vs_control_ks']={'n_accident_related_voyages':len(incident),'n_control_voyages':len(control),
            'statistic':None if ks is None else float(ks.statistic),'p_raw':raw,'p_bonferroni_family2':corrected,
            'confound_ks_adjusted_p_lt_0_05':bool(corrected is not None and corrected<0.05),
            'confound_present':bool(g5['windows'][str(w)]['ALL']['confound_rho_abs_ge_0_2'] or (corrected is not None and corrected<0.05))}
    (HERE/'g5_confound_summary.json').write_text(json.dumps(g5,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(HERE/'g5_hour_distribution.csv',g5['hour_distributions'])
    bucket_rows=[]
    for w in WINDOWS:
        for vid in sorted(ids):
            vv=[v for v in voyages if v['rfid_id']==vid and v[f'lin_min_w{w}'] is not None]
            for bucket in ('day_06_18','night_18_06'):
                n=sum(v[f'collapse_bucket_w{w}']==bucket for v in vv)
                bucket_rows.append({'w':w,'rfid_id':vid,'bucket':bucket,'effective_voyages':n,
                    'other_effective_references_if_target_in_bucket':max(0,n-1),'leave_one_out_other_refs_ge10':bool(n>=11),
                    'potential_target_voyages_with_other_refs_ge10':n if n>=11 else 0})
    write_csv(HERE/'g5_same_bucket_reference_coverage.csv',bucket_rows)

    log.update({'ended_at':utc_now(),'elapsed_seconds':round(time.time()-started,2),'dev_input_quality':qa,'dev_duplicates':dev_dup,
       '2025_input_quality':tqa,'2025_duplicates':test_dup,'counts':{'dev_events':len(events),'dev_event_vessels':len(ids),
       'tier01_events':int((events.tier<=1).sum()),'dev_rows_selected_raw':len(dev_raw),'dev_unique_rows':len(dev_kept),
       'dev_voyages':len(voyages),'2025_raw_rows':len(t_raw),'2025_unique_rows':len(test_kept),
       '2025_vessels':len(test_counts),'2025_voyages':len(test_voyages),
       'dev_raw_eligibility_vessels_ge11':sum(v['raw_voyages']>=11 for v in coverage if v['dataset']=='dev'),
       'dev_table_vessels_lt10':sum(v['protocol_table_voyages_lt10'] for v in coverage if v['dataset']=='dev'),
       'dev_exactly_10_voyages_nonqualifying':sum(v['raw_voyages']==10 for v in coverage if v['dataset']=='dev'),
       'dev_vessels_effective_loo_ge10_w3':sum(v['w3_effective_leave_one_out_other_ge10'] for v in coverage if v['dataset']=='dev'),
       'dev_vessels_effective_loo_ge10_w7':sum(v['w7_effective_leave_one_out_other_ge10'] for v in coverage if v['dataset']=='dev'),'real_direct_sum_samples':len(direct),
       'real_direct_sum_mismatches':sum(not x['match'] for x in direct)},
       'source_hashes_after':source_manifest(),'synthetic_validation':'pending execution of validate_round013.py',
       'outputs':['g3_voyage_count_coverage.csv','g3_coverage_summary.json','g4_voyage_local_collapse.csv','g5_confound_summary.json','g5_hour_distribution.csv',
                  'g5_same_bucket_reference_coverage.csv','input_quality_dev.json','input_quality_2025.json','real_direct_sum_audit.csv']})
    (HERE/'execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
    if log['source_hashes_before']!=log['source_hashes_after']:
        raise AssertionError('Protected input/context file hash changed during run')
    print(json.dumps({'counts':log['counts'],'dev_duplicates':dev_dup,'2025_duplicates':test_dup,
       'w':{w:{'rho':g5['windows'][str(w)]['ALL']['spearman_rho_min_lin_vs_collapse_hour'],
       'ks_statistic':g5['windows'][str(w)]['accident_vs_control_ks']['statistic'],
       'ks_p_raw':g5['windows'][str(w)]['accident_vs_control_ks']['p_raw'],
       'ks_p_bonferroni':g5['windows'][str(w)]['accident_vs_control_ks']['p_bonferroni_family2'],
       'confound':g5['windows'][str(w)]['accident_vs_control_ks']['confound_present']} for w in WINDOWS}},ensure_ascii=False,indent=2))

if __name__=='__main__': main()





