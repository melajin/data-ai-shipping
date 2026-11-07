"""Compare frozen Gemini/Codex artifacts; stdlib, no source parquet loading."""
import csv,json,math,hashlib,re
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent;ROOT=P.parent;C=ROOT/'codex_independent';G=P/'original_root_snapshot'
METRICS=['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(name,value):(P/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def finite(x):return isinstance(x,(float,int)) and math.isfinite(x)
def clean(x):
    if isinstance(x,float) and not math.isfinite(x):return None
    if isinstance(x,list):return [clean(v) for v in x]
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    return x
def design(key):
    match=re.search(r'(?:\+\-|±)(\d+)',key)
    h=int(match.group(1)) if match else None
    return f'hod_{"none" if h is None else h}/nrows_{"matched" if "matched" in key else "unmatched"}'
def stratum(name):return name[5:] if name.startswith('type_') else name
def main():
    a,b,ca,cb=read(G/'t1_gate_results.json'),read(G/'t2_state_distribution.json'),read(C/'t1_gate_results.json'),read(C/'t2_state_distribution.json')
    lookup={(r['half_width_h'],r['design'],r['stratum'],r['metric']):r for r in ca['results']}
    pairs=[]
    def add(half,des,s,metric,v,context):
        r=lookup.get((half,des,s,metric))
        if r is None:return
        binary=v.get('zero_inflated_gt50pct',False) or r.get('percentile_prohibited',False)
        gd=v.get('delta');gp=v.get('wilcoxon_p');cd=r.get('delta_percentile');cp=r.get('wilcoxon_p')
        pairs.append({'context':context,'half_width_h':half,'design':des,'stratum':s,'metric':metric,
          'aggregation':'event','gemini_n':v.get('n'),'codex_n':r['n_events'],
          'gemini_delta':gd if finite(gd) and not binary else None,'codex_delta':cd if not binary else None,
          'delta_difference_C_minus_G':cd-gd if finite(cd) and finite(gd) and not binary else None,
          'delta_matches_G_rounding':abs(cd-gd)<=.000050001 if finite(cd) and finite(gd) and not binary else None,
          'gemini_raw_p':gp if not binary else None,'codex_raw_p':cp if not binary else None,
          'p_matches_G_rounding':abs(cp-gp)<=.000005001 if finite(cp) and finite(gp) and not binary else None,
          'gemini_ci95':v.get('ci95') if not binary else None,'codex_ci95':r.get('ci95') if not binary else None,
          'gemini_mde':v.get('mde_bonf') if not binary else None,'codex_mde':r.get('mde80_percentile_approx') if not binary else r.get('mde80_positive_rate_approx'),
          'zero_inflation_comparison_prohibited':binary,'inferential_result':not des.startswith('hod_none')})
    for key,grid in a['grid_results_10_variations'].items():
        for s,v in grid['strata'].items():
            for metric,rec in v['metrics'].items():add(3,design(key),stratum(s),metric,rec,'10_design_grid')
    for width,ss in a['width_sensitivity'].items():
        half=int(re.search(r'(\d+)',width).group(1))
        for s,v in ss.items():
            for metric,rec in v['metrics'].items():add(half,'hod_1/nrows_matched',s,metric,rec,'width_sensitivity')
    # Per-event primary values are more informative than rounded summary agreement.
    primary={}
    with (C/'t1_event_percentiles.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['half_width_h']=='3' and row['design']=='hod_1/nrows_matched':primary[(int(row['acc_id']),row['metric'])]=row
    events=[]
    with (G/'t1_event_percentiles.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            for metric in METRICS:
                other=primary[(int(row['acc_id']),metric)]
                def num(x):
                    try:return float(x) if math.isfinite(float(x)) else None
                    except (TypeError,ValueError):return None
                gv,cv=num(row.get('acc_'+metric)),num(other['acc_value'])
                gp,cp=num(row.get('pct_'+metric)),num(other['percentile'])
                events.append({'acc_id':int(row['acc_id']),'metric':metric,'tier':int(row['tier']),
                    'gemini_acc_value':gv,'codex_acc_value':cv,'acc_abs_difference':abs(gv-cv) if gv is not None and cv is not None else None,
                    'gemini_percentile':gp if metric!='still_frac' else None,'codex_percentile':cp,
                    'percentile_difference':cp-gp if cp is not None and gp is not None and metric!='still_frac' else None,
                    'gemini_n_ctrl':int(row['n_ctrl']),'codex_n_ctrl_finite':int(other['n_ctrl_finite']),
                    'gemini_eligible':row['eligible']=='True','codex_exclusion':other['exclusion'] or None})
    event_summary={}
    for metric in METRICS:
        rr=[r for r in events if r['metric']==metric]
        event_summary[metric]={'n_events':len(rr),
          'both_acc_values_finite':sum(r['gemini_acc_value'] is not None and r['codex_acc_value'] is not None for r in rr),
          'acc_value_disagreements_gt_1e_7':sum(r['acc_abs_difference'] is not None and r['acc_abs_difference']>1e-7 for r in rr),
          'acc_finite_mismatch_ids':[r['acc_id'] for r in rr if (r['gemini_acc_value'] is None)!=(r['codex_acc_value'] is None)],
          'percentile_disagreements_gt_1e_9':[r['acc_id'] for r in rr if r['percentile_difference'] is not None and abs(r['percentile_difference'])>1e-9],
          'max_acc_abs_difference':max([r['acc_abs_difference'] for r in rr if r['acc_abs_difference'] is not None],default=None),
          'max_percentile_abs_difference':max([abs(r['percentile_difference']) for r in rr if r['percentile_difference'] is not None],default=None)}
    state_pairs=[]
    for s,ss in b['state_distribution_and_drift_audit'].items():
        sn='기관손상' if s.startswith('기관손상') else s
        for name,rec in ss['states_mcnemar'].items():
            r=next(v for v in cb['results'] if v['metric']==name and v['stratum']==sn and v['half_width_h']==3 and v['design']=='hod_1/nrows_matched')
            state_pairs.append({'stratum':sn,'state':name,'n':r['n_events'],
                'gemini_acc_rate':rec['acc_rate'],'codex_acc_rate':r['acc_positive_rate'],
                'gemini_ctrl_rate':rec['ctrl_mean_rate'],'codex_ctrl_rate':r['ctrl_positive_rate_event_weighted'],
                'acc_rate_matches_G_rounding':abs(rec['acc_rate']-r['acc_positive_rate'])<=.000050001,
                'ctrl_rate_matches_G_rounding':abs(rec['ctrl_mean_rate']-r['ctrl_positive_rate_event_weighted'])<=.000050001,
                'gemini_p_rounded_fractional_discordances':rec['mcnemar_exact_p'],
                'codex_p_pairing_mixture_merger':r['p_raw'],
                'codex_mde_approx':r['mde80_positive_rate_approx'],
                'rates_comparable_but_p_methods_different':True})
    drift_pairs=[]
    for s,ss in b['state_distribution_and_drift_audit'].items():
        sn='기관손상' if s.startswith('기관손상') else s
        r=next(v for v in cb['results'] if v['metric']=='direct_drift' and v['stratum']==sn and v['half_width_h']==3 and v['design']=='hod_1/nrows_matched')
        rec=ss['direct_drift_eval']['has_drift_2h_mcnemar']
        drift_pairs.append({'stratum':sn,'n':r['n_events'],'gemini_positive_events':round(rec['acc_rate']*rec['n']),
          'codex_positive_events':round(r['acc_positive_rate']*r['n_events']),
          'gemini_acc_rate':rec['acc_rate'],'codex_acc_rate':r['acc_positive_rate'],
          'gemini_ctrl_rate':rec['ctrl_mean_rate'],'codex_ctrl_rate':r['ctrl_positive_rate_event_weighted'],
          'directly_comparable':False,'reasons':['anchor definition differs','two hourly samples versus >=2h elapsed (three samples)','within-window detection versus globally sustained rows']})
    mainrows=[r for r in pairs if r['context']=='10_design_grid' and r['design']=='hod_1/nrows_matched' and r['stratum'] in ['ALL','Tier0_1']]
    candidate=[]
    for g in ca['gates']:
        r=g['primary'];checks=dict(g['checks']);checks['corrected_p_below_alpha']=r['p_raw'] is not None and r['p_raw']<.05/7
        candidate.append({'metric':g['metric'],'stratum':g['stratum'],'normal_single_Bonferroni_pass':all(checks.values()),
          'literal_double_Bonferroni_pass':g['passed'],'normal_checks':checks,'delta':r['delta_percentile'],
          'n':r['n_events'],'raw_p':r['p_raw'],'adjusted_p':r['p_bonferroni'],'ci95':r['ci95'],
          'mde':r['mde80_percentile_approx'] or r.get('mde80_positive_rate_approx'),'sign_count':g['sign_consistent_designs']})
    forbidden=[]
    for key,grid in a['grid_results_10_variations'].items():
        for s,ss in grid['strata'].items():
            for m,r in ss['metrics'].items():
                if r.get('zero_inflated_gt50pct') and r.get('wilcoxon_p') is not None:forbidden.append({'design':key,'stratum':s,'metric':m})
    summary={'created_at':datetime.now().astimezone().isoformat(),'scope':'post-result comparison; no blind independence claim',
      'gemini_T1_grid_cells':sum(len(ss['metrics']) for gg in a['grid_results_10_variations'].values() for ss in gg['strata'].values()),
      'codex_T1_cells':len(ca['results']),'codex_T2_cells':len(cb['results']),
      'compared_records_including_duplicate_primary_width':len(pairs),
      'primary_numeric_comparison':mainrows,'primary_event_comparison':event_summary,
      'canonical_gate':candidate,'state_comparison':state_pairs,'direct_drift_comparison':drift_pairs,
      'gemini_forbidden_zero_inflated_percentile_cells':forbidden,
      'gemini_T1_source_provenance':'root t1_decompose.py overwritten by Codex before separation; original Gemini source unavailable; current root t1_memory and t1_execution do not prove Gemini exit',
      'Gemini_T2_exit_evidence':'reported as 0 in prose, no independently captured T2 execution receipt retained',
      'input_counts':ca['input'],'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [G/'t1_gate_results.json',G/'t2_state_distribution.json',C/'t1_gate_results.json',C/'t2_state_distribution.json']}}
    save('comparison_results.json',clean(summary));save('comparison_t1_full.json',clean(pairs));save('comparison_t1_event_values.json',clean(events))
    for name,records in [('comparison_t1.csv',pairs),('comparison_t2_states.csv',state_pairs),('comparison_direct_drift.csv',drift_pairs)]:
        with (P/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    print(json.dumps({'compared_cells':len(pairs),'state_pairs':len(state_pairs),'primary_event_summary':event_summary},ensure_ascii=False))
if __name__=='__main__':main()
