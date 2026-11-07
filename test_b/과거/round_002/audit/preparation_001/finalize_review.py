from __future__ import annotations
import csv, hashlib, json, sys
from pathlib import Path
from datetime import datetime

ROOT=Path.cwd(); AUDIT=ROOT/'testB/round_002/audit/preparation_001'; PREP=ROOT/'testB/round_002/preparation'; EXEC=ROOT/'testB/round_002/execution'; ROUND=ROOT/'testB/round_002'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def j(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
scan=j(AUDIT/'independent_scan_result.json'); fixture=j(AUDIT/'independent_scorer_fixture.json')
pm=j(PREP/'manifest.json'); em=j(EXEC/'execution_manifest.json'); p_hash=j(PREP/'artifact_hashes.json')

p_artifact_checks=[]
for rel,expected in p_hash['files'].items():
 path=PREP/rel; actual=sha(path) if path.is_file() else None
 p_artifact_checks.append({'path':str(path.relative_to(ROOT)),'expected_sha256':expected,'actual_sha256':actual,'match':actual==expected})

def verify_map(name):
 m=em.get(name,{})
 ok=[]; bad=[]; missing=[]
 for rel,expected in m.items():
  path=EXEC/rel
  if not path.is_file(): missing.append(rel); continue
  actual=sha(path)
  if actual==expected: ok.append(rel)
  else: bad.append({'path':rel,'expected_sha256':expected,'actual_sha256':actual})
 return {'entry_count':len(m),'verified_match_count':len(ok),'mismatch_count':len(bad),'missing_count':len(missing),'mismatches':bad,'missing':missing}
map_old=verify_map('artifacts_sha256'); map_current=verify_map('artifact_sha256')

required_logs=['row_scan.exit_code.txt','row_scan_attempt04.exit_code.txt','syntax_final.exit_code.txt','synthetic_checks_final.exit_code.txt','syntax_repair.exit_code.txt','synthetic_repair.exit_code.txt','preflight_report_mojibake_legacy.md','execution_manifest_mojibake_legacy.json']
log_data={}
for name in required_logs:
 p=EXEC/'logs'/name
 if name.endswith('.exit_code.txt'):
  log_data[name]=p.read_text(encoding='ascii').strip() if p.exists() else 'missing'
 else: log_data[name]={'exists':p.exists(),'sha256':sha(p) if p.exists() else None}
execution_ok=(log_data['row_scan_attempt04.exit_code.txt']=='0' and log_data['syntax_final.exit_code.txt']=='0' and log_data['synthetic_checks_final.exit_code.txt']=='0' and log_data['syntax_repair.exit_code.txt']=='0' and log_data['synthetic_repair.exit_code.txt']=='0')

summ=scan['full_source_scan']; stat=scan['static_review']; readonly=scan['read_only_integrity']['unchanged']
all_source_hashes_match=all(x.get('matches') is True for x in scan['source_code_hashes'].values()) and len(scan['source_code_hashes'])==4
selection_ok=scan['ids']['count']==100 and scan['ids']['unique']==100 and scan['ids']['ordered_match_prior_direct_rows'] and scan['ids']['direct_zip_member_sha256']==pm['new_submission']['member_sha256'] and scan['ids']['intake_copy_sha256']==pm['new_submission']['intake_copy_sha256']
rows_ok=(summ['rows_scanned']==4212389 and summ['selected_rows']==46705 and summ['source_selected_exact'] and summ['row_index_errors']==0 and summ['summary_field_mismatch_count']==0 and summ['scorable_producer_total']==46705 and summ['scorable_contract_total']==46705 and summ['invalid_calendar_date_rows']==0 and summ['invalid_hour_rows']==0 and summ['key_valid_not_true_rows']==0 and summ['nonfinite_or_missing_numeric_cells']==0)
runner_ok=all(stat.get(k) is True for k in ['uses_explicit_source_hash_guard','shim_is_simple_namespace','AST_extracts_only_allowlisted_defs','build_gate_default_denies','test_fit_partition_fenced','load_inputs_manifest_unpack_fixed','scoring_order_includes_source_ordinal','A_source_order_selection','output_path_validation_present','main_entrypoint_guard'])
fixture_ok=fixture.get('status')=='pass' and fixture.get('haversine_calls',0)>=26 and fixture.get('s_change_first_defined_row')==24 and fixture.get('floor_fixture_preserved') is True
p_hash_ok=all(x['match'] for x in p_artifact_checks)
current_map_ok=map_current['mismatch_count']==0 and map_current['missing_count']==0 and map_current['entry_count']>0
hash_map_problem=map_old['mismatch_count']>0 or map_old['missing_count']>0

checks=[
 {'id':'ordered_100_id_lineage','status':'pass' if selection_ok and p_hash_ok else 'fail','evidence':{'ids':scan['ids'],'preparation_artifact_hashes':p_artifact_checks}},
 {'id':'independent_full_parquet_scan_and_selected_rows','status':'pass' if rows_ok else 'fail','evidence':summ},
 {'id':'production_source_hash_and_runner_boundary_review','status':'pass' if all_source_hashes_match and runner_ok else 'fail','evidence':{'source_code_hashes':scan['source_code_hashes'],'runner_static_review':stat}},
 {'id':'independent_synthetic_score_and_A_regression','status':'pass' if fixture_ok else 'fail','evidence':fixture},
 {'id':'production_scan_and_repair_exit_receipts','status':'pass' if execution_ok else 'fail','evidence':{'manifest_execution':em.get('execution'),'actual_exit_code_files':log_data}},
 {'id':'execution_manifest_latest_hash_map','status':'pass' if current_map_ok else 'fail','evidence':map_current},
 {'id':'execution_manifest_secondary_artifacts_sha256_map','status':'fail' if hash_map_problem else 'pass','evidence':{'interpretation':'present in the current manifest without an explicit historical/legacy label; therefore stale values are surfaced as a manifest integrity failure','verification':map_old,'notable_current_file_matches':{'preflight_report_legacy_backup_sha256':sha(EXEC/'logs/preflight_report_mojibake_legacy.md'),'preflight_report_claimed_old_sha256':next((x['expected_sha256'] for x in map_old['mismatches'] if x['path']=='preflight_report.md'),None)}}},
 {'id':'read_only_during_audit','status':'pass' if readonly else 'fail','evidence':scan['read_only_integrity']},
 {'id':'actual_reference_score_and_operational_performance','status':'unknown','evidence':'No production reference rebuild or actual data scoring was run, by the active gate. Accident truth/normal basis, development use, thresholds, splits, model performance, and full production RAM peak remain unknown.'},
 {'id':'provider_internal_model_effort','status':'unknown','evidence':'Orca launch receipt records requested gpt-6-luna/xhigh; provider internal model and actual internal effort are not observable.'},
]
overall='fail' if any(x['status']=='fail' for x in checks) else ('unknown' if any(x['status']=='unknown' for x in checks) else 'pass')
review={'schema_version':1,'overall_status':overall,'audit_scope':'Independent audit of Test B Round002 selected rows and modified runner only; no production reference rebuild or actual score generation.','run_id':'run_a0639d5ac36a','task_id':'task_8b98c91a7e20','dispatch_id':'ctx_f5235ff89d75','requested_model':'gpt-6-luna','requested_effort':'xhigh','provider_internal_model_effort':'unknown','checks':checks,'audit_process_exit_codes':{'independent_validator':int((AUDIT/'independent_validator.exit_code.txt').read_text().strip()),'independent_scorer_fixture':int((AUDIT/'independent_scorer_fixture.exit_code.txt').read_text().strip()),'aggregate_review':1 if overall=='fail' else 0},'final_note':'The data selection and independent fixture checks pass. Overall audit is FAIL because the current execution manifest contains a secondary artifacts_sha256 map with four current-file hash mismatches, while its separate artifact_sha256 map verifies 53/53 entries; the ambiguous stale map requires owner correction.'}
(AUDIT/'review.json').write_text(json.dumps(review,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

# Readable review report.
months=summ['per_month']; month_lines='\n'.join(f"| {m['month']} | {m['source_rows_scanned']:,} | {m['selected_in_source']:,} | {m['selected_parquet_rows']:,} | {'일치' if m['source_selected_values_exact'] else '불일치'} |" for m in months)
oldbad='\n'.join(f"- `{b['path']}`: manifest `{b['expected_sha256']}`, current `{b['actual_sha256']}`" for b in map_old['mismatches'])
report=f'''# V 독립 검산 보고서 — 실제 선별행·수정 runner

- 검산 결과: **{overall.upper()}**
- 범위: Test B Round002의 명부/선별 행/요약과 격리 runner 정적·합성 검산. 원자료·canonical·기존 cache·생산 execution은 읽기 전용으로 유지했습니다.
- Orca 실행: `orca --version` = `1.4.246`; 설치된 CLI의 `orca skills get orchestration --json` 안내를 읽었습니다. V launch receipt는 요청 모델 `gpt-6-luna`, effort `xhigh`를 기록합니다. provider 내부 모델/effort는 **unknown**입니다.
- 산출물은 이 폴더에만 썼습니다. 실제 점수/참조 구축은 실행하지 않았습니다.

## 핵심 결과

정확한 100개 문자열 ID, 순서, 고유성, prior direct recheck source rows 및 ZIP 제출샘플 워크북을 직접 대조했습니다. ZIP member와 intake copy SHA-256은 모두 `{scan['ids']['direct_zip_member_sha256']}`이며, 준비 명부 SHA-256은 `{scan['ids']['sha256']}`입니다. ZIP 전체 해시나 13GB 원 CSV 재해시·재파싱은 하지 않았습니다.

독립 validator가 원 Test parquet 6개를 `iter_batches(batch_size=16384)`와 필수 11열 투영으로 전수 스캔했습니다. 총 `{summ['rows_scanned']:,}`행 중 대상 행은 `{summ['selected_rows']:,}`행입니다. 각 선택 Parquet 행의 값, 월·source file·원 `row_index`, 계산한 `source_ordinal`을 원 parquet의 해당 ID 행과 비교해 **46,705/46,705 완전 일치**, 누락/추가/불일치 0건을 확인했습니다.

| 월 | 원 parquet 전체 | 독립 선별 | 저장 selected | 비교 |
|---:|---:|---:|---:|:---:|
{month_lines}

100개 target summary의 **모든 필드**를 별도 집계로 비교했습니다. raw 46,705, valid WKT 46,705, production 기준 scorable 46,705, 계약의 엄격 기준 scorable 46,705, 차이 0입니다. 달력상 잘못된 날짜 0, hour 0–23 밖 0, `key_valid`가 true가 아닌 행 0, 결측/비유한 점수입력 숫자 0, 중복 timestamp 재등장 0입니다. 관측 기간은 2025-01-01–2025-06-30이며 CRS/datum 및 시간대 의미는 unknown입니다. WKT 원문 정확성 검증 범위는 아닙니다.

## 수정 runner 검토

네 원본 생산코드의 현재 SHA-256을 고정값 및 E manifest와 대조해 4/4 일치했습니다. 독립 정적검토에서 run_008/remeasure allowlist AST 추출, 해시 가드, `SimpleNamespace` shim, train-only reference fit 경계, default-deny reference builder, `load_inputs` 반환 unpack, `source_ordinal` 순서/A 선택, output 경로 제한, main guard를 확인했습니다.

별도 작성한 26행 synthetic fixture는 원 scorer 함수를 source-hash 검증 뒤 AST로 추출하여 실행했습니다. 실제 haversine 호출 375회, 야간 정박→이동 state 경로, s_change의 24개 과거 행 경계(0–23행 결측, 24행부터 계산)를 확인했습니다. 24행의 `s_zone/s_change/s_gap/score`는 독립 scalar 식과 각각 일치합니다. 별도 fixture에서 floor `1e-6`, 서로 다른 시각의 동점은 원 입력 ordinal 첫 행 선택, 동일 시각 점수 충돌 및 valid/missing 혼합은 `data_conflict`, 전부 결측은 `no_valid_score`를 확인했습니다. 참조/실제 Test score는 생성하지 않았습니다.

E 생산 로그에서 row scan attempt04 exit 0, final syntax/synthetic exit 0을 확인했고, 최초 실패 exit 1과 SQLite scratch 재사용으로 폐기된 시도 및 UTF-8 수정 전 report/manifest 백업도 보존되어 있습니다. E manifest는 `references_rebuilt=false`, `actual_scores_computed=false`라고 기록합니다. 이번 독립 스캔 결과 exit 0, synthetic fixture exit 0입니다. stdout/stderr 및 실제 exit 파일은 이 폴더의 로그와 execution 원본 로그에서 확인 가능합니다.

## 실패: execution manifest 안의 stale hash map

현재 E `execution_manifest.json`의 최신 `artifact_sha256` map은 53/53 항목이 현재 파일과 일치합니다. 그러나 같은 manifest의 별도 `artifacts_sha256` map은 44개 중 4개가 현재 산출물과 다릅니다. map에 legacy라는 명시가 없어 이를 역사적 해시라고 단정할 수 없으므로 manifest 무결성 실패로 기록하고 소유자에게 수정을 요청합니다.

{oldbad}

특히 이전 `preflight_report.md` 해시는 보존된 손상 legacy report 백업 SHA와 일치합니다. 따라서 stale map이 이전 상태를 가리키는 정황은 있지만, manifest 안에서 구분하지 않습니다. current map의 53개 해시는 모두 일치합니다. 두 해시 세트는 [hash_manifest.json](hash_manifest.json)에 나눠 기록했습니다. 공용 execution/manifest는 소유권상 수정하지 않았습니다.

## 메모리·무결성 기록

전수 scan 직전 가용 RAM `{scan['ram_start']['available_mib']} MiB` / 총 `{scan['ram_start']['total_mib']} MiB`, 약 337개 프로세스(여러 Orca/Codex 포함; 병행 task 수 자체는 unknown), Python 프로세스 1개가 관측됐습니다. 예상 audit 증분 peak는 256 MiB, 별도 세션 여유 512 MiB를 유지했습니다. 이 감사 프로세스 RSS 시작 `{scan['ram_measured_process_rss_start_mib']} MiB`, batch 경계 표본 최대 `{scan['ram_peak_rss_sampled_mib']} MiB`, 증가 `{scan['ram_peak_rss_sampled_delta_mib']} MiB`였습니다. 이는 실제 순간 peak 보장이 아닌 batch 표본입니다. Source parquet 파일은 scan 전후 size/mtime을 비교했으나 전체 해시는 하지 않았습니다. production runner, manifest, 보고서, 요약 및 selected 6개 parquet의 audit 전후 SHA/stat은 변하지 않았습니다.

## 미확인 사항

사고 정답·정상 근거·개발 사용 여부·임계값·split·실제 성능과 성능 인증은 unknown입니다. 고정 참조 재구축과 새 100척 실제 점수 계산은 수행하지 않았고, 미실행 참조 builder의 dynamic import/write side effect도 정적검토 한계가 있습니다. provider 내부 모델/effort도 unknown입니다.

## 생성물

- `independent_validator.py`, `independent_scorer_fixture.py`
- `independent_scan_result.json`, `independent_scorer_fixture.json`
- 두 실행의 UTF-8 stdout/stderr, 실제 exit code 파일
- `review.json`, `hash_manifest.json`
'''
(AUDIT/'audit_report.md').write_text(report,encoding='utf-8')

# Full but bounded artifact manifest. Source parquet is stat-checked, intentionally not rehashed.
input_paths=['AGENTS.md','testB/round_002/ROUND_PLAN.md','testB/round_002/contract/EXPLORATORY_EXECUTION_CONTRACT.md','testB/round_002/contract/E_FIX_REVIEW.md','testB/round_002/preparation/preparation_report.md','testB/round_002/preparation/manifest.json','testB/round_002/preparation/artifact_hashes.json','testB/round_002/preparation/new_testB_ids_100.csv','testB/round_002/scorer_review/scorer_review.md','testB/round_002/scorer_review/manifest.json','testB/round_002/execution/preflight_report.md','testB/round_002/execution/execution_manifest.json','testB/round_002/execution/isolated_runner.py','testB/round_002/execution/scan_result.json','testB/round_002/execution/target_row_summary.csv','testB/round_001/audit/v2_id_recheck_001/source_id_rows.csv','testB/round_001/audit/v2_id_recheck_001/summary.json']
input_hashes={rel:{'sha256':sha(ROOT/rel),'size_bytes':(ROOT/rel).stat().st_size} for rel in input_paths}
production_paths=['testB/round_002/execution/logs/preflight_report_mojibake_legacy.md','testB/round_002/execution/logs/execution_manifest_mojibake_legacy.json']+[f'testB/round_002/execution/selected_rows/month_{m:02d}.parquet' for m in range(1,7)]
production_hashes={rel:{'sha256':sha(ROOT/rel),'size_bytes':(ROOT/rel).stat().st_size} for rel in production_paths}
source_stats={p:{'size_bytes':v['size_bytes'],'mtime_ns':v['mtime_ns'],'content_sha256':'not_computed'} for p,v in scan['read_only_integrity']['source_parquet_stats_before_after'].items()}
audit_files=[p for p in AUDIT.rglob('*') if p.is_file() and p.name!='hash_manifest.json']
audit_hashes={str(p.relative_to(ROOT)):{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(audit_files)}
hm={'schema_version':1,'created_local':datetime.now().astimezone().isoformat(),'algorithm':'SHA-256','self_hash':'omitted to avoid a self-referential digest','source_parquet_policy':'read-only; size/mtime before-after recorded; no full content hash performed by this audit','p_preparation_artifact_hashes':{'expected_count':len(p_artifact_checks),'matched_count':sum(x['match'] for x in p_artifact_checks),'checks':p_artifact_checks},'e_execution_manifest_hash_maps':{'artifact_sha256_current_map':map_current,'artifacts_sha256_secondary_map':map_old},'input_file_hashes':input_hashes,'production_artifact_hashes':production_hashes,'source_parquet_stats':source_stats,'audit_artifact_hashes':audit_hashes}
(AUDIT/'hash_manifest.json').write_text(json.dumps(hm,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

# Explicit aggregate nonzero outcome for the stale, unlabelled hash map.
rc=1 if overall=='fail' else 0
(AUDIT/'review.exit_code.txt').write_text(str(rc)+'\n',encoding='ascii')
(AUDIT/'review.stdout.log').write_text(json.dumps({'overall_status':overall,'independent_scan_exit':scan['audit_exit'],'synthetic_fixture':fixture['status'],'stale_manifest_map_mismatches':map_old['mismatch_count'],'current_manifest_map_mismatches':map_current['mismatch_count'],'aggregate_exit':rc},ensure_ascii=False)+'\n',encoding='utf-8')
(AUDIT/'review.stderr.log').write_text(('FAIL: execution_manifest.artifacts_sha256 has unlabelled current-file hash mismatches; owner correction requested.\n' if rc else ''),encoding='utf-8')
hm_path=AUDIT/'hash_manifest.json'; hm=json.loads(hm_path.read_text(encoding='utf-8'))
hm['audit_artifact_hashes']={str(p.relative_to(ROOT)):{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(AUDIT.rglob('*')) if p.is_file() and p.name!='hash_manifest.json'}
hm_path.write_text(json.dumps(hm,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'overall_status':overall,'p_hash_match_count':sum(x['match'] for x in p_artifact_checks),'e_current_map':map_current,'e_secondary_map':map_old,'aggregate_exit':rc},ensure_ascii=False))
sys.exit(rc)
