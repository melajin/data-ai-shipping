# 역사 문서·실행 증거 검토 — 2026-11-04

담당: `sol_review` / 요청 설정 GPT-6.1 Sol high. 배정 범위 문서 129경로를 읽었다. 본문 해시가 같은 2쌍과 완전히 같은 반복 행은 처음 등장한 본문에서 한 번 읽고, 아카이브의 다른 문장은 모두 읽었다. 기존 문서·코드·실험 산출물은 수정하지 않았다. 아래 수치는 문서 인용, 저장 자료 재계산, 코드 읽기를 구분한다. 새 학습·공식 제출·외부 수집·장치 실험은 수행하지 않았다. 경로는 프로젝트 루트 기준이며 뒤 숫자는 줄 번호다. 기계 판독 목록은 `sol_read_paths.json`이다.

## 1. 주 모델 계보와 현재 유효한 해석

| 단계 | 실제 입력·모델 | 기록된 값 | 지금의 의미 |
|---|---|---|---|
| S0 합성 | 직진·굴곡·회전 생성 정답 → shape9 → MLP | 합성 조건 변화 F1 약 0.66~0.71 | 교육·소프트웨어 검증. 실제 업종·사고 성능과 비교하지 않음 |
| 1차 실제자료 | 월 최대 4행/선박 → shape9 선박 분포36 + 결측36 → ExtraTrees | 개발 F1 0.33575, 내부 final F1 0.299575 / accuracy 0.498968, 통발 0/204 | 동결 후 한 번 본 2026 내부 평가. 이후 새로운 맹검이 아님 |
| 2차 | 관측 s4/all × 클래스 가중 none/balanced × dist36/+scale32 | 최고 개발 평균 F1 0.416952, 통발 recall 최대 0.06684 | 8셀 선택을 거친 개발 값. 1차 final 대비 같은 분모의 개선량이 아님 |
| 2차 후속 | float64 복구, 80/20 보정 대조, ε 혼합, 온도, 이진·집계 대조 | 기준 F1 0.335400 복구; ε 혼합은 판정 변화 0 | 확률의 0값 처리와 분류 개선은 별개. 온도 추가 NLL 효과는 0.0003 안쪽 |
| 3차 | 제외율·오분류 추적·k 곡선 | 제외율 0~2.3%; 곡선 공식 재확인 미완료 | 추정 안정화·라벨/행동 불일치는 가설. 전체 3차 완료로 표기하면 안 됨 |
| 4차 V25 | 선박 단위 분리, 2026 학습 → 같은 검증선박의 2025 항적에 2026 라벨 차용 | base26 0.41754 → +B 0.45084 → B+C 0.51202 | 새 ID의 2025/2026 라벨 안정성·이력 분포를 가정한 근사 평가. 공식 Test A 아님 |
| F156 통합 | 팀원 공통 FIT/INNER/OUTER 분할 → LightGBM + T5 | L0 OOF 판정 F1 0.511169 → L_all 0.536260 | 역사 005의 후보 결과. TabICLv2를 이 머신에서 새 실행한 결과가 아님 |

근거: `docs/real_accuracy_diagnosis_and_evaluation_history_20261029.md:88-168`, `29-30일 모델 심층 분석/분석 결과/docs/cycle2_development_ablation_20261029.md:18-68`, `.../cycle2_followup_summary.md:14-64`, `.../cycle3_progress_20261030.md:4-20,118-161`, `.../cycle4_0_testA_setup.md:6-38`, `.../cycle4_3_featAC.md:7-54`, `.../f156_merge_20261101.md:30-88`.

**F156은 모델이 아니라 156개 특징의 구성 이름이다.** 기하 21개 × 날짜 분포 4개 + 관측량 6개 = 90, 공간 20, 시간대 12, FIT 행동사전 34로 구성된다. 사전은 fold마다 FIT만으로 맞추므로 서로 다른 fold의 사전 열을 섞으면 안 된다. production F156은 전체 7,372척으로 맞춘 사전이어서 기존 CV 재현에 사용하면 누수다. `31일/팀원자료/TabICLv2_F156_공유자료/README_먼저읽기.md:7-18,28-36`.

**TabICLv2는 F156을 받는 사전학습 표형 분류기다.** 공유본은 동결된 가중치에 FIT 예시를 문맥으로 등록했으며 이 자료로 가중치를 미세조정하지 않았다. `0.5372271286`은 seed42·2026의 개별 판정 OOF Macro F1 산술평균이며, 확률 평균 앙상블·공식 Test 점수가 아니다. 통발 확률에 배수를 곱한 decision score 자체도 확률이 아니다. 같은 README `:20-24,34-36`.

