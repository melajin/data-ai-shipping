# Round 010 실행 전 계획

관리 시작 2026-11-04 19:34:41 UTC; 종료 상한 20:04:41 UTC(30분). 이번 단계는 본인 학습자용 재현·자원 진단이며 성능 채택 실험이 아니다.

## 가설과 고정 범위

round009의 합성 의미 보존을 통과한 column16+row8 어댑터를 함께 적용하면 고정 실제 FIT3144×312 및 INNER 두 질의의 기존 확률을 허용오차 안에서 재현할 수 있다. 원래 ROW의 T는 독립 배치축이며 ICL 전체 T는 문맥축이므로 그대로 유지한다. 변경 변수는 기존 실제 column16 경로에 검증된 row8 추가와 기존 호출의 ROW/ICL 경계 계측이다. 기존 CPU FP32, seed42, estimators8, batch1, threads3, AMP/FA3/KV false, offload auto, 입력/클래스/head/정밀도를 고정한다.

checkpoint1/context fit1/predict_proba1만 허용한다. 원경로 재실행0, 추가 forward0, 계수학습0, M4/OUTER/holdout/F1/원자료 읽기0. 실제 입력은 이미 승인된 development context를 바이트복사한 두 파일뿐이다. 고정 ID [36001915,31703435]를 바꾸지 않는다. historical reference는 round008 P 정의의 evaluation/seed_42/fold_0/inner_predictions.csv에서 header와 첫 두 행의 ID,p0..p3만 기존 reader로 사용하고 라벨은 해석하지 않는다. 행 byte에 미해석 다른 열이 포함될 수 있음을 기록한다.

입력 NPZ SHA256 9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5(1916394bytes), query_freeze 6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef(748bytes). 복사 대상 round010/artifacts/context_export_attempt_001. 두 어댑터는 round009 승인본을 바이트복사하고 SHA 고정한다.

## 단계·검증·실행 한도

1. 작성자와 독립 검토자는 각각 Luna xhigh/fork none. 작성자는 code/*, manager/run_bounded.py, author_notes만; 검토자는 review/*만; 관리자는 나머지 문서/입력/실행/공유 상태를 소유한다. 다른 담당자의 수정은 보존한다. 소스 검토와 승인 manifest를 동결한다.
2. 순수 callable mock 1회≤30초; 결함 수정 후 최대 1회 추가. COL/ROW 설정 전달, 공존·복원, tail/순서/미인식 tensor 거부를 확인한다. 모델/실제 자료를 로드하지 않는다.
3. 동일 승인 SHA map의 mock 통과 후 실제 재현 1회≤600초(계산590+정리10), 재시도0. 한 번에 큰 계산1, threads≤3. 시작 직전 RAM≥4GiB; 실행 중 <1.5GiB이면 소유 PID/생성시각/실행상태를 확인해 정리한다. exact Popen handle fallback과 미확인 자손 unverified 보존을 유지한다. 사용자 프로세스는 종료하지 않는다.
4. 통과: finite/[0,1]의 2×4 확률, 클래스[0,1,2,3], 행합오차≤1e-5, historical reference와 maxabs≤1e-4, 두 argmax 일치, 입력·shuffle 불변. exact와 tolerance를 분리한다. 복원/호출횟수/소스불변/소유트리 종료도 확인한다. 실패 후 허용오차 완화·질의 교체·재실행은 금지한다.

ROW와 COL은 fit 후 원관리자에 resolved config를 configure한 뒤 설치한다. 모든 설치 이후 진단을 try/finally로 보호하고 복원을 기록보다 먼저 수행한다. ROW/ICL 계측은 원래 호출 안에서만 기록한다. source 객체와 configure_source를 분리한다.

## 메모리·실패 분기

최초 Windows 조회 가용 RAM 약4.23GiB, 실행 중인 Python 없음. 새 경로 전체 peak는 미측정이다. round008 중단 sampled peak 약2.96GiB는 실제 요구 상한이 아니다. full column embedding은 대략1×3146×316×128×4≈486MiB이며 복사/잔존 output/ICL attention·runtime을 포함하지 않는다. 시작4GiB 관문은 안전 보장이 아니므로 runtime 감시를 유지한다. pure mock 예상50MiB, 소스 검토·문서작업은 수 MiB 수준이다.

RAM 부족 시 먼저 소스계약/문서/계절 metadata 근거를 검토한 뒤 실행 단계에서 재확인한다. polling/watch를 만들지 않는다. 대체작업 후에도 부족하면 정확한 재개조건을 남기고 RAM 조회만 하는 새 세션을 시작하지 않는다. 실행 실패 시 마지막 COL/ROW/ICL 경계와 자원/수치/설정 계층을 구분하고 바뀐 가설만 다음 회차로 이관한다. 성공해도 M4는 자동 실행하지 않으며 후속 별도 회차에서 평가계약·자원·선택규칙부터 검토한다.

## 목표·학습·산출

기술 목표: 두 고정 실제 질의 확률 재현과 병목 경계 확인. 학습 목표: 합성 통과와 실제 재현/F1의 차이, 독립 배치축과 문맥축, exact/tolerance, sampled peak 한계를 설명한다. 질문: 왜 ICL의 T를 ROW처럼 자를 수 없는가? 두 질의 일치가 5897척 F1을 증명하지 않는 이유는? 조건·예상·계산값·해석을 보고서에 기록한다. 학습자의 이해와 장치 실험은 측정하지 않는다.

기존 개발 OUTER5897 baseline micro0.5930133966423605, 탐색미채택0.5933525521451586, 독립/공식null. 이번 회차에는 새 F1이 없다. 완료 시 ROUND_REPORT, STATUS(current_round=round_010, handoff.ready=true), EXPERIMENT_LEDGER, NEXT_SESSION을 갱신하고 실행 가능한 후속이 있으면 지정 launcher의 수락 영수증을 확인한 뒤 중지한다.
