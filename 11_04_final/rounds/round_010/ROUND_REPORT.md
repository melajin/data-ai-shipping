# Round 010 — 실제 두 질의 수치 재현 통과, 소스 동결 위반

고정 FIT3144×312/INNER2에서 COL16+ROW8의 확률 최대절대차는 **1.8446231598301388e-6**로 사전 허용오차1e-4를 통과했다. argmax[0,1]도 일치했고 exact equality는 false다. 그러나 실행 중 wrapper가 수정되어 전체 실행관문은 실패했다. 새 F1은 없으며 목표0.7은 미달이다.

## 이전 → 현재 → 다음

round008 실제 재현은 첫 COL 완료 후 RAM 중단으로 끝났고, round009는 tiny합성 의미보존을 통과했다. 이번에는 검증된 ROW8을 실제 문맥에 추가해 전체 ROW/ICL과 최종확률을 얻었다. 다음 round011은 모델을 다시 돌리지 않고 출처검산·동결절차 보강과 M4 소스/평가/자원 계약을 작성한다. 원래회차를 소급하여 clean으로 바꾸지 않는다.

## 조건·예상·실제 계산값

예상은 동일 고정 두질의의 확률 허용오차 내 재현이었다. TabICL2.2.0/Torch2.6.0+cpu, 고정110368038byte checkpoint, seed42/estimators8/batch1/threads3, CPU FP32, AMP/FA3/KV false를 유지했다. 입력·query_freeze는 round008에서 바이트복사하고 SHA를 확인했다. reference는 고정경로 header/첫2행 ID+p0..p3만 사용했으며 라벨은 해석하지 않았다. y_inner 접근0.

| 항목 | 결과 |
|---|---|
| 호출 | checkpoint/contextfit1, predict1, 계수학습0, 새F1 0 |
| mock | 1회0.281초 exit0, 잔존0; 추가mock0 |
| 실제 | 1회 wrapper215.485초/child213.898초; child exit0, wrapper command exit4 |
| 상한 | 실행 전600→480초(470+10) 축소; 실제재시도0; 관리자30분 |
| RAM | 시작4.562309GiB/최저3.300785GiB, sampled 소유트리peak1,265,553,408bytes |
| 확률 | finite/[0,1]2×4, 클래스[0,1,2,3], 저장JSON float64 행합오차5.541369318962097e-8 |
| 비교 | maxabs1.8446231598301388e-6≤1e-4, exact=false, argmax[0,1]일치 |
| 흐름 | COL8회/112청크, ROW8회/3152청크, ICL8회; 전체T3146/train_size3144유지 |
| 상태 | 입력/shuffle불변, COL/ROW/ICL observer복원true, gradients없음 |
| 종료 | stop_reason=null, owned_tree clear/잔존0, 강제종료없음 |

메모리는 이번 관측값이며 통제된 절감량이나 전체자료 최대수요 상한이 아니다. 두 질의 재현을5897척 F1으로 확대하지 않는다.

## 동결 위반과 근거

승인manifest/mock/pilot 실행wrapper사본 SHA는 c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210이다. 작성자가19:57:09.149UTC에 root_identity_capture_failed 조기반환의 진단2줄을 추가해 live SHA는 c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867이 됐다. mock19:56:17.987/pilot19:56:30.749 이후다. 해당분기는 이번 실행에서 사용되지 않았지만 원본불변계약은 위반했다.

실행중 적재된wrapper와 저장실행사본, model script/adapter/입력은 유지됐다. 종료후26항목 대조에서 livewrapper1개만불일치했다. 원본복원이나 승인map 사후수정으로 위반을 감추지 않았다. 변경본은 manager/run_bounded_after_freeze_incident.txt에 보존했다. receipt의 failed_or_stopped는 RAM/timeout/수치오류가 아닌 wrapper_unchanged=false 판정이다. child는 PILOT_COMPLETE, 저장JSON 독립검산은 saved_numeric_replay_gates_passed=true/all_execution_gates_passed=false다. review/INCIDENT_REVIEW.md와 FINAL_REVIEW.md를 참조한다.

승인26개항목·실행사본·stdout/stderr·resource_curve·PID/creation tick·영수증은 logs와review에 있다. manager/*evidence.json은 Astra/high 관리자와 Luna/xhigh 작성자·검토자의 요청 및 host turn_context를 분리해 기록한다. 호스트 설정증거이며 내부모델인증은 아니다. 원자료/이전저장소/과거회차/venv변경, 외부업로드·공식제출·유료자원·설치0이다.

## 학습·후속

기술목표인 실제 두질의 수치재현은 달성했고 전체절차관문은 미달했다. 원인계층은 모델수치가 아닌 협업동결/실행출처다. 학습질문: 수치가 맞아도 실행사본과live변경을 분리해야 하는 이유는? ROW배치축과ICL문맥축은 왜 다른가? exact와허용오차판정은 어떻게 다른가? 학습자이해·장치동작은 평가하지 않았다.

기존 반복노출 개발OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 탐색미채택0.5933525521451586 유지. 독립/공식null. NEXT_SESSION의 유한 후속을 새Astra high에 인계하며 수락은 automation/receipts/round_010_launch.json으로 확인한다. CLI에 structured-chat닫기명령이 없으므로 수락후 관리자를 종료하고 필요하면 완료세션 codex_4a9e4942_60c6_472c_8d6c_9cfe5f78c72d 탭만 수동으로 닫는다.
