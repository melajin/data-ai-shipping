"""Fixed FIT 4-CV gate: same 304 baseline vs 304+2 geometry sequence features."""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import csv, gc, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
import psutil

HERE=Path(__file__).resolve().parent
R25=HERE.parent/'round_025'
EXP01=Path(r'D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01')
SOURCE=HERE/'worker'/'derived_features.csv'
NAMES=('turn_sign_reversal_fraction','nonlocal_return_vertex_fraction')
RESOURCE=[]

def save(name,obj):
    (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def guard(stage,entry=False):
    p=psutil.Process()
    if os.name=='nt':p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    m=psutil.virtual_memory()
    r={'utc':datetime.now(timezone.utc).isoformat(),'stage':stage,'available_gib':m.available/2**30,
       'rss_gib':p.memory_info().rss/2**30,'expected_peak_gib':.5,
       'other_python':[q.pid for q in psutil.process_iter(['name']) if q.pid!=p.pid and q.info['name'] and 'python' in q.info['name'].lower()]}
    RESOURCE.append(r);save('fit_resource_checks.json',RESOURCE)
    if r['available_gib']<(1.5 if entry else 1.) or r['rss_gib']>.75:
        raise RuntimeError('RAM gate; defer fit')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def cm_metrics(y,p):
    cm=np.bincount(y*4+p,minlength=16).reshape(4,4)
    tp=cm.diagonal();sup=cm.sum(1);pred=cm.sum(0)
    f1=np.divide(2*tp,sup+pred,out=np.zeros(4),where=sup+pred>0)
    return {'correct':int(tp.sum()),'micro':float(tp.sum()/len(y)),'macro':float(f1.mean()),
            'tp':tp.tolist(),'f1':f1.tolist(),'precision':np.divide(tp,pred,out=np.zeros(4),where=pred>0).tolist(),
            'recall':np.divide(tp,sup,out=np.zeros(4),where=sup>0).tolist(),'cm':cm.tolist()}

guard('entry_before_numeric_import',True)
import numpy as np
import lightgbm as lgb

def main():
    if (HERE/'fit_results.json').exists() or (HERE/'fit_predictions_frozen.npz').exists():
        raise RuntimeError('Existing gate result; do not overwrite frozen evidence')
    if not SOURCE.exists():raise FileNotFoundError(SOURCE)
    guard('read_small_feature_cache')
    with np.load(EXP01/'fold_0_features.npz',allow_pickle=False) as z:
        roles=z['roles'].astype(str); all_ids=z['rfid_ids'].astype(str)
        fit=roles=='FIT';ids=all_ids[fit];y=z['y'][fit].astype(np.int64)
        X=z['X'][fit].astype(np.float32)
        names=z['feature_names'].astype(str)
    assert X.shape==(3144,304) and len(set(ids))==3144 and len(names)==304
    assert not set(NAMES)&set(names)
    rows={}
    with SOURCE.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        assert set(['rfid_id',*NAMES]).issubset(reader.fieldnames)
        for r in reader:
            key=str(r['rfid_id'])
            if key in rows:raise ValueError('duplicate vessel feature')
            rows[key]=[float(r[n]) if r[n] and r[n].lower() not in ('nan','null') else float('nan') for n in NAMES]
    missing_ids=set(ids)-set(rows)
    if missing_ids:raise ValueError(f'missing FIT IDs count={len(missing_ids)}')
    addon=np.array([rows[i] for i in ids],dtype=np.float32)
    if np.isinf(addon).any():raise ValueError('infinite derived feature')
    config=json.loads((R25/'configs/experiment.json').read_text(encoding='utf-8'))
    params=config['lgbm'];assert params['n_jobs']==1
    pred={n:np.full(len(y),-1,dtype=np.int8) for n in ('baseline','candidate')}
    fold_out=[];fit_log=[]
    for fold in range(4):
        guard(f'cv{fold}_before_fit')
        with np.load(R25/f'artifacts/gate/feature_evidence/fold_{fold}_features.npz',allow_pickle=False) as z:
            tr=z['train_indices'].astype(int);va=z['valid_indices'].astype(int)
            t5=z['t5_matrix'].astype(np.float32)
            assert np.array_equal(z['train_labels'],y[tr])
        assert not set(tr)&set(va) and len(tr)+len(va)==len(y)
        base=X.copy();base[:,156:166]=t5
        fold_rec={'fold':fold,'n_train':len(tr),'n_valid':len(va),'models':{}}
        for name in ('baseline','candidate'):
            guard(f'cv{fold}_{name}_fit')
            mat=base if name=='baseline' else np.column_stack([base,addon])
            model=lgb.LGBMClassifier(**params)
            fit_log.append({'fold':fold,'name':name,'status':'started','utc':datetime.now(timezone.utc).isoformat()})
            save('fit_progress.json',fit_log)
            model.fit(mat[tr],y[tr])
            p=model.predict(mat[va]).astype(np.int8)
            pred[name][va]=p
            fold_rec['models'][name]=cm_metrics(y[va],p)
            fit_log[-1]['status']='completed';save('fit_progress.json',fit_log)
            del model,mat,p
            gc.collect()
        fold_out.append(fold_rec)
        del base,t5
        gc.collect()
    assert all(np.all(v>=0) for v in pred.values())
    np.savez_compressed(HERE/'fit_predictions_frozen.npz',ids=ids,y=y,**pred)
    result={'baseline':cm_metrics(y,pred['baseline']),'candidate':cm_metrics(y,pred['candidate']),
            'folds':fold_out,'n_fits':len(fit_log),'source_sha256':digest(SOURCE),
            'input_npz_sha256':digest(EXP01/'fold_0_features.npz'),
            't5_evidence_sha256':[digest(R25/f'artifacts/gate/feature_evidence/fold_{k}_features.npz') for k in range(4)],
            'plan_sha256':digest(HERE/'ROUND_PLAN.md'),'code_sha256':digest(Path(__file__)),
            'missing_feature_counts':np.isnan(addon).sum(0).tolist()}
    with np.load(R25/'artifacts/gate/predictions_baseline.npz',allow_pickle=False) as z:
        replay_ok=(np.array_equal(z['row_index'],np.arange(len(y))) and
                   np.array_equal(z['y_true'],y) and np.array_equal(z['y_pred'],pred['baseline']))
    delta=result['candidate']['correct']-result['baseline']['correct']
    bt=result['baseline']['tp'];ct=result['candidate']['tp'];bf=result['baseline']['f1'];cf=result['candidate']['f1']
    result['gate']={'delta_correct':delta,'baseline_replay_exact':bool(replay_ok),
                    'candidate_min1833':result['candidate']['correct']>=1833,
                    'delta_min16':delta>=16,'target_tp_and_f1_gain':any(ct[k]>bt[k] and cf[k]>bf[k] for k in (1,2)),
                    'tp0_no_drop':ct[0]>=bt[0],'tp3_no_drop':ct[3]>=bt[3]}
    result['gate']['pass']=all(v for k,v in result['gate'].items() if k not in ('delta_correct','pass'))
    save('fit_results.json',result)
    guard('complete')
    print(json.dumps(result['gate'],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
