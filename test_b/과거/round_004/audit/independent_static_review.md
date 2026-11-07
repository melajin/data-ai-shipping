# Round004 V 독립 정적 필요조건 검토 — 2026-11-05

## 범위와 판정

**정적 필요조건 검토 완료. 제한 정수 도메인 논증은 조건부 통과, actual data coverage·E 구현·동적 동등성은 unknown이며 생산 loader 사용은 보류다.** canonical loader AST 실행, E 코드 실행, fixture, parquet/CSV/전체 key scan, 큰 Test scan, 26행 합성, 참조·실점수·A·membership는 수행하지 않았다. 원자료/canonical/cache/선행 round는 읽기 전용이며 내 산출물은 `round_004/audit/` 아래에만 둔다.

Orca 설정은 `ORCA_CLI_COMMAND=C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe`다. 실제 `skills get orchestration --json` 및 `skills get orca-cli --json` 안내를 읽었다. 이번 task의 요청/launch 설정은 GPT-6 Luna/xhigh; provider 내부 model/effort는 unknown이고 요청 설정을 실행 증거로 확대하지 않는다.

## Canonical SHA와 직접 확인한 호출

네 파일의 SHA-256을 직접 다시 계산했고 모두 pinned 값과 일치했다.

| 원본 | SHA-256 | 직접 확인 |
|---|---|---|
| `D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py` | `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c` | `load_rows` 구현/호출 |
| `.../run_008_testB_20261101.py` | `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8` | train harbor/density/gap builders |
| `.../run_005_F156_merge_20261101.py` | `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4` | `_train_arrays` cache, `_build_t5_dicts` |
| `.../run_cycle4_3_featAC_20261101.py` | `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3` | `_load_year_arrays` load columns, WKT mask/RFID sort |

`load_rows(dataset, columns, months=MONTHS, key_valid_only=True)`에서 `month`는 caller 요청열에서 제외되어도 내부 반환에 붙는다. `key_valid`도 요청에 없으면 parquet projection과 반환 열에 추가한다. 월별로 `pq.read_table(columns=...).to_pandas()` 후 key_valid_only이면 concat 전에 필터한다. 월 물리순으로 붙이고 `month:int8`를 설정한 뒤 `pd.concat(ignore_index=True)`한다. 연결된 전체 `rfid_id` Series를 먼저 `pd.to_numeric(errors="coerce")` → NaN 행 제거 → `int64` cast, 그 다음 남은 행의 전체 `part_dt`를 동일 변환 → NaN 제거 → `int32` cast한다. drop 후 원래 concat index의 구멍은 보존된다. 요청열에 key가 없으면 그 변환은 생략된다. 반환 열은 호출열 순서와 같다고 가정할 수 없다.

Builder 호출 columns/kwargs 직접 확인 결과(별도 kwargs 없음: `months=MONTHS`, `key_valid_only=True` default):

- Harbor: `load_rows("train", ["rfid_id", "cen_lon", "cen_lat", "len_m", "bbox_m", "wkt_valid"])`.
- Density: `m._train_arrays()` → `_load_year_arrays("train")` → `load_rows(dataset, ["rfid_id", "part_dt", "rfid_time", "len_m", "bbox_m", "cen_lon", "cen_lat", "wkt_valid"])`; cache는 `_TRAIN_ARRAYS`이고 `_build_t5_dicts`도 이를 소비한다.
- Gap/jump: `load_rows("train", ["rfid_id", "part_dt", "rfid_time", "cen_lon", "cen_lat", "wkt_valid"])`.
- Own moorings: `load_rows(dataset, ["rfid_id", "cen_lon", "cen_lat", "len_m", "bbox_m", "wkt_valid", "rfid_time"])`.

`columns=["rfid_id"]`도 implicit key_valid/month 반환을 갖는다. 빈 월 목록은 원본 `pd.concat([])` 오류를 낼 수 있어 adapter가 정상 빈 결과로 바꾸면 API 차이다. 물리 빈 batch/month, 호출열별 dtype/order는 E 경로에서 별도 동적으로 확인해야 한다.

## 제한 정수 domain과 동등성 필요조건

지원 문법은 ASCII `[+-]?[0-9]+`; 부호/leading-zero 허용, 기호만 있는 token은 거부다. 선행 0을 없애고 정확한 정수 비교를 하며 float로 boundary 판단하지 않는다. raw length 제한을 둘 경우 초과는 bad row 처리하지 말고 전체 호출 fail-closed다.

