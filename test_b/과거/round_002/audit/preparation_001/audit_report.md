# V 독립 검산 보고서 — 실제 선별행·수정 runner

- 검산 결과: **FAIL**
- 범위: Test B Round002의 명부/선별 행/요약과 격리 runner 정적·합성 검산. 원자료·canonical·기존 cache·생산 execution은 읽기 전용으로 유지했습니다.
- Orca 실행: `orca --version` = `1.4.246`; 설치된 CLI의 `orca skills get orchestration --json` 안내를 읽었습니다. V launch receipt는 요청 모델 `gpt-6-luna`, effort `xhigh`를 기록합니다. provider 내부 모델/effort는 **unknown**입니다.
- 산출물은 이 폴더에만 썼습니다. 실제 점수/참조 구축은 실행하지 않았습니다.

## 핵심 결과

정확한 100개 문자열 ID, 순서, 고유성, prior direct recheck source rows 및 ZIP 제출샘플 워크북을 직접 대조했습니다. ZIP member와 intake copy SHA-256은 모두 `035fbced3dd46319f2506ab9b8bbb4f1756712ae3d94ecf6953d3587e056609c`이며, 준비 명부 SHA-256은 `d7c5affc53473cc45a3372c9bc7b82eb0466cdb99a77e2f4996b6cc8325d3ec4`입니다. ZIP 전체 해시나 13GB 원 CSV 재해시·재파싱은 하지 않았습니다.

독립 validator가 원 Test parquet 6개를 `iter_batches(batch_size=16384)`와 필수 11열 투영으로 전수 스캔했습니다. 총 `4,212,389`행 중 대상 행은 `46,705`행입니다. 각 선택 Parquet 행의 값, 월·source file·원 `row_index`, 계산한 `source_ordinal`을 원 parquet의 해당 ID 행과 비교해 **46,705/46,705 완전 일치**, 누락/추가/불일치 0건을 확인했습니다.

| 월 | 원 parquet 전체 | 독립 선별 | 저장 selected | 비교 |
|---:|---:|---:|---:|:---:|
| 1 | 592,013 | 6,258 | 6,258 | 일치 |
| 2 | 442,715 | 5,387 | 5,387 | 일치 |
| 3 | 624,514 | 6,625 | 6,625 | 일치 |
| 4 | 755,491 | 7,907 | 7,907 | 일치 |
| 5 | 888,878 | 10,099 | 10,099 | 일치 |
| 6 | 908,778 | 10,429 | 10,429 | 일치 |

100개 target summary의 **모든 필드**를 별도 집계로 비교했습니다. raw 46,705, valid WKT 46,705, production 기준 scorable 46,705, 계약의 엄격 기준 scorable 46,705, 차이 0입니다. 달력상 잘못된 날짜 0, hour 0–23 밖 0, `key_valid`가 true가 아닌 행 0, 결측/비유한 점수입력 숫자 0, 중복 timestamp 재등장 0입니다. 관측 기간은 2025-01-01–2025-06-30이며 CRS/datum 및 시간대 의미는 unknown입니다. WKT 원문 정확성 검증 범위는 아닙니다.

## 수정 runner 검토

네 원본 생산코드의 현재 SHA-256을 고정값 및 E manifest와 대조해 4/4 일치했습니다. 독립 정적검토에서 run_008/remeasure allowlist AST 추출, 해시 가드, `SimpleNamespace` shim, train-only reference fit 경계, default-deny reference builder, `load_inputs` 반환 unpack, `source_ordinal` 순서/A 선택, output 경로 제한, main guard를 확인했습니다.

별도 작성한 26행 synthetic fixture는 원 scorer 함수를 source-hash 검증 뒤 AST로 추출하여 실행했습니다. 실제 haversine 호출 375회, 야간 정박→이동 state 경로, s_change의 24개 과거 행 경계(0–23행 결측, 24행부터 계산)를 확인했습니다. 24행의 `s_zone/s_change/s_gap/score`는 독립 scalar 식과 각각 일치합니다. 별도 fixture에서 floor `1e-6`, 서로 다른 시각의 동점은 원 입력 ordinal 첫 행 선택, 동일 시각 점수 충돌 및 valid/missing 혼합은 `data_conflict`, 전부 결측은 `no_valid_score`를 확인했습니다. 참조/실제 Test score는 생성하지 않았습니다.

