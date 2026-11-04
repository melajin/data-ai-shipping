# S0 합성 항적 분류 시스템: 수식에서 코드와 증거까지

작성일: 2026-10-12  
자료 성격: 개인 학습자용 독립 교재  
범위: 합성 좌표 생성 → 부분선 기하 → 전처리 → 분류기 → 검증·보정 → 지표·시각화 → 실제 자료 도입 관문

본문에 정의·수식·계산 예제·실험 수치를 포함했으므로 이 Markdown 파일 하나를 학습 소스로 사용할 수 있다. Python 예제를 실행할 때는 프로젝트 코드와 저장된 JSON 산출물이 필요하다. 문서 안의 파일 경로는 프로젝트 루트를 기준으로 한다.

**읽기 지도**

| 학습 목적 | 먼저 읽을 절 | 확인할 결과 |
|---|---|---|
| 전체 흐름과 데이터 이해 | 1~7절 | 생성 정답·부분선·여덟 특징·16차원 입력을 설명 |
| 수식과 학습 원리 이해 | 8~13절 | 손실·기울기·모델 선택·확률과 거리의 차이를 계산 |
| 코드와 화면을 직접 추적 | 14~17절 | 한 표본의 입력부터 확률·점수까지 재현 |
| 개선과 실제자료 도입 계획 | 18~20절 | 변경 근거와 평가 관문을 설계 |
| 복습과 팀 설명 | 21~26절 | 답안과 비교하고 근거 있는 설명을 작성 |

> 여기서 straight, sweep, turn은 생성기가 만든 경로 모양 이름이다. 공식 fishing_code, 실제 조업 행동, 정상·사고 상태를 뜻하지 않는다. 아래 수치와 모델은 seed 42의 합성 실행 결과다. 실제 선박 자료의 성능이나 하드웨어 실험 결과가 아니다.

## 1. 이 장을 마치면 설명할 수 있어야 하는 것

시스템이 실행된다는 사실과 학습자가 그 이유를 설명할 수 있다는 사실은 별개의 완료 조건이다. 이 장에서는 아래 능력을 확인한다.

1. 합성 경로가 어떤 가정·난수·수식으로 만들어졌고, 라벨이 무엇을 뜻하지 않는지 설명한다.
2. 부분선 경계를 지키며 여덟 기하 특징을 계산하고 단위, 결측 조건, 평균 방식의 차이를 말한다.
3. 학습 데이터에서만 대치값·평균·표준편차·가중치·공분산을 맞추고, validation·calibration·test의 역할을 구분한다.
4. row-vector 행렬 규약으로 선형 분류기와 tanh 16개 은닉층의 순전파·손실·역전파를 손으로 확인한다.
5. accuracy, macro F1, NLL, Brier, 혼동행렬, 선박 bootstrap 구간, Mahalanobis 거리의 질문과 한계를 구분한다.
6. 현재 test/stress 차이만으로 순수 교란 효과나 과적합을 단정할 수 없는 이유를 설명한다.
7. 현 CLI가 합성 자료용인 이유와, 실제 자료 도입 전에 필요한 좌표·시점·라벨·그룹 분할 관문을 제안한다.

## 2. 시작점, 선수개념, 확인되지 않은 조건

문서의 용도는 본인 학습용으로 확인됐다. 학습자의 구체적인 수학·Python 선수지식, 공부 시간, CPU·메모리 환경은 확인되지 않았다. 그래서 이 장은 용어를 먼저 정의하고 작은 수 계산을 거쳐 코드와 큰 실험으로 이동한다. 실습 시간을 임의로 정하지 않는다.

학습에 유용한 기초는 다음과 같다. 익숙하지 않은 항목은 해당 절의 정의와 예제를 먼저 따라간다.

| 선수개념 | 이 장에서 쓰는 뜻 |
|---|---|
| 좌표와 벡터 | 점 (x,y)와 두 점 차이로 만든 이동 벡터 |
| 길이와 피타고라스 정리 | 두 점 간 거리 √(Δx²+Δy²) |
| 내적·2D 외적 | 방향의 유사도와 평면에서의 회전 방향·넓이 성분 |
| 평균·분산·표준편차 | 값을 요약하고 평균 주변의 퍼짐을 재는 방법 |
| 배열과 행렬곱 | 여러 표본을 한꺼번에 계산하는 NumPy의 기본 연산 |
| 지수·로그 | 확률의 softmax, 음의 로그우도, 로그합지수 |
| 미분과 연쇄법칙 | 목적값이 가중치 변화에 따라 얼마나 바뀌는지 추적 |
| 분류 평가 | 정답과 예측을 세고 확률 오차를 요약 |

현재 시스템은 소프트웨어 안에서 생성한 지역 XY 미터 자료를 쓴다. 센서, 핀, 전압, 통신, 실제 샘플링 주기, 기기 지연은 정해지거나 측정되지 않았다. 생성기 내부의 시뮬레이션 시간 간격을 실제 장치 주기로 바꾸어 부르면 안 된다.

## 3. 용어 사전

| 용어 | 뜻과 이 장에서의 취급 |
|---|---|
| record | 한 경로 표본과 그 메타데이터를 묶은 JSON 항목 |
| 부분선(part) | 관측된 연속 구간. 누락·단절 전후의 두 배열은 서로 독립적이다. |
| label | 생성기가 사용한 클래스 번호 0, 1, 2. 순서는 straight, sweep, turn이다. |
| 그룹(vessel group) | 같은 생성 조건을 공유하는 합성 선박 ID. 분할의 기본 단위다. |
| feature | 한 record의 기하를 숫자 여덟 개로 요약한 입력 |
| 결측(mask) | 특징이 계산되지 않았다는 표시. 수치 0과 다른 상태다. |
| logit | softmax를 적용하기 전 클래스별 점수. 확률이 아니다. |
| softmax | logit을 합이 1인 클래스 확률로 바꾸는 함수 |
| NLL | 정답 확률에 로그를 적용해 틀린 정도를 계산하는 평균 손실. 낮을수록 좋다. |
| L2 정규화 | 가중치 크기에 벌점을 더하는 항. 이번 목적식에서 편향은 벌점 대상이 아니다. |
| epoch | 전체 학습 표본을 사용해 gradient update를 한 번 수행한 단위 |
| validation | 고정 후보·최적 epoch·거리 임계값을 선택하는 개발 분할 |
| calibration | 고른 분류기의 확률 온도 T만 결정하는 별도 분할 |
| test | 최종 결과를 보고하는 잠금 평가 분할. 반복 설계 선택에 쓰지 않는다. |
| stress | 미리 고정한 합성 변화 조건 분할. 실제 분포 변화의 대체물이 아니다. |
| temperature | logit을 양수 T로 나눈 뒤 softmax를 적용하는 확률 보정값 |
| Mahalanobis 거리 | 학습 클래스 중심·공분산을 기준으로 입력이 얼마나 떨어졌는지 재는 거리 |
| 유보(abstain) | 계산 계약을 만족하지 않아 분류 결과를 내지 않는 상태 |
| data leakage | 평가 자료나 같은 그룹의 관계를 학습·선택에 섞어 결과가 낙관될 수 있는 누출 |
| CRS | 지리 좌표의 기준계. 실제 좌표를 거리 계산에 쓰려면 확인해야 한다. |
| available time | 자료가 시스템에 실제 이용 가능해진 시점. 미래 정보를 앞서 쓰지 않기 위한 시간 기준 |

## 4. 시스템의 입력·출력과 자료 경계

### 4.1 전체 흐름

```text
seed와 명시된 합성 가정
  → fishing_sample_v1 JSON: metadata + records
  → 좌표, 시간 배열, ID, 그룹 분할 계약 검사
  → record별 부분선 기하 특징 8개
  → train에서 중앙값 대치·평균/표준편차·결측 mask 8개를 적합
  → 고정된 5개 분류 후보를 train으로 학습
  → validation NLL로 epoch와 후보 선택
  → calibration NLL로 temperature 선택
  → train에서 클래스별 공분산, validation에서 거리 임계값 결정
  → test와 stress 결과만 계산
  → model/report/predictions JSON과 오프라인 HTML 저장
  → 저장 모델을 다시 읽어 추론 재현성 확인
```

여기서 물리 현상, 센서, 회로, 펌웨어, 전송 계층은 구현되지 않는다. 현재의 작은 전체 흐름은 합성 데이터에서 응용 소프트웨어까지다. 실제 장비의 허용 조건을 확인하지 않았으므로 장치 연결을 지시하거나 실측 결과를 주장하지 않는다. 이 장에서 말하는 AI 모델은 Python/NumPy로 구현한 선형 분류기와 tanh MLP다. 이 문서를 작성하거나 읽는 대화형 언어 모델(LLM)과 혼동하지 않는다.

### 4.2 JSON 계약

최상위 객체에는 metadata와 records가 있다. metadata의 고정 핵심은 다음과 같다.

| 필드 | 기본값 또는 뜻 |
|---|---|
| schema_version | fishing_sample_v1 |
| source_type | synthetic |
| coordinate_system | local_xy_m |
| class_names | [straight, sweep, turn] |
| seed | 기본 42 |
| generator_version | 1.0.0 |
| split_group_counts | train 36, validation 12, calibration 12, test 12, stress 12 |
| samples_per_class | 기본 4 |
| assumptions | 생성 목적·좌표·시간·라벨 겹침·단절·stress 조건 설명 |

각 record의 핵심 필드는 아래와 같다.

| 필드 | 예시 형태 | 모델 입력 여부 |
|---|---|---|
| sample_id | 문자열 ID | 사용하지 않음 |
| vessel_id | 그룹 ID | 사용하지 않음; 분할과 감사에만 사용 |
| split | train/validation/calibration/test/stress | 사용하지 않음; 실행 역할 지정에 사용 |
| label | 정수 0~2 또는 null | 특징에 넣지 않음; 학습·선택·보정·평가의 정답으로 사용하며 추론 확률·점수 계산에는 넣지 않음 |
| parts | 부분선별 [[x,y], …] 배열, 미터 단위 | 여기서만 기하를 계산 |
| sim_times | parts와 맞는 초 배열 | 특징에 넣지 않음; 실제 관측 시간 아님 |
| scenario | base 또는 shift | 특징에 넣지 않음 |
| quality | 원점 수, 관측 수, 누락률, 부분선 수 등 | 특징에 넣지 않음; 오류 해석용 |

파이프라인 감사 정보는 feature에서 label, vessel_id, split, scenario, sim_times, quality를 제외했음을 저장한다. 잘못된 좌표·배열 정합성·중복 ID는 조용히 고쳐 쓰지 않고 오류로 거절한다. 유효 길이가 없는 경로는 분류에 억지로 넣지 않고 유보한다. 현재 생성 표본 1008개는 모두 유효하고 유보되지 않았지만, 그것이 미래 입력도 모두 유효함을 보장하지 않는다.

### 4.3 디렉터리에서 확인할 산출물

저장소에서의 기본 위치와 역할이다. NotebookLM에 이 장 하나만 넣어도 내용을 이해하도록 이 절에 산출물 의미를 설명한다.

