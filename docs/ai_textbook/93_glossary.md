# 용어집

이 용어집은 교재의 주요 개념을 한국어·영어로 찾고 해당 장으로 이동하기 위한 색인이다. 자세한 조건과 계산은 각 장의 본문을 따른다.

## 문제와 데이터

| 한국어 | English | 짧은 정의 | 관련 장 |
|---|---|---|---|
| 인공지능 | Artificial Intelligence (AI) | 목표에 맞는 추론·예측·행동을 다루는 넓은 분야 | [01](chapters/01_problem_data.md) |
| 머신러닝 | Machine Learning (ML) | 자료에서 예측 규칙이나 표현을 학습하는 방법 | [01](chapters/01_problem_data.md) |
| 딥러닝 | Deep Learning (DL) | 다층 신경망을 중심으로 표현과 예측을 학습하는 ML 분야 | [01](chapters/01_problem_data.md) |
| 관측 단위 | Unit of analysis | 데이터의 한 행이 나타내는 사람·장비·시점 등의 단위 | [01](chapters/01_problem_data.md) |
| 특성 | Feature | 입력 사례를 설명하는 측정값 또는 속성 | [01](chapters/01_problem_data.md) |
| 목표값 | Target | 모델이 예측하도록 정의한 값 | [01](chapters/01_problem_data.md) |
| 레이블 | Label | 학습 사례에 연결된 정답 또는 범주 | [01](chapters/01_problem_data.md) |
| 지도학습 | Supervised learning | 입력과 목표값 쌍으로 예측 함수를 학습하는 설정 | [01](chapters/01_problem_data.md) |
| 비지도학습 | Unsupervised learning | 사람이 제공한 사례별 정답 없이 자료 구조를 찾는 설정 | [01](chapters/01_problem_data.md) |
| 자기지도학습 | Self-supervised learning | 자료 자체에서 만든 목표로 표현을 학습하는 설정 | [01](chapters/01_problem_data.md), [09](chapters/09_learning_paradigms.md) |
| 강화학습 | Reinforcement learning (RL) | 행동과 환경 상호작용에서 보상 신호로 정책을 학습하는 설정 | [01](chapters/01_problem_data.md) |
| 회귀 | Regression | 수치 목표를 예측하는 출력 과제 | [01](chapters/01_problem_data.md) |
| 분류 | Classification | 정해진 범주를 예측하는 출력 과제 | [01](chapters/01_problem_data.md) |
| 생성 | Generation | 문장·음성·이미지 등 구조화된 결과를 출력하는 과제 | [01](chapters/01_problem_data.md) |
| 손실함수 | Loss function | 학습 중 줄이도록 계산하는 오차 수치 | [01](chapters/01_problem_data.md) |
| 평가 지표 | Metric | 예측 결과를 사용 목적에 따라 요약하는 수치 | [01](chapters/01_problem_data.md) |
| 기준선 | Baseline | 새 모델의 효과를 비교할 단순 규칙 또는 기존 방법 | [01](chapters/01_problem_data.md) |
| 임계값 | Threshold | 확률을 양성·음성 결정으로 바꾸는 경계값 | [01](chapters/01_problem_data.md) |
| 혼동행렬 | Confusion matrix | TP·FP·FN·TN으로 분류 결과를 세는 표 | [01](chapters/01_problem_data.md) |
| 참양성 | True positive (TP) | 실제 양성이며 양성으로 예측한 사례 수 | [01](chapters/01_problem_data.md) |
| 거짓양성 | False positive (FP) | 실제 음성이지만 양성으로 예측한 사례 수 | [01](chapters/01_problem_data.md) |
| 거짓음성 | False negative (FN) | 실제 양성이지만 음성으로 예측한 사례 수 | [01](chapters/01_problem_data.md) |
| 참음성 | True negative (TN) | 실제 음성이며 음성으로 예측한 사례 수 | [01](chapters/01_problem_data.md) |
| 정확도 | Accuracy | 전체 사례 중 맞게 분류한 비율 | [01](chapters/01_problem_data.md) |
| 정밀도 | Precision | 양성으로 예측한 사례 중 실제 양성의 비율 | [01](chapters/01_problem_data.md) |
| 재현율 | Recall | 실제 양성 사례 중 찾아낸 비율 | [01](chapters/01_problem_data.md) |
| 학습 자료 | Training set | 모델 매개변수를 맞추는 데 사용하는 자료 | [01](chapters/01_problem_data.md) |
| 검증 자료 | Validation set | 모델·설정·임계값을 선택하는 자료 | [01](chapters/01_problem_data.md) |
| 시험 자료 | Test set | 선택 과정에서 보류하고 마지막 점검에 사용하는 자료 | [01](chapters/01_problem_data.md) |
| 데이터 누수 | Data leakage | 배포 때 알 수 없는 정보가 학습·평가에 섞이는 문제 | [01](chapters/01_problem_data.md) |
| 일반화 | Generalization | 학습에 쓰지 않은 관련 사례에서도 예측이 유지되는 정도 | [01](chapters/01_problem_data.md), [06](chapters/06_statistical_learning.md), [18](chapters/18_evaluation.md) |

## 수학과 최적화

