# -*- coding: utf-8 -*-
"""Round013 ?7: fixed endpoints, cluster bootstrap, exact-binomial MDE."""
from __future__ import annotations
import csv,hashlib,json,math,random,sys,time,ctypes,platform
from collections import defaultdict,Counter
from datetime import datetime
from pathlib import Path
from scipy.stats import binom,binomtest

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
G6=HERE/'g6_event_results.csv';STATUS=HERE/'g6_vessel_status.csv';CONF=HERE/'g3_confidence.csv'
WINDOWS=(7,3);B=4000;SEED=11052026;ALPHA=.025;POWER=.8

def utc_now():return datetime.now().astimezone().isoformat(timespec='seconds')
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def source_manifest():
 paths=[G6,STATUS,CONF,HERE.parent/'g4_voyage_local_collapse.csv',HERE.parent/'g5_confound_summary.json',
        ROOT/'AGENTS.md',ROOT/'.codex/agents/luna_worker.toml',HERE.parent/'PROTOCOL.md',
        HERE.parent/'SUPERVISOR_TASK_01.md',HERE.parent/'SUPERVISOR_TASK_02.md',HERE.parent/'run_round013.py',
        HERE/'g6_selection_and_confidence.py',HERE/'g7_evaluate.py',HERE/'validate_round013_post.py',ROOT/'testB/round_011_20261105/PROTOCOL.md',
        ROOT/'testB/round_012_20261105/g_gate_v2.py']
 return {str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths}
def memory_snapshot():
 class M(ctypes.Structure):
  _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
 m=M();m.dwLength=ctypes.sizeof(m)
 if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('GlobalMemoryStatusEx failed')
 ps=[]
 try:
  import psutil
  for p in psutil.process_iter(['pid','name','memory_info']):
   try:x=p.info;ps.append({'pid':x['pid'],'name':x['name'],'working_set_mib':round(x['memory_info'].rss/1048576,1)})
   except (psutil.NoSuchProcess,psutil.AccessDenied):pass
 except ImportError:ps=[{'note':'psutil unavailable'}]
 return {'stage':'before g7 evaluation/bootstrap','checked_at':datetime.now().astimezone().isoformat(timespec='seconds'),
         'available_ram_mib':round(m.ullAvailPhys/1048576,1),'total_ram_mib':round(m.ullTotalPhys/1048576,1),
         'estimated_additional_peak_mib':180,
         'peak_estimate_basis':'At most 200 event rows, 4,000 bootstrap replicates x qualifying vessels, one small float per replicate (<1 MiB); SciPy already installed; sequential population/window loops; no parquet arrays.',
         'processes':ps}
