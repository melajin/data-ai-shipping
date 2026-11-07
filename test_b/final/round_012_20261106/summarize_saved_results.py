"""Read-only descriptive strata/overlap; creates no predictions and changes no labels."""
from pathlib import Path
import hashlib
import json
import time

HERE = Path(__file__).resolve().parent
FINAL = HERE.parent
ROOT = FINAL.parent.parent


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):
            h.update(b)
    return h.hexdigest()


def main():
    import psutil
    available=psutil.virtual_memory().available
    preflight={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'available_mib':available/1048576,
               'expected_extra_mib':512,'reserve_mib':640,'allowed':available>=1152*1048576,
               'basis':'Small saved event tables and100-row metadata only; no parquet or raw data load'}
    if not preflight['allowed']:
        raise MemoryError('Read-only diagnostic deferred for RAM')
    import pandas as pd
    out=HERE/'diagnostic_001'
    if out.exists():
        raise FileExistsError('Fresh diagnostic folder required')
    out.mkdir()
    started=time.perf_counter()
    paths={
        'R4':FINAL/'round_004_20261105/execution_001/event_results.csv',
        'R5':FINAL/'round_005_20261106/execution_002/event_results.csv',
        'R6':FINAL/'round_006_20261106/execution_001/event_results.csv',
        'R8':FINAL/'round_008_20261106/execution_001/event_results.csv',
        'R9':FINAL/'round_009_20261106/execution_001/event_results.csv',
        'R11':FINAL/'round_011_20261106/execution_001/event_results.csv'}
    sources=list((ROOT/'testB').glob('*/round_008_linkage_audit_20261105/devset_positives.csv'))
    if len(sources)!=1:
        raise ValueError('One metadata source required')
    meta_path=sources[0]
    meta=pd.read_csv(meta_path,dtype={'rfid_id':str})
    meta['acc_id']=meta.acc_id.astype(int)
    if len(meta)!=100 or meta.acc_id.duplicated().any() or meta.rfid_id.nunique()!=82:
        raise ValueError('Metadata cohort changed')
    subset=meta[meta.tier<=1]
    if len(subset)!=60 or subset.rfid_id.nunique()!=55:
        raise ValueError('Tier01 cohort changed')
    fields=['acc_id','rfid_id','tier','conflict','dt_h','dist_km','발생유형']
    hashes={str(p):sha(p) for p in [meta_path,*paths.values()]}
    frames=[]
    for source,path in paths.items():
        frame=pd.read_csv(path,dtype={'rfid_id':str})
        frame['acc_id']=frame.acc_id.astype(int)
        frame['hit']=frame.hit.map(lambda x: str(x).strip().lower() in {'true','1'})
        if frame.duplicated(['acc_id','method','k']).any():
            raise ValueError(f'Duplicate event/method/budget in{source}')
        for (method,k),group in frame.groupby(['method','k']):
            if len(group)!=100 or set(group.acc_id)!=set(meta.acc_id):
                raise ValueError(f'Event denominator changed:{source}/{method}/{k}')
        joined=frame[['acc_id','rfid_id','method','k','hit']].merge(meta[fields],on=['acc_id','rfid_id'],validate='many_to_one',how='left',indicator=True)
        if not joined['_merge'].eq('both').all():
            raise ValueError('Stored event identity differs from unchanged metadata')
        joined=joined.drop(columns='_merge')
        joined['source']=source
        frames.append(joined)
    allrows=pd.concat(frames,ignore_index=True)
    records=[]
    for (source,method,k),group in allrows.groupby(['source','method','k'],sort=True):
        for scope,scoped in [('all',group),('tier01',group[group.tier<=1])]:
            records.append({'source':source,'method':method,'k':int(k),'stratum':'cohort','value':scope,'events':len(scoped),'rfids':scoped.rfid_id.nunique(),'hits':int(scoped.hit.sum())})
        for field in ['tier','conflict','발생유형','dt_h']:
            for value,scoped in group.groupby(field,dropna=False,sort=True):
                records.append({'source':source,'method':method,'k':int(k),'stratum':field,'value':str(value),'events':len(scoped),'rfids':scoped.rfid_id.nunique(),'hits':int(scoped.hit.sum())})
    pd.DataFrame(records).to_csv(out/'strata_counts.csv',index=False,encoding='utf-8-sig')
    allrows.to_csv(out/'unchanged_event_results_with_metadata.csv',index=False,encoding='utf-8-sig')
    overlap={}
    for scope,cohort in [('all',meta),('tier01',subset)]:
        ids=set(cohort.acc_id)
        overlap[scope]={}
        for k in [1,4]:
            selected=allrows[(allrows.k==k)&allrows.acc_id.isin(ids)]
            sets={f'{s}:{m}':set(g.loc[g.hit,'acc_id'].astype(int)) for (s,m),g in selected.groupby(['source','method'])}
            union=set().union(*sets.values())
            intersection=set.intersection(*sets.values()) if sets else set()
            overlap[scope][f'top{k}']={'event_denominator':len(cohort),'attempted_list_hit_union':sorted(union),
                'union_n':len(union),'all_list_hit_intersection':sorted(intersection),
                'by_saved_list':{name:sorted(values) for name,values in sets.items()},
                'NOT_a_deployable_selector':True,'budgets_or_pools_can_differ_between_rounds':True}
    (out/'retrospective_overlap.json').write_text(json.dumps(overlap,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(sha(Path(p))!=h for p,h in hashes.items()):
        raise ValueError('Read-only diagnostic input changed')
    receipt={'status':'complete','analysis':'Descriptive unchanged-label strata and retrospective overlap ONLY',
        'new_predictions':False,'new_labels':False,'performance_improvement_claim':False,'ram_preflight':preflight,
        'input_sha256':hashes,'source_sha256':sha(Path(__file__)),'rows_metadata':100,'rfids':82,'tier01_events':60,
        'elapsed_seconds':time.perf_counter()-started,
        'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}}
    (out/'EXECUTION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({s:{k:{'union_n':v['union_n'],'intersection':v['all_list_hit_intersection']} for k,v in data.items()} for s,data in overlap.items()},ensure_ascii=False))


if __name__=='__main__':
    main()