| 한국어 | English | 짧은 정의 | 관련 장 |
|---|---|---|---|
| 스칼라 | Scalar | 하나의 수 | [02](chapters/02_math.md) |
| 벡터 | Vector | 순서가 있는 수의 목록 | [02](chapters/02_math.md) |
| 행렬 | Matrix | 행과 열로 배열된 수 | [02](chapters/02_math.md) |
| 텐서 | Tensor | 여러 축을 가진 수치 배열 | [02](chapters/02_math.md), [04](chapters/04_computing.md) |
| 차원·모양 | Dimension / shape | 배열의 축 수와 각 축의 길이 | [02](chapters/02_math.md), [04](chapters/04_computing.md) |
| 자료형 | Data type (dtype) | 원소를 저장할 숫자 표현 형식과 정밀도 | [04](chapters/04_computing.md) |
| 전치 | Transpose | 행과 열 또는 벡터의 행·열 방향을 바꾸는 연산 | [02](chapters/02_math.md) |
| 내적 | Inner product / dot product | 대응 성분을 곱해 더한 값 | [02](chapters/02_math.md) |
| 노름 | Norm | 벡터의 크기를 수치화하는 함수 | [02](chapters/02_math.md) |
| 정사영 | Orthogonal projection | 잔차가 선택한 방향과 수직이 되도록 그 방향 위에서 찾은 성분 | [02](chapters/02_math.md) |
| 고유값 | Eigenvalue | 행렬 변환 결과가 대응하는 고유벡터의 몇 배인지 나타내는 수 | [02](chapters/02_math.md) |
| 고유벡터 | Eigenvector | 행렬 변환 결과가 자신의 상수배가 되는 0이 아닌 벡터 | [02](chapters/02_math.md) |
| 특이값 분해 | Singular value decomposition (SVD) | 행렬을 직교 방향과 비음수 크기들로 분해하는 방법 | [02](chapters/02_math.md) |
| 주성분분석 | Principal component analysis (PCA) | 중심화 자료의 큰 분산 방향을 직교축으로 요약하는 방법 | [02](chapters/02_math.md) |
| 미분 | Derivative | 입력의 작은 변화에 따른 함수값 변화율 | [02](chapters/02_math.md) |
| 편미분 | Partial derivative | 여러 입력 중 하나만 바꿀 때의 변화율 | [02](chapters/02_math.md) |
| 기울기 | Gradient | 각 매개변수에 대한 편미분을 모은 벡터 | [02](chapters/02_math.md) |
| 연쇄법칙 | Chain rule | 연결된 함수의 미분을 각 단계의 미분 곱으로 계산하는 규칙 | [02](chapters/02_math.md), [04](chapters/04_computing.md) |
| 역전파 | Backpropagation | 연쇄법칙으로 신경망의 기울기를 효율적으로 계산하는 절차 | [02](chapters/02_math.md), [08](chapters/08_neural_networks.md) |
| 최적화 | Optimization | 목적함수를 최소화·최대화하는 변수 값을 찾는 문제 | [02](chapters/02_math.md) |
| 제약 최적화 | Constrained optimization | 가능한 변수 범위나 관계를 지키며 목적함수를 최적화하는 문제 | [02](chapters/02_math.md) |
| 경사하강법 | Gradient descent | 손실 기울기의 반대 방향으로 매개변수를 갱신하는 방법 | [02](chapters/02_math.md) |
| 학습률 | Learning rate | 한 번의 최적화 업데이트 크기를 정하는 값 | [02](chapters/02_math.md) |
| 미니배치 | Mini-batch | 한 업데이트의 기울기를 추정하는 사례의 작은 묶음 | [02](chapters/02_math.md) |
| 조건수 | Condition number | 입력 오차가 계산 해에 증폭되는 민감도를 요약하는 값 | [02](chapters/02_math.md) |
| 부동소수점 | Floating-point number | 유한 비트로 근사해 저장하는 실수 표현 | [02](chapters/02_math.md), [04](chapters/04_computing.md) |
| 오버플로 | Overflow | 계산 결과가 표현 가능한 수 범위를 넘는 현상 | [02](chapters/02_math.md) |
| 언더플로 | Underflow | 작은 계산값이 표현 한계 아래로 내려가 0 등에 반올림되는 현상 | [02](chapters/02_math.md) |
| 상쇄 오차 | Cancellation error | 비슷한 크기의 두 수를 빼며 유효 숫자를 잃는 현상 | [02](chapters/02_math.md) |

## 확률과 정보