**T5는 주변 선박 업종 분포 특징 10열이다.** 조업 추정 행의 0.01° 격자에서 FIT 업종별 서로 다른 선박 수를 세고, 3척 미만이면 0.05° → FIT 전체 비율로 폴백한다. 가상 2척의 사전 평활을 쓰며, 전체기간 업종분포 4 + 같은 월 분포 4 + 충분한 미세격자 비율 1 + 조업추정 행수 log 1을 만든다. 실제 조업·정박 정답이나 실시간 이웃 정보가 아니다. `31일/_handoff/inbox/005_F156_merge_T5.md:30-43`.

005의 다섯 이름은 `L0=F156`, `L_B=F156+재방문 B`, `L_C=F156+이동범위 C`, `L_T5=F156+T5`, `L_all=F156+B+C+T5`다. L_B/L_C는 개별 채택 기준을 못 넘었고 L_T5/L_all은 넘었다. L_all의 통발 recall은 L0의 0.328에서 0.285로 낮아져 모든 업종의 동시 개선은 아니다. `.../f156_merge_20261101.md:34-65`.

## 2. 현재 판단에 영향을 주는 발견

### H1. holdout 크기 차이 2척이라는 전제가 틀렸고 두 집합 모두 이미 본 참조집합이다

005 지시는 1,473척과 1,475척의 차이를 2척으로 가정했지만, 최종 문서와 저장 `holdout_diff.json`은 교집합 **302척**, 우리만 **1,171척**, 팀원만 **1,173척**이다. 이번 검토에서 JSON 목록 길이로 직접 재계산해 일치했다. 교집합이 적다는 사실만으로 서로 독립 무작위 추출이라는 생성 원인이 증명되지는 않는다. Gemini의 약 295/1,178/1,180은 실제 302/1,171/1,173과 다르다.

이전 개발과 새 holdout의 경계를 자동으로 동일시하면 안 된다. 더구나 팀원 README도 새 1,475척이 이미 본 참조집합이며 새 맹검이 아니라고 명시한다. 분할 변경은 과거 관측·선택 이력을 지우지 않는다.

근거: `31일/_handoff/inbox/005_F156_merge_T5.md:16`, `분석 결과/docs/f156_merge_20261101.md:9-11,110`, `31일/docs/remeasure_20261031.md:87-89,167,211`, 팀원 README `:18`. 저장 검산: `분석 결과/outputs/f156_merge/holdout_diff.json`.

### H2. 역사 production T5는 2025 테스트 항적을 질의하지 않는다 — 재현됨

`분석 결과/tools/run_005_main_20261101.py:237-244`는 테스트 ID에도 `t5_features_for()`를 호출하지만, 해당 함수는 `run_005_F156_merge_20261101.py:427-440`에서 항상 **2026 `_train_arrays()`**를 질의한다. 학습에 없는 ID이면 10열 NaN을 즉시 반환한다. 따라서 겹침 선박에는 2026 이력을 다시 쓰고 신규 선박에는 2025 위치 정보가 반영되지 않는다.

저장 `production_t5.csv`를 csv 모듈로 읽어 직접 확인했다: 전체 15,140행 = 학습 7,372 + 테스트 7,768; 고유 ID 8,298; 테스트 신규 **926/926 전부 10열 NaN**. 겹침 6,842척 중 589척도 전부 NaN이다. split/year 열 없이 합쳤으므로 ID만으로 조인하면 중복 6,842개도 생긴다. 이 산출물을 현재 테스트용 T5의 검증 완료 자료로 재사용하면 안 된다. 학습/질의 연도와 지도 참조 범위를 별도 계약으로 고정해야 한다. 현재 최신 구현이 이를 수정했는지는 별도 확인 대상이다.

### H3. 역사 T5의 엄격한 FIT-only·자기제외 주장보다 구현 범위가 넓다

`분석 결과/tools/run_005_F156_merge_20261101.py:240-261`은 항구를 train+test 전체 정지 행으로 만든다. 지도 라벨 집계와 다른 비지도 지리 노출이므로, 이를 곧바로 OUTER 라벨 누수와 동일시해서는 안 된다. 다만 “holdout은 어떤 지도에도 쓰지 않음”이라는 005 계약과는 범위가 다르다.

