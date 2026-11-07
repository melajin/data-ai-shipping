from __future__ import annotations
import csv, datetime as dt, json, math, os, pathlib, statistics, time
import numpy as np
import pandas as pd
import psutil

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'testB' / 'first_results'
OUT = ROOT / 'testB' / 'next_analysis_20261105'
COMPONENTS = ['s_zone', 's_change', 's_gap']
START = time.perf_counter()
PROC = psutil.Process(os.getpid())

def jsafe(x):
    if x is None:
        return None
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, (np.bool_, bool)): return bool(x)
    return x

def label(row):
    date, hour = row.get('part_dt'), row.get('rfid_time')
    if pd.isna(date) or pd.isna(hour): return None
    try: return f'{int(date):08d} {int(hour)}'
    except (ValueError, TypeError, OverflowError): return None

def finite_value(v):
    try: return math.isfinite(float(v))
    except (TypeError, ValueError): return False

def peak_info(g, comp):
    valid = g[g[comp].map(finite_value)]
    nvalid = len(valid)
    missing = len(g) - nvalid
    if nvalid == 0:
        return {'status':'no_valid_component','valid_rows':0,'missing_rows':missing,'max_tie_count':0,'unique_tied_timestamp_count':0,'unique_valid_value_count':0,'constant_valid_component':False,'peak_value':None,'peak_time':None,'peak_ts':None,'peak_source_ordinal':None,'peak_row_index':None,'peak_source_month':None,'peak_source_file':None,'peak':None,'tied_rows':None}
    mx = float(valid[comp].max())
    ties = valid[valid[comp] == mx].sort_values('source_ordinal',kind='stable')
    pk = ties.iloc[0]
    tied_ts = ties['ts'].dropna().unique() if 'ts' in ties else []
    nunique = int(valid[comp].nunique(dropna=True))
    return {'status':'available','valid_rows':nvalid,'missing_rows':missing,'max_tie_count':len(ties),'unique_tied_timestamp_count':len(tied_ts),'unique_valid_value_count':nunique,'constant_valid_component':nunique==1,'peak_value':mx,'peak_time':label(pk),'peak_ts':int(pk['ts']) if pd.notna(pk['ts']) else None,'peak_source_ordinal':int(pk['source_ordinal']) if pd.notna(pk['source_ordinal']) else None,'peak_row_index':int(pk['row_index']) if pd.notna(pk['row_index']) else None,'peak_source_month':int(pk['source_month']) if pd.notna(pk['source_month']) else None,'peak_source_file':str(pk['source_file']) if pd.notna(pk['source_file']) else None,'peak':pk,'tied_rows':ties}

def a_component(g, comp):
    row = g[g['source_ordinal'] == int(g['_A_ordinal'].iloc[0])]
    if len(row) != 1: return None
    v=row.iloc[0][comp]
    return float(v) if finite_value(v) else None

def delta_info(pk, a):
    if pk is None or a is None or pd.isna(pk['ts']) or pd.isna(a['ts']):
        return {'signed_delta_hours':None,'absolute_delta_hours':None,'same_time':None,'within_6h_inclusive':None}
    delta = int(pk['ts']) - int(a['ts'])
    return {'signed_delta_hours':delta,'absolute_delta_hours':abs(delta),'same_time':delta == 0,'within_6h_inclusive':abs(delta) <= 6}

def peak_score_ties(g):
    vals = g['score'].map(lambda x: float(x) if finite_value(x) else np.nan)
    valid=vals[np.isfinite(vals)]
    return int((vals == valid.max()).sum()) if len(valid) else 0

def counter_template():
    return {'available_vessels':0,'unavailable_vessels':0,'exact_same_time':0,'different_time':0,'same_source_row':0,'different_source_row':0,'within_6h_inclusive':0,'outside_6h':0,'earlier_than_A':0,'later_than_A':0,'comparable_time_delta_vessels':0,'median_absolute_delta_hours':None,'max_absolute_delta_hours':None,'valid_rows':0,'missing_rows':0,'vessels_with_exact_max_tie':0,'vessels_with_constant_valid_component':0,'vessels_with_zero_valued_peak':0,'exact_max_tie_rows':0}

def peak_memory_mib():
    mi=PROC.memory_info()
    v=getattr(mi,'peak_wset',None)
    if v is not None: return round(v/1024**2,1)
    try:
        return round(PROC.memory_full_info().peak_wset/1024**2,1)
    except Exception: return None