- ID: 정규화한 정수 `abs(ID) <= 9,007,199,254,740,992 (=2^53)`.
- date: `-2,147,483,648 <= date <= 2,147,483,647`.
- 이 유효 집합 안의 정수는 global numeric inference가 int64/uint64 또는 null/nonnumeric로 float64 승격이어도 정확하다. batch별 추론 타입이 다를 수 있어도 null/invalid mask가 같고 마지막 정수 cast를 하면 ID int64/date int32의 값은 같다는 조건부 논증이 가능하다. 현재 실제 source가 이 domain을 만족하는지는 확인하지 않았다.
- null/NaN/pd.NA와 명백한 nonnumeric는 원본 `errors="coerce"`와 같은 제외 후보지만 정의와 mask를 명시해야 한다. numeric-like·원본이 숫자로 받아들이는 미지원 값과 혼동하면 안 된다.
- `1.0`, `1.5`, `1e3`, whitespace 숫자, int32 overflow, `2^53` 초과, Unicode 숫자 등은 지원 문법 밖일 수 있다. 이를 invalid 행처럼 silently 삭제하면 안 된다. 해당 값이 발견되면 whole transform/loader를 fail-closed해야 한다. 원본 float/cast/overflow 동작을 임의 교정하지 않는다.

순서는 월/물리 순회 중 key_valid admission → admission 후 global concat ordinal → 전체 ID 변환/NaN ID drop/int64 → ID drop 뒤 남은 행에만 date 검사/변환/NaN drop/int32 → feature 행과 원 index hole 보존이다. ID 불능 행의 unsupported date를 먼저 검사하여 실패시키면 원본이 date를 보지 않는 순서와 달라진다. 월별 batch-local index를 출력하거나 마지막 reset_index하면 안 된다.

## 정적 판정

| 항목 | 판정 |
|---|---|
| Canonical 4 SHA와 builder 요청열/default kwargs 직접 추적 | PASS |
| 좁은 integer domain에서 global/batch 최종 숫자값 동등성 | 조건부 PASS, 실제 domain 관측 없음 |
| null/명백한 nonnumeric 세분화 및 bad mask | UNKNOWN; adapter·fixture 미검토 |
| numeric-like unsupported values fail-closed | 요구조건 명시; E 구현/부정시험 UNKNOWN |
| ID 후 date 변환, concat ordinal/index holes | canonical 동작 PASS; E 경로 UNKNOWN |
| requested columns, empty batch/month, dtype/NaN 경계 | canonical API 일부 정적확인; E 경로 UNKNOWN |
| 실제 전체 domain, multi-batch, 메모리 peak, reference/score/A/Testfit | UNKNOWN 또는 미실행 |

## Round002/003 증거 계승

Round003 E 최종 비교는 actual exit 2 / failed였다. V의 별도 실패 재현 audit은 canonical `load_rows` AST와 independent oracle로 알려진 반례를 재현했고 fixture actual exit 0 / audit task succeeded였다. 생산 동등성 성공을 의미하지 않는다. 16,384행은 8,192행 두 입력 batch를 합친 한 Table 변환이므로 batch 증거가 아니며 runner는 production builder 없는 default-deny stub이었다.

Round002 최초 독립감사 FAIL/exit1과 별도 metadata-only delta PASS10/exit0를 각각 보존한다. 역사 44-hash의 최초 의미/기록 시점과 byte restoration은 unknown이다. 기존 V fixture를 반복 실행하지 않았고 이번 검토는 source 재해시와 직접 정적 코드 읽기로 독립 확인했다. E output이 아직 없어 이번 runtime 검증은 수행되지 않았다.

## RAM 및 실제 작업

정적 검토 RAM 관측(KST, host aggregate): 05:53:34 3,893.9 MiB free; 05:54:05 4,090.4; 05:54:16 4,097.2; 05:54:27 4,040.9; 05:54:43 4,084.5; 05:55:04 4,118.8; 05:56:01 3,911.7. 정적 텍스트 검토 증분 ≤256 MiB 추정 + 512 MiB 여유로 계획했다. E 동시 작업은 ≤512 MiB + 별도 512 MiB 여유 추정이며 정확한 host 작업 귀속은 unknown. peak는 미측정, 안전 보장은 아니다. polling/watch 또는 사용자 프로세스 종료는 없었다.

UTF-8 `Get-Content`, `Get-FileHash -Algorithm SHA256`, 원본 call-site `rg -n`/직접 line 판독, Orca 선택 실행파일의 두 `skills get` 명령을 사용했다. 실제 명령 결과와 확인 hash는 manifest에 남긴다. 테스트/fixture/production call 및 큰 자료 스캔은 하지 않았다.

## E 완료 후 별도 followup

[followup_dynamic_review_plan.md](followup_dynamic_review_plan.md)에 별도 task의 독립 oracle/원본 AST 비교, 신규 fixture 행렬, 실제 multi-batch sample 검산 기준을 적었다. E 코드를 복제한 oracle 하나로 독립성을 주장하지 않는다. 해당 followup도 audit/만 수정하고 production 수정은 E에게 요청한다.

임계값/B/C/사고여부/성능/제출/실제 split/사고파일 개발 사용/외부수집·연락/push는 수행하지 않았다.
