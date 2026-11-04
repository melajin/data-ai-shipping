# Round015 — M4 합성 수치검사 완료, 실행기 종료·JSON 판정 실패

smoke 1회와 mock 1회는 성공했다. 합성 Python도 1회 실행되어 종료코드 0, 완료 JSON과 두 head 저장물을 남겼다. 그러나 PowerShell 실행기가 완료 JSON을 읽는 과정의 예외와 제한시간 이전 timed_out=true 기록 때문에 **합성 실행기 영수증 completed=false**다. 저장된 수치검사 통과와 전체 실행 판정 실패를 구분하며, 모델을 재실행하거나 실패 영수증을 수정하지 않았다. 새 F1은 없다.

## 이전 회차 대비 변경과 결과

Round014는 코드 작성·정적 검토만 하고 동적 실행을 하지 않았다. 이번에는 승인된 세 파일의 round_014/round014/Round014 표기만 015로 변경했다. 역치환 후 원본과 바이트 단위 일치했고 작성자 ACK(21:31:13UTC) 뒤 코드를 동결했다. 독립 승인map 및 관리자의 직접 64자리 해시 확인을 거쳤다. 초기 복사·승인 5분 목표는 넘겼으나 30분 관리자 예산 안에서 모델 실행과 문서 시간을 확보했다.

| 단계 | 실제 결과 | 실행 시간 |
|---|---|---:|
| process smoke | exit0/7 두 child의 정수 종료값·stdout/stderr·소유트리 종료 확인; completed=true | 1.0178889초 |
| stdlib mock | 클래스 복원, target 분리, 호출상한, 중복merge 거부 4시험 성공; completed=true | 0.6014277초 |
| 합성 Python | exit0, stderr 비어 있음, 결과 status=completed | 실행기 기록16.7639027초 |
| 합성 실행기 | JSON 변환 오류 및 제한시간 전 timed_out=true; completed=false | 모델 재시도0 |

승인map SHA256은 2cede678cba53e4a92832c663bf4968b75ee63b5c1287ad25804aaf3dce59dd4다. 세 단계에서 map·live source·snapshot 전후해시와 stdout/stderr 수집·소유프로세스 종료가 유지됐다. 합성 소유트리는 Python PID388과 conhost PID24672였고 잔존0이다. conhost는 추가 모델 프로세스가 아니다.

## 합성 계산값과 해석

고정 seed20261112, context16×8/target4×8 FP32, CPU threads3, TabICL2.2.0/Torch2.6cpu/NumPy2.3.5, 기존 pinned checkpoint를 사용했다. target 라벨은 predict 이후 외부 head loss에만 생성됐다. 실제 관찰된 마지막 층은 W[10,1024]/b[10], target cache H[4,4,1024]/logits[4,4,10]이다.

- checkpoint hash1/load1, contextfit1, predict1, nativeforward4, head평가12, backward4. a/b 각 SGD2step이며 범위를 넘기지 않았다.
- 원head 재계산 raw 차이0. 공식 predict 확률 재구성 차이5.960464477539063e-08≤1e-6, argmax 일치. 완전 동일과 허용오차 내 일치는 구분한다.
- a/b 초기복사, a 학습head 재로드, b 단일병합·재로드의 raw 및 확률 차이는 모두0. 6개 비교 모두 고정 문턱을 충족했다고 저장됐다.
- a gradient finite/nonzero·비활성행0, b 첫 Agradient0/첫 B비영/두번째 A비영, bias와 비활성행 불변, upstream 파라미터·buffer·gradient·mode 불변과 hook 복원 검사를 통과했다.
- a CE 진단은 초기1.4843811988830566, 두 step 전 값1.4843811988830566/1.484022617340088. b는1.4843811988830566/1.4843813180923462로 작은 증가도 있다. CE 감소를 성공조건이나 후보선택에 사용하지 않았다.

이는 합성 head-only 정합성의 저장 실행 증거이며 독립 모델 재실행이나 전체 estimator 저장재로드 검증은 아니다. head 파일을 독립 검토자가 다시 역직렬화하지 않는다. 결과 JSON SHA256=365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105, a head=c33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0, b head=8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36. 원본 파일과 실행기 영수증을 그대로 보존한다.

## 실패 계층과 후속

