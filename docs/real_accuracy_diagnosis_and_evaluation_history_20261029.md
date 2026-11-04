# 실제 조업 분류 정확도 진단과 평가 연혁 — 2026-10-29

대상: 본인 학습자용 기술·평가 설명  
범위: 2026-10-12 S0 합성 교육 실험부터 2026-10-29 실제자료 내부 holdout 독립 감사까지  
현재 판단: 사전 정의한 상대 개선 기준은 통과했지만, 통발을 평가가능 204척 중 0척 맞혀 실무 분류기로 준비되지 않았다. 이 결과는 실제 조업 분류가 시도된 연구용 내부 평가이지 공식 Test A 성능, 사고 탐지 성능 또는 현장 운항 검증이 아니다.

## 1. 이 기록을 읽을 때 먼저 기억할 점

모델의 정확도는 평가 분모를 함께 읽어야 한다. 평가가능한 1,453척만 비교하면 후보 ExtraTrees 정확도는 49.8968%(725정답/728오류), 다수 클래스 상수 예측은 49.6903%(722정답)다. 후보의 순증은 3척뿐이다. 최종 roster 1,473척 전체에서는 후보가 유보한 20척을 오답으로 세므로 후보 정확도는 49.2193%가 된다. 같은 전체 분모에서 항상 연안복합을 내는 상수 기준은 49.5587%(730/1,473)로 후보보다 높다. 따라서 “조건부 정확도는 조금 개선됐다”와 “전체 선박을 다룰 때 다수 상수 기준을 이겼다”는 서로 다른 문장이다.

Macro F1은 16.68997%에서 29.95753%로 13.26756%p 올랐고, 선박 층화 paired bootstrap 95% 구간은 +8.53713~+17.56736%p다. 이 상대 개선은 사전 기준 통과를 뜻한다. 절대 분류 수준은 낮다. 통발 recall은 0/204이고, 모델이 통발로 예측한 6척도 모두 오답이다. 이 사실 때문에 결과의 적절한 결론은 “조건에 맞춰 유의미한 상대 개선이 관찰됐지만 실제 적용 준비는 미달”이다.

이 문서는 세 종류의 문장을 구분한다.

- **확인 사실**: 파일, 고정 protocol, 저장 예측, 재계산 결과에서 직접 확인한 값.
- **원인 가설**: 후속 실험으로 검증할 수 있는 설명. 관찰만으로 원인이라고 확정하지 않는다.
- **미확인**: 현재 데이터나 실험으로 답할 수 없는 조건.

## 2. 실험의 연혁: 합성 성과에서 실제자료 내부평가로

### 2026-10-12 — S0 교육용 합성 시스템

사용자가 실제자료 확보 전 모델·시스템·시각화의 작은 전체 흐름을 만들고, 수식·코드·과적합 방지를 설명해 달라고 요청했다. 이에 직진형·굴곡형·회전형 합성 경로를 S0 실험으로 만들었다. 이 이름은 생성기에서 붙인 경로 유형이며 공식 fishing code나 실제 조업 라벨이 아니다. S0의 목적은 코드 흐름과 학습 절차를 익히는 것이었고 실제 어선 분류 성능을 입증하는 것이 아니었다.

### 2026-10-26 — 합성 shape9로 반복 개선

기존 8기하 특징 모델을 기준으로 shape7, shape9, shape15 구성을 같은 개발 조건에서 비교했다. 전체 길이 특징을 없앤 shape7은 조건 변화에서 나빠졌고, 9개 형상 특징을 쓴 shape9 MLP가 미리 정한 합성 개발·최종 기준을 통과했다. 최종 10개 합성 seed에서 조건 변화 Macro F1은 기존 0.5566에서 0.6634로 개선됐다. 그래도 이는 고정 생성기 및 가상 교란에서의 결과다. 실제 조업 class, 실제 해역 또는 사고 여부의 정답으로 해석할 수 없다.

### 2026-10-27 — shape9 비판 감사와 비교

사용자가 제기한 학습 종료, 결측 mask, 표본 수, 온도 보정, 학습 연장, L2, 선형·트리와 시간 특징 문제를 합성 자료에서 감사했다. 기존 모델 파일 해시·데이터 해시를 확인하고, 고정 비교 계약에 따라 MLP·선형·ExtraTrees 및 합성 시간·보폭 대조군을 비교했다. 개발에서 formal 적격 후보는 없었고, 최종 비교는 사전 고정한 보조 분석으로 보고했다. 이 단계에서 나온 모델 차이는 실제 CSV의 특징 계약과 조업 라벨 평가가 아니다.

### 2026-10-28~29 — 실제 CSV 점검, 교정, 학습 및 최종 잠금

실제 CSV 12개를 확인한 뒤, 공식 설명에서 X=경도, Y=위도, 행의 단위가 선박·일자·시간대이고 Train의 `fishing_code`가 조업 정답임을 확인했다. 정확 EPSG/datum, 점별 시각, 간격 계약은 확인되지 않았다.

스트리밍 메타데이터 점검에서 Train 6개 파일은 파싱 종료·EOF hash 확인을 통과했다. Test 계열 6월 파일은 CSV parse error로 조기 종료되어 전체 행이 검사되지 않았다. v1 byte counter/hash EOF 집계 오류도 뒤늦게 확인되어, 12개 합계 11,834,630,398 bytes는 원본 파일 크기 합이지 실제로 모두 읽고 hash한 바이트라고 주장하지 않는다.

특징 캐시에서 두 가지 수정을 했다. 첫째, 폴더 이름을 월로 읽어 모든 샘플이 1월이라고 표시되던 버그를 basename·원본 날짜를 기준으로 고쳤다. 둘째, Train 6월 file ordinal 5 / data record ordinal 127,862의 날짜·시간·geometry 구조 오류 행을 라벨 불일치와 함께 격리했다. 이 행의 원문 라벨·ID·좌표는 문서에 공개하지 않는다. 빈 라벨 행 1개는 별도 집계이며 위치를 알 수 없어 이 격리 행과 합치거나 추정하지 않았다. 원본 CSV와 v1 SQLite는 수정하지 않았다. 정정 캐시는 root 독립 검사를 통과했다.