| 위치 | 역할 |
|---|---|
| fishing_demo/data.py | 합성 경로, 입력 계약 검사, JSON 읽기·쓰기 |
| fishing_demo/features.py | 여덟 기하 특징 계산 |
| fishing_demo/models.py | 전처리, 분류기, 지표, 온도, 거리 모델 |
| fishing_demo/pipeline.py | 분할 경계, 학습·선택·보정·평가·직렬화 연결 |
| fishing_demo/visualization.py | 외부 의존 없는 오프라인 HTML |
| tools/run_sample_system.py | demo/generate/train/predict CLI |
| outputs/sample_system/sample_dataset.json | 생성 자료 |
| outputs/sample_system/model.json | 전처리 통계·분류 가중치·온도·거리 모델과 임계값 |
| outputs/sample_system/report.json | split별 지표·후보 이력·감사와 제한 |
| outputs/sample_system/predictions.json | 표본별 정답(있을 경우)·예측·확률·점수·특징 |
| outputs/sample_system/dashboard.html | report와 predictions를 담은 오프라인 관찰 화면 |
| outputs/sample_system/test_summary.json | 별도 이전 실행의 저장된 테스트 요약 |

이 경로들은 구현·계산 증거의 출처다. 파일이 존재한다는 사실만으로 실제자료 적합성이나 학습자의 성취를 입증하지 않는다.

## 5. 생성기의 라벨, 수식, 그룹, 시뮬레이션 시간

### 5.1 숫자로 보는 기본 표본 수

기본 설정은 seed=42, 그룹별 클래스당 4개 표본이다. 각 합성 선박 그룹은 클래스 3개를 모두 가지고 있다.

| split | 그룹 수 | 클래스당 record | record 계산 |
|---|---:|---:|---:|
| train | 36 | 4 | 36 × 3 × 4 = 432 |
| validation | 12 | 4 | 12 × 3 × 4 = 144 |
| calibration | 12 | 4 | 12 × 3 × 4 = 144 |
| test | 12 | 4 | 12 × 3 × 4 = 144 |
| stress | 12 | 4 | 12 × 3 × 4 = 144 |
| 합계 | 84 |  | 1008 |

train의 클래스 support는 각 36×4=144개다. 나머지 각 split의 support는 클래스별 12×4=48개다. 전체 표본의 84개 vessel ID는 분할끼리 겹치지 않는다. 같은 그룹의 경로는 방향·이동 원점·척도·잡음·누락 같은 nuisance 조건을 공유한다. record 행만 섞으면 가까운 같은 선박 표본이 양쪽에 들어갈 수 있어 새 그룹 일반화를 과대평가할 위험이 있다.

### 5.2 경로 생성 규칙

경로 점 수 N은 55에서 85까지 정수로 뽑는다. 진행률은 다음과 같다.

$$
u_i = \frac{i}{N-1},\qquad i=0,\ldots,N-1
$$

코드에서는 마지막 점에 도달하기 위한 N−1개 이동에 heading[0]부터 heading[N−2]까지만 쓴다. heading[N−1]은 이동에 쓰지 않는다. 생성기 길이 척도 ℓ은 800~1600 m 균등 난수에 그룹 배율을 곱해 정한다. 점 사이 기본 이동은 아래와 같고 누적한 뒤 ℓ로 환산한다.

$$
\Delta r_i =
\frac{\ell}{N-1}
\left(\cos h(u_i),\;\sin h(u_i)\right),
\qquad
r_k = \sum_{i=0}^{k-1}\Delta r_i
$$

각도 가족 h(u)는 라벨마다 다르게 샘플링하지만 일부 범위가 겹친다. s는 +1 또는 −1이다.

| 라벨 이름 | 코드에서 뽑는 값 | heading h(u) |
|---|---|---|
| straight, label 0 | a∼Uniform(0,1), b∼Uniform(0,0.18) | s·a(u−0.5)+b·sin(2πu) |
| sweep, label 1 | A∼Uniform(0.25,1.3), c∼Uniform(0.7,1.6), ψ∼Uniform(−0.5,0.5) | s·A·sin(2πcu+ψ) |
| turn, label 2 | a∼Uniform(0.75,3.6), b∼Uniform(0,0.12) | s·a(u−0.5)+b·sin(2πu) |

예를 들어 설명 목적으로 a=0.9 rad, b=0.05, 같은 s를 둔다. 이 a는 straight 범위 0~1에도, turn 범위 0.75~3.6에도 들어가므로 같은 기본 heading 식을 만들 수 있다. 이 계산 예는 생성기 범위가 겹친다는 설명이지 실제 파일에서 그 두 라벨의 완전히 같은 표본 쌍을 관찰했다는 주장이 아니다. 같은 입력 모양에 서로 다른 생성 라벨을 붙일 수 있다면 입력만으로 생성기의 원래 분기를 완벽히 복원하지 못한다. 그래서 모든 오분류를 모델 과적합으로 몰아갈 수 없다.

이 이름은 기하 가족의 약칭이다. straight가 실제 직항·무조업을, sweep이 특정 어구 작업을, turn이 조업 행동을 뜻한다는 근거가 없다. 실제 fishing_code가 선박 고정 업종, 시간별 활동, 항차 상태 중 무엇을 표현하는지도 미확인이다. 세 합성 이름과 실제 라벨을 직접 연결하면 안 된다.

방향을 만들고 난 뒤 경로를 회전·이동시키고 좌표 잡음을 추가한다.

$$
R(\phi)=
\begin{bmatrix}
\cos\phi&-\sin\phi\\
\sin\phi&\cos\phi
\end{bmatrix},
\qquad
r'_i = R(\phi)r_i + o + \epsilon_i
$$

그룹 회전 φ는 −π~π에서, 원점 o의 X·Y는 각각 −4000~4000 m에서 정한다. record마다 그룹 방향에 평균 0, 표준편차 0.18 rad인 작은 편차가 더해진다. 그룹 길이 배율은 exp(Normal(0,0.25)), 좌표 잡음 표준편차는 0.18~0.55 m다. 이 수치는 생성기 가정이지 실제 선박 센서의 데이터시트 사양이나 측정값이 아니다.

### 5.3 결측·단절·stress

base 그룹마다 점 누락 확률은 0.01~0.06, 부분선 단절 확률은 0.005~0.025에서 정한다. 점 수는 보통 55~85개다. 누락 또는 단절은 각기 별도 부분선으로 남기며 그 사이를 잇지 않는다. 각 샘플의 dt는 3~8초 난수이고 sim_times[i]=i·dt로 붙인다. 이것은 시뮬레이션을 위한 가상 초 단위다. 실제 장치의 sampling rate도 아니고 실제 관측 timestamp도 아니다. 따라서 실선 속력·가속도를 계산하지 않는다.

stress 생성은 path family label 번호는 유지하면서 다음 네 조건을 한꺼번에 바꾼다.

| 조건 | stress 설정 |
|---|---:|
| 길이 척도 | base에서 뽑은 길이 × 2.6 |
| 좌표 잡음 크기 | 그룹 잡음 × 5 |
| 점 누락 확률 | 0.24 |
| 부분선 단절 확률 | 0.07 |

시나리오 문자열 shift는 생성 조건을 기록하는 메타데이터일 뿐 모델 입력 feature가 아니다. 생성기가 라벨 숫자를 유지한다고 해서 통계학적 조건부 분포 P(Y|X)가 보존된다는 증거가 되지는 않는다. 이번 결과는 엄밀한 covariate shift 검증을 하지 않았다. test와 stress는 서로 다른 12개 그룹이고 네 조건이 함께 바뀌었으므로 그 차이를 조건 하나의 순수 효과로 설명하지 않는다.

## 6. 여덟 기하 특징: 정의, 단위, 결측, 집계

부분선 j의 점을 p[j,0], …, p[j,m−1]라 하자. 이웃한 두 점의 차이 벡터와 세그먼트 길이는

$$
v_{j,i}=p_{j,i+1}-p_{j,i},\qquad
\ell_{j,i}=\|v_{j,i}\|_2
$$

다. 부분선 길이 L[j]는 그 부분선 안 모든 세그먼트 길이의 합, 끝점 변위 D[j]는 첫 점과 마지막 점 거리다. 길이 0인 부분선은 특징 집계에 참여하지 않는다.

| 순서 | 코드 변수 이름 | 계산 정의 | 단위·예외 |
|---:|---|---|---|
| 1 | log1p_total_length_m | ln(1 + Σ[j] L[j] / 1 m) | 무차원 로그. 양의 모든 부분선 길이를 합산한다. |
| 2 | mean_part_straightness | 양의 길이 부분선의 산술평균 mean[j](D[j]/L[j]) | 무차원 0~1. 부분선마다 같은 가중치이며 ΣD/ΣL과 다르다. |
| 3 | mean_abs_turn_rad | 유효 이웃 비영 세그먼트 회전각 θ 전체에 대해 mean(abs(θ)) | rad. 유효한 각도 자체가 없으면 결측. |
| 4 | turn_direction_concentration | abs(Σθ) / Σabs(θ) | 무차원. 각도는 있지만 분모가 0이면 0, 각도 자체가 없으면 결측. |
| 5 | std_turn_rad | 유효 signed θ 전체의 모집단 표준편차, ddof=0 | rad. 각도 자체가 없으면 결측. |
| 6 | max_abs_turn_rad | max(abs(θ)) | rad. 각도 자체가 없으면 결측. |
| 7 | mean_part_spread_ratio | 부분선별 중심 공분산 고유값 λmin≤λmax에 대해 sqrt(λmin/λmax), 그 산술평균 | 무차원. 점구름이 길고 가늘면 0에 가까운 경향. |
| 8 | mean_part_chord_deviation_ratio | 유효한 부분선별 H[j]/L[j]를 산술평균 | 무차원. 끝점 변위 D[j]=0이면 그 부분선을 평균에서 뺀다. |

특징 이름·순서는 저장 모델의 입력 계약이다. 이름이나 순서가 바뀌면 모델이 다른 숫자를 다른 의미로 받아들이게 된다.

### 6.1 각도와 부분선 집계 방식

각 부분선 안에서 영벡터(같은 좌표 반복)는 방향을 정의하지 않으므로 방향각 계산에서만 제외한다. 남은 각 이웃 벡터의 signed 각은

$$
\theta_i=\operatorname{atan2}
\left(x_i y_{i+1}-y_i x_{i+1},\;
v_i\cdot v_{i+1}\right)
$$

로 계산하며 −π에서 π 범위다. 부분선을 넘는 각도는 만들지 않는다. 모든 부분선에서 구한 θ들을 한 배열에 모아 회전 통계량을 계산한다. 즉 각 부분선 통계를 먼저 구한 다음 부분선 평균을 다시 내는 방식이 아니다. 표본 간 실제 회전이 π보다 크면 atan2의 wrap 때문에 반대 방향의 짧은 변화와 구분되지 않을 수 있다. 샘플링 조건을 모르는 실제 경로에서는 이를 실제 회전량처럼 해석하지 않는다.

spread용 부분선 중심 공분산은

$$
C_j=\frac{1}{m_j}\sum_i
(p_{j,i}-\bar p_j)(p_{j,i}-\bar p_j)^T
$$

다. 분모는 그 부분선 점 수 m[j]다. 여기서는 점구름의 모양을 계산한다.

chord 특징에서 끝점 chord 벡터는 c[j]=p[end]−p[0], 그 길이는 D[j]=||c[j]||다. 각 점의 끝점 방향 무한 직선에 대한 수직거리를

$$
H_j = \max_i
\frac{|(p_{j,i}-p_{j,0})\times c_j|}{D_j}
$$

로 잡고 최종 특징은 H[j]/L[j]다. H는 수직거리이고 D는 그 거리의 분모인 chord 길이다. 최종 특징에 쓰는 분모는 부분선 총 길이 L이다. 이 정의는 선분까지의 최단거리가 아니라 끝점 chord를 지나는 무한 직선에 대한 거리다. D=0인 닫힌 부분선은 방향이 정의되지 않으므로 feature 8 집계에서 제외한다.

