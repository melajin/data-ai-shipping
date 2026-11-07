# E 실행 — Round004 제한 정수 도메인 adapter

실제 Orca gpt-6-luna/xhigh 실행자다. provider 내부 모델/effort는 unknown으로 구분한다. 프로젝트 루트 AGENTS.md, testB/USER_DIRECTIVE_20261105.md, ROUND_PROTOCOL.md, STATUS.json, round_004/ROUND_PLAN.md, round_003/NEXT_ROUND.md, ROUND_REPORT.md, execution의 bounded_loader.py/compare_loader_sample.py/preflight_report.md, audit/failure_001/failure_audit.md, round_002/contract/EXPLORATORY_EXECUTION_CONTRACT.md를 UTF-8로 전부 읽는다. ORCA_CLI_COMMAND를 따르고 선택 실행파일의 skills get orchestration/orca-cli 안내부터 확인한다.

수정 소유권은 testB/round_004/execution/ 아래만. 당신 혼자 작업하는 저장소가 아니다. V는 audit/, 감독은 공통/통합 문서를 소유한다. 타인의 변경을 되돌리지 말고 수용한다. 원자료/canonical/cache/선행round 읽기전용이다.

현재 범위: 원본4모듈 pinned SHA와 load_rows/실제 builder 호출의 columns/kwargs를 읽고 제한 정수 도메인 fail-closed adapter를 새로 구현한다. Round003의 단순 batch inference는 기각됐다. ID abs<=2^53/date int32 등의 안전 범위와 ASCII [+-]?[0-9]+ 문법/길이/leading-zero/부호/null/명백한 nonnumeric를 명세한다. 분류가 불확실하면 fail-closed한다. 소수/scientific/공백/overflow/미지원은 임의 제외하지 않고 전체 단계를 중단한다. 원본이 수용하는 값을 임의 삭제하지 않는다. key_valid 우선, 전체 concat ordinal, ID numeric 실패 제외 후 date 검사/제외 순서, 출력 index의 구멍, 값/열/순서/dtype/NaN을 보존한다. 실제 전체 domain은 unknown이다. 열이 요청되지 않은 경우에도 원본 API 의미를 보존한다. 원본 동작을 임의 교정하지 않는다.

작은 신규 fixture에서 원본 load_rows AST를 주입해 비교한다: key_valid_only True/False, 월/배치경계/빈batch/키 누락/leading-zero/부호/NaN/명백한 nonnumeric/2^53 양끝/초과 반례/소수/overflow/미지원 중단/ID 실패행의 date 미검사를 포함한다. 실제 train 표본은 <=16,384행 필수열 투영, batch<=4096. 원본 AST에는 제한 표본을 주입하고 새 경로는 transform_batches를 실제 여러번 호출·batch번호/offset/index를 기록한다. 결합표 transform 한 번을 청크 증거로 쓰지 않는다. unsupported 실제표본이 있으면 stop/보고한다. 참조/점수/전수 key-only scan은 아직 금지다.

RAM: 각 로딩/변환/학습/검산/병렬 전 현재가용/총RAM·기대peak·타작업·추정근거/시각을 기록한다. 이번 경량증분 <=512MiB 계획+512MiB 세션 여유, 보장값 아님. V 정적검토<=256MiB+512MiB 여유와 host가 병행될 수 있다. 부족하면 먼저 문서/코드 등 가능한 작업, 재개직전 다시 확인. 청크/순차/동시수 축소 우선, polling/watch/사용자process 종료 금지. python -B/PYTHONDONTWRITEBYTECODE와 격리 cwd/AST를 사용하고 canonical import/progress 쓰기 부작용을 막는다.

산출물: adapter/검사코드, domain 명세·동등성 논증, fixture와 실제 multi-batch 표본의 값/열/월·물리순서/dtype/NaN/제외/index 결과, 선택범위/배치호출추적, 실제명령/exit/stdout/stderr/입출력해시/RAM/RSS 범위, 차기 key-only scan 사전계약 초안 및 peak 추정. 실패 시 실패를 숨기지 않는다. 이번 task의 코드/fixture 통과는 전체 domain/참조 성공이 아니다.

Round00246,705행 전수Test대조/26행합성 반복금지. E최종exit2/failed와 V실패재현fixtureexit0/감사succeeded, 역사44해시unknown을 보존한다. 임계값/B/C/사고여부/성능/제출/실제split/사고파일개발사용/외부수집·연락/push 금지. 후보/합의/사고미등재를 정답으로 만들지 않는다. 질문은 orchestration ask, 완료는 지정 task/dispatch로 worker_done outcome과 실제 exit/산출 경로를 보고하고 종료한다. 비정상 exit는 수정 후에도 불일치가 남으면 task failed다.
