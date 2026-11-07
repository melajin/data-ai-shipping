# Round005 V 후속 — 독립 동적 검산 보고

작성: 2026-11-05 KST. 요청 설정 GPT-6 Luna/xhigh, provider 내부 model/effort unknown. 수정 소유권은 이 audit/dynamic_001 아래뿐이며 E 코드·공통문서·원자료·canonical/cache는 수정하지 않았다.

## 판정

최종 독립 fixture 실행은 actual exit 0 (16 frame contract + 16 caller/atomic case), 고정 실제 sample 실행은 actual exit 0이다. 결과는 제한 fixture와 month1 첫 16,384 physical row에 대한 독립 검산이다. **생산 loader gate는 FAIL/조건부 보류**다. Arbitrary empty template의 잘못된 feature dtype 또는 index class가 거부되지 않고 공개되며, per-batch receipt metadata는 batch 수에 비례해 RAM에 누적되고 cap이 없다. Exact canonical empty template provenance와 metadata scale budget을 호출 경계에서 보장하기 전에는 general empty-schema·bounded-RAM 생산 승인을 할 수 없다.

검산 task 성공과 생산 gate 성공은 별개다. Round004 E 제한 표본 exit 0, Round004 V 최종 감사 exit 2/생산 FAIL/task succeeded, Round003 E exit 2·V 실패재현 fixture exit 0/audit succeeded/단일 결합 16,384행 한계, Round002 초기 FAIL·별도 metadata-only delta PASS10/exit 0·역사 44 hash unknown은 그대로 계승한다.

## 고정 snapshot·계보·환경

감독 확인 최신 E followup은 task `task_6ff53dda043c` / dispatch `ctx_8f62e408a6cd`, worker_done `msg_70525506a270`, succeeded였다. E 최종 SHA를 직접 검산했고 실행 전후 고정값과 일치했다.

| 입력 | SHA-256 |
|---|---|
| `round_005/execution/bounded_loader.py` | `0c60af2d4453c4ffb0a640410006e09247218a96633075cdd89567e4ae6f3cee` |
| `round_005/execution/isolated_stage.py` | `76f3f7f8e3a39a27d8c24f1d3532b83181bf2e20470da38b7543b55a04795fea` |
| `round_005/execution/verify_fixtures.py` (E hash 확인만; V는 실행하지 않음) | `61c7b9c3acddce4e904bf3b368ff8c3828a78f6344d5cfd2aee072c9219ed57f` |

canonical 4개 직접 SHA:

- `run_remeasure_20261031.py`: `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c`
- `run_008_testB_20261101.py`: `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8`
- `run_005_F156_merge_20261101.py`: `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4`
- `run_cycle4_3_featAC_20261101.py`: `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3`

`load_rows`는 pinned source byte hash 검증 후 AST에서 함수 노드만 뽑아 fake `pq.read_table`/Parquet table을 주입해 실행했다. 독립 oracle은 E helper·comparator·fixture를 import/reuse하지 않고 월 물리순서 → key filter → concat → whole ID Series coercion/drop/int64 → 남은 행의 whole date Series coercion/drop/int32를 별도 구현했다. 세 구현 비교 전 손계산 expected를 고정했다. 엄격 comparator는 `assert_frame_equal(check_exact=True, check_index_type=True, check_column_type=True, check_frame_type=True, check_names=True, check_dtype=True)`로 전체 열 순서·값·dtype·NA·index type/name/labels를 확인했고 reset_index는 하지 않았다.

환경은 `C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe` (E 영수증 기준 Orca 1.4.246), Python 3.13.3, pandas 2.2.3, NumPy 2.2.5, PyArrow 24.0.0. 선택 실행파일에서 `skills get orchestration`과 `skills get orca-cli` 안내를 읽었다. 요청 model/effort는 gpt-6-luna/xhigh, provider 내부 값은 unknown이다. canonical/E/sample 직접 pre/post hash는 `post_run_integrity_hashes.json`에 있다.

## 독립 fixture — actual exit 0

최종 command `PYTHONDONTWRITEBYTECODE=1 python -B independent_dynamic_check.py --fixtures`, actual exit 0, stderr 0 byte다. stdout은 16 frame case + 16 atomic case 및 `all_fixture_assertions_passed=true`다. 실제 stdout/stderr/exit는 `fixture_run07_stdout.log`, `fixture_run07_stderr.log`, `fixture_run07_exit_code.txt`; 상세 결과는 `fixture_result.json`이다.

