# Round004 E 제한 정수 adapter — 실행 결과

작성: 2026-11-05 KST. Orca 요청/launch 설정은 gpt-6-luna/xhigh이며 provider 내부 모델·effort는 unknown. 수정 소유권 `testB/round_004/execution/`만 준수했다. V의 정적 검토는 조건부 동등성만 인정하고 실제 coverage를 unknown으로 판정했다. 실행은 실제 production builder를 부르지 않았으며 아래 제한된 AST/표본 검증만 했다.

## 판정 요약

- 신규 adapter는 선언한 좁은 정수 도메인 밖 값을 행 삭제하지 않고 `UnsupportedDomain`으로 전체 단계 중단한다. 작은 synthetic fixture 두 경우(`key_valid_only=True/False`)에서 원본 `load_rows` AST와 열·행·전역 index·dtype·값/NaN이 같았다.
- 신규 실제 Train 표본에서 Parquet 물리순서의 첫 16,384행, 열 10개 projection, 최대 4,096행 batch 네 개를 각각 adapter에 따로 전달했다. 원본 AST에는 동일 표본을 한 번 ordered table로 안전 주입했다. 4회 실제 `transform_batches` 호출 추적을 남겼고, 원본·adapter의 출력 열/순서/index/dtype/값/NaN과 출력 CSV 직렬화 SHA-256이 모두 같았다. 이 표본에서는 제외행/index 구멍이 0개였고 불일치도 없었다.
- 검증 fixture exit 0은 해당 두 구현의 작은 조건/선택 표본 동등성만 뜻한다. 실제 전체 Train ID/date domain, 모든 입력에서의 동등성, loader 전체 또는 builder/reference의 production 성공을 뜻하지 않는다. 전수 key-only scan·reference·score/A/membership는 실행하지 않았다.

## 고정 소스와 API / builder 호출

원본 4개 모듈은 실행 직전 SHA-256을 다시 계산했고 Round002 pin 및 V의 static review 값과 일치했다.

| 원본 코드 | SHA-256 | 직접 추적한 요청 |
|---|---|---|
| `D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py` | `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c` | `load_rows(dataset, columns, months=MONTHS, key_valid_only=True)`. 별도 kwargs를 주지 않은 실제 builder들은 기본 인자 사용. `columns`에서 caller `month` 제외, `key_valid` 없으면 내부 요청/반환에 추가. 월별 `pq.read_table(..., columns=list(needed))`, key filter, `month:int8`, caller 열 순서 + `key_valid` + `month`, 월별 `pd.concat(ignore_index=True)`, 전체 ID `pd.to_numeric(errors="coerce")` → bad drop → int64 → 남은 행만 date 변환/drop → int32. drop 후 index hole 보존. |
| `run_008_testB_20261101.py` | `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8` | Harbor 요청열 `[rfid_id, cen_lon, cen_lat, len_m, bbox_m, wkt_valid]`; gap/jump `[rfid_id, part_dt, rfid_time, cen_lon, cen_lat, wkt_valid]`; density `_train_arrays()` + own moorings. |
| `run_005_F156_merge_20261101.py` | `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4` | `_train_arrays()`는 `_TRAIN_ARRAYS` cache를 통해 `featac._load_year_arrays("train")` 호출, `_build_t5_dicts(...)`가 해당 배열을 사용. |
| `run_cycle4_3_featAC_20261101.py` | `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3` | `_load_year_arrays(dataset)` 요청열 `[rfid_id, part_dt, rfid_time, len_m, bbox_m, cen_lon, cen_lat, wkt_valid]`; WKT mask 후 정렬/배열. |

추가 직접 확인된 builder 요청열은 gap/jump 및 harbor 외에 own moorings `[rfid_id, cen_lon, cen_lat, len_m, bbox_m, wkt_valid, rfid_time]`다. 각 호출에 months 또는 key_valid kwargs는 별도 전달되지 않는다. builder 본문은 실행하지 않았다. 원본 `load_rows` AST만 in-memory namespace에 추출했고 canonical 모듈 import/progress write는 하지 않았다.

## 제한 domain 및 동등성 논증

명세 및 범위는 [domain_and_equivalence.md](domain_and_equivalence.md)에 기록했다. ASCII `[+-]?[0-9]+`, raw 최대 길이 128, ID `[-2^53, 2^53]`, date signed int32를 제한 지원한다. 선행 0, `+`/`-`, 부호 없음이 허용된다. null/NaN/`pd.NA`와 `pd.to_numeric(errors="coerce")`가 NaN으로 분류하는 명백한 텍스트는 원본처럼 실패값으로 제외한다. coercible `inf` 같은 단어는 unsupported다. 공백·소수·과학표기·overflow·지원 범위초과·불명확 토큰은 조용히 drop하지 않고 호출 전체를 중단한다. ID 실패행은 date 검사를 건너뛰고, ID 통과행만 date 검사한다.