### 6.2 ㄱ자 손계산: 하나의 연속 부분선

한 부분선이 (0,0) → (3,0) → (3,4) m라고 하자.

- 두 이동 벡터는 (3,0), (0,4), 각 길이는 3 m와 4 m다.
- 부분선 총 길이 L=3+4=7 m, 끝점 변위 D=√(3²+4²)=5 m다.
- 부분선 직선성은 D/L=5/7≈0.7143이다.
- 전체 길이 특징은 ln(1+7)=ln(8)≈2.0794다.
- 외적은 12, 내적은 0이므로 θ=atan2(12,0)=π/2≈1.5708 rad다.
- 각도는 하나다. mean |θ|=π/2, 방향 집중도=1, 모집단 표준편차=0, max |θ|=π/2.
- chord 길이는 D=5 m다. 중간점의 수직거리 H=|3·4−0·0|/5=2.4 m다. 최종 chord 특징은 H/L=2.4/7≈0.3429다.
- 중심 공분산은 [[2,1.3333],[1.3333,3.5556]] 정도, 고유값은 약 1.2342와 4.3214다. spread는 √(1.2342/4.3214)≈0.5343이다.

이 예제는 수식 확인용이다. 세 점이나 하나의 각도로 실제 조업을 판정한다는 뜻은 아니다.

### 6.3 두 부분선과 잘못된 연결의 차이

두 관측 부분선이 A: (0,0)→(3,0), B: (3,2)→(3,4) m라고 하자. 관측되지 않은 구간을 직선으로 연결하지 않는 것이 계약이다.

- 분리 유지: 총 관측 길이 L=3+2=5 m다. 두 부분선 모두 직선성이 1이므로 feature 2는 (1+1)/2=1이다. 각 부분선 안에는 이웃한 이동이 없어 각도 특징 3, 4, 5, 6은 계산 불가여서 결측이다.
- 연결 금지 위반: A의 끝과 B의 시작 사이에 임의의 (0,2) m 선분을 넣으면 길이가 7 m로 바뀌고, 관측되지 않은 방향각 π/2도 생긴다. 이는 원자료에 없는 정보를 모델에 주입한다.

같은 첫/끝 점으로도 평균 직선성이 길이 가중 비율과 다를 수 있다. 길이 10 m, 직선성 0.9인 부분선과 길이 90 m, 직선성 0.2인 부분선이 있다고 하자. 코드의 feature 2는 각 부분선 동일 가중으로 (0.9+0.2)/2=0.55다. ΣD/ΣL로 계산하면 (0.9·10+0.2·90)/100=0.27이다. 두 값은 다른 통계량이며 서로 대체하면 안 된다.

또 하나의 gap 예제를 보자. 연속 부분선 A: (0,0)→(3,0)→(3,2)→(3,4)는 길이 7 m, 변위 5 m, 직선성 5/7, 각도 배열 [π/2,0], 평균 절대 각도 π/4다. 이를 A1: (0,0)→(3,0), A2: (3,2)→(3,4)로 나눠 보존하면 총 관측 길이는 5 m, 각 부분선 직선성은 1이고 각도 특징은 결측이다. 보이지 않는 gap을 2 m 직선으로 채워 그 회전을 모델에 넣으면 안 된다. 그러면 표준화된 결측 대치값과 mask=1 대신 가짜 측정값이 들어가 예측 자체가 달라진다.

## 7. 결측 처리: 8개 특징에서 16개 열로

짧은 부분선에는 방향각이 없을 수 있고 닫힌 부분선에는 chord 편차를 계산하지 않는다. feature_matrix는 None을 NaN으로 표현한다. 먼저 특징 함수가 최소 하나의 양의 길이 부분선이 있는지 확인한다. 그렇지 않으면 8개 값을 모두 null로 두고 유효성 false, 이유 no_positive_length_parts를 돌려준다.

Preprocessor.fit은 학습 X_train의 각 feature 열 d에 대해 다음 순서로 동작한다.

1. 관측된 train 값의 중앙값 m[d]를 구한다. train 전체에서 열이 결측이면 m[d]=0으로 둔다.
2. 결측을 m[d]로 채운 train 행렬에서 평균 μ[d]와 모집단 표준편차 σ[d] (ddof=0)를 구한다.
3. σ[d]=0이면 1로 둔다. train 전체가 결측이면 μ[d]=0, σ[d]=1이다.
4. 새 row x의 결측 셀은 저장한 m[d]로 채운 뒤 z[d]=(filled(x[d])−μ[d])/σ[d]로 표준화한다.
5. 원래 결측이었는지 M[d]=1[missing]도 만든다.
6. 모델 입력은 [z[1],…,z[8], M[1],…,M[8]]로 붙여 16개 열로 만든다.

실제 관측값 0과 관측 실패는 서로 다를 수 있다. 중앙값 대치와 결측 mask를 함께 쓰면 이 구분을 남긴다. 새 split마다 평균을 다시 계산하지 않는다. test의 값을 이용해 스케일을 다시 맞추면 test가 학습 변환에 영향을 주어 평가 경계가 흐려진다. 입력 크기 D=16인 이유는 기하 feature 8개에 결측 표시자 8개를 붙이기 때문이다.

실제 저장 test record S0-test-000-straight-00의 첫 특징은 6.34578798이다. 저장된 train 평균은 6.99486912, 표준편차는 0.31948241이다.

$$
z_1=(6.34578798-6.99486912)/0.31948241\approx -2.03166470
$$

이 표본의 나머지 일곱 특징도 같은 방식으로 변환됐고 여덟 결측 mask는 모두 0이다. 이 숫자는 기존 model.json의 통계값과 저장된 dataset을 다시 읽은 단일 추론 추적에서 얻은 값이다.

## 8. 분류기: row-vector 규약으로 순전파와 손실

### 8.1 기호와 행렬 크기

코드는 표본을 행(row)으로 놓고 행렬곱한다. 이 규약을 끝까지 유지한다.

| 기호 | 크기 | 뜻 |
|---|---|---|
| N | 스칼라 | 현재 묶음의 유효 표본 수 |
| D | 16 | 8개 표준화 특징 + 8개 결측 mask |
| C | 3 | 분류 클래스 수 |
| X | N×16 | 한 표본이 한 행인 모델 입력 |
| W | 16×3 | 선형 후보 가중치 |
| b | 3 | 선형 후보 편향 |
| W1 | 16×16 | MLP 첫 가중치 |
| b1 | 16 | MLP 첫 편향 |
| H | N×16 | tanh 은닉 출력 |
| W2 | 16×3 | MLP 출력 가중치 |
| b2 | 3 | MLP 출력 편향 |
| Z | N×3 | logit 행렬 |
| P | N×3 | 클래스 확률 행렬 |
| y | N | 정수 정답 클래스 index |
| Q | N×3 | y를 one-hot으로 바꾼 정답 행렬 |

선형 후보는 Z=XW+b다. 코드의 가중치 W 모양은 (D,C)다. 일부 교재에서 열벡터 규약 Wᵀx+b를 쓰지만 이 장에서는 표본행 규약의 XW+b를 사용한다. 두 식은 전치 규약만 다르며 같은 선형 연산이다.

MLP는 아래 순서로 계산한다.

$$
A_1=XW_1+b_1,\qquad H=\tanh(A_1)
$$
$$
Z=HW_2+b_2,\qquad P=\operatorname{softmax}(Z)
$$

선형 모델 파라미터 수는 16×3+3=51개다. tanh MLP는 16×16+16+16×3+3=323개다. MLP가 더 복잡하다고 정확도가 자동으로 높아지는 것은 아니다. 이번 비교에서도 각 구조·λ·validation 결과를 측정했다.

### 8.2 안정한 softmax와 교차엔트로피

각 row의 logit z[k]는 아직 확률이 아니다. 직접 exp(z[k])를 계산하면 큰 양수에서 overflow가 날 수 있다. row 최대값 m=max[k]z[k]를 먼저 빼서

$$
p_k=\frac{\exp(z_k-m)}{\sum_c\exp(z_c-m)}
,\qquad \sum_k p_k=1
$$

로 계산한다. 빼는 값이 모든 클래스에서 동일하므로 확률비는 바뀌지 않는다.

log-sum-exp는 큰 값을 빼고 다시 더해 안정하게 구한다.

$$
\operatorname{LSE}(z)=m+\log\sum_k\exp(z_k-m)
$$

한 표본의 정답 class를 y, 정답 one-hot을 q라 하면 교차엔트로피는

$$
\ell=-\log(p_y)
=\operatorname{LSE}(z)-z_y
$$

다. N개의 유효 label의 평균 negative log-likelihood는

$$
L_{\mathrm{NLL}}
=-\frac{1}{N}\sum_{i=1}^N\log p_{i,y_i}
=\frac{1}{N}\sum_i
\left(\operatorname{LSE}(z_i)-z_{i,y_i}\right)
$$

다. 정답 클래스 확률이 작으면 손실이 커진다. 목적값이 평균이므로 batch 크기와 무관하게 대략 표본당 오차 척도를 유지한다.

### 8.3 L2 목적식과 한 표본 손계산

가중치만 정규화하는 목적식은

$$
J(W,b)=L_{\mathrm{NLL}}+
\frac{\lambda}{2}\|W\|_F^2
$$

다. 여기서 ||W||²_F는 모든 가중치 성분 제곱합이다. 편향 b는 합산 대상이 아니다. /2가 있으므로 제곱합을 미분하면 λW가 남는다.

기호가 실제로 어떤 값을 내는지 작은 예를 계산해 보자. 입력 특징 하나 x=1, 클래스 3개, 확률 p=(0.5,0.3,0.2), 정답 class 0, 가중치 W=(0.2,−0.1,0.3), λ=0.1이라고 가정한다.

$$
q=(1,0,0),\qquad
p-q=(-0.5,0.3,0.2)
$$

정답 확률이 0.5이므로 NLL은 −ln(0.5)≈0.6931이다. 벌점은

$$
\frac{0.1}{2}(0.2^2+(-0.1)^2+0.3^2)=0.007
$$

이므로 목적값 J≈0.7001이다. 한 표본에서 logit gradient는 p−q다. x=1인 가중치 gradient에 데이터 항과 벌점 항을 더하면

$$
\nabla_WJ=(-0.5,0.3,0.2)+0.1(0.2,-0.1,0.3)
=(-0.48,0.29,0.23)
$$

이다. 편향은 벌점 없이 ∇b=(-0.5,0.3,0.2)다. 이것은 개념을 연습하는 한 특징 예제이며 실제 모델의 16차원 가중치 일부를 측정한 결과는 아니다.

## 9. 역전파, learning rate, 수치 미분

### 9.1 softmax 교차엔트로피 미분

정답 one-hot Q를 사용하면 batch 평균의 logit 미분은

$$
D_Z=\frac{\partial J}{\partial Z}=(P-Q)/N
$$

다. pipeline은 valid label을 먼저 고르고 그 유효 개수 N으로 한 번 나눈다. 손실을 평균내면서 gradient를 또 다른 값으로 한 번 더 나누지 않는다.

선형 모델에서

$$
\nabla_WJ=X^TD_Z+\lambda W,\qquad
\nabla_bJ=\sum_{i=1}^{N}D_{Z,i}
$$

다. 크기도 맞는다. Xᵀ는 16×N, D_Z는 N×3이므로 XᵀD_Z는 16×3이고 W와 같다.

