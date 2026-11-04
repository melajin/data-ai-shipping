# 학습 자료 출처 색인

확인일: 2026-10-06

이 목록은 이 교재의 설명·수식·공개 사례를 뒷받침하는 선별 자료다. 전 분야의 모든 연구를 망라한다고 주장하지 않는다. 논문은 해당 방법의 정의와 저자들이 보고한 실험 조건을 확인하는 근거로 쓴다. 논문 초록의 비교 수치를 일반적 우월성 주장으로 옮기지 않는다. 기업의 공식 문서는 공개된 사용 형태와 입력·출력 제약의 근거로만 인용하고, 기업의 성능 설명은 독립적으로 확인된 사실처럼 쓰지 않는다.

## 기초·범위·학습 방법

- [Artificial Intelligence: A Modern Approach, 4th US edition](https://aima.cs.berkeley.edu/) — 에이전트, 탐색, 제약·논리·계획, 확률 추론과 의사결정, 머신러닝·강화학습, 언어·비전·로봇·안전까지 AI 지도를 확인한다. 개괄서이므로 각 분야의 수학적 깊이와 최신 모델 구현은 별도 논문·자료가 필요하다.
- [Deep Learning](https://www.deeplearningbook.org/) — 선형대수·확률·수치계산, 학습·최적화, CNN/RNN, 표현·생성 모델의 공통 기초를 확인한다. 현대 Transformer 이후의 세부를 포괄하는 자료로 쓰지 않는다.
- [Probabilistic Machine Learning: Advanced Topics](https://probml.github.io/pml-book/book2.html) — 확률 모델, 근사추론, 생성 모델 등 고급 확률 ML의 연결을 확인한다. 모든 AI 분야나 특정 기업 모델의 사양을 설명하지 않는다.
- [Reinforcement Learning: An Introduction, 2nd edition — MIT Press](https://mitpress.mit.edu/9780262039246/reinforcement-learning/) — Sutton·Barto의 MDP, 동적계획, Monte Carlo, temporal-difference, 함수근사와 정책 방법을 설명할 때 근거로 쓴다. RL 전용 교재이며 다른 학습 패러다임을 대신하지 않는다.
- [Causal Inference: What If](https://miguelhernan.org/whatifbook) — Hernán·Robins의 저자 페이지에서 모형 없는 인과추론, 모형을 사용한 방법, 복잡한 종단자료의 구성을 확인한다. 인과 추론과 자료의 가정에 한정된다.
- [An Introduction to Statistical Learning](https://www.statlearning.com/) — 회귀·분류, 재표집, 정규화, 트리, SVM, 딥러닝, 비지도학습과 다중검정의 입문 근거다. 현대 LLM의 학습 시스템을 상세히 다루지는 않는다.
- [Stanford CS324: Large Language Models](https://stanford-cs324.github.io/winter2022/) — LLM의 모델링·이론·윤리·시스템 관점, 평가와 구축 활동의 범위를 확인한다. Winter 2022 과목 자료이므로 이후 변화의 근거로 확대 해석하지 않는다.
- [Stanford CS25: Transformers United V6](https://web.stanford.edu/class/cs25/) — Transformer 연구 세미나의 공개 강의 목록에서 구조 변형, 상태공간모델, 정렬, RAG, 에이전트 등 주제 범위를 확인한다. 선별된 세미나 강연이므로 체계적인 기초 교재는 아니다.
- [Stanford CS336: Language Modeling from Scratch, Spring 2025 archive](https://cs336.stanford.edu/spring2025/) — 토큰화·Transformer 구현, GPU와 분산 학습, 데이터 준비, 스케일링·평가·정렬까지 언어모델 제작 흐름과 선수지식을 확인한다. 구현 중심 과목이며 범위가 언어모델에 집중된다.

## 핵심 방법 논문

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762) — 재귀·합성곱 없이 attention으로 구성한 Transformer와 encoder–decoder, self-attention, 위치 정보 설명의 근거다. 번역 실험이 모든 Transformer 사용 사례를 대표하지 않는다.
- [Auto-Encoding Variational Bayes](https://arxiv.org/abs/1312.6114) — 잠재변수 생성모델에서 변분 하한과 재매개변수화 추정기를 설명할 때 근거로 쓴다. VAE의 모든 변형을 다루는 문헌은 아니다.
- [Generative Adversarial Networks](https://arxiv.org/abs/1406.2661) — 생성기와 판별기의 적대적 최소최대 학습 구도를 소개하는 원 논문이다. 후속 GAN의 안정화 기법은 별도 근거가 필요하다.
- [Denoising Diffusion Probabilistic Models](https://arxiv.org/abs/2006.11239) — 정방향 잡음화와 역방향 복원, 변분 목적과 denoising score matching의 관계를 설명한다. 모든 diffusion/score 기반 생성 절차가 동일하다는 뜻은 아니다.
- [Variational Inference with Normalizing Flows](https://arxiv.org/abs/1505.05770) — 단순한 밀도에서 가역 변환을 연속 적용해 유연한 근사 분포를 만드는 normalizing flow의 근거다. 가역성·계산 가능한 밀도 조건이 모델 선택을 제한한다.
- [Efficiently Modeling Long Sequences with Structured State Spaces (S4)](https://arxiv.org/abs/2111.00396) — 연속 상태공간 모델을 장기 의존 시퀀스 학습에 적용하고 구조화해 계산하는 S4 접근을 확인한다. 특정 구조·벤치마크의 결과를 전체 SSM의 일반 성능으로 취급하지 않는다.
- [Mamba: Linear-Time Sequence Modeling with Selective State Spaces](https://arxiv.org/abs/2312.00752) — 입력에 따라 선택적으로 상태를 갱신하는 SSM과 하드웨어 인식 구현의 설계 동기를 확인한다. 논문에 보고된 성능은 해당 실험 설정에 한정된다.
- [Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity](https://arxiv.org/abs/2101.03961) — 토큰별 expert 라우팅을 통한 희소 활성화, 라우팅·통신·학습 안정성 문제의 근거다. 이 특정 설계를 MoE 전체의 유일한 구현으로 보지 않는다.
- [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685) — 사전학습 가중치를 고정하고 저랭크 행렬을 학습하는 적응 방법과 적용 조건을 확인한다. 모든 모델·작업에서 full fine-tuning과 동등하다는 보장은 없다.
- [Training language models to follow instructions with human feedback (InstructGPT)](https://arxiv.org/abs/2203.02155) — 시연 데이터 기반 지도 미세조정, 선호 순위와 보상모델, RLHF 절차 및 저자 실험의 범위를 설명한다. 결과는 논문에 정의된 프롬프트 분포와 평가 조건에 묶어 기술한다.
- [Direct Preference Optimization](https://arxiv.org/abs/2305.18290) — 선호 쌍을 분류 손실로 직접 최적화하는 DPO의 유도와 RLHF 절차와의 관계를 설명한다. DPO가 모든 정렬 문제에서 RLHF를 대체한다고 일반화하지 않는다.
- [Semi-Supervised Classification with Graph Convolutional Networks](https://arxiv.org/abs/1609.02907) — 그래프 연결과 노드 특성을 함께 표현하는 GCN의 전파 구조 및 반지도 분류 설정을 설명한다. 인용망·지식그래프 실험을 임의의 그래프 문제로 일반화하지 않는다.

## 공개 모델·응용 사례

- [GraphCast: AI model for faster and more accurate global weather forecasting — Google DeepMind](https://deepmind.google/blog/graphcast-ai-model-for-faster-and-more-accurate-global-weather-forecasting/) — 개발자 공개 설명에서 Graph Neural Network 기반 예보 사례, 두 시점 상태를 입력해 다음 시점을 예측하고 반복하는 사용 흐름을 확인한다. 성능·속도 비교는 DeepMind가 제시한 평가 주장으로 귀속한다.
- [Learning Transferable Visual Models From Natural Language Supervision (CLIP)](https://arxiv.org/abs/2103.00020) — 이미지와 문장 쌍의 대조 사전학습, 텍스트로 시각 개념을 지정하는 zero-shot 평가 설정의 근거다. 저자 연구의 데이터와 평가 조건을 벗어난 성능을 주장하지 않는다.
- [Robust Speech Recognition via Large-Scale Weak Supervision (Whisper)](https://arxiv.org/abs/2212.04356) — 대규모 오디오·전사 자료로 학습한 다국어 음성 인식·번역 모델과 공개된 모델·추론 코드의 범위를 확인한다. 언어·환경별 품질을 보장하는 근거로 쓰지 않는다.
- [Segment Anything (SAM)](https://arxiv.org/abs/2304.02643) — 점·상자 등 프롬프트에 반응하는 분할 모델과 SA-1B 데이터셋의 연구 설정을 확인한다. 임의 도메인에서의 정확도를 일반화하지 않는다.
- [TypeSafe Jev: Introduction](https://docs.typesafe.ai/introduction), [Primitives](https://docs.typesafe.ai/primitives), [Confidence](https://docs.typesafe.ai/confidence) — 공식 문서에 명시된 Choice·Score·Noul 출력 형태와 문항 제약을 사례로 확인한다. Choice/Score의 confidence는 출력 확률분포 모양을 요약하고 Noul에는 별도 confidence가 없으며, 임계값은 사용 맥락에서 검증해야 한다. 이는 벤더 설명이지 독립 성능 검증이 아니다.

<!-- chapter-source-index -->
## 장별 추가 근거

각 장의 정의·가정·원리를 확인한 추가 근거다. 2026-10-06~07에 자료를 수집·검토했다. 구체적으로 어떤 설명을 뒷받침하는지는 연결한 장의 인용 위치에서 확인한다. 위의 공통 자료와 URL이 같은 항목은 다시 나열하지 않는다.

- [AIMA의 A* 강의 자료](https://aima.cs.berkeley.edu/slides-pdf/chapter04a.pdf) — [05](chapters/05_symbolic.md)
- [scikit-learn 공식 문서 §1.6.2~1.6.4](https://scikit-learn.org/stable/modules/neighbors.html) — [06](chapters/06_statistical_learning.md)
- [scikit-learn 공식 문서 §2.3.6](https://scikit-learn.org/stable/modules/clustering.html#hierarchical-clustering) — [06](chapters/06_statistical_learning.md)
- [scikit-learn 공식 DBSCAN 정의와 매개변수](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html) — [06](chapters/06_statistical_learning.md)
- [Understanding Machine Learning 저자 제공본](https://www.cs.huji.ac.il/~shais/UnderstandingMachineLearning/understanding-machine-learning-theory-algorithms.pdf) — [06](chapters/06_statistical_learning.md)
- [구조화된 확률모형의 정의와 그래프 관점](https://www.deeplearningbook.org/contents/graphical_models.html) — [07](chapters/07_probabilistic_models.md)
- [scikit-learn 공식 Naive Bayes 정의](https://scikit-learn.org/stable/modules/naive_bayes.html) — [07](chapters/07_probabilistic_models.md)
- [scikit-learn 공식 GMM 정의와 한계](https://scikit-learn.org/stable/modules/mixture.html) — [07](chapters/07_probabilistic_models.md)
- [Rasmussen·Williams, GPML §2.2~2.3와 Algorithm 2.1](https://gaussianprocess.org/gpml/chapters/RW2.pdf) — [07](chapters/07_probabilistic_models.md)
- [SimCLR의 대조학습 설계](https://arxiv.org/abs/2002.05709) — [09](chapters/09_learning_paradigms.md)
- [Model-Agnostic Meta-Learning](https://arxiv.org/abs/1703.03400) — [09](chapters/09_learning_paradigms.md)
- [Overcoming catastrophic forgetting](https://arxiv.org/abs/1612.00796) — [09](chapters/09_learning_paradigms.md)
- [Communication-Efficient Learning of Deep Networks from Decentralized Data](https://arxiv.org/abs/1602.05629) — [09](chapters/09_learning_paradigms.md)
- [High-Resolution Image Synthesis with Latent Diffusion Models](https://arxiv.org/abs/2112.10752) — [10](chapters/10_generative.md)
- [Introduction to Information Retrieval, §6.2](https://nlp.stanford.edu/IR-book/pdf/06vect.pdf) — [12](chapters/12_language_models.md)
- [Speech and Language Processing, 3장 §3.1·§3.6, 2026-08-19 초안](https://web.stanford.edu/~jurafsky/slp3/3.pdf) — [12](chapters/12_language_models.md)
- [Efficient Estimation of Word Representations in Vector Space, §3.1–3.2](https://arxiv.org/abs/1301.3781) — [12](chapters/12_language_models.md)
- [MIT Signals and Systems, Sampling 강의 노트](https://ocw.mit.edu/courses/res-6-007-signals-and-systems-spring-2011/8708ec068ebdea2c4ee2f38fad39fb83_MITRES_6_007S11_lec16.pdf) — [13](chapters/13_multimodal.md)
- [Connectionist Temporal Classification, §3](https://www.cs.toronto.edu/~graves/icml_2006.pdf) — [13](chapters/13_multimodal.md)
- [Pearl의 원논문, §2~3](https://ftp.cs.ucla.edu/pub/stat_ser/r350.pdf) — [15](chapters/15_causality.md)
- [Dudík·Langford·Li, 2011, §2~3](https://arxiv.org/pdf/1103.4601) — [15](chapters/15_causality.md)
- [DeepProbLog, Manhaeve 등, 2018](https://arxiv.org/abs/1805.10872) — [16](chapters/16_alternative_scientific.md)
- [DreamCoder, Ellis 등, 2020](https://arxiv.org/abs/2006.08381) — [16](chapters/16_alternative_scientific.md)
- [NEAT, Stanley·Miikkulainen, 2002](https://nn.cs.utexas.edu/downloads/papers/stanley.ec02.pdf) — [16](chapters/16_alternative_scientific.md)
- [Zadeh의 *Theory of Fuzzy Sets*, 1977, 정의와 기본 연산](https://www2.eecs.berkeley.edu/Pubs/TechRpts/1977/ERL-m-77-1.pdf) — [16](chapters/16_alternative_scientific.md)
- [Gerstner 등, *Neuronal Dynamics*, §1.3](https://neuronaldynamics.epfl.ch/online/Ch1.S3.html) — [16](chapters/16_alternative_scientific.md)
- [Raissi·Perdikaris·Karniadakis의 저자 자료, 연속시간 모형](https://maziarraissi.github.io/PINNs/) — [16](chapters/16_alternative_scientific.md)
- [Li 등, FNO, 2020/2021, §2~4](https://arxiv.org/html/2010.08895v3) — [16](chapters/16_alternative_scientific.md)
- [Cohen·Welling, G-CNN, 2016](https://arxiv.org/abs/1602.07576) — [16](chapters/16_alternative_scientific.md)
- [GPipe, Huang 등, 2018/2019](https://arxiv.org/abs/1811.06965) — [17](chapters/17_systems.md)
- [Jacob 등, 2017/2018, §2~3](https://arxiv.org/pdf/1712.05877) — [17](chapters/17_systems.md)
- [Hinton·Vinyals·Dean, 2015](https://arxiv.org/pdf/1503.02531) — [17](chapters/17_systems.md)
- [Lewis 등, 2020/2021](https://arxiv.org/abs/2005.11401) — [17](chapters/17_systems.md)
- [ReAct, Yao 등, 2022/2023](https://arxiv.org/abs/2210.03629) — [17](chapters/17_systems.md)
- [Guo 등, 2017, §2·4](https://arxiv.org/html/1706.04599v2) — [18](chapters/18_evaluation.md)
- [Sugiyama·Krauledat·Müller, 2007](https://www.jmlr.org/papers/v8/sugiyama07a.html) — [18](chapters/18_evaluation.md)
- [Goodfellow·Shlens·Szegedy, 2014/2015](https://arxiv.org/abs/1412.6572) — [18](chapters/18_evaluation.md)
- [Ribeiro·Singh·Guestrin, 2016](https://arxiv.org/abs/1602.04938) — [18](chapters/18_evaluation.md)
- [NIST AI 600-1, 2024, 위험 개관과 제안 활동](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) — [18](chapters/18_evaluation.md)
- [Dwork·Roth, 2014, §2.3·3.3·3.5](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf) — [18](chapters/18_evaluation.md)
- [Hardt·Price·Srebro, 2016, §2 및 §6](https://arxiv.org/pdf/1610.02413) — [18](chapters/18_evaluation.md)
- [Mitchell 등, *Model Cards*, 2018/2019](https://arxiv.org/abs/1810.03993) — [18](chapters/18_evaluation.md)
- [NIST AI RMF 1.0, 2023, Appendix C](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) — [18](chapters/18_evaluation.md)

<!-- fishing-source-index -->
## 어선 적용편 추가 근거

확인 기준일: 2026-10-07. 각 장의 본문에서 정의·수식·적용 조건 바로 옆에 출처를 연결했다. 아래는 추가된 주요 자료의 탐색 색인이다. 공통 Transformer·VAE·GAN·DDPM·Gaussian process·확률 보정 자료는 위 목록과 각 장의 연결을 함께 읽는다. 출처의 모델 정의와 이 교재가 만든 선박 시나리오·숫자·설계 선택은 서로 다른 증거다.

- [대회 공식 문제](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004601/detail.do) — [19장](chapters/19_fishing_data_geometry.md), [길잡이](95_fishing_guide.md): 과제·제공자료 설명의 출발점. 실제 파일 값과 평가식은 별도 확인.
- [GEOS WKT 문법](https://libgeos.org/specifications/wkt/), [QGIS 좌표계](https://docs.qgis.org/3.44/en/docs/gentle_gis_introduction/coordinate_reference_systems.html), [pyproj Geod](https://pyproj4.github.io/pyproj/stable/api/geod.html) — [19장](chapters/19_fishing_data_geometry.md): 기하 표현·좌표계·측지선 계산의 단위.
- [tslearn DTW](https://tslearn.readthedocs.io/en/stable/user_guide/dtw.html), [Shapely 거리 연산](https://shapely.readthedocs.io/en/stable/measurement.html) — [19장](chapters/19_fishing_data_geometry.md): 경로 비교의 정의·계산·구현 규약.
- [scikit-learn 선형 모델](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression), [트리](https://scikit-learn.org/stable/modules/tree.html#mathematical-formulation), [앙상블](https://scikit-learn.org/stable/modules/ensemble.html) — [20장](chapters/20_fishing_classification.md): 분류·분기·앙상블의 기본 구조.
- [Adam 원논문](https://arxiv.org/abs/1412.6980), [Gradient Surgery 원논문](https://arxiv.org/abs/2001.06782) — [20장](chapters/20_fishing_classification.md): 최적화와 공동 목적의 기울기 충돌.
- [TCN 연구](https://arxiv.org/abs/1803.01271), [GRU 원논문](https://arxiv.org/abs/1406.1078), [Rabiner HMM](https://www.cs.cmu.edu/~cga/behavior/rabiner1.pdf), [Kalman 원논문](https://people.math.harvard.edu/archive/116_fall_03/handouts/Kalman1960.pdf) — [21장](chapters/21_fishing_sequence_models.md): 순서 표현·이산 숨은 상태·수치 상태 추정.
- [SciPy MAD](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html), [Gaussian 밀도](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.multivariate_normal.html), [KDE](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gaussian_kde.html) — [22장](chapters/22_fishing_anomaly.md): 기준 통계와 밀도 점수.
- [Isolation Forest 원논문](https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/icdm08b.pdf), [One-Class SVM 원논문](https://alex.smola.org/papers/2001/SchPlaShaSmoetal01.pdf) — [22장](chapters/22_fishing_anomaly.md): 고립 경로·한 클래스 경계의 목적과 가정.
- [Autoencoder 저자 교재](https://www.deeplearningbook.org/contents/autoencoders.html), [Denoising autoencoder 원논문](https://icml.cc/Conferences/2008/papers/592.pdf), [Page CUSUM](https://doi.org/10.1093/biomet/41.1-2.100), [Focal Loss 원논문](https://openaccess.thecvf.com/content_iccv_2017/html/Lin_Focal_Loss_for_ICCV_2017_paper.html) — [22장](chapters/22_fishing_anomaly.md): 복원·순차 변화·불균형 지도 손실.
- [기상청 해양기상부이](https://data.kma.go.kr/data/sea/selectBuoyRltmList.do?pgmNo=52), [국립해양조사원 최신 관측 API](https://www.data.go.kr/data/15155516/openapi.do), [QGIS 보간](https://docs.qgis.org/3.44/en/docs/gentle_gis_introduction/spatial_analysis_interpolation.html) — [23장](chapters/23_fishing_environment.md): 외부자료 후보·보간. 최신값 API가 과거 대회기간 자료 제공을 보장하지 않음.
- [CVAE 원논문](https://papers.nips.cc/paper_files/paper/2015/hash/8d55a249e6baa5c06772297520da2051-Abstract.html), [Fossen 해양체 모형](https://www.fossen.biz/html/marineCraftModel.html), [Duke OU 강의](https://sites.duke.edu/probabilityworkbook/ornstein-uhlenbeck-process/), [MIT 반마르코프 강의](https://ocw.mit.edu/courses/6-231-dynamic-programming-and-stochastic-control-fall-2015/resources/mit6_231f15_lec13/) — [24장](chapters/24_fishing_virtual_units.md): 조건 생성·운동·확률적 변화·체류시간. 실제 어선 매개변수를 검증한 출처로 확대 해석하지 않음.
- [scikit-learn 그룹·시간 분할](https://scikit-learn.org/stable/modules/cross_validation.html), [지표](https://scikit-learn.org/stable/modules/model_evaluation.html), [average precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html), [확률 보정](https://scikit-learn.org/stable/modules/calibration.html), [SHAP 원논문](https://arxiv.org/abs/1705.07874) — [25장](chapters/25_fishing_evaluation_system.md): 평가의 단위·순위·확률·설명 기여. 공식 대회 지표를 대신하지 않음.
