# final round_001 ~ round_012: 코어 재구성과 순차 규칙의 연쇄 검증

## 0. 코어 재구성의 배경과 운영 기준

2026-11-05 야간, 과거 라운드들이 로더 동등성 검증과 단일 시각 적중률 튜닝에 매몰되어 목적에 부합하는 체계적 진전을 이루지 못했다는 판단에 따라, 실험 체계를 `testB/final/`로 전면 재구성하고 라운드 번호를 round_001부터 새로 시작했다(`testB/final/CORE_ALIGNMENT_REVIEW_20261105.md`, `testB/final/CORE_PLAN.md`).

사용자 지시를 바탕으로 확립된 코어 원칙은 다음과 같다(`testB/final/CORE_ALIGNMENT_REVIEW_20261105.md`, `testB/final/CORE_PLAN.md`).
1. **규칙 순차 적용 관찰**: "특징을 지운다"는 것은 단순한 입력 변수 제거 실험이 아니라, 판정 규칙을 차례로 적용하며 후보가 좁혀지는 과정을 관찰하는 것이다(`testB/final/CORE_ALIGNMENT_REVIEW_20261105.md`).
2. **어업 유형별 맥락과 대기 구분**: 어업 유형(연안복합, 통발, 자망, 채낚기)별 정상 항적 리듬을 먼저 파악하고, 정상적인 대기나 투망을 사고로 오인하지 않도록 공통 규칙과 어업별 추가 규칙을 분리한다(`testB/final/CORE_ALIGNMENT_REVIEW_20261105.md`).
3. **엄격한 내부 주관문**: 새로운 방법이 채택되려면 B0 기준선 대비 Tier 0~1 적중률 +5%p 이상, 선박 단위 paired bootstrap 95% CI 하한 > 0, 전체 100건 비악화, 동일 풀의 무작위 기대를 초과해야 한다(`testB/final/CURRENT_STATUS.md`). 사후적으로 유리한 부분 집합을 골라 주지표를 변경하는 행위는 금지되었다(`testB/final/CURRENT_STATUS.md`).

---

## 1. round_001_20261105

round_001은 과거 결과의 계보와 평가 기반을 재정리하고, 새 final 파이프라인에서 2026년 잠정 연결 82척/100사건(Tier 0~1 55척/60사건) 및 B0 기준선의 성능을 확인·동결하려 했다(`testB/final/round_001_20261105/ROUND001_상세보고서.md`). 평가 조건은 2026년 Train 항적의 잠정 연결 100건(82척)이었다(`testB/final/round_001_20261105/ROUND001_상세보고서.md`).

과거 계보 감사를 전수 완료했다(`testB/final/round_001_20261105/ROUND001_상세보고서.md`). 고정 기준선(B0)의 시간 국소화 성능은 전체 100사건 중 3건 적중(3.0%), 고신뢰 Tier 0~1 60사건 중 2건 적중(3.33%)으로 확인되었다(`testB/final/round_001_20261105/ROUND001_상세보고서.md`, `testB/final/CURRENT_STATUS.md`).

