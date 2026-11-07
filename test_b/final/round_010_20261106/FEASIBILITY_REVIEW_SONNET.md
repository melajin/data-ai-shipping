# Round10 가용성 검토 + 점수 설계 제안 — Sonnet

## 1. 가용성 수치 경량 재확인 (신규 계산 없음)

`probe_outputs/actual_001/position_ledger.parquet`(99,677행,22열)을 직접 열람: `coordinate_valid`=99,677, `own_distance_eligible`=96,976, `peer_eligible`=94,525 — summary.json·ROUND010_상세보고서와 전수 일치. 열 스키마(`nearest_distance_m`,`own_ref_n`,`own_ref_dates`,`peer_eligible_n` 등)도 CONTRACT.md 정의와 일치함을 확인했다. root_validation_001은 이미 사고라벨 읽기 전 동결·82척/12질의 일치를 거쳤으므로 이번 리뷰는 재검산하지 않고 그 결과를 그대로 신뢰 입력으로 쓴다(지시대로 "no actual new scoring during review" 준수).

이번 단계가 **가용성 확인이지 성능이 아니라는** 점, Tier01 53/60·peer보유 79/82가 사전기준(50/60, 6척)을 넘었을 뿐 제출 성능 증거가 아니라는 점에 동의한다. 내가 R9에서 주장했던 "흔한 자리=오탐 자동억제"는 이미 총책임자가 미채택 처리했고, 이번 설계에도 그 주장을 다시 넣지 않는다 — 평균중심은 실제항로·항만이 아니며 반복위치가 정상이라는 정답도 없다.

## 2. 제안: ONE 고정 B0/S/G 최근접거리 점수 실험

**격자 미사용 justification**: 0.05도 셀을 재사용하지 않는다. Round10이 연속 거리를 택한 이유가 "임의 셀 경계효과를 추가하지 않기 위해서"였으므로(보고서 §"채택한 접근"), 같은 이유로 점수 단계에서도 격자를 넣지 않고 `nearest_distance_m`을 그대로, 그리고 그 값의 **한쪽꼬리(one-tail) 순위통계**로만 쓴다 — 거리는 "0에 가까울수록 반복, 클수록 낯섦"이라는 방향이 이미 있어 R6/R8처럼 양쪽꼬리를 쓸 이유가 없다.

### 공통 규칙 (어업 무관)
- **자기희귀도**: 시각 t의 `nearest_distance_m`을, 같은 RFID의 **[t−720,t) 과거 중 `own_distance_eligible=True`였던 행들의 `nearest_distance_m` 값 집합**(이미 position_ledger에 존재, 재계산 없음)과 비교한다. p = (과거값 < 현재값 개수 + 0.5×동률개수) / n. self_rarity = p (한쪽꼬리: 현재거리가 과거 대부분보다 크면 p→1, 즉 "평소보다 훨씬 낯선 곳"일수록 높은 점수). 과거 참조 자체는 CONTRACT의 24/3 조건을 그대로 쓰고(새 문턱 아님), 이번엔 추가로 "그 과거행 자신도 own_distance_eligible"이어야 비교 모집단에 넣는다(자기참조 거리값이 정의된 행만 분포에 포함).
- **최소 참조**: self 모집단 n<24 또는 날짜<3이면 defer(= R10의 own_status/own_reason 그대로 재사용, 새 상태 아님).

### 어업 추가 규칙 (G)
- 동일 단일어업 ≥5 적격 동료(R10의 `peer_eligible`/`peer_eligible_n` 그대로 재사용)가 있으면, **이 배의 현재 `nearest_distance_m` 값을 각 적격 동료 자신의 과거 거리분포에 동일한 one-tail CDF로 평가**한 뒤 선박 균등평균한다(R6/R8이 쓴 "자기값을 동료 각자의 과거분포에 비교 후 평균" 구조를 그대로 재사용 — 동료의 현재 관측 불필요, CONTRACT와 일치). 동료 참조는 peer 자신의 own-window 거리값 집합이며 새 통계식이 아니라 self_rarity와 동일한 CDF 함수를 피호출자만 바꿔 재사용한다.
- 동료 모집단 부족(5미만)이면 defer, singleton(채낚기연승낚시)은 자동 defer — R10에서 이미 계산된 `peer_status/peer_reason` 그대로.

