# R: 기존 고정 scorer 독립 코드 검토

당신은 별도 실제 Orca gpt-6-luna/xhigh 검토 실행자다. 감독 Run run_a0639d5ac36a. AGENTS.md, round002 ROUND_PLAN, round001 NEXT_ROUND, 26_11_5/testb_next_experiment_20261105/contract/preparation_contract.md와 필요한 기존 보고/코드를 UTF-8로 읽는다. 실제 설치버전 orchestration 가이드를 먼저 읽고 worker_done으로 보고한다. 모델 요청/Orca launch/provider 내부unknown을 구분한다.

소유권은 testB/round_002/scorer_review/뿐이다. 혼자 작업하는 것이 아니므로 타인 변경을 되돌리거나 공통문서를 수정하지 않는다. P는 preparation/를 소유한다. canonical D:/repos/fishing-track-classification, 기존캐시/원자료/이전라운드는 읽기전용이다.

목표는 정확한 기존 점수함수·성분/가중치·floor·결측·동점·시간·원행순서와 참조/지도/KDE/스케일러/군집/분위수의 생성 경로·적합대상을 코드와 보존manifest로 독립 추적하는 것이다. rg로 필요한 파일을 좁힌다. 2025 Test 데이터가 적합·보정에 쓰였는지, 고정참조 membership과 Test 적합을 구분한다. 알려지지 않은 근거를 안전하다고 가정하지 않는다. 호출 그래프와 입력/출력/부작용, 고정출력경로, 2025 새100척 전체항적 추론의 조건부 가능/불가/unknown을 근거 경로·줄번호·해시로 보고한다. 기존 최고점A와 round001 timing 계약 연결도 확인한다. 수정/새점수/모델/캐시생성·대용량 로딩·전체CSV재해시·임계값/사고판정/B/C/제출/외부연락 금지.

경량 코드·문서 조사 증분 예산256MiB. 시작에 RAM·병행 작업·시각과 예상peak 근거를 기록하고 부족하면 다른 작은 작업 후 재개직전 재확인한다. streaming/순차 우선, 반복polling/프로세스종료 금지. 산출물 scorer_review.md, manifest.json, 함수/참조 계보표·입력코드해시·환경/실제검사exit. 검증을 실행하지 않았으면 미실행으로 적는다. 사고 신원·정상근거·개발사용/분할 미확보 때문에 성능을 만들지 않는다. 성공 판정 전에 반드시 필요한 증거와 추론 contract 권고를 감독에게 보고한다. 감독이 나중에 별도 생산/독립 계산검산을 위임한다.