### 9.2 tanh 16개 은닉층 미분

tanh의 미분은 d tanh(a)/da=1−tanh(a)²다. H=tanh(A1), Z=HW2+b2를 역방향으로 미분한다.

$$
\nabla_{W_2}J=H^TD_Z+\lambda W_2,\qquad
\nabla_{b_2}J=\sum_iD_{Z,i}
$$
$$
D_{H}=D_ZW_2^T,\qquad
D_{A_1}=D_H\odot(1-H^2)
$$
$$
\nabla_{W_1}J=X^TD_{A_1}+\lambda W_1,\qquad
\nabla_{b_1}J=\sum_iD_{A_1,i}
$$

여기서 ⊙는 성분별 곱이다. XᵀD_A1은 16×16으로 W1과 같은 크기이고, HᵀD_Z는 16×3으로 W2와 같다. 코드의 bias 행은 입력 batch의 모든 표본에 더해지므로 bias gradient는 batch 방향(axis=0) 합이다.

### 9.3 한 번의 업데이트와 gradient 검산

learning rate η=0.03인 full-batch gradient descent는 epoch마다 모든 train 표본으로 계산한 gradient를 이용해

$$
\theta_{\mathrm{new}}=\theta_{\mathrm{old}}-\eta\nabla_\theta J
$$

로 모든 파라미터를 동시에 갱신한다. 실제 코드의 기본 최대 epoch는 400, patience는 35다. 여기서 η는 반복마다 얼마만큼 이동할지 정하는 step 크기이며, 너무 크면 목적값이 불안정할 수 있고 너무 작으면 느리게 움직일 수 있다.

수식으로 만든 gradient가 코드의 배열 인덱스·부호·batch 평균과 같은지 수치 미분으로 확인할 수 있다. 한 파라미터 θ[j]의 중앙차분 근사는

$$
g_j^{\mathrm{num}}
=
\frac{J(\theta_j+\varepsilon)-J(\theta_j-\varepsilon)}{2\varepsilon}
$$

다. 이를 역전파의 g[j]와 비교한다. ε는 작은 양수다. 상대 오차가 작으면 그 파라미터 근처의 목적함수 기울기를 코드가 잘 계산한다는 증거다. 저장된 검증 기록은 softmax·tanh 수치 미분 테스트 통과를 보고한다. 이 검사는 코드의 국소 미분 계산을 확인할 뿐 라벨이 올바르다거나 실제 자료에 일반화된다는 것을 증명하지 않는다.

## 10. 학습, 후보 선택, early stopping, 온도 보정

### 10.1 다섯 후보와 고정된 split 역할

사전 후보군은 선형 2개, tanh 16개 MLP 3개다. 이름의 l2 숫자는 λ다.

| 후보 | 은닉층 | λ | validation NLL, 보정 전 | 선택 epoch |
|---|---:|---:|---:|---:|
| linear_l2_001 | 없음 | 0.01 | 0.527081 | 400 |
| linear_l2_01 | 없음 | 0.1 | 0.596607 | 400 |
| mlp16_l2_0 | tanh 16 | 0 | **0.467992** | 400 |
| mlp16_l2_001 | tanh 16 | 0.01 | 0.478080 | 400 |
| mlp16_l2_01 | tanh 16 | 0.1 | 0.601108 | 400 |

pipeline은 각 epoch의 validation NLL을 기록한다. 더 낮은 validation NLL이 엄격하게 나올 때 best checkpoint를 저장한다. 35회 연속 개선이 없으면 멈추고 best checkpoint로 돌아간다. 후보 간 비교도 보정 전 validation NLL 하나만 사용한다. 점수가 같으면 후보 목록의 앞순서를 택해 더 단순한 후보가 tie를 이긴다.

이번 seed42 결과에서 mlp16_l2_0가 선택됐고 λ=0이다. 다섯 모델의 best epoch는 모두 400이어서 이번 실행에서 조기 종료가 발생하지 않았다. 따라서 “early stopping이 이번 점수를 개선했다” 또는 “L2가 결과를 더 좋게 했다”고 결론 내릴 근거가 없다. 반대로 L2가 늘 필요 없다고 결론 내릴 수도 없다. 이 결과는 작은 후보군, 한 번의 생성·초기화 seed, 이 validation 그룹에 대한 비교다.

### 10.2 split의 권한

| split | 이 자료에서 fit/선택하는 것 | 허용되는 사용 |
|---|---|---|
| train | 중앙값·평균·표준편차, classifier 가중치, 클래스 공분산 | 파라미터 fitting |
| validation | 매 epoch checkpoint, 5개 후보, Mahalanobis 임계값 | 미리 정한 후보 안의 선택 |
| calibration | positive scalar temperature | 확률 NLL 보정 |
| test | 정확도·오차·확률 지표, vessel bootstrap | 최종 결과 보고 |
| stress | 사전 고정 합성 조건에서의 동일 지표 | 고정 stress 관찰 보고 |

같은 record를 여러 역할에 섞지 않는다. 같은 vessel 그룹도 split을 넘지 않는다. report의 group_overlap_count는 0이다. test/stress를 보고 모델이나 특징을 바꾼 뒤 그 점수를 독립 최종 점수로 다시 부르면 안 된다.

### 10.3 Early stopping이 무엇을 하는지와 이번 관찰

학습 중 train NLL은 보통 계속 낮아질 수 있다. train NLL은 내려가는데 validation NLL이 올라가기 시작하면 학습 표본에 더 맞으면서 선택 그룹에서 덜 맞는 상황일 수 있어 과적합 의심 신호다. 두 곡선의 간격, 후보 간 validation NLL, 오답이 모이는 클래스를 함께 본다.

이번 선택 MLP의 train NLL은 epoch400에서 0.435238, validation NLL은 0.467992다. 두 곡선은 epoch400까지 감소했다. max epoch라는 경계에 도달했으므로 이후에도 같은 추세인지 모른다. 과적합이 전혀 없음을 증명하지도, 과적합이 발생했음을 증명하지도 않는다. 학습 epoch를 더 허용하는 선택은 별도 개발용 검증 계획에 넣어야 한다.

### 10.4 Temperature: 확률 보정과 분류 결정

선택 모델 logit 행 z를 양수 temperature T로 나눠 softmax한다.

$$
p_k(T)=\frac{\exp(z_k/T)}{\sum_c\exp(z_c/T)}
$$

구현은 T를 0.1~10의 로그 간격 81개 후보로 정하고 T=1을 기준에 포함한다. calibration 자료의 NLL이 가장 작아지는 T를 고른다. 이번 선택값은 T=0.9440608763이다. T<1은 확률을 더 뾰족하게 하고, T>1은 더 고르게 한다. 이 과정이 항상 과신을 줄이는 것은 아니다. 양수 T로 나누어도 logit의 순서는 바뀌지 않으므로 argmax 클래스와 정확도는 그대로다. NLL·Brier 같은 확률의 질은 달라질 수 있다.

손으로 보는 예로 logits=(2,1,0)일 때 T=1의 첫 확률은 e²/(e²+e+1)≈0.6652이고 정답이 class0이면 NLL≈0.4076이다. T=2에서는 확률 약 0.5065, NLL 약 0.6802다. 더 고른 확률이 이 표본의 정답 확률을 낮추어 NLL을 높였다. 실제 선택은 calibration 전체 NLL을 81개 grid에서 비교한 결과이지 이 한 행 계산으로 유도한 값이 아니다.

이번 test에서 보정 전/후 NLL은 0.442877→0.438500, 정확도는 모두 0.8125다. stress NLL은 0.871707→0.880226으로 올라갔다. calibration에 맞춘 온도가 모든 다른 분할을 개선한다고 보장하지 않는다.

## 11. 분류 지표를 직접 읽고 계산하기

### 11.1 정확도·precision·recall·F1

분류 확률에서 가장 큰 항목을 예측 클래스로 정한다. 정확도는 정확히 맞춘 행 수를 유효 평가 정답 수로 나눈 값이다.

클래스 k에 대해 TP는 그 클래스에서 맞은 수, FP는 다른 정답인데 k로 예측한 수, FN은 k 정답인데 다른 클래스로 예측한 수다.

$$
\mathrm{precision}_k=\frac{TP_k}{TP_k+FP_k},\qquad
\mathrm{recall}_k=\frac{TP_k}{TP_k+FN_k}
$$
$$
F1_k=\frac{2\,\mathrm{precision}_k\,\mathrm{recall}_k}
{\mathrm{precision}_k+\mathrm{recall}_k}
=\frac{2TP_k}{2TP_k+FP_k+FN_k}
$$

macro F1은 세 클래스 F1의 산술평균이다. 표본이 많은 클래스에 추가 가중치를 주지 않는다.

### 11.2 test 혼동행렬에서 sweep의 F1을 계산하기

혼동행렬의 행은 정답, 열은 예측이고 순서는 straight, sweep, turn이다.

$$
\begin{bmatrix}
40&3&5\\
15&32&1\\
1&2&45
\end{bmatrix}
$$

sweep 한 클래스를 직접 계산한다.

- TP=32: 정답 sweep 중 예측 sweep.
- FP=3+2=5: 정답 straight 또는 turn인데 sweep으로 예측.
- FN=15+1=16: 정답 sweep인데 straight 또는 turn으로 예측.
- precision=32/(32+5)=32/37≈0.8649.
- recall=32/(32+16)=32/48≈0.6667.
- F1=64/(64+5+16)=64/85≈0.7529.

나머지 두 F1은 straight 80/104≈0.7692, turn 90/99≈0.9091이다. 평균은 (0.7692+0.7529+0.9091)/3≈0.8104다. 대각선 합은 40+32+45=117이고, 117/144=0.8125가 test accuracy다.

### 11.3 NLL과 Brier는 확률을 본다

accuracy는 맞았는지만 본다. 같은 정답이 class1인 두 예측 A=(0.6,0.3,0.1), B=(0.99,0.005,0.005)은 둘 다 argmax가 class0이므로 둘 다 오답이고 accuracy 관점에서 동률이다. NLL은 정답 class1 확률을 봐서 A는 −ln(0.3)≈1.204, B는 −ln(0.005)≈5.298이다. 틀렸을 때 잘못된 확신이 더 큰 B를 NLL이 더 나쁘게 평가한다.

multiclass Brier는 각 행의 세 확률과 one-hot 정답 차이를 제곱해 더한 뒤 평균한다.

$$
\mathrm{Brier}
=\frac1N\sum_i\sum_{k=1}^{3}
(p_{ik}-q_{ik})^2
$$

낮을수록 확률 분포가 정답에 가깝다. 확률 배열로 평가 NLL을 계산할 때는 정답 확률의 하한으로 float64의 최소 양의 정규수 np.finfo(np.float64).tiny, 약 2.2251×10⁻³⁰⁸을 사용한다. 확률이 이보다 작으면 하한으로 올린 뒤 로그를 취한다. 이는 표현 가능한 가장 작은 양수인 약 5×10⁻³²⁴와 다르다. 학습 손실은 8.2절의 안정한 log-softmax로 계산한다.

## 12. 기존 실행의 수치와 해석 한계

다음은 저장된 report.json의 seed42 합성 실행이다. 각 표본 수와 클래스 support는 모든 split에서 유효 100%였고 유보는 0개다.