실제 학습 전 fixed protocol은 후보, 선박 단위 분할, 선택/보정/최종 역할, seed, 적격/성공 기준을 고정했다. 개발 단계에서 5개 조건(4개 후보와 degree-control baseline)을 세 split × 두 initialization으로 **30회 적합**하고 개발 결과에서 ExtraTrees를 선택·동결했다. 이후 final에서 기준 R0와 선택 ExtraTrees를 두 initialization으로 각각 적합해 **4회** 실행했다. 합계는 34 fit이다. run evidence의 실제 수행 시각은 2026-10-29 한국시간 02:40:52~02:45:35(UTC로는 2026-10-28 17:40:52~17:45:35), 282.31초다. 산출 경로명 `evaluation_cycle_20261028`의 날짜는 주기/고정 계약 이름이지 final 실행의 현지 날짜가 아니다. final 이후 새 학습이나 final 재선택은 하지 않았다. 최종 예측의 독립 지표 재계산·분할 계보 감사와 저장 모델 재추론 검증에서 결과 차이는 0이었다. 연혁과 역할은 [감독 기록](evaluation_cycle_supervision_20261028.md), 고정 조건은 [실험 계약](real_model_cycle_protocol_20261028.md), 최종 판정은 [감독 최종 검토](real_model_cycle_final_review_20261029.md)를 참조한다.

## 3. 데이터와 분모: 각 숫자가 세는 대상

| 단계 | 규모와 분모 | 설명 |
| --- | ---: | --- |
| Train CSV 파서 처리 | 3,887,069행 | 여섯 Train 파일의 파서가 처리한 행. 네 공개 클래스 행은 합 3,887,067이며 unknown 구조오염 1행과 빈 라벨 1행은 구분된다. |
| 공식 Train 라벨 행 | 연안복합 1,682,455 / 자망 1,422,675 / 통발 601,059 / 채낚기연승낚시 180,878 | 행 단위 원자료 분포. 선박별 model split support와 같은 분모가 아니다. |
| 일관 라벨 Train 선박 | 7,372척 | 유일한 비어 있지 않은 조업 라벨을 가진 선박. 클래스별로 연안복합 3,650, 자망 2,520, 통발 1,044, 채낚기연승낚시 158척이다. |
| 해시로 선택된 특징 행 | 129,142행 | 매 Train 월 파일에서 선박별 hash 순위 상위 최대 4행. 최대 24행/선박/6개월이며 형상 계산은 이 선택 subset에만 수행했다. |
| 선택 행 geometry 유효성 | 115,300 유효 / 13,842 유보 | 유보 사유는 길이 0. 90척은 유효 행이 한 개도 없어 전체 roster에서 유지한 채 예측을 abstain했다. |
| final holdout roster | 1,473척 | 클래스를 층화해 잠근 final 선박. 정답 support는 순서상 채낚기 31, 통발 208, 자망 504, 연안복합 730척이다. |
| final scorable | 1,453척 | 선택 후보와 baseline이 함께 확률을 낼 수 있는 공통 분모. support는 채낚기 29, 통발 204, 자망 498, 연안복합 722척이다. 나머지 20척은 abstain이다. |

클래스 순서는 모든 혼동행렬·확률을 읽을 때 **채낚기연승낚시, 통발, 자망, 연안복합**이다. 숫자가 붙은 단계가 서로 다른 질문을 답한다. 행 수는 한 선박이 여러 날짜·시간대에 관측된 수이고, 선박 수는 분류 단위이며, 129,142는 geometry가 제한적으로 검사된 원본 선택 행 수, 1,453은 final 성능 지표의 선박 수다. 이 분모를 서로 바꾸어 읽지 않는다.

제출 템플릿에서 읽은 Test A 100 ID 중 91개, Test B 100 ID 중 95개가 labeled Train과 겹쳤다. 파싱된 무라벨 선박과도 높은 overlap이 확인됐다. 파일명과 템플릿만으로 공식 Test A가 실제 신규 선박 분할인지 확정할 수 없고, Test 6월 파일도 완전 검사되지 않았다. 이번 final은 그 미확인 제출 분할을 평가한 점수가 아니다. [ID 교차 감사](../outputs/submission_id_coverage_audit_20261029.json)를 참조한다.

## 4. shape9에서 36분포·72입력으로

실제 기하는 각 선택 레코드 안에서 관측점 평균 `(lon0, lat0)`을 원점으로 둔 연구용 접평면 좌표로 변환했다.

```text
x = (lon − lon0) × π/180 × cos(lat0 × π/180)
y = (lat − lat0) × π/180
```

지구반경을 곱하지 않으므로 값은 미터가 아니다. 정확 datum/EPSG가 미확정이고 점마다 시각이 없어서 실제 거리·속력·가속도를 계산할 수 없다. 부분선 끝을 다음 부분선 시작과 연결하지 않았다. 20도 초과 spatial span, 평균 위도 85도 초과, 유한 범위 밖 등의 geometry 조건은 유보된다.

각 레코드에서 계산한 아홉 무시간 특징은 다음과 같다.