| 한국어 | English | 짧은 정의 | 관련 장 |
|---|---|---|---|
| 사건 | Event | 확률을 부여하는 결과 또는 결과들의 집합 | [03](chapters/03_probability.md) |
| 확률변수 | Random variable | 가능한 결과를 수로 대응시키는 변수 | [03](chapters/03_probability.md) |
| 확률질량 | Probability mass | 이산 확률변수가 특정 값을 가질 확률 | [03](chapters/03_probability.md) |
| 확률밀도 | Probability density | 연속변수의 구간 확률을 적분으로 구하는 함수; 함수값 자체는 확률이 아님 | [03](chapters/03_probability.md) |
| 기대값 | Expectation | 각 결과를 그 확률로 가중 평균한 값 | [03](chapters/03_probability.md) |
| 분산 | Variance | 값이 평균에서 퍼진 정도의 제곱 평균 | [03](chapters/03_probability.md) |
| 조건부 확률 | Conditional probability | 어떤 사건이 주어졌다고 알 때 다른 사건의 확률 | [03](chapters/03_probability.md) |
| 독립 | Independence | 한 사건을 알아도 다른 사건의 확률이 변하지 않는 관계 | [03](chapters/03_probability.md) |
| 베이즈 규칙 | Bayes' rule | 사전확률과 가능도를 결합해 사후확률을 계산하는 규칙 | [03](chapters/03_probability.md) |
| 사전확률 | Prior probability | 증거를 보기 전 상태에 부여한 확률 | [03](chapters/03_probability.md) |
| 가능도 | Likelihood | 관측 자료를 고정하고 모수의 함수로 본 확률 또는 확률밀도 | [03](chapters/03_probability.md) |
| 사후확률 | Posterior probability | 자료를 관측한 뒤 상태에 부여한 확률 | [03](chapters/03_probability.md) |
| 모수 | Parameter | 모집단 분포나 모델을 규정하는 값; 베이지안 분석은 미지의 값에 관한 불확실성을 분포로 표현함 | [03](chapters/03_probability.md) |
| 추정량 | Estimator | 표본으로 모수를 추정하도록 정한 계산 규칙 | [03](chapters/03_probability.md) |
| 추정값 | Estimate | 실제 표본에 추정량을 적용해 얻은 수치 | [03](chapters/03_probability.md) |
| 표준오차 | Standard error | 추정량의 표집분포 표준편차; 실제로는 표본에서 이를 추정하기도 함 | [03](chapters/03_probability.md) |
| 신뢰구간 | Confidence interval | 정해진 반복 표집 성질을 갖도록 구성한 모수 추정 범위 | [03](chapters/03_probability.md) |
| 귀무가설 | Null hypothesis | 검정에서 자료와 비교하는 기준 가설 | [03](chapters/03_probability.md) |
| 대립가설 | Alternative hypothesis | 귀무가설과 구별되는 방향이나 차이를 표현한 가설 | [03](chapters/03_probability.md) |
| p값 | p-value | 귀무가설과 검정 가정 아래 미리 정한 검정통계량이 관측값 이상으로 극단적일 확률 | [03](chapters/03_probability.md) |
| 유의수준 | Significance level | 검정 전에 정하는 귀무가설 기각 규칙의 기준값 | [03](chapters/03_probability.md) |
| 엔트로피 | Entropy | 확률분포의 평균 정보량 또는 불확실성 요약 | [03](chapters/03_probability.md) |
| 교차 엔트로피 | Cross-entropy | 실제 분포의 결과를 다른 분포가 얼마나 큰 로그손실로 예측하는지 나타낸 값 | [03](chapters/03_probability.md) |
| KL 발산 | Kullback–Leibler divergence | 한 분포를 다른 분포로 근사할 때의 방향성 있는 정보 차이 | [03](chapters/03_probability.md) |
| 상호정보량 | Mutual information | 한 변수를 알 때 다른 변수의 불확실성이 줄어드는 양 | [03](chapters/03_probability.md) |

## 계산과 재현

| 한국어 | English | 짧은 정의 | 관련 장 |
|---|---|---|---|
| 배열 | Array | 수치 자료를 축과 인덱스로 저장하는 자료구조 | [04](chapters/04_computing.md) |
| 시간복잡도 | Time complexity | 입력 크기에 따라 필요한 연산량이 증가하는 경향 | [04](chapters/04_computing.md) |
| 메모리 사용량 | Memory footprint | 프로그램 실행 중 데이터와 중간값이 차지하는 저장공간 | [04](chapters/04_computing.md) |
| 계산 그래프 | Computational graph | 연산과 값의 의존 관계를 방향 그래프로 표현한 것 | [04](chapters/04_computing.md) |
| 자동미분 | Automatic differentiation | 프로그램의 기본 연산을 따라 연쇄법칙으로 미분을 계산하는 방법 | [04](chapters/04_computing.md) |
| 난수 시드 | Random seed | 의사난수 생성기의 초기 상태를 정하는 값 | [04](chapters/04_computing.md) |
| 재현성 | Reproducibility | 기록된 데이터·코드·환경으로 계산을 다시 확인할 수 있는 성질 | [04](chapters/04_computing.md) |
| 강건성 | Robustness | 조건이 변해도 성능이나 동작이 유지되는 정도 | [04](chapters/04_computing.md), [18](chapters/18_evaluation.md) |

## 기호·탐색과 통계학습