Matrix에는 no numeric keys, ID-only/date-only/both, explicit/implicit key_valid 및 True/False filter, explicit/implicit month와 열 순열, 월 역순/경계/빈 달, zero-row batch, all-empty/no-batch/all-None/`months=[]`, all-numeric-drop, no-drop RangeIndex, null/None/NaN/pd.NA/clear text drop, ID 실패 행의 unsupported date 미검사, supported endpoints와 unsupported fail-closed가 포함됐다. ID ±2^53, 128-code-point leading-zero 토큰, +0/-0, date int32 양끝을 통과시켰고 decimal/scientific/공백/Unicode/범위 초과/129자 값은 첫 yield 전에 전체 중단했다.

세 구현은 16개 frame case에서 strict equality였다. 두 달 핵심 fixture surviving labels는 key_valid-only on `[0,3,4]`, off `[0,3,4,5,6]`였다. 이는 admission 후 global concat ordinal과 numeric drop 뒤 index holes 보존을 확인한다. ID-only 호출은 date를, date-only 호출은 ID를 변환하지 않았다. ID-invalid 행에 둔 `part_dt="1.5"`도 canonical 순서처럼 ID drop 이후에는 검사되지 않았다.

Canonical AST/oracle에서 만든 exact empty template로 all-empty/no-batch caller commit 후 재구성하면 strict equality였다. 반면 zero-row `wkt_valid:object` template과 zero-row `Index([])` template는 caller가 받아 commit했고 canonical bool/RangeIndex와 달랐다. Nonempty template와 wrong-column empty template는 거부·quarantine됐다. 따라서 caller의 zero-row/column shape 검사만으로 dtype/index/provenance는 증명되지 않는다.

## Trace·caller·원자성·경로

`trace=None`에서 row-index trace list가 생성·누적되지 않는 구조를 source에서 확인했고, 7-batch dynamic call에서 frame attrs에 trace state가 없었다. Debug list `trace_limit=2`는 두 record로 제한됐고 row index array가 없었다. Callback sink는 event를 즉시 넘기나 callback 소유자가 이벤트를 저장/지연할 수 있다. 이는 loader가 보장하지 않는 별도 경계다.

Caller가 앞선 generator yield를 rollback한다고 가정하지 않는 것을 검증했다. 정상 1 batch 이후 late unsupported 및 일반 예외는 scratch part만 남고 final 없음, quarantine marker/receipt 있음으로 끝났다. Parquet write, stage mkdir, commit 실패를 각각 구분했고 모두 final 부재와 quarantine을 확인했다. 사전 존재 final sentinel은 바이트/SHA 불변이었다. commit 직전 target 생성 경쟁에서 Windows no-replace rename이 거부됐고 sentinel만 남으며 partial final은 생기지 않았다. 성공 때만 parts+manifest가 있는 directory rename 뒤 final이 공개됐다. 반환 receipt는 published true이고, 공개 manifest는 published flag 대신 directory가 final에서 visible할 때만 public이라는 `publication_semantics`를 둔다.

비-testfit stage/dataset, root 자체, root 밖/`..` traversal, duplicate columns, 예약 index 열, schema 없는 no-batch 호출을 거부했다. 0-row physical batch와 batch 자체가 없는 경우도 구분했다. Wrong template의 shape 오류는 quarantine됐다.

Windows symlink 생성은 `WinError 1314`로 거부되어 실제 symlink object 검증은 미실행이다. audit scratch 안에서 directory junction fallback으로 final path escape와 quarantine-root 외부 경로를 만들어 둘 다 거부됨을 확인했고 외부 target write는 0건이었다. junction fallback 결과를 symlink 검증으로 확대하지 않는다. OS handle 기반 no-follow 경계로 악의적인 check/use 중 동시 junction 교체까지 검증한 것은 아니다.

`receipt["files"]`는 part별 metadata를 RAM에서 유지한다. 1/8/32 batch 계측 recursive Python object size는 receipt 4,691/13,375/43,232 bytes, manifest entry list 2,285/12,075/45,723 bytes였다. Cap은 없고 O(batch count)다. 현재 관측 약 1.3KB/entry를 949 batches에 곱하면 약 1.2MiB지만 이는 불완전한 추정치며 allocator·manifest serialization·경로/dtype 비용의 보장은 아니다. Frame 전체는 저장하지 않고 현재 batch 단위로 처리한다. Metadata 보유와 frame 보유를 같은 RAM 주장으로 합치지 않는다.

