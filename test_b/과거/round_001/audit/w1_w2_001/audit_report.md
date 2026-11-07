# W1/W2 독립 검산 보고서

검산 상태: **fail** (제품 검증 통과와 별개)

## 결과
- **PASS — W1 rows, priority union, nine conditions and aggregates**
- **PASS — W1 identity/use/normal claims bounded**
- **PASS — W1 E0023 trace/units/sample cache summary**
- **PASS — W1 E0023 direct accident row and selected cache row**
- **PASS — W1 listed input/code/output hashes, final exit, attempts and environment**
- **PASS — W2 ordered 100 unique IDs and A values vs canonical CSV**
- **PASS — W2 B/C are blank and not computed, no normal label**
- **FAIL — W2 current tie contract, manifest generator, split pending, 95 overlap bounded**
- **PASS — Independent synthetic timing checks (not self_check)**
- **UNKNOWN — Duplicate-timestamp conflicting-score policy fully specified**
- **UNKNOWN — Positive score-floor semantics resolved for future evaluation**
- **FAIL — max_gap parameter can bridge unobserved time**
- **PASS — W2 observed synthetic exit, environment, request receipt**
- **PASS — W2 round code lineage, output hashes and process logs are consistent**
- **PASS — W3 model/effort request receipt and dispatch identity**
- **UNKNOWN — Provider-internal actual runtime model independently observable**
- **PASS — W2 source manifest references resolve/hash-match**
- **PASS — Inspected W1/W2 target hashes unchanged during independent audit**

## 핵심 판단

- W1 30개 사건과 우선 합집합 10개를 표에서 다시 집계했다. 9조건 관계, 안정 1건, 시간확대 다후보 7건, 다선박 수 불일치 3건, 신원 확정 0건이 일치한다. 사용범위는 unknown이고 정상 근거가 없으며, 잔차는 후보 연결 근거다.
- W2 A 순서/ID/시각/점수는 기존 제출 CSV와 대조했다. scored_rows.pkl은 열지 않았다. B/C 값은 비었고 not_computed이며 행별 사유와 not_assessed_not_accident_label 상태가 유지됐다.
- W2 manifest의 ties_and_duplicates는 earliest maximum이라는 옛 문구가 남아 코드와 code_lineage의 원입력 순서 최초 최대 계약과 충돌한다. `publish_legacy_preparation.py`도 같은 옛 문구를 재생성하므로 둘 다 고쳐야 한다.
- 독립 합성 검사에서는 동점 A, 동일 구간 B/C 및 C=B, NaN/시간간격 분절, 중복시각 지속행수, 파라미터 출처, 빈 점수 계산불가를 확인했다. 실제 점수 임계값은 선택하지 않았다.
- max_gap_hours가 샘플 cadence보다 크면 미관측 구간을 연결한다. 중복 timestamp 값 충돌의 채택 정책은 미정이며, positive floor는 결측이 아닌 유한점수로 취급되어 임계값에 따라 판정을 바꿀 수 있다.

## 조치 필요
- **blocking** testB/round_001/timing/input_split_manifest.json (method_states.ties_and_duplicates): Contract contradicts current A tie implementation and can select a different row. 재현: Read current JSON field: says earliest maximum wins; code and lineage say first max in original input order. 제안: Change to first maximum in original source order for A; stable timestamp+ordinal ordering is B/C only; retain duplicate rows and count unique timestamps for persistence.
- **high** testB/round_001/timing/publish_legacy_preparation.py (line 94: method_states.ties_and_duplicates literal): Re-running the publisher can restore the contradictory earliest-maximum contract after a manifest-only correction. 재현: Search this generator for 'earliest maximum wins'; it serializes the old rule into input_split_manifest.json. 제안: Update the generator literal to first maximum in original input order for A; note timestamp sorting only affects B/C.
- **open_design_limit** testB/round_001/timing/timing_interface.py (estimate_vessel gap comparison; TimingParams.max_gap_hours): A configured tolerance above nominal cadence connects across unobserved bins; this is unresolved against a strict no-missing-time policy. 재현: Synthetic ts=0 and ts=2 above threshold with max_gap_hours=2 yields one segment (B=0). 제안: Supervisor must explicitly choose supported cadence/gap semantics. If missing bins always break, require adjacent expected cadence rather than a variable tolerance.

## 미확정 인터페이스 한도

- `timing_interface.py`의 timestamp 정렬은 원행 ordinal을 유지하고 중복 시각은 행 추적에 남기며 지속 행수는 고유 시각 수로 센다. 그러나 같은 시각의 점수가 충돌할 때 사전 중복 제거·통합 규칙은 아직 없다. 적용 위치: `timing_interface.py` 79–87, 130–131행.
- `input_split_manifest.json`의 점수식 설명은 양수 floor를 언급하고, 인터페이스는 `1e-6`을 보통 유한 점수로 받아들인다. threshold가 승인되지 않았고 floor의 평가 의미도 고정되지 않아 실제 판정에 미칠 영향은 unknown이다. 실제 임계값은 선택하지 않았다.

## 한계

W0 v2, 원자료 전체, 디스크 전체, 전체 43+31 선행감사 재검산은 포함하지 않는다. actual split, 2026 실제 점수/사고 평가, 모델 학습, threshold 선택은 하지 않았다. Orca 영수증은 gpt-6-luna/xhigh 요청을 보여주며 provider 내부 모델 관찰은 별도 불가.
