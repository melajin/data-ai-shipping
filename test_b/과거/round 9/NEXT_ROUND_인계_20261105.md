# Round 009 이후 인계서 (NEXT_ROUND_인계_20261105)

**작성 일자**: 2026-11-05 13:26  
**작성 기준**: Round 009 완료 (Task 1 신원 연결 감사 & Task 2 선박 내 대조창 가설 검증 완료)  
**참조 보고서**: [`ROUND009_종합보고서_20261105.md`](ROUND009_종합보고서_20261105.md)

---

## 1. 확정된 새 기준선 (New Ground Truth & Baseline)

1. **사고 선박 개발셋 확정**:
   - **주분석 집합 (Primary Set)**: `task1_linkage_audit_167.csv` 기준 **`LINKED_CLEAN` 95건 / 78척**.
   - **고신뢰 벤치마크셋 (High-Confidence Set)**: 신원 충돌률 0.0%인 **`Tier 0~1 (w0, r<=5km)` 60건 / 55척**.
   - **제외 집합**: 조건 역전 충돌 5건(`LINKED_CONFLICT`), 원천 결측/경합/범위외 미연결 67건은 양성 정답셋에서 공식 배제.
2. **사고 신호의 통계적 판정**:
   - 동일 선박 내 관측행 수 1:1 매칭 통제 시, 단순 이동량 급감(H1), 직선도(H2), 상태 전이(H3)는 모두 **귀무가설 기각 실패 ($p > 0.19$)**.
   - 고신뢰 계층(Tier 0~1)에서 기존 이상점수(`score`)의 사고창 vs 대조창 차이는 **$+0.0170$ ($p = 0.4816$)**으로 완전한 무신호(Zero-signal) 영역임.
   - 선박 단위 최고점 AUC 0.7558은 순수 관측행 수 편향($r = 0.514$)에 의한 착시였으며, 실제 사고 탐지 능력이 아님.

---

## 2. 다음 라운드(Round 10) 금지 및 필수 준수 사항

### 금지 사항 (Strictly Prohibited):
1. **단순 기구학 임계치 모델링 금지**:
   - `len_m`, `bbox_m`, `linearity` 등 1차원 이동량 요약치로 사고를 탐지하려는 시도는 어선의 정상 조업 노이즈로 인해 성립하지 않음을 증명하였으므로 반복하지 않는다.
2. **행 수 미통제 AUC 지표 채택 금지**:
   - 관측행 수(n_rows)를 짝짓지 않은 상태에서 단순 max-pooling 점수로 계산한 선박 분류 AUC를 모델 성능으로 보고하지 않는다.
3. **충돌 5건 및 미연결 67건의 임의 라벨링 금지**:
   - 조건별 신원 불일치가 발생한 5건을 단일 선박 정답으로 단정하여 모델을 학습시키지 않는다.

### 필수 사항 (Mandatory Requirements):
1. **도메인 특화 상태 머신(Fishing State-Machine) 잔차 도입**:
   - 어선의 일상 조업(조업-항해-정박 3상태)을 모형화하고, "정상 조업이어야 할 시간/위치에서의 비정상 정박/표류"라는 상태 전이 잔차 특징을 설계한다.
2. **선박 내 1:1 대조 평가 체계 유지**:
   - 모든 신규 모델/특징은 본 Round 009의 `task2_within_vessel_comparison` 파이프라인(동일 선박 비사고 대조창 1:1 매칭 및 Wilcoxon 검정)을 통과하는지 사전 스크리닝한다.
3. **메모리 계약 준수**:
   - 가용 RAM 사전 점검, 컬럼 필터링 로딩, 배치 실행 원칙을 철저히 승계한다.

---

## 3. 작업 파일 보존 내역
- Task 1 스크립트 및 데이터: [`run_task1_linkage.py`](run_task1_linkage.py), [`task1_linkage_audit_167.csv`](task1_linkage_audit_167.csv), [`task1_linkage_stability_metrics.json`](task1_linkage_stability_metrics.json), [`task1_unlinked_breakdown.json`](task1_unlinked_breakdown.json), [`task1_conflict_audit.json`](task1_conflict_audit.json)
- Task 2 스크립트 및 데이터: [`run_task2_comparison.py`](run_task2_comparison.py), [`task2_within_vessel_comparison.csv`](task2_within_vessel_comparison.csv), [`task2_event_comparison.csv`](task2_event_comparison.csv), [`task2_hypothesis_results.json`](task2_hypothesis_results.json), [`task2_decomposition.json`](task2_decomposition.json)
- 상세 보고서: [`task1_report.md`](task1_report.md), [`task2_report.md`](task2_report.md), [`ROUND009_종합보고서_20261105.md`](ROUND009_종합보고서_20261105.md)
