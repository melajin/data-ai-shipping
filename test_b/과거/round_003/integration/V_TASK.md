# Round003 V — 독립 정적 검토와 동등성 검산 준비

프로젝트 D:/obsidian/claude/obsidian_export/DATA AI SHIPPING. 감독 codex_4269e9a1_ce56_4684_9e30_794fd12ed5b7, Run run_202dfeeb8d64. 실제 Orca gpt-6-luna/xhigh 요청/launch와 provider 내부 모델/effort unknown을 구분한다. 내부 subagent 금지. 다른 작업자가 있으므로 타인 수정 되돌리기 금지. 소유권은 testB/round_003/audit/만이며 생산 execution/공통문서/선행라운드/원자료/canonical/cache는 읽기전용이다.

먼저 AGENTS.md, round003/ROUND_PLAN.md, round002/NEXT_ROUND.md, contract/EXPLORATORY_EXECUTION_CONTRACT.md, execution/preflight_report.md와 isolated_runner.py, scorer_review/scorer_review.md 및 manifest를 UTF-8로 읽는다. ORCA_CLI_COMMAND와 실제 버전 skills get orchestration/orca-cli 안내를 확인한다. 원본 canonical 4개 모듈의 loader/builders 및 해시를 독립 검토한다. E가 execution/에서 bounded numeric loader와 작은 표본 비교를 준비 중이다.

이번 dispatch는 정적 독립검토다. 원본 loader의 열·순서·dtype·key_valid/badnumeric 제외집합 및 batch별 pd.to_numeric의 추론차이/overflow/혼합 문자열·결측·날짜 경계를 검토한다. 모든 builder의 유지배열·전역 cache·정렬/그룹/지도/closure 중첩과 RAM 계획이 충족해야 할 조건을 독립 정리한다. Testfit 차단·원본 알고리즘/라벨/정렬동점 보존·쓰기 격리·pycache/progress 부작용 차단을 확인하는 후속 검산 계획을 작성한다. 실제 코드가 준비되면 후속 dispatch에서 변경범위/동등성/참조/실점수 검산을 맡게 된다. 생산파일은 수정하지 말고 결함을 감독과 E에 보고한다.

이번에는 큰 parquet/원CSV/pickle 로딩·전체train/test스캔·참조생성·실점수·A 실행 금지다. 기존 46,705행 전수대조와26행 합성을 반복하지 않는다. 초기 독립감사 FAIL/exit1과 metadata-only delta PASS10/exit0를 구분하고 역사44해시 최초시점/바이트복원 unknown을 보존한다. 사고파일·외부수집·Testfit·임계값·B/C·사고판정·성능·제출·split·push 금지다.

시작/메모리 작업 직전 가용RAM·예상peak·다른작업·근거·시각 기록. 정적 검토 증분 예상256MiB 이하/세션여유512MiB, E는 작은표본 증분512MiB 한도다. 부족시 다른작업 우선/재개직전재확인, polling/watch/사용자프로세스종료 금지. 근거경로/해시·코드검토와 동적검증의 차이·미확인/실패·실제exit를 audit/에 남긴다. 요청된 정적 검토의 완료를 worker_done으로 보고하되 큰 실행 안전성/전체동등성 pass로 부풀리지 않는다. outcome은 실제 task 성패에 맞춰 보고한다.