def run_aggregation_preflight():
    preflight_path = OUT / 'aggregation_preflight.json'
    initial = None
    if preflight_path.exists():
        initial = json.loads(preflight_path.read_text(encoding='utf-8'))
        # Keep the prior preparation snapshot without retaining command-line arguments.
        for process in initial.get('concurrent_large_processes', []):
            process.pop('cmdline', None)
    now_local = dt.datetime.now().astimezone()
    now_utc = dt.datetime.now(dt.timezone.utc)
    available = psutil.virtual_memory().available
    threshold_mib = 128
    large_processes = []
    for process in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            rss = process.info['memory_info'].rss
            if rss >= threshold_mib * 1024**2:
                large_processes.append({'pid': process.info['pid'], 'name': process.info['name'], 'rss_mib': round(rss / 1024**2, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    large_processes.sort(key=lambda item: item['rss_mib'], reverse=True)
    peak_estimate_mib = 512
    reserve_mib = 640
    record = {
        'recorded_local': now_local.isoformat(timespec='seconds'),
        'recorded_utc': now_utc.isoformat(timespec='seconds'),
        'psutil_available_ram_mib': round(available / 1024**2, 1),
        'estimated_process_peak_mib': peak_estimate_mib,
        'reserve_mib': reserve_mib,
        'adequate_for_estimate_plus_reserve': available >= (peak_estimate_mib + reserve_mib) * 1024**2,
        'estimate_basis': 'Task estimate for pandas/Arrow and copies aggregating 46,705 x 20; 640 MiB reserve follows the existing Test B preflight convention.',
        'concurrent_large_processes_threshold_mib': threshold_mib,
        'concurrent_large_processes': large_processes,
        'inputs_expected': ['testB/first_results/hourly_scores.parquet', 'testB/first_results/candidate_A.csv', 'testB/first_results/results.json'],
        'execution_policy': 'Single sequential aggregation process; no run.py execution or import.',
    }
    if initial is not None:
        record['initial_preparation_check'] = initial
    preflight_path.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    if not record['adequate_for_estimate_plus_reserve']:
        raise RuntimeError(f"Insufficient available RAM: {record['psutil_available_ram_mib']} MiB; require at least {peak_estimate_mib + reserve_mib} MiB including reserve.")
    return record

# Fresh memory check occurs before opening any baseline data.
PREFLIGHT = run_aggregation_preflight()

# Required reusable inputs only; no scorer import or execution.
candidates = pd.read_csv(SRC/'candidate_A.csv', dtype={'rfid_id':'string'}, keep_default_na=False)
results_baseline = json.loads((SRC/'results.json').read_text(encoding='utf-8'))
df = pd.read_parquet(SRC/'hourly_scores.parquet', columns=['rfid_id','part_dt','rfid_time','row_index','source_month','source_file','source_ordinal','ts','s_zone','s_change','s_gap','score'])
df['rfid_id'] = df['rfid_id'].astype('string')
if list(candidates['rfid_id']) != list(dict.fromkeys(candidates['rfid_id'])):
    raise ValueError('candidate IDs are not unique')
if len(candidates) != 100 or len(df) != 46705 or set(df.rfid_id) != set(candidates.rfid_id):
    raise ValueError('input dimensions or IDs differ from the stated baseline')

# Map each candidate A row by the provided string ID and source ordinal.
lookup = {}
records=[]
for c in candidates.itertuples(index=False):
    rid=str(c.rfid_id); ordinal=int(c.source_ordinal)
    g=df[df.rfid_id == rid].copy()
    arows=g[g.source_ordinal == ordinal]
    if len(arows) != 1: raise ValueError(f'A row not unique for {rid}')
    a=arows.iloc[0]
    g['_A_ordinal']=ordinal
    lookup[rid]={'group':g,'a':a,'candidate':c}

for ci, c in enumerate(candidates.itertuples(index=False)):
    rid=str(c.rfid_id); g=lookup[rid]['group']; a=lookup[rid]['a']
    n=len(g)
    # Source ordering for previous observed row follows baseline scoring sort.
    ordered=g.sort_values(['ts','rfid_time','source_ordinal'],kind='stable',na_position='last').reset_index(drop=True)
    arow={
      'rfid_id':rid,'n_rows':n,'single_row':n==1,'rows_under_25':n<25,
      'A_time':label(a),'A_ts':int(a['ts']) if pd.notna(a['ts']) else None,
      'A_source_ordinal':int(a['source_ordinal']),'A_score':float(a['score']) if finite_value(a['score']) else None,
      'A_score_max_tie_count':peak_score_ties(g),
      'A_score_floor_1e_6':bool(finite_value(a['score']) and float(a['score'])==1e-6),
      'A_s_zone':float(a['s_zone']) if finite_value(a['s_zone']) else None,
      'A_s_change':float(a['s_change']) if finite_value(a['s_change']) else None,
      'A_s_gap':float(a['s_gap']) if finite_value(a['s_gap']) else None,
      'A_s_zone_missing':not finite_value(a['s_zone']),
      'A_s_change_missing':not finite_value(a['s_change']),
      'A_s_gap_missing':not finite_value(a['s_gap']),
      'A_finite_component_count':sum(finite_value(a[x]) for x in COMPONENTS),
      'candidate_A_time':str(c.A),'candidate_A_score':float(c.score),
      'candidate_A_row_match':int(c.source_ordinal)==int(a['source_ordinal']) and math.isclose(float(c.score),float(a['score']),rel_tol=0.0,abs_tol=1e-12),
      'no_valid_change':not any(finite_value(v) for v in g.s_change),
    }
    # Candidate ordinal/time must match; serialized score is compared within 1e-12 absolute tolerance.
    if not arow['candidate_A_row_match'] or str(c.A) != label(a):
        raise ValueError(f'candidate A does not match persisted score row for {rid}')
    any_time=[]; all_time=[]; peaks={}
    for comp in COMPONENTS:
        p=peak_info(g,comp); peaks[comp]=p
        delta=delta_info(p['peak'],a)
        if p['status']=='available': any_time.append(delta['same_time'])
        if delta['same_time'] is not None: all_time.append(delta['same_time'])
        arow.update({f'{comp}_valid_rows':p['valid_rows'],f'{comp}_missing_rows':p['missing_rows'],f'{comp}_status':p['status'],f'{comp}_peak_value':p['peak_value'],f'{comp}_peak_time':p['peak_time'],f'{comp}_peak_source_ordinal':p['peak_source_ordinal'],f'{comp}_peak_row_index':p['peak_row_index'],f'{comp}_peak_source_month':p['peak_source_month'],f'{comp}_peak_source_file':p['peak_source_file'],f'{comp}_max_tie_count':p['max_tie_count'],f'{comp}_unique_tied_timestamp_count':p['unique_tied_timestamp_count'],f'{comp}_unique_valid_value_count':p['unique_valid_value_count'],f'{comp}_constant_valid_component':p['constant_valid_component'],f'{comp}_peak_is_zero':(p['peak_value']==0.0) if p['peak_value'] is not None else None,f'{comp}_A_value':arow[f'A_{comp}'],f'{comp}_peak_minus_A_value':(p['peak_value']-arow[f'A_{comp}']) if p['peak_value'] is not None and arow[f'A_{comp}'] is not None else None, f'{comp}_signed_delta_hours':delta['signed_delta_hours'],f'{comp}_absolute_delta_hours':delta['absolute_delta_hours'],f'{comp}_same_time':delta['same_time'],f'{comp}_same_source_row':(p['peak_source_ordinal']==int(a['source_ordinal'])) if p['peak_source_ordinal'] is not None else None,f'{comp}_within_6h_inclusive':delta['within_6h_inclusive']})
        if comp=='s_gap' and p['peak'] is not None:
            pk=p['peak']; pkord=int(pk.source_ordinal)
            pos=ordered.index[ordered.source_ordinal == pkord]
            prevrow=ordered.iloc[int(pos[0])-1] if len(pos) and int(pos[0])>0 else None
            arow.update({'s_gap_previous_time':label(prevrow) if prevrow is not None else None,'s_gap_previous_source_ordinal':int(prevrow.source_ordinal) if prevrow is not None and pd.notna(prevrow.source_ordinal) else None,'s_gap_elapsed_observed_gap_hours':int(pk.ts)-int(prevrow.ts) if prevrow is not None and pd.notna(pk.ts) and pd.notna(prevrow.ts) else None})
        elif comp=='s_gap':
            arow.update({'s_gap_previous_time':None,'s_gap_previous_source_ordinal':None,'s_gap_elapsed_observed_gap_hours':None})
    arow['all_three_components_available'] = all(peaks[x]['status']=='available' for x in COMPONENTS)
    arow['all_three_peak_times_equal'] = (len(all_time)==3 and len(set([peaks[x]['peak_ts'] for x in COMPONENTS]))==1) if arow['all_three_components_available'] else None
    arow['A_equals_any_peak_time'] = any(v is True for v in any_time) if any_time else None
    arow['A_equals_all_available_peak_times'] = all(v is True for v in any_time) if any_time else None
    records.append(arow)

outdf=pd.DataFrame(records)
# Summaries with explicit comparable denominators and integer-only category counts.
summary={'baseline':{'vessels':len(candidates),'scored_rows':len(df),'results_json_target_vessels':results_baseline.get('target_vessels'),'results_json_scored_rows':results_baseline.get('scored_rows')},'row_counts':{'total_rows':len(df),'finite_score_rows':int(df.score.map(finite_value).sum()),'valid_and_missing_rows_by_component':{}},'vessel_counts':{'total':len(candidates),'single_row':int(outdf.single_row.sum()),'rows_under_25':int(outdf.rows_under_25.sum()),'no_valid_change':int(outdf.no_valid_change.sum()),'A_score_floor_1e_6':int((outdf.A_score==1e-6).sum()),'A_score_max_tie_vessels':int((outdf.A_score_max_tie_count>1).sum()),'A_candidate_row_score_matches':int(outdf.candidate_A_row_match.sum()),'candidate_A_score_match_absolute_tolerance':1e-12,'A_missing_components':{c:int(outdf[f'A_{c}_missing'].sum()) for c in COMPONENTS},'all_three_components_available':int(outdf.all_three_components_available.sum()),'all_three_peak_times_equal_among_available':int((outdf.all_three_peak_times_equal==True).sum()),'A_equals_any_peak_time':int((outdf.A_equals_any_peak_time==True).sum()),'A_equals_all_available_peak_times':int((outdf.A_equals_all_available_peak_times==True).sum()),'low_information_under_25':int(outdf.rows_under_25.sum()),'remaining_at_least_25':int((~outdf.rows_under_25).sum())},'components':{},'low_information_stratum_comparison':{'stratum_definition':'n_rows < 25; remaining means n_rows >= 25','under_25_vessels':{},'at_least_25_vessels':{}},'examples':{},'interpretation_limit':'Component peak timing comparisons are descriptive internal diagnostics only, not accident hit rates, competition performance, or accident probabilities. 2026 accident records are not 2025 ground truth; accident-RFID identities remain candidates.'}
equal_rows=outdf[(outdf.all_three_components_available==True)&(outdf.all_three_peak_times_equal==True)].sort_values('rfid_id')
summary['all_three_peak_time_equal_vessels']=[{'rfid_id':str(r.rfid_id),'n_rows':int(r.n_rows),'component_peak_time':str(r.s_zone_peak_time),'A_time':str(r.A_time) if pd.notna(r.A_time) else None,'A_equals_any_peak_time':bool(r.A_equals_any_peak_time),'A_equals_all_available_peak_times':bool(r.A_equals_all_available_peak_times)} for r in equal_rows.itertuples(index=False)]
ties=outdf[outdf.s_zone_max_tie_count>1].sort_values(['s_zone_max_tie_count','rfid_id'],ascending=[False,True])
if len(ties):
    t=ties.iloc[0]
    summary['s_zone_tie_example']={'rfid_id':str(t.rfid_id),'n_rows':int(t.n_rows),'s_zone_peak_value':float(t.s_zone_peak_value),'s_zone_max_tie_count':int(t.s_zone_max_tie_count),'s_zone_unique_tied_timestamp_count':int(t.s_zone_unique_tied_timestamp_count),'chosen_source_ordinal':int(t.s_zone_peak_source_ordinal),'chosen_peak_time':str(t.s_zone_peak_time)}
else:
    summary['s_zone_tie_example']=None
requested=[]
for wanted in ['31010758','36011779','36012931','34400012']:
    matches=outdf[outdf.rfid_id.astype(str)==wanted]
    if len(matches)!=1: raise ValueError(f'Requested vessel missing or nonunique: {wanted}')
    r=matches.iloc[0]
    requested.append({'rfid_id':wanted,'n_rows':int(r.n_rows),'A_time':r.A_time,'A_source_ordinal':int(r.A_source_ordinal),'A_score':float(r.A_score) if pd.notna(r.A_score) else None,'A_score_floor_1e_6':bool(r.A_score_floor_1e_6),'A_s_zone':float(r.A_s_zone) if pd.notna(r.A_s_zone) else None,'A_s_change':float(r.A_s_change) if pd.notna(r.A_s_change) else None,'A_s_gap':float(r.A_s_gap) if pd.notna(r.A_s_gap) else None,'s_zone_peak_time':r.s_zone_peak_time,'s_zone_peak_value':float(r.s_zone_peak_value) if pd.notna(r.s_zone_peak_value) else None,'s_zone_signed_delta_hours':jsafe(r.s_zone_signed_delta_hours),'s_change_peak_time':r.s_change_peak_time,'s_change_peak_value':float(r.s_change_peak_value) if pd.notna(r.s_change_peak_value) else None,'s_change_signed_delta_hours':jsafe(r.s_change_signed_delta_hours),'s_gap_peak_time':r.s_gap_peak_time,'s_gap_peak_value':float(r.s_gap_peak_value) if pd.notna(r.s_gap_peak_value) else None,'s_gap_signed_delta_hours':jsafe(r.s_gap_signed_delta_hours),'s_gap_previous_time':r.s_gap_previous_time,'s_gap_previous_source_ordinal':jsafe(r.s_gap_previous_source_ordinal),'s_gap_elapsed_observed_gap_hours':jsafe(r.s_gap_elapsed_observed_gap_hours)})
summary['requested_records']=requested
for comp in COMPONENTS:
    p=peaks=None
    summary['row_counts']['valid_and_missing_rows_by_component'][comp]={'valid_rows':int(outdf[f'{comp}_valid_rows'].sum()),'missing_rows':int(outdf[f'{comp}_missing_rows'].sum()),'denominator_rows':len(df)}
    c=counter_template(); absd=[]
    for _,r in outdf.iterrows():
        c['valid_rows']+=int(r[f'{comp}_valid_rows']); c['missing_rows']+=int(r[f'{comp}_missing_rows'])
        if r[f'{comp}_status']=='available':
            c['available_vessels']+=1
            if r[f'{comp}_max_tie_count']>1: c['vessels_with_exact_max_tie']+=1
            if bool(r[f'{comp}_constant_valid_component']): c['vessels_with_constant_valid_component']+=1
            if r[f'{comp}_peak_is_zero']: c['vessels_with_zero_valued_peak']+=1
            c['exact_max_tie_rows']+=int(r[f'{comp}_max_tie_count'])
            if r[f'{comp}_same_time'] is not None:
                if r[f'{comp}_same_time']: c['exact_same_time']+=1
                else: c['different_time']+=1
            if r[f'{comp}_same_source_row'] is not None:
                if r[f'{comp}_same_source_row']: c['same_source_row']+=1
                else: c['different_source_row']+=1
            d=r[f'{comp}_signed_delta_hours']
            if d is not None:
                c['comparable_time_delta_vessels']+=1; absd.append(abs(int(d)))
                if abs(int(d))<=6: c['within_6h_inclusive']+=1
                else: c['outside_6h']+=1
                if int(d)<0: c['earlier_than_A']+=1
                elif int(d)>0: c['later_than_A']+=1
        else: c['unavailable_vessels']+=1
    c['median_absolute_delta_hours']=float(statistics.median(absd)) if absd else None
    c['max_absolute_delta_hours']=max(absd) if absd else None
    c['denominator_vessels']=len(candidates)
    c['comparable_time_denominator_vessels']=c['comparable_time_delta_vessels']
    c['same_different_time_denominator_vessels']=c['exact_same_time']+c['different_time']
    c['same_different_row_denominator_vessels']=c['same_source_row']+c['different_source_row']
    c['within_outside_6h_denominator_vessels']=c['within_6h_inclusive']+c['outside_6h']
    c['direction_denominator_vessels']=c['comparable_time_delta_vessels']
    c['delta_statistics_denominator_vessels']=c['comparable_time_delta_vessels']
    summary['components'][comp]=c
    for key, predicate in [('under_25_vessels',lambda r:bool(r.rows_under_25)),('at_least_25_vessels',lambda r:not bool(r.rows_under_25))]:
        sub=outdf[outdf.apply(predicate,axis=1)]
        comparable=int(sub[f'{comp}_absolute_delta_hours'].notna().sum())
        summary['low_information_stratum_comparison'][key][comp]={'vessels':len(sub),'available':int((sub[f'{comp}_status']=='available').sum()),'A_same_time':int((sub[f'{comp}_same_time']==True).sum()),'A_same_time_denominator_vessels':comparable,'within_6h_inclusive':int((sub[f'{comp}_within_6h_inclusive']==True).sum()),'within_6h_denominator_vessels':comparable,'different_time':int((sub[f'{comp}_same_time']==False).sum()),'different_time_denominator_vessels':comparable}

# Reproducible examples: largest available absolute delta, multi-way equal peaks with >=25 rows, one-row/floor.
usable=[]
for _,r in outdf.iterrows():
    ds=[r[f'{c}_absolute_delta_hours'] for c in COMPONENTS if r[f'{c}_absolute_delta_hours'] is not None]
    if ds: usable.append((max(ds),str(r.rfid_id)))
if usable:
    _,rid=max(usable,key=lambda z:(z[0],z[1]))
    r=outdf[outdf.rfid_id==rid].iloc[0]
    summary['examples']['largest_component_A_time_disagreement']={'rfid_id':rid,'n_rows':int(r.n_rows),'A_time':r.A_time,'A_source_ordinal':int(r.A_source_ordinal),'components':{c:{'peak_time':r[f'{c}_peak_time'],'signed_delta_hours':r[f'{c}_signed_delta_hours'],'absolute_delta_hours':r[f'{c}_absolute_delta_hours'],'peak_source_ordinal':r[f'{c}_peak_source_ordinal']} for c in COMPONENTS if r[f'{c}_status']=='available'}}
coal=outdf[(outdf.all_three_components_available==True)&(outdf.all_three_peak_times_equal==True)&(outdf.n_rows>=25)]
if len(coal):
    r=coal.sort_values(['n_rows','rfid_id'],ascending=[False,True]).iloc[0]
    summary['examples']['three_component_peak_time_agreement']={'rfid_id':str(r.rfid_id),'n_rows':int(r.n_rows),'A_time':r.A_time,'component_peak_time':r.s_zone_peak_time,'A_equals_any_peak_time':bool(r.A_equals_any_peak_time),'A_equals_all_available_peak_times':bool(r.A_equals_all_available_peak_times)}
one=outdf[(outdf.single_row==True)|(outdf.A_score==1e-6)]
if len(one):
    r=one.sort_values(['single_row','A_score','rfid_id'],ascending=[False,True,True]).iloc[0]
    summary['examples']['one_row_or_floor_case']={'rfid_id':str(r.rfid_id),'n_rows':int(r.n_rows),'single_row':bool(r.single_row),'A_score':float(r.A_score),'A_time':r.A_time,'component_peak_times':{c:r[f'{c}_peak_time'] for c in COMPONENTS}}

# Convert NumPy/Pandas scalars and ensure strict JSON null semantics.
summary=json.loads(json.dumps(summary,default=jsafe,allow_nan=False))
# Output field values are scalar and nullable; CSV writes blanks for None/NaN.
outdf.to_csv(OUT/'component_time_comparison.csv',index=False,encoding='utf-8-sig',na_rep='')
(OUT/'analysis_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

# One small persisted-output read: verify row order/uniqueness and representative values against input in memory.
check=pd.read_csv(OUT/'component_time_comparison.csv',dtype={'rfid_id':'string'})
assert len(check)==100 and check.rfid_id.is_unique and list(check.rfid_id.astype(str))==list(candidates.rfid_id.astype(str))
assert 'A_score_floor_1e_6' in check.columns and list(check['A_score_floor_1e_6'].astype(bool))==list(outdf['A_score_floor_1e_6'].astype(bool))
for rid in [summary['examples'].get('largest_component_A_time_disagreement',{}).get('rfid_id'),summary['examples'].get('three_component_peak_time_agreement',{}).get('rfid_id'),summary['examples'].get('one_row_or_floor_case',{}).get('rfid_id'),*[r['rfid_id'] for r in summary['requested_records']]]:
    if rid is None: continue
    rr=check[check.rfid_id==rid].iloc[0]
    src=lookup[rid]['a']
    assert int(rr.A_source_ordinal)==int(src.source_ordinal)
    assert float(rr.A_score)==float(src.score)
    assert bool(rr.A_score_floor_1e_6)==(finite_value(src.score) and float(src.score)==1e-6)
    for comp in COMPONENTS:
        expected=float(src[comp]) if finite_value(src[comp]) else None
        got=rr[f'A_{comp}']
        if expected is None: assert pd.isna(got)
        else: assert math.isclose(float(got),expected,rel_tol=0.0,abs_tol=1e-15)
# Summary arithmetic identities over the fixed 100-vessel / 46,705-row denominators.
assert summary['vessel_counts']['single_row']<=100 and summary['vessel_counts']['rows_under_25']<=100
for comp in COMPONENTS:
    sc=summary['components'][comp]
    assert sc['available_vessels']+sc['unavailable_vessels']==100
    assert sc['valid_rows']+sc['missing_rows']==46705
    assert sc['exact_same_time']+sc['different_time']==sc['same_different_time_denominator_vessels']
    assert sc['same_source_row']+sc['different_source_row']==sc['same_different_row_denominator_vessels']
    assert sc['within_6h_inclusive']+sc['outside_6h']==sc['within_outside_6h_denominator_vessels']
    assert sc['earlier_than_A']+sc['later_than_A']+sc['exact_same_time']==sc['comparable_time_delta_vessels']
assert summary['vessel_counts']['A_candidate_row_score_matches']==100

# Technical fact sheet only; no causal or accident-performance interpretation.
lines=['# Component timing aggregation facts','',f"Generated: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}",'','This is a descriptive aggregation of the existing Test B baseline. It does not evaluate accident hits, competition performance, or accident probabilities. 2026 accident records are not 2025 ground truth; accident-RFID identities remain candidates.','',f"Denominators: {len(candidates)} vessels; {len(df):,} scored rows.",'','## Component summary','','| Component | Available / 100 | Unavailable / 100 | Same time / comparable | Different time / comparable | Same row / comparable | Different row / comparable | Within ±6h / comparable | Outside ±6h / comparable | Earlier / comparable | Later / comparable | Median abs h / comparable | Max abs h / comparable | Valid rows / 46,705 | Missing rows / 46,705 | Exact-max tie vessels / 100 | All-valid-constant vessels / 100 | Zero-valued peak vessels / available |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for comp, s in summary['components'].items():
    lines.append(f"| {comp} | {s['available_vessels']} | {s['unavailable_vessels']} | {s['exact_same_time']} / {s['same_different_time_denominator_vessels']} | {s['different_time']} / {s['same_different_time_denominator_vessels']} | {s['same_source_row']} / {s['same_different_row_denominator_vessels']} | {s['different_source_row']} / {s['same_different_row_denominator_vessels']} | {s['within_6h_inclusive']} / {s['within_outside_6h_denominator_vessels']} | {s['outside_6h']} / {s['within_outside_6h_denominator_vessels']} | {s['earlier_than_A']} / {s['direction_denominator_vessels']} | {s['later_than_A']} / {s['direction_denominator_vessels']} | {s['median_absolute_delta_hours']} / {s['delta_statistics_denominator_vessels']} | {s['max_absolute_delta_hours']} / {s['delta_statistics_denominator_vessels']} | {s['valid_rows']} | {s['missing_rows']} | {s['vessels_with_exact_max_tie']} | {s['vessels_with_constant_valid_component']} | {s['vessels_with_zero_valued_peak']} / {s['available_vessels']} |")
lines += ['', '## Other counts','',f"- Single-row vessels: {summary['vessel_counts']['single_row']} / 100.",f"- Vessels with fewer than 25 rows: {summary['vessel_counts']['rows_under_25']} / 100.",f"- No valid `s_change`: {summary['vessel_counts']['no_valid_change']} / 100.",f"- A at score floor 1e-6: {summary['vessel_counts']['A_score_floor_1e_6']} / 100.",f"- A score has exact max ties: {summary['vessel_counts']['A_score_max_tie_vessels']} / 100.",f"- A missing components: {summary['vessel_counts']['A_missing_components']}.",f"- All three component peaks available: {summary['vessel_counts']['all_three_components_available']} / 100; among these all three peak times equal: {summary['vessel_counts']['all_three_peak_times_equal_among_available']}.",f"- A equals any available component peak time: {summary['vessel_counts']['A_equals_any_peak_time']} / 100; equals all available peak times: {summary['vessel_counts']['A_equals_all_available_peak_times']} / 100.",f"- Candidate A row and score match: {summary['vessel_counts']['A_candidate_row_score_matches']} / 100 (score absolute tolerance {summary['vessel_counts']['candidate_A_score_match_absolute_tolerance']}; ordinal and time exact).",'','## Reproducible examples','']
for key, example in summary['examples'].items(): lines += [f"### {key}",'',json.dumps(example,ensure_ascii=False,indent=2),'']
lines += ['### All-three component peak-time equal vessels','','| RFID | Rows | Peak time | A time | A equals any | A equals all available |','|---|---:|---|---|---|---|']
for r in summary['all_three_peak_time_equal_vessels']:
    lines.append(f"| {r['rfid_id']} | {r['n_rows']} | {r['component_peak_time']} | {r['A_time']} | {r['A_equals_any_peak_time']} | {r['A_equals_all_available_peak_times']} |")
lines += ['', '### Concrete s_zone exact-tie example','',json.dumps(summary['s_zone_tie_example'],ensure_ascii=False,indent=2),'','### Requested comparison CSV rows','','| RFID | Rows | A time | A score | A floor | A components (zone/change/gap) | Peak times (zone/change/gap) | Peak deltas h (zone/change/gap) | Gap previous time | Previous ordinal | Elapsed observed gap h |','|---|---:|---|---:|---|---|---|---|---|---:|---:|']
for r in summary['requested_records']:
    lines.append(f"| {r['rfid_id']} | {r['n_rows']} | {r['A_time']} | {r['A_score']} | {r['A_score_floor_1e_6']} | {r['A_s_zone']} / {r['A_s_change']} / {r['A_s_gap']} | {r['s_zone_peak_time']} / {r['s_change_peak_time']} / {r['s_gap_peak_time']} | {r['s_zone_signed_delta_hours']} / {r['s_change_signed_delta_hours']} / {r['s_gap_signed_delta_hours']} | {r['s_gap_previous_time']} | {r['s_gap_previous_source_ordinal']} | {r['s_gap_elapsed_observed_gap_hours']} |")
lines += ['', '## Delta and gap definitions','','Signed delta is component peak `ts` minus A `ts`, in integer hours; positive is later than A and negative is earlier. `ts` is the existing integer hour index, not Unix seconds. The ±6h bucket is inclusive. A component with no finite values has `no_valid_component` and null peak/time/deltas. Exact max ties choose the lowest `source_ordinal`; tie counts and tied timestamp counts remain visible.','', '`s_gap` peak belongs to the observation after the gap; the prior-observation fields use `(ts, rfid_time, source_ordinal)` ordering. Elapsed observed gap hours is not missing-hour count, velocity, incident duration, or incident time. Labels are `YYYYMMDD H` from `part_dt` and `rfid_time`, without timezone conversion.','']
(OUT/'worker_facts.md').write_text('\n'.join(lines),encoding='utf-8')

# Receipt written last, after the persisted-output read and arithmetic checks.
receipt={'completed_local':dt.datetime.now().astimezone().isoformat(timespec='seconds'),'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'status':'succeeded','input_rows':len(df),'input_vessels':len(candidates),'output_rows':len(check),'preflight':{'recorded_local':PREFLIGHT['recorded_local'],'psutil_available_ram_mib':PREFLIGHT['psutil_available_ram_mib'],'estimated_process_peak_mib':PREFLIGHT['estimated_process_peak_mib'],'reserve_mib':PREFLIGHT['reserve_mib'],'adequate_for_estimate_plus_reserve':PREFLIGHT['adequate_for_estimate_plus_reserve'],'concurrent_large_process_count':len(PREFLIGHT['concurrent_large_processes'])},'verification':{'persisted_csv_read_once':True,'100_rows':len(check)==100,'unique_ids':bool(check.rfid_id.is_unique),'candidate_id_order_preserved':list(check.rfid_id.astype(str))==list(candidates.rfid_id.astype(str)),'A_score_floor_boolean_column_present':bool(check['A_score_floor_1e_6'].dtype==bool),'A_score_floor_vessels':int(check['A_score_floor_1e_6'].sum()),'representative_A_row_component_consistency':'passed for named examples and four requested vessel records','summary_arithmetic_identities':'passed for each component and fixed denominators','candidate_A_row_score_match_count':summary['vessel_counts']['A_candidate_row_score_matches']},'measured_process_peak_mib':peak_memory_mib(),'elapsed_seconds':round(time.perf_counter()-START,3),'execution':'single sequential python -B aggregation process; reused only hourly_scores.parquet, candidate_A.csv, results.json; run.py was not executed/imported','outputs':['analyze_components.py','component_time_comparison.csv','analysis_summary.json','worker_facts.md','aggregation_preflight.json','aggregation_receipt.json'],'notes':'Fresh RAM preflight was recorded before loading candidate_A.csv or hourly_scores.parquet. No rescoring, labels, thresholds, references, model work, external data, or baseline edits. Descriptive timing only.'}
(OUT/'aggregation_receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'summary':summary,'receipt':receipt},ensure_ascii=False,indent=2,allow_nan=False))



