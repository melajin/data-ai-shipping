# final round_013: 7대 가설 병렬 검증과 지표 재채점

## 0. round_013의 설계 배경

round_012까지의 단일 순차 실험들이 모두 내부 주관문(+5%p 개선)을 통과하지 못함에 따라, round_013에서는 평가 계약을 전면 복원하고 후보 시각 선택과 관련된 7대 가설을 병렬로 검증하는 대규모 진단을 수행했다(`testB/final/round_013_design_20261106_060012/ROUND013_PLAN.md`, `testB/final/round_013_20261106/PROTOCOL.md`). 또한 과거 회차(R1~R12)에서 산출된 모든 저장 예측값에 대해 연속 오차 중앙값(abs_error median)을 기준으로 paired Wilcoxon 검정과 Holm step-down 다중비교 보정을 적용하여 사후 통계적 생존 여부를 전수 재검증했다(`testB/final/round_013_metric_rescore/RESCORE.md`).

---

## 1. 7대 가설별 검증 결과

### 1) 급변 기하 피처 (`round_013_abrupt_feature`)

1. **가설**: 6시간 경계상자 크기(`bbox_m`)의 로그비 급변량이 사고 순간의 기하학적 궤적 붕괴를 포착하여 사고 시각을 정확히 분리할 수 있는가(`testB/final/round_013_abrupt_feature/result.txt`).
2. **조건**: 2026년 dev 100건 사건(`testB/final/round_013_abrupt_feature/event_results.csv`).
3. **측정값**: 절대오차 중앙값은 917.5시간이었고, $\pm 6$시간 적중 수는 3/100(3.0%)이었으며, 2,000회 사건 셔플 순열검정 $p$값은 0.0260이었다(`testB/final/round_013_abrupt_feature/result.txt`).
4. **판정**: 기각(`testB/final/round_013_abrupt_feature/result.txt`). 시간당 박스 크기의 급변이 사고 특유의 징후라기보다는 정상 조업과 항해 이동 간의 일상적 전환에도 민감하게 반응하여 기존 B0(3/100) 대비 적중 수를 개선하지 못했다(`testB/final/round_013_abrupt_feature/result.txt`).
5. **이전과의 차이**: 축약된 정적 요약치 대신 시간대별 상자 크기의 비율 변화량을 직접 추적했다.
6. **다음과의 차이**: 단일 기하 변형 대신 공간적 이동 패턴(표류)을 시험했다.
7. **원본 경로**: (`testB/final/round_013_abrupt_feature/result.txt`, `testB/final/round_013_abrupt_feature/event_results.csv`).

### 2) 공란 판정 임계값 (`round_013_abstention`)

1. **가설**: 선박별 이상항적 최고점에 임계값($\ge 0.60$)을 적용하여 점수가 낮은 선박의 예측 칸을 전면 공란(기각) 처리하면, 오탐을 줄여 F1을 개선할 수 있는가(`testB/final/round_013_abstention/RESULT.md`).
2. **조건**: 2025년 Test B 100척 대상 탐색 임계값 적용(`testB/final/round_013_abstention/RESULT.md`).
3. **측정값**: 임계값 0.60을 적용했을 때 사고 판정 선박은 37척, 비사고(공란) 판정 선박은 63척으로 분리되었다(`testB/final/round_013_abstention/RESULT.md`). 사고판정군과 기각군의 기존 이상점수 중앙값은 각각 0.683506 대 0.509826이었다(`testB/final/round_013_abstention/RESULT.md`). 민감도 검토에서는 임계값 0.50에서 75척 사고/25척 공란, 0.55에서 50척 사고/50척 공란, 0.65에서 22척 사고/78척 공란으로 집계되었다(`testB/final/round_013_abstention/RESULT.md`). 그러나 2025 Test 100척과 개발 82 RFID 간의 ID 교집합이 0척이었으므로 라벨 일치율 및 실제 F1 수치는 산출할 수 없었다(`testB/final/round_013_abstention/RESULT.md`).
4. **판정**: 탐색 기준 수립 및 성능 확정 보류(`testB/final/round_013_abstention/RESULT.md`). 임계값 0.60은 공란 처리를 실행·비교하기 위한 기술적 기준이며, 공식 F1의 실제 개선 여부는 정답 부재로 인해 확인되지 않았다(`testB/final/round_013_abstention/RESULT.md`).
5. **이전과의 차이**: 100척 전 칸을 채우던 기존 제출 방식에서 벗어나 공란 판정 메커니즘을 최초로 구체화했다.
6. **다음과의 차이**: round_015에서 공식 규칙을 반영한 F1 산출식으로 민감도를 엄격히 재평가했다.
7. **원본 경로**: (`testB/final/round_013_abstention/RESULT.md`).