| 한국어 | English | 정확한 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 논리적 함의 | Logical entailment | 지식베이스를 만족시키는 모든 해석에서 결론도 참인 의미론적 관계. 인과 관계를 자동으로 뜻하지 않는다. | [05](chapters/05_symbolic.md) |
| 건전성 | Soundness | 증명 절차가 도출하는 모든 문장이 주어진 의미론에서 타당하다는 성질. | [05](chapters/05_symbolic.md) |
| 제약충족 문제 | Constraint satisfaction problem (CSP) | 변수별 값 집합과 허용 조합의 제약을 정하고 모든 제약을 만족하는 배정을 찾는 문제. | [05](chapters/05_symbolic.md), [16](chapters/16_alternative_scientific.md) |
| 탐색 완전성 | Search completeness | 지정한 공간·알고리즘 조건에서 해가 존재하면 탐색이 해를 찾는 성질. 논리 증명 절차의 완전성과 구분한다. | [05](chapters/05_symbolic.md) |
| 허용적 휴리스틱 | Admissible heuristic | 각 상태에서 실제 최소 잔여 비용을 과대평가하지 않는 비용 추정 함수. | [05](chapters/05_symbolic.md) |
| 일관적 휴리스틱 | Consistent heuristic | 모든 전이에서 현재 추정값이 전이 비용과 다음 추정값의 합 이하인 휴리스틱. | [05](chapters/05_symbolic.md) |
| A* 탐색 | A* search | 시작부터의 누적 비용과 잔여 비용 추정의 합이 작은 후보부터 확장하는 탐색. 최적성에는 휴리스틱·비용·상태 처리 조건이 필요하다. | [05](chapters/05_symbolic.md) |
| 경험위험 | Empirical risk | 주어진 표본에서 손실을 평균한 값. 사용할 전체 분포의 위험과 구분한다. | [06](chapters/06_statistical_learning.md) |
| 정규화 | Regularization | 벌점·학습 제한 등으로 자료 적합 이외의 선호를 넣어 일반화를 돕는 설계. 값의 normalization과 구분한다. | [06](chapters/06_statistical_learning.md), [08](chapters/08_neural_networks.md) |
| 커널 | Kernel | 특징 공간의 내적을 입력 쌍의 함수로 계산하는 방식. 임의의 유사도 함수가 항상 유효한 커널은 아니다. | [06](chapters/06_statistical_learning.md) |
| PAC 학습 | Probably approximately correct learning | 정한 표본·가설·분포 가정 아래 충분한 표본으로 높은 확률에 작은 일반화 오차를 얻는 학습 가능성을 다루는 틀. | [06](chapters/06_statistical_learning.md) |
| VC 차원 | Vapnik–Chervonenkis dimension | 이진 함수군이 어떤 점 집합의 모든 이진 레이블 배정을 실현할 수 있는 최대 점 수. 매개변수 수와 동일하지 않다. | [06](chapters/06_statistical_learning.md) |

## 확률적 추론과 신경 표현

| 한국어 | English | 정확한 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 잠재변수 | Latent variable | 직접 관측하지 않지만 관측 분포나 구조를 설명하기 위해 모형에 둔 변수. 실제 물리 원인과 자동으로 동일시하지 않는다. | [07](chapters/07_probabilistic_models.md) |
| 베이즈망 | Bayesian network | 방향 비순환 그래프의 부모 관계에 따른 조건부 분포들의 곱으로 결합분포를 표현하는 확률모형. | [07](chapters/07_probabilistic_models.md), [15](chapters/15_causality.md) |
| 주변화 | Marginalization | 관심 밖 변수를 합하거나 적분해 제거하면서 나머지 변수의 분포를 얻는 계산. | [07](chapters/07_probabilistic_models.md) |
| 최대사후 추정 | Maximum a posteriori estimation (MAP) | 사후 확률 또는 밀도가 가장 큰 변수·모수 값을 선택하는 기준. 사후 평균과 구분한다. | [07](chapters/07_probabilistic_models.md) |
| 마르코프 연쇄 몬테카를로 | Markov chain Monte Carlo (MCMC) | 목표분포가 정상분포인 마르코프 연쇄를 구성해 표본을 얻는 근사추론 방법군. 유한 표본의 혼합·자기상관을 확인해야 한다. | [07](chapters/07_probabilistic_models.md) |
| 변분추론 | Variational inference | 계산 가능한 분포족에서 최적화하여 목표 사후분포를 근사하는 방법. 근사족과 최적화의 제한이 남는다. | [07](chapters/07_probabilistic_models.md) |
| 증거 하한 | Evidence lower bound (ELBO) | 선택한 근사분포에서 계산하는 로그 주변우도의 하한이며, 정확한 사후와의 KL 차이로 연결되는 목적함수. | [07](chapters/07_probabilistic_models.md) |
| 임베딩 | Embedding | 이산 항목 등을 벡터로 대응시키는 표현. 벡터 사이의 관계는 표현·학습 목적과 데이터 조건에 의존한다. | [08](chapters/08_neural_networks.md), [17](chapters/17_systems.md) |
| 어텐션 | Attention | 질의와 키의 적합도에서 만든 가중치로 값 표현을 결합하는 연산. 가중치만으로 인과 설명이 되지는 않는다. | [08](chapters/08_neural_networks.md), [18](chapters/18_evaluation.md) |
| 트랜스포머 | Transformer | 어텐션·위치별 변환·잔차·정규화 등으로 시퀀스 표현을 구성하는 구조 계열. 이름만으로 세부 학습 조건을 확정하지 않는다. | [08](chapters/08_neural_networks.md) |
| 상태공간 모형 | State-space model (SSM) | 내부 상태의 전이와 관측·출력 관계로 시간적 의존성을 표현하는 모형. 선형 형태와 입력 선택형 신경 설계를 구분한다. | [08](chapters/08_neural_networks.md) |
| 전문가 혼합 | Mixture of experts (MoE) | 입력에 따라 라우터가 여러 전문가 함수를 선택·가중 결합하는 구조. 전체 매개변수와 활성 매개변수가 다를 수 있다. | [08](chapters/08_neural_networks.md), [17](chapters/17_systems.md) |

## 학습 신호와 지식 재사용

