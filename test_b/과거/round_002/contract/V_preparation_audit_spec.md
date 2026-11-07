# V: 실제 선별행·수정runner 독립 검산

별도 실제 Orca gpt-6-luna/xhigh 독립검산자. Run run_a0639d5ac36a. 설치버전 orchestration guide, AGENTS.md RAM규칙, round002 ROUND_PLAN, contract/EXPLORATORY_EXECUTION_CONTRACT.md와 E_FIX_REVIEW, preparation/와 scorer_review/ 및 execution/ 보고/manifest를 UTF-8로 읽는다. 요청/Orca launch와 provider내부unknown을 구분한다. worker_done에 pass/fail/unknown·실제exit를 보고한다.

소유권은 testB/round_002/audit/preparation_001/만. 생산코드/공통파일 수정 금지. 다른 작업자가 함께 있으므로 타인 변경을 되돌리지 않는다. 원자료/canonical/기존캐시/생산 execution/는 읽기전용. import/py_compile/테스트가 execution/__pycache__ 또는 canonical에 쓰지 않게 PYTHONDONTWRITEBYTECODE/별도pycache를 설정한다. validator와 logs/결과는 자기 폴더에만.

독립 범위:
1. 정확100개 명부 원문·순서/중복/원ZIP member/intake/prior source rows 계보와 P/E 해시를 비교한다. 작은 workbook 직접비교는 허용. 13GB재해시/CSV재파싱/legacy score loading 금지.
2. selected_rows6파일을 독립읽기(46,705행)하여 raw/valid/scorable/월·대상/범위/finite/중복/sourceordinal와 target_row_summary를 전수비교한다. YYYYMMDD 실제달력과hour0..23/key_valid도 검증한다. 기존4,212,389행 중 누락·비대상혼입을 확인하려면 source parquet를 batch16384·필수열투영으로 독립스캔하여 ID선별/row_index/전체카운트·선택행값을 비교한다. 메모리<=512MiB 예상에서 streaming hash 또는 월별선별값 비교를 사용하고 전역 DataFrame concat 금지. 원CSV/WKT 정확성은 이 검산의 범위밖이다.
3. 고정원본해시/AST추출/생산shim·trainfit경계·output격리·회원명부 unpack/leading0·A원입력동점·동시간충돌·floor/결측을 독립적으로 검토한다. 생산자의 self-check를 그대로 재실행하는 것을 독립검산으로 대체하지 않는다. 별도작성한 합성 fixture로 다행 haversine 실제경로와24행전후 s_change/state 경로, A동점·중복충돌·결측을 확인한다. 가능한 경우 독립 scalar 식으로 score성분을 대조한다. synthetic reference만 사용하며 실제train참조/새100척점수 생성 금지. 생성함수의 미실행 참조경로는 정적검토 한계를 표시한다.
4. 수정전손상/실패로그 보존, 최신UTF8/manifest의 현재hash와 legacy hash를 구분, 실행exit·실제scan과미실행을 검증한다. source stat/hash검사범위와 검사중 생산파일불변을 기록한다. 늦게 발견한 결함은 자기 audit보고서에만 남겨 감독에게 수정요청한다.

RAM 시작/메모리작업직전 available/예상peak/병행작업/시각/근거 기록. 본 검산 증분<=512MiB 예상, session 여유512MiB 별도. 부족하면 작은코드/계약검토 먼저, 재개직전재확인; 청크/순차 우선, 반복polling/사용자process종료금지. 큰train참조/점수는 병행하지 않는다. peak 실측과 batch RSS표본을 구분한다.

deliverables: audit_report.md(읽기쉬운 UTF8), review.json(pass/fail/unknown+근거), independent validator code, environment/RAM, stdout/stderr/실제exit, hash manifest. 실제사고정답/정상근거/개발사용/임계값/분할/성능/provider내부모델은 unknown이며 성능인증을 하지 않는다. 검산실패는 nonzero와 fail로 보고하고 성공으로 덮지 않는다.
