"""Lightweight completeness checks, not independent T3 statistics recomputation."""
import csv,json,sys
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent
def read(n):return json.loads((P/n).read_text(encoding='utf-8-sig'))
a,b=read('t1_gate_results.json'),read('t2_state_distribution.json')
assert len(a['results'])==2520
assert len(b['results'])==2160
for data in [a,b]:
    for r in data['results']:
        assert r['n_events']+r['excluded_events']==r['n_events_total']
        if r.get('zero_fraction',0)>.5:
            assert r['delta_percentile'] is None and r['wilcoxon_p'] is None
        assert r.get('mde80_positive_rate_approx')!=0
        if r['method']=='not_estimable':assert r['n_events']==0
        if r.get('percentile_prohibited'):assert r['wilcoxon_p'] is None
for g in a['gates']:assert g['passed']==all(g['checks'].values())
count=0
with (P/'t1_event_percentiles.csv').open(encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        count+=1
        if not row['exclusion']:assert int(row['n_ctrl_finite'])>=15
assert count==21000
for task in ['t1','t2']:
    receipt=read(task+'_execution.json');assert receipt[-1]['exit_code']==0
assert read('synthetic_verification.json')['status']=='passed'
result={'status':'passed','checked_at':datetime.now().astimezone().isoformat(),
 'scope':'artifact completeness and invariant checks only; independent T3 still pending',
 't1_cells':len(a['results']),'t2_cells':len(b['results']),'t1_event_metric_design_rows':count,
 'zero_inflation_percentile_suppression_verified':True,'binary_Wilcoxon_prohibited_verified':True,
 'zero_MDE_not_reported_verified':True,'latest_T1_T2_actual_exit_codes':[0,0]}
(P/'artifact_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
