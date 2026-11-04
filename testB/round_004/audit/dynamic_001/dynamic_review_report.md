# Round004 V 독립 동적 검산 보고서

## 판정

동적 검산과 보고 산출물은 완료했다. 검산 스크립트의 최종 실제 exit는 2이며, bounded loader의 전체 단계 fail-closed 및 trace 메모리 주장은 통과하지 못했다. 이 감사 완료는 생산 adapter PASS를 뜻하지 않는다.

요청 설정은 GPT-6 Luna / xhigh이고 provider 내부 model·effort는 확인할 수 없어 unknown으로 기록했다. 확인한 ORCA_CLI_COMMAND는 C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe, 버전은 1.4.246이다. skills get orchestration --json 및 skills get orca-cli --json 안내 조회는 exit 0이었다.

## 고정한 입력과 실행 범위

- E 첫 작업 msg_dd0fa18d7756 및 최신 후속 msg_cf5c24f09425는 둘 다 succeeded로 전달되었다. 검산 직전 E 코드 hash는 bounded_loader.py=da1c5b35561ea4d7478dc169e0cf4edaa6416c0aabb87e34d418dea9a9ab11c8, compare_loader_adapter.py=f1205517b8f3995677e2e678d116fe4fa1e5a04defed6541e90a4f945f4645fe로 E manifest와 일치했다. E artifact manifest에 적힌 21개 파일도 순차 SHA 재검산 결과 21/21 일치, mismatch 0이었다.
- E execution_receipt의 최종 명령은 isolated cwd에서 PYTHONDONTWRITEBYTECODE=1 python -B compare_loader_adapter.py, 실제 exit 0, stderr 0 byte였다. 기록된 stdout은 {"fixture_equal":[true,true],"unsupported_stopped":[true,true,true,true,true,true,true,true,true],"actual_equal":true,"actual_stop":null,"actual_transform_calls":4}다. 이 PASS는 E의 fixture와 16,384행 결합 출력 비교 결과이며, 본 V는 네 batch를 각각 직접 호출해 독립 검산했다.
- 원본 4개 pinned SHA는 최종 동적 결과의 source snapshot과 모두 일치한다: run_remeasure_20261031.py=5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c, run_008_testB_20261101.py=cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8, run_005_F156_merge_20261101.py=e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4, run_cycle4_3_featAC_20261101.py=8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3.
- 실제 표본은 고정 Train month1 파일 rows_train_1.parquet, SHA 7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140의 물리 첫 16,384행만 읽었다. 투영한 10열은 row_index, rfid_id, part_dt, rfid_time, key_valid, wkt_valid, len_m, bbox_m, cen_lon, cen_lat이며 최대 batch 4,096이다. row_index == 0..16383으로 표본 선택을 손으로 확인했다. V는 네 batch를 각각 독립적인 transform_batches 호출로 대조했고 표본 전체를 E에 한 번만 넘기지 않았다.
- 나머지 Train 파일은 footer/schema metadata만 읽었다. 전체 Parquet row scan, 기존 Test 전체 scan, full key scan, 참조·점수·A·membership, 26행 합성, 실제 split 또는 외부 자료 접근은 수행하지 않았다. E의 compare_loader_adapter.py는 비교용 harness/stub이며 생산 runner의 atomic commit 경로는 없다.

## 통과한 제한 범위