| feature | 계산 의미 |
| --- | --- |
| `mean_part_straightness` | 각 부분선의 끝점 직선거리 ÷ 부분선 길이 비율의 평균. 직선에 가까우면 1에 가깝다. |
| `mean_abs_turn_rad` | 연속된 0이 아닌 선분 방향 변화각의 절댓값 평균(라디안). |
| `turn_direction_concentration` | 방향 변화각의 signed 합 절댓값 ÷ 절댓값 합. 한 방향으로 누적되면 커진다. |
| `std_turn_rad` | 부호 있는 방향 변화각의 모집단 표준편차. |
| `max_abs_turn_rad` | 관측된 방향 변화각 절댓값 중 최대. |
| `mean_part_spread_ratio` | 부분선별 좌표 공분산 고유값의 `sqrt(λmin/λmax)`를 평균. 0에 가까우면 선형으로 길게 늘어진 형태다. |
| `mean_part_chord_deviation_ratio` | 각 부분선 점의 끝점 chord 이탈 중 최대 수직거리를 부분선 길이로 나눈 값의 평균. |
| `cloud_spread_ratio` | 모든 관측점을 모은 점 구름 공분산에서 `sqrt(λmin/λmax)`. 부분선 사이를 이동 경로로 잇지 않는다. |
| `cloud_radial_fourth_moment_ratio` | 중심에서 정규화된 거리 `r`의 `E[r⁴] / E[r²]²`. 점 구름 내 반경 분포의 꼬리·집중 형태를 요약한다. |

각 선박은 hash 표본으로 선택된 서로 다른 원자료 레코드 최대 24개를 갖고, 각 레코드에서 shape9 특징 한 묶음을 계산한다. 선박 분류기에는 레코드 개별값을 그대로 펼치지 않고 선박의 유효 행별 값에서 특징별 **평균 9 + 모집단 표준편차 9 + 25% 분위수 9 + 75% 분위수 9 = 36개**를 만든다. R0는 평균 9개만 쓴다. 나머지 distribution36 후보는 36개 요약을 쓴다.

36개 각각은 train에서만 중앙값 대치·표준화를 적합한다. 그 다음 원래 누락 여부를 나타내는 36개 binary mask를 붙여 **36개 값 + 36개 mask = 72개 입력**으로 만든다. 이 mask는 선택된 통계 특징 중 값이 관측됐는지 표시한다. 모델은 선박 hash, 조업 label, 월, 행수, clock time, 절대 좌표를 입력으로 받지 않는다. 방향 변화 특징은 WKT 안에서 연속된 점의 순서를 사용하지만, 별도 point timestamp나 속도·보폭 feature를 추가한 것은 아니다. baseline mean9의 입력은 9개 값 + 9개 mask = 18개다.

## 5. 고정 분할, 적합, 보정, 선택, 최종

### 분할 역할과 정수 정책

먼저 각 클래스 안에서 선박 hash를 `seed=20261028`로 정렬해 final을 잠갔다. 클래스별 final 수는 `max(2, floor(0.2 × n_class))`이며 나머지만 development에 남겼다. 개발의 세 분할 seed는 3201, 3202, 3203이다. 각 분할에서 train은 약 70%, validation은 `max(2, floor(0.15 × d))`, calibration은 `max(2, d − floor(0.7 × d) − validation)`으로 잡고, `d`는 final을 뺀 개발 클래스 수다. 모든 클래스 최소 2척 조건과 선박 중복 없음이 검사됐다.

실제 세 development split 각각에서 역할 roster는 train 4,127척, validation 884척, calibration 888척이었다. `valid geometry`가 없는 배는 역할 roster에는 남아 있지만, fit·확률 계산에서는 그 역할의 scorable mask로 제외된다. 그러므로 role roster와 학습/metric 분모는 다르다.

| split seed | role | roster | scorable fit/metric | abstain | scorable class support `[채낚기, 통발, 자망, 연안복합]` |
| ---: | --- | ---: | ---: | ---: | --- |
| 3201 | train | 4,127 | 4,077 | 50 | [86, 580, 1,395, 2,016] |
| 3201 | validation | 884 | 878 | 6 | [19, 125, 300, 434] |
| 3201 | calibration | 888 | 874 | 14 | [20, 126, 300, 428] |
| 3202 | train | 4,127 | 4,079 | 48 | [86, 581, 1,399, 2,013] |
| 3202 | validation | 884 | 874 | 10 | [19, 125, 295, 435] |
| 3202 | calibration | 888 | 876 | 12 | [20, 125, 301, 430] |
| 3203 | train | 4,127 | 4,075 | 52 | [87, 582, 1,394, 2,012] |
| 3203 | validation | 884 | 876 | 8 | [19, 124, 300, 433] |
| 3203 | calibration | 888 | 878 | 10 | [19, 125, 301, 433] |

세 split은 다른 hash 배치지만 같은 전체 선박 모집단을 사용하므로, 결과를 서로 독립인 세 연구로 취급하지 않는다. final 1,473척은 모델·전처리·온도 선택을 전부 끝내고 freeze한 뒤 1회 비교했다. 최종 적합은 사전 선택한 seed3201의 train/validation/calibration 역할을 사용했다.

### 4개 후보

| 코드 | 입력·모델 | 고정 조건 |
| --- | --- | --- |
| R0 `mean9_mlp16` | 평균 shape9 9개 + mask 9개 | MLP hidden 16, L2 0.01, 최대 400 epoch |
| R1 `distribution36_mlp16` | distribution36 + mask 36개 | MLP hidden 16, L2 0.01, 최대 400 epoch |
| R2 `distribution36_linear` | 같은 distribution36+mask | hidden 없이 선형 classifier, L2 0.01, 최대 400 epoch |
| R2 `distribution36_extratrees256_leaf2` | 같은 distribution36+mask | ExtraTrees 256개, `min_samples_leaf=2`, `max_features=1.0`, class weight 없음, 단일 worker |

실제 라벨은 네 class라 출력층 차원은 4다. 실제 R0 MLP는 `18 → 16 → 4`로 372개 parameter, distribution36 MLP는 `72 → 16 → 4`로 1,236개, 선형 후보 `72 → 4`는 292개다. 합성 shape9의 3-class `18 → 16 → 3` MLP에 있던 355개 parameter를 실제 모델의 크기로 옮겨 쓰면 안 된다. ExtraTrees의 모델 크기는 각 트리의 분할 결과로 정해져 dense-layer parameter 수와 같은 방식으로 세지 않는다.

