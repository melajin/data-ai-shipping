# Round 003 결과 — TabICL A 저장 확률의 판정 손익

작성: 2026-11-05 KST. **R0 계산과 독립 검산을 완료했다. 새 INNER 선택 정책은 원확률 대비 사전 진행 기준을 통과하지 못해 확인 후보로 채택하지 않는다. 목표 micro-F1 .7은 미달이다.**

## 결과와 판단

반복 노출된 개발 OUTER **5,897척**, seed42/2026의 저장 확률을 사용했다. 같은 선박의 두seed 지표를 각각 계산한 후 산술평균했다. 확률 평균 앙상블도, 11,794척의 독립 표본도 아니다.

| 판정 | seed42 정답 | seed2026 정답 | 평균 micro-F1 | 평균 macro-F1 | 평균 weighted-F1 |
|---|---:|---:|---:|---:|---:|
| A_raw: 원확률 argmax | 3,491 | 3,503 | **.593013397** | .515558032 | .553984391 |
| A_old: 통발 fold배수2/3/2 | 3,391 | 3,389 | .574868577 | **.537227129** | .558096721 |
| A_micro_select: INNER 제한 선택 | 3,495 | 3,503 | .593352552 | .520562845 | .556421857 |

선택은 seed42 fold별 **[1,1.5,1]**, seed2026 **[1,1,1]**이었다. 지원 부족에 따른 raw 복귀는 발생하지 않았다. 원확률 대비 새정책은 seed42에서32척을 고치고28척을 새로 틀려 순증4척, seed2026은 변화0척이다. 평균 정답순증2척에 해당하는 **micro+.000339156**이다.

원확률 대비 평균micro 차이의 선박 bootstrap5,000회95%구간은 **[−.000932678,+.001610989]**이다. 사전 기준인 평균micro+.005, 두seed 모두양수, CI하한>0을 모두 충족하지 못했다. 평균macro 하락없음, 각seed 클래스F1/자연1–7일macro 하락<=.01은 통과했지만 전체 진행 조건은 실패다. macro 차이+.005004813의 구간[+.002607409,+.007562640]이 양수여도 micro 목표의 채택 기준을 대신하지 않는다.

| 변경 | seed42 고침/새오답/순증 | seed2026 고침/새오답/순증 | 평균micro차이 | paired95%구간 |
|---|---:|---:|---:|---:|
| old→raw | 289/189/+100 | 301/187/+114 | +.018144819 | [.011192132,.025012718] |
| old→selected | 261/157/+104 | 301/187/+114 | +.018483975 | [.011868323,.024843141] |
| raw→selected | 32/28/+4 | 0/0/0 | +.000339156 | [−.000932678,.001610989] |

기존 배수를 제거하면 micro는 오르지만 macro는 평균 .021669097 낮아졌다. selected도 old보다 macro가 .016664283 낮다. 따라서 기존 보정이 단순한 오류라고 결론내리지 않는다. macro와 통발 성능을 얻는 대신 전체 정답 수를 잃었던 손익을 확인한 것이다. 이번 결과를 보고 배수나 제약을 다시 골라 덮어쓰지 않았다.

| 업종 평균F1 | raw | old | selected |
|---|---:|---:|---:|
| 연안복합 | .703295 | .690509 | .703183 |
| 자망 | .465924 | .445159 | .464925 |
| 통발 | .227649 | .352188 | .247466 |
| 채낚기연승낚시 | .665365 | .661052 | .666677 |

원확률 micro평균 .593013은 역사 LightGBM5seed 기준값과 숫자가 같지만 **서로 다른 모델의 결과**다. 이번 selected .593353도 과거 six_source_mean .593353과 별개다. 역사 기준선과 탐색값은 유지하며 새 정책을 채택 기준선으로 교체하지 않는다.

## 조건·학습목표·검증

기술 목표는 원확률을 고정한 판정 규칙의 정답 손익을 계산하는 것이었다. 학습 목표는 모델 학습 손실·원확률·최종 라벨, micro/macro 손익과 선박 단위 재표집을 구별하는 것이다. 성능 상승을 예상값으로 정하지 않았다.

- 실행 전에 ROUND_PLAN, configs/experiment.json, 소스·입력 해시를 동결했다. seed별·fold별 INNER787척에서만 p2배수[1,1.5,2,2.5,3]를 선택했다.
- raw 대비 INNER macro하락없음, 클래스별F1/자연1–7일macro 하락<=.01인 후보 중 micro최대를 택했다. 동점은1에 가까운 값, 다시 동점은 작은 값이다. labels=[0,1,2,3], zero_division=0, tolerance1e-12다.
- 전체INNER 또는 자연1–7일INNER에 정답 클래스가 빠지면 raw로 복귀하도록 사전 고정했다. 여섯 배수 JSON을 저장·해시 확인한 뒤 OUTER 지표를 계산했다.
- OOF fold1966/1966/1965, 개발명부17691행=5897척×3역할fold, seed간 ID·정답·관측일 일치와 원확률 finite/범위/행합을 검사했다. 최대 행합 오차는1.11e-16이다.
- 같은 선박 인덱스를 두seed에 함께 적용한 bootstrap5000회(seed20261105)를 수행했다. 반복 개발선택·해역 의존을 제거하는 구간은 아니다.

전체/seed/fold, 관측일1–7/8–30/31–90/91+, 0일/미지원의 micro·macro·weighted와 업종별precision/recall/F1/support, 혼동행렬·양방향변화는 artifacts/result.json에 있다. 빈 집단은 null과0지원으로 표시했다. 관측일은 실제 운항시간이 아니다.