허용 정수 범위에서는 값이 int64/int32에 들어간다. null 또는 명백한 nonnumeric 때문에 원본 전역 numeric 결과가 float64로 승격돼도 ID 절댓값 ≤2^53 및 date int32 정수는 float64에 정확히 표현된다. 따라서 동일한 bad mask 및 ID 우선/drop 순서라는 전제 아래 최종 정수 cast 결과·dtype가 같다. 이 논증은 실제 전체 입력이 해당 범위라는 사실을 증명하지 않는다. adapter는 열을 요청하지 않은 key의 변환을 생략하며 자동 `key_valid`, 끝의 `month:int8`, 요청 순서를 원본 API에 맞춘다. `transform_months(())`는 원본 `pd.concat([])`와 같은 `ValueError: No objects to concatenate`를 내도록 했고 동적으로 비교했다.

## 합성 fixture 결과

`comparison_result.json`에 전체 출력 비교를 보존했다. Fixture는 두 달, physical row order, 실제 batch 분할, 빈 RecordBatch, key_valid True/False, key filter에서 빠지는 행, null/NaN 문자열/명백한 nonnumeric, leading zero, 양·음 부호, ID ±2^53, date int32 양끝, ID/date 실패, ID 실패 행에 넣은 미지원 date(`1.5`)를 포함한다. 원본 AST와 adapter 비교는 reset_index 없이 수행했다.

| 케이스 | canonical 결과 index | ID 출력 순서 | columns/rows/index/dtype/value+NaN |
|---|---|---|---|
| `key_valid_only=True` | `[0,1,2,4,5,10,12,14]` | `1, 2, -3, 9007199254740992, -9007199254740992, 7, 8, 9` | 모두 일치 |
| `key_valid_only=False` | `[0,1,2,5,6,7,12,14,16,17]` | `1, 2, -3, 9007199254740992, -9007199254740992, 4, 7, 8, 9, 10` | 모두 일치 |

별도 거부검사 9건 모두 전체 중단: ID `±(2^53+1)`, `1.5`, `1e3`, 앞/뒤 공백 숫자, 129문자 정수, int32 초과 date, int64/ID 범위 초과 대형 정수. Unsupported를 누락·행 제외로 성공시키지 않았다. 열 요청 API fixture는 `[wkt_valid]`만 요청했고 ID/date 입력에 의도적으로 미지원 token을 넣었다. 원본과 비교해 반환열 `[wkt_valid,key_valid,month]` 및 dtype/값/index가 같고 ID/date 변환은 생략됐다. 월을 비운 API fixture도 원본과 adapter 양쪽에서 같은 `ValueError`/message를 냈다.

## 실제 작은 Train 표본

- 대상 입력 `.../rows_train_1.parquet`, SHA-256 `7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140`.
- 선택은 월 1의 Parquet physical order 첫 16,384행. Projection은 `[row_index, rfid_id, part_dt, rfid_time, key_valid, wkt_valid, len_m, bbox_m, cen_lon, cen_lat]`. `ParquetFile.iter_batches(batch_size=4096)` 4회, 각 선택 행의 개별 `RecordBatch`에 adapter를 4회 호출했고 `batch number`, source physical offset, 첫/끝 row_index, concat offset, admitted/output 수와 모든 output index를 JSON에 저장했다. 원본 AST의 `pq.read_table`은 작은 선택 Table만 받았고 원본 전체 경로는 호출하지 않았다.
- batch trace: #0 physical rows 0–4095 / index 0–4095; #1 4096–8191 / index 4096–8191; #2 8192–12287 / index 8192–12287; #3 12288–16383 / index 12288–16383. 각 batch 4,096행을 key-valid admission했고 output도 4,096행이었다.
- 원본 AST와 adapter 출력은 16,384행, columns, index, dtype 및 값/NaN까지 동등했다. dtype는 `rfid_id:int64`, `part_dt:int32`, `rfid_time:int16`, `wkt_valid:bool`, geometry/length `float64`, `key_valid:bool`, `month:int8`. 제외행은 이 선택 표본에서 0이며 output serialization SHA 두 개가 모두 `0e70ea62112fc29e1feda89cb61e620c5b40e4558a99ae235a3fe08ad364c581`이다. 이 sample만 지원범위상 미지원 토큰이 없었다는 사실이다.

## RAM/RSS 관측과 실행 증거

