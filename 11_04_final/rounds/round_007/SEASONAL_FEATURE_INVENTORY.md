# 월·시간대 특징 인벤토리 — 코드와 특징명 대조

이번 작업은 코드·특징명 metadata의 정적 대조다. 실제자료 배열·개별확률·원자료·holdout은 읽지 않았으며 새 모델/F1 계산은 없다. 정확한 304개 특징명과 참조10개 SHA256은 `artifacts/seasonal_feature_metadata.json`에 저장했다. 읽기 전용 이전 저장소의 코드 경로를 아래에 표시한다.

| 블록 | 이미 포함된 시간 정보 | 월별 변화 보존의 한계 |
|---|---|---|
| F156의 형태84열 | 21개 형태의 일별 p10/median/p90/IQR | 날짜별 순서와 월별 변화가 최종 집계에서 사라짐 |
| F156 공간20열 | 일별 위치·범위·shift, 인접시간 정적 비율 등 | 기간 전체 공간 요약이며 월별 지역 전환 열은 없음 |
| F156 temporal12열 | native hour 0–5/6–11/12–17/18–23 × zero_path_fraction/log_length_median/straightness_median | 일×구간 요약 뒤 관측일 중앙값. 월별 순서 없음; timezone 미확인 |
| F156 vocabulary34열 | 16개 모드 일별 비율·자기유지확률, 일별 entropy/distinct | FIT-only dictionary, 관측시간 인접 전이 요약. 월별 모드 변화 자체는 보존하지 않음 |
| F156 quality6열 | observed_rows/days/usable_days, 관측·geometry·large_jump 비율 | 관측량/품질이며 조업시간 정답 아님 |
| F304의 T5 10열 | main 업종분포4, month 업종분포4, fine-grid 비율, log fishing rows | 월마다 FIT 업종 참조분포를 조회하나 선박의 관측행 전체에서 평균해4열로 축약. 월별 시계열이 아님 |
| F304의 behavior68열 | 관측시간수/일 coverage, 재방문 일간격, 연속저이동/구간 길이 proxy, hour_entropy, 시간대 비율4, night-stat비율, 원형집중도 | 기간 전체 집계; 월별 형태·지역·시간대 조합은 명시되지 않음 |
| F304의 local_rel70열 | behavior69(원 obs_days 포함)의 지역 중앙값/MAD 상대값69 + region_n | 같은 연도 cohort 전체 통계·자기 포함. 월별 상대화나 FIT-only 아님 |

F304=F156156+T510+behavior68+local_rel70이다. 현재 TabICL 재현 입력312열은 F156의 값156+결측표시156이며 F304와 다른 계약이다. 재현 비교에서 F304나 시간 특징을 끼워 넣지 않는다.

## 소스에서 확인한 세부사항

- `team/tabiclv2_f156/metadata/feature_columns.json`: F156156열의 순서와 위 블록 크기. `.../historical/TabM/TabM_개선_20261030/temporal_features.py`의 `build_temporal`: `rfid_time // 6`, 일별 집계 뒤 날짜별 median. 결측 bin은 NaN, support는 별도 metadata. native clock은 KST/UTC가 확인되지 않았다.
- 같은 위치의 `vocabulary_features.py`: FIT-only dictionary와 일별 빈도·연속관측 전이. 이름의 stay_probability를 검증된 정박행동으로 해석하지 않는다.
- `code/tools/run_005_F156_merge_20261101.py`의 `t5_features_for`: 각 관측행의 month에 맞는 dictionary를 조회하고 `out[4:8]=mean(month_vecs)`로 축약한다. FIT 라벨에서 참조를 만들고 FIT 자기표본을 보정하지만 기존 항구/geometry 통계의 transductive 조건은 남는다.
- `11월 4일/code/01_build_behavior_features_20261104.py`: 시간대 구간은22–03/04–07/08–17/18–21로 F156의6시간 구간과 다르다. `trip`은 관측 간격≥3시간에서 나눈 계산상 구간이고 검증된 출항이 아니다. hourly centroid 변화·관측빈수·stationary flag는 좌표별 실속력·정지시간·실제 조업행동으로 바꾸어 말하지 않는다.
- `11월 4일/code/07_local_relative_20261104.py`: 전체 연도 내 주격자 기반 중앙값/MAD, 작은 지역의 전체분포 fallback, 자기포함이다. 원 코드 주석의 “라벨을 쓰지 않으므로 누수가 없다”를 FIT-only/독립성 증명으로 채택하지 않는다.
- `coach/gpt/rank1_experiments_20261104/shared/data_adapter.py`와 `reports/exp01/data_validation.json`: F304의 정확한 블록순서·특징명. CSV/NPZ 값은 읽지 않았다.

## 기존 monthly_repeat와 새 가설의 차이

`code/temporal_cache_adapter.py`와 기존 설정의 기간은1–6월181일이다. monthly_repeat35열은 월별 관측mask/active-days/hour-bins18열, 월간 관측량 통계8열, 시간대별 월간 평균·SD8열, 연속관측일 profile cosine1열이다. 이는 월별 형태나 지역 centroid의 변화량을 직접 넣는 계약은 아니다. monthly daypart 평균·SD도 월 순서를 완전히 보존하지 않는다. date/hour는 시간별 요약행의 시각이며 WKT 좌표별 시각이 아니다.

round006에 보존된 역사 monthly_repeat 결과는 none_micro seed42 대비 개발 micro+0.0044090/순증26, paired95%구간[-0.0016958,+0.0108530]이다. 현재 sqrt_macro5seed와 다른 비교이며 이번 새 계산이 아니다. 이 인벤토리도 계절 효과의 인과적·성능적 증거가 아니다.

후속 가설은 월별 관측량 자체와 별도로 월별 형태·지역·시간대 변화량을 보존하는 것이다. 최소 후보 설계 전에 timezone·유효 분모·월mask·월별 관측량 교란을 확인하고 선박 단위 분할을 유지한다. 기준선과 같은 학습/선택 예산에서 월관측량 후보와 월별변화 후보를 구분한다. 1–6월만으로 사계절·연도 독립 일반화나0.7 달성을 주장하지 않는다. 이번 회차는 가설/인벤토리 완성에서 멈춘다.

학습 질문: 월별 T5 평균과 월별 시계열은 무엇이 다른가? 무관측과 비조업은 왜 구분해야 하는가? local_rel의 라벨 미사용이 FIT-only를 보장하지 않는 이유는 무엇인가? 같은 선박의 월을 학습/평가로 나누면 어떤 일반화 질문으로 바뀌는가?