MLP·linear는 NumPy full-batch gradient descent, learning rate 0.03, patience 35, validation NLL 최저 checkpoint로 적합했다. 한 epoch는 유효한 train 선박 전체에 대한 한 번의 full-batch gradient update다. 학습 objective는 `train NLL + (λ/2) × Σ(weight²)`이며 `λ=.01`, bias는 L2 합산에서 제외된다. 저장된 `train_nll` 이력에는 L2 항이 들어 있지 않고, validation checkpoint도 정규화 없는 validation NLL을 최소화한다. 결측 대치·표준화 통계는 각 후보의 train subset에서만 계산했다. 각 fit seed 42와 137 모델은 calibration set에서 별도 양의 온도를 fit해 확률 보정했다. 고정 temperature grid는 .1~10의 81개 `geomspace` 값이며 T=1이 그 안에 포함된다. 탐색은 이 81개 값에서 calibration NLL이 엄격히 더 낮은 온도를 선택하고, T=1을 기준값으로 보장한다. 두 초기화의 calibrated probability를 평균했다. Tree는 class index 순서를 검사하고 확률에 `log(clip(p, 1e−15, 1))`를 적용해 같은 방식으로 보정했다.

### 개발 선택 기준과 네 후보의 수치

R0 대비 개발 3분할 평균에서 Macro F1 개선이 +0.03 이상, accuracy 차이가 −0.01 이상, NLL 차이가 +0.02 이하, Brier 차이가 +0.01 이하이고, 세 분할 중 적어도 두 개에서 Macro F1 차이가 양수이며 같은 유효 분모여야 적격이었다. 적격 후보는 평균 Macro F1 개선, NLL, 선언 순서로 고정된 tie-break를 따른다.

| 후보 | Macro F1 | Accuracy | NLL | Brier | R0 대비 Macro F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| R0 mean9 MLP16 | 0.1660745268 | 0.4950532566 | 1.0576296810 | 0.6138149052 | 기준 |
| R1 distribution36 MLP16 | 0.1740484065 | 0.4927796981 | 1.0526618333 | 0.6104023618 | +0.0079738798 |
| R2 distribution36 linear | 0.1937288090 | 0.4973381071 | 1.0696480788 | 0.6163771925 | +0.0276542823 |
| R2 distribution36 ExtraTrees | **0.3357530148** | 0.4889736523 | 1.0385256164 | 0.6090193203 | **+0.1696784881** |

R1은 F1 개선 크기, R2 linear는 +0.03 최소선에서 적격이 아니었다. ExtraTrees는 다른 개발 기준도 충족해 유일하게 적격이었다. ExtraTrees의 개발 accuracy 차이는 −0.0060796, NLL 차이는 −0.0191041, Brier 차이는 −0.0047956이었다. 모델을 최종 성능을 본 뒤 바꾸지 않고 개발 선택을 동결했다.

### final 성공 기준과 결과

final 확인적 성공 기준은 Macro F1 개선 ≥+0.03, accuracy 차이 ≥−0.01, NLL 차이 ≤+0.02, Brier 차이 ≤+0.01, 같은 scoring 분모, 클래스층화 paired 선박 bootstrap 2,000회 95% 개선 하한 >0을 모두 만족하는 것이었다. 추가 1월 제외 진단에서 Macro F1 하락은 0.03 이내여야 했다. 실제 결과는 F1 +0.1326756, accuracy +0.0020647, NLL −0.0156187, Brier −0.0022130, bootstrap CI +0.0853713~+0.1756736, 1월 제외 F1 하락 −0.0194792로 사전 수치 조건을 모두 통과했다. 저장 final temperature는 R0 MLP의 init42/init137에서 .9440609/.8912509, ExtraTrees 두 초기화에서 각각 1.1885022였다.

최종 primary 비교 지표는 같은 scorable 1,453척에 대해 다음과 같다.

| 지표 | R0 baseline | 동결 ExtraTrees | 차이 |
| --- | ---: | ---: | ---: |
| Macro F1 | 0.1668996779 | 0.2995752738 | +0.1326755959 |
| Accuracy | 0.4969029594 | 0.4989676531 | +0.0020646937 |
| NLL | 1.0560091390 | 1.0403903992 | −0.0156187398 |
| Brier | 0.6132614033 | 0.6110484237 | −0.0022129795 |

**final 혼동행렬**의 행은 실제 정답, 열은 후보 예측이며, 이 표에는 scorable 1,453척만 포함한다.

| 실제 정답 / 예측 | 채낚기연승낚시 | 통발 | 자망 | 연안복합 | 실제 support |
| --- | ---: | ---: | ---: | ---: | ---: |
| 채낚기연승낚시 | 5 | 2 | 8 | 14 | 29 |
| 통발 | 4 | **0** | 43 | 157 | 204 |
| 자망 | 1 | 3 | 121 | 373 | 498 |
| 연안복합 | 1 | 1 | 121 | 599 | 722 |
| 예측 support | 11 | 6 | 293 | 1,143 | 1,453 |

| 실제 class | 정밀도 (precision) | 재현율 (recall) | F1 | 계산 |
| --- | ---: | ---: | ---: | --- |
| 채낚기연승낚시 | 45.45% | 17.24% | 0.25000 | TP 5, 예측 11, 실제 29 |
| 통발 | 0.00% | 0.00% | 0.00000 | TP 0, 예측 6, 실제 204 |
| 자망 | 41.30% | 24.30% | 0.30594 | TP 121, 예측 293, 실제 498 |
| 연안복합 | 52.41% | 82.96% | 0.64236 | TP 599, 예측 1,143, 실제 722 |