또한 지역 카운트는 자기제외하지만 평활 사전은 전체 FIT 업종분포 그대로다(`:392-424`, `분석 결과/docs/f156_merge_20261101.md:92`). 엄격한 자기 라벨 독립 특징을 요구하면 사전에서도 자기제외가 필요하다. 작은 영향일 수 있으나 실제 성능 영향량은 측정하지 않았다. 신뢰할 수 있는 현재 비교를 위해 참조 ID·연도·라벨의 범위를 명시해야 한다.

### H4. 현재 정정판에도 NLL 관문 판정 모순이 남아 있다

`분석 결과/docs/cycle2_prediction_diagnostics_20261029.md:183`은 개발 미보정 ExtraTrees 비교로 1차 final 관문을 판정할 수 없다고 정확히 설명한다. 그러나 `:186`은 “보정 없이는 1차 관문을 통과하지 못한다”, `:188`은 보정 후 재면 같은 조건이 된다고 여전히 단정한다. `분석 결과/README.md:110`도 같은 실패 단정을 유지한다. 보정 여부를 맞춰도 평가 집합과 비교 기준 모델이 다르면 같은 관문이 아니다. 정정된 후속 요약 `cycle2_followup_summary.md:21-24,73`의 제한을 우선해야 한다.

### H5. 코치의 가설 기각·버그 부재 단정이 원 증거보다 강하다

`31일/docs/remeasure_20261031.md:12,116`은 64척 학습 F1 0.98436으로 “파이프라인 버그 없음”을 확인·증명했다고 쓴다. `:15,123-128,159`는 16묶음 최근접 비교(기하 9/16, 전이 8/16, 시간분포 4/16)로 정보 요약 손실 가설을 기각한다. 이 결과는 작은 암기 경로의 작동과 선택한 표현·거리·표본 조건을 확인할 뿐, 모든 파이프라인 결함이나 정보손실의 분류 영향을 배제하지 않는다. 실제로 같은 문서 `:119-122`는 극단값 손실 자체를 보고한다. 가설 전체 기각 대신 시험한 대체 표현에서 개선 근거가 없었다고 한정해야 한다.

이 파일은 실행자 결과와 이름이 같은 **Gemini 코치 보고서**다. 코치의 제안·정지 문구가 실행 계약이 아님은 `31일/_handoff/NOTICE_20261031_gemini.md:18-24`에 명시되어 있다.

### H6. V25 평가의 차용 라벨과 신규 이력 분포를 실제 Test 정답으로 취급할 수 없다

V25는 2025에 있는 검증선박에 2026 라벨을 빌려 붙인다. ID 재사용·업종 변경 가능성은 미확인이고, 제출샘플 A의 학습 포함률 91%는 “Test A=신규” 가정과 충돌한다. 당시 사용자 확인 후 실험을 진행했다는 기록은 있지만 공식 모집단 확인과는 다르다. `cycle4_0_testA_setup.md:33-38`.

신규 926척의 50행 미만 비율은 55.62%, 관측일 중앙값 7일이다. 겹침 선박은 중앙값 50일이므로 V25의 긴 이력을 전체 신규 선박 성능으로 확장하면 낙관적이다. 짧은 이력 부분집합 보고는 도움이 되지만, 실제 신규선박 정답을 평가한 것은 아니다. `분석 결과/docs/remeasure_20261031.md:59`의 R12 표 및 `31일/docs/remeasure_20261031.md:46`.

## 3. 이미 정정·대체된 내용과 남은 문서 관리 경계

