# Round 007 결과 — CPU 컬럼 분할의 작은 합성 동등성 통과

동일한 fitted TabICL estimator에서 원경로1회와 컬럼chunk16 경로1회를 비교했다. 합성 질의2개×4클래스의 확률 최대절대차는 **0.0**, 수치값의 exact equality와 argmax2개 일치를 확인했다. 허용오차1e-5 관문을 통과했다. 실행은30.078초에 정상 종료했으며 소유 계산프로세스는 모두 종료됐다. 실제선박자료 추론·새F1은0회이고 micro-F1 0.7은 아직 달성하지 못했다.

## 이전 → 현재 → 다음

round006은 전체 FIT3144/고정두질의의 원경로 추론 중 가용RAM1.5GiB 미만으로 중단돼 확률을 얻지 못했다. round007은 CPU가 자동배치 경로를 우회하는 pinned소스를 확인한 뒤 컬럼별 독립 배치축만 분할하는 로컬 어댑터를 작성·별도검토했다. 원모델/정밀도/학습문맥축/ROW/ICL은 유지했다. 이번 개선은 **실행경로 변경의 의미 보존을 작은 합성 입력에서 확인한 것**이며 성능 개선이 아니다.

다음 round008은 같은 FIT3144/고정 INNER2에 이 어댑터만 적용한 실제재현1회다. 현재 어댑터는 configure된 CPU원관리자에 설치하므로, fit직후 설정만 먼저 적용하고 설치하는 순서를 별도mock·소스검토한다. 큰 원경로 예측을 먼저 실행해 configure하지 않는다. 실제재현 통과 전 M4학습은 진행하지 않는다.

## 조건·실제 계산값

| 항목 | 관측 결과 |
|---|---|
| 합성 입력 | default_rng(20261105) 표준정규 float32 FIT32×312, query2×312; y=tile(arange(4),8) |
| 모델 | 기존checkpoint1회/문맥fit1회; 계수학습0회; seed42/estimators8/batch1/n_jobs3 |
| 환경 | 기존Python3.12.14 환경, TabICL2.2.0/Torch2.6.0+cpu, CPU FP32; AMP/FA3/KVfalse |
| 예측 | 같은estimator predict_proba 시도2/완료2; 원경로→분할경로; 재시도0 |
| 확률 | 각각2×4, finite/[0,1]/행합오차≤1e-5, 클래스[0,1,2,3] |
| 비교 | 최대절대차0.0, exact numeric equal=true; 두argmax[1,2]로 일치 |
| 불변성 | 입력의 shape/dtype/바이트해시와 shuffle 상태 전후일치; 원관리자 복원=true |
| 실제 컬럼호출 | 8회; 입력(1,316,34,3)→출력(1,316,34,128), 분할축1 |
| chunk | 각호출20개, 총160 forward; 최대16, 마지막12; T=34/FIT=32/그룹내부폭3 보존 |
| 실행시간·종료 | 30.078초, exit0, timeout/RAM중단 없음, 잔존소유프로세스0 |
| 관리자 실행직전 RAM | 18:27:46UTC4.815147400GiB; 다른해당계산0개 |
| wrapper 생성직전 RAM | 4.787761688GiB; 관측최저4.139598846GiB |
| sampled 소유트리 peak working set | 780,906,496bytes(약0.727GiB); 실제Python OS peak770,179,072bytes |
| 신규 실제자료/F1/OUTER/holdout/설치·다운로드 | 각각0회 |

추정peak1–2GiB는 실행 전 모델파라미터/런타임과34행 문맥에 근거한 보수적 추정이었다. 표의 RAM은 이번 합성 프로세스의 관측값이다. 원경로와 분할경로의 별도peak를 통제비교한 실험이 아니며, 전체3144문맥에서 필요한 RAM이나 절감폭을 보장하지 않는다. 실제 chunk의316축은 feature-group/예약토큰을 포함하는 배치축이며 원입력312개 특징과 혼동하지 않는다.

## 검토와 실행감시 수정

작성자와 별도검토자가 컬럼축 독립성·target확장·정규화/attention문맥·shuffle재조립·output_repeat를 pinned소스와 해시로 검토했다. 모델은 `_prepare_inputs/_run_forward`의 CPU/no_grad/AMP 의미를 유지한다. estimator의 col_embedder.inference_mgr만 감싸고 복원한다. 소스검토 중 configure전달 누락, 설정객체/torch.device 직렬화, 입력지문 비교schema 등을 실행 전에 수정했다.

