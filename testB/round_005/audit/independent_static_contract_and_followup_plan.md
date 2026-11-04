# Round005 V — 독립 정적 계약 검토와 후속 동적검산 계획

작성: 2026-11-05 KST. 역할은 독립 정적검토자 V다. 요청 모델/effort는 GPT-6 Luna/xhigh이며 provider 내부 실제 model·effort는 unknown이다. 이 문서는 정적 필요조건과 별도 followup 실행계획만 고정한다. E가 새 loader/caller를 작성 중이므로 변경 중 snapshot은 실행하지 않았다. 최초 확인 시 `round_005/execution/`은 비어 있었고, 07:12:01에 나온 `bounded_loader.py`를 이후 읽기 전용으로 정적 검토했으나 caller 산출물은 확인되지 않았다.

## 확인한 입력·계보·범위

UTF-8로 `AGENTS.md`, `testB/USER_DIRECTIVE_20261105.md`, `ROUND_PROTOCOL.md`, `SUCCESS_CRITERIA.md`, `round_005/ROUND_PLAN.md`, `round_004/NEXT_ROUND.md`, `round_004/ROUND_REPORT.md`, `round_004/execution/bounded_loader.py`, `round_004/execution/domain_and_equivalence.md`, `round_004/audit/independent_static_review.md`, `round_004/audit/dynamic_001/dynamic_review_report.md`, Round004 E의 attempt03 stdout/exit/receipt와 V의 attempt03 stdout/receipt를 직접 읽었다.

기록 보존: Train 6 footer 합계는 3,887,069 (월별 497,942 / 479,290 / 657,292 / 717,294 / 761,846 / 773,405)이다. Round004 E 초안의 4,212,389는 기존 Test 합계 오류이고 Train domain은 unknown이다. Round004 E attempt03 제한 비교는 actual exit 0 및 stdout `fixture_equal=[true,true]`, `unsupported_stopped` 9건 true, `actual_equal=true`, `actual_transform_calls=4`였지만 이는 제한 fixture 및 month1 물리 첫 16,384행/10열/4096 batch 표본 결과다. Round004 V attempt03 stdout은 `overall_dynamic_loader_gate=FAIL`; actual exit 2이며 감사 task succeeded와 생산 gate 성공은 별개다. 원인에는 trace=None 월별 output index 누적, late unsupported 이후 앞 batch 1행 yield, empty stream의 빈 schema 미구현, strict pandas index container class 차이가 포함된다. Round003 E exit2/생산 실패, V 실패재현 fixture exit0/audit succeeded/단일 결합 16,384행 한계와 stub runner, Round002 최초 FAIL·별도 metadata-only delta PASS10/exit0·역사 44 hash unknown도 계승한다. 기존 Test 46,705행 전수대조와 26행 합성은 반복하지 않는다.

## 원본 SHA·AST/API 직접 확인

`Get-FileHash -Algorithm SHA256`으로 아래 네 pinned 원본을 다시 계산했고 모두 일치했다.

| 원본 | SHA-256 |
|---|---|
| `D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py` | `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c` |
| `D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py` | `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8` |
| `D:/repos/fishing-track-classification/code/tools/run_005_F156_merge_20261101.py` | `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4` |
| `D:/repos/fishing-track-classification/code/tools/run_cycle4_3_featAC_20261101.py` | `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3` |

직접 판독한 canonical `load_rows` (첫 모듈 442–480행)의 계약: 요청에서 `month`를 빼고, `key_valid`는 미요청이어도 투영 및 출력에 추가한다. 각 월에서 `pq.read_table(..., columns=list(needed)).to_pandas()`를 읽어 `key_valid_only=True`면 필터한 뒤, 월 물리 순서로 `month=np.int8(month)`를 붙여 쌓고 `pd.concat(..., ignore_index=True)`한다. 요청에 `rfid_id`가 있으면 연결 전체 Series에 `pd.to_numeric(errors="coerce")`, NaN행 drop, `int64` cast를 하고, 그 뒤 요청된 경우 남은 행의 전체 `part_dt`에 같은 coercion/drop 및 `int32` cast를 적용한다. 두 변환은 요청 열이 없으면 생략된다. drop은 기존 concat index를 재설정하지 않아 hole을 남긴다. 빈 `months`는 `pd.concat([])` 오류 경로다. 요청열 순서를 그대로 반환한다고 가정할 수 없다.

`rg -n`으로 실제 caller도 재확인했다: Round008 harbor/gap/density 경로와 `_train_arrays()` → `_load_year_arrays()` 및 Round005 `_train_arrays()` cache / `_build_t5_dicts()` 관계가 확인됐다. 별도 kwargs가 없는 경로는 기본 `months=MONTHS`, `key_valid_only=True`를 따른다. 즉 이 계약은 단순 parser 결과만이 아니라 투영열·implicit key_valid/month·caller output 사용에 맞아야 한다.

