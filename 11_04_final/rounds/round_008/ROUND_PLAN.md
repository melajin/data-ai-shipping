# Round 008 실행 전 고정 계획

변경 변수: round006 고정 FIT3144/INNER 앞2질의에 검증된 column chunk16만 적용한다. round007 합성 동등성 이후 실제 확률 재현을 확인한다. 모델/문맥/질의/정밀도/확률허용오차 불변. F1, OUTER, holdout, 원자료, 전체7372행, Test2025 접근 및 계수학습은 0회.

- 관리자 30분. 순차 큰 계산1개, threads≤3. pure mock1회≤30초, 결함수정 후 추가1회만. 실제 pilot1회≤600초(정리10초 포함), 재시도0. checkpoint1/fit1/predict1.
- 시작RAM≥3GiB, 실행중<1.5GiB이면 PID/생성시각 일치 소유트리만 종료. 사용자 프로세스 종료 금지. 부족하면 소스/계절후속설계/문서검산 후 실행 직전 재확인. 단순 polling 금지.
- 입력 바이트복사 및 streaming SHA 확인만, 재export/전체재검산 없음. y_inner 금지. ID/입력계약 확인 후 역사 CSV 헤더와 첫2행 p0..p3만 읽기.
- finite/범위/행합오차≤1e-5, 클래스[0,1,2,3], 역사확률 최대절대차≤1e-4 및 두argmax일치. exact와 tolerance 별도. 실제재현 통과 전 M4 금지.
- 원관리자.configure(**estimator.inference_config_.COL_CONFIG) → resolved CPU/AMP/offload 검사 → adapter설치 → 단한번predict → finally복원. pinned embedding configure 계약과 별도mock 확인. 전역/ROW/ICL/venv 불변.
- 이전 실패는 원경로 추론 RAM급증. chunk16의 전체문맥 peak는 미확인이다. 임시 계획 추정 1–4GiB 이상 가능: 작은합성 약0.73GiB + 3146문맥 컬럼중간배열 및 ROW/ICL. 원행렬 크기만으로 추정하지 않는다. 안전감시가 필요하며 시작가용량은 성공보장이 아니다.

담당: 관리자=공유계약/입력복사/실행/최종보고/STATUS/LEDGER/NEXT. Luna 작성자=code/* 및 manager/run_bounded.py, author_notes.md. 별도 Luna 검토자=review/* 및 승인manifest(manager/approved_sources.json). 다른 담당자 변경을 되돌리지 않는다. 모든 새 산출/temp/cache는 round008. 원본/과거회차는 읽기전용.

기술목표: 고정 실제확률 재현 또는 자원/수치/진단 실패계층의 증거 확보. 학습목표: 합성동등성·실제재현·F1과 계산축/메모리병목 구분. 학습자 설명 질문: 컬럼 분할은 왜 문맥 분할과 다른가? 두질의 일치로 F1을 주장할 수 없는 이유는? 학습자의 이해와 하드웨어 동작은 측정하지 않는다.
