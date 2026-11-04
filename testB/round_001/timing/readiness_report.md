# Test B 시각추정 준비 — Round 001

작성 시각: 2026-11-05T02:41:34.095426+09:00

## 현재 결과

100척 비교표에는 기존 제출 CSV에서 읽은 A만 `inherited_existing_baseline`으로 기록했다. 이 worker는 A를 재계산하지 않았고, 이미 승인된 재현 결과(100척, 비교 8열 불일치 0)를 계승했다. B와 C는 모두 계산하지 않았으며 각 행에 이유를 기록했다. 이 상태는 사고 확정이나 미사고 판정이 아니다.

2025 Test B 캐시는 100척·82,626행·16열로 기록돼 있다. 2026 학습 항적과 사고 167건은 별도 데이터 역할이며, 기존 점수 캐시는 2026 점수를 포함하지 않는다. 기존 점수는 `nanmean(s_zone, s_change, s_gap)`로, 높은 값이 더 이상한 쪽인 탐색 지표이며 사고 확률이 아니다. 구역/공백 정규화는 학습참조 분포를 사용했고 구역 과거 미방문 거리는 고정 20km 스케일이다. 참조 라벨 집합 7,372척, 대상 ID 겹침 95척은 집합 중복이며 실제 격자 기여나 점수 희석을 입증하지 않는다.

## 입력·분할 설계

`input_split_manifest.json`에는 필요한 계산 열, 단위와 시간 구간, 방향, 원본 계보, 참조집합과 적합범위를 기록했다. 반복 후보가 있는 사건과 선박은 사건–선박 이분 그래프의 연결요소로 묶어 같은 분할에 둔다. 전처리/참조 지도 적합은 train, 선택·임계는 dev, 보정이 도입되면 별도 calibration, 최종 평가는 독립 event-vessel 그룹으로 분리한다. 평가 기간 예측을 먼저 고정한 뒤 사고 기록과 대조한다. 실제 배정은 `pending`이다.

사고자료 개발 사용 허용, 확정 신원, 신뢰할 양·음성 근거, 표본 분할 가능성은 확인되지 않았다. 따라서 임계값, comparator, 구간 최대 간격과 지속 최소 시간/행수는 선택하지 않았다. 공식 F1 수식과 6시간 경계도 미확정이다.

## A/B/C 인터페이스와 검증

`timing_interface.py` is a pure A/B/C selection skeleton with explicit parameters. A is the first maximum in original input order (`idxmax` semantics); time sorting is used only for B/C segment search. Hourly `max_gap_hours` must be in (0,1], so no missing hourly bin can be bridged. NaN splits a segment. Identical duplicate scores preserve source IDs and persistence counts unique timestamps; conflicting scores, including missing/valid conflicts, return `data_conflict / duplicate_timestamp_scores_conflict` with A/B/C blank. C=B on persistence pass. The positive score floor has unresolved accident-decision meaning. Checks are synthetic only.

The current interface passed 14 synthetic checks with actual exit code 0: the prior eight checks plus rejection of max_gap_hours >1, split at timestamps 0/2, acceptance of identical-score duplicates, rejection of conflicting duplicates with blank A/B/C, equivalent missing duplicates, and missing/valid conflict. Logs, environment, memory check, pre-change snapshot, and before/after code hashes are in timing/fix_20261105_w2f/. No actual data or performance evaluation was used.

## 감독자가 고정할 다음 조건

1. 사고 스프레드시트의 개발 사용 권한과 라벨 출처를 확정한다.
2. 신원 확정 기준 및 정상/미사고 근거를 제시한다.
3. 반복 후보 연결요소 단위의 train/dev/calibration/eval 배정과 고정 시드를 승인한다.
4. 참조 지도·분위수 전처리에서 각 eval vessel/event를 제외할 범위를 확정한다.
5. 임계값 출처, 초과 경계, 최대 구간 간격, 지속 최소 행수·시간을 사전 고정한다.
6. 전체 예측을 사고시각 열람 전에 동결하고, 공식 시간오차 F1 수식·6시간 경계를 확인한다.

At the time of the original W2 preparation, 1103_v2 was still in the parent intake queue; this report therefore describes legacy inputs only. The latest direct comparison of the legacy and new rosters is documented in ../audit/v2_id_recheck_001/recheck_report.md. The 100-vessel table remains legacy-only; do not relabel its rows or transfer predictions.