정답 수로 accuracy 차이를 분해하면 R0는 722/1,453, 후보는 725/1,453으로 순증이 3척이다(후보 오답 728척). 클래스별 정답 증감 `[채낚기연승낚시, 통발, 자망, 연안복합]`은 `[+5, 0, +120, −122]`이며 합계가 +3이다. 채낚기와 자망에서 정답이 합계 125척 증가했지만, 이 중 122척분이 연안복합 정답 감소로 상쇄되어 전체 accuracy 순증은 3척에 그쳤다. 이 분해는 관찰된 혼동 변화의 산술 요약이며, 클래스별 변화가 왜 생겼는지 인과를 설명하지 않는다.

final roster에는 유보 20척이 더 있다. 지원 수가 class 순으로 전체 31/208/504/730, 평가가능 29/204/498/722이므로 class별 유보는 2/4/6/8척이다. final 예측 분포는 채낚기 11, 통발 6, 자망 293, 연안복합 1,143척이다. R0는 연안복합 1,451척, 자망 2척으로 예측했다. 이 붕괴 양상과 Train class 불균형은 **함께 관찰된 사실**이지만, 불균형이 붕괴를 일으켰다고 이 비교만으로 인과를 증명하지는 않는다.

## 6. 확인 사실, 원인 가설, 미확인 사항

| 유형 | 현재 말할 수 있는 내용 | 여기서 넘어가면 안 되는 주장 |
| --- | --- | --- |
| 확인 사실 | final에서 후보는 통발 0/204, 연안복합 599/722를 맞혔다. 통발 예측 6건은 전부 오답이다. | 특정 선박의 점 좌표를 읽어 보지 않고 “해당 경로가 통발처럼 생겨서” 틀렸다고 설명하기. |
| 확인 사실 | Train 학습 split 지원이 class 순으로 86/580/1,395/2,016이며 불균형이다. R0는 예측 1,451/1,453개를 연안복합으로 냈다. | “class 불균형 때문에 collapse가 일어났다”는 단정. 불균형이 원인인지 추가 조작 실험이 필요하다. |
| 확인 사실 | shape 표본은 6개월 각 파일에서 선박별 최대 4개 행을 hash로 골랐다. record 내 점별 timestamp는 입력 특징에 없다. | “시간 간격 손실이 이번 오분류의 원인이다” 또는 “이 정도 표본이면 연간 항적을 대표한다”는 단정. |
| 확인 사실 | 수치 성공 기준과 1월 제외 진단은 통과했지만 전체 분모 accuracy는 다수 상수 예측보다 낮다. | “통계적 상대 개선이 있으니 현장 배치 가능”이라는 결론. |
| 원인 가설 | 불균형을 보정한 class weight/sampling이 통발·희소 class recall을 개선할 수 있다. | 아직 비교하지 않은 설정이 반드시 성능을 높인다고 가정하지 않는다. |
| 원인 가설 | 월당 4행 선택의 변동, 분포 요약의 정보 손실, 학습률·정규화·epoch 한도 등 optimizer 영향이 분류 차이에 관여할 수 있다. | 각 요인이 기여한 크기를 ablation 없이 설명하지 않는다. 특히 L2=.01, 최대 400 epoch 때문에 실패했다는 결론은 자료가 없다. |
| 원인 가설 | 실제 timestamp·시간 간격이 라벨 구분에 유용할 수 있다. | 현재 점별 시각이 없으므로 시간/보폭을 만들어 넣거나 기존 실패를 시간 누락으로 확정하지 않는다. |
| 원인 가설 | 일부 항적 창에 조업·이동·정박이 섞이거나 vessel-level fishing label과 시간대 행이 맞지 않을 가능성은 별도 domain audit 질문이다. | 공식 `fishing_code`가 조업형태 정답이라는 사실만으로 이 가설이 확인되거나 오류 원인이라는 뜻은 아니다. |
| 미확인 | exact EPSG/datum, 실제 좌표 기준계, 점별 수집 시각, 점 간 거리·시간, month별 대표성, 공식 Test A split 의미. | 경위도 범위만으로 WGS84 또는 정확한 좌표계라고 주장할 수 없다. |
| 미확인 | 각 선택 시간대 항적이 조업 중·이동 중·정박 중 어느 행동인지 별도 행동 정답으로 검증하지 않았다. | vessel class label을 각 점 또는 시간대의 행동 label로 간주하지 않는다. |
| 미확인 | Test 6월 전체 파싱, Test A/B 대회 성능, 사고와 항적의 확정 매핑, 사용자의 시스템 이해 성취. | 내부 holdout 결과를 공식 대회·사고·현장 성능으로 옮기지 않는다. |

### 학습 전에 고친 구현·자료 문제와 현재 성능의 분리

오염 라벨 행의 격리, 모든 월이 1월로 표시되던 파생 cache 오류, runner의 3-class 잔재·tree train-mask 정합성·`max_features` 값·degree-control 키 불일치는 **실제 model fit 전에** 수정하고 테스트/캐시 독립 검증했다. 이들은 초기 구현의 신뢰성 문제였으나 교정된 cache와 코드로 최종 평가했으므로, 현재 49.9% 조건부 정확도나 통발 0/204의 원인으로 열거할 수 없다. 오염 라벨 문자열이 원본 데이터에서 생긴 정확한 경로(원본 생성, 전송, CSV 해석)는 미확인이다. Test 6월 파싱 미완료와 공식 제출 ID overlap은 공식 외부 평가의 한계이며 이번 내부 holdout의 성능 원인이 아니다.

기준 모델 대비 확률 품질 지표 NLL 1.0560→1.0404, Brier 0.6133→0.6110도 소폭 개선했다. 이 모델 간 지표 차이는 온도 보정 자체의 효과와 구분해야 한다. 낮은 class별 recall 문제를 가려 주지는 않는다. 예측 abstention 20척과 전체 geometry 무효 90척도 denominator와 운영 coverage를 낮춘다.

