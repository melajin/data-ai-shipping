from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import csv, hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final')
BASE = Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING')
P = next(BASE.glob('29-*/31*/**/TabICLv2_F156*'))
EXP = Path(r'D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01')
OUT = ROOT/'rounds'/'round_004'/'context_recovery'
FOLD = 0
SEED = 42


def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def digest_json(value) -> str:
    # Exact BASE.digest_json semantics for JSON-able lists of vessel IDs.
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8'))
def read_json(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def read_csv(p):
    with p.open('r',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


def main():
    t0=time.perf_counter(); started=datetime.now(timezone.utc).isoformat()
    split_p=P/'splits'/'splits_original.json'
    rule_p=P/'evaluation'/'final_fixed_decision_rule.json'
    parent_p=P/'evaluation'/'seed_42'/'parent_fingerprint.json'
    vocab_p=P/'metadata'/'fold_0'/'vocabulary_state.json'
    prep_p=P/'evaluation'/'seed_42'/'fold_0'/'preprocessor.json'
    roles_p=P/'splits'/'development_roles_long.csv'
    roster_p=EXP/'fixed_split_roster.csv'
    npz_p=EXP/'fold_0_features.npz'
    features_p=P/'metadata'/'feature_columns.json'
    classes_p=P/'metadata'/'classes.json'
    comparison_p=next((P/'code'/'historical'/'TabM').glob('*/comparison_models.py'))
    runner_p=next((P/'code'/'historical'/'TabM').glob('*/run_experiments.py'))
    base_p=next((P/'code'/'historical'/'TinyTabM').glob('*/fishing_tiny_tabm.py'))
    input_paths={'split_manifest':split_p,'decision_rule':rule_p,'parent_fingerprint':parent_p,
                 'fold0_vocabulary_state':vocab_p,'seed42_fold0_preprocessor':prep_p,
                 'P_development_roles':roles_p,'exp01_development_roster':roster_p,
                 'exp01_fold0_npz':npz_p,'P_feature_columns':features_p,'P_classes':classes_p,
                 'P_comparison_models_source':comparison_p,'P_split_generator_source':runner_p,
                 'P_BASE_digest_json_source':base_p}
    hashes={k:sha_file(v) for k,v in input_paths.items()}
    if hashes['exp01_fold0_npz']!='858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95':
        raise ValueError('exp01 development NPZ hash differs from reviewed lineage anchor')

    # ID-only split manifest schema; do not inspect or print any ID values outside intended fold0 export.
    manifest=read_json(split_p)
    if not isinstance(manifest,dict) or not isinstance(manifest.get('folds'),list):
        raise ValueError('split manifest is not the confirmed ID-only folds-list schema')
    if not isinstance(manifest.get('development_ids'),list) or not isinstance(manifest.get('holdout_ids'),list):
        raise ValueError('development/holdout ID-list schema mismatch')
    if set(manifest['development_ids']) & set(manifest['holdout_ids']):
        raise ValueError('manifest development/holdout ID sets overlap')
    folds=[x for x in manifest['folds'] if isinstance(x,dict) and x.get('fold')==FOLD]
    if len(folds)!=1: raise ValueError('fold0 entry missing or duplicated')
    fold=folds[0]
    for key,count in [('fit_ids',3144),('inner_ids',787)]:
        if key not in fold or not isinstance(fold[key],list) or not all(isinstance(x,str) for x in fold[key]):
            raise ValueError(f'fold0 {key} is not an ID string list')
        if len(fold[key])!=count or len(set(fold[key]))!=count:
            raise ValueError(f'fold0 {key} count/uniqueness mismatch')
    if not isinstance(fold.get('outer_ids'),list) or len(fold['outer_ids'])!=1966:
        raise ValueError('fold0 outer_ids list count mismatch (values not used)')
    fit_ids=list(fold['fit_ids']); inner_ids=list(fold['inner_ids'])
    if set(fit_ids)&set(inner_ids): raise ValueError('fold0 FIT/INNER IDs overlap')

    rule=read_json(rule_p)
    rule_entries=[x for x in rule.get('inner_choices',[]) if x.get('seed')==SEED and x.get('fold')==FOLD]
    if len(rule_entries)!=1: raise ValueError('frozen rule has no unique seed42/fold0 INNER digest')
    expected_inner_digest=rule_entries[0].get('inner_ids_sha256')
    actual_inner_digest=digest_json(inner_ids)
    if actual_inner_digest!=expected_inner_digest:
        raise ValueError('one direct BASE.digest_json comparison failed for fold0 INNER order')
    manifest_hash=hashes['split_manifest']
    if rule.get('split_manifest_sha256')!=manifest_hash:
        raise ValueError('split manifest SHA does not match frozen decision rule')
    parent=read_json(parent_p)
    recorded_split_hashes=[v for k,v in parent.get('input_lineage',{}).get('files',{}).items() if k.lower().endswith('work\\splits.json')]
    if len(recorded_split_hashes)!=1 or recorded_split_hashes[0]!=manifest_hash:
        raise ValueError('parent fingerprint does not bind this split manifest hash')

    vocab=read_json(vocab_p)['provenance']
    if vocab.get('fit_id_count')!=len(fit_ids) or vocab.get('fit_ids_sha256')!=digest_json(sorted(set(fit_ids))):
        raise ValueError('fold0 FIT membership differs from frozen vocabulary FIT-ID fingerprint')
    p_roles=[r for r in read_csv(roles_p) if int(r['outer_fold'])==FOLD]
    role_map={r['rfid_id']:r['role'].upper() for r in p_roles}
    roster=[r for r in read_csv(roster_p) if int(r['fold'])==FOLD]
    roster_map={r['rfid_id']:(r['role'].upper(),int(r['y_true'])) for r in roster}
    for name,ids,expected_role in [('FIT',fit_ids,'FIT'),('INNER',inner_ids,'INNER')]:
        if any(rid not in role_map or role_map[rid]!=expected_role for rid in ids):
            raise ValueError(f'fold0 {name} IDs disagree with P development role roster')
        if any(rid not in roster_map or roster_map[rid][0]!=expected_role for rid in ids):
            raise ValueError(f'fold0 {name} IDs disagree with exp01 development roster')

    pclasses=read_json(classes_p); class_names=[pclasses[str(i)] for i in range(4)]
    pcols=[str(x) for x in read_json(features_p)]
    prep=read_json(prep_p); med=np.asarray(prep['median'],dtype=np.float64)
    if len(pcols)!=156 or len(med)!=156 or prep.get('kind')!='fit_median_and_raw_missing_flags':
        raise ValueError('P F156 columns/preprocessor contract mismatch')
    with np.load(npz_p,allow_pickle=False) as z:
        npz_ids=z['rfid_ids'].astype(str); labels=z['y'].astype(np.int64); roles=z['roles'].astype(str)
        X=z['X']; names=z['feature_names'].astype(str).tolist()
        if X.shape!=(5897,304) or names[:156]!=pcols: raise ValueError('development NPZ first156 schema mismatch')
        if len(set(npz_ids.tolist()))!=len(npz_ids): raise ValueError('NPZ development IDs duplicate')
        index={rid:i for i,rid in enumerate(npz_ids.tolist())}
        fit_idx=np.asarray([index[x] for x in fit_ids],dtype=np.int64)
        inner_idx=np.asarray([index[x] for x in inner_ids],dtype=np.int64)
        if any(roles[i]!='FIT' for i in fit_idx) or any(roles[i]!='INNER' for i in inner_idx):
            raise ValueError('NPZ fold0 FIT/INNER roles mismatch')
        y_fit=labels[fit_idx].copy(); y_inner=labels[inner_idx].copy()
        if any(roster_map[rid][1]!=int(y) for rid,y in zip(fit_ids,y_fit)) or any(roster_map[rid][1]!=int(y) for rid,y in zip(inner_ids,y_inner)):
            raise ValueError('NPZ labels differ from development roster')
        def transform(idx):
            raw=np.asarray(X[idx,:156],dtype=np.float64).copy(); raw[~np.isfinite(raw)]=np.nan
            missing=~np.isfinite(raw); imputed=np.where(missing,med,raw)
            return np.c_[imputed,missing.astype(float)].astype(np.float32)
        X_fit=transform(fit_idx); X_inner=transform(inner_idx)
    if X_fit.shape!=(3144,312) or X_inner.shape!=(787,312): raise ValueError('transformed tensor shape mismatch')
    if not np.isfinite(X_fit).all() or not np.isfinite(X_inner).all(): raise ValueError('transformed tensor has non-finite values')
    feature_names=pcols+[f'{c}__missing_flag' for c in pcols]
    output_p=OUT/'fold0_seed42_context.npz'
    np.savez_compressed(output_p,fold=np.int64(FOLD),seed=np.int64(SEED),
        ids_fit=np.asarray(fit_ids,dtype=str),ids_inner=np.asarray(inner_ids,dtype=str),
        X_fit=X_fit,X_inner=X_inner,y_fit=y_fit,y_inner=y_inner,
        feature_names=np.asarray(feature_names,dtype=str),class_names=np.asarray(class_names,dtype=str))
    output_hash=sha_file(output_p)
    result={'status':'CONTEXT_READY','scope':{'fold':FOLD,'seed':SEED,'development_only':True,
        'holdout_feature_label_probability_rows_loaded':0,'split_manifest_includes_holdout_id_metadata':True,'feature_rows_outside_dev_loaded':0,'model_or_checkpoint_loaded':False,
        'inference_or_training':False,'F1_computed':False},
        'split_sequence':{'source_linkage':'P splits_original SHA matches both frozen decision rule and seed42 parent-fingerprint work/splits.json hash',
            'inner_digest_serializer':'BASE.digest_json=json.dumps(jsonable(value),sort_keys=True,ensure_ascii=False) UTF-8 SHA256',
            'inner_digest_expected':expected_inner_digest,'inner_digest_actual':actual_inner_digest,'inner_order_match':True,
            'fit_membership_vocab_hash_match':True,'fit_order_source':'split manifest list, source .loc[fold[fit_ids]]',
            'future_query_ids_first2':inner_ids[:2]},
        'arrays':{'X_fit':{'shape':list(X_fit.shape),'dtype':str(X_fit.dtype),'sha256_C_order_float32':sha_bytes(X_fit.tobytes(order='C'))},
            'X_inner':{'shape':list(X_inner.shape),'dtype':str(X_inner.dtype),'sha256_C_order_float32':sha_bytes(X_inner.tobytes(order='C'))},
            'ids_fit_sha256':digest_json(fit_ids),'ids_inner_sha256':digest_json(inner_ids),
            'y_fit':{'shape':list(y_fit.shape),'dtype':str(y_fit.dtype)},'y_inner':{'shape':list(y_inner.shape),'dtype':str(y_inner.dtype)},
            'feature_count':len(feature_names),'class_names':class_names},
        'input_sha256':hashes,'output':{'path':str(output_p),'bytes':output_p.stat().st_size,'sha256':output_hash},
        'command':f'& "{sys.executable}" -B "{Path(__file__).resolve()}"',
        'started_utc':started,'elapsed_seconds':time.perf_counter()-t0}
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'counts':{'fit':len(fit_ids),'inner':len(inner_ids)},
        'inner_digest_match':True,'tensor_shapes':[list(X_fit.shape),list(X_inner.shape)]},ensure_ascii=False))

if __name__=='__main__': main()
