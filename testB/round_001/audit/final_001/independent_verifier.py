from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import csv,ctypes,hashlib,importlib.util,io,json,math,os,platform,re,struct,sys,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
REPO=Path.cwd().parent; ROUND=REPO/'testB'/'round_001'; OUT=ROUND/'audit'/'final_001'; OUT.mkdir(parents=True,exist_ok=True)
START=datetime.now(timezone.utc).isoformat(); TIMING=ROUND/'timing'; FIX=TIMING/'fix_20261105_w2f'; W0=ROUND/'input_compatibility'
TARGETS=[ROUND/'timing/timing_interface.py',ROUND/'timing/publish_legacy_preparation.py',ROUND/'timing/input_split_manifest.json',ROUND/'timing/comparison_readiness_100.csv',ROUND/'timing/summary.json',ROUND/'timing/readiness_report.md',ROUND/'timing/code_lineage.json',ROUND/'timing/run_tie_order_regression.py',FIX/'pre_change_hashes.json',FIX/'post_change_hashes.json',FIX/'process_result.json',FIX/'syntax_process_result.json',FIX/'stdout.log',FIX/'stderr.log',FIX/'syntax_stdout.log',FIX/'syntax_stderr.log',FIX/'environment.json',FIX/'memory_before_tests.json',FIX/'memory_before_syntax.json',FIX/'docfix_20261105/process_result.json',FIX/'docfix_20261105/stdout.log',FIX/'docfix_20261105/stderr.log',W0/'run_comparison.py',W0/'finalize_outputs.py',W0/'metadata_correction.py',W0/'sync_metadata_correction.py',W0/'summary.json',W0/'manifest.json',W0/'comparison_report.md',W0/'csv_identity.csv',W0/'workbook_cell_differences.csv',W0/'workbook_comparison.json',W0/'metadata_correction_log.json',W0/'stdout.log',W0/'stderr.log',W0/'exit_status.txt',W0/'correction_exit_status.txt',W0/'correction_sync_exit_status.txt',W0/'correction_stdout.log',W0/'correction_stderr.log',W0/'correction_sync_stdout.log',W0/'correction_sync_stderr.log',W0/'finalizer_exit_status.txt',W0/'finalizer_stdout.log',W0/'finalizer_stderr.log',ROUND/'integration/runtime_receipts/W0_start.json',ROUND/'integration/runtime_receipts/W0_process.json',ROUND/'integration/runtime_receipts/W2F_start.json',ROUND/'integration/runtime_receipts/W2F_process.json',REPO/'testB/intake/1103_v2/inspection_001/archive_manifest.json',ROUND/'audit/v2_id_recheck_001/summary.json',ROUND/'audit/v2_id_recheck_001/process_result.json',ROUND/'audit/v2_id_recheck_001/recheck_report.md',OUT/'independent_verifier.py']
def stamp(): return datetime.now(timezone.utc).isoformat()
def readj(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def hfile(p,chunk=1024*1024):
 h=hashlib.sha256();n=0
 with Path(p).open('rb') as f:
  while True:
   b=f.read(chunk)
   if not b: break
   h.update(b);n+=len(b)
 return h.hexdigest(),n
def mem():
 class MS(ctypes.Structure):
  _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('avail',ctypes.c_ulonglong),('page_total',ctypes.c_ulonglong),('page_avail',ctypes.c_ulonglong),('virt_total',ctypes.c_ulonglong),('virt_avail',ctypes.c_ulonglong),('ext_avail',ctypes.c_ulonglong)]
 m=MS();m.length=ctypes.sizeof(MS)
 if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)): raise OSError('GlobalMemoryStatusEx failed')
 return {'available_bytes':int(m.avail),'total_bytes':int(m.total),'available_mib':round(m.avail/1048576,1),'load_percent':int(m.load)}
def fstat(p):
 s=Path(p).stat();return {'exists':True,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
pre={}
for p in TARGETS:
 k=str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)
 try: d,n=hfile(p);pre[k]={'sha256':d,'bytes':n,'mtime_ns':p.stat().st_mtime_ns,'status':'hashed'}
 except FileNotFoundError: pre[k]={'status':'missing'}