평가 기반과 B0 기준선 수치는 채택되었다(`testB/final/round_001_20261105/ROUND001_상세보고서.md`). 과거의 혼선을 정리하고 비교의 출발점을 명확히 고정했다는 점이 판정 근거였다(`testB/final/round_001_20261105/ROUND001_상세보고서.md`). 코어 재구성을 위해 본 라운드가 진행되었으며, 다음 라운드에서는 과거 경로량과 위치 조건을 결합한 규칙을 시험했다(`testB/final/round_002_20261105/ROUND002_상세보고서.md`). 원본 기록은 `testB/final/round_001_20261105/ROUND001_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 2. round_002_20261105

round_002는 동일 선박(RFID)의 과거 경로량(U: unconditioned)에 반복 방문 위치 조건(C: conditioned, 동일 격자)을 결합하면 정상 조업 구역에서의 감속과 낯선 해역에서의 감속을 구분하여 B0 대비 적중률을 개선할 수 있는지 검증하려 했다(`testB/final/round_002_20261105/ROUND002_상세보고서.md`). 평가 조건은 2026년 잠정 연결 100건/82척 및 Tier 0~1 60건/55척이었다(`testB/final/round_002_20261105/ROUND002_상세보고서.md`).

측정 결과, 위치 조건 C를 적용한 변경안의 $\pm 6$시간 적중률은 전체 2/100, Tier 0~1 0/60에 그쳐 기존 기준선 B0(전체 3/100, Tier 0~1 2/60)보다 오히려 낮았다(`testB/final/CURRENT_STATUS.md`). (참고: 후속 감사에서 R2 execution_001 실행본은 C와 U의 정렬 오류로 무효 판정을 받았다: `testB/final/round_002_20261105/execution_001/INVALID_COMPARISON.md`, `testB/final/round_013_metric_rescore/RESCORE.md`).

위치 조건 C 규칙은 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). 기준선 대비 적중률이 하락하고 Tier 0~1에서 적중이 0건으로 소멸했기 때문이다(`testB/final/CURRENT_STATUS.md`). round_001의 기준선 고정 후 첫 성능 개선 가설로 본 라운드가 진행되었으며, 다음 라운드에서는 4대 어업 유형별 정상 항적 기준선 관찰로 이행했다(`testB/final/round_003_20261105/ROUND003_상세보고서.md`). 원본 기록은 `testB/final/round_002_20261105/ROUND002_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 3. round_003_20261105

round_003은 어업 유형(연안복합, 자망, 통발, 채낚기)에 따라 평상시 기동 양상이 완전히 다르다는 코어 분석에 입각하여, 2026년 Train 전체 항적에서 어업 그룹별 관측 기준선을 확립할 수 있는지 검증하려 했다(`testB/final/round_003_20261105/ROUND003_상세보고서.md`). 평가 조건은 2026년 Train 7,372척 전체의 조업 항적이었다(`testB/final/round_003_20261105/ROUND003_상세보고서.md`).

어업 4개 그룹별 관측 요약과 대표 사례 분석이 완료되었다(`testB/final/round_003_20261105/ROUND003_상세보고서.md`). 통발과 자망의 정박 및 정지 비율, 연안복합의 이동 특성 등 거시적 분포 차이가 정리되었다(`testB/final/round_003_20261105/ROUND003_상세보고서.md`).

본 라운드는 정량 채점 실험이 아닌 기초 행동 관찰 단계로 채택되었다(`testB/final/CURRENT_STATUS.md`). round_002의 기각 이후 어업별 기준선 수립이 선행되어야 한다는 판단에서 진행되었으며, 다음 라운드에서는 이를 바탕으로 경로량 급감(small)의 개시 및 지속 조건에 어업 기준을 주입하는 실험을 진행했다(`testB/final/round_004_20261105/ROUND004_상세보고서.md`). 원본 기록은 `testB/final/round_003_20261105/ROUND003_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 4. round_004_20261105

round_004는 시간별 경로량 급감(small)의 개시 시점과 지속 조건에 어업별 기준(G)을 적용하면, 정상 조업 중 감속을 배제하고 사고 발생 시점을 분리할 수 있는지 검증하려 했다(`testB/final/round_004_20261105/ROUND004_상세보고서.md`). 평가 조건은 2026 dev 82척/100사건 및 Tier 0~1 60사건이었다(`testB/final/round_004_20261105/ROUND004_상세보고서.md`).

측정 결과, 변경안 G의 $\pm 6$시간 적중률은 전체 1/100, Tier 0~1 1/60에 머물렀다(`testB/final/CURRENT_STATUS.md`). 기준선 B0(3/100, 2/60)보다 낮은 결과였다(`testB/final/CURRENT_STATUS.md`).

개시·지속 조건 및 어업 기준 G는 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). round_003의 어업 기준선을 규칙에 적용하려던 시도였으나 적중률 향상으로 이어지지 않았기 때문에, 다음 라운드에서는 개시 단계에서의 후보 손실 원인을 추적하는 S1 분석으로 전환했다(`testB/final/round_005_20261106/ROUND005_상세보고서.md`). 원본 기록은 `testB/final/round_004_20261105/ROUND004_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 5. round_005_20261106

