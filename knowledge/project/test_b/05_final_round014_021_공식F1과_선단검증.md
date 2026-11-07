# final round_014 ~ round_021: 공식 F1 실측과 전 선단 검증

## 1. round_014_visual_audit

round_014는 Test B 평가 대상인 2025년 100척 전원의 항적 궤적을 선박별 시각 패널로 전수 렌더링하여 데이터의 공간적 왜곡, 비정상 좌표, 중심점 요약의 기하학적 형태를 시각적으로 전수 검수하려 했다(`testB/final/round_014_visual_audit/verification.json`, `testB/final/round_014_visual_audit/summary.json`). 평가 조건은 2025년 Test B 100척 46,705행의 WKT 원시 궤적이었다(`testB/final/round_014_visual_audit/summary.json`).

측정 결과, 100척 전원(100/100)에 대해 총 100장의 개별 패널 이미지(PNG)와 통합 검수 문서(`testb_100_panels.pdf`, 총 101쪽), SQLite 기하 캐시 생성이 완료되었다(`testB/final/round_014_visual_audit/summary.json`, `testB/final/round_014_visual_audit/verification.json`). 중심점들이 고립되어 나타나는 형태, 항구 주변의 군집, 관측이 1행에 불과한 희소 선박 등의 물리적 분포가 확인되었다(`testB/final/round_014_visual_audit/summary.json`).

시각 검수 패널 산출물은 정상 검수 증거로 채택되었다(`testB/final/round_014_visual_audit/verification.json`). 수치 요약치 이면에 존재하는 실제 궤적의 형태를 확인하기 위해 진행되었으며, 다음 라운드에서는 주최 측 공식 규칙을 적용한 F1을 최초로 산출했다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 원본 기록은 `testB/final/round_014_visual_audit/summary.json`과 `testB/final/round_014_visual_audit/verification.json`에 있다.

---

## 2. round_015_official_f1_20261106

round_015는 주최 측 질의응답을 통해 확정된 공식 평가 규칙(선박 단위 F1, 사고시각 오차 $\pm 6$시간 허용, 초과 시 0점 처리, 미사고 선박 전 칸 공란)을 엄격히 적용했을 때 고정 기준선 B0의 실제 공식 F1을 측정하고, 공란 판정 임계값 조정으로 F1이 개선되는지 검증하려 했다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 평가 조건은 2026년 dev 82척 99,677행이었으며 모델 학습은 0회였다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 허용창을 벗어난 예측은 맞히지 못했으므로 위양성(FP)이자 위음성(FN)으로 동시에 집계했다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`).

측정 결과, 고정 기준선 B0의 공식 F1은 정확히 **0.0366**이었다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 82척 평가 집단 기준 정밀도 0.0366, 재현율 0.0366, TP 3, FP 79, FN 79였다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 공란 판정 임계값을 변화시키며 민감도를 실측한 결과, 임계값을 0.50에서 0.54까지 올릴 때는 TP 3, FP 79, FN 79로 F1 0.0366이 유지되었으나, 0.55에서는 TP 2, FP 73, FN 80으로 F1이 0.0267로 떨어졌고, 0.60에서는 TP 1, FP 52, FN 81로 F1이 0.0172로 하락했으며, 0.65 이상에서는 TP가 0건이 되어 F1이 0.0000이 되었다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 맞힌 3척의 이상점수가 집단 중위값(0.5488)보다 낮았기 때문에, 이상점수가 높은 선박만 남기는 방식은 맞힌 것부터 버리는 결과를 초래했다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 미사고 선박이 섞인 100척 집단에 같은 제출률을 투영하면 F1은 0.0067~0.0330으로 더욱 하락했다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`).

공식 F1 실측값 0.0366은 확정 채택되었으나, 공란 판정 임계값을 올려 F1을 개선하려는 가설은 기각되었다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 점수 순위와 시간 적중 간의 상관관계가 결여되어 임계값 상향이 성능 하락으로 직결되었기 때문이다(`testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`). 공식 평가지표를 확인하기 위해 본 평가가 진행되었으며, 다음 라운드에서는 사고 시각과 파생 상태 간의 상관성을 직접 검증했다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 원본 기록은 `testB/final/round_015_official_f1_20261106/ROUND015_공식F1_보고서_20261106.md`에 있다.

---

## 3. round_016_state_signal_20261106

round_016은 사고 100건 중 기관손상 34건, 부유물감김 11건 등 추진·조타 상실 유형이 과반(56건)을 차지하므로 추진을 잃은 어선이 바다에 멈춰 서서 사고 시각의 상태가 `해상정지`로 분류될 확률이 평소보다 높을 것이라는 가설을 검증하려 했다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 만약 이 가설이 성립하면 후보 시간을 `해상정지` 구간으로 축소할 수 있다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 평가 조건은 2026 dev 82척 99,677행 및 100건 사고였다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`).

측정 결과, 사고 시각 $\pm 6$시간 창 안에 `해상정지` 관측이 존재하는 비율은 15.0%(15/100건)에 불과했다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 반면 같은 선박·같은 창 길이에서 평상시 무작위로 관측을 뽑았을 때의 기대치는 **26.0%**였다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 사고 시각에 `해상정지`가 평소보다 오히려 덜 나타났으며, 관측 방향이 가설과 정반대였다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`).