results=[]
def add(name,status,evidence,issue=None): results.append({'id':name,'status':status,'evidence':evidence,**({'issue':issue} if issue else {})})

# W2F before/after and process evidence.
pre_records=readj(FIX/'pre_change_hashes.json');post_records=readj(FIX/'post_change_hashes.json')
proc=readj(FIX/'process_result.json');syntax=readj(FIX/'syntax_process_result.json');docfix=readj(FIX/'docfix_20261105/process_result.json')
docfix_text=json.loads(docfix.get('stdout_text','{}'))
lineage=readj(TIMING/'code_lineage.json');tsum=readj(TIMING/'summary.json');manifest=readj(TIMING/'input_split_manifest.json')
current_post={};post_match=True
for r in post_records:
 p=TIMING/r['file'].replace('\\','/')
 try: d,n=hfile(p);current_post[r['file']]={'sha256':d,'bytes':n,'exists':True};post_match &= d==r['sha256'] and n==r['bytes']
 except FileNotFoundError: current_post[r['file']]={'exists':False};post_match=False
prechecks=[]
for r in pre_records:
 p=FIX/'pre_change'/r['file']
 try: d,n=hfile(p);prechecks.append({'file':r['file'],'match':d==r['sha256'] and n==r['bytes'],'sha256':d,'bytes':n})
 except FileNotFoundError: prechecks.append({'file':r['file'],'match':False,'missing':True})
w2f_start=readj(ROUND/'integration/runtime_receipts/W2F_start.json')['result']; w2f_receipt=readj(ROUND/'integration/runtime_receipts/W2F_process.json')
code_sha=hfile(TIMING/'timing_interface.py')[0]
docfix_ok=docfix.get('actual_exit_code')==0 and docfix_text.get('exit_code')==0 and docfix_text.get('code_changed') is False and docfix_text.get('existing_checks_rerun') is False
proc_ok=proc.get('exit_code')==0 and proc.get('checks')==14 and proc.get('code_sha256_before')==proc.get('code_sha256_after')==code_sha and syntax.get('exit_code')==0 and w2f_receipt.get('exit_code')==0 and docfix_ok
add('w2f_execution_receipts_and_hash_lineage','pass' if proc_ok and post_match and all(x['match'] for x in prechecks) else 'fail',{
 'timing_fix_exit':proc.get('exit_code'),'checks':proc.get('checks'),'scope':proc.get('scope'),'syntax_exit':syntax.get('exit_code'),
 'root_process_receipt_exit':w2f_receipt.get('exit_code'),'docfix_exit':docfix.get('actual_exit_code'),'docfix_output':docfix_text,
 'code_sha256_before_after_current':[proc.get('code_sha256_before'),proc.get('code_sha256_after'),code_sha],
 'pre_snapshots_all_match':all(x['match'] for x in prechecks),'pre_snapshot_checks':prechecks,'post_hashes_all_match':post_match,
 'W2F_launch_model_effort':{'model':w2f_start.get('model'),'effort':w2f_start.get('effort'),'provider_internal_runtime':'unknown'}},
 None if proc_ok and post_match and all(x['match'] for x in prechecks) else 'W2F 실행, 전후 해시 또는 스냅샷 불일치')