### B0/S/G 풀·순위·폴백·예산 (R4~R9와 동일 틀)
- B0 = 기존 숫자장부의 유효 기하+유한 legacy score 행 전체(= s0, 신규 아님). legacy score 내림차순, ts 오름차순, ordinal 오름차순.
- S = `own_distance_eligible=True` 행. self_rarity 내림차순 → legacy 내림차순 → ts → ordinal. 빈 풀이면 B0로 명시 fallback.
- G = `peer_eligible=True` 행. self_rarity 내림차순(1순위) → peer_rarity 내림차순(2순위, 동률에서만 개입) → legacy → ts → ordinal. 빈 풀이면 S의 실제 해결 풀/순위로 복귀.
- cap = min(4, G 실제 풀 크기), B0/S/G 동일 적용. 동일 RFID의 연결 사건은 같은 예측목록 공유. top1 = 같은 top4의 rank1.

### 평가 (변경 없음)
전체100/82, Tier01=60/55, ±6h 포함, RFID paired bootstrap(B=4000, seed=20261105), 방법·코호트별 실제풀 random 기대 분리, 기존 4관문(Tier01 G−B0 top1≥+5%p / CI하한>0 / 전체100 비악화 / Tier01 G 관측률>동일풀 random기대) 그대로. 사건창 후보부재와 선박전체 가용성 부재를 분리 보고(R9 교훈 반영). 사고정보는 예측 동결 후에만 읽는다.

## 3. 정직성 제약 (사전 선언)

`cen_lon/cen_lat`는 시간행의 **평균 중심**이며 실제 부분선·항로가 아니다. `nearest_distance_m`이 작다고 "정상 대기/항만"이라 부르지 않고, 크다고 "사고 발생"이나 "신규 조업지가 아니다"라고 단정하지 않는다. "자동 위양성 억제" 주장은 하지 않는다(root가 이미 R9에서 이를 명시 거부). 이동량(R4/R6/R9)·형상(R8)과 위치(이 제안)는 모두 **같은 다중 부분선 평균이라는 공통 입력 제약**을 공유하므로 서로 "완전히 독립"이라고 과장하지 않는다.

## 4. 5개 코어 점검 + 기술/학습 목표

1. **코어 해당**: "기존 선로·반복 공간과 현재 관측의 관계"를 위치 전용 축으로 다룬다. 입력이 평균중심이라는 대리성을 계속 명시.
2. **비코어 명시**: small-run 계열(개시/지속/재개) 재탐색 아님, 항로/항만/실제속력/통신상태 미구현.
3. **기술목표**: position_ledger의 `nearest_distance_m`만으로 동일예산 B0/S/G를 산출. **학습목표**: 거리 대리값의 자기/동료 희귀도가 적중률에 기여하는지, 반복위치와 정상상태의 차이를 분리 설명.
4. **입력가용성**: R10 probe_outputs/actual_001 position_ledger.parquet(해시 c3943c95...로 root 동결) 재사용, 신규 추출 없음. 정상/대기/항만/실제시간대 미확인 유지.
5. **다음관문**: 기존 4관문 전부 충족 여부로 판정, 미통과 시 거리정의·창·동료수를 사후 조정하지 않는다.

## 5. 중단 기준

4관문 중 하나라도 미달이면: (a) 거리 임계값·과거창(720h)·24/3/5 조건을 바꾸지 않는다, (b) "위치가 통하지 않았다"를 "위치 전체가 무의미하다"로 과장하지 않고 이번 특정 one-tail self/peer 설계의 실패로 범위를 한정한다, (c) 다음은 위치 대리값 계열 전체를 보류하고 R9 FINAL_RESULT_RECONCILIATION이 열어둔 다른 축(예: 사건별 교집합/연결신뢰도 분석)으로 넘어간다.

## 결론

가용성 결과를 신뢰 입력으로 채택하고, 격자 없이 연속 `nearest_distance_m`의 one-tail 자기/동료 희귀도만으로 기존 B0/S/G 틀에 맞춘 최소 설계 1건을 제안한다. 신규 추출·임계값탐색·모델 없음.