"사고 시각 = 해상정지" 가설은 전면 기각되었다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 어선은 평상시에도 투망 대기, 조류 표류 등으로 수시로 멈추며, 1시간 단위 기하 요약의 단순 상태 라벨 하나로는 사고 정지와 일상 정지를 가를 수 없다는 점이 판정 근거였다(`testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`). 후보 공간 축소를 위해 본 가설이 시험되었으나 기각되었으며, 다음 라운드에서는 82척을 넘어선 전체 7,372척 규모의 대규모 음성 풀 추출을 진행했다(`testB/final/CURRENT_STATUS.md`). 원본 기록은 `testB/final/round_016_state_signal_20261106/ROUND016_상태신호_기각_20261106.md`에 있다.

---

## 4. round_017_fleet_negatives_20261106

round_017은 평가 집단이 82척 사고 연결 선박에 국한되어 오경보로 인한 FP를 제대로 측정할 수 없다는 한계를 해결하기 위해, 2026년 Train 7,372척 전체 선단에서 시간대별 항적 데이터를 전수 추출하여 음성 풀을 구성하려 했다(`testB/final/CURRENT_STATUS.md`). 조건은 2026년 Train 6개월 3,887,065행 전체였다(`testB/final/CURRENT_STATUS.md`).

측정 결과, 7,372척 전원에 대한 시간대별 기하 요약 데이터(3,887,065행) 추출이 완료되었으며, 6개월 분할 Parquet 파일(`hourly_01.parquet` ~ `hourly_06.parquet`)로 저장되었다(`testB/final/round_017_fleet_negatives_20261106/execution_001/extract_summary.json`).

전 선단 음성 데이터 추출은 채택되었다(`testB/final/CURRENT_STATUS.md`). 대규모 음성 모집단을 확보하기 위해 본 라운드가 진행되었으며, 다음 라운드에서는 82개 제외선박 교차검증 릿지 모형의 성능을 평가했다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`). 원본 기록은 `testB/final/round_017_fleet_negatives_20261106/execution_001/extract_summary.json`과 `testB/final/CURRENT_STATUS.md`에 있다.

---

## 5. round_018_pointwise_loov_20261106

round_018은 부분선 길이, 경계상자 크기, 좌표 수의 로그 변환 및 2차 기하 특징 9개에 대해 선박별 Leave-One-Out(LOOV) 균형 릿지 로지스틱 회귀($\lambda=0.01$)를 적용했을 때, 사고 시각 top-1 적중 수가 기준선 B0 대비 증가하는지 사전 고정 실험으로 검증하려 했다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`). 조건은 2026년 잠정 연결 82척(100사건, 다중사고 11척)이었으며, 82회 반복에서 평가 대상 선박의 모든 관측과 사고를 학습에서 철저히 제외했다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`).

측정 결과, $\pm 6$시간 top-1 적중 수는 3/82(3.6585%)로 고정 기준선(3/82, 3.6585%)과 동일했다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`). 선박별 최소 절대오차 중앙값은 760.0시간이었으나, 우연모델 단측 $p$값은 0.2755, 기준선 최악 적중 겹침 단측 $p$값은 1.0이었다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`).

점별 LOOV 모델은 기각되었다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`). 기준선 대비 추가 적중이 0척이었고 우연 모델 대비 유의성을 확보하지 못했기 때문이다(`testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`). 기하 특징 기반 지도학습의 한계를 실측하기 위해 본 라운드가 진행되었으며, 다음 라운드에서는 7,372척 전체 선단에 대한 frozen baseline 점수화 및 선박 분별력을 평가했다(`testB/final/round_019_vessel_discrimination_20261106/ROUND019_보고서.md`). 원본 기록은 `testB/final/round_018_pointwise_loov_20261106/ROUND018_report.md`에 있다.

---

## 6. round_019_vessel_discrimination_20261106

round_019는 2026년 Train 7,372척(3,887,065행) 전체에 대해 고정 기준선(frozen baseline) 점수를 산출하고, 사고 연결 82척과 나머지 비연결 선박 7,290척 간의 선박 수준 분별력(ROC AUC)을 실측하려 했다(`testB/final/round_019_vessel_discrimination_20261106/ROUND019_보고서.md`, `docs/fishing_execution_plan.md`).

측정 결과, 전체 7,372척의 점수화가 완료되었다(`docs/fishing_execution_plan.md`). 선박별 최고 이상의 양성 매칭 ROC AUC는 **0.5756**, 부분선 중심점 반경 AUC는 **0.6073**으로 나타났다(`docs/fishing_execution_plan.md`).

