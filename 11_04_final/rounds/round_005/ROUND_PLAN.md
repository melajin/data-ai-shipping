# Round 005 사전 계획

관리자 시작: 2026-11-04T17:22:32Z. 관리 종료 상한: 17:57:32Z (35분).
관리자: codex_505bd45f_37f4_4824_b7ff_6d9075c223fa. 요청 gpt-6-astra/high, host turn_context도 동일 보고. 이는 호스트 설정 증거이며 모델 내부 인증은 아니다.

## 목적과 가설

원래 순서의 fold0 개발 입력을 복구하면, 동일 체크포인트와 설정의 CPU 추론이 고정된 INNER 첫 2척의 과거 CUDA 원확률을 허용오차 내에서 재현하는지 확인할 수 있다. 변경 조건은 장치(CUDA→CPU)와 질의 묶음(787→2)이다. 새 성능 개선이나 계수학습은 하지 않는다.

기술 목표는 순서 있는 입력·클래스·결측 변환과 소수 질의 추론의 검증이다. 학습 목표는 입력값/행순서/확률 재현/분류 성능을 구별하고 자원 관문의 이유를 설명하는 것이다. 학습자의 이해 달성은 별도 미평가 상태다.

## 동결 범위

- round004 인계 SHA256: 5C97CEF4DF735D23F79C8399FC1FD4A5AA755EC84ED16701FC51E83CEAD695C3. 보존사본과 현재 문서 모두 일치하며 인계 receipt 수신 ID는 현재 ORCA_AGENT_SESSION_ID와 같다.
- export 최대 1회 + 근거 있는 수정 1회, 각각 프로세스 생성부터 60초. 독립 배열 검산 1회.
- pilot 최대 1회, 프로세스 생성부터 600초. FIT 3144 전부, 원INNER 순서 첫 2개 ID 고정, seed42, 8 estimators, batch1, threads≤3, CPU FP32, AMP/FA3/자동다운로드 비활성.
- 실행 직전 RAM≥3GiB, 실행 중 가용 RAM<1.5GiB면 해당 자식만 종료. 동시 큰 계산 1개. 다른 사용자 프로세스 종료 금지.
- checkpoint load 1회, 문맥 fit 1회, predict_proba 1호출. 새 계수학습/F1/OUTER 추론/추가 smoke/설치/다운로드 0회.
- fold0 개발 NPZ와 허용 source/metadata만 읽는다. holdout ID metadata는 분리 검사만 허용. holdout 특징·라벨·확률, 전체 7372행 표, Test2025, 원자료는 열지 않는다. 이전 저장소와 공유자료는 읽기 전용.
- query IDs를 먼저 저장·해시 고정한 다음 해당 2개의 과거 원확률 p0..p3를 읽는다. INNER 정답은 모델에 전달하지 않는다.

## 인수조건과 실패 분기

입력: 고정 NPZ 해시, manifest와 frozen rule/parent fingerprint 연결, fold0 역할/라벨/열/클래스, FIT/INNER/OUTER 상호 분리 및 dev/holdout 비중첩, 원INNER ordered digest 단 1회 비교를 통과한다. saved median156과 원결측156으로 float32 312열을 복구한다. 독립 검토자는 원NPZ에서 배열·순서·멤버십·클래스와 결측/대치 예시를 재계산한다.

pilot: 유한값/범위/행합/클래스순서 검사를 통과하고, 두 질의 각각 과거 원확률 최대절대차≤1e-4와 argmax 일치를 모두 충족하면 작은 재현 관문 PASS. bitwise와 tolerance 일치는 구분한다. 이것은 F1 또는 성능 채택 판정이 아니다.

입력 실패 시 pilot 0회. RAM 미달/timeout/API 오류/확률 불일치 시 동일 회차 pilot 재시도 0회. 소스/입력 해시, PID, 시각, 종료코드, stdout/stderr, 단계별 결과와 RAM곡선을 보존한다. 다음 가설은 확인된 실패 계층을 좁히며 동일 무정보 실험을 반복하지 않는다.

## 역할과 산출

- 관리자: 계획·모델 실행 승인/실행·공유 상태/보고/인계 통합.
- round005_author: gpt-6-luna/xhigh/fork_turns=none. code/와 author_notes.md 전담, exporter/pilot 실행 금지.
- round005_reviewer: gpt-6-luna/xhigh/fork_turns=none. review/ 전담, 사전검토·독립검산·최종검토. 작성 코드 수정 금지.
- 관리자 포함 동시 3슬롯, 호스트 허용 총 4슬롯 내. 모든 새 산출·temp/cache/offload는 작업루트 안.

완료 시 ROUND_REPORT.md, EXPERIMENT_LEDGER.csv, STATUS.json(current_round=round_005, handoff.ready=true), NEXT_SESSION.md를 실제 결과로 갱신한다. 실행 가능한 다음 작업이 있으면 승인된 Start-NextSession.ps1로 새 Astra high에 인계하고 수락 영수증 확인 후 종료한다.