| split | 그룹 / record | support straight,sweep,turn | accuracy | macro F1 | NLL | Brier |
|---|---:|---|---:|---:|---:|---:|
| train | 36 / 432 | 144,144,144 | 0.8264 | 0.8271 | 0.4302 | 0.2422 |
| validation | 12 / 144 | 48,48,48 | 0.7708 | 0.7734 | 0.4641 | 0.2728 |
| calibration | 12 / 144 | 48,48,48 | 0.8125 | 0.8125 | 0.4453 | 0.2619 |
| test | 12 / 144 | 48,48,48 | **0.8125** | **0.8104** | **0.4385** | **0.2564** |
| stress | 12 / 144 | 48,48,48 | **0.6181** | **0.6180** | **0.8802** | **0.4998** |

train에서 정한 다수 클래스 기준 예측은 각 클래스가 균형이므로 test와 stress에서 accuracy 0.3333, macro F1 0.1667이다. 선택 모델은 이 단순 기준보다 이번 합성 경로 유형을 잘 분류했다. 이는 실제 조업 분류 점수가 아니다.

test의 48개 sweep 중 15개가 straight로 예측됐다. 이 한 관찰만으로 특징 부족, 생성기 겹침, noise, 표본 변동 중 하나를 원인으로 확정할 수 없다. 스트레스 정확도는 test보다 0.1944, 즉 약 19.44 percentage points 낮다. 하지만 test와 stress는 다른 12개 그룹이고 stress에는 척도·잡음·누락·단절 네 변경이 동시 적용됐다. 따라서 이 하락을 어느 한 조건의 순수효과나 과적합의 증거라고 부르지 않는다.

### 12.1 95% 구간이 말하는 것

현재 구간은 각 평가 split에서 선박 12개를 복원추출하고, 선택된 선박의 record를 모아 지표를 계산하는 vessel-level bootstrap이다. 이를 200회 반복해 2.5%, 97.5% 분위수를 저장했다.

| 분할 | accuracy 95% bootstrap 구간 | macro F1 95% bootstrap 구간 |
|---|---|---|
| test | 0.7639~0.8752 | 0.7549~0.8747 |
| stress | 0.5417~0.6875 | 0.5353~0.6866 |

이 구간은 해당 생성기와 현재 한 번의 학습 실행 아래 그룹 표본 변동을 요약한다. 생성기가 현실을 대표하지 않을 가능성, 모델 초기화/데이터 생성 seed 간 변동, 새 해역 변동은 포함하지 않는다. 모집단 일반화 보증으로 읽지 않는다. CI라는 이름만으로 실험의 모든 불확실성을 덮지 않는다.

## 13. 분류 확률과 별개인 이상 분포 점수

classifier의 세 확률은 “세 합성 클래스 중 어느 logit이 상대적으로 큰가”를 표현한다. anomaly score는 train 각 클래스의 분포 중심에서 입력이 얼마나 떨어졌는지를 표현한다. 둘은 다른 계산이다.

각 클래스 k의 train feature 평균을 μ[k], 표본 공분산을 S[k], 차원을 d라 하자. 이 공분산은 전처리한 16열에서 계산하며 분모는 max(n[k]−1,1)이다. feature 7의 점구름 공분산 분모 m[j]와 다른 정의다.

$$
S_k=\frac{(X_k-\mu_k)^T(X_k-\mu_k)}{\max(n_k-1,1)}
$$

v=trace(S)/d, shrinkage α=0.2로 공분산을 안정화한다.

$$
r=\max(10^{-6},10^{-6}v),\qquad
\Sigma_k=(1-\alpha)S_k+(\alpha v+r)I
$$

상대적으로 불안정한 대각 성분을 평균 분산 v 쪽으로 당기고 작은 ridge r을 더해 역행렬이 가능하게 한다. 한 입력 x의 클래스별 제곱 Mahalanobis 거리는

$$
d_k^2(x)=(x-\mu_k)\Sigma_k^{-1}(x-\mu_k)^T
$$

이고 모델은 세 값 중 최솟값을 반환한다. 큰 값은 세 학습 클래스 중심 모두에서 멀다는 뜻이다. 거리 하나가 사고, 실제 이상, 위험의 확률인 것은 아니다. 공분산을 쓴다고 입력이 정규분포라고 검증된 것이 아니며, 이 임계값은 χ² 분포의 임계값이나 유의확률이 아니다.

validation 거리의 95번째 백분위수 17.6125588을 고정 임계값으로 쓰며 점수가 임계값보다 엄격히 클 때만 flag를 켠다. 이 선택은 보장된 오탐률이나 conformal prediction 보장이 아니다. 기본 실행 test의 임계 초과율은 0.0139, stress는 0.3819다.

두 종류 출력이 다르게 보일 수 있는 예가 실제로 저장돼 있다. S0-train-000-sweep-01은 보정 확률이 대략 [0.00106, 0.97243, 0.02650]으로 sweep에 큰 확률을 주지만, 학습 분포 거리 점수는 약 40.9068로 임계값 17.6126보다 크다. “세 합성 클래스 중 sweep이 상대적으로 가장 그럴듯하다”와 “어느 학습 클래스 분포 중심에도 가깝지 않다”는 동시에 성립할 수 있다. 이것은 사고나 오분류를 확정하지 않는다.

test에서 가장 긴 부분선의 중간 좌표에 (1500,−1500) m를 더한 좌표 교란 검산은 60쌍 모두 거리 점수를 높였고 증가량 중앙값은 5234.10이었다. 큰 인위적 입력 교란에서 점수가 어떻게 반응하는지를 본 것이다. 사고 탐지율이나 실제 센서 오류 검출 성능은 측정하지 않았다.

## 14. 저장 자료 한 건으로 feature → 전처리 → logit → 확률 따라가기

기존 sample_dataset.json과 model.json을 읽고 분류기를 다시 학습하지 않은 단일 trace다. 표본은 S0-test-000-straight-00, 합성 정답 0(straight), 생성 원점 68개 중 누락 처리 후 64개를 관측했으며 6부분선이다.

여덟 raw feature는 순서대로 다음과 같다.

$$
[6.345788,\;0.998170,\;0.048132,\;0.146725,\;0.059866,\;0.151943,\;0.021914,\;0.019938]
$$

모든 특징이 관측되어 결측 mask는 [0,0,0,0,0,0,0,0]이다. 저장된 학습 통계로 바꾼 16열은 아래와 같다.

$$
[-2.031665,\;0.531320,\;-0.423997,\;-0.586482,\;-0.240681,\;-0.239254,\;-0.731622,\;-0.824860,\;0,0,0,0,0,0,0,0]
$$

분류기 logits는 [1.311668, −1.077751, −0.766252]다. logit이 양수·음수라는 것 자체는 확률이나 맞음·틀림을 뜻하지 않는다. 보정 전 확률은 [0.821778, 0.075343, 0.102879]다. T=0.9440608763을 적용한 보정 후 확률은 [0.840148, 0.066858, 0.092994]이며 합은 1이다. 예측 argmax는 class0이고 생성기 label과 일치한다. anomaly score는 9.5532로 기준 17.6126 이하이지만, “안전” 판정은 할 수 없다.

다음은 이 파일들로 같은 추론 경로를 만드는 짧은 Python 예다.

```python
import numpy as np
from fishing_demo.data import load_dataset
from fishing_demo.features import extract_features
from fishing_demo.pipeline import load_model
from fishing_demo.models import Preprocessor, Classifier, AnomalyModel, softmax

data = load_dataset("outputs/sample_system/sample_dataset.json")
bundle = load_model("outputs/sample_system/model.json")
row = next(r for r in data["records"]
           if r["sample_id"] == "S0-test-000-straight-00")
detail = extract_features(row)

X8 = np.array([[np.nan if v is None else v
                for v in detail["values"]]], dtype=float)
Z16 = Preprocessor.from_dict(bundle["preprocessor"]).transform(X8)
model = Classifier.from_dict(bundle["classifier"])
logits = model.predict_logits(Z16)
probabilities = softmax(logits, bundle["temperature"])
scores = AnomalyModel.from_dict(bundle["anomaly_model"]).score(Z16)

print("features:", detail["values"])
print("scaled + missing mask:", Z16[0].tolist())
print("logits:", logits[0].tolist())
print("probabilities:", probabilities[0].tolist())
print("anomaly score:", float(scores[0]))
```

이 trace는 저장된 모델과 저장 자료가 연결되는 계산 예다. test 한 표본의 정답을 보고 모델을 다시 맞추거나 후보 선택에 사용하지 않았다. 실제 전체 점수는 144개 test 표본의 결과이며, 한 사례를 전체 성능으로 일반화하지 않는다.

## 15. 코드 읽기 순서와 실제 구현 발췌

### 15.1 함수별 학습 순서

| 순서 | 파일과 함수 | 읽을 질문 |
|---:|---|---|
| 1 | fishing_demo/data.py: _path, generate_dataset | 라벨 이름이 어떤 heading 식과 난수 범위에서 나오는가? |
| 2 | fishing_demo/data.py: validate_record, validate_dataset | 어떤 좌표·시간·ID 오류를 거절하고 무엇을 조용히 보정하지 않는가? |
| 3 | fishing_demo/features.py: extract_features, feature_matrix | 부분선 경계와 null 값이 여덟 특징 및 NaN 배열에 어떻게 남는가? |
| 4 | fishing_demo/models.py: Preprocessor.fit, transform | 대치·표준화 통계는 어디서 맞추고 어떻게 16열이 되는가? |
| 5 | fishing_demo/models.py: Classifier._forward, loss_and_gradients | 행렬 크기·logit·gradient가 식과 맞는가? |
| 6 | fishing_demo/models.py: Classifier.fit | 어느 기준으로 checkpoint를 저장하고 언제 되돌리는가? |
| 7 | fishing_demo/models.py: fit_temperature, classification_metrics, AnomalyModel | 보정·확률 지표·분포 거리의 자료와 의미가 각각 무엇인가? |
| 8 | fishing_demo/pipeline.py: split_indices, train_experiment, predict_records | 그룹 누출을 막고 각 split의 역할을 보장하는가? |
| 9 | fishing_demo/visualization.py: write_dashboard | 저장 JSON을 어떻게 자체 포함 HTML로 안전하게 표시하는가? |
| 10 | tools/run_sample_system.py: main | CLI 명령·입력 파일·출력 경로 제한이 무엇인가? |

### 15.2 코드에서 확인하는 짧은 부분

feature_matrix는 None을 NaN으로 바꾸며 각 record의 상세 정보도 함께 보관한다.

```python
values = [[np.nan if value is None else value
           for value in item["values"]]
          for item in extracted]
X = np.asarray(values, dtype=float)
```

전처리는 fit 때 저장한 train median·mean·scale만 사용하고, 원래 누락 여부를 끝에 붙인다.

```python
missing = np.isnan(values)
filled = np.where(missing, self.medians_, values)
scaled = (filled - self.means_) / self.scales_
return np.concatenate((scaled, missing.astype(float)), axis=1)
```

파이프라인은 다섯 후보를 맞춘 뒤 validation의 보정 전 NLL만 사용해 고른다.

```python
best = min(range(len(candidates)),
           key=lambda i: (candidates[i]["validation_metrics"]["nll"], i))
model = fitted[best]
temperature = fit_temperature(
    model.predict_logits(Z["calibration"]),
    y[indices["calibration"]])
```

이 발췌는 원 코드의 실제 구조를 축약한 부분이다. 표본 생성·검사, 유효 label mask, 저장 bundle의 클래스 순서·차원 검사 등은 각각 다른 함수가 담당한다.

## 16. CLI 사용과 산출물 확인

명령은 저장소 루트에서 실행한다. 런타임에 필요한 외부 수치 라이브러리는 NumPy이며 Python 표준 라이브러리를 사용한다.