전 선단 기준 분별력 실측은 채택되었다(`docs/fishing_execution_plan.md`). 7,290척의 대규모 비교군을 투입했을 때 이상점수의 선박 선별력이 0.58 수준으로 매우 약하다는 점이 확증되었다(`docs/fishing_execution_plan.md`). 다음 라운드에서는 관측 없는 시간까지 포함한 구간 합산 선택 실험으로 이행했다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`). 원본 기록은 `testB/final/round_019_vessel_discrimination_20261106/ROUND019_보고서.md`와 `docs/fishing_execution_plan.md`에 있다.

---

## 7. round_020_missing_hour_time_20261106

round_020은 관측이 없는 내부 시간(미관측 193,707시간)까지 포함한 전체 정수시간 후보(293,384시간)에 대해, round_018에서 학습된 로짓을 바탕으로 $\pm 6$시간 구간 합산 점수를 통해 최고점을 선택하면 적중 수가 증가하는지 검증하려 했다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`). 평가 조건은 2026 잠정 연결 82척/100사건이었으며, 사용자의 지시에 따라 평가 전에 완화된 기준(5척 이상 개선 후보, 4척 보류, 3척 이하 기각)을 사전 고정했다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`).

측정 결과, 선박별 $\pm 6$시간 top-1 적중 수는 **3/82(3.6585%)**로 기준선과 동일했다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`). 최소 절대오차 중앙값은 573.5시간으로 감소했으나 추가 적중 수는 0척이었다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`). 관측 없는 후보 193,707시간을 추가했음에도 실제 선택된 시각은 82척 전원에서 관측이 존재하는 시각이었다(81척에서 시각 변경 발생)(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`).

구간 합산 및 미관측 후보 확장 규칙은 기각되었다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`). 완화된 개선 기준(5척) 및 보류 기준(4척)을 충족하지 못하고 적중 수가 3척에 머물렀기 때문이다(`testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`). 관측 없는 시간의 사고 가능성을 다루기 위해 본 실험이 진행되었으나 기각되었으며, 다음 라운드에서는 7,372척 전 선단 대상의 내부 F1 산출과 최종 시각 진단으로 진입했다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`, `testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`). 원본 기록은 `testB/final/round_020_missing_hour_time_20261106/ROUND020_report.md`에 있다.

---

## 8. round_021_internal_f1_judgement_20261106 및 round_021_timing_diagnosis_20261106

round_021은 7,372척 전체를 대상으로 기존 대표 규칙(`최고 이상점수 ≥ 0.75`)을 적용하여 선박 선정 및 시각 포함 사건 내부 F1을 확정하고(judgement), 기존 최고점(B), 연속 관측 구간 중앙(T), 공백 직전 중앙(G) 세 가지 시각 선택 규칙을 개발/검증 분할에서 대조하여 시각 적중 개선이 가능한지 진단하려 했다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`, `testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`). 조건은 7,372척(3,887,065행) 전 선단이었으며, SHA-256 고정 순서로 개발 3,686척(사고 50척)과 검증 3,686척(사고 32척)으로 분할했다(`testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`). 나머지 7,290척은 미연결 비교군으로 F1 계산에서 음성으로 가정했다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`).

측정 결과, `최고 이상점수 ≥ 0.75` 규칙은 183척을 선별했다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`). 183척 중 잠정 사고 연결 선박은 7척이 포함되어 **선박 선정 내부 F1은 0.05283(5.283%)**이었다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`). 그러나 그 7척에서 선택된 시각 중 사고시각 $\pm 6$시간 안에 들어온 경우는 0건이어서, **시각 포함 사건 내부 F1은 0.00000(0%)**이었다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`).

시각 진단 결과, 잠정 연결 82척 중 79척에서 사고창 안에 이상점수가 존재했음에도 전체 기간 최고점은 사고창 밖 다른 시각에 위치해 있었다(`testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`). 동점 선택으로 인해 사고를 놓친 사례는 0척이었다(`testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`). 세 규칙(B, T, G) 비교에서 개발 선박에서 기존 최고점 B보다 적중 수를 개선한 대안이 없었다(`testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`).

대안 시각 규칙 T와 G는 개선 미달로 기각되었고, 고정 기준선 B0 방식이 최종 유지되었다(`testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`). 전체 선단 내부 F1 산출 및 진단 보고서는 완료 채택되었다(`testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`). 이로써 Test B의 모든 실험 라운드가 종결되었으며, 연구 결과는 재현 가능한 실행 패키지(`deliverables/testb_system_20261106/`)와 최종 제출 문서로 패키징되었다(`deliverables/testb_system_20261106/README.md`). 원본 기록은 `testB/final/round_021_internal_f1_judgement_20261106/ROUND021_판단근거와_내부F1.md`와 `testB/final/round_021_timing_diagnosis_20261106/ROUND021_report.md`에 있다.