## 7. 개발 진단 추가자료: 저장 학습 이력에서 읽을 수 있는 범위

약 739MB `development_model_audit.json`을 mmap 및 bounded decoding으로 선택 추출해 만든 [진단 summary JSON](../outputs/real_accuracy_diagnostic_summary_20261029.json)을 사용한다. 이 절차는 fit·pickle decode·model inference를 수행하지 않았다. summary는 source 크기 738,855,051 bytes, SHA-256 `40a94748d5e70fdce9cb656839cbf4997097e656076b46d084122b07e7b03914`인 development audit의 저장 값만 요약한다.

세 개발 seed × 두 초기화에 기록된 validation 결과를 먼저 보자. 아래는 각 저장 initialization의 validation 지표를 평균한 표다. split마다 두 초기화 확률을 먼저 평균한 뒤 지표를 계산한 공식 development 결과표와 집계 순서가 달라 수치가 같지 않다. 예를 들어 R0 individual-mean Macro F1은 .175923이지만 probability ensemble의 세 split 평균은 .166075이고, 개별평균 NLL은 1.060478, ensemble development NLL은 1.057630이다. 두 표는 다른 집계 질문에 답하므로 혼합하지 않는다.

| 모델 | raw val acc | raw val Macro F1 | raw val NLL | raw val Brier | temperature 범위 | calibrated val NLL | calibrated val Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 mean9 MLP16 | .494673 | .175923 | 1.063680 | .614987 | .8913~.9441 | 1.060478 | .615232 |
| R1 distribution36 MLP16 | .494676 | .182530 | 1.058187 | .611339 | .8913~.9441 | 1.054613 | .611549 |
| R2 distribution36 linear | .496197 | .198520 | 1.080540 | .617155 | .7943~.8414 | 1.071993 | .617309 |
| R2 distribution36 ExtraTrees | .489352 | .336696 | 1.037776 | .609748 | 1.0593~1.4962 | 1.040241 | .609915 |

양의 temperature scaling은 예측 확률의 확신 정도를 바꾸지만 이 기록에서는 후보별 validation hard-label accuracy·Macro F1이 raw와 calibrated 사이에서 같았다. ExtraTrees validation individual-mean NLL은 보정 전 1.037776에서 보정 후 1.040241로 오히려 증가했다. Calibration이 validation에서 항상 모든 지표를 개선하지 않는다. 온도 보정만으로 통발의 class recall 문제가 해결되었다고 말할 수 없다. ExtraTrees 개발 초기화별 온도는 3201/3202/3203에 따라 달랐고 범위가 1.0593~1.4962였다. 이를 초기화 간 불안정성의 확정 판정으로 쓰기보다 작은 calibration set에 의한 추정 변동을 추가 검토할 질문으로 남긴다.

| gradient로 학습된 모델 | best epoch 기록 범위 | 마지막 20개 기록(epoch 381→400)의 val NLL 변화 | validation−train NLL 차이 범위 | 해석 |
| --- | ---: | ---: | ---: | --- |
| R0 mean9 MLP16 | 400~400 | −.00143~−.00100 | −.00577~+.00545 | 최고 checkpoint가 400 epoch 한도에 닿았다. 끝부분 validation NLL은 조금 더 감소했으나 400 뒤 결과는 없다. |
| R1 distribution36 MLP16 | 400~400 | −.00171~−.00117 | −.00651~+.00561 | checkpoint가 한도에 닿았다. 기록된 범위에서 뚜렷한 train/val gap이나 validation 악화는 관찰되지 않는다. |
| R2 distribution36 linear | 400~400 | −.00243~−.00200 | +.00407~+.01300 | checkpoint가 한도에 닿았고 validation NLL은 마지막 구간에 조금 낮아졌다. 한도 이후 수렴 또는 성능을 알 수 없다. |
| R2 ExtraTrees | epoch 개념 없음 | — | — | 저장 history가 없으므로 epoch별 수렴 분석은 적용되지 않는다. |

R0/R1/linear의 18개 fit(세 개발 seed × 두 init × 세 gradient-trained 후보)은 모두 400 epoch 한도에서 best epoch를 기록했다. 대표적으로 R0의 **epoch 1(첫 full-batch update 직후) train NLL**은 1.4366~1.4798이었고 best train NLL은 1.0605~1.0668로 내려갔다. best validation NLL은 1.0573~1.0722, validation−train NLL gap은 −.00577~+.00545였다. 따라서 “학습이 전혀 안 됐다”거나 “발산했다”는 주장은 맞지 않으며, 현재 기록에서 큰 train/validation NLL 과적합 gap도 관찰되지 않는다. 다만 이 범위만으로 classwise 학습의 충분성은 알 수 없다.

R0 train NLL도 train label prior entropy 1.0740~1.0755에 가까운 값에서 끝난다. NLL 감소는 loss 학습이 진행됐음을 보여 주지만, 균형 분류를 잘 배웠다는 뜻은 아니다. class-prior 예측과 비슷한 확률 손실 수준이므로 풍부한 class 구분이 학습됐다는 증거는 약하다. Train accuracy/confusion은 저장되지 않아 train classwise 성능과 validation 간 classwise gap은 이 summary로 계산할 수 없다.

마지막 20개 history 기록의 첫 값(epoch 381)과 끝 값(epoch 400)을 비교하면 validation NLL이 조금 내려갔다. 이는 19 update 간격의 변화이지 20회 업데이트 차이라는 뜻은 아니다. 이 변화는 더 긴 학습 후보를 development에서 고정 비교할 근거가 될 수 있다. 반대로 400 epoch 상한에서 best를 기록했다는 사실만으로 완전 수렴을 확인할 수 없으며, 더 학습하면 accuracy나 희소 class recall이 오를 보장도 없다. 학습 횟수를 늘린 모델이 이번 final에서 더 나았을 것이라고 말하지 않는다.