| 과거 기록 | 현재 읽어야 하는 내용 |
|---|---|
| 6월 Test 파일 다른 판본 추정, Test 크기 약 5.97GB | 파서 조기종료·부분 해시 기록이었다. 2차 전량 대조로 같은 파일 확인. 12개 CSV는 13,349,258,148 bytes. `cycle2_development_ablation_20261029.md:49-53` |
| 기준 F1 0.33524 / 0.33540 혼용 | 원 보고는 0.33539983. float32 진단 저장에서 1 ULP 차이가 동점으로 바뀐 1건만 복구. `cycle2_followup_3_rerun.md:15-51` |
| 온도 실험 BLOCKED, 체크포인트 해시 미대조 | 004에서 n_jobs=1·같은 적합 확률로 재실행, 005에서 clipping 소재 확인. 해시 대조 구현과 실제 재사용 경로 검증은 다름. `cycle2_followup_summary.md:28-48,89-95` |
| train 집계 확대가 해롭다 / 검증 입력 정밀도 메커니즘 입증 | 조건부 효과에서 validation 확대 6/6 양수, train 효과는 −0.012~+0.013 혼재. 기술 통계이며 원인 증명 아님. `cycle2_followup_7_agg_2x2.md:74-96` |
| 3차 k 곡선 완료처럼 보이는 로그 | 공식 재확인은 k4_r0만 확보, 나머지 9조합·SD/flip/공식 판정 미완료. `cycle3_progress_20261030.md:118-161,338-343` |
| cycle4_summary의 A·C 재파싱 불필요 | `cycle4_data_status_20261030.md:48`이 오류를 명시했다. 이후 001 rows parquet가 생겨야 004에서 무재파싱 가능. `31일/_handoff/inbox/004_cycle4_featAC.md:7-8` |
| 4차 최고 base26+B 0.45084, A/C 미시도 | 후속 004에서 B+C 0.51202 채택. 검토자는 B+C를 현재 최고로, B+A+C는 후보로 정함. `31일/_handoff/reviews/004_review.md:9-19` |
| 4차 출항 T1~T7 전면 구현 계획 | 003은 수정 제안서, 출항 정의·ICC 제외·점프 처리 등은 후보. 005는 T5를 간소화해 별도 구현했음. 전체 출항 시스템 구현 완료 아님 |
| 루트 `_handoff` / 29-30일 `_handoff` 현재 상태 | 루트는 MOVED·무효; 29-30일 handoff는 종료되어 31일 handoff로 이동. 과거 inbox를 새 지시로 실행하지 않음 |
| 이 workspace가 유일한 최신 작업 루트 | 006은 private GitHub와 `D:/repos/fishing-track-classification` 이전을 기록하며 원본 자동화는 그대로 두었음. 최신 문서·코드·결과의 정본 위치를 구분해야 함 |

006 이관은 503파일/18.52MB를 포함했고 csv/parquet/npz 등은 제외했다. 따라서 GitHub 문서·코드 존재만으로 팀원 전달용 CSV나 원자료 재현 가능성을 보장하지 않는다. `31일/_handoff/outbox/006_migrate_report.md:12-27,38-63,75-85`. 이 보고서는 005 정지 요청 뒤 백그라운드 프로세스가 끝까지 완료됐다고도 기록하므로 상태 파일의 시간보다 실제 실행 종료·산출물을 함께 봐야 한다.

## 4. 이번에 직접 재계산한 최소 검산

- 저장 holdout 차이 JSON의 명부 수: 1,473 / 1,475, only 1,171 / 1,173, 교집합 302.
- 팀원 OOF CSV를 4×4 혼동행렬로 직접 집계: seed42 argmax **0.515399375184595**, 판정 **0.5379037851325068**; seed2026 argmax **0.5157166887155967**, 판정 **0.536550471968573**. 두 판정 평균 **0.5372271285505399**. README 정의와 일치한다.
- 005 저장 variants JSON: L0 OOF 판정 **0.5111694690141018**, L_T5 **0.5248333424761751**, L_all **0.5362604749649567** 확인. fold 평균과 합친 OOF F1은 서로 다른 계산이다. 수치가 저장 문서와 일치한다는 사실이 평가 설계 적합성까지 증명하지 않는다.
- 역사 production T5 CSV의 신규 926척 전부 NaN 재현(H2). 원자료 전체 재읽기·T5 재생성·학습 없음.

## 5. 최신 평가 경계에 대한 독립 간단 검토

부모 요청으로 Astra의 최신 검토를 받고 해당 코드 줄을 직접 읽었다. 역사 129경로의 읽기 목록은 그대로 보존하며 다음은 별도 보조 검토다. 새 모델 실행 없이 split CSV 집합 연산과 선택 코드의 자료 흐름만 확인했다.