### 3) 표류 패턴 (`round_013_drift`)

1. **가설**: 추진이나 조타를 상실한 어선은 외력에 의해 표류하므로, 저속 조건 하에서 대권 방위각의 원형 분산(최근 6시간 대 직전 12시간)이 증가하는 패턴을 통해 사고 시각을 특정할 수 있는가(`testB/final/round_013_drift/결과.md`).
2. **조건**: 2026 dev 100건 사건 중 18시간 연속 유효 이동 및 감속 조건을 충족하는 37건(28척)(`testB/final/round_013_drift/결과.md`).
3. **측정값**: 절대오차 중앙값은 909시간이었고, $\pm 6$시간 적중 수는 0/100(후보가 존재하는 37건 중에서도 0/37 적중)이었으며, 순열검정 $p$값은 0.3015였다(`testB/final/round_013_drift/결과.md`).
4. **판정**: 기각(`testB/final/round_013_drift/결과.md`). 시간대 박스 중심점의 이동 방향이 선박의 실제 침로를 정확히 대변하지 못했고, 18시간 연속 이동이라는 엄격한 필터로 인해 평가 가능 사건이 37건으로 급감하여 표류 전환 신호를 분리하지 못했다(`testB/final/round_013_drift/결과.md`).
5. **이전과의 차이**: 이동량 크기 대신 방위각 원형 분산이라는 방향성 지표를 적용했다.
6. **다음과의 차이**: 단일 선박의 이동성 대신 전체 선단의 동시적 움직임을 고려하는 동시성 필터로 전환했다.
7. **원본 경로**: (`testB/final/round_013_drift/결과.md`).

### 4) 동료 선박 동시성 필터 (`round_013_fleet_simultaneity`)

1. **가설**: 특정 시각에 동료 선박 다수(5척 이상 중 20% 이상)가 동시에 상위 10%의 이상점수를 나타내는 경우를 기상 악화 등 외부 환경 충격으로 정의하고 이를 제외하면, 선박 고유의 사고 시각 적중률이 향상되는가(`testB/final/round_013_fleet_simultaneity/결과.md`).
2. **조건**: 2026 dev 82척 99,677행 및 100건 사건(`testB/final/round_013_fleet_simultaneity/결과.md`).
3. **측정값**: 전체 99,677행 중 10,864행(10.90%)이 동시성 필터에 의해 제외되었다(`testB/final/round_013_fleet_simultaneity/결과.md`). 필터 적용 후 절대오차 중앙값은 827시간으로 기존 B0(1,053.5시간) 대비 단축되었고, $\pm 6$시간 적중 수는 4/100으로 B0(3/100) 대비 1건 증가했으며, 순열검정 $p$값은 0.0005였다(`testB/final/round_013_fleet_simultaneity/결과.md`).
4. **판정**: 탐색적 성과 채택 및 공식 승격 보류(`testB/final/round_013_fleet_simultaneity/결과.md`). 외부 공통 노이즈 제거 효과가 관찰되었으나, 적중 수 증가(+1건)가 운영 채택 기준(+5%p)에 미달하여 단독 모델로 승격하지 않았다(`testB/final/round_013_fleet_simultaneity/결과.md`).
5. **이전과의 차이**: 개별 선박의 항적만을 보던 방식에서 벗어나 전체 선단의 시공간 동시 분포를 최초로 필터링에 활용했다.
6. **다음과의 차이**: 관측 공백과 위치 점프 비율을 다루는 관측 단절 가설로 이행했다.
7. **원본 경로**: (`testB/final/round_013_fleet_simultaneity/결과.md`).

### 5) 단절 길이 대비 재개 위치 점프 비율 (`round_013_gap_jump_ratio`)