## 정적 필요조건 및 판정

제한 adapter의 조건부 동등성 주장은 실제 domain 관측과 분리해야 한다. 후보 grammar는 ASCII `[+-]?[0-9]+`, ID 범위 `[-2^53,+2^53]`, date signed int32다. 이 제한 안에서는 float64 중간 경로가 있어도 정수를 정확히 표현할 수 있다는 논증이 가능하나 실제 Train 전체 도메인이 이 범위에 속한다는 근거는 아직 없다. null/NaN/pd.NA 및 명백한 nonnumeric의 원본 coercion/drop mask는 별도로 고정해야 한다. numeric-like unsupported 값(소수/scientific/공백·Unicode 숫자/범위 초과/길이 상한 위반)을 정상 drop으로 위장하면 안 되고 전체 단계 중단 조건이다. unsupported가 ID-invalid 행의 date에만 있으면 원본의 순서상 date를 검사하지 않는다는 점도 필요하다.

| 항목 | 정적 판정 |
|---|---|
| Canonical 변환 순서·값·dtype·NA/drop·월/물리순서·index hole | 고정 가능; 새 E 경로 판정은 미확인 |
| batch별 offset/admitted count | offset은 key-valid admission 후의 실제 concat ordinal 누적만으로 계산; list 길이·입력 raw row 수로 대체 불가 |
| trace 보유량 | debug=False/trace=None에서는 output index/row별 trace 구조를 생성하지 않아야 함. debug=True도 O(batch) streaming sink 또는 명시 상한 K 이하. 월 전체 trace list는 FAIL |
| empty API/schema | `months=[]`의 canonical concat 오류 보존. 빈 물리 batch/빈 월/모든 월 empty는 요청열 및 implicit `key_valid`/마지막 `month:int8`을 포함한 exact empty schema와 index class 검증 필요 |
| exact index | 무탈락 결과의 RangeIndex와 숫자 drop 뒤 hole-bearing Index를 `assert_frame_equal` 등 index type 엄격 비교. 라벨만 같은 것을 strict equality라 하지 않음; reset_index 금지 |
| 실제 domain | UNKNOWN; Train 합계/월 footer만으로 domain·coverage 증명 불가 |
| 생산 승인 | 미승인. 새 caller의 transaction 경로 및 동적 부정검사가 아직 필요 |

### Round005 변경 중 loader snapshot 정적 관찰 (미실행)

07:12:01 snapshot `round_005/execution/bounded_loader.py`는 `transform_months`에서 월별 local trace list를 없애고 각 batch를 `trace=None`으로 호출한다. `transform_batches`에서 offset을 key_valid filter 뒤의 admitted row 수로 증가시키며 숫자 drop 뒤에도 시작/끝 ordinal을 attrs에 둔다. 이 구조는 Round004의 O(month output) trace 원인을 정적으로 제거하는 방향이다. Trace list는 `trace_limit`에 의해 제한되고 callback은 streaming 전달이지만 callback 소유자가 데이터를 쌓지 않는다는 보장은 별도 sink 계약이 필요하다. 구현 동작은 미실행이므로 결과 판정은 unknown이다.

07:12:30에 새로 나타난 `isolated_stage.py`도 실행 없이 읽었다. generator의 earlier yield를 stage_dir 안의 parquet part로 순차 기록하고 성공 종료 후만 directory rename을 호출하며 예외 시 quarantine하는 구조는 부분 yield와 caller 게시를 분리하는 방향이다. 다만 다음 조건은 정적 위험/미충족으로 남아 동적/코드 수정 검토가 필요하다.