- 원본 load_rows pinned AST, 독립 whole-column oracle, 명시 hand-expected 표, E adapter 세 가지가 두 달 합성 표에서 모두 일치했다. key_valid=True/False, ID/date 모두 요청·각각 단독·둘 다 생략, 명시적 key_valid/month, caller 열 순서 변경, 빈 batch, 2개월 경계, 변환 탈락 후 index hole을 포함했다. 출력 열 순서와 int64 ID, int32 date, bool flags, int8 month dtype도 같았다.
- ID-only 호출에서 날짜의 비정수 토큰을, date-only 호출에서 ID 비정수 토큰을 확인하지 않는 경우와 key_valid=False인 malformed ID/date 행을 먼저 제외하는 경우가 합성 입력에서 일치했다. 두 numeric 열을 생략한 요청, key/month만 요청, 월 열을 명시한 요청, caller 열 순서 변경도 AST/oracle/adapter 결과가 같았다.
- 두 달 핵심 fixture의 key_valid=True 행에 rfid_id=abc와 part_dt=1.5를 함께 넣었다. ID coercion/drop가 먼저 적용되므로 해당 행의 unsupported 날짜는 이후 검사에서 제외되고 세 결과가 일치했다. 이 fixture가 ID 제외 뒤 date 변환 순서를 직접 구별한다.
- 합성 핵심표의 명시 index 결과는 key_valid=True에서 [0,3,4,5], False에서 [0,1,4,5,6,8]이며 세 구현이 그대로 보존했다. 이는 key filter 뒤의 월 간 concat ordinal을 전달하고 numeric drop 뒤의 index 구멍을 남기는 순서를 확인한다.
- Python None과 IEEE NaN을 ID/date 각각에 넣은 제한 fixture에서 AST, oracle, adapter가 모두 같은 빈 결과와 dtype을 냈다. 단, 빈 결과를 실제 출력 chunk로 제공하는 동작은 별도 미확인이다.
- 실제 16,384행 표본에서 AST와 독립 whole-column oracle의 엄격 비교는 통과했다. 네 adapter 호출은 물리 offset 및 concat ordinal [0,4096), [4096,8192), [8192,12288), [12288,16384)를 각각 처리했고, 모두 4,096행 admitted/output, 제외 0, index 라벨 구간도 각각 같았다. AST·adapter serialization SHA가 모두 0e70ea62112fc29e1feda89cb61e620c5b40e4558a99ae235a3fe08ad364c581이었다. 엄격한 pandas frame comparator는 전체 출력에서 RangeIndex 대 Index의 컨테이너 class 차이만 보고했다. 독립 비교로 columns/order, values, dtypes, NaN 배치, index dtype 및 라벨이 모두 같음을 확인했으며 index reset은 하지 않았다.
- 실제 unsupported-token 시험의 19개 문자열 fixture는 모두 adapter가 첫 yield 전에 UnsupportedDomain으로 중단했다. 여기에는 ID의 ±2^53 초과, 소수, scientific notation, 앞/뒤 공백, 비ASCII Unicode, 129자 문자열, int64 초과와 date의 소수/scientific/공백/Unicode/129자 및 int32 양쪽 초과가 포함됐다. 원본은 이 중 16개를 받아 변환 또는 wrap했고 3개 Unicode junk는 drop했다. 예: ID 1.5 → 1, 1e3 → 1000, 9223372036854775808 → -9223372036854775808; date 20250101.5 → 20250101, 2147483648 → -2147483648. 이 차이가 좁은 안전 도메인 밖에서 보수적으로 중단해야 하는 이유다. ASCII ID 001, +2, -0004 및 ID ±2^53 양끝, date int32 양끝은 핵심 fixture에서 확인했다.
- key_valid=False인 1.5 ID / 2.025e7 date 행은 원본과 adapter 모두 numeric validation 전에 제외했고 오류 없이 0행을 냈다.

## 확인된 실패 및 unknown

### 실패: trace=None이어도 월별 output index를 전부 보유

transform_months는 매월 local_trace=[]를 만들고, caller trace가 None이어도 이를 transform_batches(..., trace=local_trace)에 넘긴다. 각 batch trace의 output_index list가 월 처리가 끝날 때까지 남는다. 3개 batch 합성 관측에서도 trace=None일 때 retained record/index 수가 1 → 2 → 3으로 증가했다. 이는 batch-only memory bound가 아니라 O(월 output 행 수)다.

현재 Train footer에서 가장 큰 달은 773,405행이다. 64-bit CPython의 index 정수 28 byte와 list pointer 8 byte를 기준으로 한 보수적 payload 추정은 773,405 × 36 = 27,842,580 byte, 약 26.55 MiB다. 실제 peak 측정은 아니며 dict/list header, allocator 여유 등은 제외한다. 전체 행이 output으로 남는 가정 아래의 월별 index 보유량 추정이고, full Train 실행은 하지 않았다.

