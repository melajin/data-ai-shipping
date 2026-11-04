# Round003 E — bounded loader 동등성과 단계별 RAM 계획

프로젝트 D:/obsidian/claude/obsidian_export/DATA AI SHIPPING. 감독 codex_4269e9a1_ce56_4684_9e30_794fd12ed5b7, Run run_202dfeeb8d64. 요청·Orca launch gpt-6-luna/xhigh, provider 내부 모델/effort unknown으로 구분한다. 내부 subagent를 만들지 않는다. 다른 작업자가 함께 있으므로 타인 수정 되돌리기 금지. 오직 testB/round_003/execution/의 파일·코드·scratch·로그를 소유하며 공통문서/선행라운드/원자료/canonical/기존cache는 읽기전용이다.

먼저 AGENTS.md, round003/ROUND_PLAN.md, round002/NEXT_ROUND.md, contract/EXPLORATORY_EXECUTION_CONTRACT.md, execution/preflight_report.md와 isolated_runner.py, scorer_review/scorer_review.md 및 code_review_manifest 관련 해시, preparation manifest를 UTF-8로 읽는다. ORCA_CLI_COMMAND를 따라 실제 skills get orchestration 및 orca-cli 안내를 읽는다. 원본 canonical 4개 모듈 코드와 load_rows/train schema/footer/parse 계보를 조사한다. 원본 해시 불일치면 중지·보고한다.

할 일: 원본 numeric 변환·key_valid 필터·badnumeric ID/date 제외·rfid_id:int64/part_dt:int32/month:int8·나머지 dtype·열/행순서를 보존하는 bounded loader와 harbor/density/gap 순차 단계 계획을 만든다. 공통참조 계산 규칙·상수·라벨·정렬동점·집합을 바꾸지 않으며 기존 순수함수 재사용을 우선한다. 전역 cache/배열·정렬/그룹/지도·closure 보유와 단계 중첩을 코드 근거로 산정한다. 사전할당/mmap/scratch와 cache 해제를 검토하고 모든 단계의 예상 peak 및 여유/불확실성을 명시한다. 2GiB 초기 추정을 보장값으로 쓰지 않는다.

구현이 가능한 범위에서 새 loader/격리 실행 코드를 작성하되 큰 실행 관문은 default deny로 둔다. 정확 선택범위를 기록한 실제 train 표본 최대16,384행과 새 loader 경계 합성에서 원본 loader 연산과 새 loader의 열·순서·값·NaN·dtype·제외집합을 비교한다. 원본 전체 load_rows는 호출하지 말고 작은 표본을 안전하게 주입하여 원본 변환 경로를 재사용/AST 추출한다. 배치별 pd.to_numeric dtype 추론/혼합 문자열·부호·overflow/leading-zero·결측·날짜 등으로 전체변환과 달라질 가능성을 검토한다. 표본 통과를 전체 동등성 증명이라 부르지 않는다. 기존 46,705행 전수스캔/26행 점수 합성은 반복하지 않는다.

지금은 전체 train 참조/전체train 중복로딩/실제 새100척 점수/A/membership 전수 생성 금지다. 추론 후속의 정확 명령·출력경로·파라미터·해시·memory gate와 필요한 독립검산을 제안하고 worker_done으로 보고한다. 사고파일·Testfit·보정·임계값·B/C·사고여부·성능·제출·외부수집·push 금지. stockCLI/main/stage 금지, canonical import의 pycache/progress 쓰기를 차단한다.

RAM 규칙: 시작과 표본/변환 등 메모리 작업 직전에 현재 가용RAM·예상peak·다른 작업·추정근거·확인시각을 기록한다. 현재 E 경량 증분 예산512MiB/별도 세션 여유512MiB이며 V는 정적검토 중이다. 예상초과나 부족시 중지하고 작은 독립작업을 먼저 한다. 보류재개 직전 다시 확인하고 polling/watch·사용자process종료 금지. 순차실행·청크·동시수축소 우선. 실제 exit/stdout/stderr/명령·해시·변경범위·실패와 미실행을 보존한다. 주요 비교 실패/비0 exit는 실패로 보고하며 숨기지 않는다. 결과 report와 machine-readable summary 및 실행 영수증을 execution/에 남기고 반드시 injected task/dispatch에 worker_done outcome을 보낸다.
