# 녹조 예측 교재 근거 자료

확인일은 2026년 10월 7일이다. 아래는 녹조 확장 19~25장에서 사용한 공식 설명·원논문·공식 라이브러리 문서다. 자체 유도와 가상 계산은 출처의 실제 실험 결과로 표현하지 않는다. 특정 모델이 이 데이터에서 우수하다는 근거로 논문의 다른 과제 성능을 옮기지 않는다.

## 과제와 환경 현상

- [KISTI 녹조 예측 과제](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004602/detail.do): 과제명·기관·데이터 첨부 안내를 확인했다. 상세 규칙은 10월 6일에 기록된 조건과 이번 조회의 확인 범위를 구분하며 최종 원문 재확인이 필요하다.
- [EPA What Causes HABs](https://www.epa.gov/habs/what-causes-habs): 영양분·온도·빛·물 이동 등 복합 요인의 연결.
- [EPA Climate Change and Freshwater HABs](https://www.epa.gov/habs/climate-change-and-freshwater-harmful-algal-blooms): 강우·영양분 유출과 환경 조건 변화.
- [EPA WASP](https://www.epa.gov/hydrowq/water-quality-analysis-simulation-program-wasp): 수질모형의 구역별 상태와 물질 이동 설명.
- [EPA Seasonal and Diel Oxygen and Phytoplankton Dynamics](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100YSKQ.TXT): 환경 제한을 결합한 수질모형 사례. 하구 식물플랑크톤 자료이며 해당 대회 지점의 계수를 제공하지 않는다.
- [USGS Cyanobacteria in Lakes and Reservoirs](https://pubs.usgs.gov/twri/twri9a7/twri9a7_7.5.pdf): 채수 위치·수심·순환과 관측의 해석 한계.

## 시간 연결과 특징 처리

- [pandas merge_asof](https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html): 과거·미래·최근접 연결의 API 구분.
- [pandas rolling](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.rolling.html): 행 개수와 기간 창의 차이.
- [scikit-learn 결측 처리](https://scikit-learn.org/stable/modules/impute.html): 대체와 결측 표시의 기능.
- [scikit-learn 누수 방지](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage): 학습 자료에서 전처리를 맞추는 원칙.
- [scikit-learn 주기 특징](https://scikit-learn.org/stable/auto_examples/applications/plot_cyclical_feature_engineering.html): 시간의 주기 표현 사례.

## 회귀와 트리 모델

- [scikit-learn Ridge](https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification): L2 정규화된 회귀.
- [mgcv GAM](https://stat.ethz.ch/R-manual/R-devel/library/mgcv/html/gam.models.html): 가법 평활항과 상호작용.
- [scikit-learn 회귀트리](https://scikit-learn.org/stable/modules/tree.html#mathematical-formulation): 분할과 잎 예측.
- [scikit-learn 앙상블](https://scikit-learn.org/stable/modules/ensemble.html): Random Forest와 Gradient Boosting.
- [Chen·Guestrin XGBoost](https://arxiv.org/abs/1603.02754): 정규화된 트리 목적함수와 분할 개선.
- [LightGBM 공식 특징](https://lightgbm.readthedocs.io/en/stable/Features.html): histogram과 잎 중심 성장.
- [Prokhorenkova 등 CatBoost](https://arxiv.org/abs/1706.09516): 범주 처리와 ordered boosting.
- [CatBoost has_time](https://catboost.ai/docs/en/references/training-parameters/common#has_time): 입력 순서 관련 옵션. 전체 누수 방지 보장과 구분한다.

## 시간과 물리 혼합 모델

- [statsmodels SARIMAX](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html): 외부 입력과 계절 오차 구조.
- [statsmodels 상태공간 추세](https://www.statsmodels.org/stable/examples/notebooks/generated/statespace_local_linear_trend.html): 관측식과 상태식.
- [statsmodels 상태공간 예측](https://www.statsmodels.org/stable/examples/notebooks/generated/statespace_forecasting.html): 예측의 정보 범위와 절차.
- [PyTorch LSTM 공식 소스](https://github.com/pytorch/pytorch/blob/main/torch/nn/modules/rnn.py): gate 식과 입력·출력 차원.
- [Bai 등 TCN](https://arxiv.org/abs/1803.01271): 인과 합성곱·dilation·잔차 구조.
- [Vaswani 등 Attention Is All You Need](https://arxiv.org/abs/1706.03762): scaled dot-product attention과 Transformer.
- [Raissi 등 PINN](https://arxiv.org/abs/1711.10561): 관측·초기조건·방정식 잔차의 결합.

## 검증과 불확실성

- [Hyndman·Athanasopoulos 시계열 검증](https://otexts.com/fpp3/tscv.html): 기준 시점 이동과 여러 예측 간격의 평가.
- [같은 저자의 변환 예측](https://otexts.com/fpp3/ftransformations.html): 역변환 평균과 중앙값의 차이.
- [같은 저자의 예측구간](https://otexts.com/fpp3/prediction-intervals.html): 미래값 구간과 가정.
- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): 행 단위 분할과 gap. 불규칙 시간에 대한 날짜 분할은 별도 확인한다.
- [scikit-learn R²](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.r2_score.html): 점수 정의와 상수 정답 처리.
- [Angelopoulos·Bates Conformal Prediction](https://arxiv.org/abs/2107.07511): 분리 보정과 교환가능성 가정.
- [Zaffran 등 Adaptive Conformal Predictions for Time Series](https://proceedings.mlr.press/v162/zaffran22a.html): 시간 의존성에서의 보정 연구. 단순 구간에 같은 보장을 자동 부여하지 않는다.

## 근거의 경계

성장 상수·최적 온도·환경수용력은 가상 값으로 계산했다. 실제 제공 파일의 모델 성능, 실제 수역 실험, 장치 동작 검증은 수행하지 않았다. API 문서는 원리를 확인하는 자료이며 사용자 실행 환경의 설치 버전은 실제 구현 단계에서 고정한다.

[녹조 학습 길잡이](algae_learning_path.md) · [기존 AI 근거 자료](92_sources.md)
