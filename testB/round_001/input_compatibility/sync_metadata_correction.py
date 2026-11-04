import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'testB/round_001/input_compatibility'
def filehash(p):
 h=hashlib.sha256();n=0
 with p.open('rb') as f:
  while True:
   b=f.read(1024*1024)
   if not b:break
   h.update(b);n+=len(b)
 return h.hexdigest(),n
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
log=json.loads((OUT/'metadata_correction_log.json').read_text(encoding='utf-8'))
receipt_path=ROOT/'testB/round_001/integration/runtime_receipts/W0_start.json'
receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))['result']
exit_code=int((OUT/'correction_exit_status.txt').read_text().strip())
started=(OUT/'correction_started_utc.txt').read_text(encoding='utf-8-sig').strip();finished=(OUT/'correction_finished_utc.txt').read_text(encoding='utf-8-sig').strip()
codehash=filehash(OUT/'metadata_correction.py')[0]
sync_hash=filehash(OUT/'sync_metadata_correction.py')[0]
receipt_observation={'path':str(receipt_path.relative_to(ROOT)),'sha256':filehash(receipt_path)[0],'dispatchId':receipt.get('dispatchId'),'taskId':receipt.get('taskId'),'runId':receipt.get('runId'),'state':receipt.get('state'),'agent':receipt.get('agent'),'model_observed_at_launch':'gpt-6-luna','effort_observed_at_launch':'xhigh','receipt_model':receipt.get('model'),'receipt_effort':receipt.get('effort'),'provider_internal_execution_details':'unknown; the Orca launch receipt records the requested/launch-observed model and effort, not a provider-internal attestation'}
exec_info={'started_utc':started,'finished_utc':finished,'actual_exit_code':exit_code,'code_sha256':codehash,'stdout_path':'testB/round_001/input_compatibility/correction_stdout.log','stderr_path':'testB/round_001/input_compatibility/correction_stderr.log','exit_path':'testB/round_001/input_compatibility/correction_exit_status.txt','runtime_receipt':receipt_observation}
summary['metadata_correction']['execution']=exec_info
summary['metadata_correction']['sync_code_sha256']=sync_hash
summary['orca_runtime_receipt']=receipt_observation
log['execution']=exec_info;log['sync_code_sha256']=sync_hash
# Write correction note in report, then persist summary and correction log.
report=OUT/'comparison_report.md';txt=report.read_text(encoding='utf-8')
extra=f"\n\nCorrection execution: actual exit code **{exit_code}**, UTC {started} to {finished}; correction code SHA-256 `{codehash}`. Orca receipt `{receipt_observation['path']}` (SHA-256 `{receipt_observation['sha256']}`) records launch-observed model `{receipt_observation['model_observed_at_launch']}` and effort `{receipt_observation['effort_observed_at_launch']}` for dispatch `{receipt_observation['dispatchId']}`. Provider-internal execution attestation is unknown; this is a launch receipt observation.\n"
if 'Correction execution: actual exit code' not in txt:txt+=extra
report.write_text(txt,encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'metadata_correction_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
# Hash every durable file in the authorized output tree. Exclude only this manifest and its own post-exit sync captures.
artifacts=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file() and p.name not in ('manifest.json','correction_sync_stdout.log','correction_sync_stderr.log','correction_sync_exit_status.txt'):
  dh,n=filehash(p);artifacts.append({'path':str(p.relative_to(ROOT)),'bytes':n,'sha256':dh})
manifest={'generated_utc':datetime.now(timezone.utc).isoformat(),'task':'W0 metadata-verdict correction and legacy100 applicability note','status':'corrected','correction_execution':exec_info,'correction_code_sha256':codehash,'sync_code_sha256':sync_hash,'preserved_pre_correction':log['preserved_files'],'previous_manifest_sha256':log['original_manifest_sha256'],'previous_summary_sha256':log['original_summary_sha256'],'previous_report_sha256':log['original_report_sha256'],'archive_unchanged_evidence_reused_from_original_run':{'sha256_before':summary['archive_sha256_before'],'sha256_after':summary['archive_sha256_after'],'unchanged':summary['archive_unchanged_by_hash']},'large_input_rehash_performed':False,'old_input_content_hash_match_count':sum(1 for x in summary['old_input_posthash_verification'] if x['comparison_sha256']==x['post_sha256']),'old_input_metadata_match_count':sum(1 for x in summary['old_input_posthash_verification'] if x['metadata_unchanged_through_posthash']),'id_set_intersections':summary['test_id_sequence_summary'],'legacy100_new_target_use':summary['legacy100_new_target_use'],'runtime_receipt':receipt_observation,'artifacts':artifacts}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'ok','actual_correction_exit':exit_code,'artifact_count':len(artifacts),'manifest_sha256':filehash(OUT/'manifest.json')[0]},ensure_ascii=False))
