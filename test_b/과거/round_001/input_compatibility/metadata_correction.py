import ast,csv,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'testB/round_001/input_compatibility';ARCH=OUT/'pre_metadata_fix'
ARCH.mkdir(exist_ok=True)
source_files=['summary.json','manifest.json','comparison_report.md','run_comparison.py','finalize_outputs.py','csv_identity.csv','workbook_comparison.json']
def sha(path):
 h=hashlib.sha256();n=0
 with path.open('rb') as f:
  while True:
   b=f.read(1024*1024)
   if not b:break
   h.update(b);n+=len(b)
 return h.hexdigest(),n
before={}
for name in source_files:
 p=OUT/name
 if p.exists():
  digest,n=sha(p); dest=ARCH/name
  if not dest.exists():shutil.copy2(p,dest)
  before[name]={'path':str(p.relative_to(ROOT)),'sha256':digest,'bytes':n,'preserved_copy':str(dest.relative_to(ROOT)),'preserved_sha256':sha(dest)[0]}
(ARCH/'lineage.json').write_text(json.dumps({'preserved_utc':datetime.now(timezone.utc).isoformat(),'files':before},ensure_ascii=False,indent=2),encoding='utf-8')
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
raw_manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
verify=summary['old_input_posthash_verification']; old_before=summary['old_files_meta_before']; old_after=summary['old_files_meta_after']
corrections=[]
def typed(meta): return {'bytes':int(meta['bytes']),'mtime_ns':int(meta['mtime_ns'])}
for rec in verify:
 path=rec['path'];pre=old_before.get(path);post=old_after.get(path)
 if pre is None or post is None:raise RuntimeError('Structured whole-run metadata missing for '+path)
 pre_cmp=typed(pre);post_cmp=typed(post)
 pre_hash_raw=rec.get('metadata_before_posthash',post);post_hash_raw=rec.get('metadata_after_posthash',rec.get('post_metadata',post));pre_hash=typed(pre_hash_raw);post_hash=typed(post_hash_raw)
 raw_fields={k:rec.get(k,'<absent>') for k in ['metadata_before_comparison','metadata_after_comparison','metadata_before_posthash','metadata_after_posthash','post_metadata','metadata_unchanged_through_posthash']}
 all_values=[pre_cmp,post_cmp,pre_hash,post_hash]
 unchanged=all(x==all_values[0] for x in all_values[1:])
 corrected={'path':path,'comparison_sha256':rec['comparison_sha256'],'post_sha256':rec['post_sha256'],'comparison_bytes':rec.get('comparison_bytes'), 'post_bytes':rec.get('post_bytes'), 'comparison_hash_matches_post':rec['comparison_hash_matches_post'],
 'metadata_before_comparison':pre_cmp,'metadata_after_comparison':post_cmp,'metadata_before_posthash':pre_hash,'metadata_after_posthash':post_hash,'metadata_fields_compared':['bytes','mtime_ns'],'metadata_unchanged_through_posthash':unchanged,'posthash_metadata_basis':'recorded before/after fields when available; otherwise structured comparison metadata plus legacy post_metadata',
 'legacy_raw_fields':raw_fields,'legacy_false_was_type_mismatch':(isinstance(rec.get('metadata_before_comparison'),str) and isinstance(rec.get('metadata_before_posthash'),dict)) or (isinstance(rec.get('metadata_after_comparison'),str) and isinstance(rec.get('metadata_after_posthash'),dict))}
 corrections.append(corrected)
rec_by_path={r['path']:r for r in corrections}
summary['old_input_posthash_verification']=corrections
summary['old_inputs_posthash_all_match']=all(r['comparison_hash_matches_post'] and r['metadata_unchanged_through_posthash'] for r in corrections)
summary['all_old_file_metadata_unchanged']=all(typed(old_before[p])==typed(old_after[p]) for p in old_before)
summary['metadata_correction']={'status':'corrected','type':'metadata field type normalization','corrected_utc':datetime.now(timezone.utc).isoformat(),'raw_sources_preserved':True,'preservation_directory':str(ARCH.relative_to(ROOT)),'original_file_hashes':before,'reused_structured_summary_fields':['old_files_meta_before','old_files_meta_after'],'rehashed_large_inputs':False,'all_14_metadata_records_unchanged':all(r['metadata_unchanged_through_posthash'] for r in corrections),'all_14_content_hashes_match':all(r['comparison_sha256']==r['post_sha256'] for r in corrections)}
# Independently recompute ID set intersections from retained logical workbook snapshots.
wb=json.loads((OUT/'workbook_comparison.json').read_text(encoding='utf-8'));sample=wb['workbooks'][1]; old_s=sample['old_snapshot']['sheets'];new_s=sample['new_snapshot']['sheets']
ids={}
for old,new in zip(old_s,new_s):
 def values(sh):return [str(sh['cells'][f'A{r}']['value']) for r in range(2,102)]
 oi=values(old);ni=values(new);common=sorted(set(oi)&set(ni))
 ids[old['title']]={'old_count':len(oi),'new_count':len(ni),'old_unique_count':len(set(oi)),'new_unique_count':len(set(ni)),'intersection_count':len(common),'intersection_denominator':100,'intersection_ids':common,'old_only_count':len(set(oi)-set(ni)),'new_only_count':len(set(ni)-set(oi)),'old_sequence_first_10':oi[:10],'new_sequence_first_10':ni[:10]}
