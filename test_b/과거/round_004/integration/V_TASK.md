# V 독립 정적검토 — Round004

별도 실제 Orca gpt-6-luna/xhigh 독립검산자다. 요청/launch 설정과 provider 내부 unknown을 구분한다. ORCA_CLI_COMMAND와 선택 실행파일 skills get orchestration/orca-cli 안내, AGENTS RAM 규칙부터 확인한다. AGENTS.md, testB/USER_DIRECTIVE_20261105.md, ROUND_PROTOCOL.md, STATUS.json, round_004/ROUND_PLAN.md, round_003/NEXT_ROUND.md/ROUND_REPORT.md, audit/independent_static_review.md와 audit/failure_001/failure_audit.md/fixture_result.json, round_002/contract/EXPLORATORY_EXECUTION_CONTRACT.md를 UTF-8로 전부 읽는다.

소유권은 testB/round_004/audit/만이다. 당신 혼자 작업하는 저장소가 아니다. E는 execution/, 감독은 공통/통합문서를 소유한다. 타인 변경을 되돌리지 말고 수용한다. 생산코드 수정은 E에 요청한다. 원자료/canonical/cache/선행round 읽기전용이다.

첫 task는 독립 정적 필요조건 검토다. 원본4해시와 load_rows/builder 호출 columns/kwargs를 직접 읽고, 좁은 ASCII정수 도메인의 global/batch numeric 동등성 논증을 검토한다. abs(ID)<=2^53, date int32, null/명백한 nonnumeric 및 문법/길이/leadingzero/부호를 구체화한다. 소수/scientific/공백/overflow 등 원본 수용가능한 unsupported 값을 임의 제외하면 안 된다. fail-closed 조건과 ID 제외 뒤 date 검사/변환 순서, key_valid 이후 concat ordinal 및 numeric drop 후 index 구멍 보존, 요청열별 API와 빈batch/월경계/NaN dtype를 검토한다. E 코드를 복제한 oracle로 독립성을 주장하지 않는다. E 완료 후 별도 followup task에서 원본 AST+독립 oracle와 신규 fixture/실제 multi-batch 증거를 검산할 계획을 작성한다. 이번 task는 원본 파일/정적 텍스트검토만; 큰 parquet/전체 key scan/기존Test scan/26행합성/참조/실점수/A는 수행하지 않는다.

각 메모리 작업 전 fresh RAM/기대peak/타작업/추정근거·시각을 기록한다. 이번 정적검토 증분<=256MiB 계획+512MiB 여유, E<=512MiB+512MiB 여유와 host가 병행될 수 있다. peak 실측/안전보장 아님. 부족하면 가능한 다른 작업부터, 보류재개직전 재확인. 청크/순차/동시수 축소 우선, polling/watch/사용자process 종료 금지다.

정적검토 보고서와 manifest/확인해시/명령·실제exit·RAM근거를 audit/에 남긴다. 보고서에는 통과/실패/unknown과 아직 동적검산하지 않은 범위를 구분한다. Round003 E실패(exit2)와 V실패재현감사성공(exit0)을 보존한다. 실제16,384행 결합표단일변환은 batch동등성 증거가 아니며 runner는 stub이다. 실제전체domain/참조/점수/A/membership 없음, round002초기FAIL/deltaPASS10/exit0·역사44해시unknown을 계승한다.

임계값/B/C/사고여부/성능/제출/실제split/사고파일개발사용/외부수집·연락/push 금지. 사고신원/정상근거/개발사용/공식수식 부재를 후보/합의로 대체하지 않는다. task/dispatch 지시에 따라 worker_done으로 정적검토 완료와 남은 동적검산을 보고한다. 감사성공을 생산성공으로 표시하지 않는다.
