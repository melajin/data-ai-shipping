# -*- coding: utf-8 -*-
"""Independent Round013 ?6-7 audit; standard-library-only, no production imports."""
import csv,json,math,random
from collections import defaultdict,Counter
from math import comb
from pathlib import Path
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
SEED=11052026;B=4000;WINDOWS=(7,3);POPULATIONS=('Tier0-1','ALL')
def read_csv(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def near(a,b,tol=1e-12):
 if a is None or b is None:return a is None and b is None
 return abs(float(a)-float(b))<=tol
def fscore(row,key):
 x=row.get(key,'')
 if x is None or str(x).strip()=='':return None
 y=float(x)
 return y if math.isfinite(y) else None
def tail(k,n,p):
 if n<0 or k>n:return 0.0
 if k<=0:return 1.0
 return sum(comb(n,j)*(p**j)*((1-p)**(n-j)) for j in range(k,n+1))
def qlinear(x,q):
 if not x:return None
 z=(len(x)-1)*q;lo=math.floor(z);hi=math.ceil(z)
 return x[lo] if lo==hi else x[lo]*(hi-z)+x[hi]*(z-lo)
def audit_mde(n,p0,alpha=.025,target=.8):
 if n<=0 or p0 is None:return {'defined':False}
 critical=next((k for k in range(n+1) if tail(k,n,p0)<=alpha),None)
 if critical is None:return {'defined':False,'critical_k':n+1}
 if tail(critical,n,1)<target:return {'defined':False,'critical_k':critical}
 lo=p0;hi=1.0
 for _ in range(120):
  mid=(lo+hi)/2
  if tail(critical,n,mid)>=target:hi=mid
  else:lo=mid
 return {'defined':True,'critical_k':critical,'minimum_alternative_p':hi,'mde_absolute':hi-p0}
def mismatch(msg,errors):errors.append(msg)
def main():
 errors=[];g4=read_csv(PARENT/'g4_voyage_local_collapse.csv')
 statuses=read_csv(HERE/'g6_vessel_status.csv');selections=read_csv(HERE/'g6_selection.csv')
 event_rows=read_csv(HERE/'g7_event_evaluation.csv')
 summary=json.loads((HERE/'summary.json').read_text(encoding='utf-8'))
 boot=json.loads((HERE/'g7_bootstrap_ci.json').read_text(encoding='utf-8'))
 mde=json.loads((HERE/'g7_mde.json').read_text(encoding='utf-8'))
 conf=read_csv(HERE/'g3_confidence.csv')
 byv=defaultdict(list)
 for r in g4:byv[r['rfid_id']].append(r)
 selmap={(int(r['w']),r['rfid_id']):r for r in selections}
 statusmap={(int(r['w']),r['rfid_id']):r for r in statuses}
 evby=defaultdict(list)
 for r in event_rows:evby[int(r['w'])].append(r)
 cfmap={(int(r['w']),r['rfid_id']):r for r in conf}
 checks={'g4_voyages':len(g4),'status_rows':len(statuses),'selection_rows':len(selections),
         'confidence_rows':len(conf),'event_rows':len(event_rows),'w':{},'independent_bootstrap':{},'independent_mde':{}}
 if len(g4)!=3615:mismatch(f'expected 3615 g4 voyages, found {len(g4)}',errors)
 if len(event_rows)!=200:mismatch(f'expected 200 event-window rows, found {len(event_rows)}',errors)
 for w in (3,7):
  counts=Counter()
  for vid,vr in byv.items():
   raw=int(vr[0]['raw_voyage_count_for_vessel']); valid=[r for r in vr if fscore(r,f'lin_min_w{w}') is not None]
   if raw<11:reason='raw_history_insufficient'
   elif len(valid)==0:reason='no_valid_voyage'
   elif len(valid)<11:reason='valid_history_insufficient'
   else:reason='eligible'
   counts[reason]+=1
   s=statusmap.get((w,vid))
   if s is None:mismatch(f'missing vessel status w{w} {vid}',errors);continue
   if s['status']!=reason or int(s['raw_voyages'])!=raw or int(s['valid_voyages'])!=len(valid):
    mismatch(f'status gate mismatch w{w} {vid}',errors)
   sel=selmap.get((w,vid))
   if reason!='eligible':
    if sel is not None:mismatch(f'ineligible vessel selected w{w} {vid}',errors)
    continue
   minimum=min(fscore(r,f'lin_min_w{w}') for r in valid)
   ties=[r for r in valid if fscore(r,f'lin_min_w{w}')==minimum]
   expected=min(ties,key=lambda r:(int(r['t_start']),int(r['voyage_no'])))
   if sel is None:mismatch(f'missing selection w{w} {vid}',errors);continue
   if int(sel['voyage_no'])!=int(expected['voyage_no']) or not near(sel['lin_min'],minimum):
    mismatch(f'argmin/tie order mismatch w{w} {vid}',errors)
   refs=[fscore(r,f'lin_min_w{w}') for r in valid if int(r['voyage_no'])!=int(expected['voyage_no'])]
   less=sum(x<minimum for x in refs);equal=sum(x==minimum for x in refs);rank=(less+.5*equal)/len(refs)
   c=cfmap.get((w,vid))
   if c is None or int(c['n_reference'])!=len(refs) or not near(c['rank_percentile'],rank) or not near(c['confidence'],1-rank):
    mismatch(f'rank-confidence mismatch w{w} {vid}',errors)
   for field in ('t_start','t_end'):
    if int(sel[field])!=int(expected[field]):mismatch(f'selected {field} mismatch w{w} {vid}',errors)
   if int(sel['t_collapse'])!=int(expected[f't_collapse_w{w}']):mismatch(f'selected collapse time mismatch w{w} {vid}',errors)
   # g4 does not carry t_mid; g6_execution records raw-id/ts split parity and midpoint reconstruction.
  # Every event follows vessel status and shares one vessel-level decision.
  wr=evby[w]
  for e in wr:
   s=statusmap[(w,e['rfid_id'])]
   if e['status']!=s['status']:mismatch(f'event eligibility mismatch w{w} acc {e["acc_id"]}',errors)
   if s['status']=='eligible':
    selected=selmap[(w,e['rfid_id'])]
    if int(e['voyage_no'])!=int(selected['voyage_no']):mismatch(f'events did not share vessel prediction w{w} acc {e["acc_id"]}',errors)
    start=int(selected['t_start']);end=int(selected['t_end']);acc=int(e['acc_ts'])
    p=max(0,min(end,acc+6)-max(start,acc-6)+1)/(end-start+1)
    if not near(e['baseline_p0'],p):mismatch(f'baseline mismatch w{w} acc {e["acc_id"]}',errors)
    if int(e['collapse_hit'])!=int(abs(int(e['t_collapse'])-acc)<=6):mismatch(f'collapse hit mismatch w{w} acc {e["acc_id"]}',errors)
    if int(e['mid_hit'])!=int(abs(int(e['t_mid'])-acc)<=6):mismatch(f'mid hit mismatch w{w} acc {e["acc_id"]}',errors)
    if int(e['end_hit'])!=int(abs(int(e['t_end'])-acc)<=6):mismatch(f'end hit mismatch w{w} acc {e["acc_id"]}',errors)
   elif e['prediction_available'].lower()=='true':mismatch(f'ineligible event has prediction w{w} acc {e["acc_id"]}',errors)
  checks['w'][str(w)]={'vessel_status_counts':dict(counts),'event_rows':len(wr),
      'eligible_events_all':sum(e['status']=='eligible' for e in wr),
      'eligible_events_tier01':sum(e['status']=='eligible' and int(e['tier'])<=1 for e in wr)}
 # Summary metrics and reproduce exact vessel-cluster bootstrap stream with stdlib only.
 rng=random.Random(SEED);metricmap={(int(x['w']),x['population']):x for x in summary['metrics']}
 for w in (7,3):
  for pop in POPULATIONS:
   eligible=[e for e in evby[w] if e['prediction_available'].lower()=='true' and (pop=='ALL' or int(e['tier'])<=1)]
   nall=sum(pop=='ALL' or int(e['tier'])<=1 for e in evby[w])
   hits=sum(int(e['collapse_hit']) for e in eligible)
   p0=sum(float(e['baseline_p0']) for e in eligible)/len(eligible) if eligible else None
   m=metricmap[(w,pop)]
   mid_hits=sum(int(e['mid_hit']) for e in eligible);end_hits=sum(int(e['end_hit']) for e in eligible)
   for k,x in [('eligible_events',len(eligible)),('total_events',nall),('collapse_hits',hits),
               ('mid_hits_same_eligible_denominator',mid_hits),('end_hits_same_eligible_denominator',end_hits)]:
    if int(m[k])!=x:mismatch(f'metric {k} mismatch w{w} {pop}: {m[k]} vs {x}',errors)
   if not near(m['collapse_hit_rate_conditional'],hits/len(eligible) if eligible else None):mismatch(f'conditional hit rate mismatch w{w} {pop}',errors)
   if not near(m['collapse_hits_over_all_target_events_service_rate'],hits/nall if nall else None):mismatch(f'service rate mismatch w{w} {pop}',errors)
   if not near(m['mid_rate_same_eligible_denominator'],mid_hits/len(eligible) if eligible else None) or not near(m['end_rate_same_eligible_denominator'],end_hits/len(eligible) if eligible else None):mismatch(f'mid/end rate mismatch w{w} {pop}',errors)
   if not near(m['baseline_p0_mean_event_probability'],p0):mismatch(f'mean p0 mismatch w{w} {pop}',errors)
   pvalue=tail(hits,len(eligible),p0) if eligible and p0 is not None else None
   if not near(m['binomial_p_raw_one_sided'],pvalue,1e-10):mismatch(f'binomial tail mismatch w{w} {pop}',errors)
   groups=defaultdict(list)
   for e in eligible:groups[e['rfid_id']].append(e)
   ids=sorted(groups);values=[]
   for _ in range(B):
    chosen=[rng.choice(ids) for _ in ids];num=den=0
    for vid in chosen:
     num+=sum(int(e['collapse_hit']) for e in groups[vid]);den+=len(groups[vid])
    if den:values.append(num/den)
   values.sort();key=f'w{w}_{pop}';ci=boot[key]
   lo=qlinear(values,.0125);hi=qlinear(values,.9875)
   if not near(ci['lower'],lo) or not near(ci['upper'],hi):mismatch(f'bootstrap CI mismatch {key}',errors)
   checks['independent_bootstrap'][key]={'clusters':len(ids),'replicates':len(values),'lower':lo,'upper':hi,'match':near(ci['lower'],lo) and near(ci['upper'],hi)}
   if pop=='Tier0-1':
    expected=audit_mde(len(eligible),p0)
    recorded=mde[str(w)]
    if expected['defined']!=recorded['defined'] or expected.get('critical_k')!=recorded.get('critical_k') or not near(expected.get('minimum_alternative_p'),recorded.get('minimum_alternative_p'),1e-10):
     mismatch(f'MDE mismatch w{w}',errors)
    checks['independent_mde'][str(w)]={'n':len(eligible),'p0':p0,**expected,'match':True}
 # Persist the exact denominators and no-ineligible-prediction invariant.
 checks['all_checks_passed']=not errors;checks['errors']=errors
 (HERE/'independent_audit.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(checks,ensure_ascii=False,indent=2))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
