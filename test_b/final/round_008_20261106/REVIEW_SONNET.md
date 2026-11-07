# Round8 중간관리자 검토 — Sonnet

## 판정: RELEASE (조건부) — 1건의 구체적 보완만 요구, 설계 재협상 불필요

## 내 이전 제안의 결함 인정

1. **사고시각 누수**: 내가 제안한 "acc_ts±6h 창으로 원시추출 범위를 제한"하는 방식은 후보군 생성 자체가 정답(사고시각)에 의존하므로 방법 비교에 결과를 흘려넣는다. Root의 기각이 정확하다. R7의 B그룹(사건인근 실패관찰)처럼 "결과를 알고 고른 진단 관찰"로는 유효하지만, 점수 생성/방법 선택에는 쓸 수 없다는 구분에 동의한다. CONTRACT.md의 "Never read accident files to select raw records, references or pools"와 "Select raw records... for ALL observed hours, never by event timestamps"가 이를 올바르게 고정했다.
2. **n_points≥3 대 n_unique_coords≥3**: R7에서 내가 "n_points>=3"을 기준으로 썼던 것은 틀렸다. R7 자체 자료에서 101개 부분선 중 고유좌표 3개 이상인 것은 79개뿐이라고 Root가 지적했고(동일 좌표 반복은 점 개수만 늘릴 뿐 형상 정보를 주지 않음), CONTRACT.md가 "n_unique_coords>=3"로 올바르게 교정했다. 승인.
3. **durationCDF 혼합 금지**: 내가 PG안에서 Round6 self_cdf(지속시간 기반)를 2차 tie-break로 재사용하자고 한 것은 서로 다른 두 가설(지속시간 이례성 vs 형상 이례성)의 혼합이라 인과 해석을 흐린다. CONTRACT.md가 "No R6 durationCDF mixed in"으로 명시 분리한 것이 맞다.

## 실제 Terra 안에 대한 평가 — 강점 2건, 수용

- **"가장 긴 적격 부분선 선택"**: 내 "정보적 부분선 전체 중 최소 D/L" 방식보다 낫다. 짧고 노이즈가 많은 부분선 하나가(좌표 jitter로 우연히 낮은 D/L을 가져도) 행 전체의 이례성 판정을 좌우하는 것을 구조적으로 막는다. 선택 기준(path_length, 결과와 무관한 기하량)과 평가 기준(D/L)이 분리돼 있어 순환성도 없다.
- **전체82척/전 관측기간, 결과 비의존**: 내 bounded-window 방식보다 번거롭지만 유일하게 안전한 설계다. R7이 이미 22행/101부분선/334MiB/27초로 스트리밍 추출 실현성을 증명했으므로 99,677행 전체로의 확장도 CONTRACT의 월별 incremental writer·scalar-only 저장 방식이면 현실적이다.

## 구체적 보완 1건 (release를 막지 않는 조건부 수정)

**동점(tie) 활성화율을 사전에 진단 지표로 명시 요구한다.** G는 self_rarity 우선, peer_rarity는 self_rarity가 정확히 동점일 때만 순위에 개입하는 2차 기준이다. self_rarity가 연속값에 가까우면 동점은 드물 수 있고, 이 경우 "어업 맥락이 기여하는가"라는 이번 라운드 핵심 질문(코어점검 3번)을 peer_rarity가 거의 작동하지 않는 메커니즘으로 시험하게 된다. CONTRACT.md에는 이 활성화율을 측정/보고하는 항목이 없다. 요구사항: metrics에 "G 후보 중 self_rarity 동점으로 peer_rarity가 실제 순위를 바꾼 RFID/사건 비율"을 결과를 보기 전에 저장하도록 1줄 추가한다. 이 비율이 낮게 나와도 결과를 본 뒤 self/peer 우선순위를 뒤집지 않는다 — 이는 이미 과제가 요구한 원칙("lack of peer influence is measured, not compensated by changing priority after seeing results")이며, 수치 산출 의무만 신규로 추가하는 것이다. 수식·분모·관문은 변경하지 않는다.

## 5개 코어 점검 확인

1. **코어 해당 범위**: s0→s1(non-small)→s2(형상 유효)→s3(자기 과거)→s4(어업 동료)의 순차 규칙 자체가 PROTOCOL 1번 코어("순차 판정 규칙 적용")에 정확히 대응한다.
2. **비코어 명시**: 선로추종·항만·실제속력·조업상태 분류는 여전히 미구현(PROTOCOL 2번과 동일), 이번 추출량 증가 자체를 적중률 진척으로 세지 않는다는 문구 유지 확인.
3. **목표/구현물/관찰/검증/질문**: CONTRACT의 geometry_ledger.parquet 1행=원행 1개, n_parts/n_informative_parts/chosen_part_index/shape_dl/geometry_status 스키마가 PROTOCOL 3번의 "형상장부·순차상태·예측·풀·사건지표" 요구와 일치. 질문("형상 이례성이 기존 점수보다 낫는가")에 답할 수 있는 B0/S/G 비교 구조도 갖춤.
4. **입력 가용성**: 1/5/6월 해시는 R7 기록과 재대조, 2~4월은 "새로 관측한 해시"로만 기록하고 과거 일치 주장은 하지 않음 — 정직한 범위 qualification, 승인. R4 candidate_ledger 99,677행/82RFID 키 재사용도 확인됨.
5. **다음 관문**: G-B0 Tier01 top1 +5%p, paired bootstrap 95%하한>0, 전체100 비악화, Tier01 G 실제풀 random 기대 초과 — 4개 모두 충족해야 하며 미통과 시 "임계/집계 통계 사후 교체 금지"가 PROTOCOL에 이미 명시됨. 이는 R4~R7에서 실제로 지켜진 전례(매 라운드 널결과를 그대로 기록)와 일치하므로 신뢰할 수 있다.

## 추가 기술 체크리스트

- **raw keys/hash/cache coverage**: ordinal = monthly offset + zero-based row_index 공식과 월별 offset/count 값이 R7 lineage_audit의 기존 수치와 동일하게 재인용됨. 1e-4m/1e-7deg 허용오차도 R7과 동일. 불일치 행은 scoring 릴리스를 막고 진단으로만 보존 — 적절.
- **finite point/unique coord rule**: n_unique_coords>=3 AND path_length>0 AND finite D/L∈[0,1] — 앞서 지적한 R7 교정사항 반영 확인.
- **strict past at same t**: 자기/동료 참조 모두 [t-720,t) 반개구간, 현재·미래 행 참조 금지 명시 — leakage 없음.
- **fallbacks**: S는 s3→s0 직행(미보정 raw-shape 중간 폴백 없음)으로 "보정 안 된 원시 형상값으로 순위를 매기지 않는다"는 원칙을 지킨다 — R4/R6의 d2(원시 legacy로 랭크 가능한 중간폴백)보다 더 보수적이고 타당하다.
- **shared budget**: B0/S/G cap=min(4, G 실제 풀 n) 공유, 동일 RFID 연결사건 동일 예측목록 — R4~R6과 동일 관행 유지.
- **fixed primary gate**: G-B0 Tier01 top1 고정, 결과 후 S나 top4로 전환 금지 — 명시적 사전동결, R5의 "S top4 cherry-pick 금지" 교훈 계승.
- **반복 dev 한계**: 이번에도 탐색적 증거일 뿐이며 일반화 확정이 아님을 PROTOCOL이 유지 — 확인.

## 결론

Blocking 이슈 없음. 위 tie-활성화율 보고 1줄 추가만 요청하고, 나머지 CONTRACT.md는 그대로 실행 승인한다.