첫 pure mock은 여섯 검사함수 통과/exit0/0.281초였지만 감시자receipt가 종료된 root의 남은 Popen핸들을 실행중으로 오인해 failed_or_stopped를 기록했다. 원receipt는 보존했다. PID생성시각에 더해 WaitForSingleObject의실행상태를 검사하도록 수정하고 별도승인 후 두번째이자마지막 mock을 실행했다. mock02는 여섯검사 통과/exit0/0.265초/잔존0이다. 이 오류는 감시자의 종료판정 계층이며 어댑터검사 실패나 모델OOM이 아니다. manager/WRAPPER_CORRECTION.md와 mock_01_postexit_correction.json이 근거다.

합성 실행소스 SHA는 `67f74942b38c4c2ee42c6a0509c39997828c0e98658bc04adb2ca96850f445b3`, 어댑터는 `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded`, 실행wrapper는 `2820871e8884a0fd642e550301154c16039d6c85c6168bda32cbf67340f3bee4`다. 승인manifest와 실행snapshot SHA를 대조했다. 단계별JSON·chunkshape·stdout/stderr·PID생성시각·RAM곡선·종료코드는 artifacts와 logs/pair_01에 있다.

## 평가·학습·가설의 한계

합성동등성은 실제선박 확률재현/F1/독립성 증거가 아니다. 역사적 채택기준 sqrt_macro5seed 개발OUTER5897의 micro0.5930133966423605/macro0.5252719738966167은 유지한다. 탐색최고0.5933525521451586은 미채택이고 독립·공식점수는 없다. 원자료·보호7372행·holdout·실제특징/확률배열을 이번회차에서 읽지 않았다.

기술목표인 소스계약·mock·작은합성동등성은 달성했다. 학습자의 batch축/sequence축 구분과 결과해석 역량은 LEARNING_NOTES.md 질문으로 남겼으며 이해달성을 측정하지 않았다. 하드웨어 실험도 없다.

SEASONAL_FEATURE_INVENTORY.md에는 F156/F304의 기존 시간특징과 새월별변화 가설을 구분했다. T5도 월별분포를 사용하지만 최종행평균으로 축약한다. 기존monthly_repeat35열은 월별관측량·시간대변동 등을 다루며 월별형태/지역변화의효과를 따로입증하지 않는다. 이 작업은 코드·특징명 metadata와10개소스해시 대조이며 새성능평가가 아니다. 1–6월을 사계절자료로 부르지 않는다.

## 모델 증거·후속 인계

현재 관리자의 host turn_context는 gpt-6-astra/high, 작성자·검토자는 gpt-6-luna/xhigh였다. manager/model_runtime_evidence.json과 assistant_host_evidence.json은 요청값과 호스트 관측을 구분한다. 내부 모델 인증을 주장하지 않는다. 관리자와 보조2명으로 호스트4슬롯 한도 내에서 수행했다.

독립 실행 전 검토는 review/precheck.json·mock02_precheck.json·synthetic_precheck.json, 실행 후 검토는 review/FINAL_REVIEW.md·final_review.json에 기록한다. artifacts/result.json은 관리자 집계이며 실제 합성 결과는 synthetic_pair_result.json과 synthetic_pair_outputs.npz다. 최종 NEXT_SESSION에는 round008의 입력 해시·설정 순서·예산·판정·실패 분기·RAM 대체 작업 규칙을 남긴다.

독립 검토자가 NumPy만 사용해 저장 NPZ와 JSON을 대조하고 RNG 입력·해시·확률·chunk 순서를 다시 계산한 50개 검사가 모두 통과했다. 각 확률의 최대 행합오차는 5.960464477539063e-08이었다. 검토용 스크립트의 첫 경로 오류를 고친 뒤 완료한 검산이며 모델을 다시 실행하지 않았다. 입력 파일·출력 확률의 검산과 새로운 모델 실행 횟수를 구분한다.

후속 세션 수락의 정본은 automation/receipts/round_007_launch.json이다. 수락 확인 후 현재 관리자는 종료하며 round008 실험을 여기서 이어하지 않는다. 현재 CLI agent 도움말에는 launch만 있고, structured-chat용 close API는 확인되지 않았다. 수동 정리가 필요하면 완료된 세션 `codex_3f5d6e5d_c588_43a3_9279_40d5d4f4edd6` 탭만 닫는다. 다른 터미널이나 앱은 종료하지 않는다.