저장된 실행 기록의 환경은 Python 3.13.3과 NumPy 2.2.5다. 프로젝트의 의존성 파일로 환경을 준비할 수 있다.

```powershell
python -m pip install -r requirements-sample.txt
```

아래 명령은 목적별 실행 방법이다. 전체 실험을 재현할 때는 demo 하나를 사용하고, 과정을 나누어 관찰할 때는 generate → train → predict를 사용한다. 동일한 출력 폴더의 산출물은 갱신되므로 기존 실험을 보존하려면 별도의 --out 폴더를 지정하고 입력 경로도 그에 맞춘다.

```powershell
# 전체 기본 흐름: 생성, 학습, 선택, 보정, test/stress 평가, JSON/HTML 저장
python tools/run_sample_system.py demo --out outputs/sample_system --seed 42 --epochs 400

# 데이터 생성만
python tools/run_sample_system.py generate --out outputs/sample_system --seed 42

# 생성한 fishing_sample_v1 JSON으로 학습
python tools/run_sample_system.py train --data outputs/sample_system/sample_dataset.json --out outputs/sample_system --seed 42 --epochs 400

# 저장된 합성 모델로 재학습 없이 예측
python tools/run_sample_system.py predict --data outputs/sample_system/sample_dataset.json --model outputs/sample_system/model.json --out outputs/sample_prediction
```

실제 CLI는 기본 command를 demo, 기본 --out을 outputs/sample_system, --seed 기본값 42, --epochs 기본값 400으로 둔다. seed는 0 이상, epochs는 1~400이어야 한다. train에는 --data가 필요하고 predict에는 --data와 --model이 필요하다. generate는 sample_dataset.json, demo는 dataset/model/report/predictions/dashboard, train은 model/report/predictions/dashboard, predict는 predictions.json을 만든다. CLI는 docs, tools, fishing_demo, tests, data/raw 등 보호 경로에 출력하거나 입력을 덮어쓰는 경로를 거부한다.

demo를 같은 출력 디렉터리에 다시 실행하면 그 명령이 만드는 파일을 갱신한다. 이전 실행을 보존하려면 별도의 --out 디렉터리를 지정한다.

이 CLI는 일반 CSV를 실제 자료처럼 받지 않는다. generate/train/predict 모두 합성 스키마와 synthetic/local_xy_m 모델 계약에 묶여 있다. 문자열 하나만 synthetic에서 real로 바꾸거나 local CRS를 실제 좌표계라고 바꿔 쓰는 방법은 안전한 adapter가 아니다. predict는 저장된 대치·표준화, 가중치, 온도, 이상 거리 모델을 읽어 재사용하며 재학습하지 않는다. 기본 train/demo 실행은 저장 모델을 다시 읽어 동일 데이터에 재추론한 결과가 처음 예측과 같은지 비교한다.

## 17. 대시보드에서 확인할 것과 오독 방지

화면은 report와 predictions JSON을 포함한 네트워크 없는 자체 포함 HTML이다. 경로 그림·필터·확률·feature 표·부분선 계산·혼동행렬·loss 곡선은 설명을 돕는 도구다.

1. **화면의 범위:** 상단에서 synthetic, local XY, seed를 확인한다. 실제 지도나 실제 운항이 아니다.
2. **부분선 그림:** X·Y는 같은 축척의 미터이고 각 부분선은 다른 선으로 그려진다. 빈 구간을 자동 연결하지 않는다. 시작·끝 표시와 부분선별 길이·변위·직선성을 함께 본다.
3. **표본 필터:** split·합성 정답·ID 검색으로 샘플을 찾는다. 한 표본의 모양만 보고 전체 정확도를 판단하지 않는다.
4. **분류 패널:** 합성 정답, 예측, temperature를 적용한 클래스 확률을 읽는다. 이 확률을 실제 조업 행동의 확률로 바꾸어 해석하지 않는다.
5. **분포거리 패널:** 점수와 validation 95백분위 임계값 초과 여부를 본다. 초과는 세 합성 클래스 중심에서 먼 입력이라는 뜻일 뿐 사고·안전 판정이 아니다. 임계 이하도 안전 보증이 아니다.
6. **혼동행렬:** 행은 정답, 열은 예측이다. diagonal 합은 맞은 표본 수, 각 행 합은 class support다. test와 stress를 전환해도 조건이 다르고 그룹이 다르다는 사실을 기억한다.
7. **학습곡선:** train과 validation NLL을 함께 비교한다. validation 최저 checkpoint를 저장한다. 이번 선택 epoch 400 표시는 조기 종료가 일어나지 않았다는 뜻이다. validation이 계속 낮다고 미사용 실제자료 성능까지 좋다고 말할 수 없다.
8. **후보·감사 표:** 후보 NLL, seed, 그룹 분리, 데이터 hash, 선택 역할, 제한사항을 본다. 후보가 여러 개라는 이유로 test를 반복해 탐색하면 안 된다.

화면은 계산 결과를 보여주지만 원인 자체를 증명하지 않는다. 낮은 정확도의 이유를 특정 feature로 확정하려면 그 feature를 통제하는 개발 실험이 필요하다. 축·단위가 실제 지도를 뜻하는 것처럼 보이거나, 점수가 사고확률처럼 보여서는 안 된다.

## 18. 과적합·낙관 편향을 다루는 실제 절차

### 18.1 현재 실행에서 이미 지킨 통제

- vessel ID별 그룹을 train/validation/calibration/test/stress로 분리했다.
- 중앙값·평균·표준편차와 분류 가중치·공분산은 train에만 fit했다.
- 후보는 미리 고정한 다섯 개다. validation NLL로만 epoch와 후보를 선택했다.
- temperature는 선택을 마친 뒤 별도 calibration에서 맞췄다.
- test/stress는 마지막 보고에만 쓰고 재선택하지 않았다.
- 저장 bundle은 feature 이름·단위·클래스 순서·입력 차원과 synthetic 좌표 계약을 검사한다.
- 저장 모델과 재로딩 추론의 표본별 예측이 같음을 report의 audit에 기록한다.

이 통제는 현재 데이터와 설정의 누출 위험을 줄인다. 과적합이나 편향을 모두 없애지는 않는다.

### 18.2 validation도 반복 선택에 과적합될 수 있다

test를 잠갔다고 해서 선택 편향이 사라지는 것은 아니다. 후보와 특징을 validation 결과에 맞춰 계속 바꾸면 작은 validation 그룹의 우연한 조건에 맞는 설계를 고를 수 있다. 이것이 validation 선택 과적합 위험이다. 이번 실행은 seed42와 사전 후보 5개를 비교한 제한된 한 번의 실험이다. 이 결과를 보고 현재 test/stress에 맞춰 특징·후보·임계값을 고치지 않는다.

다음 탐색은 아래 계획을 실행 전에 고정한다.

1. 개발용 선박 그룹 안에서 GroupKFold 등 그룹 교차검증을 쓰거나, 아직 모델 선택에 쓰지 않은 개발 그룹을 별도로 둔다.
2. 후보 수 예산, 지표, 생성 seed 목록, 모델 초기화 seed 목록을 실행 전에 선언한다.
3. 지정 seed 전체 결과를 보고하며 최고 seed 하나만 골라 발표하지 않는다.
4. 현재 API는 하나의 seed를 데이터 생성과 모델 초기화에 함께 전달한다. 후속 계획에서 generator_seed와 model_init_seed를 별도 입력·보고 필드로 나눈다. 현재 API가 이미 분리됐다고 말하지 않는다.
5. 특징과 후보를 동결하고 별도 calibration으로 보정한 뒤, 끝까지 사용하지 않은 test 그룹에서 한 번 최종평가한다. 그 결과를 보고 변경하면 새 미사용 평가 그룹이 필요하다.

### 18.3 test/stress 차이를 분해하는 실험

현재 test 정확도 0.8125와 stress 0.6181의 차이 약 19.44%p에는 다른 vessel 그룹 표본과 네 조건 동시 변경이 들어 있다. 그 수치만으로 잡음의 효과, 누락의 효과, 단절의 효과, 과적합 중 무엇이 원인인지 말할 수 없다.

원인을 알아보려면 개발 그룹에 한해서 같은 잠재 원경로·방향·이동 원점·난수 흐름을 공유하고, 길이 배율 또는 잡음 또는 누락 또는 단절률 중 하나만 달리한 paired 실험을 사전 설계한다. 각 쌍의 feature·유보 상태·예측 변화와 vessel 단위 성능을 비교한다. 비교 강도와 지표를 보기 전에 고정한다. 최종 test/stress를 조건 탐색용으로 되돌려 쓰지 않는다.

누락은 모델이 보는 정보 자체를 줄인다. paired 점수가 떨어져도 그 원인이 입력 정보 손실인지 모델 민감도인지 완전히 분리했다고 자동으로 주장하지 않는다. 합성 생성기의 원래 경로를 알고 있는 개발 예제라면 삭제 전·후의 feature 변화도 볼 수 있지만, 현실에서 관측하지 못한 위치의 참 경로를 안다고 가정하지 않는다.

### 18.4 점수 차와 불확실성

test/stress 각각 12개 그룹은 큰 모집단을 대표한다고 보장되지 않는다. bootstrap 구간이 겹치는지 여부만으로 유의성이나 원인을 단정하지 않는다. 여러 seed를 실행해도 최고 성능 seed를 고르면 다시 선택 편향이 생긴다. 신뢰할 평가를 위해 모든 사전 선언 seed를 보고하고, 모델 동결 뒤 새 그룹에서 평가한다.

### 18.5 성능 개선 후보를 검증하는 방법

18절의 통제와 다음 실험을 연결하면 성능 개선을 검증 가능한 작업으로 바꿀 수 있다. 아래는 아직 수행하지 않은 개발 실험의 예다. 어느 변경이든 개발 자료에서 비교하고 선택을 마친 뒤 미사용 평가자료로 확인한다.

| 개발 자료에서 확인한 문제 | 변경 후보와 수식 연결 | 비교 방법 |
|---|---|---|
| 라벨 정의가 모호함 | 학습 목표 y의 단위·출처부터 정리 | 라벨 감사와 근거 확인을 먼저 수행; 정답 변경 이력 보존 |
| 길이·관측 밀도 변화에 민감함 | 로그 길이 특징과 무차원 비율 특징의 역할을 분리 | 특정 특징만 뺀 ablation과 조건 하나씩 바꾼 짝 실험 |
| 학습 손실은 줄고 개발 손실은 커짐 | 가중치 벌점 λ, 모델 크기, 선택 epoch를 조정 | 고정 후보 예산과 선박 그룹 교차검증으로 비교 |
| 일부 클래스만 잘 맞힘 | 평균 정확도 외 클래스별 recall·F1 확인 | 충분한 라벨 표본 확보; 가중 손실 등은 별도 후보로 검증 |
| 정답은 맞지만 확률이 부정확함 | 별도 보정 자료에서 온도 T를 조정 | accuracy와 NLL/Brier를 함께 보고 보정의 효과를 구분 |

이 절차는 정확도를 높일 가능성이 있는 변경을 고르는 방법이다. 결과가 나빠지거나 개선 근거가 없으면 기존 기준선을 유지하고 실패 원인을 기록한다. 합성 정확도 상승만으로 실제자료 범용성이 향상됐다고 결론내리지 않는다.

## 19. 실제자료용 adapter를 만들기 전의 계획

