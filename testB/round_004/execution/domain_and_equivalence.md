# Round004 제한 정수 도메인 adapter — 조건과 한계

요청/기록된 실행은 Orca gpt-6-luna/xhigh이며 provider 내부 모델·effort는 unknown이다. 이 문서는 작은 fixture 및 16,384행 표본용 조건부 변환기 설계다. 실제 Train 전체 도메인은 unknown이고, 전체 스캔·참조·점수·사고판정은 수행하거나 허용하지 않았다.

## 고정 원본과 호출 경로

| 모듈 | 고정 SHA-256 | 이번에 확인한 실제 연결 |
|---|---|---|
| `run_remeasure_20261031.py` | `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c` | `load_rows(dataset, columns, months=MONTHS, key_valid_only=True)`가 각 월에 `pq.read_table(path, columns=list(needed))` 호출. `needed`는 요청 base 열과 자동 추가 `key_valid`의 집합. key 필터 후 월 `int8` 추가, `out_cols + month` 순서로 월 프레임을 concat(ignore_index=True)하고 전역 ID 변환/제외/cast 뒤 date 변환/제외/cast. |
| `run_008_testB_20261101.py` | `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8` | harbor: `load_rows("train", [rfid_id, cen_lon, cen_lat, len_m, bbox_m, wkt_valid])`; gap/jump: `[rfid_id, part_dt, rfid_time, cen_lon, cen_lat, wkt_valid]`; density는 `_train_arrays()`, harbor 및 `_build_own_moorings("train")` 연계. |
| `run_005_F156_merge_20261101.py` | `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4` | `_train_arrays()`가 `featac._load_year_arrays("train")`를 cache함. `_build_t5_dicts(fit_rid_label, fishing_mask, month_filter)`는 해당 배열들을 사용. |
| `run_cycle4_3_featAC_20261101.py` | `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3` | `_load_year_arrays(dataset)`가 `load_rows(dataset, [rfid_id, part_dt, rfid_time, len_m, bbox_m, cen_lon, cen_lat, wkt_valid])` 후 배열화/정렬. |

파일 SHA는 Round002 pinned manifest와 일치했다. 전체 canonical import를 피하고 첫 모듈의 `load_rows` AST만 고정 SHA 검증 후 주입 데이터로 실행했다. Builder 자체는 이번에 호출하지 않았다.

## 제한 입력 도메인

- 허용 문자열은 ASCII `[+-]?[0-9]+`만이며 raw 길이는 최대 128 code point다. 선행 0, `+`/`-`, 부호 없는 숫자를 그대로 허용한다. ID 값 범위는 `[-2^53, +2^53]`(양끝 포함), date는 signed int32 범위(양끝 포함)다. Python/NumPy 정수 값도 해당 범위일 때만 허용한다.
- 빈 Arrow null, Python `None`, `pd.NA`, IEEE NaN은 원본 coercion 결과처럼 숫자실패로 다뤄 행 제외 후보가 된다. `key_valid_only=True`면 해당 검사는 key filter 이후에만 한다.
- 알파벳/underscore 토큰은 원본 pandas `to_numeric(errors="coerce")`가 scalar를 NaN으로 분류하는 경우만 명백한 nonnumeric으로 행 제외한다. `inf` 등 coercible non-finite word는 지원하지 않고 중단한다. 원본과 다르게 임의로 제외하는 분류는 없다.
- 공백, 소수점 표기, scientific notation, ASCII가 아닌 숫자/부호, 불확실 문법, bool, 128자 초과, ID 범위 초과, date 범위 초과는 전체 단계를 `UnsupportedDomain`으로 중단한다. 소수·과학표기·overflow를 원본이 받아도 adapter는 지우지 않고 전체 단계 중단으로 알린다.
- ID 숫자 실패만 먼저 제외한다. 그 행의 date 문자열은 검사하지 않는다. 남은 행에서 date coercion/실패 제외를 진행한다. ID/date 열을 요청하지 않았으면 해당 변환 단계는 건너뛴다. 원본 API처럼 `key_valid`를 출력에 추가하고 `month:int8`을 마지막 열에 붙인다. 요청 열 순서와 중복 key_valid 처리를 유지한다.

## 조건부 동등성 논증

