내부 선택 지표: k=1의 저장 abs_error 중앙값(h), 작을수록 좋음. 공식 F1 점수가 아니다.
B0 대비 양측 paired Wilcoxon, zero_method=wilcox, method=auto; 전체 20개 비교에 Holm step-down, α=0.05.
R2 기준은 B0_full이며 B0_common도 비교 대상이다. 실행본을 합치거나 유리한 실행을 선택하지 않았다. 중복 실행도 보수적으로 별도 비교에 포함했다.
중앙값은 유효 예측 행 기준, 검정은 같은 acc_id의 양쪽 유효 예측만 사용한다. 결측은 0으로 대체하지 않았다. R2 B0_common은 98/100행으로 다른 방법의 100행 중앙값과 직접 순위 비교에 주의한다.

| 회차/실행 | 방법 | 오차중앙값(h) | B0대비 Wilcoxon p | Holm보정 후 생존여부 |
|---|---|---:|---:|---|
| R1/— | 저장 CSV 없음 | — | — | 산출 불가 |
| R2/execution_001 | B0_common | 738.0 | 2.51038e-05 | 예 (p_adj=0.000502077) |
| R2/execution_001 | B0_full | 1053.5 | — | 기준선 |
| R2/execution_001 | C | 758.0 | 2.51038e-05 | 제외: 기존 실행 무효(C/U 정렬 오류) |
| R2/execution_001 | U | 758.0 | 2.51038e-05 | 제외: 기존 실행 무효(C/U 정렬 오류) |
| R2/execution_002 | B0_common | 738.0 | 2.51038e-05 | 예 (p_adj=0.000502077) |
| R2/execution_002 | B0_full | 1053.5 | — | 기준선 |
| R2/execution_002 | C | 1304.0 | 0.177235 | 아니오 (p_adj=1) |
| R2/execution_002 | U | 1158.0 | 0.328935 | 아니오 (p_adj=1) |
| R3/— | 저장 CSV 없음 | — | — | 산출 불가 |
| R4/execution_001 | B0 | 1053.5 | — | 기준선 |
| R4/execution_001 | G | 1032.5 | 0.97335 | 아니오 (p_adj=1) |
| R4/execution_001 | S | 845.5 | 0.0636667 | 아니오 (p_adj=0.955001) |
| R5/execution_001 | B0 | 1053.5 | — | 기준선 |
| R5/execution_001 | G | 1032.5 | 0.97335 | 아니오 (p_adj=1) |
| R5/execution_001 | S | 845.5 | 0.0636667 | 아니오 (p_adj=0.955001) |
| R5/execution_001 | S1 | 1113.5 | 0.983453 | 아니오 (p_adj=1) |
| R5/execution_002 | B0 | 1053.5 | — | 기준선 |
| R5/execution_002 | G | 1032.5 | 0.97335 | 아니오 (p_adj=1) |
| R5/execution_002 | S | 845.5 | 0.0636667 | 아니오 (p_adj=0.955001) |
| R5/execution_002 | S1 | 1113.5 | 0.983453 | 아니오 (p_adj=1) |
| R6/execution_001 | B0 | 1053.5 | — | 기준선 |
| R6/execution_001 | G | 743.0 | 0.258817 | 아니오 (p_adj=1) |
| R6/execution_001 | S | 760.0 | 0.210714 | 아니오 (p_adj=1) |
| R7/— | 저장 CSV 없음 | — | — | 산출 불가 |
| R8/execution_001 | B0 | 1053.5 | — | 기준선 |
| R8/execution_001 | G | 811.5 | 0.0195293 | 아니오 (p_adj=0.331998) |
| R8/execution_001 | S | 952.0 | 0.128497 | 아니오 (p_adj=1) |
| R9/execution_001 | B0 | 1053.5 | — | 기준선 |
| R9/execution_001 | G | 966.5 | 0.727143 | 아니오 (p_adj=1) |
| R9/execution_001 | S | 955.5 | 0.375687 | 아니오 (p_adj=1) |
| R10/— | 저장 CSV 없음 | — | — | 산출 불가 |
| R11/execution_001 | B0 | 1053.5 | — | 기준선 |
| R11/execution_001 | G | 829.5 | 0.0436006 | 아니오 (p_adj=0.697609) |
| R11/execution_001 | S | 823.0 | 0.0134879 | 아니오 (p_adj=0.242782) |

R1·R3·R7·R10은 저장 event_results.csv가 없어 산출 불가. R8 synthetic_execution은 합성 검증이므로 제외했다.
R2 execution_001 C/U는 같은 폴더 INVALID_COMPARISON.md에서 무효로 판정된 실행이다. 오차·p는 기록 검산용이며 Holm 및 가설 판단에서 제외했다. 생존은 양측 차이의 유의성을 뜻하며 새 방법의 유효성 또는 공식 성능을 입증하지 않는다.
검증: 저장 오차와 저장 top1 시각의 차이 일치, 사건 키 중복 없음, 짝의 사고시각 일치 확인. /3600 변환 없음.
1차 remeasure.py는 R2의 B0 별칭을 건너뛰고 결측·중복을 명시하지 않으며 Holm이 없다. null.py는 execution_001만 다루고 Monte Carlo p에 +1 보정이 없다. 여기서는 모든 실행을 검사하고 (b+1)/(2000+1)을 사용했다.
순열검정은 사건 간 저장 예측시각의 교환가능성을 가정한 진단이며 B0 대비 개선 검정이 아니다. 후보 가용성·선박별 시간분포를 보존하지 않으므로 공식 성능 근거로 사용하지 않는다. 진단 수치는 audit.json에 기록했다.
재현: python testB/final/round_013_metric_rescore/rescore.py