1. **가설**: 1시간을 초과하는 관측 단절 구간에서 양 끝 중심점 간 대권거리를 단절 시간과 직전 정상 이동속도로 나눈 비율(`gap_jump_speed_ratio_abs_log`)이 사고로 인한 위치 급변이나 예인 시작을 포착하는가(`testB/final/round_013_gap_jump_ratio/결과.md`).
2. **조건**: 6,205개 단절 경계 쌍 중 기준을 충족하는 5,387개, 79척 97건 사건(`testB/final/round_013_gap_jump_ratio/결과.md`).
3. **측정값**: 절대오차 중앙값은 1,095시간이었고, $\pm 6$시간 적중 수는 1/97(전체 100건 중 1건)이었으며, 순열검정 $p$값은 0.0115였다(`testB/final/round_013_gap_jump_ratio/결과.md`).
4. **판정**: 기각(`testB/final/round_013_gap_jump_ratio/결과.md`). 적중 수가 1건에 그쳐 B0(3/100)보다 낮았으며, 단절 길이 대비 점프 비율의 변화가 사고 시점보다는 통신 결측 및 집계 조건을 더 많이 반영했기 때문이다(`testB/final/round_013_gap_jump_ratio/결과.md`).
5. **이전과의 차이**: 단순 공백 시간이 아닌 공백 전후의 공간적 점프 거리를 속도와 결합하여 평가했다.
6. **다음과의 차이**: 공백 재개 시점의 위치 대신 최장 공백 자체의 시점을 시험했다.
7. **원본 경로**: (`testB/final/round_013_gap_jump_ratio/결과.md`).

### 6) 최장 관측 공백 재개 시각 (`round_013_gap_signal`)

1. **가설**: 선박의 전체 항적 중 가장 길게 이어진 관측 공백이 재개되는 시점이 사고 발생 시각과 직접 일치하는가(`testB/final/round_013_gap_signal/result.txt`).
2. **조건**: 2026 dev 100건 사건(`testB/final/round_013_gap_signal/result.txt`).
3. **측정값**: 절대오차 중앙값은 1,220.5시간이었고, $\pm 6$시간 적중 수는 1/100(1.0%)이었으며, 순열검정 $p$값은 0.901이었다(`testB/final/round_013_gap_signal/result.txt`).
4. **판정**: 기각(`testB/final/round_013_gap_signal/result.txt`). 관측 공백은 사고로 인한 통신 두절뿐 아니라 정상 입항 및 자료 누락 등 다양한 요인으로 발생하므로 사고와의 연결이 지지되지 않았다(`testB/final/round_013_gap_signal/result.txt`).
5. **이전과의 차이**: 복잡한 비율 대신 최장 공백 시점 하나만을 단순 지표로 검증했다.
6. **다음과의 차이**: 관측 공백 대신 관측이 드문 조업 시간대 이탈을 가중하는 방식으로 전환했다.
7. **원본 경로**: (`testB/final/round_013_gap_signal/result.txt`).

### 7) 조업시간대 이탈 가중 (`round_013_offhours_weight`)

1. **가설**: 선박별로 평소 관측 빈도가 낮은 시간대(off-hours)에 나타난 이상점수에 가중치(`2 - count/max_count`)를 곱하면 야간 및 비조업 시간의 사고 시각 선택을 개선할 수 있는가(`testB/final/round_013_offhours_weight/결과.md`).
2. **조건**: 2026 dev 82척 100건 사건(후보 날짜 제외 나머지 날짜 집계)(`testB/final/round_013_offhours_weight/결과.md`).
3. **측정값**: 사건 100개 중 69개의 선택 시각이 변경되었다(`testB/final/round_013_offhours_weight/결과.md`). 오차 중앙값은 998.5시간(가중 전 1,053.5시간 대비 감소), $\pm 6$시간 적중 수는 4/100(가중 전 3/100 대비 +1건), 순열검정 $p$값은 0.0085였다(`testB/final/round_013_offhours_weight/결과.md`).
4. **판정**: 탐색적 성과 채택 및 공식 승격 보류(`testB/final/round_013_offhours_weight/결과.md`). 오차 감소가 관찰되었으나 기준선 대비 적중률 향상 폭(+1건)이 주관문(+5%p)에 미달했고, 후보일을 제외한 미래 날짜의 통계가 포함되어 사후 분석에 한정되었기 때문이다(`testB/final/round_013_offhours_weight/결과.md`).
5. **이전과의 차이**: 기하학적 형태나 공백 대신 시간대별 생활 리듬의 희소도를 가중치로 활용했다.
6. **다음과의 차이**: 7대 가설 검증 완료 후 기존 R1~R12 회차의 통계적 재채점으로 종합 진단을 완료했다.
7. **원본 경로**: (`testB/final/round_013_offhours_weight/결과.md`).

---

## 2. round_013_metric_rescore (지표 재채점과 통계적 사후 검증)

회차 1부터 12까지 저장된 20개 실행 결과에 대해 내부 선택 지표인 오차 중앙값(abs_error median)을 기준으로 B0 대비 양측 paired Wilcoxon 검정과 Holm step-down 다중비교 보정($\alpha=0.05$)을 전수 재계산했다(`testB/final/round_013_metric_rescore/RESCORE.md`).