round_005는 round_004의 엄격한 지속 조건으로 인해 정작 사고 시점의 후보가 조기 탈락하는 후보 손실 문제를 해결하기 위해, 개시 후보 자체(S1)를 평가하여 적중률을 회복할 수 있는지 검증하려 했다(`testB/final/round_005_20261106/ROUND005_상세보고서.md`). 평가 조건은 2026 dev 82척/100사건 및 Tier 0~1 60사건이었다(`testB/final/round_005_20261106/ROUND005_상세보고서.md`).

측정 결과, 개시 후보 S1의 적중률은 전체 2/100, Tier 0~1 2/60에 그쳤다(`testB/final/CURRENT_STATUS.md`). B0(3/100, 2/60) 대비 개선을 달성하지 못했다(`testB/final/CURRENT_STATUS.md`).

개시 후보 S1 규칙은 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). 개시 시점만으로는 평상시 정상 투망 개시와 구별되지 않아 오탐이 다수 발생했기 때문이다(`testB/final/CURRENT_STATUS.md`). round_004의 후보 손실을 보완하려던 시도에서 본 라운드가 나왔으며, 다음 라운드에서는 단일 시점이 아닌 진행 중인 small run의 길이를 평가하는 방향으로 전환했다(`testB/final/round_006_20261106/ROUND006_상세보고서.md`). 원본 기록은 `testB/final/round_005_20261106/ROUND005_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 6. round_006_20261106

round_006은 진행 중인 저속/소이동 연속 구간(small run)의 길이에 대해 선박 자기 이력 및 어업별 이력을 대조하여, 평소보다 비정상적으로 길게 이어지는 run을 사고 징후로 포착할 수 있는지 검증하려 했다(`testB/final/round_006_20261106/ROUND006_상세보고서.md`). 평가 조건은 2026 dev 82척/100사건 및 Tier 0~1 60사건이었다(`testB/final/round_006_20261106/ROUND006_상세보고서.md`).

측정 결과, 진행 중 small run 기반 변경안 G의 적중률은 전체 1/100, Tier 0~1 1/60으로 기준선 B0(3/100, 2/60)보다 낮았다(`testB/final/CURRENT_STATUS.md`).

진행 중 small run 규칙 G는 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). 기구학 요약치 기반의 run 지속성 역시 정상 대기 및 조류 표류와 사고를 구별하지 못했다(`testB/final/CURRENT_STATUS.md`). 축약된 지표의 한계가 명확해짐에 따라, 다음 라운드에서는 요약치를 배제하고 원본 WKT 부분선 기하를 직접 열어보는 관찰로 전환했다(`testB/final/round_007_20261106/ROUND007_상세보고서.md`). 원본 기록은 `testB/final/round_006_20261106/ROUND006_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 7. round_007_20261106

round_007은 축약된 `len_m`이나 `bbox_m` 대신 22개 대표 관측행의 원본 WKT MultiLineString을 직접 추출하여, 부분선 내부의 선분 구성, 굴곡도, 점별 분포 등 기하학적 형상에 사고 특유의 징후가 존재하는지 검증하려 했다(`testB/final/round_007_20261106/ROUND007_상세보고서.md`). 조건은 22개 표본 관측행의 원시 WKT 추출이었다(`testB/final/round_007_20261106/ROUND007_상세보고서.md`).

측정 결과, 부분선 내부의 좌표 수, 선분 구성, 형태학적 특성의 추출 및 관찰이 완료되었다(`testB/final/round_007_20261106/ROUND007_상세보고서.md`).