def read_csv(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_csv(path,rows,cols=None):
 rows=list(rows);cols=cols or (list(rows[0]) if rows else [])
 with open(path,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
def upper_tail(k,n,p):
 if n<=0:return None
 return float(binom.sf(k-1,n,p))
def exact_mde(n,p0,alpha=ALPHA,power=POWER):
 if n<=0:return {'defined':False,'reason':'zero eligible events','n':n,'p0':p0,'alpha':alpha,'power_target':power}
 if p0 is None or not math.isfinite(p0) or not (0<=p0<=1):return {'defined':False,'reason':'invalid p0','n':n,'p0':p0,'alpha':alpha,'power_target':power}
 critical=None
 for k in range(n+1):
  if upper_tail(k,n,p0)<=alpha:
   critical=k;break
 if critical is None:return {'defined':False,'reason':'no rejection count attainable at null alpha','n':n,'p0':p0,'alpha':alpha,'power_target':power,'critical_k':n+1}
 max_power=upper_tail(critical,n,1.0)
 if max_power is None or max_power<power:return {'defined':False,'reason':'target power unattainable','n':n,'p0':p0,'alpha':alpha,'power_target':power,'critical_k':critical,'power_at_p1':max_power}
 lo=p0;hi=1.0
 for _ in range(120):
  mid=(lo+hi)/2
  if upper_tail(critical,n,mid)>=power:hi=mid
  else:lo=mid
 alt=hi
 return {'defined':True,'n':n,'p0':p0,'alpha':alpha,'power_target':power,'critical_k':critical,
         'minimum_alternative_p':alt,'mde_absolute':alt-p0,'achieved_power':upper_tail(critical,n,alt)}
def linear_quantile(sorted_values,q):
 if not sorted_values:return None
 pos=(len(sorted_values)-1)*q;lo=math.floor(pos);hi=math.ceil(pos)
 if lo==hi:return float(sorted_values[lo])
 frac=pos-lo
 return float(sorted_values[lo]*(1-frac)+sorted_values[hi]*frac)
def cluster_bootstrap(events_by_vessel,reps=B,seed=SEED):
 ids=sorted(events_by_vessel)
 if not ids:return {'defined':False,'reason':'no eligible event clusters','clusters':0,'replicates':reps,'seed':seed}
 rng=random.Random(seed);values=[];n=len(ids)
 for _ in range(reps):
  picks=[rng.choice(ids) for _ in range(n)]
  hits=den=0
  for vid in picks:
   group=events_by_vessel[vid];den+=len(group);hits+=sum(int(e['collapse_hit']) for e in group)
  if den:values.append(hits/den)
 sv=sorted(values)
 return {'defined':True,'clusters':n,'replicates_requested':reps,'replicates_used':len(values),'seed':seed,
         'ci_level':.975,'quantile_method':'linear percentile, interpolation at (B-1)*q',
         'lower':linear_quantile(sv,.0125),'upper':linear_quantile(sv,.9875),
         'degenerate_fraction':sum(v in (0.0,1.0) for v in values)/len(values) if values else None,
         'unique_bootstrap_rates':sorted(set(values))}
def baseline_probability(start,end,acc):
 first=max(start,acc-6);last=min(end,acc+6)
 overlap=max(0,last-first+1)
 return overlap/(end-start+1)
def passes(rate,adjusted_p):return rate is not None and adjusted_p is not None and rate>=.12 and adjusted_p<.05

def run():
 t0=time.time();pre=HERE/'g7_preflight.json'; external=json.loads(pre.read_text(encoding='utf-8-sig')) if pre.exists() else None
 log={'started_at':utc_now(),'command':'python -B testB/round_013_20261105/supervised_task02/g7_evaluate.py',
      'scope':'?7 only; no Round014, new features, threshold search, model training, 2025 inference or submission',
      'requested_model':'GPT-6 Luna xhigh as dispatched by supervisor task',
      'actual_model_telemetry':'not exposed by Python process; do not infer from stored project defaults',
      'external_preflight':external,'python':sys.version,'platform':platform.platform(),
      'bootstrap':{'B':B,'seed':SEED,'cluster_unit':'vessel; all events of a sampled vessel included together',
                   'sampling':'sample n eligible vessels with replacement; event-weighted mean within replicate',
                   'ci_percentiles':[1.25,98.75]},'memory_checks':[],'source_hashes_before':source_manifest()}
 mem=memory_snapshot();log['memory_checks'].append(mem)
 if mem['available_ram_mib']<768 or mem['available_ram_mib']<mem['estimated_additional_peak_mib']:
  (HERE/'g7_execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
  raise RuntimeError('RAM below threshold/estimated peak; g7 deferred')
 source=read_csv(G6); statuses=read_csv(STATUS); confidences=read_csv(CONF)
 rows=[]
 for r in source:
  x=dict(r);x['w']=int(r['w']);x['acc_id']=int(r['acc_id']);x['tier']=int(r['tier']);x['acc_ts']=int(r['acc_ts'])
  x['prediction_available']=r['prediction_available'].lower()=='true'
  if x['prediction_available']:
   for f in ('voyage_no','t_start','t_end','n_rows','t_collapse','t_mid','n_reference','less','equal','tied_minimum_candidates'):
    x[f]=int(r[f])
   for f in ('lin_min','rank_percentile','confidence'):
    x[f]=float(r[f])
   x['collapse_hit']=int(abs(x['t_collapse']-x['acc_ts'])<=6)
   x['baseline_p0']=baseline_probability(x['t_start'],x['t_end'],x['acc_ts'])
   x['mid_hit']=int(abs(x['t_mid']-x['acc_ts'])<=6)
   x['end_hit']=int(abs(x['t_end']-x['acc_ts'])<=6)
  else:
   x['collapse_hit']=x['baseline_p0']=x['mid_hit']=x['end_hit']=None
  rows.append(x)
 write_csv(HERE/'g7_event_evaluation.csv',rows)
 metric_rows=[]; metrics=[]; bootstrap={};mde={};status_details={}
 rng_seed=SEED
 # Bootstrap call order fixed for reproducibility: w=7 then w=3; Tier0-1 then ALL.
 rng=random.Random(rng_seed)
 for w in WINDOWS:
  wrows=[r for r in rows if r['w']==w]
  status_w=[r for r in statuses if int(r['w'])==w]
  status_details[str(w)]={}
  for pop in ('Tier0-1','ALL'):
   pop_all=[r for r in wrows if pop=='ALL' or r['tier']<=1]
   eligible=[r for r in pop_all if r['prediction_available']]
   n_all=len(pop_all);n=len(eligible);hits=sum(r['collapse_hit'] for r in eligible)
   base_probs=[r['baseline_p0'] for r in eligible];p0=(sum(base_probs)/n if n else None)
   mid_hits=sum(r['mid_hit'] for r in eligible);end_hits=sum(r['end_hit'] for r in eligible)
   rate=(hits/n if n else None);service=(hits/n_all if n_all else None)
   if n and p0 is not None: p_raw=float(binomtest(hits,n,p0,alternative='greater').pvalue)
   else:p_raw=None
   p_adj=min(1.0,2*p_raw) if p_raw is not None and pop=='Tier0-1' else None
   pass_flag=passes(rate,p_adj) if pop=='Tier0-1' else None
   exc=Counter(r['status'] for r in pop_all if not r['prediction_available'])
   vpop={r['rfid_id'] for r in pop_all}
   reason_vessel=Counter(s['status'] for s in status_w if s['rfid_id'] in vpop and s['status']!='eligible')
   metric={'w':w,'population':pop,'role':('primary_first' if pop=='Tier0-1' and w==7 else 'primary_second' if pop=='Tier0-1' else 'descriptive_only'),
     'total_events':n_all,'eligible_events':n,'excluded_events':n_all-n,'n_eligible_vessels':len({r['rfid_id'] for r in eligible}),
     'eligible_vessel_status_counts':{s:sum(r['status']==s for r in status_w if r['rfid_id'] in vpop) for s in ('raw_history_insufficient','valid_history_insufficient','no_valid_voyage','eligible')},
     'excluded_event_status_counts':{s:int(exc.get(s,0)) for s in ('raw_history_insufficient','valid_history_insufficient','no_valid_voyage')},
     'collapse_hits':hits,'collapse_hit_rate_conditional':rate,'collapse_hits_over_all_target_events_service_rate':service,
     'baseline_p0_mean_event_probability':p0,'baseline_expected_hits':sum(base_probs),'binomial_p_raw_one_sided':p_raw,
     'binomial_p_bonferroni_family2':p_adj,'pre_registered_pass':pass_flag,
     'mid_hits_same_eligible_denominator':mid_hits,'mid_rate_same_eligible_denominator':mid_hits/n if n else None,
     'end_hits_same_eligible_denominator':end_hits,'end_rate_same_eligible_denominator':end_hits/n if n else None,
     'midpoint_definition':'sorted voyage observed row at zero-based index len(rows)//2',
     'pvalue_approximation_caveat':'binomtest uses the mean of event-specific baseline probabilities; heterogeneous event p0 and within-vessel event dependence mean this is not exact independent-event confirmation.'}
   metric_rows.append(metric);metrics.append(metric)
   # Build cluster event groups for deterministic vessel bootstrap; no event is resampled alone.
   groups=defaultdict(list)
   for r in eligible:groups[r['rfid_id']].append(r)
   key=f'w{w}_{pop}'
   if groups:
    cluster_ids=sorted(groups);samples=[]
    for _ in range(B):
     selected=[rng.choice(cluster_ids) for _ in cluster_ids]
     hn=dn=0
     for vid in selected:
      group=groups[vid];dn+=len(group);hn+=sum(e['collapse_hit'] for e in group)
     if dn:samples.append(hn/dn)
    samples.sort()
    ci={'defined':True,'cluster_count':len(cluster_ids),'replicates_requested':B,'replicates_used':len(samples),'seed':SEED,
        'ci_level':.975,'lower':linear_quantile(samples,.0125),'upper':linear_quantile(samples,.9875),
        'degenerate_fraction':sum(x in (0.0,1.0) for x in samples)/len(samples) if samples else None,
        'bootstrap_order':'w=7 then w=3; Tier0-1 then ALL, one Random(SEED) stream'}
   else:ci={'defined':False,'reason':'no eligible event clusters','cluster_count':0,'replicates_requested':B,'seed':SEED,'lower':None,'upper':None}
   bootstrap[key]=ci
   if pop=='Tier0-1':mde[str(w)]=exact_mde(n,p0)
 # Confidence score diagnostics: selected-vessel distribution only, not a cutoff or risk estimate.
 conf_diagnostics={}
 for w in WINDOWS:
  cs=[float(r['confidence']) for r in confidences if int(r['w'])==w]
  ps=[float(r['rank_percentile']) for r in confidences if int(r['w'])==w]
  conf_diagnostics[str(w)]={'selected_vessels':len(cs),'confidence_min':min(cs) if cs else None,
    'confidence_median':linear_quantile(sorted(cs),.5),'confidence_max':max(cs) if cs else None,
    'fraction_confidence_exactly_one':sum(x==1.0 for x in cs)/len(cs) if cs else None,
    'fraction_confidence_ge_0_95':sum(x>=.95 for x in cs)/len(cs) if cs else None,
    'distinct_confidence_values':len(set(cs)),'rank_percentile_median':linear_quantile(sorted(ps),.5) if ps else None,
    'warning':'rank-based confidence is not calibrated probability; selected raw minima make confidence concentrate near 1.'}
 # Coverage denominator counts by vessel, events, and tier.
 coverage={}
 for w in WINDOWS:
  sw=[r for r in statuses if int(r['w'])==w]
  cov={'vessels_total':len(sw),'vessels_by_status':{},'events_by_status_all':{},'events_by_status_tier01':{}}
  for st in ('raw_history_insufficient','valid_history_insufficient','no_valid_voyage','eligible'):
   subset=[r for r in sw if r['status']==st]
   cov['vessels_by_status'][st]=len(subset)
   cov['events_by_status_all'][st]=sum(int(r['n_events_all']) for r in subset)
   cov['events_by_status_tier01'][st]=sum(int(r['n_events_tier01']) for r in subset)
  coverage[str(w)]=cov
 # Summarize family, MDE caveat, and scope boundaries.
 summary={'round':'Round013','scope':'?6-7 only; selection and evaluation use saved ?3-5 outputs; no changes to protocol/older rounds/raw data',
   'supervisor_branch':'approved all-voyage reference pool without day/night restriction for both w; confound not detected, not proven absent',
   'selection':'per vessel/w minimum lin_min among valid voyages after raw-history n>=11 and valid-history n>=11 gates; exact ties earliest t_start then voyage_no',
   'shared_prediction':'multiple events on one vessel share the vessel selected voyage; acc_ts used only after selection for evaluation',
   'confidence':'P=(less + 0.5*equal)/n_reference; confidence=1-P; descriptive rank diagnostic only, no filtering/submission',
   'baseline':'uniform integer hour from selected [t_start,t_end], inclusive; p0 is overlap with inclusive [acc_ts-6,acc_ts+6] divided by voyage integer-hour count',
   'binomial':'one-sided exact binomtest against mean event p0; event-specific p0 and within-vessel dependence make this an approximation',
   'primary_order':'Tier0-1, w=7 first and w=3 second; per-window alpha .025; pass requires rate>=.12 and Bonferroni-adjusted p<.05',
   'all_population':'descriptive only; no additional confirmatory test family',
   'bootstrap':{'B':B,'seed':SEED,'unit':'vessel cluster','CI':'97.5% percentile [1.25%,98.75%]','event_weighted':True},
   'mde':{'method':'independent binomial approximation using eligible Tier0-1 n, mean event p0, alpha=.025, power=.8','not_cluster_adjusted':True},
   'coverage_by_w':coverage,'metrics':metrics,'bootstrap_ci':bootstrap,'mde_by_w':mde,'confidence_diagnostics':conf_diagnostics,
   'source_paths':{'section4':'g4_voyage_local_collapse.csv','section5':'g5_confound_summary.json','section3_coverage':'g3_coverage_summary.json'},
   'limits':['Dev labels are provisional linked positives, not independently confirmed incident truth.','This is batch, post-hoc localization, not early warning.','R009?R010?R012?R013 prior lin-family selection is not fully corrected within the capped dev set.','No 2025 feature/inference/scoring, model training, submission, or Round014 work.','Learner understanding was not assessed.']}
 (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 write_csv(HERE/'g7_metric_summary.csv',metric_rows)
 (HERE/'g7_bootstrap_ci.json').write_text(json.dumps(bootstrap,ensure_ascii=False,indent=2),encoding='utf-8')
 (HERE/'g7_mde.json').write_text(json.dumps(mde,ensure_ascii=False,indent=2),encoding='utf-8')
 (HERE/'g7_confidence_diagnostics.json').write_text(json.dumps(conf_diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
 (HERE/'g7_coverage_by_window.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding='utf-8')
 log.update({'ended_at':utc_now(),'elapsed_seconds':round(time.time()-t0,3),'memory_checks':[mem],
   'dimensions':{'event_result_rows':len(rows),'status_rows':len(statuses),'confidence_rows':len(confidences),
     'metrics':len(metrics),'bootstrap_replicates_per_metric':B},'source_hashes_after':source_manifest(),
   'outputs':['g7_event_evaluation.csv','g7_metric_summary.csv','g7_bootstrap_ci.json','g7_mde.json','g7_confidence_diagnostics.json','g7_coverage_by_window.json','summary.json']})
 (HERE/'g7_execution.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
 if log['source_hashes_before']!=log['source_hashes_after']:raise AssertionError('Source hash changed during g7')
 print(json.dumps({'metrics':metrics,'bootstrap_ci':bootstrap,'mde':mde,'confidence_diagnostics':conf_diagnostics},ensure_ascii=False,indent=2))

if __name__=='__main__':run()
