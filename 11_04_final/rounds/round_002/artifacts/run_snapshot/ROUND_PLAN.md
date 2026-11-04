# Round 002 사전 계획

동결 시각: 2026-11-04 14:33 UTC. 인계 문서 SHA256: C8F0D8C90ED3C60FD2140B91482483CEE2F9DF5B9DEAE652AF39928E1ABF7577. 구체적인 실행 설정은 configs/experiment.json에 기록하고 학습 전에 해시를 고정한다.

기술 목표는 같은 X304/FIT에서 새 모델 파이프라인이 다른 오류를 줄이는지 확인하는 것이다. 학습 목표는 조기 종료·결합 선택 자료 분리, 짝지은 정답 변화, 개발 평가의 한계를 설명하는 것이다. 예상 성능은 미정이다.

- 개발 5,897척의 기존 3fold 고정 NPZ만 사용한다. 원자료 및 holdout 개별 특징·정답·확률은 읽지 않는다. T5/local_rel의 기존 transductive 조건은 유지하며 FIT-only 특징이라고 부르지 않는다.
- fold INNER를 stratified test_size=0.5, random_state=20261105로 ES/SELECT로 나눈다. 같은 FIT로 기존 sqrt_macro seed42 기준선을 재학습한다. 기존 exp01 설정을 보존하고 ES만 바꾼다.
- 환경 확인 후 CatBoost 1개 파이프라인을 사전 선택한다. 설치/호환 실패 또는 설치 시간 초과에만 ExtraTrees로 전환한다. 점수 기반 후보 교체는 금지한다. CatBoost: CPU, seed42, 최대3000회, depth6, lr0.03, l2=3, threads3, MultiClass, 비가중 Accuracy ES200, sample weight 없음. 결측은 공식 API를 확인하여 실행 전에 고정한다.
- 각 fold SELECT에서 alpha 0/0.25/0.5/0.75/1의 micro 최고를 선택하고 동점은 작은 alpha다. OUTER는 그 fold의 학습·조기 종료·결합 선택에 사용하지 않는다. 여러 fold SELECT를 합쳐 alpha를 고르지 않는다.
- 학습 전 별도 Luna 검토를 받는다. 모델·확률·명부·입력/코드/환경 해시를 보존하고 reload 확률 abs<=1e-12, 역할 분리, 클래스/특징 순서, 확률 유한성과 합계를 확인한다.
- 동일조건 기준선·후보·fold-local blend의 개발 OUTER micro/macro, 클래스 recall/F1, 1–7/8–30/31–90/91+일 구간, fold 지표, paired gain/loss/net와 5000회 seed20261105 bootstrap95%CI를 보고한다. 기존5seed .593013은 역사 비교로만 표시한다.
- 전체 45분(14:30:47–15:15:47 UTC), 환경 탐색5분/설치8분, fit+추론30분, 새 fit 최대6개, 동시 학습1개, threads<=3, 새 fit 전에 가용RAM>=1.5GiB. 예산 초과 시 부분 결과와 정확한 재개 범위를 남긴다.

판정: 계보·입력·reload 실패는 채택 금지다. 유효 개발 micro>=.7이면 독립 평가 이력 감사로 인계한다. 그 미만에서 동일조건 대비 micro>=+.005, paired CI 하한>0, macro/각 클래스 recall/각 관측일 구간 micro 하락<=.03이면 다음 회차 5seed 확인 후보로 진행한다. 아니면 월별35 특징의 같은 seed·같은 학습규칙 통제 비교를 다음 회차에서 설계한다. 이는 개발 탐색 진행 기준이며 독립 일반화 증명이 아니다.

학습 질문: 기존 전체 INNER로 조기 종료한 모델을 SELECT에 재사용하면 왜 분리가 완성되지 않는가? 새 정답과 새 오답을 함께 세는 이유는 무엇인가? 파이프라인 차이를 순수 모델 계열의 인과효과로 볼 수 없는 이유는 무엇인가?