본 라운드는 성능 지표 산출이 아닌 기술적 형상 관찰 단계로 채택되었다(`testB/final/CURRENT_STATUS.md`). round_006의 실패 이후 원시 궤적의 기하학적 형태를 확인하기 위해 진행되었으며, 다음 라운드에서는 이 부분선 형상 특징을 전수로 추출하여 정량 평가를 진행했다(`testB/final/round_008_20261106/ROUND008_상세보고서.md`). 원본 기록은 `testB/final/round_007_20261106/ROUND007_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 8. round_008_20261106

round_008은 round_007에서 확인된 부분선 내부 형상 특징(직선도, 굴곡도, 좌표 밀도)을 전체 데이터에서 전수 추출하고, 자기 과거 이력 대비 이탈도(G)를 평가하여 사고 시각 적중률을 개선할 수 있는지 검증하려 했다(`testB/final/round_008_20261106/ROUND008_상세보고서.md`). 평가 조건은 2026 dev 82척/100사건 및 Tier 0~1 60사건이었다(`testB/final/round_008_20261106/ROUND008_상세보고서.md`).

측정 결과, 부분선 형상 이력 대조안 G의 적중률은 전체 1/100, Tier 0~1 0/60으로 B0(3/100, 2/60) 대비 개선되지 않았다(`testB/final/CURRENT_STATUS.md`).

부분선 형상 이력 규칙 G는 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). 1시간 동안 집계된 MultiLineString 형상 역시 조업 행동의 복잡성으로 인해 사고와의 분별력이 없다는 점이 확인되었다(`testB/final/CURRENT_STATUS.md`). round_007의 관찰을 전체 정량 평가로 확장한 결과 기각되었기 때문에, 다음 라운드에서는 정지 후 상태 전이 패턴을 시험했다(`testB/final/round_009_20261106/ROUND009_상세보고서.md`). 원본 기록은 `testB/final/round_008_20261106/ROUND008_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 9. round_009_20261106

round_009는 사고 선박이 바다에 멈춘 뒤 구조선에 예인되거나 자력으로 조업을 중단하고 복귀한다는 가설에 따라, small 상태가 2회 이상 지속된 후 비-small 상태로 전환되는 시점(small-small-non-small 전이 G)을 포착하면 사고 시각을 특정할 수 있는지 검증하려 했다(`testB/final/round_009_20261106/ROUND009_상세보고서.md`). 평가 조건은 2026 dev 82척/100사건 및 Tier 0~1 60사건이었다(`testB/final/round_009_20261106/ROUND009_상세보고서.md`).

측정 결과, 상태 전이 규칙 G의 적중률은 전체 2/100, Tier 0~1 2/60으로 B0(3/100, 2/60)보다 낮았다(`testB/final/CURRENT_STATUS.md`).

상태 전이 규칙 G는 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). 어선의 정상 투망 후 이동 재개 패턴과 사고 후 예인 패턴이 기하학적으로 구별되지 않았기 때문이다(`testB/final/CURRENT_STATUS.md`). 상태 전이 가설이 기각되었기 때문에, 다음 라운드에서는 공간적 이탈 신호인 자기 과거 활동 중심점 거리의 가용성을 점검했다(`testB/final/round_010_20261106/ROUND010_상세보고서.md`). 원본 기록은 `testB/final/round_009_20261106/ROUND009_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 10. round_010_20261106

round_010은 선박의 과거 활동 영역 중심점으로부터 현재 관측 중심점까지의 대권거리를 공간적 이상치 대리 변수로 산출하고, 해당 지표의 데이터 가용성을 확인하려 했다(`testB/final/round_010_20261106/ROUND010_상세보고서.md`). 평가 조건은 2026 dev 항적 데이터였다(`testB/final/round_010_20261106/ROUND010_상세보고서.md`).

측정 결과, 자기 과거 중심거리의 산출 및 가용성 검증이 정상 완료되었다(`testB/final/round_010_20261106/ROUND010_상세보고서.md`).

가용성 점검 산출물은 채택되었다(`testB/final/CURRENT_STATUS.md`). 성능 실험이 아닌 기술적 준비 단계였으며, 다음 라운드에서는 이 거리 지표를 CDF로 모형화하여 정량 평가를 진행했다(`testB/final/round_011_20261106/ROUND011_상세보고서.md`). 원본 기록은 `testB/final/round_010_20261106/ROUND010_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 11. round_011_20261106

