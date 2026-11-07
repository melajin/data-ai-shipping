"""Targeted final invariants: comparison, raw reconstruction, links and hashes."""
import json,hashlib,re,statistics
from pathlib import Path
from datetime import datetime,timezone
P=Path(__file__).resolve().parent;R=P.parent;B=R.parent
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
co=read(P/'comparison_results.json');de=read(P/'final_decision.json');raw=read(P/'t3_raw_recompute.json');ver=read(P/'t3_verification.json')
assert raw['status']=='completed' and raw['n_mismatches']==0 and raw['n_event_metric_records']==300
assert raw['n_selected_rows']==99677 and raw['n_vessels']==82
assert all(r['eligibility_matches'] and (r['percentile_abs_error'] or 0)<=1e-9 for r in raw['records'])
assert ver['statistics_match'] and len(ver['event_summary_recomputations'])==6
assert all(r['delta_abs_error']<1e-12 and r['wilcoxon_abs_error']<1e-8 for r in ver['event_summary_recomputations'])
assert len(de['single_Bonferroni_candidates'])==1
assert de['single_Bonferroni_candidates'][0]['metric']=='lin_raw' and de['single_Bonferroni_candidates'][0]['stratum']=='Tier0_1'
assert not de['double_Bonferroni_candidates']
assert all(x['acc_rate_matches_G_rounding'] and x['ctrl_rate_matches_G_rounding'] for x in co['state_comparison'])
cb=read(R/'codex_independent/t2_state_distribution.json');state_validations=[]
for state in ['저속굴곡','이동','정박정지','해상정지','연안정지']:
    for s in ['ALL','Tier0_1','기관손상']:
        rr=[r for r in raw['state_events'] if r['metric']==state and (s=='ALL' or s=='Tier0_1' and r['tier']<=1 or s=='기관손상' and r['cause']==s)]
        old=next(x for x in cb['results'] if x['metric']==state and x['stratum']==s and x['half_width_h']==3 and x['design']=='hod_1/nrows_matched')
        ar=statistics.mean(r['a'] for r in rr);cr=statistics.mean(r['control_positive_count']/r['n_controls'] for r in rr)
        assert len(rr)==old['n_events'] and abs(ar-old['acc_positive_rate'])<1e-12 and abs(cr-old['ctrl_positive_rate_event_weighted'])<1e-12
        state_validations.append({'metric':state,'stratum':s,'n':len(rr),'independent_raw_rates_match':True})
count=0
for file in P.glob('raw_source_vessel_*.json'):
    records=read(file);ts=[r[0] for r in records]
    assert len(ts)==len(set(ts)) and all(datetime.fromtimestamp(t*3600,tz=timezone.utc).year==2026 for t in ts)
    count+=len(records)
assert count==99677
documents=['README.md','ROUND010_비교및결과보고_20261105.md','T1_결론상세보고_20261105.md','T2_결론상세보고_20261105.md','t1_report.md','t2_report.md','ROUND_REPORT.md','ROUND010_실행보고_20261105.md','t3_audit_report.md','NEXT_ROUND.md','REPRODUCE.md']
links=0
for name in documents:
    path=R/name;text=path.read_text(encoding='utf-8')
    assert '\ufffd' not in text and '????' not in text
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
        if not target.startswith(('http:','https:','#')):assert (path.parent/target).exists(),(name,target)
        links+=1
manifest=read(P/'closeout_manifest.json');verified=0
for relative,sha in manifest['outputs'].items():
    file=R/relative;assert file.exists() and hashlib.sha256(file.read_bytes()).hexdigest()==sha,relative;verified+=1
status=read(B/'STATUS.json');assert status['round010_comparison_closeout']['state']=='comparison_and_implementation_audit_completed'
prior=read(P/'prior_global_STATUS.json')
for key in ['active_round','active_supervisor_session','workers','run_id']:assert status.get(key)==prior.get(key)
result={'status':'passed','checked_at':datetime.now().astimezone().isoformat(),
 'raw_event_metric_comparisons':300,'raw_mismatches':0,'independent_statistical_recomputations':6,
 'independent_state_rate_comparisons':state_validations,'raw_selected_rows_checked_2026_no_duplicate_hours':count,
 'same_operator_implementation_independence_only':True,'single_Bonferroni_candidate':'lin_raw/Tier0_1',
 'markdown_links_checked':links,'stable_output_hashes_verified':verified,'historical_runtime_owner_preserved':True}
(P/'final_artifact_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='independent_state_rate_comparisons'},ensure_ascii=False))
