"""Independent implementation audit. Does not import either producer's functions.

First recomputes statistics from event evidence with stdlib. A separately gated
raw parquet scan independently rebuilds 3 metrics and state presence controls.
Same Codex operator: implementation independence, not independent reviewer.
"""
import sys
sys.dont_write_bytecode=True
import bisect,collections,csv,ctypes,json,math,random,hashlib,traceback,statistics
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent;ROOT=P.parent;C=ROOT/'codex_independent';BASE=ROOT.parent
METRICS=['lin_raw','speed_mean','step_mean'];STATES=['저속굴곡','이동','정박정지','해상정지','연안정지']
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def quantile(values,p):
    x=sorted(values);at=(len(x)-1)*p;i=int(at);return x[i]+(at-i)*(x[min(i+1,len(x)-1)]-x[i])
def memory(stage,expected=512,reserve=1024):
    class M(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('available',ctypes.c_ulonglong),('tp',ctypes.c_ulonglong),('ap',ctypes.c_ulonglong),('tv',ctypes.c_ulonglong),('av',ctypes.c_ulonglong),('ext',ctypes.c_ulonglong)]
    m=M();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    class PMC(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(x,ctypes.c_size_t) for x in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage']]
    pm=PMC();pm.cb=ctypes.sizeof(pm)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(pm),ctypes.sizeof(pm)):raise OSError('own process memory unavailable')
    rss=pm.WorkingSetSize/2**20;remaining=max(0,expected-rss)
    r={'checked_at':datetime.now().astimezone().isoformat(),'stage':stage,'available_mib':m.available/2**20,
       'estimated_total_process_peak_mib':expected,'own_current_rss_mib':rss,'own_peak_rss_mib':pm.PeakWorkingSetSize/2**20,
       'estimated_remaining_increment_mib':remaining,'reserve_mib':reserve,'allowed':m.available/2**20>=remaining+reserve and pm.PeakWorkingSetSize/2**20<=expected,
       'estimate_basis':f'TOTAL stage ceiling {expected}MiB including resident imports; remaining increment=ceiling-current RSS. Raw scan estimate calibrated to256MiB from earlier fully loaded positive-row observation167.668MiB plus >88MiB margin; cached stdlib load128MiB; one vessel windows256MiB. Original T1/T2 512MiB upper envelope is not exceeded. Reserve stays1024MiB; observed peak checked against estimate.',
       'concurrent_tasks':'no own parallel jobs; user processes untouched'}
    path=P/'t3_memory.json';old=read(path) if path.exists() else [];old.append(r);save(path.name,old);return r['allowed']

def rank_test(d):
    """SciPy-compatible Wilcoxon without scipy: exact untied <=50, else normal.
    Ties are average ranks; normal variance includes tie correction, no continuity.
    """
    d=[x for x in d if x!=0];n=len(d)
    if not n:return {'wilcoxon_p':1.,'sign_p':1.,'n_nonzero':0}
    sorted_abs=sorted((abs(v),i) for i,v in enumerate(d));ranks=[0.]*n;ties=[];j=0
    while j<n:
        k=j+1
        while k<n and sorted_abs[k][0]==sorted_abs[j][0]:k+=1
        rank=(j+1+k)/2
        for _,i in sorted_abs[j:k]:ranks[i]=rank
        if k-j>1:ties.append(k-j)
        j=k
    plus=math.fsum(r for r,v in zip(ranks,d) if v>0);minus=sum(ranks)-plus
    if n<=50 and not ties:
        dist=[1]
        for r in range(1,n+1):
            new=dist+[0]*r
            for i,v in enumerate(dist):new[i+r]+=v
            dist=new
        p=min(1.,2*sum(dist[:int(min(plus,minus))+1])/2**n);method='exact_signed_rank_untied'
    else:
        variance=(n*(n+1)*(2*n+1)-sum(t**3-t for t in ties)/2)/24
        p=math.erfc(abs(plus-n*(n+1)/4)/math.sqrt(2*variance));method='normal_signed_rank_tie_corrected_no_continuity'
    positives=sum(v>0 for v in d);sp=min(1.,2*sum(math.comb(n,k) for k in range(min(positives,n-positives)+1))/2**n)
    return {'wilcoxon_p':p,'sign_p':sp,'n_nonzero':n,'rank_method':method,'ties':ties}