| 한국어 | English | 정확한 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 의사라벨 | Pseudo-label | 모델의 예측을 학습에 사용할 임시 목표로 정한 값. 정답으로 확인된 라벨은 아니다. | [09](chapters/09_learning_paradigms.md) |
| 전이학습 | Transfer learning | 이전 과제·분포에서 얻은 표현이나 매개변수를 다른 과제·분포에 활용하는 설정. 가중치를 반드시 갱신해야 하는 것은 아니다. | [09](chapters/09_learning_paradigms.md) |
| 미세조정 | Fine-tuning | 사전학습한 모형의 일부 또는 전체 매개변수를 후속 자료·목적에 맞춰 갱신하는 학습. | [09](chapters/09_learning_paradigms.md), [17](chapters/17_systems.md) |
| 문맥 내 학습 | In-context learning (ICL) | 예시·지시를 입력 문맥에 넣어 반응을 바꾸는 사용 방식. 일반적인 실행 시점의 가중치 갱신과 구분한다. | [09](chapters/09_learning_paradigms.md), [17](chapters/17_systems.md) |
| 메타학습 | Meta-learning | 여러 과제의 경험으로 새로운 과제에 적응하는 초기화·규칙·표현 등을 학습하는 설정. | [09](chapters/09_learning_paradigms.md) |
| 지속학습 | Continual learning | 순차적으로 들어오는 과제를 학습하며 이전 지식과 성능을 유지하려는 설정. | [09](chapters/09_learning_paradigms.md) |
| 능동학습 | Active learning | 제한된 라벨 획득 예산에서 어떤 표본에 라벨을 요청할지 선택하는 학습 설정. | [09](chapters/09_learning_paradigms.md) |
| 연합학습 | Federated learning | 보통 원자료를 여러 참여자에 남겨 두고 갱신을 모아 학습하는 데이터 접근·협력 설정. 그 자체로 개인정보 보장은 아니다. | [09](chapters/09_learning_paradigms.md), [17](chapters/17_systems.md) |

## 인과와 통합·과학 접근

| 한국어 | English | 정확한 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 구조적 인과모형 | Structural causal model (SCM) | 변수별 생성 함수와 외생 요인으로 원인 관계와 개입 후 생성 과정을 표현하는 모형. | [15](chapters/15_causality.md) |
| 개입 | Intervention | 변수의 기존 생성 메커니즘을 지정한 행동·값으로 바꾸는 조작. 관찰값을 조건으로 고르는 것과 다르다. | [15](chapters/15_causality.md) |
| 반사실 | Counterfactual | 관찰된 대상이 실제와 다른 행동·조건을 겪었을 때의 결과에 관한 질문. 구조 또는 잠재결과의 가정을 요구한다. | [15](chapters/15_causality.md), [18](chapters/18_evaluation.md) |
| 교란 | Confounding | 행동과 결과의 공통 원인 때문에 관찰적 비교가 관심 개입 효과와 달라지는 문제. | [15](chapters/15_causality.md) |
| 선택편향 | Selection bias | 분석에 포함되는 과정 때문에 분석 집단의 관계나 효과가 목표 모집단과 달라지는 문제. | [15](chapters/15_causality.md), [18](chapters/18_evaluation.md) |
| 인과 식별 | Causal identification | 명시한 인과 가정에서 목표 효과를 관측 가능한 분포의 함수로 유일하게 표현할 수 있는지의 문제. | [15](chapters/15_causality.md) |
| 신경기호 | Neuro-symbolic AI | 신경 표현·지각과 명시적인 기호·논리·제약 추론을 연결하는 접근군. 결합 방식과 보장 범위는 별도 명시한다. | [16](chapters/16_alternative_scientific.md) |
| 프로그램 합성 | Program synthesis | 예제나 논리 명세를 만족하는 프로그램을 정한 후보 언어에서 찾는 문제. | [05](chapters/05_symbolic.md), [16](chapters/16_alternative_scientific.md) |
| 진화 알고리즘 | Evolutionary algorithm | 후보 집단의 평가와 선택·변이·교차 등으로 해를 탐색하는 방법군. 미분 불가 평가도 쓸 수 있으나 일반적인 전역 최적 보장은 없다. | [16](chapters/16_alternative_scientific.md) |
| 퍼지 소속도 | Fuzzy membership degree | 대상이 점진적 경계를 가진 집합·언어 범주에 부합하는 정도. 사건의 발생 확률과 구분한다. | [16](chapters/16_alternative_scientific.md) |
| 스파이킹 신경망 | Spiking neural network (SNN) | 발화 시각의 사건과 시간적 상태 변화로 신호를 전달·처리하는 신경망. | [16](chapters/16_alternative_scientific.md) |
| 물리정보 신경망 | Physics-informed neural network (PINN) | 함수 근사에 관측·초기·경계 조건과 물리 방정식의 잔차를 학습 제약으로 적용하는 접근. | [16](chapters/16_alternative_scientific.md) |
| 신경연산자 | Neural operator | 입력 함수에서 출력 함수로 가는 사상을 학습하는 모형군. 한 조건의 해만 근사하는 것과 목적이 다르다. | [16](chapters/16_alternative_scientific.md) |
| 등변성 | Equivariance | 입력을 변환했을 때의 출력이 원래 출력을 대응 방식으로 변환한 결과와 같다는 성질. 출력이 유지되는 불변성과 구분한다. | [16](chapters/16_alternative_scientific.md) |

