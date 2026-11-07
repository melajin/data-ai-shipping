# Round11 실제결과 검토 — Sonnet

## 1. 독립 재검증

event_results.csv 직접 재집계로 전수 일치: B0=3/100·2/60·7/100·5/60, S=2/100·1/60·10/100·7/60, G=2/100·1/60·9/100·6/60. ROOT_STAGE_COVERAGE_SUMMARY.json(all s0~s4=100→92→88→87→87, tier01=60→53→53→53→53)와 pool_manifest.csv 집계(G cap 전부4, S fallback 2척, G fallback 3척)도 전수 일치.

**사건 적중 집합**: Tier01 top1에서 B0={22,79}, S={22}, G={22} — S/G는 B0가 맞힌 두 사건 중 22만 유지하고 79는 잃었으며 새로 얻은 사건이 없다. R9(방법마다 서로 다른 고유 적중)보다도 더 나쁜 패턴으로, 거리 CDF가 B0의 적중을 대체하지 못하고 순수 손실만 냈다.

**결정론적 RFID 3개×3방법=9건 재현**: 처음 시도에서 S/G 모두 2건 MISMATCH가 났으나, 원인은 내 검증스크립트가 pool_stage 라벨(s2/s4)만 보고 순위기준을 잘못 가정했기 때문이었다 — **method별 실제 tie-break 체인(B0=legacy; S=self_distance_cdf→legacy; G=self_distance_cdf→peer_distance_cdf_mean→legacy)**으로 재검증하니 9/9 전부 일치했다. 이 과정에서 직접 발견한 사실: 31001758은 self_distance_cdf=1.0에서 4-way 동률, 31007500·31008085는 2-way 동률이었고 G는 그 안에서 실제로 peer_distance_cdf_mean이 더 높은 쪽을 정확히 골랐다 — 보고서의 "self CDF 동률 78/79척, 최댓값 동률 69/79척"과 정합적이다. **단측 self CDF가 1.0에서 자주 포화(saturate)되어 변별력이 급격히 떨어진다**는 것이 이번에 직접 확인한 구체적 실패 메커니즘 후보다(공식 주장은 아니며 보고서의 "peer가 작동은 했으나 개선 없음"과 같은 방향의 보충 설명).

**동결 확인**: EXECUTION.json에서 `frozen_before_event_parse` 해시와 `frozen_post_eval_unchanged=true`, `source_and_input_hashes_unchanged=true` 직접 확인.

## 2. 5개 코어 점검

1. **코어 해당**: 반복공간-현재위치 관계를 자기/어업 단측CDF로 순차 적용, R8 HistorySweep.cdf를 읽기전용 재사용(새 통계 아님).
2. **비코어 명시**: run/재개/형상 문턱 재탐색 아님, 항로·항만·정상대기 미판정.
3. **학습목표**: "좌표이력 적격(R10)"과 "거리값이력 적격(R11, 94,290/92,257)"이 다르다는 구분을 보고서·diagnostics 양쪽에서 확인.
4. **입력가용성**: R10 거리/계보 재사용, 신규추출 없음.
5. **다음관문**: 4관문 전부 실패 재확인(Tier01 diff −1.67%p, CI[−5.36%,0%], 전체 −1%p, random 1.667%<2.337%).

## 3. 다음 단계 평가

위치/형상/지속/재개 계열이 4라운드 연속(R6·R8·R9·R10→R11) 전부 주관문 실패했고, 사전 중단조건대로 같은 자료의 추가 임계값 탐색을 제안하지 않는다. 이번 과제의 본 제안(라벨 관측가능성 진단)은 별도 파일 `OBSERVABILITY_EVIDENCE.md`에 담았다 — 특징을 더 늘리기 전에 평가 대상(잠정 사고-RFID 연결) 자체가 무엇을 보여줄 수 있는지 먼저 확인하는 것이 특징 설계보다 선행돼야 한다는 보고서의 판단에 동의한다.
