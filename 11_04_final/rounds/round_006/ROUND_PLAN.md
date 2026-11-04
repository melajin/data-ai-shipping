# Round 006 — 선택 속성 진단 수정과 고정 2질의 재현

실행 전 동결: 2026-11-04 UTC. 정확한 시작/30분 기한은 manager/model_runtime_evidence.json에 기록한다. 인계 원본은 manager/incoming_NEXT_SESSION.md에 보존한다.

가설: round005 실패는 kv_cache=False에서 존재하지 않는 cache_mode_를 기록한 진단 코드 결함이다. 이 결함을 고치면 원래 모델·문맥·질의를 바꾸지 않고 실제 확률 재현 여부를 판별할 수 있다. 기술 목표는 진단 수정과 재현 증거이며 F1 개선이 아니다. 학습 목표는 선택 속성 부재/None, 문맥 fit/계수학습, 실행/재현/성능 검증을 구별하는 것이다.

작성자는 code/ 및 author_notes.md, 독립 검토자는 review/만 소유한다. 관리자는 manager/·공통 상태·통합 보고서를 소유한다. 모두 원본과 다른 담당자 파일을 변경하지 않는다. 관리자 Astra high와 보조 Luna xhigh 요청/호스트 증거를 분리한다. 관리자+보조2명으로 호스트 총4슬롯 이내다.

변경은 round005 실제 snapshot의 안전한 진단 속성 접근, 존재 여부 기록, fit 반환 직후 stage 저장, ROUND 경로에 한정한다. 역사 freeze schema와 입력은 보존한다. 입력은 검증된 NPZ/freeze 바이트 복사와 SHA 확인만 수행하며 재export/전체 배열 검산은 0회다.

예산: 관리자30분, source 수정1세트와 별도검토, 모델 미로딩 mock1회/30초(실패 시 근거 있는 수정 후1회만 추가), 실제 pilot 최대1회/600초, 큰 계산 동시1개, threads<=3. 실행직전 RAM>=3GiB, 실행중 RAM<1.5GiB면 소유트리만 중단. RAM미달/timeout/API오류 모두 이번 회차 재시도하지 않는다. 기존 환경/체크포인트를 사용하고 설치·다운로드·계수학습·F1·OUTER추론·질의재선정·합성smoke 반복은0회다.

FIT3144 전체, 원INNER 앞2개 [36001915,31703435], seed42, estimators8, batch1, CPU FP32, AMP/FA3false, n_jobs3, offloadauto, kv_cachefalse를 유지한다. COL offload auto, ROW/ICL false와 CPU/AMP/FA3를 검사한다. 진단 mock은 부재와 None 허용 및 잘못된 CPU/AMP/FA3/offload/KV 거부를 확인한다. 모델 forward 검증이라 부르지 않는다.

승인 pilot SHA를 호출부에서 강제하고 wrapper의 immutable snapshot을 실행한다. source/hash/입력/환경/PID생성시각/자원곡선/stdout/stderr/종료코드를 보존한다. checkpoint load1, 문맥fit1, predict_proba1호출만 허용한다. 두 역사확률은 이미 round005에 읽은 개발 INNER 자료이고 라벨은 사용하지 않는다.

재현 판정: finite, [0,1], 행합오차<=1e-5, 클래스순서 일치, 두 질의 모두 최대절대차<=1e-4 및 argmax일치. exact와 tolerance를 구분한다. 실패 시 관찰된 계층과 다음 가설을 변경하며 같은 시도를 반복하지 않는다. 통과해야만 별도 round007 M4-a 계약 검증을 계획한다. 이번 회차에서 확대 실행하지 않는다.

개발 OUTER5897은 반복 노출됐고 현재 채택 기준 micro0.5930133966423605, macro0.5252719738966167은 역사값이다. 독립·공식 점수는 없다. holdout 노출 이력 미해결로 개별 특징/라벨/확률과 전체7372행, Test2025, 원자료는 열지 않는다.

완료 시 ROUND_REPORT, 독립검토, EXPERIMENT_LEDGER, STATUS(current_round=round_006,handoff.ready=true), NEXT_SESSION을 실제 결과로 갱신한다. 실행 가능한 후속은 지정 launcher로 fresh Astra high 세션에 인계하고 수락 영수증을 확인한 뒤 현재 세션을 종료한다.