1. **pooled INNER 전역 선택은 fold-local OUTER 평가를 보존하지 않는다.** 외부 작업 루트 `D:/repos/fishing-track-classification/11월 4일/code/08_final_ensemble_20261104.py:228-231`은 fold별 INNER/OUTER를 합치고 `:255-275`는 통발 배수·혼합 α·전체 가중치를 합친 INNER 정답으로 선택한다. `26_11_4/work/상한선_011/code/S6_large_capacity_model.py:176-195`도 같은 전역 w 선택이다. 팀원 `development_roles_wide.csv`를 이번 검토에서 직접 집계하니 INNER 합집합 **2,121척**이고, OUTER fold별 교집합은 **699/1,966, 716/1,966, 706/1,965**, 총 **2,121/5,897**이다. 즉 어떤 fold의 OUTER 정답이 다른 fold의 INNER 역할로 전역 선택에 소비된다. 같은 fold의 FIT 학습 누수와 구분되는 **fold 사이 선택 누수**다. 그 선택을 고정한 채 계산하는 bootstrap CI는 이 오염을 제거하지 않는다.
2. **S4의 ID·정답 일치 assert는 확률 출처를 보장하지 않는다.** `26_11_4/work/상한선_011/code/S4_model_oracle.py:183-203`은 각 fold INNER ID를 모은 다음 seed별 OUTER OOF 파일을 ID 하나로 조회한다. 같은 ID의 정답이 일치해도 해당 확률을 생성한 fold·FIT·전처리 사전은 원하는 INNER 모델과 다를 수 있다. fold별 `inner_predictions.csv`를 쓰거나 동등한 생성 계보를 검증하기 전에는 S4의 INNER 기반 모델·oracle 대조 해석을 확정할 수 없다.
3. **S6 채택 조건에 짧은 이력 guard가 없다.** `S6_large_capacity_model.py:219-230`의 `passed`는 전체 Δ≥0.005, CI 하한>0, 최대 클래스 F1 하락≤0.01만 검사한다. 사전 계약에 1~7일 보호 조건이 있다면 현재 `passed`는 전체 계약 통과를 뜻하지 않는다. 단기군 결과와 동일 프로토콜 baseline을 포함해야 한다.

따라서 Astra의 순서인 **증거 동결 → fold·ID·role·생성모델 계보 감사 → 각 fold 자신의 INNER에서만 선택하고 자신의 OUTER에 적용 → 같은 baseline·보호 조건·분모로 paired 재평가**는 타당하다. 기준선도 pooled 선택을 했다면 동일하게 재평가해야 한다. 이는 모델 성능이 반드시 낮아진다는 예측이 아니라, 현재 숫자를 확정 채택 근거로 쓰기 전에 해결해야 할 평가 계약 문제다. 최종 모델 채택과 새 실험 범위 판단은 Astra/부모가 통합한다.

## 6. 읽기 목록과 제외

배정 문서의 경로·SHA-256·행 수·완독 방식 및 동일본문 대응은 아래 자동 생성 목록과 `sol_read_paths.json`에 남긴다. 범위 안 `.md/.txt`는 모두 포함했다. 원자료·CSV/Parquet/NPZ/모델 바이너리 전체, 가상환경·vendor, PDF는 문서 완독 대상에서 제외했다. 단, 위 최소 검산에 명시한 작은 CSV/JSON과 코드 일부를 보조 증거로 읽었다. AGENTS.md는 작업 지침으로 별도 읽었다.

129 document paths; 123 unique SHA-256 contents.