round_011은 round_010에서 확보된 자기 과거 중심거리에 대해 단측 누적분포함수(CDF)를 적용한 이탈도(G)가 B0 기준선 대비 시간 국소화 성능을 개선하는지 검증하려 했다(`testB/final/round_011_20261106/ROUND011_상세보고서.md`). 평가 조건은 2026 dev 82척/100사건 및 Tier 0~1 60사건이었다(`testB/final/round_011_20261106/ROUND011_상세보고서.md`).

측정 결과, 과거 거리 CDF 규칙 G의 적중률은 전체 2/100, Tier 0~1 1/60에 머물렀다(`testB/final/CURRENT_STATUS.md`).

과거 거리 CDF 규칙 G는 개선 미달로 기각되었다(`testB/final/CURRENT_STATUS.md`). 어선의 조업지 이동이나 원거리 출항이 공간적 이상치로 채점되어 사고와 무관한 시각이 최고점으로 선택되었기 때문이다(`testB/final/CURRENT_STATUS.md`). 11개 회차 동안 단일 규칙 개선이 모두 실패함에 따라, 다음 라운드에서는 회차 간 층별·교집합 진단을 수행했다(`testB/final/round_012_20261106/ROUND012_상세보고서.md`). 원본 기록은 `testB/final/round_011_20261106/ROUND011_상세보고서.md`와 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 12. round_012_20261106

round_012는 회차 1~11의 저장 결과를 층별로 진단하고, 여러 규칙의 적중 교집합 및 합집합을 분석하여 사후적 앙상블을 구축할 수 있는지 검증하려 했다(`testB/final/round_012_20261106/ROUND012_상세보고서.md`). 평가 조건은 회차 1~11의 전체 저장 산출물이었다(`testB/final/round_012_20261106/ROUND012_상세보고서.md`).

측정 결과, 각 회차의 서로 다른 변경안들이 맞힌 사건들의 사후 합집합을 취하면 적중 수가 표면상 늘어나는 것처럼 보였으나, 정작 어떤 선박에 어떤 규칙을 우선 적용해야 하는지 사전에 결정할 수 있는 독립적 분기 기준이 전무했다(`testB/final/round_012_20261106/FINAL_DECISION.md`). 두 중간관리자의 반박 검토 결과, 사후 적중 합집합만으로 임의 통합을 실행 가능한 예측기로 채택할 통계적 근거가 없다는 점이 규명되었다(`testB/final/round_012_20261106/FINAL_DECISION.md`, `testB/final/CORE_PLAN.md`).

임의 앙상블 통합안은 기각되었다(`testB/final/round_012_20261106/FINAL_DECISION.md`). 대신 저장된 고정 기준선 B0의 변경 없는 사본과 평가 결과를 한곳에 정리한 [기준선 검토 패킷](round_012_20261106/review_packet_001/README.md)을 구성하여 동결했다(`testB/final/round_012_20261106/FINAL_DECISION.md`, `testB/final/CURRENT_STATUS.md`). 12개 회차의 누적 실패 분석 이후, 다음 라운드(round_013)에서는 평가 계약을 전면 복원하고 7대 가설을 병렬 검증하는 대규모 진단으로 전환했다(`testB/final/round_013_design_20261106_060012/ROUND013_PLAN.md`). 원본 기록은 `testB/final/round_012_20261106/ROUND012_상세보고서.md`와 `testB/final/round_012_20261106/FINAL_DECISION.md`에 있다.