- 성공 시 stage 안에 저장하는 `manifest.json`은 rename 전에 `published:false` 상태로 직렬화된다. 이후 메모리의 dict만 `published:true`로 바꾸고 반환하므로 공개된 manifest는 실제 commit 성공과 모순된다. 공개 manifest의 성공 의미와 fail path quarantine manifest를 별도로 검증해야 한다.
- 기본 commit은 `os.replace`이고 final 존재를 사전 및 commit 직전 확인하지만 check-then-rename 경쟁창이 있다. 플랫폼에서 기존 빈 directory를 replace할 수 있는지 여부에 무관하게 계약은 no-clobber 원자적 게시를 요구하므로 target 생성 경쟁 부정검사에서 기존 target의 바이트/hash 불변을 입증해야 한다. 주입 commit 함수는 실패 상황 시험에는 유용하지만 성공 경로에서 원자성 증거로 취급하지 않는다.
- `batches`가 0개(또는 전부 None)이면 schema/dtype이 있는 part 없이 `columns`/`dtypes`가 null인 manifest를 성공 게시한다. 이는 all-empty canonical schema 계약을 충족하지 못한다. zero-row RecordBatch가 들어오는 경우의 parquet schema는 별도 경로이며 둘을 나눠 시험해야 한다.
- 성공 시 `__canonical_index__`를 Parquet column으로 보존하고 batch별 index class/dtype/name/경계값을 manifest에 보관하는 방향은 확인했다. 다만 실제 재구성된 exact pandas index class와 labels는 검증되지 않았고, schema/name 충돌 열이나 중복 요청열도 확인되지 않았다.
- `_paths`는 root 아래 path와 기존 final을 사전 거부하려는 경계다. symlink/path traversal/허용 root 자체/다른 volume을 대상으로 쓰기 전 차단하는지, quarantine root가 예상 경로로 유지되는지는 부정검사 대상이다. `stage_dir.mkdir()`가 try 이전이므로 scratch 생성 실패는 후속 quarantine/receipt 경로와 구별해 확인해야 한다.

이 caller는 late unsupported/중간 오류에서 generator가 이전 yield를 취소한다고 주장하지 않는다. 요구되는 핵심은 앞선 parts가 private scratch에만 남고 최종 결과와 manifest가 게시되지 않는 것이다. 위 항목은 미완성 snapshot의 정적 결함/unknown 목록이며 E의 최종 결과 판정은 아니다.

## 별도 동적 followup 계획 (이번 task에서는 미실행)

선행: E가 worker_done, 최종 source file hash, 실제 exit/stdout/stderr 및 manifest를 제출한 뒤 새 followup dispatch를 연다. 시작 직전 fresh RAM, 예상 증분 256 MiB + 512 MiB 여유 계획, E/host 병행 작업, 근거·시각을 기록한다. 이는 계획치이지 peak 상한 보장이 아니다. 부족하면 가능한 정적 작업을 우선하고 재개 직전 재확인하며 batch 축소/순차화를 택한다. polling/watch·사용자 프로세스 종료 금지. E 산출물은 읽기 전용, 신규 파일은 `round_005/audit/`에만 쓴다.

독립 비교의 세 축: (1) SHA 고정 canonical `load_rows` AST를 in-memory namespace에 추출해 작은 고정 Arrow 입력만 주입, (2) E parser/helper/comparator를 import하거나 복제하지 않은 독립 whole-column oracle로 canonical 월/물리순서·필터·global concat·ID 전체 변환/drop/cast 후 남은 date 변환/drop/cast 구현, (3) 미리 손계산해 fixture에 고정한 expected 값·열·dtype·NA·mask·index. 먼저 (1)(2)(3)이 서로 일치해야 E 비교를 시작한다. 모든 시도는 isolated scratch에 두고 E 코드를 oracle로 재사용하지 않는다.

고정 fixture 행렬: `no_numeric_keys`; ID-only/date-only/both; implicit 및 명시 `key_valid=True/False`; `month` 요청 및 미요청; 호출 열 순열; 다월 물리순서/월 경계/빈 물리 batch/빈 월/모든 월 empty/`months=[]`; 유효/무효 ID와 ID 탈락행에만 있는 unsupported date; null/None/NaN/pd.NA/명백한 nonnumeric; ASCII 부호·leading zero/2^53 양끝과 바깥 값, date int32 양끝/바깥 값, decimal/scientific/공백/Unicode/length-limit. 매 케이스에서 canonical과 exact expected에 대해 행 수·행 순서·열·각 값·dtype·NA 위치·drop mask·index class/라벨을 비교한다. 요청 키 미포함 때 해당 conversion이 생략되는지도 관찰한다. `month:int8`, `key_valid` bool 및 raw feature dtype 보존을 확인한다. unsupported input은 행 삭제로 통과하지 않고 전체 시도 fail-closed여야 한다.

Bounded trace 검사에서는 batch 크기 B, admitted count A, trace cap K, emitted record count, 보유 index 수를 호출 전후에 기록한다. 여러 월의 길어진 연속 generator 소비에서도 debug=False는 retained row/index trace가 0, debug=True는 sink 밖 메모리 O(B) 또는 사전고정 K를 초과하지 않는지 확인한다. batch offset이 `누적 admitted count`와 일치하는지 admission/drop 및 월 경계에서 검증한다. 작은 측정만으로 full-scale RAM 안전을 주장하지 않고 테스트 코드의 보유 구조 + RSS 관측을 분리 보고한다.