### 실패: late unsupported에서 이전 batch가 먼저 yield됨

정상 1행 batch 다음에 ID 1.5를 둔 독립 synthetic 입력은 첫 batch 1행을 이미 yield한 뒤 후속 오류 rfid_id row 1: unsupported token '1.5'를 냈다. transform_batches 자체에는 staging, rollback, quarantine, atomic commit이 없다. 따라서 caller가 yield 결과를 최종 산출물로 바로 쓰면 전체 stage fail-closed가 아니다. 안전한 stage 결과를 주장하려면 caller가 임시 sink에 격리해 전체 성공 후 commit하는 동작이 별도로 필요하지만 runner에서 확인되지 않았다.

### Unknown: empty stream과 exact pandas index class

빈 month 한 개 및 모든 month가 빈 경우 canonical/oracle은 schema가 있는 0행 frame을 만들지만 adapter stream은 chunk를 하나도 내지 않아 해당 frame을 materialize할 수 없다. caller 계약에 빈 결과 schema가 없어 pass로 추정하지 않았다. 빈 months 목록의 ValueError: No objects to concatenate는 canonical/adapter에서 같았다.

실제 표본의 adapter output은 index 라벨/값과 dtype이 같고 serialization SHA도 같지만, 결합된 chunk의 pandas index container class가 RangeIndex가 아닌 Index다. 후속 caller가 pandas index class 자체에 의존하는지는 확인되지 않았다.

## 계보 및 이력 보존

Round002 pinned history는 Train 3,887,069행, 기존 Test 4,212,389행을 기록한다. 여섯 Train parquet의 footer 합도 3,887,069행(월별 497,942 / 479,290 / 657,292 / 717,294 / 761,846 / 773,405)으로 Train 이력과 일치한다. E 초안의 4,212,389는 Test 기존 합계와 같은 수이므로 full Train scan 계약으로 채택하지 않는다. 이번 작업은 Test parquet row를 읽지 않았다.

Round003 E failure exit 2 및 V fixture-failure reproduction audit exit 0/succeeded는 그대로 유지한다. Round002 초기 FAIL, delta PASS10/exit 0, historical 44 hash unknown도 계승한다. 이번 audit script exit 2는 V의 생산 PASS가 아니라 bounded-loader 실패 발견을 기록한 exit다.

## 실행 및 RAM 증거

최종 실행 전 2026-11-05 06:42:34 KST에 host RAM 5,906.4 / 14,140.9 MiB free/total이었다. 예상 Python peak은 512 MiB, host reserve는 1,024 MiB, 시작 기준은 1,536 MiB였다. Orca/Explorer/Codex 및 기타 process RSS가 관측됐지만 소유/부하 귀속은 unknown으로 두었고 어떤 process도 종료하지 않았다. 표본 run 후 host free 5,897.9 MiB, Python peak RSS 125.46 MiB, process commit peak 618.65 MiB였다. Host free, RSS, commit은 다른 지표이며 이 작은 run은 full-scale safety guarantee가 아니다.

최종 명령은 isolated cwd에서 PYTHONDONTWRITEBYTECODE=1 python -B <absolute independent_dynamic_check.py>였고 실제 exit 2, stdout은 attempt03_python_stdout.log, stderr는 0 byte (attempt03_python_stderr.log)다. Attempt01은 잘못 공유된 AST fixture 때문에 API/sample 비교가 거짓 실패한 초안이며 보존했다. Attempt02는 그 harness 문제를 고친 중간 결과이고 pandas index container 차이가 strict comparator에 잡혔다. Attempt03은 oracle의 무탈락 RangeIndex 처리를 보정하고 index label comparator를 추가한 최종 결과다. 모든 시도별 실제 exit/stdout/stderr hash 및 RAM preflight는 함께 보존했다.