# Independent synthetic cases; producer self_check is not the verifier.
spec=importlib.util.spec_from_file_location('timing_interface_audit',TIMING/'timing_interface.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
P=mod.TimingParams;Err=mod.ContractError;estimate=mod.estimate_vessel
def pars(hours=2,rows=3,gap=1,source='synthetic-independent'): return P(.5,'gt',gap,hours,rows,source)
def blank(r): return all(getattr(r,k) is None for k in ('a_ts','a_score','a_source_row','b_ts','b_score','b_source_row','c_ts','c_score','c_source_row','c_passed'))
def reject_gap():
 try:P(.5,'gt',1.01,0,1,'synthetic').validate()
 except Err:return True
 return False
def reject_source():
 try:P(.5,'gt',1,0,1,'').validate()
 except Err:return True
 return False
cases={}
def run_case(k,fn):
 try: cases[k]={'pass':bool(fn())}
 except Exception as e: cases[k]={'pass':False,'error':type(e).__name__+': '+str(e)}
run_case('max_gap_over_1_rejected',reject_gap)
run_case('hour_0_to_2_splits',lambda:(lambda r:r.b_ts==2 and r.segment_source_rows==['peak'] and r.status=='persistence_not_met')(estimate([{'ts':0,'score':.8,'source_row_id':'h0'},{'ts':2,'score':.9,'source_row_id':'peak'}],pars(1,2))))
run_case('A_tie_first_original_input',lambda:(lambda r:(r.a_ts,r.a_source_row,r.b_ts)==(4,'input_first',4))(estimate([{'ts':4,'score':.9,'source_row_id':'input_first'},{'ts':1,'score':.9,'source_row_id':'earlier_time'}],pars(0,1))))
run_case('B_C_same_segment_and_C_equals_B',lambda:(lambda r:r.status=='candidate_ready' and r.b_ts==2 and r.c_ts==r.b_ts and r.segment_source_rows==['t2','t3','t4'])(estimate([{'ts':4,'score':.7,'source_row_id':'t4'},{'ts':2,'score':.7,'source_row_id':'t2'},{'ts':3,'score':.7,'source_row_id':'t3'}],pars(2,3))))
run_case('NaN_splits_segment',lambda:(lambda r:r.b_ts==2 and r.segment_source_rows==['peak'])(estimate([{'ts':0,'score':.8,'source_row_id':'before'},{'ts':1,'score':float('nan'),'source_row_id':'nan'},{'ts':2,'score':.9,'source_row_id':'peak'}],pars(0,1))))
run_case('identical_duplicates_trace_unique_time_persistence',lambda:(lambda r:r.status=='persistence_not_met' and r.duplicate_timestamp_rows==1 and r.segment_source_rows==['d1','d2'] and r.c_ts is None)(estimate([{'ts':1,'score':.9,'source_row_id':'d1'},{'ts':1,'score':.9,'source_row_id':'d2'}],pars(0,2))))
run_case('conflicting_valid_duplicates_blank_ABC',lambda:(lambda r:r.status=='data_conflict' and blank(r) and set(r.conflict_source_rows)=={'v1','v2'})(estimate([{'ts':1,'score':.8,'source_row_id':'v1'},{'ts':1,'score':.9,'source_row_id':'v2'}],pars(0,1))))
run_case('missing_duplicates_and_missing_valid_conflict',lambda:(lambda a,b:a.status=='insufficient_data' and a.duplicate_timestamp_rows==1 and b.status=='data_conflict' and blank(b) and set(b.conflict_source_rows)=={'missing','valid'})(estimate([{'ts':1,'score':None,'source_row_id':'none'},{'ts':1,'score':float('nan'),'source_row_id':'nan'}],pars(0,1)),estimate([{'ts':1,'score':None,'source_row_id':'missing'},{'ts':1,'score':.9,'source_row_id':'valid'}],pars(0,1))))
run_case('parameter_source_required',reject_source)
synthetic_ok=len(cases)==8 and all(x['pass'] for x in cases.values())
add('w2f_independent_synthetic_contract_cases','pass' if synthetic_ok else 'fail',{'cases':cases,'independent_case_count':len(cases),'actual_data_used':False,'producer_self_check_used_as_verification':False})

# Current manifest/generator/summary/lineage/readiness agreement after the doc fix.
generator=(TIMING/'publish_legacy_preparation.py').read_text(encoding='utf-8-sig')
readiness=(TIMING/'readiness_report.md').read_text(encoding='utf-8-sig')
tie=str(manifest.get('method_states',{}).get('ties_and_duplicates',''));gap=str(manifest.get('method_states',{}).get('max_gap_policy',''))
summary_tie=str(tsum.get('tie_break_contract',''))+' '+str(tsum.get('A_tie_semantics',''))
lin=str(lineage.get('round_copy',{}).get('change',''))
tie_ok=all('first maximum in original input order' in s.lower() for s in (tie,summary_tie,lin)) and not any('earliest maximum' in s.lower() or 'earliest max' in s.lower() for s in (tie,summary_tie,lin)) and 'ties_and_duplicates' in generator
maxgap_ok='at most 1' in gap and 'values above 1 raise ContractError' in gap and 'at most 1' in tsum.get('max_gap_policy','') and 'max_gap_policy' in generator
pending_ok=manifest.get('split_design_pending',{}).get('actual_assignment','').startswith('pending') and tsum.get('status')=='preparation_only_pending_supervisor_gate' and tsum.get('B_computed')==0 and tsum.get('C_computed')==0
ref=tsum.get('target_reference_id_overlap',{});ref_ok=ref.get('count')==95 and 'membership only' in ref.get('interpretation','') and 'unmeasured' in ref.get('interpretation','')
floor_ok='unresolved' in tsum.get('score_floor_semantics','').lower()
readable='\ufffd' not in readiness and re.search(r'\?{3,}',readiness) is None
round_hashes=tsum.get('round_output_hashes',{})
round_hash_checks={name:hfile(TIMING/name)[0]==expected for name,expected in round_hashes.items() if (TIMING/name).exists()}
lineage_current=lineage.get('round_copy',{}).get('sha256')==code_sha and round_hash_checks and all(round_hash_checks.values())
contract_ok=tie_ok and maxgap_ok and pending_ok and ref_ok and floor_ok and readable and lineage_current
add('w2f_current_contract_and_pending_scope','pass' if contract_ok else 'fail',{'manifest_tie':tie,'summary_tie':summary_tie,'lineage_change':lin,
 'generator_tie_field': 'ties_and_duplicates' in generator,'manifest_max_gap':gap,'summary_max_gap':tsum.get('max_gap_policy'),
 'split_assignment':manifest.get('split_design_pending',{}).get('actual_assignment'),'B_C_computed':[tsum.get('B_computed'),tsum.get('C_computed')],
 'reference_overlap':ref,'floor_semantics':tsum.get('score_floor_semantics'),'readiness_readable_utf8':readable,
 'readiness_sha256':hfile(TIMING/'readiness_report.md')[0],'readiness_tail':readiness.splitlines()[-6:],
 'summary_output_hash_checks':round_hash_checks,'lineage_current_code_hash_matches':lineage.get('round_copy',{}).get('sha256')==code_sha},
 None if contract_ok else '현재 문서/계약/해시 정합성 실패')
# W0 retained full-stream comparison evidence and current output hashes; large source inputs are not rehashed.
w0=readj(W0/'summary.json');w0man=readj(W0/'manifest.json');w0log=readj(W0/'metadata_correction_log.json')
with (W0/'csv_identity.csv').open('r',encoding='utf-8-sig',newline='') as f: csvrows=list(csv.DictReader(f))
boolv=lambda x:str(x).strip().lower()=='true'
new_total=sum(int(x['new_stream_bytes']) for x in csvrows);old_total=sum(int(x['old_stream_bytes']) for x in csvrows)
csv_ok=len(csvrows)==12 and all(boolv(x['content_identical']) and boolv(x['sha256_equal']) and int(x['new_stream_bytes'])==int(x['old_stream_bytes']) and boolv(x['zip_crc_checked_to_eof']) for x in csvrows) and new_total==old_total==w0.get('csv_summary',{}).get('total_new_bytes')==w0.get('csv_summary',{}).get('total_old_bytes')==13349258148
runner=(W0/'run_comparison.py').read_text(encoding='utf-8-sig')
stream_logic=all(s in runner for s in ('def sha_stream','zf.read(4*1024*1024)','of.read(4*1024*1024)','zip_crc_checked_to_eof','archive_sha256_before','archive_sha256_after'))
artifact_checks=[]
for a in w0man.get('artifacts',[]):
 p=REPO/Path(a['path'])
 try:d,n=hfile(p);artifact_checks.append({'path':a['path'],'match':d==a['sha256'] and n==a['bytes'],'bytes':n,'sha256':d})
 except FileNotFoundError:artifact_checks.append({'path':a['path'],'match':False,'missing':True})
artifact_ok=bool(artifact_checks) and all(x['match'] for x in artifact_checks)
runexit=int((W0/'exit_status.txt').read_text(encoding='utf-8-sig').strip());corr=int((W0/'correction_exit_status.txt').read_text(encoding='utf-8-sig').strip());sync=int((W0/'correction_sync_exit_status.txt').read_text(encoding='utf-8-sig').strip());finalizer=int((W0/'finalizer_exit_status.txt').read_text(encoding='utf-8-sig').strip())
w0_start=readj(ROUND/'integration/runtime_receipts/W0_start.json')['result'];w0proc=readj(ROUND/'integration/runtime_receipts/W0_process.json')
process_ok=w0.get('actual_exit_code')==runexit==0 and corr==sync==finalizer==0 and w0proc.get('exit_code')==0 and w0.get('runner_code_sha256')==hfile(W0/'run_comparison.py')[0] and w0.get('finalizer_code_sha256')==hfile(W0/'finalize_outputs.py')[0] and w0_start.get('model')=='gpt-6-luna' and w0_start.get('effort')=='xhigh'
add('w0_csv_streaming_results_and_artifact_hashes','pass' if csv_ok and stream_logic and artifact_ok and process_ok else 'fail',{
 'csv_pairs':len(csvrows),'identical_pairs':sum(boolv(x['content_identical']) for x in csvrows),'new_bytes':new_total,'old_bytes':old_total,
 'eof_crc_rows':sum(boolv(x['zip_crc_checked_to_eof']) for x in csvrows),'streaming_and_EOF_logic_inspected':stream_logic,
 'full_source_rehash_performed_by_this_audit':False,'W0_recorded_archive_SHA256':{'before':w0.get('archive_sha256_before'),'after':w0.get('archive_sha256_after'),'bytes':w0.get('archive_hash_bytes_before'),'unchanged':w0.get('archive_unchanged_by_hash')},
 'actual_exit_codes':{'main':runexit,'correction':corr,'sync':sync,'finalizer':finalizer,'runtime_receipt':w0proc.get('exit_code')},
 'W0_launch_model_effort':{'model':w0_start.get('model'),'effort':w0_start.get('effort'),'provider_internal_runtime':'unknown'},
 'W0_artifact_manifest_count':len(artifact_checks),'all_hashes_match':artifact_ok,'hash_mismatches':[x for x in artifact_checks if not x['match']]},
 None if csv_ok and stream_logic and artifact_ok and process_ok else 'W0 요약/실행코드/출력 해시 정합성 실패')

# Confirm old metadata false evidence remains verbatim and corrected typed-field comparisons are coherent.
oldsummary=readj(W0/'pre_metadata_fix/summary.json');rawvals=w0log.get('raw_legacy_values',[]);corrected=w0log.get('corrected_metadata_records',[])
false_rows=[x for x in corrected if x.get('legacy_false_was_type_mismatch') is True and x.get('legacy_raw_fields',{}).get('metadata_unchanged_through_posthash') is False]
typed_ok=len(corrected)==14 and all(x.get('comparison_hash_matches_post') is True and x.get('metadata_unchanged_through_posthash') is True and x.get('metadata_fields_compared')==['bytes','mtime_ns'] and x.get('metadata_before_comparison',{}).get('bytes')==x.get('metadata_after_comparison',{}).get('bytes')==x.get('metadata_before_posthash',{}).get('bytes')==x.get('metadata_after_posthash',{}).get('bytes') and x.get('metadata_before_comparison',{}).get('mtime_ns')==x.get('metadata_after_comparison',{}).get('mtime_ns')==x.get('metadata_before_posthash',{}).get('mtime_ns')==x.get('metadata_after_posthash',{}).get('mtime_ns') for x in corrected)
raw_preserved=len(rawvals)==14 and len(false_rows)==12 and all(isinstance(x.get('legacy_raw_fields',{}).get('metadata_before_comparison'),str) and isinstance(x.get('legacy_raw_fields',{}).get('metadata_before_posthash'),dict) and x.get('legacy_raw_fields',{}).get('metadata_unchanged_through_posthash') is False for x in corrected[:12])
metadata_summary_ok=w0.get('metadata_correction',{}).get('all_14_metadata_records_unchanged') is True and w0.get('metadata_correction',{}).get('all_14_content_hashes_match') is True and len(w0.get('old_input_posthash_verification',[]))==14 and all(x.get('comparison_sha256')==x.get('post_sha256') and x.get('comparison_hash_matches_post') is True and x.get('metadata_unchanged_through_posthash') is True for x in w0['old_input_posthash_verification'])
preserved=[]
for name,v in w0log.get('preserved_files',{}).items():
 p=REPO/Path(v['preserved_copy'])
 try:d,n=hfile(p);preserved.append({'file':name,'match':d==v['sha256']==v['preserved_sha256'] and n==v['bytes'],'sha256':d,'bytes':n})
 except FileNotFoundError:preserved.append({'file':name,'match':False,'missing':True})
preserved_ok=all(x['match'] for x in preserved) and hfile(W0/'pre_metadata_fix/summary.json')[0]==w0log.get('original_summary_sha256')
meta_ok=typed_ok and raw_preserved and metadata_summary_ok and preserved_ok
add('w0_metadata_correction_evidence','pass' if meta_ok else 'fail',{
 'preserved_original_false_type_mismatch_rows':len(false_rows),'expected_csv_rows':12,'typed_corrected_records':len(corrected),'typed_metadata_14_of_14':typed_ok,
 'recorded_comparison_and_posthashes_equal_14_of_14':metadata_summary_ok,'pre_correction_summary_status':oldsummary.get('status'),
 'pre_correction_summary_copy_hash_matches_log':hfile(W0/'pre_metadata_fix/summary.json')[0]==w0log.get('original_summary_sha256'),
 'preserved_files':preserved,'large_input_rehash_performed_during_correction':w0.get('metadata_correction',{}).get('rehashed_large_inputs')},
 None if meta_ok else '원 false/raw 증거, 정수 metadata 비교 또는 14개 기록 중 불일치')

# Reuse direct W3 cache/submission key comparisons; do not open the pickle or parquet here.
prior=readj(ROUND/'audit/v2_id_recheck_001/summary.json');prior_exit=readj(ROUND/'audit/v2_id_recheck_001/process_result.json').get('exit_code')
sets={x['comparison']:x for x in prior.get('set_comparisons',[])}
prior_ok=prior_exit==0 and sets.get('oldB_vs_newB',{}).get('intersection_count')==0 and sets.get('newB_vs_score_cache_keys',{}).get('intersection_count')==0 and sets.get('oldB_vs_score_cache_keys',{}).get('intersection_count')==100 and sets.get('oldA_vs_newB',{}).get('intersection_count')==13
wids=w0.get('test_id_sequence_summary',{})
w0ids_ok=wids.get('테스트B',{}).get('intersection_count')==0 and wids.get('테스트A',{}).get('intersection_count')==2 and w0.get('legacy100_new_target_use',{}).get('scores_usable_for_new_target') is False and w0.get('legacy100_new_target_use',{}).get('predictions_usable_for_new_target') is False and w0.get('legacy100_new_target_use',{}).get('new_actual_predictions_created') is False
add('prior_id_recheck_reused_without_cache_reload','pass' if prior_ok and w0ids_ok else 'fail',{
 'prior_audit_exit':prior_exit,'prior_intersections':{k:v.get('intersection_count') for k,v in sets.items()},
 'W0_summary_intersections':{'oldB_newB':wids.get('테스트B',{}).get('intersection_count'),'oldA_newA':wids.get('테스트A',{}).get('intersection_count')},
 'legacy_predictions_transfer_allowed':False,'pickle_or_parquet_reopened':False},None if prior_ok and w0ids_ok else '기존 독립 ID 결과와 W0 표기가 다름')