실패는 모델·gradient·RAM 단계가 아닌 실행 제어·결과 소비 단계다. 추가로 process.wait_finished=false/timed_out=true가 16.7639027초 기록에 남았으며 170초 제한에 도달한 실제 시간초과라고 볼 수 없다. memory_stop=false/kill_attempted=false/exit_confirmed=true/exit_code=0이다. runner는 재호출 WaitForExit(1)의 거짓값만으로 timedOut을 설정하고 deadline 도달을 함께 요구하지 않는다. 정확한 동적 발생 경로는 미확정이며 JSON 오류와 별개로 보존한다. 유효한 JSON의 upstream_model.module_training_before_after에는 루트 모듈을 나타내는 빈 문자열 key가 있다. 작성자는 stdlib json.tool 성공과 PowerShell5.1.26100.9711의 동일 파일 변환 실패를 독립 확인했다. 원인·추가 실행상태 불일치 증거는 manager/CONTROL_LAYER_FINDINGS.md 및 review/FINAL_REVIEW.md를 따른다. 관리자의 첫 stdlib 읽기 명령은 PowerShell 인수 따옴표 변환으로 SyntaxError가 났고 stdin 전달로 수정했다. 이는 모델 재실행이 아닌 저장 JSON 읽기다.

다음 회차는 이 결과를 다시 생성하지 않고 빈 key를 보존하는 판독 경로, 정상종료/실제deadline 판정, 저장 JSON 감사를 모델 없이 유한 검증한다. round015의 역사적 전체gate=false를 바꾸지 않는다. 그 관문을 통과한 다음에 사전선택 M4-a 전체estimator 통합을 별도 회차로 진행한다. 실제 FIT 학습과 F1 평가로 자동 확대하지 않는다.

## 자원·모델·학습 경계

21:26:37UTC 가용RAM5.6695GiB, 합성 직전21:35:37UTC5.7838GiB/다른Python0이었다. 실행 시작3GiB 이상, 실행중1.5GiB 미만 중단 기준을 유지했다. 관측 최소 가용RAM5.2197876GiB, sampled owned-tree peak585891840bytes=558.75MiB, memory_stop=false이며 timed_out=true가 비정상적으로 기록됐다. kill_attempted=false이고 실측경과16.764초이므로 실제170초 제한 도달은 확인되지 않았다. 이는 약1초 간격 샘플의 최대값이며 연속 peak가 아니다. 사전 예상1.5GiB는 checkpoint105MiB/로딩사본/Torch/작은 cache에 근거한 가정이었다. RAM부족 보류·사용자process종료·RAM대기loop0.

관리자 host turn_context는 gpt-6-astra/high, 두 보조는 gpt-6-luna/xhigh로 기록됐다. 명시 요청과 host 메타데이터는 manager/host_turn_evidence.json 및 worker_model_evidence.json에 분리했고 내부 모델 인증으로 주장하지 않는다. 작성자와 검토자는 독립이며 추가child0이다.

원자료·NPZ·reference·OUTER·holdout 읽기0, 설치·네트워크·공식제출·외부업로드·유료0. 선택한 기존 문서·코드·설치소스18개 전후해시가 일치했다. 기존 개발 OUTER5897 baseline micro-F1 **0.5930133966423605**, macro0.5252719738966167, 미채택 탐색0.5933525521451586 유지. 독립/공식null, 목표0.7미달. round010 역사·현재 source gate false도 보존한다.

기술 목표는 수치관문과 실행기 전체판정을 분리해서 평가한다. 학습질문은 LEARNING_NOTES의 클래스 순열·B=0 gradient·context/target 경계·합성검증과F1의 차이다. 학습자 이해 및 하드웨어 검증은 미평가다.

## 완료·인계

독립 저장결과 검토를 반영한 뒤 STATUS.current_round=round_015, handoff.ready=true, active_workers=[] 및 LEDGER/NEXT를 갱신한다. Start-NextSession.ps1 -FromRound round_015 수락 영수증의 새세션·prompt 전달 확인 즉시 이 관리자는 종료한다. orca agent 도움말에 structured chat 닫기명령이 없으므로 앱전체나 무관한 세션을 닫지 않고, 필요한 경우 이 완료 탭만 수동으로 닫는다.