def event_evidence_audit():
    rows=[]
    with (C/'t1_event_percentiles.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['design']=='hod_1/nrows_matched' and row['half_width_h']=='3' and row['metric'] in METRICS and not row['exclusion']:
                row['percentile']=float(row['percentile']);rows.append(row)
    out=[]
    for metric in METRICS:
        for s in ['ALL','Tier0_1']:
            rr=[r for r in rows if r['metric']==metric and (s=='ALL' or int(r['tier'])<=1)]
            d=[r['percentile']-.5 for r in rr];test=rank_test(d)
            source=next(g['primary'] for g in read(C/'t1_gate_results.json')['gates'] if g['metric']==metric and g['stratum']==s)
            sd=statistics.stdev(d)
            mde=(statistics.NormalDist().inv_cdf(1-.05/7/2)+statistics.NormalDist().inv_cdf(.8))*sd/math.sqrt(len(d))
            groups=collections.defaultdict(list)
            for r,v in zip(rr,d):groups[int(r['rfid_id'])].append(v)
            clusters=list(groups.values());rng=random.Random(20261105);boots=[]
            for _ in range(2000):
                sample=[rng.choice(clusters) for _ in clusters];boots.append(math.fsum(math.fsum(v) for v in sample)/sum(map(len,sample)))
            out.append({'metric':metric,'stratum':s,'aggregation':'event','n_events':len(rr),'n_vessels':len(groups),
              'delta_recomputed':statistics.mean(d),'delta_source':source['delta_percentile'],
              'delta_abs_error':abs(statistics.mean(d)-source['delta_percentile']),
              'wilcoxon_recomputed':test['wilcoxon_p'],'wilcoxon_source':source['wilcoxon_p'],
              'wilcoxon_abs_error':abs(test['wilcoxon_p']-source['wilcoxon_p']),
              'sign_recomputed':test['sign_p'],'sign_source':source['sign_p'],
              'mde_recomputed':mde,'mde_source':source['mde80_percentile_approx'],
              'rank_method':test['rank_method'],'n_abs_tie_groups':len(test['ties']),
              'cluster_bootstrap_ci95_posthoc':[quantile(boots,.025),quantile(boots,.975)],
              'cluster_bootstrap_note':'2000 vessel cluster resamples, event-weighted mean, Python Random seed20261105; posthoc sensitivity, not gate replacement'})
    save('t3_event_recompute.json',{'implementation_independence':'separate stdlib implementation, same operator','results':out})
    return out

def distance(lat1,lon1,lat2,lon2):
    p,q=math.radians(lat1),math.radians(lat2)
    a=math.sin((q-p)/2)**2+math.cos(p)*math.cos(q)*math.sin(math.radians(lon2-lon1)/2)**2
    return 12742000*math.asin(math.sqrt(max(0,min(1,a))))

def raw_audit():
    with (BASE/'round_008_linkage_audit_20261105/devset_positives.csv').open(encoding='utf-8-sig',newline='') as f:pos=list(csv.DictReader(f))
    ids={int(r['rfid_id']) for r in pos};groups=collections.defaultdict(list)
    columns=['rfid_id_int','ts','len_m','bbox_m','cen_lon','cen_lat','state','score']
    source=BASE/'round_008_linkage_audit_20261105/dev_hourly_scores.parquet'
    fingerprint={'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns,'path':str(source)}
    cache_manifest=P/'raw_source_cache_manifest.json'
    if cache_manifest.exists() and read(cache_manifest)['fingerprint']==fingerprint:
        if not memory('before_independent_raw_cache_load',128):return {'status':'deferred_memory','actual_raw_metrics_rebuilt':False}
        for rid in ids:groups[rid]=read(P/f'raw_source_vessel_{rid}.json')
    else:
        if not memory('before_raw_parquet_loading_calibrated256',256):return {'status':'deferred_memory','actual_raw_metrics_rebuilt':False}
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
        target=pa.array(sorted(ids),type=pa.int64());pf=pq.ParquetFile(source)
        for i,batch in enumerate(pf.iter_batches(batch_size=8192,columns=columns,use_threads=False)):
            if not memory(f'before_raw_batch_{i}_conversion',256):return {'status':'deferred_memory','actual_raw_metrics_rebuilt':False,'processed_batches':i}
            selected=batch.filter(pc.is_in(batch.column('rfid_id_int'),value_set=target))
            for r in selected.to_pylist():groups[int(r['rfid_id_int'])].append((int(r['ts']),r['len_m'],r['bbox_m'],r['cen_lat'],r['cen_lon'],r['state']))
        for rid,records in groups.items():save(f'raw_source_vessel_{rid}.json',records)
        save(cache_manifest.name,{'fingerprint':fingerprint,'reader':'independent PyArrow scan; no producer features imported','n_rows':sum(map(len,groups.values()))})
    lo=min(r[0] for gg in groups.values() for r in gg);hi=max(r[0] for gg in groups.values() for r in gg)
    events_by_v=collections.defaultdict(list)
    for e in pos:events_by_v[int(e['rfid_id'])].append(e)
    expected={}
    with (C/'t1_event_percentiles.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['design']=='hod_1/nrows_matched' and r['half_width_h']=='3' and r['metric'] in METRICS:expected[(int(r['acc_id']),r['metric'])]=r
    differences=[];rebuilt=[];state_events=[]
    for rid,records in groups.items():
        if not memory(f'before_raw_vessel_{rid}_windows',256):return {'status':'deferred_memory','actual_raw_metrics_rebuilt':False,'vessels_completed':len({r['rfid_id'] for r in rebuilt})}
        records.sort();ts=[r[0] for r in records];centers=range(lo+3,hi-2);windows=[]
        for c in centers:
            a=bisect.bisect_left(ts,c-3);b=bisect.bisect_right(ts,c+3);sub=records[a:b]
            lenses=[r[1] for r in sub];ratios=[r[2]/r[1] for r in sub if r[1]>=1]
            steps=[distance(x[3],x[4],y[3],y[4])/(y[0]-x[0]) for x,y in zip(sub[:-1],sub[1:])]
            windows.append((c,len(sub),{
              'lin_raw':statistics.mean(ratios) if ratios else None,
              'speed_mean':statistics.mean(lenses) if lenses else None,
              'step_mean':statistics.mean(steps) if steps else None}, {s:any(r[5]==s for r in sub) for s in STATES}))
        lookup={c:i for i,(c,*_) in enumerate(windows)};allacc=[int(e['acc_ts']) for e in events_by_v[rid]]
        for e in events_by_v[rid]:
            aid=int(e['acc_id']);acc=int(e['acc_ts']);w=windows[lookup[acc]]
            pool=[]
            for cw in windows:
                d=abs(cw[0]%24-acc%24)
                if cw[1]==w[1] and cw[1]>0 and min(d,24-d)<=1 and all(abs(cw[0]-at)>=76 for at in allacc):pool.append(cw)
            for metric in METRICS:
                val=w[2][metric];values=[v[2][metric] for v in pool if v[2][metric] is not None]
                pct=(sum(v<val for v in values)+.5*sum(v==val for v in values))/len(values) if val is not None and len(values)>=15 else None
                old=expected[(aid,metric)];oldpct=float(old['percentile']) if old['percentile'] else None
                error=abs(pct-oldpct) if pct is not None and oldpct is not None else None
                rec={'acc_id':aid,'rfid_id':rid,'tier':int(e['tier']),'metric':metric,'value':val,'n_ctrl':len(values),'percentile':pct,
                  'source_percentile':oldpct,'percentile_abs_error':error,'eligibility_matches':(pct is not None)==(oldpct is not None)}
                rebuilt.append(rec)
                if not rec['eligibility_matches'] or (error is not None and error>1e-9):differences.append(rec)
            if len(pool)>=15:
                for s in STATES:state_events.append({'acc_id':aid,'rfid_id':rid,'tier':int(e['tier']),'cause':e['발생유형'],'metric':s,
                    'a':int(w[3][s]),'n_controls':len(pool),'control_positive_count':sum(v[3][s] for v in pool)})
    result={'status':'completed','actual_raw_metrics_rebuilt':True,'n_selected_rows':sum(map(len,groups.values())),
      'n_vessels':len(groups),'n_event_metric_records':len(rebuilt),'n_mismatches':len(differences),
      'max_percentile_error':max((r['percentile_abs_error'] or 0 for r in rebuilt),default=0),
      'mismatches':differences,'records':rebuilt,'state_events':state_events,
      'input_columns':columns,'guard_centers_h':76,'min_controls':15,'hod_circular_h':1,
      'reuse_note':'does not import build_vessel/ctrl_mask/pct_rank or either producer; deliberately independent verifier'}
    save('t3_raw_recompute.json',result);return result

def exact_matched_set(records,k=6):
    """1:M conditional exact binary test; M=1 reduces to exact McNemar.
    Working model assumes independent matched sets despite repeated vessels and
    overlapping windows: those dependence limitations are explicit.
    """
    probabilities=[(r['a']+r['control_positive_count'])/(r['n_controls']+1) for r in records]
    observed=sum(r['a'] for r in records);pdf=[1.]
    for q in probabilities:
        new=[0.]*(len(pdf)+1)
        for i,p in enumerate(pdf):new[i]+=p*(1-q);new[i+1]+=p*q
        pdf=new
    threshold=pdf[observed];p=min(1.,sum(x for x in pdf if x<=threshold+max(1e-15,threshold*1e-12)))
    return {'n_events':len(records),'acc_positive_count':observed,'acc_rate':observed/len(records),
      'control_rate_event_weighted':statistics.mean(r['control_positive_count']/r['n_controls'] for r in records),
      'conditional_exact_p':p,'bonferroni_K':k,'p_bonferroni':min(1.,k*p),
      'method':'1_to_M_conditional_exact_matched_set_Poisson_binomial',
      'limitations':'posthoc methodological repair; independent matched-set working assumption; repeated vessels/overlapping windows unadjusted'}

def state_supplement(raw):
    events=raw.get('state_events')
    if events is None:
        # Recover integer counts from producer's per-event q only as fallback;
        # this is not represented as independent raw data reconstruction.
        events=[]
        for file in sorted(C.glob('t2_checkpoint_*.json')):
            for r in read(file)['state_events']:
                if r['half_width_h']==3 and r['design']=='hod_1/nrows_matched' and r['exclusion'] is None:
                    m=r['n_ctrl_finite'];k=round(r['ctrl_positive_rate']*m)
                    assert abs(k-r['ctrl_positive_rate']*m)<1e-8
                    events.append({'acc_id':r['acc_id'],'rfid_id':r['rfid_id'],'tier':r['tier'],'cause':r['cause'],'metric':r['metric'],'a':int(r['acc_value']>0),'n_controls':m,'control_positive_count':k})
    # Direct drift differs between producers; this supplement uses the explicit
    # Codex >=2h elapsed / density definition and is labelled producer-derived.
    for file in sorted(C.glob('t2_checkpoint_*.json')):
        for r in read(file)['drift_events']:
            if r['half_width_h']==3 and r['design']=='hod_1/nrows_matched' and r['exclusion'] is None:
                m=r['n_ctrl_finite'];k=round(r['ctrl_positive_rate']*m)
                assert abs(k-r['ctrl_positive_rate']*m)<1e-8
                events.append({'acc_id':r['acc_id'],'rfid_id':r['rfid_id'],'tier':r['tier'],'cause':r['cause'],'metric':'direct_drift','a':int(r['acc_value']>0),'n_controls':m,'control_positive_count':k})
    output=[];cb=read(C/'t2_state_distribution.json')
    for metric in STATES+['direct_drift']:
        for s in ['ALL','Tier0_1','기관손상']:
            rr=[r for r in events if r['metric']==metric and (s=='ALL' or (s=='Tier0_1' and r['tier']<=1) or (s=='기관손상' and r['cause']==s))]
            v=exact_matched_set(rr);v.update(metric=metric,stratum=s,
                evidence_source='producer event counts' if metric=='direct_drift' or not raw.get('actual_raw_metrics_rebuilt') else 'independent raw scan')
            original=next(x for x in cb['results'] if x['metric']==metric and x['stratum']==s and x['half_width_h']==3 and x['design']=='hod_1/nrows_matched')
            v.update(mde80_positive_rate_approx=original['mde80_positive_rate_approx'],ci95_positive_rate=original['ci95_positive_rate'],
              mde_note='expected-discordance normal planning approximation from event counts; not exact power of this repaired conditional test')
            output.append(v)
    ca=read(C/'t1_gate_results.json');still=[]
    with (C/'t1_event_percentiles.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['half_width_h']=='3' and r['design']=='hod_1/nrows_matched' and r['metric']=='still_frac' and not r['exclusion']:
                m=int(r['n_ctrl_finite']);q=float(r['ctrl_positive_rate']);k=round(q*m);assert abs(k-q*m)<1e-8
                still.append({'tier':int(r['tier']),'a':int(float(r['acc_value'])>0),'n_controls':m,'control_positive_count':k})
    still_output=[]
    for s in ['ALL','Tier0_1']:
        rr=[r for r in still if s=='ALL' or r['tier']<=1];v=exact_matched_set(rr,7)
        original=next(g['primary'] for g in ca['gates'] if g['metric']=='still_frac' and g['stratum']==s)
        v.update(metric='still_frac',stratum=s,mde80_positive_rate_approx=original['mde80_positive_rate_approx'],ci95_positive_rate=original['ci95_positive_rate'])
        still_output.append(v)
    # Verify reduction to ordinary exact McNemar without any fractional rounding.
    fixture=[{'a':1,'control_positive_count':0,'n_controls':1}]*7+[{'a':0,'control_positive_count':1,'n_controls':1}]*2
    check=exact_matched_set(fixture)['conditional_exact_p'];expected=2*sum(math.comb(9,j) for j in range(3))/2**9
    assert abs(check-expected)<1e-12
    save('t3_matched_set_binary.json',{'source':'independent raw reconstruction' if raw.get('actual_raw_metrics_rebuilt') else 'producer integer-count reconstruction; no raw independence claim',
      'method_note':'posthoc 1:M conditional matched-set extension, not silently renamed original McNemar',
      'McNemar_reduction_fixture':{'p':check,'expected':expected,'passed':True},'results':output,'T1_still_frac_supplement':still_output})

def main():
    event=event_evidence_audit()
    if '--evidence-only' in sys.argv:
        raw=read(P/'t3_raw_recompute.json') if (P/'t3_raw_recompute.json').exists() else {'status':'deferred_memory','actual_raw_metrics_rebuilt':False}
    else:raw=raw_audit()
    state_supplement(raw)
    save('t3_verification.json',{'same_operator':True,'separate_session_reviewer':False,
      'implementation_independence':True,'event_summary_recomputations':event,
      'raw_status':{k:v for k,v in raw.items() if k not in ['records','state_events']},
      'statistics_match':all(r['delta_abs_error']<1e-12 and r['wilcoxon_abs_error']<1e-8 for r in event),
      'source_gate_audit_pending_report':True})
    print(json.dumps({'raw_status':raw['status'],'event_recomputations':len(event),'raw_mismatches':raw.get('n_mismatches')},ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc();sys.exit(1)