각 development train split의 class support는 순서 `[채낚기연승낚시, 통발, 자망, 연안복합]`로 seed3201 `[86,580,1395,2016]`, seed3202 `[86,581,1399,2013]`, seed3203 `[87,582,1394,2012]`다. Validation은 split별 전체 roster 884척이며, 평가가능 class support는 각각 `[19,125,300,434]`, `[19,125,295,435]`, `[19,124,300,433]`다. 나머지 6/10/8척은 geometry 유효 특징이 없어 abstain됐다. 이 작은 희소-class validation 분모에서 macro metric과 confusion을 함께 볼 필요가 있다. Summary의 train-prior entropy NLL은 1.0740~1.0755였으나, 이는 class prior 확률의 기준값이다. 이를 train accuracy 또는 모델이 잘 수렴했다는 척도로 혼동하지 않는다.

진단 한계는 summary에도 기록돼 있다. Calibration/validation은 checkpoint·후보 선택 과정에 사용됐으므로 독립 final 증거가 아니다. Train NLL이 class-prior entropy 아래라는 사실만으로 균형 정확도가 높거나 최적화가 완료됐다고 결론 낼 수 없다. 이 수치들만으로 불균형, 400 epoch, L2=.01, 누락 mask 또는 optimizer 가운데 하나를 실제 실패 원인으로 특정할 수 없다. 저장 final 예측/logit의 설명적 사후 해설·검산은 할 수 있지만, 이 final을 새 후보 선택·튜닝 또는 새 독립 확증 자료로 재사용하지 않는다.

### 저장 final logits로 한 사후 확률 진단

summary의 `posthoc_final_saved_logit_diagnostics`는 저장돼 있던 final logits에 softmax를 계산한 뒤 raw 확률과 저장 temperature 보정 확률을 비교한 것이다. 새 모델 적합이나 source를 통한 신규 예측은 없었다. 두 model ensemble 모두 temperature 전후 argmax가 바뀐 선박은 **0/1,453척**이었다. 따라서 이 결과에서 낮은 class accuracy나 통발 0/204를 온도 보정이 바꿔 놓았다고 설명할 근거가 없다.

| 모델·지표 | 보정 전 logits 확률 | 보정된 확률 | 해석 |
| --- | ---: | ---: | --- |
| R0 MLP NLL | 1.059378 | 1.056009 | 소폭 개선 |
| R0 MLP Brier | 0.613198 | 0.613261 | 아주 조금 악화 |
| ExtraTrees NLL | 1.040099 | 1.040390 | 아주 조금 악화 |
| ExtraTrees Brier | 0.611740 | 0.611048 | 소폭 개선 |

Accuracy와 Macro F1은 각 모델에서 보정 전후 동일하다. NLL과 Brier는 변화 방향이 다를 수 있으므로 “calibration이 모든 확률 지표를 개선했다”고 일반화하지 않는다. 이는 동결 final에서 원인 탐색용으로 한 설명적 logit 재계산이며 새 평가나 후보 선택으로 세지 않는다.

## 8. 이후 진단 — final은 후보 선택·튜닝·독립 확증에 재사용하지 않음

개발 split에서 이미 확보한 validation 예측·학습 기록을 사용한 가설 진단은 계획할 수 있다. 새 모델 또는 변경안을 확인적으로 평가하려면 후보·지표·분할을 사전 고정하고 새로운 미개봉 선박 holdout을 마련해야 한다. 이미 본 final은 candidate 선택이나 튜닝에 쓰지 않는다. 아래는 실행하지 않은 후속 계획이다.

1. **오류 표본의 개발 전용 검토:** development validation의 class별 혼동과 유보를 보고, 내부의 file/record 참조를 승인된 보안 절차로 추적한다. 원문 ID·좌표를 공개하지 않고, 먼저 label/geometry 계약 오류인지 분류 오류인지 나눈다.
2. **불균형 개입 비교:** 같은 development split과 seed에서 기준, class-balanced loss/weight 또는 train-only resampling을 사전 등록한 후보끼리 비교한다. Macro F1뿐 아니라 통발/희소 클래스 recall, 전체 분모 accuracy, calibration과 coverage를 같이 평가한다. 여러 변경을 동시에 적용하지 않는다.
3. **입력 요약 ablation:** mean, 분포 요약, mask를 하나씩 뺀 후보를 development에만 두고 고정 비교한다. 단일 원인 결론을 내려면 입력 변경 외 학습 조건을 맞춘 짝 비교가 필요하다.
4. **표본 선택 민감도:** 월별 최대 4개라는 계산 가정의 안정성을 새로운 고정 hash seed 또는 월별 표본 수 변화로 development에서 비교한다. 선정은 label·geometry 내용·결과에 의존하지 않게 유지한다.
5. **데이터 계약 개선 후 새 protocol:** point-level timestamp와 CRS가 확인될 때에만 시간/거리 특징을 정의한다. 실제시각 부재 상태에서 Δt·속력 특징을 생성하지 않는다.
6. **독립 검증:** 후보 선택 전 새로운 labeled 선박 기간/출처의 final split, 독립 hash 및 성능 기준을 잠근다. 이미 공개된 1,473척 final은 새로운 독립 테스트로 재사용할 수 없다.

## 9. 저장 결과 확인·독립 재계산 경로와 증거

처음 세 명령은 결과·계약을 읽기만 한다. 마지막 명령은 저장된 예측/분할로 독립 audit JSON을 새로 쓰지만 model fit이나 새 추론은 하지 않는다.