원확률 logloss/Brier/10구간ECE와 max>=.9 오답 수도 저장했다. seed42는 logloss .901223848, Brier .529733252, ECE .014824196, 높은확신오답11척이다. 판정만 바꿨으므로 원확률 진단값의 개선을 주장하지 않는다. Brier는 클래스별 제곱오차 합의 선박평균이며4로 나누지 않았다.

## 출처 감사의 확인 범위와 한계

공유 package manifest, frozen rule의 여섯 INNER 파일해시, 연결된 생성소스 지문이 일치했다. 실제 TabICL 분기는 `model.fit(fit_x,fit_y)`만 호출하고 INNER를 학습/조기종료에 사용하지 않았다. 여섯 training metadata의 계수학습0/INNERunused 기록도 일치한다. 이 근거로 full INNER 선택을 수행했다.

다음 한계는 남는다.

1. 과거 INNER ID목록 해시의 원래 행순서/생성기가 없어 현재 CSV순서의 직렬화로 그 해시를 복구하지 못했다. 정확한 예측파일해시와 역할·라벨·관측일은 확인했으며 파일 손상이나 split 불일치로 단정하지 않는다.
2. 저장 decision_score는 배수 적용 뒤 정규화했고 배포코드는 비정규화 점수를 기술한다. argmax는 일치한다. 원확률을 기준으로 재계산했으며 어느 점수도 검증된 calibrated probability라고 부르지 않는다.
3. run_settings의 결측표시없음과 fingerprinted 코드의 결측표시추가가 충돌한다. saved preprocessor.kind와156개median도 결측표시추가를 지지하여 변환후312열이 유력하다. 실제 특징행/문맥순서/클래스shuffle/원출력은 재현하지 않았다.
4. OUTER 선박은 해당fold의 FIT/INNER와 분리되어 있다. 동시에 연구자는 같은 개발 OUTER 결과를 반복 관찰했다. 신규 독립평가·공식점수로 부르지 않는다.

원자료, 전체7372 F156/라벨표, holdout 개별행, Test2025를 읽지 않았다. 새 계수학습·새 원모델 추론·하드웨어 실험은0회다. 검증된 파일 해시의 범위를 전체 저장소 무변경 인증으로 확대하지 않는다.

## 실행과 독립 검산

관리자 세션은 `codex_72aeaa5c_d706_4426_8c38_be2ff5da2bd9`다. 전달된 인계SHA256과현재문서가 일치했고 이전관리자 done, 동회차 중복계산 없음, 다른TestB세션은 그대로 유지함을 확인했다. host turn_context에는 관리자 gpt-6-astra/high, 별도 작성자·검토자는 gpt-6-luna/xhigh가 기록되어 model_runtime_evidence.json에 보존했다. 모델 내부를 별도로 인증한 것은 아니다.

작성자와 독립검토자가 분리됐다. 코드검토 후 두 차례의 짧은 무점수preflight를 수행했고, 명부hash/정규화점수/빈집단처리의 기록을 보완했다. 이후 본점수 실행은 **한 번**, 16:34:27.781 UTC부터 약15.127초, PID440/launcher13580, 종료코드0이었다. 실행 전후 runner/config 해시가 같았고 timeout은 없었다. Python3.13.3/NumPy2.2.5, 스레드3, 숨김프로세스·RAM·시간상한을 적용했다. 학습0회/원모델추론0회다.

검토자는 별도 코드로 여섯선택배수와 후보grid 지표, seed별 총11794예측행(고유선박5897척), 960개 지표항목(기존816개 확인항목과 빈집단의144개 null항목), 혼동/클래스/관측일 집계, 전이, 확률진단, 세변경×micro/macro의5000회bootstrap를 다시 계산해 일치를 확인했다. 원본 review/review.json 및 artifact_comparison.json을 관리자 해석과 함께 보존한다.

## M4 준비와 다음 회차

계산 후 제한된 조사에서 지정 checkpoint **110368038bytes/SHA256 일치**를 표준 HuggingFace 로컬캐시에서 찾았다. 시스템3.13, round002환경3.13, Codex번들3.12.14에는 Torch/TabICL이 없다. 현재 WMI는 AMD Radeon780M을 보고했고 NVIDIA CUDA환경은 확인되지 않았다. 여섯fold model.pkl도 없다. 자세한 경로·metadata·검사범위는 m4_readiness/readiness.json과READINESS.md에 있다.

따라서 다음 회차는 **전용 CPU runtime 확보 → 극소 합성 smoke → 개발전용 입력계보 감사**로 한정한다. 공식2.2.0/2.6.0 CPU배포와 기존checkpoint를 재사용하는 구체적 명령·예산·실패분기를 NEXT_SESSION에 남겼다. 실제원출력replay가 선행된 후 M4-a(weight만,bias고정)와M4-b(rank2,bias고정)의 무변경/gradient/병합/reload 및한foldINNERpilot로 진행한다. 새특징·큰구조변형을 동시에 추가하지 않는다.

학습자가 설명할 질문: 왜 기존배수 제거가 micro를 높이면서 통발F1을 낮추는가? 32척을 고쳤어도 순증은 왜4척인가? 같은배의 두seed를 독립두척으로 세면 왜 안 되는가? 저장확률검산과 원모델재현은 무엇이 다른가? 시스템 산출은 완료됐지만 학습자 이해는 아직 평가하지 않았다.

핵심 산출: ROUND_PLAN.md, configs/experiment.json, artifacts/result.json·decision_policy_frozen.json·predictions.csv·paired_bootstrap_draws.npz, logs/launch_receipt_score_20261104T163427781Z.json 및 snapshot, review/, m4_readiness/, LEARNING_NOTES.md. 실제 파일명은 artifacts 목록과 result의 artifact 참조를 따른다.
