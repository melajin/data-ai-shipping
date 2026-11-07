# Round 008 결과 — 컬럼 분할 후 실제 재현은 RAM 관문에서 중단

고정 FIT3144/INNER2 실제 재현을 한 번 실행했으나 25.64초 후 가용 RAM이 1.5GiB 미만이 되어 감시자가 소유 계산트리를 종료했다. 첫 컬럼 호출의 14개 청크는 완료됐지만 predict_proba는 반환하지 않았다. 확률 비교와 새 F1은 없으며 micro-F1 0.7은 미달이다.

## 이전 → 현재 → 다음

round006 원경로는 27.594초, 시작4.2835GiB/최저1.3921GiB, sampled tree peak3,160,498,176bytes에서 중단됐다. round007은 작은 합성 입력에서 컬럼chunk16 동등성을 통과했다. 이번에는 같은 실제 입력·모델·질의를 유지하고 컬럼chunk16만 적용했다. fit직후 원컬럼관리자에 resolved COL_CONFIG를 그대로 configure한 후 설치했다. 실제 원경로의 추가 예측은 없었다.

이번 개선은 첫 컬럼 계산이 14청크로 끝났다는 위치 증거다. 전체 실행이 끝나지 않았으므로 전체문맥 메모리 절감이나 확률 재현을 달성했다고 할 수 없다. 서로 다른 시작 RAM·프로세스 상태에서의 두 중단 peak를 절감량의 통제비교로 쓰지 않는다. 다음 회차는 컬럼 이후 경로와 ROW의 독립 배치축을 소스에서 확인하고, 가능할 때 작은 합성 비교로 ROW 분할의 의미 보존을 검증한다. 동일 실제 재현은 반복하지 않는다.

## 조건과 관측 결과

| 항목 | 실제 결과 |
|---|---|
| 입력 | round006 NPZ/freeze 바이트복사와 고정 SHA 일치; FIT3144×312, 고정 INNER2 |
| 모델 | TabICL2.2.0/Torch2.6.0+cpu; seed42/estimators8/batch1/n_jobs3/FP32; AMP·FA3·KV false, offload auto |
| 실행 예산 | 사전 최대600초에서 실행 전420초(계산410+정리10)로 축소; 실제1회/재시도0 |
| 실제 실행 | 25.64초, exit1, stop_reason=available_ram_below_1_5_gib |
| RAM | wrapper시작4.144317626953125GiB, 관측최저1.3799629211425781GiB |
| sampled 소유트리 peak | 3,182,952,448bytes; 총필요메모리의 상한이 아님 |
| 호출 | checkpoint/문맥fit1회, predict_proba 시도1/완료0, 계수학습0 |
| 컬럼 | call0 입력(1,223,3146,3)→출력(1,223,3146,128); 16×13+15, 총14청크 완료 |
| 종료 | termination_confirmed=true, owned_tree_remaining=[] |
| 확률·평가 | 확률null, 비교null, 새 F1/OUTER/holdout/공식제출0회 |

마지막 이벤트는 column_chunk_call_completed이고 다음 컬럼호출 시작은 없다. 정확한 중단 연산은 계측하지 않았으므로 ROW OOM으로 확정하지 않는다. 입력의312열과 실제 컬럼그룹223축을 같은 것으로 취급하지 않는다. 실행 전 메모리 설명에 쓴316축/약0.47GiB는 합성 관측 기반 계획값이며 실제 call0은223축이었다.

강제종료 때문에 자식 JSON의 raw status는 STARTED/stage=predict_proba_start로 남았다. 최종 상태는 wrapper receipt가 판단한다. adapter_restored=false이며 Python finally가 실행됐다고 주장하지 않는다. 로컬 인스턴스만 수정하는 설계이며 소유 프로세스는 종료됐다. 전역클래스·원본환경·과거회차를 수정하지 않았다.

## 검토·mock·증거

작성자와 별도검토자는 Luna xhigh였다. 관리자 host turn_context는 Astra high, 두 보조는 Luna xhigh로 확인됐으며 요청값과 호스트 기록은 manager/*evidence.json에 분리했다. 내부 모델 인증은 아니다.

실행 전 검토에서 설치 후 진단예외의 복원범위와 Popen 직후 소유PID 생성시각 기록을 보강했다. mock01은 FakeManager의 __call__ 누락으로0.282초 exit1이었다. 모델실패나 자원실패가 아니다. 가짜관리자 프로토콜만 수정한 마지막 mock02는0.266초 exit0/잔존0으로 통과했다. mock 추가실행은 없다.

최종 pilot SHA112ca09e7abba9c194421c22bd38771563636e2852c867c089cb27e985c39b0d, adapter bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded, wrapper6962c94fa07a36cd7b3429eaeb27ac851aee3104e9b77758d7a99c0fc1a48e1d. 승인manifest, 실행snapshot, stdout/stderr, RAM곡선, PID/생성시각, 종료기록을 보존했다. independent review는 review/FINAL_REVIEW.md에 기록한다.

## 해석과 학습

실패계층은 실제 추론 중 자원감시 관문이다. OS OOM·수치불일치·모델정확도 하락으로 해석하지 않는다. 채택기준 sqrt_macro5seed 개발OUTER5897 micro0.5930133966423605/macro0.5252719738966167은 그대로다. 탐색최고0.5933525521451586은 미채택, 독립·공식점수는 없다.

기술목표 중 설정순서/mock/첫컬럼완료 증거는 확보했으나 실제확률재현은 미완료다. 학습목표는 컬럼과 문맥축, 합성동등성과 실제재현/F1, 강제종료와 finally를 구분하는 것이다. LEARNING_NOTES의 설명질문에 대한 학습자 답변은 측정하지 않았다. 하드웨어 검증은 없다. 계절 가설은 SEASONAL_FOLLOWUP_DESIGN.md로 보존했으며 이번 특징에 추가하지 않았다.

후속은 NEXT_SESSION.md에 고정하며, automation/receipts/round_008_launch.json의 수락영수증을 확인한 뒤 현재 관리자는 종료한다. CLI의 agent 도움말에는 structured-chat 닫기 명령이 없다. 필요하면 완료된 세션 codex_e959665a_5b7a_4729_897c_f8de0d0a718d 탭만 수동으로 닫는다.

## 기록상의 제한과 RAM 재확인

독립 검토에서 자식 결과의 top-level source 객체가 configure 단계의 source 문자열로 덮인 진단 schema 결함을 찾았다. 실행소스/adapter/계약해시는 wrapper receipt의 승인manifest와 실제snapshot으로 복구할 수 있다. 기존 결과를 고치거나 모델을 재실행하지 않았다. 다음 합성 소스는 configure_source처럼 별도 필드를 사용한다.

결과 집계·보고·후속 설계 작업 후19:00:25UTC에 RAM4.392494201660156GiB, 관련 계산프로세스0개를 재확인했다. 실제재현1회 예산이 소진됐고 동일경로의 전체메모리 문제를 해결한 증거가 없으므로 재실행하지 않는다. manager/ram_after_alternative_work.json에 대체작업과 판단을 남겼다.

## 다음 가설의 소스 근거

POST_COLUMN_SOURCE_AUDIT.md의 정적 대조에서 tabicl.py:422–440은 column→ROW→ICL 순서다. interaction.py:215–253의 ROW는(B,T,H+C,E)에서각행의H+C를attention sequence로처리하며B,T는배치축이다. 반면learning.py:241–282의ICL은T를학습문맥sequence로사용하므로같은분할을적용하지않는다. 이구조는ROW batch chunk8의작은합성비교를설계할근거이며실제중단연산의확정이나메모리절감측정은아니다.