```powershell
# 프로젝트 루트에서 개발 후보 평균값 읽기
Get-Content -Raw outputs/evaluation_cycle_20261028/model_cycle/development_results.json

# 동결 후보·최종 지표·성공/유보 분모 읽기
Get-Content -Raw outputs/evaluation_cycle_20261028/model_cycle/results.json

# protocol, 선택/보정/최종 역할 및 완전한 실험 조건
Get-Content -Raw docs/real_model_cycle_protocol_20261028.md

# 저장된 final probabilities·split manifest를 새 독립 감사 코드로 재계산
# fit / 모델 추론은 하지 않고, 새 audit JSON만 기록한다. 이 예시는 문서에만 적고 여기서 실행하지 않았다.
python tools/verify_real_evaluation_20261028.py --input-dir outputs/evaluation_cycle_20261028/model_cycle --output outputs/real_evaluation_recheck.json
```

| 근거 | 포함 내용 |
| --- | --- |
| [고정 protocol](real_model_cycle_protocol_20261028.md) | 후보, geometry 경계, 분할 정수 규칙, validation/calibration/final 역할, 기준과 성공 조건 |
| [실제 결과 해설](fishing_evaluation_cycle_results_20261028.md) | 데이터 검사·정정·cache, 실제 모델 결과, 익명 추적 예와 한계 |
| [최종 감독 검토](real_model_cycle_final_review_20261029.md) | 상대/절대 성능 구분, 최종 class 지표, 계보·복원·독립 감사 |
| [감독 이력](evaluation_cycle_supervision_20261028.md) | S0 이후 결정과 데이터 오류 수정, 역할·승인·경계 |
| [최종 지표 독립 재계산](../outputs/real_evaluation_independent_audit_20261028.json) | saved prediction의 confusion, precision/recall/F1, NLL/Brier, bootstrap을 별도 계산 |
| [cache 독립 검증](../outputs/real_cache_independent_audit_20261029.json) | 정정 feature cache의 행·월·hash·원본 위치 일치 여부 |
| [분할·계보 감사](../outputs/real_provenance_independent_audit_20261029.json) | seed 분할 복원, final prediction row lineage, source snapshot 일치 |
| [모델 재적재 검증](../outputs/evaluation_cycle_20261028/model_cycle/model_reload_verification.json) | 동결 상태에서 나온 logit/probability의 최대 재현 차이 |
| [개발 진단 요약](../outputs/real_accuracy_diagnostic_summary_20261029.json) | 739MB audit에서 저장된 history·validation·temperature 및 final saved-logit의 bounded posthoc 요약 |

개발 결과는 `development_results.json`에서, 최종 1회는 `results.json`/`final_predictions.json`에서 확인한다. 대용량 `development_model_audit.json`을 통째로 읽지 말고 준비된 작은 진단 summary JSON을 사용한다. 재계산 CLI는 저장 확률·분할 자료만 이용해 새로운 지표 감사를 쓴다. 이는 새 model fit·추론이나 후보 선택이 아니다. 독립 감사는 저장 예측과 기록된 lineage를 검산한 것이며, feature leakage 가능성 전체나 현장 적합성을 증명하지 않는다.

## 10. 용어와 학습자 점검

- **행 단위**: 한 선박·날짜·시간대 기록. 행을 여러 개 가진 선박이 있다.
- **선박 단위 split**: 동일 선박의 기록이 train과 validation/final로 흩어져 암기 효과가 생기는 것을 막는 분할.
- **scorable / abstain**: 유효 특징이 있어 예측·점수를 계산 / 특징이 없어 의도적으로 예측을 유보.
- **Macro F1**: class별 F1을 같은 비중으로 평균해 소수 class도 반영. accuracy와 다른 지표다.
- **Accuracy / F1 / Macro F1**: scorable `N`척에서 `Accuracy = correct/N`; class `c`의 `F1_c = 2TP_c/(2TP_c+FP_c+FN_c)`; `Macro F1 = (Σ_{c=1}^4 F1_c)/4`다. 이번 MLP는 differentiable train NLL+L2 objective를 최소화했으며 Macro F1을 직접 최적화하지 않았다. `class_weight=None`이라 class-balanced 가중치도 사용하지 않았다.
- **Precision / Recall**: 예측한 해당 class 중 정답 비율 / 실제 해당 class 중 맞힌 비율.
- **NLL / Brier**: `NLL = −(1/N)Σ_i ln(p_{i,y_i})`; `Brier = (1/N)Σ_i Σ_{k=1}^4 (p_{ik}−1[y_i=k])²`. 둘 다 예측 확률 손실이며 낮을수록 좋다. 이는 Accuracy·Macro F1과 다른 목적 지표다.
- **Calibration temperature**: 별도 calibration subset에서 확률의 확신 정도를 맞추는 양의 온도. validation·final 정답으로 선택하지 않는다.
- **Bootstrap CI**: 이번에는 선박을 클래스 층화 후 pair로 재추출해 개선 차이의 표본 불확실성을 요약한 구간. 다른 기간·해역의 성능 보증은 아니다.

직접 설명해 볼 질문:

1. 조건부 accuracy가 49.8968%인데 전체 roster accuracy가 49.2193%인 이유를 abstain 분모로 설명할 수 있는가?
2. Macro F1과 accuracy 중 하나만 보고하면 통발 0/204 문제가 어떻게 숨겨지는가?
3. 통발로 예측한 수가 6인데 precision과 recall이 모두 0인 이유는 무엇인가?
4. 9개 record feature와 36개 vessel distribution feature, 72개 model input은 어떻게 연결되는가?
5. observed class imbalance와 majority-class collapse는 확인됐지만 인과가 입증되지 않았다고 말해야 하는 이유는 무엇인가?
6. 어떤 새로운 시간 자료·좌표계·독립 final 자료가 있어야 다음 단계의 결론 범위를 넓힐 수 있는가?

동작하는 학습·평가 pipeline과 학습자가 설계 선택·자료 조건·오류 원인을 설명할 수 있는 역량은 별도 완료 항목이다. 이번 보고서는 기술 계산과 증거를 정리했으며 학습자의 이해 자체를 측정하지 않았다.