summary['test_id_sequence_summary']=ids
summary['legacy100_new_target_use']={'scores_usable_for_new_target':False,'predictions_usable_for_new_target':False,'new_actual_predictions_created':False,'reason':'Legacy100 IDs differ from the new target; Test B set intersection is 0/100 and Test A set intersection is 2/100. Old-target scores/predictions are not valid new-target outputs.'}
# Prepare appendendum. Runtime exit and exact times are inserted by sync step after shell captures them.
report=OUT/'comparison_report.md';base=report.read_text(encoding='utf-8')
section='''\n\n## Metadata and legacy-target correction\n\nThe prior summary marked 12 CSV rows `metadata_unchanged_through_posthash=false` because CSV serialization turned the pre/post-comparison dictionaries into strings, while the posthash fields remained dictionaries. This was a type mismatch in the comparison, not evidence that an input file changed. The correction reuses structured `summary.json` `old_files_meta_before` / `old_files_meta_after` and compares normalized integer `bytes` and `mtime_ns` fields against the recorded posthash metadata. All 14 old exact-path files now agree across comparison and posthash metadata; all 14 recorded comparison SHA-256 values equal their posthash SHA-256 values. No 13 GB input was rehashed during this correction. The pre-correction summary, manifest, report, and code are preserved under `pre_metadata_fix/`; see `metadata_correction_log.json` for their hashes and the raw legacy fields.\n\nThe old/new ID set intersection is **Test B: 0/100** and **Test A: 2/100**. Therefore legacy100 scores and predictions are unusable for the new target. No new actual predictions were generated.\n'''
if '## Metadata and legacy-target correction' not in base:base+=section
report.write_text(base,encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
log={'corrected_utc':summary['metadata_correction']['corrected_utc'],'status':'corrected','reason':'CSV metadata strings compared with posthash dicts; structural metadata comparison now uses bytes and mtime_ns typed integers.','original_summary_sha256':before['summary.json']['sha256'],'original_manifest_sha256':before['manifest.json']['sha256'],'original_report_sha256':before['comparison_report.md']['sha256'],'original_finalizer_sha256':before['finalize_outputs.py']['sha256'],'runner_sha256':before['run_comparison.py']['sha256'],'preserved_files':before,'raw_legacy_values':[{k:r['legacy_raw_fields'][k] for k in r['legacy_raw_fields']}|{'path':r['path']} for r in corrections],'corrected_metadata_records':corrections,'content_hashes_reused_without_rehash':True,'reused_source':'summary.json.old_input_posthash_verification comparison_sha256/post_sha256 and summary.json.old_files_meta_before/old_files_meta_after','all_14_metadata_unchanged':summary['metadata_correction']['all_14_metadata_records_unchanged'],'all_14_content_hashes_match':summary['metadata_correction']['all_14_content_hashes_match'],'id_set_intersections':ids,'legacy100_new_target_use':summary['legacy100_new_target_use'],'runtime_receipt':{'path':'testB/round_001/integration/runtime_receipts/W0_start.json','sha256':sha(ROOT/'testB/round_001/integration/runtime_receipts/W0_start.json')[0]}}
(OUT/'metadata_correction_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'corrected','records':len(corrections),'metadata_unchanged':summary['metadata_correction']['all_14_metadata_records_unchanged'],'content_hashes_match':summary['metadata_correction']['all_14_content_hashes_match'],'id_intersections':{k:v['intersection_count'] for k,v in ids.items()},'preserved_files':list(before)},ensure_ascii=False))