E 생산 로그에서 row scan attempt04 exit 0, final syntax/synthetic exit 0을 확인했고, 최초 실패 exit 1과 SQLite scratch 재사용으로 폐기된 시도 및 UTF-8 수정 전 report/manifest 백업도 보존되어 있습니다. E manifest는 `references_rebuilt=false`, `actual_scores_computed=false`라고 기록합니다. 이번 독립 스캔 결과 exit 0, synthetic fixture exit 0입니다. stdout/stderr 및 실제 exit 파일은 이 폴더의 로그와 execution 원본 로그에서 확인 가능합니다.

## 실패: execution manifest 안의 stale hash map

현재 E `execution_manifest.json`의 최신 `artifact_sha256` map은 53/53 항목이 현재 파일과 일치합니다. 그러나 같은 manifest의 별도 `artifacts_sha256` map은 44개 중 4개가 현재 산출물과 다릅니다. map에 legacy라는 명시가 없어 이를 역사적 해시라고 단정할 수 없으므로 manifest 무결성 실패로 기록하고 소유자에게 수정을 요청합니다.

- `__pycache__/isolated_runner.cpython-313.pyc`: manifest `e590b43f9e1d719f0557271a67af104ce71da2e454364cdafb5233a01f9df5e5`, current `933c66d1fdc29b83fbce6a2a7999e63934249b6beb98b81dbd27b8b31b97a939`
- `isolated_runner.py`: manifest `19cb07986dd94912bec3d026462ef9073eba368cdfbe9368ba5cef73169af573`, current `83ccc784e4b538b41199939420a516aa0c4cc644b8f06c344712ae8db3d91c1d`
- `preflight_report.md`: manifest `ad9466701dccde0d67288651b3103e986675e3f52e21acdefabe1ff08bfcfb5e`, current `8c69bb155702260d0f2b797bc51c621a242c5030e30392ae72dd321a5c8ca58d`
- `scan_result.json`: manifest `307326e6fb125390e91d6fa464b4b14e9b582c89df00965967218838450c3cc3`, current `f72f210de4f0535c0f17377343bfcdb43a6e0e498da2914dd24e719856c4bc4c`

특히 이전 `preflight_report.md` 해시는 보존된 손상 legacy report 백업 SHA와 일치합니다. 따라서 stale map이 이전 상태를 가리키는 정황은 있지만, manifest 안에서 구분하지 않습니다. current map의 53개 해시는 모두 일치합니다. 두 해시 세트는 [hash_manifest.json](hash_manifest.json)에 나눠 기록했습니다. 공용 execution/manifest는 소유권상 수정하지 않았습니다.

## 메모리·무결성 기록

전수 scan 직전 가용 RAM `4149.3 MiB` / 총 `14140.9 MiB`, 약 337개 프로세스(여러 Orca/Codex 포함; 병행 task 수 자체는 unknown), Python 프로세스 1개가 관측됐습니다. 예상 audit 증분 peak는 256 MiB, 별도 세션 여유 512 MiB를 유지했습니다. 이 감사 프로세스 RSS 시작 `54.6 MiB`, batch 경계 표본 최대 `189.4 MiB`, 증가 `134.8 MiB`였습니다. 이는 실제 순간 peak 보장이 아닌 batch 표본입니다. Source parquet 파일은 scan 전후 size/mtime을 비교했으나 전체 해시는 하지 않았습니다. production runner, manifest, 보고서, 요약 및 selected 6개 parquet의 audit 전후 SHA/stat은 변하지 않았습니다.

## 미확인 사항

사고 정답·정상 근거·개발 사용 여부·임계값·split·실제 성능과 성능 인증은 unknown입니다. 고정 참조 재구축과 새 100척 실제 점수 계산은 수행하지 않았고, 미실행 참조 builder의 dynamic import/write side effect도 정적검토 한계가 있습니다. provider 내부 모델/effort도 unknown입니다.

## 생성물

- `independent_validator.py`, `independent_scorer_fixture.py`
- `independent_scan_result.json`, `independent_scorer_fixture.json`
- 두 실행의 UTF-8 stdout/stderr, 실제 exit code 파일
- `review.json`, `hash_manifest.json`
