# Round8 구현 검토 — Sonnet (CONDITIONAL RELEASE)

담당 초점: 추출기(Luna, 결과비의존 all82/all99677) + 규칙(strict past/own-peer/fallback/legacy DESC), 평가기 게이트 인터페이스는 보조 확인. 코드만 직접 읽고 해시를 남긴다 — raw 데이터 재실행·polling 없음.

## 판정: CONDITIONAL RELEASE — 코드 결함 없음, 증거계보(evidence binding) 1건만 보완 요구

## 1. 라인단위로 확인한 수정사항 (전부 FIX 확인됨)

- **writer 중복행 버그(FIX_01 Luna #1)**: `extract_geometry.py` L219-237 `write_geometry_rows`는 batch에 append→`batch_size` 도달시 write_table→`batch.clear()`가 정확히 연결돼 재방출 경로가 없다. 수정 확인.
- **첫행 기반 nullable 스키마 오염(FIX_01 Luna #1)**: L201-216 `_geometry_schema`가 호출 전에 고정 `pa.schema([...])`를 선언하고 `write_geometry_rows`가 이를 그대로 사용(L221-222,229,233) — 첫 행이 `informative` 아니어도 이후 유효 행이 null로 깨지지 않는다. 수정 확인.
- **per-part 적격성(CONTRACT)**: L109-121 `n_unique_coords<3`→ineligible, `path<=0`→ineligible, `ratio`는 roundoff 1e-9 허용 후 `[0,1]` clamp. 폐곡선(끝점=시작점, path>0)은 ratio=0으로 **적격 유지** — "closed curve D=0" 체크와 일치. 최장 선택은 L130 `min(eligible, key=(-path_length_m, part_index))`로 최장·동률시 작은 part_index — CONTRACT와 정확히 일치.
- **legacy DESC 수정(FIX_02)**: `shape_rules.py` L141(s0), L143(s3: self_rarity desc→legacy desc), L145(s4: self_rarity→peer_rarity→legacy, 전부 desc), L337(peer-off 대조군도 동일 legacy desc) — 네 경로 전부 `-float(...score)`로 일관 수정됨. 이전 fixture가 오답 방향을 검증하던 문제(.01이 승자)도 shape_checks.json의 "legacy-only paths rank descending as [.9,.5,.1]" 항목으로 교체 확인.
- **strict past window [t-720,t)**: `HistorySweep.advance`(L68-82)가 `times[hi]<t`일때만 편입(현재 t 행은 자기 역사에 안 들어감), `times[lo]<t-720`이면 제거 — 반개구간 정확. 전체 RFID의 sweep을 같은 t로 동시 advance(L220-221) 후 동료 적격성(`peer_sweep.eligible`, L245)을 판정하므로 "같은 t 기준 동료 자격"이 실제로 보장된다. 동료는 그 시각에 관측이 있을 필요 없이 과거이력만 있으면 됨 — Round6 패턴과 일관.
- **fallback 계층**: S=s3 있으면 s3, 없으면 **s0 직행**(L297-298, s2 미보정 폴백 없음 — CONTRACT의 "no uncalibrated raw-shape fallback" 그대로). G=s4 있으면 s4, 없으면 S가 실제로 쓴 stage 그대로(L299-301). 공유 cap은 RFID당 1회(L303 `cap=min(4,len(pools["G"][1]))`)만 계산돼 B0/S/G 모두에 동일 적용(L309 `selected=ordered[:cap]`).
- **tie 활성화 진단(내 R8-1차 REVIEW_SONNET.md 보완요청)**: shape_checks.json에 `diagnostics_peer_ties`로 s4 실제 pool 보유 RFID 7개 중 tie_groups=1, rank1이 peer로 바뀐 RFID=1건이 구현·기록됨 — 요청 반영 확인.
- **평가기 통합 수정(FIX_01 Gemini #1-5)**: `run_shape.py`에서 ① receipt 검증이 `mismatch_count==0`/`error_count==0`/`rows_written==expected`/`canonical_rows_expected==expected`/`release_ready_for_scoring is True`를 전부 명시 raise로 강제(L157-166, 필드 결측을 성공으로 default하지 않음), ② merge는 공유 수치열(len_m/bbox_m/score 등)을 **병합 전에 허용오차로 직접 대조**(L243-255)한 뒤 geometry쪽에서 그 열들을 **제외**하고 merge(L257-269, `validate="one_to_one"`)해 `_x/_y` 접미사 충돌 자체가 구조적으로 불가능하고, 병합후 행수·원순서·unsuffixed 컬럼 존재까지 재검증(L274-284) — 설계상 매우 꼼꼼함. ③ `import traceback` 존재(L21). ④ `shape_rules.py`가 source 해시 목록에 포함(L370). ⑤ 출력디렉토리는 파일이 하나라도 있으면 거부(L310-313, 완료 receipt 여부와 무관) — 전부 확인됨.

## 2. 보완 요구 1건 (release를 막지 않음, 실제추출 전 권고)

**extract_checks.json에 소스 해시가 없고, 그 생성시각(02:29:01)이 extract_geometry.py의 최종 수정시각(02:36:14)보다 앞선다.** 즉 "passed" 판정이 지금 디스크에 있는 바로 그 코드를 검증했다는 암호학적 증거가 없다(shape_checks.json은 02:35:34생성/02:34:40수정이라 순서는 맞지만 역시 해시 미기록). 내가 직접 전체 로직을 재대조해 현재 코드가 맞다는 것은 확인했지만(위 1절), 이는 이번 검토자의 수동확인이지 재현가능한 증거가 아니다. 실제 1회 추출(ACTUAL_EXTRACTION_RELEASE.md) 실행 전에 두 checks 스크립트를 재실행해 `extract_geometry.py`/`shape_rules.py`의 sha256을 각 checks JSON에 기록할 것을 요구한다. 참고로 현재 파일 해시: extract_geometry.py=`a7a6ffed1319b8c75155df2935e11e3ab1c9f1de73f384563d5c6e99f1d1ffdb`, shape_rules.py=`6eb571aef12dc881b78dc4c93fd77683ba4068d22be654ee46c208eab78e4472` (이번 검토 시점 직접 계산).

## 5개 코어 점검

1. **코어 해당**: s0→s1(non-small)→s2(형상 유효)→s3(자기 이력)→s4(동료) 순차 규칙이 PROTOCOL 1번과 정확히 대응, 코드가 이를 그대로 구현.
2. **비코어 명시**: 선로추종·항만·실제속력·조업분류 미구현 유지, 추출량 자체는 진척이 아니라는 PROTOCOL 2번 반영.
3. **구현물/검증**: geometry_ledger.parquet 스키마가 CONTRACT 요구 필드(n_parts/n_informative_parts/chosen_part_index/shape_dl/geometry_status 등)와 정확히 일치(L203-216). synthetic 10+9개 체크가 경계값(2점, 중복좌표3점미만, 폐곡선, 월경계 ordinal, 미래행 불변성, 중복키 거부)을 포괄.
4. **입력 가용성**: R4 candidate_ledger 99,677행/82RFID, R3 gear_registry 재사용, 원시 CSV 해시(1/5/6월 기지, 2-4월 신규관측)·ordinal 공식 R7 그대로 재인용. 시간은 "naive source-clock epoch-hour"로 명시, UTC/KST 임의변환 금지(TIME_INTERFACE_ADDENDUM) — 코드에 타임존 변환 호출 없음 확인.
5. **다음 관문**: G-B0 Tier01 top1 +5%p/CI하한>0/전체100비악화/Tier01 G실제풀random초과 4개 모두. 실제 채점은 아직 미방출(root 보류), 이번 검토는 그 전 단계.

## 학습/평가 구분 및 경쟁 리스크

수치·단위 테스트 통과는 "사고 탐지에 유용함"을 증명하지 않는다 — synthetic_execution의 B0/S/G 분리 자체도 가상 데이터 기준이며 실제 적중률과 무관하다. R7 B그룹(사고 인근 사례)처럼 결과를 보고 고른 사례는 진단에만 쓸 수 있고, 이번 실제 방법은 전 관측시간(all82/all99677) 기준이어야 한다는 설계 원칙은 코드(extract_geometry.py가 positives/acc_ts를 전혀 읽지 않음)로 확인했다. 반복 사용된 dev에서 설령 4관문을 통과해도 이는 탐색적 증거일 뿐 일반화 확정이 아니다. 경쟁 리스크(Terra 초점인 run_shape/evaluate_shape 수치병합·시계열영수증은 본 리뷰가 보조로만 다뤘으므로): Terra가 더 깊이 본 random-expectation 코호트 테스트나 receipt manifest 세부에서 내가 못 본 결함이 있을 수 있다 — 두 리뷰를 모두 본 뒤 총괄이 조정할 사안으로 명시해 둔다.

## 결론

Blocking 버그 없음. extract_checks.json/shape_checks.json에 소스 해시 기록 1건만 실제추출 전 요구하며, 그 외 CONTRACT.md·현재 구현은 그대로 실행 승인한다.
