# Round 009 — ROW 독립 배치 분할의 합성 의미 보존

실행 전 동결: 2026-11-04 19:06 UTC. 관리자 시작 19:04:46 UTC, 종료 목표 19:34:46 UTC(30분). 정본 세부 계약은 manager/incoming_NEXT_SESSION.md이며 SHA256 E25792729E88990F4AAC412F0219D8C9F2E39E1DEE7A2A1C7F207480A6A793DA다.

## 이전 → 현재

round008은 첫 컬럼 호출 14청크 완료 후 RAM 관문으로 중단됐고 예측은 반환하지 않았다. 정확한 중단 연산은 미확정이다. 이번에는 실제 재현을 반복하지 않고 ROW의 독립 배치축 분할을 소스·mock·작은 합성 비교로 검증한다.

가설: ROW에서 B,T는 독립 배치축이고 feature/register token은 attention sequence이므로 T chunk8이 수치 의미를 유지한다. ICL에서 T는 전체 FIT/query 문맥이므로 분할하지 않는다. 소스 독립성을 입증하지 못하면 구현 실행을 중지하고 미해결 계약을 남긴다.

## 고정 비교와 판정

- numpy default_rng(20261105), 표준정규 float32 FIT32×312/query2×312, y=tile(arange(4),8).
- 기존 checkpoint SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0, 110368038bytes. TabICL2.2.0/Torch2.6.0+cpu, seed42/estimators8/batch1/n_jobs3, CPU FP32, AMP/FA3/KV false, offload auto, 다운로드 false, native10 head/활성4클래스 유지.
- checkpoint1, context fit1, 동일 estimator predict_proba 총2회: baseline column16+원ROW, candidate column16+row8. 내부 8estimators의 기존 호출 구조 보존. 추가 forward/predict/재시도 없음.
- 입력 shape/dtype/hash, shuffle 불변; 클래스 [0,1,2,3]; 2×4 확률 finite/[0,1], 행합오차≤1e-5; 최대절대확률차≤1e-5 및 두 argmax 일치. exact와 tolerance 별도. 실패 후 허용오차 변경 금지.
- column adapter는 round008 검증본 바이트복사. COL_CONFIG를 fit 직후 원관리자에 configure하고 설치. baseline 뒤 configured 원ROW를 candidate용 로컬 어댑터로 감쌈. 원관리자 _prepare_inputs/_run_forward/CPU/no_grad/AMP 의미 유지. 미인식 tensor 거부, output_repeat와 짧은 마지막 chunk/순서/설정 전달/복원 검사.

## 실행·메모리·소유권

관리자 Astra high 요청/호스트 turn_context 일치 기록은 manager/manager_model_evidence.json에 있다. 이는 내부 모델 인증이 아니다. 보조는 author009/review009 각각 Luna xhigh 요청, fork none. 총3슬롯≤호스트4, 보조2≤사용자4. 작성자는 code/*와 manager/run_bounded.py 및 author_notes, 검토자는 review/*와 승인manifest, 관리자는 계획·실행·공유 상태 담당. 타인 수정 되돌리기 금지.

합성 pair 최대1회/총300초(정리10 포함), puremock1회≤30초+결함수정 후1회만. 계산동시1/threads≤3. 실행 전 RAM≥3GiB, 실행 중<1.5GiB이면 PID+생성시각+실행상태 일치하는 소유트리만 종료. 사용자 프로세스 종료 없음. round007 합성 sampled peak 약0.73GiB를 근거로 새 경로 예상1–2GiB(미측정)이며 실행직전 실제 RAM·다른 계산을 기록한다. 시작 점검 약3.77GiB/관련 Python 계산0. 정적작성/검토는 각 수MB 텍스트 작업, 모델·대형배열 로딩 없음. 부족하면 소스/후속설계/문서 검산 후 재확인하며 RAM polling 루프 없음.

원자료·이전저장소·과거회차·venv 읽기전용. 모든 새 파일/temp/cache는 round009 아래. 실제 배열·확률·NPZ·OUTER·holdout·M4·새 계수학습·F1·공식제출·외부 업로드0. 실행 전 source 승인 및 mock 통과 필요. source/hash/snapshot/환경/PID/종료/RAM/단계진입·완료를 저장한다.

## 기술·학습 목표와 후속

기술 목표는 ROW 독립성 근거, mock 계약, 합성 확률 의미 보존이다. 작은 합성 통과를 실제 전체문맥 메모리 절감이나 F1 향상으로 해석하지 않는다. 학습 목표는 컬럼축·ROW 배치축·ICL 문맥축, 종료/복원, exact/tolerance 차이를 설명하는 것이다. 설명 질문: 왜 ROW의 T는 자를 수 있으나 ICL의 T는 자를 수 없는가? 합성 동등성이 실제 F1을 보장하지 않는 이유는? 강제종료 시 finally는 어떻게 해석하는가? 학습자의 이해와 하드웨어 동작은 미측정이다.

성공 시 다음 별도회차의 고정 실제 FIT3144/INNER2 col+row bounded 재현을 설계한다. 실패 시 수치/설정/shape/자원 계층을 구분해 다른 가설로 전환한다. 같은 실제 중단을 무변경 반복하지 않는다. 채택 개발기준0.5930133966423605/탐색미채택0.5933525521451586, 독립·공식점수 null 유지. 결과·공유문서·구체적 NEXT를 갱신하고 fresh Astra high 수락영수증 확인 후 현재 세션 종료.
