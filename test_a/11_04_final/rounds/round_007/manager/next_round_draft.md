# 조건부 Round 008 설계 초안 — 아직 실행 승인/최종 인계 아님

이 문서는 round007 소스/mock/합성 비교가 모두 통과한 경우에만 최종 NEXT_SESSION으로 승격할 초안이다. 실패하면 원인을 반영해 변경하며 이 초안만으로 계산을 실행하지 않는다.

## 다음 변경 변수

round006의 동일 FIT3144/고정 INNER2 재현에 round007 컬럼chunk16 어댑터만 추가한다. 원경로 전체문맥 재추론은 하지 않는다. 모델 head/estimators/precision/전처리/질의/문맥/확률허용오차를 바꾸지 않는다. 새 계수학습·F1·OUTER·보호자료 접근은0회다.

## 필수 시작 자료

AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round007 ROUND_REPORT·author_notes·review/FINAL_REVIEW·artifacts/synthetic_pair_result·logs/pair_01/receipt와 round006/manager/incoming_NEXT_SESSION.md를 읽는다. round007 수신영수증의 세션/해시를 확인한다. 이전 저장소와 원자료는 읽기 전용. 모든 새 파일/temp/cache는 round008 아래다.

## 입력·환경 동결

재export/전체재검산0회. round006/artifacts/context_export_attempt_001/fold0_seed42_context.npz SHA9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5 및 query_freeze.json SHA6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef를 바이트복사·stream해시 확인한다. 고정ID[36001915,31703435], ordered digest7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969. y_inner 접근 금지. 참고 export_result와 round005 독립입력검산은 읽기 전용 근거다.

기존 environments/round_004_tabicl_cpu/Scripts/python.exe, TabICL2.2.0/Torch2.6.0+cpu, checkpoint110368038bytes/SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0. seed42/8estimators/batch1/CPU FP32/AMPfalse/FA3false/n_jobs3/offloadauto/KVfalse/다운로드false. native10출력head와 활성4클래스변환 유지.

## 구현 관문

작성자·별도검토자는 Luna xhigh/fork_turns=none, 관리자는 Astra high; 요청/host증거 구분. round006/code/replay_inner_pilot.py를 새 round008/code로 복사해 round경로와 어댑터 설치·복원·event기록만 수정한다. 입력 freeze 역사schema는 무차별 치환하지 않는다. round007 검증 adapter는 SHA를 묶어 복사한다. ROW/ICL·전역클래스·venv 불변.

중요: `fit()` 직후 원컬럼관리자는 아직 configure되지 않아 기존 adapter 설치조건을 충족하지 않을 수 있다. 원경로 predict를 먼저 호출하지 말고, pinned embedding.py와 동일하게 `original_col_manager.configure(**estimator.inference_config_.COL_CONFIG)`를 호출한다. resolvedCPU/AMP/offload조건을 검사한 다음 설치한다. 실제 ColumnEmbedding은 호출 때 같은configure를 다시 수행한다. 이 순서의 의미/동일설정을 별도소스검토하고 pure mock으로 fit상태→configure→install→call→finally restore를 검증한다. 설치 시점에 임의설정을 추가하지 않는다.

mock1회≤30초(결함수정후1회추가만). 소스/SHA/검토/mock 관문 후 실제 추론1회≤600초, 생성부터 종료확인까지(마지막10초cleanup 예약). checkpoint load1/문맥fit1/predict_proba1; 큰계산동시1, threads≤3. 시작RAM≥3GiB, 실행중<1.5GiB면 소유PID·생성시각 일치트리만 중단. 실행 시작후 재시도0회. 관리자30분.

## 판정·분기

입력/freeze/ID검사 후 이전 공유P/evaluation/seed_42/fold_0/inner_predictions.csv의 헤더와 처음2행 p0..p3만 읽는다. ID불일치 시 검색·대체하지 않는다. INNER레이블·다른확률행을 읽지 않는다. 두확률2×4 finite/[0,1]/행합오차≤1e-5/클래스[0,1,2,3], 역사 원확률대비 최대절대차≤1e-4 및 두argmax일치. exact/tolerance 구분. 재호출·허용오차확대 금지.

동작·차이·RAM·시간·실제chunkshape·소유PID종료·복원을 기록한다. 작은합성의 메모리 사용량으로 전체문맥 절감을 보장하지 않는다. RAM부족 시 다른독립작업 후재확인, 이전실패와 비교하고 단순 polling 금지. 실패 시 단계/자원/수치오류를 분리해 가설변경; 실행불가 외부제약이면 정확한 재개조건을 남긴다. 실제재현통과 전 M4-a 금지; 통과해도 M4-a는 별도 bounded설계다.

계절 가설은 round007/SEASONAL_FEATURE_INVENTORY.md를 보존한 별도후속후보로 유지한다. 현재재현에 특징을 추가하지 않는다. 개발/독립/공식 점수 분리, 목표0.7미달이며 미측정성능을 만들지 않는다.