## 시스템·평가와 책임

| 한국어 | English | 정확한 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 데이터 병렬 | Data parallelism | 모델 사본에 서로 다른 표본을 나누어 처리하고 기울기·갱신을 결합하는 계산 방식. | [17](chapters/17_systems.md) |
| 파이프라인 병렬 | Pipeline parallelism | 모델의 단계들을 계산 자원에 나누고 여러 작은 배치를 단계 사이로 흐르게 하는 방식. | [17](chapters/17_systems.md) |
| 양자화 | Quantization | 실수값을 유한한 코드와 복원 규칙으로 대응시키는 수치 표현·압축 방식. 범위 밖 포화와 구간 안 반올림을 구분한다. | [17](chapters/17_systems.md) |
| 지식 증류 | Knowledge distillation | 교사의 출력·표현을 학습 신호로 사용해 학생 모형을 학습하는 방식. 교사의 오류도 전달될 수 있다. | [17](chapters/17_systems.md) |
| 검색 증강 생성 | Retrieval-augmented generation (RAG) | 외부 자료를 검색해 생성 모형에 제공하는 시스템 구성. 검색·생성기의 매개변수 학습 여부는 구성마다 다르다. | [09](chapters/09_learning_paradigms.md), [17](chapters/17_systems.md) |
| 에이전트 | Agent | 목표를 향해 관찰·행동 선택·실행·상태 갱신을 반복하는 구성. 언어모델 사용 여부와 강화학습 여부는 별도다. | [17](chapters/17_systems.md) |
| 메모리 | Memory | 현재 문맥·검색 기록·구조화된 상태 등 이후 처리를 위해 정보를 유지하는 구성. 기록의 사실성·최신성은 별도 확인한다. | [17](chapters/17_systems.md) |
| 멱등성 | Idempotency | 같은 작업을 반복 요청해도 최종 효과가 한 번 수행한 것과 같게 유지되는 성질. | [17](chapters/17_systems.md) |
| 확률 보정 | Probability calibration | 같은 예측 확률을 낸 사례들의 실제 발생 비율이 해당 확률과 맞는 성질. 정확도나 개별 정답 보장과 다르다. | [18](chapters/18_evaluation.md) |
| Brier 점수 | Brier score | 이 장의 이진 설정에서 예측 양성 확률과 0/1 정답의 제곱 차이를 평균한 확률 평가 손실. | [18](chapters/18_evaluation.md) |
| 구간별 보정오차 | Binned calibration error (ECE) | 확률 구간별 평균 예측과 경험적 빈도의 차이를 표본 비중으로 평균한 보정 요약값. 보정 대상과 구간 정의를 명시해야 한다. | [18](chapters/18_evaluation.md) |
| 공변량 변화 | Covariate shift | 입력 분포가 달라지지만 입력을 조건으로 한 결과 분포는 유지되는 분포 변화 설정. | [09](chapters/09_learning_paradigms.md), [18](chapters/18_evaluation.md) |
| 적대적 예제 | Adversarial example | 정한 변형·접근 범위 안에서 모델 실패를 유도하도록 의도적으로 구성한 입력. | [18](chapters/18_evaluation.md) |
| 차등 개인정보보호 | Differential privacy (DP) | 지정한 보호 단위의 포함·변경이 무작위 출력 분포에 미치는 차이를 수학적으로 제한하는 보장. 접근 통제를 대신하지 않는다. | [18](chapters/18_evaluation.md) |
| 인구통계적 동등성 | Demographic parity | 집단별 양성 결정 비율이 같도록 하는 공정성 기준. 다른 공정성 기준과 일반적으로 동일하지 않다. | [18](chapters/18_evaluation.md) |
| 기회 균등 | Equality of opportunity | 실제 양성인 사례에서 양성 결정 확률, 즉 재현율을 집단별로 같게 하는 기준. | [18](chapters/18_evaluation.md) |
| 균등 오즈 | Equalized odds | 실제 양성과 음성을 각각 조건으로 했을 때 양성 결정 확률을 집단별로 같게 하는 기준. | [18](chapters/18_evaluation.md) |
| 인간 감독 | Human oversight | 사람이 정보·시간·권한을 갖고 시스템의 판단·행동을 검토·수정·중지·이의 처리할 수 있도록 역할을 설계하는 것. | [17](chapters/17_systems.md), [18](chapters/18_evaluation.md) |


## 생성 모델과 샘플링

여기서 자기회귀 생성의 AR은 조건부 분포의 순차 분해를 뜻한다. 아래 시계열의 AR 모형은 과거 관측으로 현재 값을 예측하는 특정 모형군이므로 문맥을 구분한다.

