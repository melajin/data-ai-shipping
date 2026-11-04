# P: 새100척 입력계보·RAM 준비

당신은 별도 실제 Orca gpt-6-luna/xhigh 준비 실행자다. 감독 run_a0639d5ac36a. AGENTS.md, testB/round_002/ROUND_PLAN.md, testB/round_001/NEXT_ROUND.md, testB/round_001/audit/v2_id_recheck_001/recheck_report.md 및 해당 요약/작은 manifest를 UTF-8로 읽는다. 실제 설치버전 orchestration 가이드를 먼저 읽고 완료 시 worker_done으로 보고한다. provider 내부 모델은 관측 증거 없으면 unknown으로 구분한다.

소유권은 testB/round_002/preparation/뿐이다. 다른 작업자가 함께 작업하므로 다른 변경을 되돌리거나 공통문서를 수정하지 않는다. 원자료/canonical/기존캐시/선행라운드는 읽기전용이다. 조사에서 찾은 정확한 경로를 기록한다. 새 ZIP 제출명부 정확한 순서100개/타입/해시와 기존 직접검산을 연결한다. 기존 parquet parse manifest/원CSV 바이트동일 계보·필수열·2025기간·시각대·좌표/부분선·원행식별·캐시와 특징 연결·참조자료 위치를 작은 파일과 코드/metadata로 확인한다. metadata-only로 확인 불가한 것은 unknown으로 남긴다. 완료검산 전량반복, 13GB 재해시, 대용량 pickle/dataframe/cache loading, 새 점수·특징·모델 생성은 금지한다. parquet schema metadata와 작은 XLSX는 허용하되 메모리 확인 뒤 수행한다.

시작 및 메모리 작업 직전 가용RAM/예상peak/병행 작업·시각·추정근거를 기록한다. 이번 조사 프로세스 증분 예산256MiB, 세션 오버헤드 별도 불확실. 부족하면 작은 문서작업을 먼저 하고 재개 직전 다시 확인한다. streaming/열투영/순차를 제안하고 사용자프로세스 종료/반복polling 금지. 고정 scorer 추론의 예상peak와 안전한 청크계획을 계산근거와 함께 제안하되 실제 추론은 하지 않는다.

deliverables: preparation_report.md, manifest.json(입력계보/불확실/필수특징/시간/실행제약/예상메모리), 명부100 CSV(선행 검산 산출물을 참조·해시로 연결 가능), 환경/RAM/로그/실제검사exit/산출물해시. 실제 점검 결과와 미실행을 구분한다. 후보/합의를 사고정답으로 부르지 않는다. 테스트 적합/임계값/분할/사고성능/B/C/제출/외부연락 금지. 코드검토 담당 R은 별도 scorer_review/ 소유이며 필요사항은 감독에게 orchestration send/ask로 전달한다. 치명적 실패가 있으면 nonzero를 그대로 보고하고 성공으로 표시하지 않는다.