현재 코드는 합성 전용이다. model bundle 검증은 source_type=synthetic, coordinate_system=local_xy_m, 고정 클래스명·순서, 여덟 feature 이름·단위, 16개 입력, 3개 출력을 요구한다. 문자열 하나만 synthetic에서 real로 바꾸거나 local CRS를 실제 좌표계라고 바꿔 쓰는 방법은 안전한 adapter가 아니다. 일반 CSV를 받는 실제 pipeline은 구현되지 않았다.

실제 자료가 도착하면 다음을 별도 입력 adapter와 새 계약으로 정의한다.

### 19.1 수신·좌표·시간 확인

1. 원본 파일·버전·해시·사용 권한·출처를 기록하고 실제 내용을 열람한다.
2. 관측 단위와 필드 유형을 확인한다. 위치가 위도·경도인지 projected XY인지, CRS와 축 순서, 거리 단위를 확인한다. 위경도를 미터로 바로 취급하지 않는다.
3. 관측시각의 시간대·단위·중복·누락·순서·샘플 간격을 확인한다. 시스템이 그 자료를 언제 이용 가능했는지 available time도 구분한다.
4. 원자료가 명시한 부분선 단절, 장비 누락, 정박, 품질 오류를 보존한다. 증거 없이 부분선을 연결하지 않는다.
5. 좌표별 검증된 시각이 확보될 때까지 속력·가속도 특징을 만들지 않는다. sim_times를 실제 시간으로 승격하지 않는다.

### 19.2 라벨 mapping과 평가 분할

1. 실제 예측 대상이 무엇인지 먼저 정의한다. 현재 straight/sweep/turn에서 실제 fishing_code로 바로 치환하지 않는다.
2. 각 fishing_code의 정의와 다중·모호 라벨, 라벨 출처, 검토 절차를 확보한다. 선박 고정 업종인지, 시간별 활동인지, 항차 상태인지 확인한다. 라벨 불확실 표본은 임의 매핑하지 말고 별도 상태로 보존한다.
3. 사고 label이 별도로 없으면 사고 탐지 모델이라 부르지 않는다. 사고 누락이나 “High” 같은 proxy를 사고 정답으로 만들지 않는다.
4. 사용 질문에 맞춰 선박·항차·시간 기준을 설계한다. 미래 시점 예측이면 시간 순서를 지키고, 새로운 선박 일반화를 묻는다면 선박 ID를 분리한다. 새 해역 주장을 하려면 해역도 holdout한다. 같은 선박·trip이 train/test 양쪽에 새지 않게 한다.
5. 모델·변환·정상 분포 통계는 train 그룹만으로 적합한다. validation에서 후보를 선택하고 필요하면 별도 calibration을 둔다. 끝까지 잠근 test에서 처음 최종 평가한다.

### 19.3 구현·배포 전 평가

실제 adapter는 source provenance, CRS, 좌표 순서·단위, 시간과 available-time, part 경계, label mapping 버전을 입력 계약으로 기록한다. 실제 데이터의 feature 계산과 결측 사유가 합성 코드와 동일하다고 보지 말고 원자료 몇 건을 손으로 대조한다. 모델 bundle에는 실제 전처리·feature schema·class mapping·학습 자료 hash·split 기준을 버전으로 저장한다.

실제 평가에는 baseline, 클래스별 support·precision·recall·F1, 혼동행렬, NLL/Brier, 유효·유보율, 그룹 bootstrap 및 분포별 실패를 포함한다. 운영 임계값이나 오류 허용 기준은 실제 사용 목적과 비용을 확인한 뒤 정한다. 정확도 향상, 실제 범용성, 과적합 방지는 보장되지 않는다. 외부 환경 관측, 실제 운용, 물리 digital twin, sequence·3D 확장은 이번 구현 범위를 넘어선 별도 관문이다.

### 19.4 실제 환경자료를 연결할 때의 시점 조건 — 후속 설계

현재 코드는 기상·해양 환경자료를 수집하거나 입력에 넣지 않는다. 후속 단계에서 환경자료가 필요하다고 판단되면 자료의 위치, 관측시각, 시스템 이용 가능 시각, 단위와 해상도를 계약에 추가한다. 예를 들어 바람이나 수온을 사용한다는 아이디어가 있어도, 지금 자료를 확보했거나 성능 개선을 확인한 것은 아니다.

예측 시각을 t₀, 외부 관측의 관측시각을 t_obs, 실제 이용 가능 시각을 t_avail이라 하자. 현재까지의 관측을 결합하는 설계에서는 다음 두 조건을 함께 확인한다.

$$
t_{\mathrm{obs}}\le t_0,\qquad t_{\mathrm{avail}}\le t_0
$$

관측은 과거에 이루어졌어도 나중에 공개·보정된 값이라면 t₀에서 알 수 없었던 값일 수 있다. 예보자료는 관측자료와 구분하고 예보 발표시각·이용 가능 시각을 기준으로, 당시 실제 사용할 수 있었던 버전만 고른다. 미래를 대상으로 한 예보의 유효시각 자체를 미래 정보 누출과 혼동하지 않는다.

공간적으로는 선박 위치와 환경 격자 사이의 거리, 육지·해역 경계, 해상도 차이를 확인하고 결합 규칙을 고정한다. 관측시각을 확인할 수 없는 항적에 환경값을 억지로 시간 정렬하지 않는다. 매칭 실패·자료 오래됨·결측을 표시하고, 대치 통계는 train에서만 계산한다. 외부 자료를 넣은 모델은 동일한 평가 설계에서 기존 기하 기준선과 비교해야 한다. 외부 자료가 추가됐다는 사실만으로 정확도나 일반화가 좋아졌다고 볼 수 없다.

## 20. 단계별 학습 활동과 기술 관문

각 단계는 기술적 산출물뿐 아니라 학습자가 설명할 내용을 둔다. 다음 단계로 넘어가기 전에는 이전 단계의 동작과 이해를 확인한다.

| 단계 | 기술 목표 / 학습 목표 | 구현물·관찰 현상 | 검증 방법 | 다음 단계 조건 |
|---|---|---|---|---|
| A. 계약 읽기 | JSON·class order·split 역할 설명 | metadata/record 예시와 전체 flow | label과 metadata를 feature에 넣지 않는 이유 설명 | source·unit·unknown을 구분 |
| B. 생성기 | heading 식과 그룹 nuisance 설명 | seed 42에서 84그룹·1008 record | label별 angle family, 겹치는 범위, stress 변경 확인 | 합성 라벨이 조업 사실이 아님을 설명 |
| C. 기하 | 부분선 내에서 길이·각도 계산 | ㄱ자 손계산, 부분선 2개 예 | D/L, angle pool, H/L 계산; gap을 임의 연결하지 않음 | 누락·closed part에서 null 조건 설명 |
| D. 전처리 | train-only median·scale·mask 설명 | 8 raw + 8 mask = 16열 | 실제 test 첫 record의 z1을 저장 통계로 재계산 | 결측 0과 실제 0을 구분 |
| E. 분류 수식 | softmax·CE·L2·역전파 설명 | 한 행 손계산, 매트릭스 차원 표 | finite difference의 검산 의미 설명 | gradient와 학습 목적 구분 |
| F. 평가 경계 | 후보·epoch·T의 역할 설명 | candidate table, 혼동행렬, CI | sweep F1 직접 계산; test/stress 교란 한계 설명 | test 결과를 선택에 재사용하지 않음 |
| G. dashboard | 화면 값을 source JSON과 대조 | path, 확률, 점수, 곡선, 감사표 | ID를 바꿔 JSON 레코드와 화면이 맞는지 확인 | 확률·거리·실제 위험 오독 방지 |
| H. 실제자료 관문 | adapter 전에 근거 계약 수립 | 실제 파일 없음; 미구현 계획 | CRS/time/label/group/source 문서 확인 후 별도 승인 | 미확인 조건을 명시하고 새 평가 설계 |

학습자 본인의 구체적 수준·시간·실행 자원은 미확인이다. 이 표는 개념 순서이지 고정 수업 시간표가 아니다.

## 21. 복습 질문

답안을 보기 전에 각 질문을 두 문장 이내로 설명한다.

1. label 0,1,2는 실제 어업 현장에서 무엇을 뜻하나? 무엇을 뜻한다고 말할 수 없나?
2. 왜 같은 선박의 record를 행 단위로 무작위 분할하면 test 성능이 낙관적일 수 있나?
3. 부분선 직선성 평균 0.55가 ΣD/ΣL과 같다고 할 수 있나?
4. 짧은 부분선에서 회전각이 없으면 feature 값을 0으로 단정하지 않는 이유는?
5. train에서 대치·표준화하고 test에는 저장 통계를 적용하는 이유는?
6. p와 q가 한 행일 때 logit gradient가 p−q인 이유를 말해 보라.
7. L2 항은 어떤 파라미터에 들어가며 /2는 미분에서 무슨 역할을 하나?
8. 현재 후보 모두 best_epoch=400인 결과가 조기 종료 효과를 증명하나?
9. 온도 T가 0.944일 때 accuracy가 그대로일 수 있는 이유는?
10. test 혼동행렬에서 sweep의 precision, recall, F1을 계산하라.
11. accuracy가 같은 오답 두 개의 NLL이 달라질 수 있는 이유는?
12. softmax 확률이 0.97인데 Mahalanobis 점수가 임계값보다 높을 수 있나? 두 값은 무엇을 묻나?
13. 19.44%p test/stress 차이만으로 누락률의 순수 영향을 주장할 수 있나?
14. sim_times로 실선 속력을 계산할 수 있나?
15. test를 본 후 feature를 바꾸고 같은 test를 다시 최종평가라 부르면 왜 안 되나?
16. 실제자료에 source_type 문자열만 바꾸어 현 모델을 적용하면 무엇이 빠져 있나?

## 22. 답안 기준

1. 세 값은 생성기가 뽑은 경로 모양 분기다. 실제 조업·공식 fishing_code·사고 의미는 정해지지 않았다.
2. 같은 그룹의 표본이 방향·척도·잡음 조건을 공유해 train에서 본 그룹 특성이 평가에 새어들 수 있다.
3. 아니다. 각 부분선을 동일 가중하는 코드 평균은 0.55이고, 길이 가중 비율 예는 0.27이다.
4. 각도 자체가 없다는 정보와 관측된 직선의 회전 0은 다르다. 중앙값 대치와 missing mask로 그 차이를 남긴다.
5. test를 전처리에 쓰면 평가 대상이 fitting에 들어간다. 고정 train 통계만 적용해 독립성을 지킨다.
6. softmax 교차엔트로피를 logit에 대해 미분하면 각 클래스 확률에서 정답 indicator를 뺀다. 정답 클래스 확률이 낮으면 그 logit을 높이려는 gradient가 된다.
7. 가중치에만 λW가 추가되고 편향은 벌점이 없다. 1/2가 제곱 미분의 계수 2를 상쇄한다.
8. 아니다. 이번에는 patience 조건에 도달하지 않고 최대 epoch까지 갔다. 조기 종료가 구현되어 있다는 것과 이번 실행에서 작동했다는 것은 다르다.
9. 양수 온도는 클래스 logit의 순서를 보존하므로 argmax가 유지된다. 확률의 분산과 NLL/Brier는 변할 수 있다.
10. sweep TP=32, FP=5, FN=16이므로 precision 32/37≈0.8649, recall 32/48≈0.6667, F1 64/85≈0.7529다.
11. accuracy는 argmax만 보지만 NLL은 정답 클래스에 준 확률을 본다. 더 확신을 가지고 틀린 예측이 더 큰 벌점을 받는다.
12. 가능하다. softmax는 클래스 상대 순위의 정규화 확률이고 거리는 모든 학습 클래스 분포 중심과의 거리를 측정한다. 어느 쪽도 사고 확률이 아니다.
13. 아니다. 그룹이 다르고 길이·잡음·누락·단절 네 조건이 동시에 바뀌었다. paired 단일 조건 실험이 필요하다.
14. 아니다. sim_times는 생성된 초이며 실제 관측 시각과 실제 좌표가 아니다.
15. test가 변경 선택에 영향을 받은 순간 그 test는 새 선택에 독립적이지 않다. 다음 설계에는 새로운 미사용 평가 그룹이 필요하다.
16. 실제 CRS·좌표 단위·시각·라벨 정의·선박/항차 그룹·시간 가용성·학습 분할·평가 기준을 확인해야 한다. 현재 bundle은 합성 local XY metre와 고정 세 합성 class를 요구한다.