| 한국어 | English | 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 자기회귀 생성 | Autoregressive generation (AR) | 앞서 나온 값들을 조건으로 다음 값의 분포를 예측하고 순차적으로 표본을 만드는 방식. 선형 시계열 AR에 한정되지 않는다. | [10](chapters/10_generative.md), [12](chapters/12_language_models.md) |
| 변분 오토인코더 | Variational autoencoder (VAE) | 잠재변수 생성모형과 근사 사후분포를 함께 학습하며 ELBO를 최적화하는 접근. 복원 오차만 줄이는 오토인코더와 구분한다. | [07](chapters/07_probabilistic_models.md), [10](chapters/10_generative.md) |
| 생성적 적대 신경망 | Generative adversarial network (GAN) | 실제·생성 자료를 구별하는 판별기와 그 판별을 이용해 학습하는 생성기를 결합한 적대적 학습 방식. | [10](chapters/10_generative.md) |
| 정규화 흐름 | Normalizing flow | 가역 미분 변환으로 단순 분포를 바꾸고 변수변환 공식으로 밀도를 계산하는 생성모형군. | [10](chapters/10_generative.md) |
| 에너지 기반 모형 | Energy-based model (EBM) | 낮은 에너지에 큰 확률 무게를 주고 정규화 상수로 분포를 정의하는 모형. 정규화와 표본 생성의 계산을 별도 다룬다. | [10](chapters/10_generative.md) |
| 확률분포 점수 | Distribution score | 연속 입력에 대한 로그 확률밀도의 기울기. 분류 점수나 평가자의 점수와 다른 정의다. | [10](chapters/10_generative.md) |
| 확산 모형 | Diffusion model | 자료에 잡음을 넣는 과정을 정하고 학습한 역방향 과정 등으로 잡음에서 자료를 생성하는 모형군. | [10](chapters/10_generative.md), [13](chapters/13_multimodal.md) |

## 강화학습과 제어

| 한국어 | English | 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 마르코프 결정과정 | Markov decision process (MDP) | 상태·행동·전이확률·보상·할인 등으로 순차 의사결정을 정의하는 모형. 다음 결과에 필요한 과거 정보가 현재 상태에 담긴다는 가정을 둔다. | [11](chapters/11_reinforcement_control.md) |
| 부분관측 마르코프 결정과정 | Partially observable MDP (POMDP) | 실제 상태 대신 불완전한 관측을 받는 순차 결정모형. 행동·관측 이력에서 상태에 대한 믿음을 갱신한다. | [11](chapters/11_reinforcement_control.md) |
| 정책 | Policy | 주어진 상태나 이용 가능한 정보에서 행동을 선택하는 규칙 또는 확률분포. 보상·가치와 구분한다. | [11](chapters/11_reinforcement_control.md), [15](chapters/15_causality.md) |
| 리턴 | Return | 정한 시점 이후 보상을 합한 누적량. 이 장에서는 미래 보상을 할인한 합을 사용한다. | [11](chapters/11_reinforcement_control.md) |
| 상태 가치 | State value | 한 상태에서 지정 정책을 따를 때의 기대 리턴. 그 상태의 즉시 보상과 다르다. | [11](chapters/11_reinforcement_control.md) |
| 행동 가치 | Action value (Q-value) | 한 상태에서 첫 행동을 지정하고 이후 정책을 따를 때의 기대 리턴. | [11](chapters/11_reinforcement_control.md) |
| 벨만 관계 | Bellman relation | 상태·행동 가치를 한 단계의 보상과 다음 가치의 기댓값으로 연결하는 재귀 관계. | [11](chapters/11_reinforcement_control.md) |
| 시간차 학습 | Temporal-difference learning (TD) | 한 단계 등 짧은 관측 보상과 현재의 다음 가치 추정을 이용해 가치 추정치를 갱신하는 방식. | [11](chapters/11_reinforcement_control.md) |
| Q 학습 | Q-learning | 관측 보상과 다음 상태의 최대 행동 가치를 목표로 행동 가치를 갱신하는 오프폴리시 시간차 학습 방법. | [11](chapters/11_reinforcement_control.md) |
| 모방학습 | Imitation learning | 전문가의 행동 자료·피드백 등을 이용해 행동 정책을 학습하는 접근군. 행동 복제는 상태–행동 쌍의 지도학습 형태다. | [11](chapters/11_reinforcement_control.md) |
| 오프라인 강화학습 | Offline reinforcement learning | 새 환경 상호작용 대신 고정된 과거 로그에서 리턴을 개선할 정책을 학습하는 설정. 자료 밖 행동의 가치에는 지원·외삽 문제가 있다. | [11](chapters/11_reinforcement_control.md), [15](chapters/15_causality.md) |
| 모델 예측 제어 | Model predictive control (MPC) | 현재 추정 상태에서 유한 미래 입력열을 최적화하고 첫 입력만 적용한 뒤 다시 최적화하는 제어 방식. | [11](chapters/11_reinforcement_control.md) |

## 언어모델의 단위와 적응

