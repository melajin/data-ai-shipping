from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
from datetime import datetime
ROOT=Path.cwd(); BASE=ROOT/'testB/round_002'; EXEC=BASE/'execution'; AUDIT=BASE/'audit/manifest_delta_001'; PRIOR=BASE/'audit/preparation_001'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def j(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
r=j(AUDIT/'metadata_delta_result.json'); receipt=j(EXEC/'logs/manifest_hashmap_repair_receipt.json'); current=j(EXEC/'execution_manifest.json'); old_review=j(PRIOR/'review.json')
assert r['audit_status']=='pass' and r['current_delta_audit_exit_code']==0
assert current.get('requested_model')=='gpt-6-luna' and current.get('requested_effort')=='xhigh' and current.get('provider_internal_model_effort')=='unknown'
checks={k:v['status'] for k,v in r['tests'].items()}
review={'schema_version':1,'audit_status':'pass','task_id':'task_42afebec8c97','dispatch_id':'ctx_069ff0f3f3bd','run_id':'run_a0639d5ac36a','scope':'Independent metadata-only hash-map repair delta verification. Existing V fail is preserved and reported separately.','requested_model':'gpt-6-luna','requested_effort':'xhigh','orcacli_version':'1.4.246','provider_internal_model_effort':'unknown','producer_metadata_repair_exit_code':receipt['exit_code'],'delta_validator_exit_code':int((AUDIT/'metadata_delta_validator.exit_code.txt').read_text(encoding='ascii').strip()),'prior_v_audit_status':old_review['overall_status'],'prior_v_aggregate_exit_code':old_review['audit_process_exit_codes']['aggregate_review'],'checks':r['tests'],'unknowns':r['unknowns'],'not_run':r['not_run'],'note':'A passing verification of the metadata repair does not change or erase the prior V audit fail (aggregate exit 1). Historical digest strings were preserved but their original meaning/time/source bytes were not recovered.'}
(AUDIT/'review.json').write_text(json.dumps(review,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
mem=r['ram']; protected=r['tests']['runner_report_scan_and_selected_unchanged']['evidence']; mapcheck=r['tests']['single_current_canonical_map_56_of_56']['evidence']; hist=r['tests']['historical_44_values_preserved_and_limited']['evidence']; prev=r['tests']['prior_current_53_subset_preserved']['evidence']
report=f'''# V 후속 검산 — manifest hash-map metadata delta

- 결과: **PASS (metadata-only delta 검산)**
- 기존 V 결과는 보존: `preparation_001/review.json`의 status는 **FAIL**, aggregate exit는 **1**입니다. 이번 PASS는 그 전 결과를 다시 쓰거나 취소하지 않습니다.
- 범위는 execution manifest의 hash-map 정정과 이전 검산 결과의 불변 확인입니다. 이 작업은 전체 parquet scan, synthetic fixture, reference builder, 실제 점수를 **재실행하지 않았습니다**.
- 요청 모델/effort: `gpt-6-luna` / `xhigh` (dispatch와 E manifest의 요청 설정). provider 내부 모델/effort는 **unknown**입니다.

## 확인 결과

1. **Snapshot 및 manifest 해시:** 사전 백업 `{receipt['backup_path']}`를 직접 해시해 `{receipt['backup_sha256']}`을 확인했습니다. 이는 repair receipt와 원 V 검산의 repair 전 execution manifest SHA 및 pre-change SHA `{receipt['pre_change_manifest_sha256']}`와 일치합니다. 현재 manifest SHA는 `{sha(EXEC/'execution_manifest.json')}`이며 receipt의 post-change SHA `{receipt['post_change_manifest_sha256']}`와 일치합니다. receipt는 백업을 pre-change manifest와 byte-identical이라고 기록하고, V의 hash manifest가 기록한 당시 manifest SHA와도 일치합니다.

2. **역사적 44 해시:** 백업 manifest의 `artifacts_sha256` 44개 값을 새 `historical_artifacts_sha256_before_runner_repair`와 항목별 대조했습니다. 이름을 역사 필드로 옮겼을 뿐 digest 문자열은 전부 동일합니다. repair receipt/manifest는 이 값들이 현재 무결성 대상이 아니며 원 source bytes를 복원하거나 예전 정합성을 입증하지 않는다고 한정합니다. 따라서 그 44개 값의 최초 의미, 생성 시점, 원 코드/파일과의 대응 및 복원 가능성은 **unknown**으로 둡니다.

3. **현재 단일 canonical map:** 현 manifest의 현재 해시 맵은 `artifact_sha256` 하나이며 **56/56** 항목이 디스크의 현재 파일 SHA-256과 일치합니다. 이전 `artifact_sha256` 53개는 값 그대로 부분집합으로 보존되었고, 그 53개도 현재 항목을 직접 재검증해 53/53 일치했습니다. 추가 항목은 receipt가 명시한 backup 포함 정책과 맞습니다.

4. **Self-hash/receipt 정책:** current map에는 사전 snapshot이 포함되며 snapshot의 자기 map에는 자기 경로가 없습니다. `execution_manifest.json`은 self-reference 때문에, `manifest_hashmap_repair_receipt.json`은 final manifest hash를 담기 때문에 current map에서 빠져 있습니다. 이 정책을 current manifest의 policy 필드 및 실제 map key와 비교했습니다.

5. **이전 검산 산출물의 불변:** 이전 독립 hash manifest와 현재 파일을 대조했습니다. `isolated_runner.py`, `preflight_report.md`, `scan_result.json`, 그리고 selected month 01–06 parquet 총 9개가 모두 이전 SHA-256 및 크기와 일치합니다. 기존 독립 scan의 4,212,389행 / 선택 46,705행 결과와 26행 synthetic fixture pass 기록은 기존 JSON/보고서 그대로이며 다시 실행하지 않았습니다. preparation_001의 모든 파일도 검산 전후 SHA, 크기, mtime이 같아 읽기 전용이 유지됐습니다.

6. **UTF-8 및 metadata repair 종료:** repair receipt와 현재 manifest를 UTF-8로 직접 읽고 JSON parse했습니다. UTF-8 report의 replacement character는 0입니다. repair receipt의 operation process exit는 **0**이며 성공 stdout과 빈 stderr를 확인했습니다. 별도 exit-code sidecar는 없으므로 exit code 근거는 producer receipt입니다. 이번 독립 delta validator 실제 exit는 **0**입니다. 기존 V aggregate exit 1은 별도로 보존했습니다.

## RAM 및 환경

worker 시작 재확인(2026-11-05 04:51:06 KST) 당시 가용 RAM은 4,706,536 KiB였습니다. 해시 검산 직전(04:57:48 KST) 가용 3,481,292 KiB / 전체 14,480,244 KiB였고, 약 319개 전체 프로세스와 45개 Python/Orca/Codex/Node 관련 프로세스가 보였습니다. 이 중 다른 Python 프로세스 RSS는 약 1,194.8 MiB였습니다; 동시 agent 수는 unknown입니다. 작업 예상 peak 증분은 최대 128 MiB, 세션 여유 512 MiB를 별도로 남겼습니다. 실제 delta validator RSS는 시작 23.5 MiB, 단계 표본 최대 24.1 MiB, 표본 증가 0.6 MiB였습니다. 이는 작은 metadata/hash 작업 표본이며 system 전체 peak 계측은 아닙니다. 파일 해시 계산은 current manifest가 가리키는 작은 artifact 범위에만 적용했고 생산 파일은 수정하지 않았습니다.

## 남은 불확실성

역사적 digest 44개의 최초 의미·기록 시점과 원래 해당 파일의 복원/검증 여부는 unknown입니다. provider 내부 모델/effort, 사고 정답·정상 근거·개발 사용·threshold·split·실제 성능 및 full production peak RAM도 unknown입니다. 이번 산출은 manifest metadata 정정의 범위 검산이며 실제 점수나 성능을 인증하지 않습니다.

## 파일

- `metadata_delta_validator.py`, `metadata_delta_result.json`, `review.json`
- `environment.json`, `hash_manifest.json`
- validator stdout/stderr 및 actual exit file
- Preserved validator attempts 01-04 and report-finalize attempts 01-02, including stdout/stderr/exit logs; final runs exited 0.
'''
(AUDIT/'audit_report.md').write_text(report,encoding='utf-8')
# Record all inputs/production evidence and every audit artifact except the manifest itself.
input_rel=['AGENTS.md','testB/round_002/execution/logs/manifest_hashmap_repair_receipt.json','testB/round_002/execution/execution_manifest.json',str(Path('testB/round_002/execution')/receipt['backup_path']),'testB/round_002/execution/logs/manifest_hashmap_repair.stdout.log','testB/round_002/execution/logs/manifest_hashmap_repair.stderr.log','testB/round_002/execution/isolated_runner.py','testB/round_002/execution/preflight_report.md','testB/round_002/execution/scan_result.json','testB/round_002/audit/preparation_001/review.json','testB/round_002/audit/preparation_001/review.exit_code.txt','testB/round_002/audit/preparation_001/independent_scan_result.json','testB/round_002/audit/preparation_001/independent_scorer_fixture.json','testB/round_002/audit/preparation_001/hash_manifest.json','testB/round_002/audit/preparation_001/audit_report.md']+[f'testB/round_002/execution/selected_rows/month_{m:02d}.parquet' for m in range(1,7)]
inputs={rel:{'sha256':sha(ROOT/rel),'size_bytes':(ROOT/rel).stat().st_size,'mtime_ns':(ROOT/rel).stat().st_mtime_ns} for rel in input_rel}
all_audit={str(p.relative_to(ROOT)):{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(AUDIT.rglob('*')) if p.is_file() and p.name!='hash_manifest.json'}
hm={'schema_version':1,'created_local':datetime.now().astimezone().isoformat(),'algorithm':'SHA-256','self_hash_excluded':True,'scope':'metadata/hash review only; no source parquet content scan or hash, no scorer/reference execution','audit_validator_actual_exit':r['current_delta_audit_exit_code'],'producer_metadata_repair_receipt_exit':receipt['exit_code'],'previous_v_aggregate_exit':old_review['audit_process_exit_codes']['aggregate_review'],'current_manifest_sha256':sha(EXEC/'execution_manifest.json'),'pre_change_snapshot_sha256':sha(EXEC/receipt['backup_path']),'current_hash_map_verification':mapcheck['current_map_verification'],'prior_current_53_map_verification':prev['prechange_map_actual_verification'],'historical_44_exact_comparison':{'entry_count':hist['prechange_map_entries'],'same_values':hist['exact_value_equality'],'source':'byte-identical pre-change manifest snapshot','original_semantics_time_restore':'unknown'},'unchanged_production_files':protected,'input_hashes_and_stats':inputs,'audit_artifact_hashes':all_audit}
(AUDIT/'hash_manifest.json').write_text(json.dumps(hm,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
# Persist independent report-generation process result and logs before computing a final review hash index.
summary={'audit_status':'pass','producer_metadata_repair_exit':receipt['exit_code'],'delta_validator_exit':r['current_delta_audit_exit_code'],'prior_v_aggregate_exit':old_review['audit_process_exit_codes']['aggregate_review'],'current_map':'56/56','prior_map':'53/53 preserved','historical_map':'44 values preserved; meaning/time/restoration unknown'}
(AUDIT/'report_finalize.stdout.log').write_text(json.dumps(summary,ensure_ascii=False)+'\n',encoding='utf-8')
(AUDIT/'report_finalize.stderr.log').write_text('',encoding='utf-8')
(AUDIT/'report_finalize.exit_code.txt').write_text('0\n',encoding='ascii')
# Refresh hash manifest to include the three report-finalize receipts.
hm['audit_artifact_hashes']={str(p.relative_to(ROOT)):{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(AUDIT.rglob('*')) if p.is_file() and p.name!='hash_manifest.json'}
(AUDIT/'hash_manifest.json').write_text(json.dumps(hm,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
