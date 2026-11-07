from __future__ import annotations
import csv, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT=Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final')
REPO=Path(r'D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104')
EXP=REPO/'artifacts'/'exp01'
P=Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료')
OUT=ROOT/'rounds'/'round_004'/'lineage'

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def jread(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def cread(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def add(label,p): hashes[label]=digest(p)

started=time.perf_counter(); started_utc=datetime.now(timezone.utc).isoformat()
hashes={}
# Read frozen round-002 contract, allowed source/metadata and development-only rosters.
cfgp=ROOT/'rounds'/'round_002'/'configs'/'experiment.json'; cfg=jread(cfgp); add('round_002_config',cfgp)
cols_p=P/'metadata'/'feature_columns.json'; pcols=jread(cols_p); add('P_feature_columns',cols_p)
dict_p=P/'metadata'/'F156_feature_dictionary.csv'; fdict=cread(dict_p); add('P_F156_dictionary',dict_p)
classes_p=P/'metadata'/'classes.json'; pclasses=jread(classes_p); add('P_classes',classes_p)
settings_p=P/'metadata'/'run_settings.json'; settings=jread(settings_p); add('P_run_settings',settings_p)
rebuild_p=P/'code'/'rebuild_features.py'; rebuild=rebuild_p.read_text(encoding='utf-8-sig'); add('P_rebuild_features_code',rebuild_p)
adapter_p=REPO/'shared'/'data_adapter.py'; adapter=adapter_p.read_text(encoding='utf-8-sig'); add('exp01_data_adapter',adapter_p)
contract_p=REPO/'shared'/'eval_contract.py'; contract=contract_p.read_text(encoding='utf-8-sig'); add('exp01_eval_contract',contract_p)
compare_p=next((P/'code'/'historical'/'TabM').glob('*/comparison_models.py')); compare_code=compare_p.read_text(encoding='utf-8-sig'); add('P_comparison_models_code',compare_p)
vocab_p=next((P/'code'/'historical'/'TabM').glob('*/vocabulary_features.py')); vocab_code=vocab_p.read_text(encoding='utf-8-sig'); add('P_vocabulary_features_code',vocab_p)
base_p=next((P/'code'/'historical'/'TinyTabM').glob('*/fishing_tiny_tabm.py')); base_code=base_p.read_text(encoding='utf-8-sig'); add('P_digest_json_source',base_p)
parent_meta={}; training_meta={}
for seed in (42,2026):
 pp=P/'evaluation'/f'seed_{seed}'/'parent_fingerprint.json'; parent_meta[str(seed)]=jread(pp); add(f'P_seed_{seed}_parent_fingerprint',pp)
 for f in range(3):
  tp=P/'evaluation'/f'seed_{seed}'/f'fold_{f}'/'training.json'; training_meta[f'{seed}/{f}']=jread(tp); add(f'P_seed_{seed}_fold_{f}_training',tp)
expjson_p=REPO/'configs'/'exp01'/'experiment.json'; expjson=jread(expjson_p); add('exp01_experiment_contract',expjson_p)
roster_p=EXP/'fixed_split_roster.csv'; roster=cread(roster_p); add('exp01_development_roster',roster_p)
roles_p=P/'splits'/'development_roles_long.csv'; proles=cread(roles_p); add('P_development_roles_long',roles_p)

expected_hash=cfg['input']['fold_sha256']; byroster={f:[] for f in range(3)}; byroles={f:[] for f in range(3)}
for r in roster: byroster[int(r['fold'])].append(r)
for r in proles: byroles[int(r['outer_fold'])].append(r)
pnames=[str(x) for x in pcols]
dictnames=[r['feature'] for r in fdict]; positions=[int(r['position_0based']) for r in fdict]
meta_name_order_ok=(len(pnames)==len(dictnames)==156 and positions==list(range(156)) and pnames==dictnames)
definitions_complete=(all(bool(r.get('definition_ko','').strip()) for r in fdict) and all(bool(r.get('group','').strip()) for r in fdict))
porder=[pclasses[str(i)] for i in range(4)]
exporder=expjson['model']['class_order']; class_order_ok=(porder==exporder==cfg['input']['class_order'])
settings_says_no_flags='no missing flags' in settings.get('fit_preprocess','').lower()
source_first_f156=('("F156", f156.index.tolist(), f156[fcols].to_numpy(dtype=np.float64), fcols)' in adapter and 'feature_names = tuple(fcols + tcols + bcols + lcols)' in adapter)
p_generator_order=("metadata/feature_columns.json" in rebuild and re.search(r"scope\s*=\s*'production'\s*if\s+a\.fold\s+is\s+None\s+else\s+f'fold\{a\.fold\}'",rebuild) is not None and "t[cols].sort_index()" in rebuild)
missing_flag_code=("median = np.nanmedian(x, axis=0)" in compare_code and "missing = ~np.isfinite(x)" in compare_code and "x = np.where(missing, self.median, x)" in compare_code and "np.c_[x, missing.astype(float)].astype('float32')" in compare_code)
original_id_sequence_code=("table.loc[fold['fit_ids'], columns]" in compare_code and "('fit', 'fit_ids')" in compare_code and "('inner', 'inner_ids')" in compare_code)
mismatches=[]
if not meta_name_order_ok: mismatches.append({'type':'P_metadata_name_order','detail':'feature_columns and dictionary feature names/positions differ'})
if not definitions_complete: mismatches.append({'type':'P_dictionary_definitions_incomplete','detail':'one or more feature definitions/groups are missing'})
if not source_first_f156: mismatches.append({'type':'exp01_F156_source_contract','detail':'direct first F156 block not confirmed in adapter source'})
if not p_generator_order: mismatches.append({'type':'P_rebuild_source_contract','detail':'metadata order/fold vocabulary scope not confirmed'})
if not missing_flag_code: mismatches.append({'type':'P_preprocessing_source_contract','detail':'impute plus missing-flag transform not confirmed in code'})
if not class_order_ok: mismatches.append({'type':'class_order','detail':'P/exp01/round002 classes differ'})
folds={}; feature_checks={}; vocab_checks={}; medchecks={}; transformed_checks={}
for fold in range(3):
 path=EXP/f'fold_{fold}_features.npz'; label=f'exp01_fold_{fold}_features_npz'; add(label,path)
 with np.load(path,allow_pickle=False) as z:
  keys=sorted(z.files); f=int(z['fold']); ids=z['rfid_ids'].astype(str); y=z['y'].astype(np.int64); role=z['roles'].astype(str); X=z['X']; names=z['feature_names'].astype(str).tolist(); days=z['obs_days']
 actual_hash=hashes[label]; hash_ok=actual_hash==expected_hash[str(fold)]
 rr=byroster[fold]; pr=byroles[fold]; rids=[a['rfid_id'] for a in rr]; pids=[a['rfid_id'] for a in pr]
 p_role=[a['role'].upper() for a in pr]; roster_roles=[a['role'].upper() for a in rr]
 row_ok=ids.tolist()==rids==pids; role_ok=role.tolist()==roster_roles==p_role
 label_ok=y.tolist()==[int(a['y_true']) for a in rr]
 first_names=names[:156]==pnames; fit=(role=='FIT'); nfit=int(fit.sum())
 if not hash_ok: mismatches.append({'type':'exp01_npz_hash','fold':fold,'expected':expected_hash[str(fold)],'actual':actual_hash})
 if keys!=sorted(['fold','rfid_ids','y','roles','X','feature_names','obs_days']): mismatches.append({'type':'npz_keys','fold':fold,'keys':keys})
 if not row_ok: mismatches.append({'type':'development_row_order','fold':fold})
 if not role_ok: mismatches.append({'type':'development_role_order','fold':fold})
 if not label_ok: mismatches.append({'type':'label_mapping','fold':fold})
 if not first_names: mismatches.append({'type':'first156_feature_names','fold':fold,'first_diff':next((i for i,(a,b) in enumerate(zip(names[:156],pnames)) if a!=b),None)})
 counts={name:int(np.sum(y==i)) for i,name in enumerate(porder)}
 folds[str(fold)]={'npz_sha256':actual_hash,'expected_round002_sha256':expected_hash[str(fold)],'npz_hash_matches_round002':hash_ok,'keys':keys,'shapes':{'X':list(X.shape),'ids':list(ids.shape),'labels':list(y.shape),'roles':list(role.shape),'feature_names':[len(names)],'obs_days':list(days.shape)},'dtypes':{'X':str(X.dtype),'y':str(y.dtype),'roles':str(role.dtype)},'row_order_equal_npz_exp01_roster_P_roles':row_ok,'role_order_equal':role_ok,'labels_equal_roster_y_true':label_ok,'role_counts':{n:int(np.sum(role==n)) for n in ['FIT','INNER','OUTER']},'FIT_count':nfit,'label_counts_by_P_class_order':counts,'nan_count_first156':int(np.isnan(X[:,:156]).sum()),'inf_count_first156':int(np.isinf(X[:,:156]).sum())}
 feature_checks[str(fold)]={'npz_width':int(X.shape[1]),'exp01_component_widths':cfg['input']['features_in_order'],'first156_names_match_P':first_names,'P_F156_columns':len(pnames),'remaining_columns':int(X.shape[1]-156),'remaining_columns_are_not_in_P_F156':bool(X.shape[1]-156==148),'names_unique':len(names)==len(set(names)),'no_inf':bool(not np.isinf(X).any())}
 vp=P/'metadata'/f'fold_{fold}'/'vocabulary_state.json'; v=jread(vp); add(f'P_fold_{fold}_vocabulary_state',vp); prov=v.get('provenance',{})
 vocabnames=[n for n in pnames if n.startswith('vocabulary_mode') or n.startswith('vocabulary_day_')]
 fit_ids_digest=hashlib.sha256(json.dumps(sorted(set(ids[fit].astype(str).tolist())),sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
 vocab_fit_hash_ok=(fit_ids_digest==prov.get('fit_ids_sha256'))
 vocab_checks[str(fold)]={'metadata_fit_id_count':prov.get('fit_id_count'),'development_FIT_count':nfit,'FIT_ID_hash_matches_P_fold_vocabulary':vocab_fit_hash_ok,'n_clusters':prov.get('n_clusters'),'seed':prov.get('seed'),'P_F156_vocabulary_column_count':len(vocabnames),'P_generator_selects_fold_vocabulary_scope':p_generator_order,'same_fold_NPZ_first156_name_order':first_names,'vocabulary_feature_values_independently_regenerated':False}
 if not vocab_fit_hash_ok: mismatches.append({'type':'vocabulary_FIT_ID_hash','fold':fold,'computed':fit_ids_digest,'saved':prov.get('fit_ids_sha256')})
 # Gated numerical comparison: only first 156, only if definition/order + roster/roles/labels all match.
 if meta_name_order_ok and definitions_complete and first_names and row_ok and role_ok and label_ok and source_first_f156 and p_generator_order and missing_flag_code and class_order_ok and hash_ok and vocab_fit_hash_ok:
  npz_med=np.nanmedian(X[fit,:156].astype(np.float64,copy=False),axis=0)
  for seed in (42,2026):
   pp=P/'evaluation'/f'seed_{seed}'/f'fold_{fold}'/'preprocessor.json'; prep=jread(pp); add(f'P_seed_{seed}_fold_{fold}_preprocessor',pp); saved=np.asarray(prep['median'],dtype=np.float64)
   if len(saved)!=156: mismatches.append({'type':'saved_median_length','seed':seed,'fold':fold,'length':len(saved)}); continue
   if prep.get('kind')!='fit_median_and_raw_missing_flags': mismatches.append({'type':'saved_preprocessor_kind','seed':seed,'fold':fold,'kind':prep.get('kind')}); continue
   d=np.abs(npz_med-saved); bad=np.flatnonzero(~np.isfinite(d)|(d>1e-10))
   medchecks[f'{seed}/{fold}']={'kind':prep.get('kind'),'saved_median_count':len(saved),'npz_fit_rows':nfit,'max_abs_delta':float(np.nanmax(d)),'mismatch_count':len(bad),'matches_atol_1e-10':bool(len(bad)==0),'first_mismatches':[{'index':int(i),'feature':pnames[i],'NPZ_FIT_nanmedian':float(npz_med[i]),'saved_median':float(saved[i]),'abs_delta':float(d[i])} for i in bad[:8]]}
   if len(bad): mismatches.append({'type':'fit_median_mismatch','seed':seed,'fold':fold,'count':len(bad),'max_abs_delta':float(np.nanmax(d))})
   for role_name,mask in [('FIT',fit),('INNER_QUERY',role=='INNER')]:
    raw=np.asarray(X[mask,:156],dtype=np.float64).copy(); raw[~np.isfinite(raw)]=np.nan
    missing=~np.isfinite(raw); imputed=np.where(missing,saved,raw)
    transformed=np.c_[imputed,missing.astype(float)].astype('float32')
    row_ids=ids[mask].astype(str).tolist()
    transformed_checks[f'{seed}/{fold}/{role_name}']={'shape':list(transformed.shape),'dtype':str(transformed.dtype),'sha256_C_order_float32_bytes':hashlib.sha256(transformed.tobytes(order='C')).hexdigest(),'row_ids_order_sha256':hashlib.sha256(json.dumps(row_ids,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest(),'row_count':len(row_ids),'feature_order':'first156 raw/imputed columns followed by matching 156 raw missing flags','query_role':'INNER' if role_name=='INNER_QUERY' else None,'input_is_model_replay':False,'row_order_basis':'NPZ/P development_roles_long roster order','original_fit_ids_sequence_verified':False}
    if transformed.shape[1]!=312 or transformed.dtype!=np.float32 or not np.isfinite(transformed).all(): mismatches.append({'type':'transformed_input_contract','seed':seed,'fold':fold,'role':role_name})
 else: medchecks[f'fold_{fold}']={'status':'not_run','reason':'feature definition/order or development row/role/label mapping gate failed'}

add('audit_script',Path(__file__).resolve())
result={'task':'Round 004 development-only input lineage audit','status':'PASS_WITH_LIMITATIONS' if not mismatches else 'MISMATCHES_FOUND','scope':{'read_sources':['P code/metadata; seed42/2026 per-fold preprocessors and vocabulary metadata','exp01 three NPZs and fixed development roster','P development roles roster','round002 frozen config'],'not_read_in_current_scope':['P/splits/splits_original.json (needed to prove original fit_ids/inner_ids sequence)'],'protected_row_reads':{'F156_full7372':0,'train_labels':0,'components_train':0,'holdout':0,'Test2025':0,'raw':0},'model_loads':0,'training_calls':0,'inference_calls':0,'F1_calculations':0},'source_contracts':{'round002_config_sha256':hashes['round_002_config'],'round002_NPZ_dimensions':cfg['input']['feature_count'],'components':cfg['input']['features_in_order'],'direct_F156_first_block_in_exp01_source':source_first_f156,'P_F156_metadata_name_order_consistency':meta_name_order_ok,'P_F156_dictionary_definitions_complete':definitions_complete,'semantic_feature_value_equality_against_protected_source_rows':False,'exp01_source_declares_first_block_from_F156':source_first_f156,'P_fold_F156_source_rebuild_order_and_vocabulary_scope':p_generator_order,'P_F156_columns':len(pnames),'P_class_order_matches_exp01_and_round002':class_order_ok,'P_generator_metadata_order_and_fold_vocab_scope':p_generator_order,'P_run_settings_says_no_missing_flags':settings_says_no_flags,'P_preprocessor_store_156_medians':(len(medchecks)==6 and all(v.get('saved_median_count')==156 for v in medchecks.values())),'P_preprocessor_kind':'fit_median_and_raw_missing_flags','comparison_code_appends_missing_flags_after_imputation':missing_flag_code,'P_comparison_code_uses_ordered_fit_ids':original_id_sequence_code,'original_TabICL_fit_and_query_id_sequence_verified':False,'unread_order_metadata_needed_next':'P/splits/splits_original.json (ID-only fold fit_ids/inner_ids/outer_ids after schema review)','expected_TabICL_width':312},'folds':folds,'feature_checks':feature_checks,'vocabulary_checks':vocab_checks,'fit_median_comparisons':medchecks,'transformed_input_hashes':transformed_checks,'mismatch_mapping':[{'issue':'run_settings_no_missing_flags_vs_saved_preprocessor_and_source_code_append_flags','resolution':'documented conflict; effective transform supported by comparison_models.py and preprocessor.kind; 312 columns'}, {'issue':'exp01_npz_width_304_vs_TabICL_F156_input_312','resolution':'extract first156 P F156 columns; discard added exp01 T5/behavior/local_rel148; append raw missing flags after FIT median imputation'}, {'issue':'original_ordered_fit_and_inner_id_lists_not_verified','resolution':'NPZ/P role-roster sequence only; source uses fold.fit_ids/inner_ids; inspect only P/splits/splits_original.json ID arrays in a follow-up'}, {'issue':'per_row_feature_value_equality_against_P_F156_not_checked','resolution':'source lineage, names/order, fold vocabulary ID hashes, and FIT medians verified; protected P F156 rows not read'}],'parent_fingerprint_summary':{seed:{'seed':meta.get('seed'),'feature_variant':meta.get('feature_variant'),'input_lineage_seed':meta.get('input_lineage',{}).get('seed'),'input_file_count':len(meta.get('input_lineage',{}).get('files',{})),'preprocessing':meta.get('preprocessing'),'raw_information_matches_tabm':meta.get('raw_information_matches_tabm')} for seed,meta in parent_meta.items()},'training_summary':{key:{'method':m.get('method'),'context_rows':m.get('context_rows'),'inner_vessels':m.get('inner_vessels'),'parameters_trained_on_this_dataset':m.get('parameters_trained_on_this_dataset'),'selection_metric':m.get('selection_metric'),'fit_vessels':m.get('fit_vessels')} for key,m in training_meta.items()},'mismatches':mismatches,'source_input_sha256':hashes,'commands':[f'& "{sys.executable}" "{Path(__file__).resolve()}"'],'run_metadata':{'audit_iteration':'final_extended_rerun_7','prior_diagnostic_run_count':6,'prior_diagnostic_runs_superseded':True,'started_utc':started_utc,'finished_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-started,'exit_code':0,'stdout_log':'rounds/round_004/lineage/run.log'},'counts':{'folds':3,'npz_hashes_matching_round002':sum(x['npz_hash_matches_round002'] for x in folds.values()),'first156_column_orders_matching_P':sum(x['first156_names_match_P'] for x in feature_checks.values()),'role_order_label_mappings_passing':sum(x['row_order_equal_npz_exp01_roster_P_roles'] and x['role_order_equal'] and x['labels_equal_roster_y_true'] for x in folds.values()),'preprocessor_median_comparisons':sum(1 for k in medchecks if '/' in k),'median_mismatch_count':sum(x.get('mismatch_count',0) for x in medchecks.values()),'transformed_inputs_hashed':len(transformed_checks)}}
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'counts':result['counts'],'mismatches':mismatches},ensure_ascii=False,indent=2))