Generator와 caller transaction은 별도 검증한다. 정상 batch를 먼저 yield하고 뒤 batch에서 unsupported/임의 예외를 발생시킨 경우, generator가 이전 부분 yield를 되돌릴 수 있다고 주장하지 않는다. caller가 부분분을 신규 unique scratch/quarantine 가능한 위치에만 기록하고, 전체 generator·검증이 성공한 뒤에만 최종 경로로 게시하는지 확인한다. 금지된 전체 DataFrame RAM buffer 없이 batch 순차 write가 필요하다. 최종 결과 파일과 manifest의 commit 순서도 stage 복구/완료표시가 일관되게 crash-safe인지 검증한다.

원자적 게시 경계와 부정검사: 최종 경로는 사전에 고정한 허용 workspace 하위 신규 경로여야 하며, scratch와 같은 filesystem의 atomic no-clobber rename/commit 경계를 사용한다. 기존 final 경로 sentinel hash를 사전에 기록하고, 충돌 시 fail-closed해 내용을 바꾸지 않아야 한다. 부적절 경로(허용 root 밖, root 자체, directory target, symlink 또는 path traversal)는 write 전 거부한다. 정상 배치 뒤 late unsupported, 중간 batch 예외, scratch write 실패, stage mkdir 실패, commit/rename 실패, final path 사전 존재, commit 직전 target 생성 경쟁, 잘못된 stage/dataset, path traversal/symlink를 각각 분리 주입한다. 같은 volume 요구도 별도 확인한다. 각 실패에서 기존 최종 파일 바이트/hash·manifest가 불변이고 불완전 final 없음, scratch가 명시 quarantine에 보존됨, quarantine/실패 receipt가 최종 산출물로 노출되지 않음, 성공 status/manifest가 게시되지 않음을 검증한다. 정상 케이스만 전체 지원조건 확인 뒤 atomic commit을 하고 공개된 manifest가 commit 성공을 올바르게 서술하는지 및 정확한 새 final file set/hash를 확인한다. commit 실패가 scratch 생성 실패나 late unsupported와 같은 오류로 뭉뚱그려지면 안 된다.

실제 sample은 이번 followup에서 자동 실행하지 않는다. 새 E 경로 변경으로 재검사가 필요하다고 판단될 때만 월 1, 첫 16,384 physical rows, 10 columns, 최대 4,096 batch, 기존 고정 입력 SHA `7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140`를 사전 고정한다. 변경한 adapter/caller 경로 확인이 재검사 이유다. 별도 followup에서 fresh RAM gate 후 각 batch를 독립적으로 처리하고 canonical AST·독립 oracle·expected와 비교한다. 이는 표본 한정 증거다.

## 메모리·실행 증거

2026-11-05 07:09:55 +09:00 fresh host RAM 관측: CIM free 5,559 MiB / total 14,140.9 MiB. 정적 검토 증분 계획 256 MiB + 512 MiB 여유; 동시 E 작은 작업 계획 512 MiB + 별도 512 MiB 여유. E가 새 loader/caller를 편집 중이나 정확한 RSS 귀속/peak는 unknown이며 이 RAM snapshot은 보장 상한이 아니다. 예상치는 텍스트 문서/소스 직접 판독에 근거한 계획치다. 이번에는 loader 실행, fixture/실제 sample, parquet/source scan, full key scan, 참조/새 점수/A/membership, Test fit, score, 생산 호출을 하지 않았다.

확인 명령: `& $env:ORCA_CLI_COMMAND skills get orchestration`; `& $env:ORCA_CLI_COMMAND skills get orca-cli`; `Get-Content -Encoding UTF8`; `Get-FileHash -Algorithm SHA256`; `rg -n` canonical 함수 및 caller 위치 확인. `ORCA_CLI_COMMAND`는 `C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe`로 확인했다. 도구 설정 조회는 종료코드 0이었다. E의 수정은 하지 않았고, 발견한 미확인 gate는 E 완료 후 독립 동적 검산 및 감독의 후속 key-only domain 계약 전까지 열려 있다.

## 보존해야 할 domain·성공 범위 제한

Train footer 3,887,069 / Test 4,212,389 불일치, 전체 Train domain unknown 및 위 과거 round 결과를 유지한다. unsupported 행을 임의 제외하지 않는다. 필요할 경우 전역 key 변환 A 방식(원본 순서대로 전체 ID, 이후 ID 생존 행의 전체 date 변환과 feature 청크)을 감독이 별도 RAM gate로 검토한다. 원본 변환 순서·값·dtype·NA/drop·정렬 동점·라벨·상수는 바꾸지 않는다. 사고 신원/정상 근거/개발 사용/공식 수식 부재를 후보나 합의로 채우지 않는다. 임계값/B/C/사고 여부/성능/제출/실제 split/사고파일 개발 사용/외부수집·연락/push 및 이번 실행 범위 밖의 모든 scan은 미실행이다.
