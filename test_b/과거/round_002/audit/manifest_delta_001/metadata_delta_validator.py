from __future__ import annotations
import hashlib, json, os, platform, sys, time
from datetime import datetime
from pathlib import Path
import psutil

ROOT=Path.cwd(); ROUND=ROOT/'testB/round_002'; EXEC=ROUND/'execution'; AUDIT=ROUND/'audit/manifest_delta_001'; PRIOR=ROUND/'audit/preparation_001'
RECEIPT=EXEC/'logs/manifest_hashmap_repair_receipt.json'; MANIFEST=EXEC/'execution_manifest.json'
EXPECTED_BEFORE='8f4533ca1efa2a0a1ff8d8bb4d49151344cf1e9d4569c51ac0b8a3469f7b0c9a'
EXPECTED_AFTER='a8bb74a10936572ad152aabeacc5f741a036d922e3a86fdd2f0dbcb494117e42'

def sha_file(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def read_json(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def snapshot_memory():
    v=psutil.virtual_memory(); procs=[]
    for p in psutil.process_iter(['name','memory_info']):
        try:
            if p.info['name'] and any(x in p.info['name'].lower() for x in ('python','codex','node','orca')):
                procs.append({'name':p.info['name'],'pid':p.pid,'rss_mib':round(p.info['memory_info'].rss/2**20,1)})
        except (psutil.NoSuchProcess,psutil.AccessDenied,TypeError): pass
    procs.sort(key=lambda x:x['rss_mib'],reverse=True)
    return {'local_time':datetime.now().astimezone().isoformat(),'available_mib':round(v.available/2**20,1),'available_kib':int(v.available/1024),'total_mib':round(v.total/2**20,1),'process_count':len(psutil.pids()),'relevant_process_count':len(procs),'top_relevant_processes':procs[:12]}

def verify_map(base, mapping, label):
    matches=[]; misses=[]; mismatch=[]
    for rel,expected in mapping.items():
        p=base/rel
        if not p.is_file(): misses.append(rel); continue
        actual=sha_file(p)
        if actual==expected: matches.append(rel)
        else: mismatch.append({'path':rel,'expected':expected,'actual':actual})
    return {'name':label,'entries':len(mapping),'matches':len(matches),'missing':misses,'mismatches':mismatch,'pass':len(matches)==len(mapping) and not misses and not mismatch}

def run():
    started=time.time(); mem=snapshot_memory(); expected_peak=128; reserve=512
    if mem['available_mib'] < expected_peak+reserve: raise MemoryError(f"RAM gate: available={mem['available_mib']}MiB, need {expected_peak}+{reserve}MiB")
    proc=psutil.Process(); rss_start=proc.memory_info().rss; rss_peak=rss_start
    # Snapshot all files in the prior audit folder before reading the repair delta.
    prior_before={str(p.relative_to(ROOT)):{'sha256':sha_file(p),'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in sorted(PRIOR.rglob('*')) if p.is_file()}
    receipt=read_json(RECEIPT); current=read_json(MANIFEST)
    backup=EXEC/receipt['backup_path']
    backup_actual=sha_file(backup); current_actual=sha_file(MANIFEST)
    before=read_json(backup)
    before_hash_manifest=read_json(PRIOR/'hash_manifest.json')
    prior_review=read_json(PRIOR/'review.json')
    prior_scan=read_json(PRIOR/'independent_scan_result.json')
    prior_fixture=read_json(PRIOR/'independent_scorer_fixture.json')

    before_map=before.get('artifact_sha256',{})
    before_legacy=before.get('artifacts_sha256',{})
    after_map=current.get('artifact_sha256',{})
    after_legacy=current.get('historical_artifacts_sha256_before_runner_repair',{})
    old_current_map=verify_map(EXEC,before_map,'pre-repair current artifact_sha256 (53)')
    new_current_map=verify_map(EXEC,after_map,'post-repair canonical artifact_sha256 (56)')
    current_subset={k:v for k,v in after_map.items() if k in before_map}
    prior53_preserved=(current_subset==before_map and len(before_map)==53)
    history_identical=(before_legacy==after_legacy and len(before_legacy)==44)
    snapshot_recorded_hash=next(v['sha256'] for k,v in before_hash_manifest['input_file_hashes'].items() if k.replace('\\','/')=='testB/round_002/execution/execution_manifest.json')
    # Existing core data/code outputs must remain exactly as independently hashed before metadata repair.
    protected_rel=['testB/round_002/execution/isolated_runner.py','testB/round_002/execution/preflight_report.md','testB/round_002/execution/scan_result.json']+[f'testB/round_002/execution/selected_rows/month_{m:02d}.parquet' for m in range(1,7)]
    prior_artifact_map={k.replace('\\','/'):v for k,v in before_hash_manifest['input_file_hashes'].items()}
    prior_artifact_map.update({k.replace('\\','/'):v for k,v in before_hash_manifest['production_artifact_hashes'].items()})
    protected=[]
    for rel in protected_rel:
        expected=prior_artifact_map[rel]['sha256']; p=ROOT/rel; actual=sha_file(p)
        protected.append({'path':rel,'prior_independent_sha256':expected,'current_sha256':actual,'unchanged':expected==actual,'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns})
    protected_unchanged=all(x['unchanged'] for x in protected)
    # Snapshot exact pre-change manifest hash recorded by the V audit and in repair receipt.
    prior_pre_repair_manifest_hash=snapshot_recorded_hash
    exact_before=(backup_actual==EXPECTED_BEFORE==receipt['pre_change_manifest_sha256']==receipt['backup_sha256']==prior_pre_repair_manifest_hash and receipt['backup_byte_identical_to_pre_change_manifest'] is True)
    exact_after=(current_actual==EXPECTED_AFTER==receipt['post_change_manifest_sha256'])
    historical_meta=current.get('historical_artifacts_sha256_before_runner_repair_metadata',{})
    receipt_stdout=(EXEC/'logs/manifest_hashmap_repair.stdout.log').read_text(encoding='utf-8-sig')
    receipt_stderr=(EXEC/'logs/manifest_hashmap_repair.stderr.log').read_text(encoding='utf-8-sig')
    actual_repair_exit=int(receipt.get('exit_code',-1))
    # The execution producer records its process exit in the JSON receipt; stdout/stderr are checked directly.
    repair_receipt_ok=actual_repair_exit==0 and 'Pre-change manifest copied byte-for-byte' in receipt_stdout and receipt_stderr.strip()==''
    legacy_status_ok=(historical_meta.get('status')=='legacy-only; not a current integrity target' and historical_meta.get('applied_scope')=='classification only; 44 historical digest strings retained verbatim and not recomputed or overwritten' and receipt.get('historical_map_not_restored_or_validated_as_original_source_bytes') is True and 'not establish that all 44 digests were correct' in historical_meta.get('limitations',''))
    hash_map_meta=current.get('current_hash_map_policy',{})
    receipt_fields={
      'before_manifest_hash':receipt.get('pre_change_manifest_sha256'),
      'backup_hash':receipt.get('backup_sha256'),
      'after_manifest_hash':receipt.get('post_change_manifest_sha256'),
      'legacy_count':receipt.get('legacy_map_entries'),
      'prior_current_count':receipt.get('prior_current_map_entries'),
      'new_current_count':receipt.get('new_current_map_entries'),
      'new_current_map_all_match':receipt.get('new_current_map_all_match'),
      'prior_current_map_preserved':receipt.get('prior_53_current_entries_preserved_unchanged'),
      'historical_values_match_pre_change_snapshot':receipt.get('historical_map_44_values_match_pre_change_snapshot'),
      'repair_exit_code':actual_repair_exit,
    }
    policy_ok=(hash_map_meta.get('only_current_hash_map') is True and hash_map_meta.get('canonical_map_field')=='artifact_sha256' and hash_map_meta.get('manifest_snapshot_is_hashed_by_current_map') is True and hash_map_meta.get('snapshot_contains_no_self_hash') is True and 'execution_manifest.json' in hash_map_meta.get('scope','') and 'manifest_hashmap_repair_receipt.json' in hash_map_meta.get('scope',''))
    receipt_path='logs/manifest_hashmap_repair_receipt.json'; snapshot_rel=receipt.get('backup_path')
    self_exclusion=(snapshot_rel in after_map and 'execution_manifest.json' not in after_map and receipt_path not in after_map and snapshot_rel not in before.get('artifact_sha256',{}))
    map_fields={k for k,v in current.items() if isinstance(v,dict) and k in ('artifact_sha256','artifacts_sha256','historical_artifacts_sha256_before_runner_repair')}
    current_map_fields={k for k in current if k in ('artifact_sha256','artifacts_sha256')}
    single_current=(current_map_fields=={'artifact_sha256'} and len(after_map)==56 and new_current_map['pass'])
    utf8_ok=True
    utf8_files=[]
    for p in [RECEIPT,MANIFEST,EXEC/'preflight_report.md']:
        b=p.read_bytes(); decoded=b.decode('utf-8-sig'); utf8_files.append({'path':str(p.relative_to(ROOT)),'decodes':True,'replacement_count':decoded.count('\ufffd'),'size_bytes':len(b)})
        if '\ufffd' in decoded: utf8_ok=False
    utf8_ok=utf8_ok and receipt['utf8']['new_manifest_utf8_json_parse'] and receipt['utf8']['receipt_written_as_utf8'] and current['utf8_integrity']['preflight_report_replacement_character_count']==0

    # Preserve the original V fail outcome as evidence; the follow-up audit has its own exit status.
    prior_fail_preserved=(prior_review['overall_status']=='fail' and prior_review['audit_process_exit_codes']['aggregate_review']==1 and int((PRIOR/'review.exit_code.txt').read_text(encoding='ascii').strip())==1)
    old_rows=prior_scan['full_source_scan']; old_scan_exit=int((PRIOR/'independent_validator.exit_code.txt').read_text(encoding='ascii').strip())
    old_fixture_exit=int((PRIOR/'independent_scorer_fixture.exit_code.txt').read_text(encoding='ascii').strip())
    prior_evidence_linked=(old_scan_exit==0 and old_rows['rows_scanned']==4212389 and old_rows['selected_rows']==46705 and old_rows['source_selected_exact'] is True and prior_fixture['status']=='pass' and prior_fixture['fixture_rows']==26 and old_fixture_exit==0 and protected_unchanged)
    # All non-hash-map top-level execution payload must be unchanged between the byte-identical backup and after file.
    changed_top={k:{'before_present':k in before,'after_present':k in current,'before':before.get(k),'after':current.get(k)} for k in sorted(set(before)|set(current)) if before.get(k)!=current.get(k)}
    allowed_changed={'artifacts_sha256','artifact_sha256','historical_artifacts_sha256_before_runner_repair','historical_artifacts_sha256_before_runner_repair_metadata','current_hash_map_policy','hash_map_repair'}
    metadata_scope_only=set(changed_top).issubset(allowed_changed)

    # Recheck immutable prior audit folder after our read-only use.
    prior_after={str(p.relative_to(ROOT)):{'sha256':sha_file(p),'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in sorted(PRIOR.rglob('*')) if p.is_file()}
    prior_ro=(prior_before==prior_after)
    rss_peak=max(rss_peak,proc.memory_info().rss)
    tests={
      'prechange_backup_and_postchange_manifest_hashes':{'status':'pass' if exact_before and exact_after else 'fail','evidence':{'expected_pre_change_sha256':EXPECTED_BEFORE,'actual_backup_sha256':backup_actual,'pre_change_manifest_hash_in_receipt':receipt['pre_change_manifest_sha256'],'prior_V_hash_manifest_before_repair':prior_pre_repair_manifest_hash,'expected_post_change_sha256':EXPECTED_AFTER,'actual_post_change_sha256':current_actual,'receipt_post_change_manifest_sha256':receipt['post_change_manifest_sha256']}},
      'historical_44_values_preserved_and_limited':{'status':'pass' if history_identical and legacy_status_ok else 'fail','evidence':{'prechange_map_entries':len(before_legacy),'postchange_historical_entries':len(after_legacy),'exact_value_equality':history_identical,'metadata':historical_meta,'receipt_does_not_claim_restoration':receipt.get('historical_map_not_restored_or_validated_as_original_source_bytes')}},
      'prior_current_53_subset_preserved':{'status':'pass' if prior53_preserved and old_current_map['pass'] else 'fail','evidence':{'prior_count':len(before_map),'after_subset_count':len(current_subset),'map_values_unchanged':prior53_preserved,'prechange_map_actual_verification':old_current_map}},
      'single_current_canonical_map_56_of_56':{'status':'pass' if single_current else 'fail','evidence':{'canonical_field':hash_map_meta.get('canonical_map_field'),'current_map_fields':sorted(current_map_fields),'historical_field':('historical_artifacts_sha256_before_runner_repair' if 'historical_artifacts_sha256_before_runner_repair' in map_fields else None),'current_map_verification':new_current_map,'receipt_counts':receipt_fields}},
      'backup_snapshot_and_self_hash_exclusion':{'status':'pass' if self_exclusion and policy_ok else 'fail','evidence':{'snapshot_path':snapshot_rel,'snapshot_in_current_map':snapshot_rel in after_map,'snapshot_hash_in_current_map':after_map.get(snapshot_rel),'backup_snapshot_own_artifact_map_count':len(before.get('artifact_sha256',{})),'snapshot_own_map_has_self_entry':snapshot_rel in before.get('artifact_sha256',{}),'manifest_self_entry_present':'execution_manifest.json' in after_map,'repair_receipt_entry_present':receipt_path in after_map,'policy':hash_map_meta}},
      'runner_report_scan_and_selected_unchanged':{'status':'pass' if protected_unchanged else 'fail','evidence':protected},
      'repair_utf8_and_actual_exit':{'status':'pass' if utf8_ok and repair_receipt_ok else 'fail','evidence':{'utf8_files':utf8_files,'receipt_utf8':receipt['utf8'],'receipt_exit_code':actual_repair_exit,'stdout':receipt_stdout.strip(),'stderr_empty':receipt_stderr.strip()=='' ,'exit_code_sidecar_present':(EXEC/'logs/manifest_hashmap_repair.exit_code.txt').exists()}},
      'original_V_fail_preserved':{'status':'pass' if prior_fail_preserved else 'fail','evidence':{'prior_overall_status':prior_review['overall_status'],'prior_aggregate_exit':prior_review['audit_process_exit_codes']['aggregate_review'],'prior_review_exit_file':int((PRIOR/'review.exit_code.txt').read_text(encoding='ascii').strip())}},
      'previous_row_scan_and_synthetic_evidence_linked_without_rerun':{'status':'pass' if prior_evidence_linked else 'fail','evidence':{'prior_independent_scan_exit':old_scan_exit,'prior_rows_scanned':old_rows['rows_scanned'],'prior_selected_rows':old_rows['selected_rows'],'prior_selected_match':old_rows['source_selected_exact'],'prior_synthetic_exit':old_fixture_exit,'prior_fixture_rows':prior_fixture['fixture_rows'],'prior_fixture_status':prior_fixture['status'],'unchanged_code_report_scan_selected':protected_unchanged,'rerun_this_task':False}},
      'metadata_only_change_scope':{'status':'pass' if metadata_scope_only and prior_ro else 'fail','evidence':{'changed_top_level_fields':sorted(changed_top),'allowed_metadata_fields':sorted(allowed_changed),'only_metadata_changed':metadata_scope_only,'prior_audit_folder_unchanged':prior_ro}},
    }
    fail=[k for k,v in tests.items() if v['status']=='fail']
    result={'schema_version':1,'audit_status':'fail' if fail else 'pass','scope':'Independent metadata/hash-map repair delta verification; no row scan, synthetic execution, reference rebuild or actual score rerun.','task_id':'task_42afebec8c97','dispatch_id':'ctx_069ff0f3f3bd','run_id':'run_a0639d5ac36a','requested_model':'gpt-6-luna','requested_effort':'xhigh','provider_internal_model_effort':'unknown','ram':{'before_work':mem,'expected_peak_increment_mib':expected_peak,'separate_session_reserve_mib':reserve,'rss_start_mib':round(rss_start/2**20,1),'rss_sampled_peak_mib':round(rss_peak/2**20,1),'rss_sampled_delta_mib':round((rss_peak-rss_start)/2**20,1),'sampling_note':'process RSS sampled at start and after hash/review stages; small metadata task only, not system-wide exact peak'},'environment':{'python':sys.version,'platform':platform.platform(),'psutil':psutil.__version__},'metadata_repair_receipt':{'path':str(RECEIPT.relative_to(ROOT)),'sha256':sha_file(RECEIPT),'operation':receipt['operation'],'applied_at_local':receipt['applied_at_local'],'actual_process_exit_code_recorded':actual_repair_exit,'exit_sidecar_present':(EXEC/'logs/manifest_hashmap_repair.exit_code.txt').exists()},'previous_V_audit':{'status':prior_review['overall_status'],'aggregate_exit_code':prior_review['audit_process_exit_codes']['aggregate_review'],'preserved':prior_fail_preserved},'current_delta_audit_exit_code':0 if not fail else 1,'tests':tests,'unknowns':['The preserved historical 44 digests were not restored or validated as original source bytes; their original semantic label and initial recording time remain unknown.','Historical source/pyc bytes that once corresponded to the 44 digests are not available for restoration/verification.','Provider internal model and effort are unknown.','Accident truth, normal basis, development use, thresholds, splits, performance, and full production peak RAM remain unknown.'],'not_run':['full parquet scan','independent synthetic scorer fixture','reference rebuild','actual score'],'audit_artifacts':{'output_directory':str(AUDIT.relative_to(ROOT)),'aggregate_exit_code':0 if not fail else 1}}
    (AUDIT/'metadata_delta_result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (AUDIT/'environment.json').write_text(json.dumps({'requested_model':'gpt-6-luna','requested_effort':'xhigh','provider_internal_model_effort':'unknown','memory':result['ram'],'python':result['environment'],'orcacli_version':'1.4.246','metadata_repair_actual_exit_code':actual_repair_exit,'prior_v_aggregate_exit_code':1,'delta_audit_exit_code':result['current_delta_audit_exit_code']},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    try:
        r=run(); print(json.dumps({'audit_status':r['audit_status'],'prechange_backup_verified':r['tests']['prechange_backup_and_postchange_manifest_hashes']['status'],'current_map':r['tests']['single_current_canonical_map_56_of_56']['status'],'prior_V_exit':r['previous_V_audit']['aggregate_exit_code'],'delta_exit':r['current_delta_audit_exit_code']},ensure_ascii=False))
        sys.exit(r['current_delta_audit_exit_code'])
    except Exception as e:
        error={'audit_status':'fail','error_type':type(e).__name__,'error':str(e)}
        (AUDIT/'metadata_delta_result.json').write_text(json.dumps(error,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(error,ensure_ascii=False),file=sys.stderr); sys.exit(1)
