# Round004 E 완료 후 V 동적 독립 검산 계획

작성: Round004 V 정적 task, 2026-11-05. 이번 task에서 계획만 만들며 실행하지 않았다. 다음 별도 followup은 `testB/round_004/audit/`만 소유하고 `execution/`은 읽기 전용이다. E 구현 결함은 E에게 요청한다.

## 진입 및 RAM gate

E worker_done/실제 종료코드/attempt/stdout/stderr/hash 및 실행 산출물이 확인된 뒤 시작한다. 요청·launch model/effort와 provider 내부 unknown을 구분한다. followup 시작 직전에 fresh available RAM, 예상 증분 ≤256 MiB, 512 MiB 여유, E/host 동시작업, 근거·시각을 기록한다. 메모리 부족이면 다른 문서 작업을 먼저 하고 재개 직전 재확인한다. 전체 key scan/parquet scan은 이 followup에서 허용되지 않는다.

## 독립 기준 구현

1. canonical 4개 source SHA-256을 pinned 값과 재비교한다. `run_remeasure...py`의 `load_rows` AST를 작은 in-memory namespace에 추출한다. fake `parquet_path`/`pq.read_table`만 미리 고정한 Arrow rows/batches를 반환하며 파일이나 production import side-effect를 호출하지 않는다.
2. 기준 A는 canonical `load_rows` AST 자체 실행. 기준 B는 계약을 따라 별도 작성한 whole-column oracle: 월/물리 순서, key_valid admission, concat ordinal, 전체 ID에 `pd.to_numeric(errors="coerce")`, ID drop/int64, 그 이후 남은 date 전체 변환/drop/int32, 원래 concat index holes와 반환 열 순서. B는 E parser/helper/comparator를 import/reuse하지 않는다. A/B 외에 hand-computed expected IDs/dates/drop masks도 fixture에 고정한다.
3. E adapter는 세 번째 구현으로 대조한다. AST·B oracle·명시 expected 결과가 먼저 서로 일치하지 않으면 E 통과 판정을 중단한다. 원본 AST/independent oracle 실행을 생략하고 E 코드를 복제한 oracle 하나만으로 독립성 주장하지 않는다.
4. 제한 domain만 허용: ASCII `[+-]?[0-9]+`, ID abs≤2^53, date int32. parser는 string에서 선행 zero 정규화/정수 비교를 하며 float boundary 비교 금지. null/NaN/명백한 nonnumeric의 처리 mask는 AST와 oracle expected에 정확히 맞춘다. ID-invalid row는 date 검사를 건너뛰어 원본 순서를 지킨다.
5. decimal/scientific/공백 숫자/overflow/2^53 초과/Unicode numeric 또는 문서화한 lexical length 상한 breach가 나오면 그 행을 삭제해서 성공 처리하지 않고 전체 입력 시도를 fail-closed해야 한다. 이는 unsupported input 부정시험이다. 원본 AST가 numeric conversion/cast를 통해 수용하는 값을 silent reject/drop하면 실패다.

## Fixture matrix

- `key_valid_only=True/False`; 두 달 이상; 각 월 physical order, 첫/마지막 행, 실제 batch 경계, 빈 물리 batch 및 빈 달.
- request 열: `rfid_id` only, `part_dt` only, 둘 다, numeric key 없음, explicit `key_valid`, explicit `month`, caller-order permutations. implicit key_valid/month 추가, conversion 생략, 반환열 순서/dtype을 oracle 비교. `months=[]`는 원본의 concat error를 보존하는지 확인.
- ID: `0`, ±값, `+0`/`-0`, signed/leading-zero, 2^53 및 -2^53, 양·음 2^53+1. raw leading-zero 장문과 길이 상한은 지원정책대로 통과하거나 전체 fail-closed; drop 금지.
- date: int32 min/max, 바로 바깥 값, yyyyMMdd-like integer. 범위 밖 값은 drop 대신 fail-closed.
- `None`, NaN, pd.NA (source dtype가 표현 가능한 것), 확실한 text nonnumeric; ID-invalid 행의 date에는 의도된 unsupported value를 넣어 ID 후 date 순서를 확인. valid ID + bad date는 원본처럼 date 단계에서 제거되는지 확인.
- unsupported accepted forms: `1.0`, `1.5`, `1e3`, ` 12 `, whitespace numeric, Unicode digit, int64/date int32 overflow. Canonical AST 예상동작을 독립 oracle와 비교한 뒤 E는 unsupported entire call을 중단하는지 확인. row-level filtering으로 성공하면 FAIL.
- exact compare: values, physical row order, columns, dtypes (`month:int8`, `key_valid` bool 포함), NA, reason/drop masks, batch trace, global concat ordinal, final pandas index holes. 비교 직전 reset index 금지.

## 실제 작은 multi-batch 표본

실제 작은 표본은 별도 followup dispatch가 허용하고 RAM gate가 통과할 때 최대16,384 projected rows / batch≤4096으로 제한한다. partition/month/file/physical offsets or row-group/columns/source SHA/expected count를 읽기 전에 고정한다. V가 Arrow batches를 별도 순서로 직접 iteration하고 각 호출의 batch number, physical offsets, key-filter 후 global ordinal을 기록한다. AST/oracle에는 동일 표본을 하나 ordered stream으로 inject한다. E를 single concatenated Table로 한 번 호출하는 것은 동적 검산 FAIL이다. 각 행의 value/order/column/dtype/NA/drop/index를 위치 비교한다. 이 evidence는 sample 범위에만 해당한다.

## 실패·통과 범위

source hash mismatch, unsupported numeric-like row가 silent drop됨, invalid ID 제거 전 date 검사, API 열 요구/빈 batch 오류, output order/index hole 차이, drop mask/dtype/value 불일치, duplicate/missing row, 또는 single-call trace면 실패로 기록하고 실제 exit/artifact를 보존한다. V는 audit/만 수정하고 생산 결함은 E에게 요청한다.

작은 fixture와 선택 표본이 통과해도 전 입력 domain coverage, full loader/reference equivalence, memory safety, reference builder, score/A/membership, Testfit runtime, 사고 정답·성능의 증명은 아니다. 전체 key-domain scan은 별도 계약/승인/peak·RAM gate 이후에만 가능하다.