## 23. 팀 설명용 2분 요약

“이번 S0는 실제 라벨을 받기 전에 데이터 흐름과 모델 평가를 연습하도록 만든 합성 교육 실험입니다. 생성기는 84개 가상 선박 그룹에서 1008개 경로를 만들고, 각 표본의 방향·원점·척도·잡음·누락 조건을 포함합니다. straight, sweep, turn은 경로 생성 규칙의 이름이지 공식 조업 코드나 사고 라벨이 아닙니다. 누락과 단절은 부분선 경계로 보존하고, 그 사이를 임의로 잇지 않습니다.

각 record에서 여덟 기하 특징을 만들고 train에서만 중앙값 대치와 평균·표준편차를 맞춘 다음, 결측 mask를 붙여 16개 입력으로 사용합니다. 선형 모델과 tanh 16개 MLP의 사전 고정 다섯 후보를 train에서 학습하고 validation NLL로 선택했습니다. 온도는 별도 calibration에서 정하고 test와 stress는 마지막 결과만 보고합니다.

seed42의 선택 모델은 mlp16_l2_0로 validation NLL이 가장 낮았고 test accuracy 0.8125, stress 0.6181을 기록했습니다. 다섯 후보 모두 400 epoch까지 갔으므로 실제 조기 종료는 발생하지 않았습니다. stress와 test는 그룹이 다르고 네 조건이 동시에 달라 약 19.44%p 차이를 한 조건 효과나 과적합이라고 단정하지 않습니다. 선박 bootstrap 구간은 그룹 표본 변동만 요약하며 생성기 편향과 실제 환경의 불확실성을 포함하지 않습니다. 실제 어업·사고 성능은 검증되지 않았습니다. 실제 자료를 쓰려면 좌표·CRS·시간·available time·라벨 매핑·선박 및 항차 분할·독립 평가를 새 adapter와 계약으로 먼저 확인해야 합니다.”

## 24. 수학 → 코드 → 관찰 증거 연결

| 수학·개념 | 구현 위치 | 저장된 관찰 증거 | 주의할 해석 |
|---|---|---|---|
| heading family, 누적 이동 | data.py: _path, generate_dataset | sample_dataset.json, seed42 metadata | 생성 경로일 뿐 실제 운동 방정식 아님 |
| 길이·회전·spread·chord | features.py: extract_features | predictions.json feature/part_metrics, ㄱ자 계산 | 단절을 연결하지 않고 단위·결측을 유지 |
| train median/mean/std/mask | models.py: Preprocessor | model.json preprocessor, 8→16 trace | test 통계를 사용하지 않음 |
| softmax·NLL·L2 | models.py: softmax, Classifier.loss_and_gradients | candidate history, 수치 미분 테스트 기록 | 코드 국소 수식 검산은 일반화 증명이 아님 |
| epoch·후보 선택 | models.py: Classifier.fit, pipeline.py: train_experiment | report.json candidates, 선택명 mlp16_l2_0 | validation 반복 선택에도 편향 위험 |
| temperature grid | models.py: fit_temperature | report/model temperature=0.9440608763 | argmax 고정; 다른 split NLL은 악화될 수 있음 |
| 분류 지표 | models.py: classification_metrics | test confusion와 metrics | 실제 조업 지표가 아님 |
| bootstrap | pipeline.py: _bootstrap | 200회, 선박 단위 CI | seed·생성기 편향은 미포함 |
| shrinkage covariance/d² | models.py: AnomalyModel | threshold=17.6125588, anomaly report | 사고 확률·정규성 검증·보장된 오탐률 아님 |
| 입력-출력 통합 | pipeline.py: predict_records/run_demo | 저장 모델 재추론 동일 감사 항목 | artifact 재현은 데이터 타당성 검증이 아님 |
| 브라우저 표시 | visualization.py: write_dashboard | dashboard.html, 저장 검증 기록 | 실제 지도·센서·속도 화면 아님 |

## 25. 출처, 근거 상태, 미구현 범위

### 25.1 문서와 구현 근거

| 출처 | 본문에서 사용한 내용 |
|---|---|
| docs/sample_system_contract.md | JSON 계약, 클래스·split 역할, 모듈 입력/출력, 오류와 모델 범위 |
| docs/fishing_sample_system_guide.md | 기존 실습서의 생성·특징·수학·지표·학습 해석과 참고 링크 대조 |
| docs/fishing_sample_verification.md | 실행·검증 결과와 범위·제한 확인 |
| docs/fishing_execution_plan.md | S0 범위, 실제자료 관문, 학습 성취와 미확인 조건 |
| fishing_demo/data.py | seed 기반 그룹 생성, heading 가족, 난수 범위, 결측·stress 설정, sim_times 검증 |
| fishing_demo/features.py | feature 이름·순서·단위·예외·부분선 집계 |
| fishing_demo/models.py | 전처리, row-vector 분류기, gradient·L2·조기 종료, 지표·온도·공분산 |
| fishing_demo/pipeline.py | 유효 label mask, 그룹 분할, 후보·calibration·test 흐름, JSON 출력 |
| tools/run_sample_system.py | CLI 명령, 옵션 기본값·제약, 보호 경로 검사 |
| fishing_demo/visualization.py | 오프라인 HTML, 부분선 그림, 혼동행렬·곡선·확률·점수 표시 |
| outputs/sample_system/sample_dataset.json | 실제 생성 레코드·그룹·sim_times·quality |
| outputs/sample_system/model.json | 저장된 train 통계·가중치·온도·공분산·임계값 |
| outputs/sample_system/report.json | seed42 split 지표·candidate history·CI·감사·제한 |
| outputs/sample_system/predictions.json | 표본별 feature·확률·점수와 test 예시 |
| outputs/sample_system/test_summary.json, tests.log | 이전 구현 검증 실행의 저장 결과 |

### 25.2 무엇이 구현·계산됐고 무엇은 남았는가

| 구분 | 실제 상태 |
|---|---|
| 구현 | 합성 생성 → 검사 → 기하 특징 → train 전처리 → NumPy 선형/MLP 학습 → validation 선택 → calibration 보정 → test/stress 보고 → JSON·HTML |
| 계산된 예시 | ㄱ자와 부분선 예제는 수식을 손계산했다. 단일 S0 test trace는 저장 dataset/model을 다시 읽어 계산했으며 재학습하지 않았다. |
| 저장된 검증 기록 | test_summary.json은 총 91건 중 89 통과, 실패 0, 오류 0, 건너뜀 2를 보고한다. 두 건너뜀은 Windows symlink 생성 권한에 관련된 이전 실행 기록이다. 이 문서 작성 과정에서 이 테스트를 다시 실행하지 않았다. |
| 실제 데이터 평가 | 수행하지 않음. 원자료 기반 조업 분류·사고 탐지·일반화 성능을 확인하지 않음. |
| 실제 장치 실측 | 수행하지 않음. 전압·핀·전원·센서 범위·측정 지연 미정. |
| 교육 성취 평가 | 수행하지 않음. 문서를 읽거나 코드가 작동한 사실로 학습자의 설명 능력을 판정하지 않음. |
| 후속 계획 | 실제 파일의 source/CRS/time/available-time/label mapping 확인, 실제 adapter와 버전 계약, 선박·항차·시간 holdout, 별도 calibration과 미사용 test 설계 |
| 보장되지 않는 것 | 정확도 개선, 과적합 제거, 실제 해역·계절·선종 범용성, 사고 판별, 운영 적합성 |
| 선택적 확장 | 외부 환경자료, 물리 기반 digital twin, 시계열 모델, 3D는 이번 범위에 미구현이며 근거와 필요성을 확인한 후 별도 관문에서 판단 |

### 25.3 추가 이론을 더 읽을 때

아래 공식 scikit-learn 문서는 구현 의존성이 아니라 교차검증, 전처리 누출, MLP, 공분산 추정에 대한 일반 개념 참고다. 이 장의 수치와 실제 코드는 위에 적은 NumPy 구현 및 저장 산출물에서 확인했다.

- [Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html)
- [Cross-validation: evaluating estimator performance](https://scikit-learn.org/stable/modules/cross_validation.html)
- [Neural network models: supervised learning](https://scikit-learn.org/stable/modules/neural_networks_supervised.html)
- [Covariance estimation](https://scikit-learn.org/stable/modules/covariance.html)

## 26. 이 문서를 사용한 개인 학습 질문

다음 문장을 학습 도구에 입력하거나 혼자 답해 본다. 문서에 없는 실제자료 성능이나 새 실험 결과는 추정하지 않고 미확인으로 표시하도록 요청한다.

**기초 개념부터 공부하기**

> 이 문서만 근거로 어선 합성 시스템을 처음 배우는 사람에게 설명해 줘. 생성 라벨, 부분선, 특징, 손실, 검증의 뜻부터 시작하고 각 개념을 설명한 뒤 확인 질문 하나를 제시해 줘. 구현된 내용과 후속 계획을 구분해 줘.

**수식과 코드를 함께 읽기**

> 여덟 기하 특징에서 16차원 입력, MLP, softmax, 교차엔트로피와 역전파까지 연결해 줘. 각 수식의 기호·단위·배열 크기와 담당 함수를 함께 설명하고, 표본 수로 나누는 위치를 확인해 줘.

**실제 저장 표본의 계산 따라가기**

> S0-test-000-straight-00의 관측점과 부분선, 특징, 표준화, logit, 온도 보정 확률, 이상 점수를 이 문서의 숫자로 추적해 줘. 반올림 차이와 미확인 값을 구분하고 새로운 숫자를 만들어 넣지 마.

**과적합과 성능 개선을 판단하기**

> 이 문서에서 과적합 위험을 줄이는 장치를 찾고, 각각 어떤 누출·선택 편향을 줄이는지 설명해 줘. λ=0 선택, best epoch=400, test/stress 차이가 뜻하는 것과 뜻하지 않는 것을 구분해 줘. 후속 개선안은 아직 수행하지 않은 실험으로 표시해 줘.

**실제자료 도입 준비하기**

> 실제 항적이 도착했다고 가정하고 좌표계, 시각, 라벨, 부분선, 선박·항차·기간 분할과 외부자료 시점 조건을 어떤 순서로 확인할지 정리해 줘. 현재 확인된 사실과 실제 파일을 받아야 확인할 사실을 구분해 줘.

**답안을 가리고 복습하기**

> 21절 복습 질문에서 한 문제씩 내고 내 답을 기다려 줘. 답이 틀리면 정답을 바로 공개하기 전에 힌트를 주고, 마지막에 22절 답안 기준과 비교해 설명해 줘.