| 한국어 | English | 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 토큰 | Token | 모델이 처리하는 이산 입력·출력 단위. 단어·문자·부분 문자열·바이트 등 토큰화 규칙에 따라 달라진다. | [12](chapters/12_language_models.md), [17](chapters/17_systems.md) |
| 바이트 쌍 인코딩 | Byte-pair encoding (BPE) | 빈번한 인접 단위를 반복 병합해 어휘·분절 규칙을 만드는 방식. NLP 구현의 시작 단위와 전처리 조건을 확인한다. | [12](chapters/12_language_models.md) |
| 지도 미세조정 | Supervised fine-tuning (SFT) | 지시·응답 등 입력·목표 쌍의 지도 손실로 사전학습한 모델을 후속 행동에 맞춰 갱신하는 학습. | [12](chapters/12_language_models.md) |
| 매개변수 효율적 미세조정 | Parameter-efficient fine-tuning (PEFT) | 전체 가중치 모두 대신 작은 매개변수 집합·추가 모듈 등으로 모델을 적응시키는 방법군. | [12](chapters/12_language_models.md) |
| 저랭크 적응 | Low-rank adaptation (LoRA) | 원래 가중치를 고정하고 작은 두 행렬의 곱인 저랭크 갱신을 학습해 더하는 적응 방식. | [12](chapters/12_language_models.md) |
| 인간 피드백 기반 강화학습 | Reinforcement learning from human feedback (RLHF) | 사람의 시연·선호 등에서 얻은 신호를 보상 등에 연결해 강화학습으로 정책을 조정하는 접근. 구체적인 파이프라인은 사례마다 확인한다. | [11](chapters/11_reinforcement_control.md), [12](chapters/12_language_models.md) |
| 직접 선호 최적화 | Direct preference optimization (DPO) | 선호 응답쌍과 참조 정책의 확률비를 사용해 정책을 직접 최적화하는 방법. 선호 자료의 편향이나 정확성을 자동 해결하지 않는다. | [12](chapters/12_language_models.md) |
| 추론 시 계산 | Inference-time computation | 학습된 모델을 사용할 때 후보 생성·검증·탐색·재시도 등에 쓰는 계산. 학습 계산·가중치 갱신과 구분한다. | [12](chapters/12_language_models.md), [17](chapters/17_systems.md) |

## 신호와 멀티모달

| 한국어 | English | 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 앨리어싱 | Aliasing | 서로 다른 연속 신호가 주어진 샘플링 조건에서 동일한 이산 관측을 만들어 구별되지 않는 현상. | [13](chapters/13_multimodal.md) |
| 단시간 푸리에 변환 | Short-time Fourier transform (STFT) | 시간창을 이동하며 구간별 푸리에 변환으로 시간에 따른 주파수 성분을 표현하는 연산. 창 길이와 주파수·시간 해상도를 함께 확인한다. | [13](chapters/13_multimodal.md) |
| 연결주의 시간 분류 | Connectionist temporal classification (CTC) | blank·반복 제거 규칙에 따라 같은 출력열로 대응되는 여러 프레임 정렬의 확률을 합해 학습하는 시퀀스 목적. | [13](chapters/13_multimodal.md) |
| 교집합 대 합집합 비율 | Intersection over union (IoU) | 두 영역의 교집합 크기를 합집합 크기로 나눈 겹침 지표. 합집합이 양수이고 좌표·영역 정의가 명시된 경우에 계산한다. | [13](chapters/13_multimodal.md) |
| 모달리티 정렬 | Multimodal alignment | 서로 다른 관측 형식의 관련 내용을 의미·시간 등의 대응 관계로 연결하는 문제. | [13](chapters/13_multimodal.md) |
| 모달리티 융합 | Multimodal fusion | 여러 관측 형식의 입력·표현·예측을 함께 이용해 출력하는 구성. 대응을 찾는 정렬과 역할이 다르다. | [13](chapters/13_multimodal.md) |

## 시계열과 추천·그래프

| 한국어 | English | 짧은 정의 | 관련 장 |
| --- | --- | --- | --- |
| 칼만 필터 | Kalman filter | 선형·Gaussian 상태공간 모형에서 동역학 예측과 관측 갱신으로 상태의 조건부 평균·공분산을 순차 계산하는 필터. | [14](chapters/14_structured_domains.md) |
| 자기회귀 모형(시계열) | Autoregressive model (time-series AR) | 과거 관측값으로 현재 값을 예측하는 시계열 모형군. 기본 선형 AR은 과거 값의 선형 결합과 잡음으로 정의한다. | [14](chapters/14_structured_domains.md) |
| 협업 필터링 | Collaborative filtering | 사용자–항목 상호작용 자료의 패턴으로 사용자별 항목 점수·순위를 추정하는 추천 접근. 미관측과 비선호는 구분한다. | [14](chapters/14_structured_domains.md) |
| 노출편향 | Exposure bias in recommendation | 기존 시스템이 어떤 항목을 보여 주었는지에 따라 관측된 클릭·반응 자료가 선택되는 문제. 생성 시 문맥 변화와 구분한다. | [14](chapters/14_structured_domains.md), [15](chapters/15_causality.md) |
| 그래프 신경망 | Graph neural network (GNN) | 그래프의 노드·간선·전체 구조를 이용해 표현과 예측을 학습하는 신경망군. 이 장에서는 이웃 메시지 집계와 갱신을 중심으로 설명한다. | [14](chapters/14_structured_domains.md) |
| 그래프 합성곱 신경망 | Graph convolutional network (GCN) | 정규화한 인접 관계와 학습 변환으로 노드 표현을 전파하는 GNN 구조 계열. 본문의 대칭 정규화와 단순 이웃 평균은 구분한다. | [14](chapters/14_structured_domains.md) |
| 과도 평활화 | Oversmoothing | 반복적인 그래프 전파 등으로 노드 표현이 지나치게 비슷해져 필요한 구분이 약해지는 문제. | [14](chapters/14_structured_domains.md) |
| 과도 압축 | Oversquashing | 많은 먼 노드의 정보를 제한된 차원의 표현과 전달 경로에 모으며 생기는 정보 병목. | [14](chapters/14_structured_domains.md) |