작업은 serial로 수행했고 V는 정적 검토를 병행할 수 있었다. 다른 Orca/Codex/host process attribution은 unknown. 실제 표본·변환 전에 새 RAM 상태를 기록했다. 아래 RAM availability 값은 host total/free, RSS는 Python 프로세스 working set/commit 측정이며 서로 다른 수치다. 증분 예상 ≤512 MiB + 세션 여유 512 MiB는 계획치이지 보장치가 아니다.

| 시각(KST) | Free / total MiB | 계획 / 세션 여유 | 작업 |
|---|---:|---:|---|
| 05:58:27 | 4,126.4 / 14,140.9 | 512 / 512 MiB | 최초 구현 전 gate; projection 16,384행 × 10열, batch≤4,096, fixture AST 근거 |
| 05:59:23 | 4,135.2 / 14,140.9 | 512 / 512 MiB | attempt01 직전 |
| 05:59:48 | 4,119.9 / 14,140.9 | 512 / 512 MiB | loader injection keyword 수정 후 attempt02 직전 |
| 06:00:34 | 4,101.6 / 14,140.9 | 512 / 512 MiB | RSS API 수정 반영 attempt03 직전 |
| 06:01:38 | 4,120.4 / 14,140.9 | 512 / 512 MiB | NaN 및 omitted-key/empty-month API fixture를 추가한 최종 재실행 직전 |
| 06:04:20 | 4,150.3 / 14,140.9 | 512 / 512 MiB | V 정적검토에서 제안한 API 추가 케이스를 포함한 완료본 실행 직전 |

최종 Python의 process-start RSS snapshot(라이브러리 import 후)은 80.08 MiB current/peak. 프로세스 종료 직전 current 112.53 MiB, peak working set 120.96 MiB였으며 관측된 peak는 시작 snapshot보다 40.88 MiB 높다. Windows process pagefile/commit은 시작 535.74 MiB, 종료 current 603.60 MiB, peak 611.21 MiB였다. 이 값은 host 가용RAM이 아니며 코드가 실행한 경량 표본 범위의 관측이지 미래 builder peak 상한이 아니다.

선택 실행파일은 `C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe`; `skills get orchestration` 및 `skills get orca-cli` 안내를 먼저 확인했다. 실행 환경 Python 3.13.3, pandas 2.2.3, NumPy 2.2.5, PyArrow 24.0.0. 최종 명령은 isolated cwd에서 `PYTHONDONTWRITEBYTECODE=1 python -B D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/testB/round_004/execution/compare_loader_adapter.py`; exit 0, stdout `{"fixture_equal": [true, true], "unsupported_stopped": [true, true, true, true, true, true, true, true, true], "actual_equal": true, "actual_stop": null, "actual_transform_calls": 4}` 및 stderr 0 byte다. isolated cwd는 비어 있으며 pycache가 관측되지 않았다. 전체 attempt별 명령 결과는 `attempt01_*.log` … `attempt04_*.log`와 exit code text에 보존했다. attempt01은 fake reader lambda가 keyword `columns`를 받지 않아 fixture 시작 전에 exit1, attempt02와 attempt03은 exit0이나 각각 RSS 측정/NaN-fixture 개선을 위한 중간 버전, attempt04는 검증 범위가 넓어진 성공 실행, 완료본은 V가 지적한 API cases 추가 후 재실행한 최종 exit0이다. 최종 stdout/stderr/exit는 `run_stdout.log`, `run_stderr.log`, `exit_code.txt`에 있다.

## 다음 key-only scan 제안 및 남은 단계

사전계약 초안 및 제한된 peak 추정은 [domain_and_equivalence.md](domain_and_equivalence.md)에 작성했다. 대상은 2026 Train 월별 parquet, 필요한 3열만, batch≤4,096, key_valid 선처리, 전역 ordinal 및 마스크/해시를 파일 sidecar에 스트리밍 저장하고 first unsupported에서 중단하는 설계다. 월별 4,212,389행의 두 bit mask 이론 raw 크기는 약 1.01 MiB지만 Arrow/string conversion과 임시 객체/OS page cache는 미측정이다. 실행 peak ≤512 MiB는 계획 추정이지 안전 보장값이다. 감독이 입력/해시/population/output 경로/예산과 실행 권한을 새로 고정하기 전에는 scan을 하지 않는다.

이번 E의 작은 fixture와 actual sample은 loader 전체-domain gate를 대신하지 않는다. V 정적리뷰는 조건부 논증과 필요한 dynamic cases를 확인했으며 독립 동적 재검산은 별도 V task 범위다. 생산 loader, 참조 builder, 성능/사고/threshold/B/C/제출/split은 미실행·미승인이다.
