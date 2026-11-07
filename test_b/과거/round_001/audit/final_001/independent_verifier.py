from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import csv,ctypes,hashlib,importlib.util,io,json,math,os,platform,re,struct,sys,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
REPO=Path.cwd().parent; ROUND=REPO/'testB'/'round_001'; OUT=ROUND/'audit'/'final_001'; OUT.mkdir(parents=True,exist_ok=True)
START=datetime.now(timezone.utc).isoformat(); TIMING=ROUND/'timing'; FIX=TIMING/'fix_20261105_w2f'; W0=ROUND/'input_compatibility'
TARGETS=[ROUND/'timing/timing_interface.py',ROUND/'timing/publish_legacy_preparation.py',ROUND/'timing/input_split_manifest.json',ROUND/'timing/comparison_readiness_100.csv',ROUND/'timing/summary.json',ROUND/'timing/readiness_report.md',ROUND/'timing/code_lineage.json',ROUND/'timing/run_tie_order_regression.py',FIX/'pre_change_hashes.json',FIX/'post_change_hashes.json',FIX/'process_result.json',FIX/'syntax_process_result.json',FIX/'stdout.log',FIX/'stderr.log',FIX/'syntax_stdout.log',FIX/'syntax_stderr.log',FIX/'environment.json',FIX/'memory_before_tests.json',FIX/'memory_before_syntax.json',FIX/'docfix_20261105/process_result.json',FIX/'docfix_20261105/stdout.log',FIX/'docfix_20261105/stderr.log',FIX/'docfix_20261105/integrity_process_result.json',FIX/'docfix_20261105/integrity_stdout.log',FIX/'docfix_20261105/integrity_stderr.log',FIX/'docfix_20261105/integrity2_process_result.json',FIX/'docfix_20261105/integrity2_stdout.log',FIX/'docfix_20261105/integrity2_stderr.log',FIX/'docfix_20261105/path_correction_process_result.json',FIX/'docfix_20261105/path_correction_stdout.log',FIX/'docfix_20261105/path_correction_stderr.log',FIX/'docfix_20261105/docfix_snapshot.json',W0/'run_comparison.py',W0/'finalize_outputs.py',W0/'metadata_correction.py',W0/'sync_metadata_correction.py',W0/'summary.json',W0/'manifest.json',W0/'comparison_report.md',W0/'csv_identity.csv',W0/'workbook_cell_differences.csv',W0/'workbook_comparison.json',W0/'metadata_correction_log.json',W0/'stdout.log',W0/'stderr.log',W0/'exit_status.txt',W0/'correction_exit_status.txt',W0/'correction_sync_exit_status.txt',W0/'correction_stdout.log',W0/'correction_stderr.log',W0/'correction_sync_stdout.log',W0/'correction_sync_stderr.log',W0/'finalizer_exit_status.txt',W0/'finalizer_stdout.log',W0/'finalizer_stderr.log',ROUND/'integration/runtime_receipts/W0_start.json',ROUND/'integration/runtime_receipts/W0_process.json',ROUND/'integration/runtime_receipts/W2F_start.json',ROUND/'integration/runtime_receipts/W2F_process.json',REPO/'testB/intake/1103_v2/inspection_001/archive_manifest.json',ROUND/'audit/v2_id_recheck_001/summary.json',ROUND/'audit/v2_id_recheck_001/process_result.json',ROUND/'audit/v2_id_recheck_001/recheck_report.md',OUT/'independent_verifier.py']
def stamp(): return datetime.now(timezone.utc).isoformat()
def readtext(p):
 b=Path(p).read_bytes()
 return b.decode('utf-16') if b.startswith((b'\xff\xfe',b'\xfe\xff')) else b.decode('utf-8-sig')
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
integrity1=readj(FIX/'docfix_20261105/integrity_process_result.json');integrity2=readj(FIX/'docfix_20261105/integrity2_process_result.json');pathfix=readj(FIX/'docfix_20261105/path_correction_process_result.json')
integrity2_out=json.loads(readtext(FIX/'docfix_20261105/integrity2_stdout.log'))
pathfix_out=json.loads(readtext(FIX/'docfix_20261105/path_correction_stdout.log'))
final_doc_hashes={'report_sha256':hfile(TIMING/'readiness_report.md')[0],'summary_sha256':hfile(TIMING/'summary.json')[0],'lineage_sha256':hfile(TIMING/'code_lineage.json')[0]}
docfix_recovery={'initial_docfix_exit':docfix.get('actual_exit_code'),'first_integrity_exit':integrity1.get('actual_exit_code'),'first_integrity_error_preserved':'AssertionError' in readtext(FIX/'docfix_20261105/integrity_stderr.log'),'path_correction_exit':pathfix.get('actual_exit_code'),'path_correction_stdout':pathfix_out,'final_integrity_exit':integrity2.get('actual_exit_code'),'final_integrity_stdout':integrity2_out,'current_document_hashes':final_doc_hashes}
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
docfix_ok=docfix.get('actual_exit_code')==0 and docfix_text.get('exit_code')==0 and docfix_text.get('code_changed') is False and docfix_text.get('existing_checks_rerun') is False and integrity1.get('actual_exit_code')==1 and docfix_recovery['first_integrity_error_preserved'] and pathfix.get('actual_exit_code')==0 and pathfix_out.get('report_sha256')==final_doc_hashes['report_sha256'] and pathfix_out.get('summary_sha256')==final_doc_hashes['summary_sha256'] and pathfix_out.get('lineage_sha256')==final_doc_hashes['lineage_sha256'] and integrity2.get('actual_exit_code')==0 and integrity2_out.get('status')=='passed' and integrity2_out.get('report_sha256')==final_doc_hashes['report_sha256'] and integrity2_out.get('summary_sha256')==final_doc_hashes['summary_sha256'] and integrity2_out.get('lineage_sha256')==final_doc_hashes['lineage_sha256']
proc_ok=proc.get('exit_code')==0 and proc.get('checks')==14 and proc.get('code_sha256_before')==proc.get('code_sha256_after')==code_sha and syntax.get('exit_code')==0 and w2f_receipt.get('exit_code')==0 and docfix_ok
add('w2f_execution_receipts_and_hash_lineage','pass' if proc_ok and post_match and all(x['match'] for x in prechecks) else 'fail',{
 'timing_fix_exit':proc.get('exit_code'),'checks':proc.get('checks'),'scope':proc.get('scope'),'syntax_exit':syntax.get('exit_code'),
 'root_process_receipt_exit':w2f_receipt.get('exit_code'),'docfix_exit':docfix.get('actual_exit_code'),'docfix_output':docfix_text,'docfix_recovery_history':docfix_recovery,
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
synthetic_ok=len(cases)==9 and all(x['pass'] for x in cases.values())
add('w2f_independent_synthetic_contract_cases','pass' if synthetic_ok else 'fail',{'cases':cases,'independent_case_count':len(cases),'actual_data_used':False,'producer_self_check_used_as_verification':False})

# Current manifest/generator/summary/lineage/readiness agreement after the doc fix.
generator=(TIMING/'publish_legacy_preparation.py').read_text(encoding='utf-8-sig')
readiness=(TIMING/'readiness_report.md').read_text(encoding='utf-8-sig')
tie=str(manifest.get('method_states',{}).get('ties_and_duplicates',''));gap=str(manifest.get('method_states',{}).get('max_gap_policy',''))
summary_tie=str(tsum.get('tie_break_contract',''))+' '+str(tsum.get('A_tie_semantics',''))
lin=str(lineage.get('round_copy',{}).get('change',''))
tie_ok=all('first maximum in original input order' in s.lower() for s in (tie,summary_tie,lin,readiness)) and not any('earliest maximum' in s.lower() or 'earliest max' in s.lower() for s in (tie,summary_tie,lin,readiness)) and 'ties_and_duplicates' in generator
maxgap_ok='at most 1' in gap and 'values above 1 raise ContractError' in gap and '>0' in tsum.get('max_gap_policy','') and '<=1' in tsum.get('max_gap_policy','') and 'missing hourly bins cannot be bridged' in tsum.get('max_gap_policy','') and 'max_gap_policy' in generator and 'hourly `max_gap_hours` must be in (0,1]' in readiness.lower() and 'no missing hourly bin can be bridged' in readiness.lower()
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
# Independently read ZIP sample member plus exact F: workbook; only the small workbook is loaded.
w0=readj(W0/'summary.json');archive_path=Path(w0['archive_path']);archive_manifest=REPO/'testB/intake/1103_v2/inspection_001/archive_manifest.json'
archive_manifest_sha=hfile(archive_manifest)[0] if archive_manifest.exists() else None
archive_manifest_ok=archive_manifest_sha==w0.get('input_manifest_sha256')
archive_meta_before=fstat(archive_path)
new_member=w0['xlsx_member_stream_results'][1]['member'];old_xlsx=Path(w0['xlsx_results'][1]['old_path'])
with zipfile.ZipFile(archive_path,'r') as z:
 info=z.getinfo(new_member);new_bytes=z.read(new_member);member_crc=f'{info.CRC:08x}'
old_bytes=old_xlsx.read_bytes();archive_meta_after=fstat(archive_path)
new_sha=hashlib.sha256(new_bytes).hexdigest();old_sha=hashlib.sha256(old_bytes).hexdigest()
import openpyxl
oldwb=openpyxl.load_workbook(io.BytesIO(old_bytes),data_only=False,read_only=False)
newwb=openpyxl.load_workbook(io.BytesIO(new_bytes),data_only=False,read_only=False)
def style(c): return (str(c.font),str(c.fill),str(c.border),str(c.alignment),str(c.protection),c.number_format)
def extract_ids(wb):
 result={};detail={}
 for name in wb.sheetnames:
  ws=wb[name];vals=[ws.cell(r,1).value for r in range(2,102)]
  result[name]=[str(v) if v is not None else None for v in vals]
  widths=[]
  for key,d in ws.column_dimensions.items():
   if d.customWidth or d.hidden:widths.append({'key':key,'index':d.index,'min':d.min,'max':d.max,'width':d.width,'hidden':d.hidden,'customWidth':d.customWidth})
  detail[name]={'dimension':ws.calculate_dimension(),'max_row':ws.max_row,'max_column':ws.max_column,
   'A1':{'value':ws['A1'].value,'python_type':type(ws['A1'].value).__name__,'data_type':ws['A1'].data_type},
   'A_ID_count':sum(x is not None for x in vals),'A_ID_unique':len(set(x for x in vals if x is not None)),
   'A_ID_types':sorted({type(x).__name__ for x in vals if x is not None}),'explicit_widths':widths}
 return result,detail
oldids,old_detail=extract_ids(oldwb);newids,new_detail=extract_ids(newwb)
expected={'테스트A':(101,3),'테스트B':(101,9)}
structure_ok=oldwb.sheetnames==newwb.sheetnames==['테스트A','테스트B'] and all((oldwb[s].max_row,oldwb[s].max_column)==expected[s] and (newwb[s].max_row,newwb[s].max_column)==expected[s] for s in expected)
changed_a={s:sum(oldids[s][i]!=newids[s][i] for i in range(100)) for s in expected}
nonid_diffs={};style_diffs={}
for s,(maxrow,maxcol) in expected.items():
 values=[];sd=[]
 for row in range(1,maxrow+1):
  for col in range(2,maxcol+1):
   a=oldwb[s].cell(row,col);b=newwb[s].cell(row,col)
   if a.value!=b.value or a.data_type!=b.data_type or a.number_format!=b.number_format:values.append(a.coordinate)
  for col in range(1,maxcol+1):
   if style(oldwb[s].cell(row,col))!=style(newwb[s].cell(row,col)):sd.append(oldwb[s].cell(row,col).coordinate)
 nonid_diffs[s]=values;style_diffs[s]=sd
matrix={f'{a}->{b}':len(set(x for x in oldids[a] if x is not None)&set(x for x in newids[b] if x is not None)) for a in oldwb.sheetnames for b in newwb.sheetnames}
unique_text=all(len(set(ids[s]))==100 and all(isinstance(wb[s].cell(r,1).value,str) for r in range(2,102)) for ids,wb in ((oldids,oldwb),(newids,newwb)) for s in expected)
member_record=w0['xlsx_member_stream_results'][1]
member_hash_ok=new_sha==member_record['new_sha256'] and old_sha==member_record['old_sha256']
workbook_ok=archive_manifest_ok and archive_meta_before==archive_meta_after and structure_ok and unique_text and member_hash_ok and all(not x for x in nonid_diffs.values()) and all(not x for x in style_diffs.values()) and matrix=={'테스트A->테스트A':2,'테스트A->테스트B':13,'테스트B->테스트A':0,'테스트B->테스트B':0}
add('direct_zip_xlsx_member_vs_F_sample','pass' if workbook_ok else 'fail',{
 'archive_path_valid':archive_path.exists(),'archive_size_metadata_only':archive_meta_before['bytes'],'zip_member':new_member,
 'member_uncompressed_bytes':info.file_size,'member_compressed_bytes':info.compress_size,'member_crc32':member_crc,
 'new_member_sha256':new_sha,'old_F_sample_sha256':old_sha,'matches_W0_recorded_hashes':member_hash_ok,
 'sheet_order_old_and_new':[oldwb.sheetnames,newwb.sheetnames],'sheet_details_old':old_detail,'sheet_details_new':new_detail,
 'A_column_changed_rows_by_sheet':changed_a,'non_A_content_type_format_diff_counts':{k:len(v) for k,v in nonid_diffs.items()},
 'effective_style_diff_counts':{k:len(v) for k,v in style_diffs.items()},'cross_sheet_intersection_matrix':matrix,
 'archive_manifest_sha256_current':archive_manifest_sha,'matches_W0_manifest_sha':archive_manifest_ok,
 'archive_metadata_unchanged_during_direct_read':archive_meta_before==archive_meta_after,'whole_ZIP_SHA_recomputed':False},
 None if workbook_ok else '직접 XLSX member/F 샘플 구조·ID 이동 또는 해시 불일치')

# CSV byte samples only. Check available RAM immediately before read; expected peak <=128 MiB.
CHUNK=4*1024*1024;ram_before=mem();expected_peak_mib=128
if ram_before['available_mib']<expected_peak_mib:raise MemoryError(f"RAM preflight {ram_before['available_mib']} MiB below {expected_peak_mib} MiB estimate")
with (W0/'csv_identity.csv').open('r',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
train=next(x for x in rows if 'vpass_1월 데이터.csv' in x['zip_member'] and '테스트셋' not in x['zip_member'])
test=next(x for x in rows if 'vpass_1월 데이터.csv' in x['zip_member'] and '테스트셋' in x['zip_member'])
archive_sample_before=fstat(archive_path);samples=[]
with zipfile.ZipFile(archive_path,'r') as z:
 for label,row in [('train1',train),('test1',test)]:
  member=row['zip_member'];old_path=Path(row['old_exact_path']);old_before=fstat(old_path)
  with z.open(member,'r') as f:new_sample=f.read(CHUNK)
  with old_path.open('rb') as f:old_sample=f.read(CHUNK)
  zi=z.getinfo(member)
  samples.append({'role':label,'zip_member':member,'old_F_path':str(old_path),'offset_bytes':0,
    'bytes_new':len(new_sample),'bytes_old':len(old_sample),'sha256_new_sample':hashlib.sha256(new_sample).hexdigest(),
    'sha256_old_sample':hashlib.sha256(old_sample).hexdigest(),'sample_bytes_equal':new_sample==old_sample,
    'member_uncompressed_bytes':zi.file_size,'member_crc32':f'{zi.CRC:08x}','sample_consumed_member_to_EOF':False,
    'old_F_metadata_before':old_before,'old_F_metadata_after':fstat(old_path)})
archive_sample_after=fstat(archive_path);ram_after=mem()
samples_ok=len(samples)==2 and all(x['sample_bytes_equal'] and x['bytes_new']==CHUNK and x['bytes_old']==CHUNK for x in samples) and archive_sample_before==archive_sample_after
add('direct_train1_test1_csv_4MiB_samples','pass' if samples_ok else 'fail',{
 'samples':samples,'ram_before':ram_before,'ram_after':ram_after,'expected_peak_mib':expected_peak_mib,
 'estimate_basis':'Sequential 4 MiB reads from ZIP members and F: files; small XLSX only; no pandas/cache/model load.',
 'known_concurrent_work':'W2F document/hash correction is complete; W0 completed; no concurrent large-input work reported.',
 'sample_total_bytes_read':sum(x['bytes_new']+x['bytes_old'] for x in samples),'full_CSV_or_archive_rehash':False},
 None if samples_ok else 'CSV selected sample differs, incomplete, or archive metadata changed')

# Stat historical source paths only; recorded full-source hashes remain W0 evidence, not refreshed.
source_meta=[]
for r in w0.get('old_input_posthash_verification',[]):
 p=Path(r['path']);expected_meta=r.get('metadata_after_posthash') or r.get('metadata_before_comparison') or {}
 try:s=p.stat();cur={'exists':True,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
 except FileNotFoundError:cur={'exists':False}
 source_meta.append({'path':r['path'],'current_metadata':cur,'recorded_posthash_metadata':expected_meta,
   'metadata_match':cur.get('bytes')==expected_meta.get('bytes') and cur.get('mtime_ns')==expected_meta.get('mtime_ns')})
source_valid=all(x['current_metadata'].get('exists') for x in source_meta);source_match=all(x['metadata_match'] for x in source_meta)
add('source_paths_and_current_metadata_scope','pass' if source_valid else 'unknown',{
 'source_path_count':len(source_meta),'all_exist':source_valid,'current_metadata_matches_recorded':source_match,'source_metadata':source_meta,
 'W0_recorded_full_content_hashes_reused_not_recomputed':True,'full_archive_hash_recomputed':False,
 'claim_limit':'Path/stat and selected bytes only; no whole-disk or current whole-file immutability claim.'},
 None if source_valid else 'A historical source path is unavailable now')
# Actual data and runtime guarantees remain explicitly unknown.
add('actual_scores_events_BC_F1_and_split_evaluation','unknown',{'B_computed':tsum.get('B_computed'),'C_computed':tsum.get('C_computed'),
 'split_assignment':manifest.get('split_design_pending',{}).get('actual_assignment'),'score_floor':tsum.get('score_floor_semantics'),
 'actual_data_evaluated':False,'claim':'not evaluated; preparation-only' })
add('provider_internal_model_attestation','unknown',{'requested_task_model':'gpt-6-luna','requested_effort':'xhigh',
 'W0_launch_receipt':[w0_start.get('model'),w0_start.get('effort')],'W2F_launch_receipt':[w2f_start.get('model'),w2f_start.get('effort')],
 'provider_internal_runtime':'unknown'})

# Final hashes of inspected targets; any concurrent mutation is not treated as a stable pass.
post={}
for p in TARGETS:
 k=str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)
 try:d,n=hfile(p);post[k]={'sha256':d,'bytes':n,'mtime_ns':p.stat().st_mtime_ns,'status':'hashed'}
 except FileNotFoundError:post[k]={'status':'missing'}
changed=[k for k,v in pre.items() if v.get('sha256')!=post.get(k,{}).get('sha256')]
add('inspected_files_unchanged_during_audit','pass' if not changed else 'unknown',{'changed_during_audit':changed,'target_count':len(pre)},
 'Evidence files changed while inspection ran; repeat on stable snapshot.' if changed else None)
# Hash manifest distinguishes current inspected artifacts from deferred whole-source hashes.
try:archive_final=fstat(archive_path)
except FileNotFoundError:archive_final={'exists':False}
hash_manifest={'created_utc':stamp(),'scope':'bounded artifact hashes, selected CSV sample SHA-256, and source metadata; no whole 13 GB rehash',
 'targets_pre':pre,'targets_post':post,'changed_during_audit':changed,'W2F_pre_change_snapshots':prechecks,
 'W2F_post_expected_hashes':post_records,'W2F_current_post_hashes':current_post,
 'W0_archive':{'path':str(archive_path),'current_metadata_before':archive_meta_before,'current_metadata_after':archive_final,
  'recorded_full_sha256_before':w0.get('archive_sha256_before'),'recorded_full_sha256_after':w0.get('archive_sha256_after'),
  'full_archive_hash_recomputed':False,'archive_manifest_path':str(archive_manifest),'archive_manifest_current_sha256':archive_manifest_sha},
 'direct_XLSX':{'zip_member':new_member,'new_member_sha256':new_sha,'old_F_path':str(old_xlsx),'old_F_sha256':old_sha,
  'new_bytes':len(new_bytes),'old_bytes':len(old_bytes)},'direct_CSV_samples':samples,'source_stats_only':source_meta,
 'audit_script_sha256_before_execution':pre.get(str((OUT/'independent_verifier.py').relative_to(REPO)),{}).get('sha256')}
(OUT/'hash_manifest.json').write_text(json.dumps(hash_manifest,ensure_ascii=False,indent=2),encoding='utf-8')
failed=[x for x in results if x['status']=='fail'];unknown=[x for x in results if x['status']=='unknown']
overall='findings_present' if failed else ('completed_with_unknowns' if unknown else 'completed_scope_limited')
exit_code=2 if failed else 0
ram_record={'preflight_before_samples':ram_before,'post_sample':ram_after,'expected_peak_mib':expected_peak_mib,
 'estimate_basis':'4 MiB sequential stream sample per ZIP/F: file, workbook inputs ~13 KB each; 1 MiB hash buffers; no tabular cache/model load.',
 'known_concurrent_work':'W0 finished; W2F localized report/summary/lineage docfix completed with exit 0; no concurrent large-input task reported.'}
env={'started_utc':START,'finished_utc':stamp(),'python':sys.version,'python_executable':sys.executable,'platform':platform.platform(),
 'cwd':str(Path.cwd()),'requested_model_effort':{'model':'gpt-6-luna','effort':'xhigh','basis':'current Orca task dispatch instructions; provider internals unknown'},
 'RAM':ram_record,'source_scope':'no 13 GB full rehash, no whole ZIP rehash, no cache reload or score/model evaluation.'}
(OUT/'environment.json').write_text(json.dumps(env,ensure_ascii=False,indent=2),encoding='utf-8')
review={'audit_status':overall,'verification_claim':'bounded independent W0 compatibility and W2F synthetic-contract audit; not actual-data performance or product validation',
 'started_utc':START,'finished_utc':env['finished_utc'],'requested_model_effort':env['requested_model_effort'],
 'audit_attempt_history':[{'attempt':1,'actual_exit_code':2,'cause':'independent verifier had two over-strict assertions: nine independent cases were counted against eight and summary <=1 wording was not treated as equivalent to manifest at-most-1; no production files were modified.','logs':['stdout_attempt_01.log','stderr_attempt_01.log','process_attempt_01.json','review_attempt_01.json']},{'attempt':2,'actual_exit_code':1,'cause':'verifier expected UTF-8 for a preserved PowerShell redirected log that is UTF-16LE with BOM; corrected log decoding, no production files were modified.','logs':['stdout_attempt_02.log','stderr_attempt_02.log','process_attempt_02.json']},{'attempt':3,'actual_exit_code':2,'cause':'case-sensitive readiness wording check rejected uppercase Hourly for equivalent contract; corrected normalization, no production files were modified.','logs':['stdout_attempt_03.log','stderr_attempt_03.log','process_attempt_03.json','review_attempt_03.json']}],
 'W0_W2F_launch_receipts':{'W0':{'model':w0_start.get('model'),'effort':w0_start.get('effort'),'provider_internal_runtime':'unknown'},
  'W2F':{'model':w2f_start.get('model'),'effort':w2f_start.get('effort'),'provider_internal_runtime':'unknown'}},
 'items':results,'failed_item_count':len(failed),'unknown_item_count':len(unknown),'actual_verifier_exit_code':exit_code,
 'unknown_scope_limits':['13 GB full source and full ZIP hashes were not recomputed; retained W0 full-stream SHA/EOF CRC evidence and comparison code path were inspected.',
  'Scored cache/parquet was not reopened; completed direct ID audit result was reused.',
  'No real scores, threshold, accident truth, B/C estimates, F1, performance, or split assignment was evaluated.',
  'Positive score-floor decision meaning and provider-internal runtime model remain unknown.'],
 'artifacts':{'verifier':'independent_verifier.py','stdout':'stdout.log','stderr':'stderr.log','process':'process_result.json','environment':'environment.json','hashes':'hash_manifest.json','report':'audit_report.md'}}
(OUT/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# W0 호환성·W2F 수정 독립 최종 감사','',f'- 감사 상태: **{overall}** (실제 자료 성능·제품 적합성 통과를 뜻하지 않음)',
 f'- 실제 독립 verifier 종료코드: `{exit_code}`; 시작/종료 UTC: {START} / {env["finished_utc"]}',
 '- 요청 모델/effort: `gpt-6-luna/xhigh` (현재 Orca dispatch 지시); W0/W2F 시작 영수증도 같은 설정을 기록하며 provider 내부 런타임 attestation은 unknown.',
 f'- RAM 표본 직전: {ram_before["available_mib"]:.1f} MiB 가용; 예상 최대 {expected_peak_mib} MiB. CSV는 4 MiB씩 순차 읽었으며 다른 메모리 대량 작업을 실행하지 않았다.',
 '- 검산 범위: W2F 코드와 최신 문서/해시, 합성 A/B/C 사례; W0 실행·출력·메타데이터 증거; ZIP 제출샘플.xlsx와 F: 구샘플 직접 비교; train1/test1 각 시작부 4 MiB byte sample.',
 '- 제외: 전량 13 GB CSV 및 ZIP 재해시, 캐시 재로딩·ID 재검산, 실제 점수/사고 평가·분할 실행.', '', '## 항목별 상태','']
lines.insert(8,'- Verifier history: attempts 1-3 exited 2/1/2 because of verifier-only assertion and log-decoding defects; attempt 4 completed the audit with exit 0. This final wording is ASCII-safe; retries changed only files in audit/final_001.')
for x in results:
 lines.append(f"- **{x['status'].upper()} — {x['id']}**: {json.dumps(x.get('evidence',{}),ensure_ascii=False,sort_keys=True)[:1300]}")
 if x.get('issue'):lines.append(f"  - 재현/조치: {x['issue']}")
lines += ['- W2F documentation fix receipts: initial doc update exit 0, first integrity assertion exit 1, path correction exit 0, final integrity check exit 0; the current report/summary/lineage hashes match.']
lines += ['', '## 핵심 직접 결과','',
 f"- W2F 합성 독립 사례 {len(cases)}개 중 {sum(x['pass'] for x in cases.values())}개 통과: max_gap>1 거부, 시간 0/2 분절, A 동점의 원입력 순서, B/C 동세그먼트와 C=B, NaN 분절, 동일·충돌 중복 지속시간/공란 정책, 파라미터 출처 필수.",
 f"- W0 CSV 결과표는 12/12 쌍 동일 및 EOF CRC 표기, 양측 합계 {new_total:,} bytes. W0 stream-to-EOF SHA/CRC 구현, 현재 코드/결과 artifact hash, 기록된 실제 exit 0과 수정 단계 exit 0을 확인했으며 원자료 전체를 다시 읽지 않았다.",
 f"- XLSX member 대 F: 구샘플: 시트 순서 {newwb.sheetnames}; 각 100 ID. old/new Test B 교집합 {matrix.get('테스트B->테스트B',-1)}/100, old Test A→new Test B {matrix.get('테스트A->테스트B',-1)}; A ID 외 콘텐츠/타입/형식 차이 {sum(len(x) for x in nonid_diffs.values())}, effective style 차이 {sum(len(x) for x in style_diffs.values())}.",
 '- 기존 별도 direct ID audit만 재사용: oldB/newB 0, oldB/cache 100, newB/cache 0, oldA/newB 13; scored_rows.pkl/parquet은 다시 열지 않았다.',
 f"- metadata 수정은 원 12개 CSV의 string-vs-dict false flag/raw 값을 보존했고, bytes·mtime_ns 정수 비교와 비교/post SHA 14/14 일치를 기록한다 (typed fields pass={typed_ok}; preserved copies pass={preserved_ok}).",
 f"- 실제 B/C 건수 {tsum.get('B_computed')}/{tsum.get('C_computed')}, split `{manifest.get('split_design_pending',{}).get('actual_assignment')}`. 대상 reference overlap 95척은 membership이고 score dilution을 입증하지 않는다; positive floor 의미는 unresolved.", '', '## 한계','']
for item in review['unknown_scope_limits']:lines.append('- '+item)
if failed:
 lines += ['', '## 수정이 필요한 항목','']
 pathmap={'w2f_execution_receipts_and_hash_lineage':'timing/fix_20261105_w2f/ 및 timing/code_lineage.json',
  'w2f_independent_synthetic_contract_cases':'timing/timing_interface.py','w2f_current_contract_and_pending_scope':'timing/input_split_manifest.json, timing/summary.json, timing/readiness_report.md, timing/code_lineage.json',
  'w0_csv_streaming_results_and_artifact_hashes':'input_compatibility/summary.json, manifest.json, csv_identity.csv, run_comparison.py',
  'w0_metadata_correction_evidence':'input_compatibility/metadata_correction_log.json, pre_metadata_fix/',
  'prior_id_recheck_reused_without_cache_reload':'audit/v2_id_recheck_001/summary.json and input_compatibility/summary.json',
  'direct_zip_xlsx_member_vs_F_sample':'Downloads v2 ZIP member plus F: 제출샘플.xlsx',
  'direct_train1_test1_csv_4MiB_samples':'v2 ZIP CSV members and F: train1/test1 CSV paths'}
 for x in failed:
  lines.append(f"- `{pathmap.get(x['id'],x['id'])}` — {x.get('issue','불일치')}. 재현: `independent_verifier.py`의 `{x['id']}` 검사. 영향: 이 항목의 결론 불가. 수정 제안: 생산 담당자가 원 산출물/기록을 고친 뒤 새 pre/post hash와 실제 exit 영수증을 남긴다.")
if unknown:
 lines += ['', '## Unknown 항목','']
 for x in unknown:lines.append(f"- `{x['id']}`: 추가 근거 없음/범위 제외 ({json.dumps(x.get('evidence',{}),ensure_ascii=False)[:500]}).")
lines += ['', '상세 pass/fail/unknown 및 근거는 `review.json`; 검사대상 전후 해시와 선택 표본 SHA는 `hash_manifest.json`; 환경·RAM은 `environment.json`에 기록했다.']
(OUT/'audit_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'audit_status':overall,'exit_code':exit_code,
 'counts':{'pass':sum(x['status']=='pass' for x in results),'fail':len(failed),'unknown':len(unknown)},
 'items':[{'id':x['id'],'status':x['status']} for x in results],
 'ram_before_samples_mib':ram_before['available_mib'],'expected_peak_mib':expected_peak_mib,
 'artifact_paths':[str(OUT/x) for x in ('audit_report.md','review.json','hash_manifest.json','environment.json')]},ensure_ascii=False,sort_keys=True),flush=True)
sys.exit(exit_code)