- [29-30일 모델 심층 분석/30일/cycle3_tasks_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/30일/cycle3_tasks_20261030.md>) (298 lines)
- [29-30일 모델 심층 분석/30일/cycle4_tasks_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/30일/cycle4_tasks_20261030.md>) (174 lines)
- [29-30일 모델 심층 분석/30일/cycle4_trip_tasks_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/30일/cycle4_trip_tasks_20261030.md>) (264 lines)
- [29-30일 모델 심층 분석/30일/어선항적_2차후속_진행상황_쉬운해설_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/30일/어선항적_2차후속_진행상황_쉬운해설_20261030.md>) (677 lines)
- [29-30일 모델 심층 분석/30일/어선항적_2차후속_최종정리_및_향후과제_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/30일/어선항적_2차후속_최종정리_및_향후과제_20261030.md>) (117 lines)
- [29-30일 모델 심층 분석/30일/할일_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/30일/할일_20261030.md>) (67 lines)
- [29-30일 모델 심층 분석/31일/_handoff/EXECUTOR_PROMPT.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/EXECUTOR_PROMPT.md>) (110 lines)
- [29-30일 모델 심층 분석/31일/_handoff/NOTICE_20261031_gemini.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/NOTICE_20261031_gemini.md>) (37 lines)
- [29-30일 모델 심층 분석/31일/_handoff/README.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/README.md>) (89 lines)
- [29-30일 모델 심층 분석/31일/_handoff/REVIEWER_PROMPT.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/REVIEWER_PROMPT.md>) (60 lines)
- [29-30일 모델 심층 분석/31일/_handoff/STATUS.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/STATUS.md>) (5 lines)
- [29-30일 모델 심층 분석/31일/_handoff/inbox/001_remeasure_R0-R7.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/inbox/001_remeasure_R0-R7.md>) (45 lines)
- [29-30일 모델 심층 분석/31일/_handoff/inbox/002_remeasure_R6b_R8-R14.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/inbox/002_remeasure_R6b_R8-R14.md>) (40 lines)
- [29-30일 모델 심층 분석/31일/_handoff/inbox/003_cycle4_revision_proposal.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/inbox/003_cycle4_revision_proposal.md>) (48 lines)
- [29-30일 모델 심층 분석/31일/_handoff/inbox/004_cycle4_featAC.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/inbox/004_cycle4_featAC.md>) (63 lines)
- [29-30일 모델 심층 분석/31일/_handoff/inbox/005_F156_merge_T5.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/inbox/005_F156_merge_T5.md>) (54 lines)
- [29-30일 모델 심층 분석/31일/_handoff/outbox/001_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/outbox/001_report.md>) (78 lines)
- [29-30일 모델 심층 분석/31일/_handoff/outbox/002_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/outbox/002_report.md>) (68 lines)
- [29-30일 모델 심층 분석/31일/_handoff/outbox/003_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/outbox/003_report.md>) (41 lines)
- [29-30일 모델 심층 분석/31일/_handoff/outbox/004_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/outbox/004_report.md>) (55 lines)
- [29-30일 모델 심층 분석/31일/_handoff/outbox/005_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/outbox/005_report.md>) (68 lines)
- [29-30일 모델 심층 분석/31일/_handoff/outbox/006_migrate_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/outbox/006_migrate_report.md>) (85 lines)
- [29-30일 모델 심층 분석/31일/_handoff/progress/002.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/progress/002.md>) (37 lines)
- [29-30일 모델 심층 분석/31일/_handoff/progress/004.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/progress/004.md>) (30 lines)
- [29-30일 모델 심층 분석/31일/_handoff/progress/005.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/progress/005.md>) (17 lines)
- [29-30일 모델 심층 분석/31일/_handoff/reviewer_log.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/reviewer_log.md>) (11 lines)
- [29-30일 모델 심층 분석/31일/_handoff/reviews/001_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/reviews/001_review.md>) (43 lines)
- [29-30일 모델 심층 분석/31일/_handoff/reviews/002_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/reviews/002_review.md>) (51 lines)
- [29-30일 모델 심층 분석/31일/_handoff/reviews/003_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/reviews/003_review.md>) (25 lines)
- [29-30일 모델 심층 분석/31일/_handoff/reviews/004_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/reviews/004_review.md>) (22 lines)
- [29-30일 모델 심층 분석/31일/_handoff/재시작_안내.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/_handoff/재시작_안내.md>) (46 lines)
- [29-30일 모델 심층 분석/31일/data_remeasure_20261031.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/data_remeasure_20261031.md>) (195 lines)
- [29-30일 모델 심층 분석/31일/docs/Claude_응답_gemini.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/docs/Claude_응답_gemini.md>) (36 lines)
- [29-30일 모델 심층 분석/31일/docs/remeasure_20261031.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/docs/remeasure_20261031.md>) (221 lines)
- [29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/README_먼저읽기.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/README_먼저읽기.md>) (40 lines)
- [29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/docs/기본특징설명.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/docs/기본특징설명.md>) (393 lines)
- [29-30일 모델 심층 분석/_handoff/EXECUTOR_PROMPT.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/EXECUTOR_PROMPT.md>) (64 lines)
- [29-30일 모델 심층 분석/_handoff/README.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/README.md>) (82 lines)
- [29-30일 모델 심층 분석/_handoff/STATUS.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/STATUS.md>) (5 lines)
- [29-30일 모델 심층 분석/_handoff/inbox/001_report_tasks_1-3.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/inbox/001_report_tasks_1-3.md>) (20 lines)
- [29-30일 모델 심층 분석/_handoff/inbox/002_task4.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/inbox/002_task4.md>) (60 lines)
- [29-30일 모델 심층 분석/_handoff/inbox/003_task5-6.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/inbox/003_task5-6.md>) (88 lines)
- [29-30일 모델 심층 분석/_handoff/inbox/004_task5redo-7.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/inbox/004_task5redo-7.md>) (79 lines)
- [29-30일 모델 심층 분석/_handoff/inbox/005_summary.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/inbox/005_summary.md>) (65 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/001_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/001_report.md>) (101 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/002_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/002_report.md>) (85 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/003_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/003_report.md>) (86 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/004_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/004_report.md>) (84 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/005_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/005_report.md>) (58 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/cycle3_0_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/cycle3_0_report.md>) (28 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/cycle3_2_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/cycle3_2_report.md>) (29 lines)
- [29-30일 모델 심층 분석/_handoff/outbox/cycle3_3_report.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/outbox/cycle3_3_report.md>) (33 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/001_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/001_review.md>) (56 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/002_mlsf_rank.txt](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/002_mlsf_rank.txt>) (10 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/002_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/002_review.md>) (75 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/003_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/003_review.md>) (62 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/003_verify.txt](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/003_verify.txt>) (8 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/004_review.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/004_review.md>) (74 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/004_verify.txt](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/004_verify.txt>) (20 lines)
- [29-30일 모델 심층 분석/_handoff/reviews/final_pr_reweight_check.txt](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/_handoff/reviews/final_pr_reweight_check.txt>) (17 lines)
- [29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-29_23-30_연결안내.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-29_23-30_연결안내.md>) (17 lines)
- [29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_00-05_응답_001.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_00-05_응답_001.md>) (31 lines)
- [29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_00-35_응답_C005.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_00-35_응답_C005.md>) (8 lines)
- [29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_01-15_응답_002.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_01-15_응답_002.md>) (24 lines)
- [29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_08-05_응답_003.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_08-05_응답_003.md>) (21 lines)
- [29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_08-50_응답_004.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/Claude_응답/2026-10-30_08-50_응답_004.md>) (25 lines)
- [29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-29_23-21-32_코치의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-29_23-21-32_코치의견.md>) (41 lines)
- [29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-29_23-48-27_코치의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-29_23-48-27_코치의견.md>) (31 lines)
- [29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_00-17-35_코치의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_00-17-35_코치의견.md>) (22 lines)
- [29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_00-48-22_코치의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_00-48-22_코치의견.md>) (17 lines)
- [29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_01-17-36_코치의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_01-17-36_코치의견.md>) (31 lines)
- [29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_01-48-13_코치의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/기록/2026-10-30_01-48-13_코치의견.md>) (5 lines)
- [29-30일 모델 심층 분석/gpt의 의견/문제점과_분석정리_20261030/01_현재_문제점.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/문제점과_분석정리_20261030/01_현재_문제점.md>) (129 lines)
- [29-30일 모델 심층 분석/gpt의 의견/문제점과_분석정리_20261030/02_지금까지_분석한_내용.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/문제점과_분석정리_20261030/02_지금까지_분석한_내용.md>) (171 lines)
- [29-30일 모델 심층 분석/gpt의 의견/문제점과_분석정리_20261030/README.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/문제점과_분석정리_20261030/README.md>) (8 lines)
- [29-30일 모델 심층 분석/gpt의 의견/운영안내.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/운영안내.md>) (46 lines)
- [29-30일 모델 심층 분석/gpt의 의견/현재 코치 의견.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/gpt의 의견/현재 코치 의견.md>) (39 lines)
- [29-30일 모델 심층 분석/분석 결과/README.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/README.md>) (113 lines)
- [29-30일 모델 심층 분석/분석 결과/cycle2_followup_tasks.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/cycle2_followup_tasks.md>) (190 lines)
- [29-30일 모델 심층 분석/분석 결과/cycle3_tasks_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/cycle3_tasks_20261030.md>) (298 lines) - same content as: `29-30일 모델 심층 분석/30일/cycle3_tasks_20261030.md`
- [29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_4_zero_prob_20261030_정정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_4_zero_prob_20261030_정정전.md>) (115 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_5_calibration_20261030_BLOCKED판.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_5_calibration_20261030_BLOCKED판.md>) (76 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_6_trap_binary_20261030_정정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_6_trap_binary_20261030_정정전.md>) (94 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_7_agg_2x2_20261030_정정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_followup_7_agg_2x2_20261030_정정전.md>) (97 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_prediction_diagnostics_20261029_20261030_정정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_prediction_diagnostics_20261029_20261030_정정전.md>) (228 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_prediction_diagnostics_20261029_작업2이전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_prediction_diagnostics_20261029_작업2이전.md>) (228 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/remeasure_20261031_001.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/remeasure_20261031_001.md>) (114 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/remeasure_20261031_002수정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/remeasure_20261031_002수정전.md>) (115 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/remeasure_20261031_003수정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/remeasure_20261031_003수정전.md>) (132 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/어선항적_2차모델결과_총정리_해설_20261029_작업2이전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/어선항적_2차모델결과_총정리_해설_20261029_작업2이전.md>) (256 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/archive/어선항적_2차모델결과_총정리_해설_20261030_정정전.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/archive/어선항적_2차모델결과_총정리_해설_20261030_정정전.md>) (276 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_development_ablation_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_development_ablation_20261029.md>) (173 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_1_provenance.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_1_provenance.md>) (108 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_3_rerun.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_3_rerun.md>) (116 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_4_zero_prob.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_4_zero_prob.md>) (131 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_5_calibration.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_5_calibration.md>) (97 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_6_trap_binary.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_6_trap_binary.md>) (94 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_7_agg_2x2.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_7_agg_2x2.md>) (107 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_summary.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_followup_summary.md>) (117 lines) - same content as: `29-30일 모델 심층 분석/30일/어선항적_2차후속_최종정리_및_향후과제_20261030.md`
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_prediction_diagnostics_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_prediction_diagnostics_20261029.md>) (230 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle2_summary_audit_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle2_summary_audit_20261029.md>) (91 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle3_2_exclusion.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle3_2_exclusion.md>) (49 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle3_3_error_trace.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle3_3_error_trace.md>) (94 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle3_progress_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle3_progress_20261030.md>) (343 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_0_testA_setup.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_0_testA_setup.md>) (48 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_1_baseline.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_1_baseline.md>) (34 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_2_bd.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_2_bd.md>) (44 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_3_featAC.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_3_featAC.md>) (82 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_data_status_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_data_status_20261030.md>) (76 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_revision_proposal_20261101.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_revision_proposal_20261101.md>) (33 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/cycle4_summary.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/cycle4_summary.md>) (58 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/f156_merge_20261101.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/f156_merge_20261101.md>) (110 lines)
- [29-30일 모델 심층 분석/분석 결과/docs/remeasure_20261031.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/docs/remeasure_20261031.md>) (124 lines)
- [29-30일 모델 심층 분석/분석 결과/검토_개선방안_20261029-2차.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/검토_개선방안_20261029-2차.md>) (134 lines)
- [29-30일 모델 심층 분석/분석 결과/어선항적_1차모델결과_총정리_해설.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/어선항적_1차모델결과_총정리_해설.md>) (168 lines)
- [29-30일 모델 심층 분석/분석 결과/어선항적_2차모델결과_총정리_해설.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/어선항적_2차모델결과_총정리_해설.md>) (278 lines)
- [_handoff/EXECUTOR_PROMPT.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/_handoff/EXECUTOR_PROMPT.md>) (7 lines)
- [_handoff/README.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/_handoff/README.md>) (5 lines)
- [_handoff/STATUS.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/_handoff/STATUS.md>) (4 lines)
- [_handoff/inbox/001_tasks_1-2.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/_handoff/inbox/001_tasks_1-2.md>) (5 lines)
- [docs/cycle2_development_ablation_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/cycle2_development_ablation_20261029.md>) (173 lines) - same content as: `29-30일 모델 심층 분석/분석 결과/docs/cycle2_development_ablation_20261029.md`
- [docs/cycle2_followup_tasks.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/cycle2_followup_tasks.md>) (187 lines)
- [docs/cycle2_prediction_diagnostics_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/cycle2_prediction_diagnostics_20261029.md>) (228 lines) - same content as: `29-30일 모델 심층 분석/분석 결과/docs/archive/cycle2_prediction_diagnostics_20261029_작업2이전.md`
- [docs/cycle2_summary_audit_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/cycle2_summary_audit_20261029.md>) (91 lines) - same content as: `29-30일 모델 심층 분석/분석 결과/docs/cycle2_summary_audit_20261029.md`
- [docs/cycle4_tasks_20261030.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/cycle4_tasks_20261030.md>) (174 lines) - same content as: `29-30일 모델 심층 분석/30일/cycle4_tasks_20261030.md`
- [docs/fishing_evaluation_cycle_results_20261028.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/fishing_evaluation_cycle_results_20261028.md>) (192 lines)
- [docs/fishing_report_updated_20261028.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/fishing_report_updated_20261028.md>) (356 lines)
- [docs/real_accuracy_diagnosis_and_evaluation_history_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/real_accuracy_diagnosis_and_evaluation_history_20261029.md>) (302 lines)
- [docs/어선항적_전체진행과_실제모델성능_통합정리_20261029.md](<D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/docs/어선항적_전체진행과_실제모델성능_통합정리_20261029.md>) (215 lines)