| 회차 및 실행본 | 방법 | 오차 중앙값(h) | B0 대비 Wilcoxon $p$ | Holm 보정 후 통계적 생존 여부 |
|---|---|---:|---:|---|
| R1 | 저장 CSV 없음 | — | — | 산출 불가 |
| R2 / execution_001 | B0_common | 738.0 | 2.51038e-05 | **제외: 기존 실행 무효(C/U 정렬 오류)** |
| R2 / execution_001 | B0_full | 1,053.5 | — | 기준선 |
| R2 / execution_001 | C | 758.0 | 2.51038e-05 | **제외: 기존 실행 무효(C/U 정렬 오류)** |
| R2 / execution_001 | U | 758.0 | 2.51038e-05 | **제외: 기존 실행 무효(C/U 정렬 오류)** |
| R2 / execution_002 | B0_full | 1,053.5 | — | 기준선 |
| R2 / execution_002 | C | 1,304.0 | 0.177235 | 아니오 ($p_{adj} = 1.0$) |
| R2 / execution_002 | U | 1,158.0 | 0.328935 | 아니오 ($p_{adj} = 1.0$) |
| R4 / execution_001 | G | 1,032.5 | 0.973350 | 아니오 ($p_{adj} = 1.0$) |
| R4 / execution_001 | S | 845.5 | 0.063667 | 아니오 ($p_{adj} = 0.955$) |
| R5 / execution_001 | G | 1,032.5 | 0.973350 | 아니오 ($p_{adj} = 1.0$) |
| R5 / execution_001 | S | 845.5 | 0.063667 | 아니오 ($p_{adj} = 0.955$) |
| R5 / execution_001 | S1 | 1,113.5 | 0.983453 | 아니오 ($p_{adj} = 1.0$) |
| R6 / execution_001 | G | 743.0 | 0.258817 | 아니오 ($p_{adj} = 1.0$) |
| R6 / execution_001 | S | 760.0 | 0.210714 | 아니오 ($p_{adj} = 1.0$) |
| R8 / execution_001 | G | 811.5 | 0.019529 | 아니오 ($p_{adj} = 0.332$) |
| R8 / execution_001 | S | 952.0 | 0.128497 | 아니오 ($p_{adj} = 1.0$) |
| R9 / execution_001 | G | 966.5 | 0.727143 | 아니오 ($p_{adj} = 1.0$) |
| R9 / execution_001 | S | 955.5 | 0.375687 | 아니오 ($p_{adj} = 1.0$) |
| R11 / execution_001 | G | 829.5 | 0.043601 | 아니오 ($p_{adj} = 0.698$) |
| R11 / execution_001 | S | 823.0 | 0.013488 | 아니오 ($p_{adj} = 0.243$) |

재채점 결과의 핵심 사실은 두 가지다(`testB/final/round_013_metric_rescore/RESCORE.md`).

첫째, R2 execution_001의 B0_common은 통계적으로 $p_{adj} = 0.000502$로 Holm 기준을 통과하여 생존했으나, 해당 실행본 자체가 C와 U의 데이터 정렬 오류로 인해 같은 디렉터리의 [INVALID_COMPARISON.md](../round_002_20261105/execution_001/INVALID_COMPARISON.md)에서 이미 무효 판정을 받은 실행이었다(`testB/final/round_013_metric_rescore/RESCORE.md`). 올바르게 재실행된 R2 execution_002에서는 C($p_{adj}=1.0$)와 U($p_{adj}=1.0$) 모두 통계적 유의성을 얻지 못했다(`testB/final/round_013_metric_rescore/RESCORE.md`).

둘째, 유효한 나머지 모든 회차(R4, R5, R6, R8, R9, R11)의 변경안들은 단변량 원 $p$값이 낮게 나온 경우(예: R8 G 원 $p=0.0195$, R11 S 원 $p=0.0135$)에도 20개 다중비교에 대한 Holm step-down 보정을 적용하면 모두 $p_{adj} \ge 0.243$으로 통계적 유의성을 잃고 탈락했다(`testB/final/round_013_metric_rescore/RESCORE.md`).

이로써 회차 1부터 12까지의 모든 성능 변경안은 엄격한 다중비교 기준 하에서 통계적으로 생존하지 못했음이 최종 확정되었다(`testB/final/round_013_metric_rescore/RESCORE.md`).