원본 전체 Series의 pandas 숫자 추론은 월·행 전체의 값 조합에 의존한다. 이 adapter는 그 inference를 흉내 내지 않는다. 허용 domain에서는 ID와 date의 변환 결과가 정확히 표현되는 이유로 conditional equivalence를 주장한다. 전역 결과가 int64인 경우 허용 정수는 그대로 int64에 들어간다. 결측/명백한 nonnumeric 때문에 원본 변환이 float64로 승격하더라도 모든 허용 ID는 절댓값 `2^53` 이내여서 float64 정수로 정확하다. 원본의 `int64` cast는 동일한 정수를 만든다. date는 int32 범위의 정수로 제한했으므로 float64 중간 표현도 정확하고 int32 cast 결과도 같다. unsupported 값을 발견하면 이 전제가 깨질 수 있으므로 배치별 추론/제외를 계속하지 않고 fail-closed한다.

전역 ordinal은 월순서 및 월 내 물리순서로, `key_valid` 필터를 거친 행들에 대해 concat 직후 생긴 인덱스와 동일하게 유지한다. 숫자 실패로 행을 제거해도 뒤 행 index를 재연속화하지 않는다. 합성 도메인 fixture는 원본 `load_rows` AST에 월 테이블을 주입하고 동일한 RecordBatch 경계로 adapter를 호출한다. 실제 표본도 결합 Table의 1회 transform이 아니라 최대 4,096행 batch마다 `transform_batches`를 별도로 호출한다.

이것은 작은 fixture와 선택한 표본에 대한 증거일 뿐이다. 실제 전체 정수 domain의 유효성, 모든 Arrow/Pandas type 변형, 전체 데이터의 frame 동등성, builder 출력/정렬/참조 동등성, 생산 사용 가능성 또는 성능 성공을 의미하지 않는다.

## 다음 단계 key-only scan 사전계약 초안

이 worker는 scan을 실행하지 않는다. 감독 검토 전 초안 조건:

1. 입력은 Round002 준비물에 고정된 2026 Train 월별 Parquet만. 재해시한 원본4모듈 SHA와 월별 Parquet SHA/schema, 물리 월순서, source row count를 사전 manifest에 고정한다. 원 CSV 재파싱, test, 사고파일, score, 참조 builder 호출은 금지한다.
2. 스캔할 열은 `key_valid`, `rfid_id`, `part_dt` 뿐이며 `iter_batches` 최대 4,096행으로 읽는다. 각 월에서 canonical 순서대로 `key_valid` 행만 먼저 선정해 검사 population과 전역 ordinal을 만든다. 별도 `key_valid_only=False` population 검토가 필요하면 감독이 분리 승인한다.
3. 반드시 실제 원본 loader AST/oracle와 독립 scanner 모두에서 grammar·길이·null·nonnumeric·범위 기준이 동일해야 한다. 발견한 첫 unsupported token에서 즉시 중단하고 row 위치/월/열/범주만 보존하며 원문 식별값의 광범위한 덤프는 하지 않는다. supported counts/invalid counts/min/max/leading-zero·sign 길이 summary와 exact per-row keep/index mask/hash를 범위 명시해 저장한다.
4. 메모리 계획: batch 4,096의 세 열만 투영하고 모든 행별 mask를 RAM에 보유하지 않고 SQLite/압축 bitmap 또는 순차 hash로 기록한다. 월별 row count 총 4,212,389; 1bit mask 1개 raw 크기는 약 0.50 MiB, 두 단계 mask 약 1.01 MiB(인덱싱·저장 오버헤드 제외). 세 문자열 버퍼·Arrow/pandas batch·검증 임시객체를 감안해 <=512 MiB 작업 증분을 계획 목표로 두되 보장값이 아니다. 현재 가용 RAM/총 RAM/병행작업/예상 peak와 근거를 실행 직전 새로 기록한다. 예상량을 넘거나 여유가 모자라면 중단/청크 축소한다.
5. 출력은 round004 통합 담당이 따로 고정한 path의 신규 sidecar만. 원자료/cache/canonical 쓰기는 금지. 실제 명령/exit/stdout/stderr, 입력·출력 hash, Python/Pandas/Arrow 버전, peak RSS와 OS RAM을 기록하고 별도 독립 scan으로 검산한다.
6. 모든 대상 월/선별 행이 지원 문법이면 그 제한된 population에 대한 B-adapter 사용 허용을 감독이 별도로 판단한다. unsupported가 하나라도 있거나 분류 불확실하면 B를 닫고 A방식(전역 원본 ID Series 처리 후 살아남은 date Series 처리 + feature batch) 검토로 돌아간다. 성공해도 이 gate는 참조/점수 실행 승인이 아니다.