## 고정 실제 sample — actual exit 0

사전 선택 계약은 `fixed_sample_plan.json`, 최종 script rerun 선택은 `fixed_sample_rerun_plan.json`에 고정했다. Train month1 `rows_train_1.parquet`, physical rows 0–16,383, projection 10열 `row_index/rfid_id/part_dt/rfid_time/key_valid/wkt_valid/len_m/bbox_m/cen_lon/cen_lat`, 정확히 4 × 4,096 batch다. source SHA `7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140`는 preflight 및 실행 후 동일했다. File size 18,817,327 bytes, footer 총행 497,942; projected row_index 전체가 0..16,383이었다.

최종 command `PYTHONDONTWRITEBYTECODE=1 python -B independent_dynamic_check.py --sample`, actual exit 0, stdout `all_sample_checks_passed=true`, stderr 0 byte다. E와 canonical hash는 실행 직전/직후 모두 고정값이었다. Canonical AST와 독립 whole-column oracle이 먼저 strict equal했고, 실제 E caller가 네 원본 RecordBatch를 각각 stage/write/commit한 뒤 manifest의 index metadata와 저장된 명시 index 열로 재구성한 전체 frame도 strict equal이었다. 각 part는 4,096 admitted/output rows, RangeIndex, offsets `[0,4096)`, `[4096,8192)`, `[8192,12288)`, `[12288,16384)`였다. Output dtype: row_index int64, rfid_id int64, part_dt int32, rfid_time int16, key_valid bool, wkt_valid bool, features float64, month int8. Part SHA와 manifest SHA는 `actual_sample_result.json`에 있다.

이것은 작은 고정 sample에만 해당한다. Full Train scan, 전체-domain 적합성, 전체 stage metadata bound를 뜻하지 않는다. Train footer 합계 3,887,069 (497,942 / 479,290 / 657,292 / 717,294 / 761,846 / 773,405)을 보존한다. E004의 4,212,389는 Test 합계 오류였고 전체 Train domain은 unknown이다.

## RAM과 시도 계보

매 검사 전 `preflight_before_*.json`에 fresh RAM/작업을 기록했고 계획은 process peak 512 MiB + host reserve 1,024 MiB, 시작 최소 1,536 MiB였다. Final expanded fixture 전 free 5,962.6 MiB, final sample 전 5,713.1/14,140.9 MiB였다. Process peak RSS 136.82 MiB, peak commit/pagefile 645.5 MiB, post-run host free 5,751.5 MiB. RSS·commit·host free는 구별되며 이 작은 실행은 peak 보증이 아니다. 사용자 process 종료나 polling/watch는 없었다.

초기 harness 오류도 모두 보존했다: 1차 GetProcessMemoryInfo ctypes signature, 2차 oracle `.loc`의 Index/RangeIndex 차이, 3차 fake reader keyword, 4차 hand null-mask에서 index 5 누락, 5차 caller 이름 typo가 각각 exit 1이었다. E의 문제가 아니며 각 harness 보정 후 재실행했다. 전체 실제 exit/log/분류는 `attempt_ledger.json`에 있다. Final run은 fixture 16/16 exit0 및 sample exit0이다. Round005 E 자체의 final frame14/atomic17 exit0은 별개 제한 fixture 실행이며 V가 재사용하거나 재실행하지 않았다.

기존 final Test 46,705행 대조/26행 합성, 전수 Train/Test scan, source CSV 재파싱, reference/score/A/membership, stock CLI/main/stage, 임계값/B/C/사고 판정·성능·제출/실제 split, 사고파일 개발 사용, 외부 수집·연락, push는 하지 않았다. E의 명시 testfit caller만 synthetic fixture와 고정 제한 sample에서 실행했다.

## 남은 gate

감독은 canonical AST/원본 schema에서 온 empty template provenance를 호출 전에 강제하고, `files` metadata의 memory budget/cap을 별도로 고정해야 한다. 이후에만 새 Train key-only 전수 domain 계획을 별도 RAM gate로 승인할 수 있다. Unsupported 행을 삭제하지 않고 전체 단계 중단한다. 전체 domain은 unknown이며 이번 결과로 다음 domain gate가 자동 승인되지는 않는다.
