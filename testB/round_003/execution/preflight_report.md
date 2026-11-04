# Round003 E bounded loader 동등성 및 단계별 RAM 계획

작성: 2026-11-05 KST. 요청/Orca launch 설정은 `gpt-6-luna/xhigh`; provider 내부 model/effort telemetry는 unknown. 수정 소유 범위는 이 `execution/` 폴더뿐이다. 시작 확인 RAM은 4,282.7 MiB / 총 14,140.9 MiB였고 V 독립 정적 검토 작업 및 다수 Orca/host 프로세스가 병행 중이었다(프로세스별 정확한 동시 작업 및 세션 오버헤드는 unknown). 실행 직전 표본 검사: 4,335.7 MiB, 시도 2: 4,314.3 MiB, 시도 3: 4,292.5 MiB. 증분 작업 계획 상한은 각 표본 실행에 512 MiB였으나 실제 peak는 계측하지 않았다.

## 원본 코드 / 입력 해시 관문

원본 네 모듈 전체 SHA-256이 `round_002/scorer_review/manifest.json`의 `input_code_sha256`와 일치했다. 불일치가 없어 진행했다.

| 원본 | SHA-256 | 조사한 흐름 |
|---|---|---|
| `run_remeasure_20261031.py` | `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c` | `load_rows`, `parquet_path`, parse schema/footer lineage |
| `run_008_testB_20261101.py` | `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8` | harbor, density, gap/jump, CDF, scorer |
| `run_005_F156_merge_20261101.py` | `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4` | `_TRAIN_ARRAYS`, `_train_arrays`, `_build_t5_dicts` |
| `run_cycle4_3_featAC_20261101.py` | `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3` | `_load_year_arrays`, `argsort`, array retention |

`round_002/preparation/parquet_schema_metadata.json`는 footer 조사 기록(2026-11-05, pyarrow 24.0.0)이며 전 월 스키마 일치: `row_index:int64`, `part_dt:string`, `rfid_id:string`, `rfid_time:int16`, `key_valid:bool`, `wkt_valid:bool`, `n_coords:int32`, 길이/bbox/centroid `double`. Train 원본의 parse→Parquet 계보는 `remeasure.stage_parse` 및 `rows_train_1..6.parquet`; CSV 재파싱은 하지 않았다. 선택 Train Parquet SHA는 실행 영수증에 기록했다.

`load_rows`는 월 순서대로 필요한 열만 `pq.read_table`→Pandas로 바꾸고 (기본) 월별 `key_valid` 필터 및 `month:int8`을 붙인 뒤 월별 DataFrame 모두를 `pd.concat(ignore_index=True)` 한다. 연결 후 전체 `rfid_id` Series에 `pd.to_numeric(errors="coerce")`, NaN 행 제거, `int64` cast를 하고 같은 순서로 `part_dt`를 처리해 `int32` cast한다. 월/Parquet 입력 순서를 유지하고 loader 안에서 정렬하지 않는다. 결측 또는 숫자화 실패인 ID/date만 제거한다. `wkt_valid` 필터는 호출자 선택이며 loader의 숫자 키 제외와 혼동하면 안 된다.

## 새 코드와 동등성 결과

- `bounded_loader.py`는 Arrow batch별로 동일한 필터/열순서/month/dtype/cast 작업을 하는 실험 prototype이다. 보존량을 전역으로 추론하는 단계가 없어 production 사용은 보류다.
- `round003_runner.py` 기본은 `default deny`; 허용 인자를 줘도 아직 생산 builder를 구현하지 않고 오류를 반환한다. 현재 전체 참조/score 실행 entrypoint는 존재하지 않는다.
- `compare_loader_sample.py`는 canonical 모듈 import 없이 AST에서 원본 `load_rows` 정의만 추출한다. `pq.read_table`을 16,384행 주입 테이블로 치환하여 원본 함수의 원본 변환 순서를 실행했다. 전체 데이터용 canonical `load_rows` 경로는 호출하지 않았다.
- 실제 표본은 train `rows_train_1.parquet`의 물리 `row_index` 첫 16,384행, projection `row_index,rfid_id,part_dt,rfid_time,key_valid,wkt_valid,len_m,bbox_m,cen_lon,cen_lat`, 8,192행 Arrow 배치 두 개다. 비교 결과 16,384행, 열 및 순서 일치, dtype 일치(`rfid_id:int64`, `part_dt:int32`, `month:int8`, 기타 footer dtype 유지), 값/NaN 일치, 제외 차이 없음. 이는 이 월의 선택 구간 표본 결과이며 전체자료 동등성 증명이 아니다.
- 경계 fixture는 leading zero, 부호, int64 초과, null, nonnumeric, `int32` 초과 날짜와 서로 다른 batch에 나뉜 큰 integer 및 decimal 문자열을 포함한다. 전역 `pd.to_numeric`이 `9007199254740993`을 float64 추론으로 `9007199254740992`로 만든 반면, batch마다 따로 변환하면 큰 정수 배치의 int64 값을 보존할 수 있어 값이 달라질 수 있다. 해당 경계의 original vs prototype은 동등하지 않다. pandas가 숫자열 전체를 한 번에 추론하는지/다른 배치 크기로 경계가 옮겨지는지에 따라 dtype promotion/rounding, overflow cast, NaN drop 집합이 바뀔 수 있다. 부호·leading zero, 비수치 문자열과 결측 혼합, 빈 배치, 월 경계, `YYYYMMDD`, int32/int64 overflow도 표본 일치만으로 해결되지 않았다.
- 따라서 이 prototype의 현재 verdict는 **실제 Train 샘플 통과 / 경계 합성 실패 / 전체 동등성 미증명 / 생산 loader 사용 금지**다. 허용 도메인을 “현재 표본에서 관측한 값”만으로 제한해도 나머지 3.87M행을 확인하지 않았으므로 충분하지 않다. 후속 구현은 각 전체 numeric Series의 canonical global inference를 보존하는 bounded scratch/2-pass 설계 또는 domain proof+fail-closed가 필요하다. 전량 값 스캔 없이 이 조건을 해결했다고 주장하지 않는다.

## 원본 builder와 동시 보유물

수치는 2026 train `3,887,069`행 기반의 계획 envelope이며 관측값/보장 상한이 아니다. round002 preflight의 2 GiB 초기 계획은 행당 Arrow numeric payload 단순합을 토대로 한 대략치였고, 아래 객체 중첩과 pandas object/복사/groupby, Python map/set 오버헤드를 상한화하지 않아 안전 보증으로 사용할 수 없다.

| 순차 단계 | 원본 함수 및 유지/임시 객체 | 독립 subprocess 계획 증분 peak (미측정 추정) |
|---|---|---:|
| Harbor | `build_train_harbors`: 6열 전체 train frame, `wkt_valid`/stop bool mask 및 선택 view/copy, floor된 ix/iy, `cell_df`, groupby nunique hash/table, candidate/visited Python tuple set와 BFS stack/component, harbor points 및 KDTree. 반환 closure가 tree/투영상수와 harbor points를 캡처해 이후 사용 때까지 살아남는다. | 1.5–3.0 GiB |
| Density | `build_train_fishing_density_dicts`: `_train_arrays()`로 8열 전체 배열; `_load_year_arrays`의 raw arrays+valid mask/index+`argsort(kind="stable")` 정렬 arrays 중첩; `run_005._TRAIN_ARRAYS`가 전역 참조로 남음. Harbor를 다시 빌드하고 `_build_own_moorings("train")`도 독립 frame/mask/group 결과를 구성. `harbor_dist`, `mooring_dist`, `fishing_mask`, `_build_t5_dicts`의 vessel별 fine/coarse visited-cell set 및 count dict, 최종 102,053/9,174 cell maps, 반환 ref density Series/list/array를 생성. | 3–6 GiB |
| Gap/jump + CDF | `build_gap_jump_reference`: 6열 train frame 및 valid copy, `_ts_hours`, timestamp sort용 pandas 인덱스/정렬 프레임, 같은 vessel mask, gap/jump 임시와 반환 배열. `build_quantile_normalizer`가 각각 float 변환/정렬 배열을 만들어 closure에 저장. 두 CDF closure는 이후 모든 score까지 reference 배열을 보유한다. 같은 프로세스에서 실행하면 `_TRAIN_ARRAYS`, density maps, harbor closure/tree도 살아 있어 누적된다. | 1.5–3.5 GiB 단독; 앞 결과와 같은 프로세스면 총 6–12+ GiB 가능성 |
| 후속 score | 위의 nearest harbor closure/KDTree, 두 density map, 두 sorted CDF 배열을 동시 보유. 선택 test만 선박별 처리 권장. | 별도 계측 없는 상태로 추정 불가; 실행 금지 |

따라서 harbor, density, gap/CDF는 **순차 별도 subprocess**에서 각각 산출하고 scratch에 단계 산출물을 저장한 뒤 종료해 로더 frame/정렬 임시/전역 `_TRAIN_ARRAYS`를 OS가 회수하도록 한다. 함수를 바꾸거나 순서를 재정의하지 말고 기존 builder 및 참조 상수·label map·집합·정렬 동점을 재사용한다. Density 자체가 harbor를 한 차례 더 호출하는 기존 동작은 알고리즘 경로에서 그대로 보존해야 하며, 실행 계획에서 그 중복 peak를 반드시 포함한다. `gap`의 `(rfid_id, ts)` 정렬 동점은 원본 미명시 순서를 임의 stable sort로 바꾸지 않는다. 결과 전달은 pickle/전체 DataFrame cache 대신 scratch columnar arrays/maps를 우선 평가하되, serializer가 값/순서/키 의미를 바꾸지 않는 별도 비교가 필요하다. Scratch도 RAM/mmap/page cache 압력을 만들 수 있으므로 자동으로 “메모리 무료”라 가정하지 않는다.

### 실행 전 RAM gate

새 단계 시작 직전 OS 가용 RAM, 실행 중인 주요 process/다른 worker, 예상 peak 및 근거를 기록한다. E dispatch 증분 계획 한도는 512 MiB 및 세션 여유 512 MiB였다. 향후 큰 실행은 동시 세션을 정리하거나 별도 시간으로 분리하고, 각 단계에서 `free RAM >= stage peak estimate + max(1 GiB uncertainty reserve, 512 MiB session reserve)`를 요구한다. 현 시점 계획 envelope로는 harbor preflight 최소 4.0 GiB, density 최소 7.0 GiB, gap 최소 4.5 GiB 가용 RAM이 필요하다(동시에 다른 유의미한 작업이 없고 estimate/uncertainty가 재검토된 경우에만). Density 6 GiB peak 추정에 1 GiB 불확실성 reserve를 적용한 값이며 2 GiB 계획을 보장값으로 취급하지 않는다. 예상치/현재 RAM 어느 쪽이 불명확하거나 gate 미달이면 중단한다. 프로세스를 강제 종료하지 않고 polling/watch를 사용하지 않는다. 단계 RSS와 시스템 free RAM은 구간 경계에서 기록하되 sampling은 순간 peak를 증명하지 않는다.

## 보류 상태와 후속 명령 제안

현재는 전체 train 참조, 전체 train 중복 적재, 실제 새 100척 점수/A/membership 전수 생성, canonical import/build, stockCLI/main/stage를 실행하지 않았다. Round002의 46,705행 전수스캔 및 26행 합성은 반복하지 않았다. `__pycache__` 억제(`python -B`, `PYTHONDONTWRITEBYTECODE=1`)를 표본 AST 경로에 적용했다. 새 생산 builder는 구현되지 않았으므로 제안 명령은 향후 구현·독립 V 검토·감독 gate 이후에만 사용할 수 있다.

후속 권고(아직 실행 금지): 각 stage를 새 프로세스로 다음 interface의 **별도 호출**로 실행하고, 이전 단계 artifact hash를 입력으로 고정한다.

```powershell
python -B testB/round_003/execution/round003_runner.py --stage harbor --partition train --batch-rows 8192 --scratch testB/round_003/execution/scratch --output testB/round_003/execution/reference/harbor --source-manifest testB/round_003/execution/source_hashes.json --expected-train-rows 3887069 --allow-production
python -B testB/round_003/execution/round003_runner.py --stage density --partition train --batch-rows 8192 --scratch testB/round_003/execution/scratch --output testB/round_003/execution/reference/density --harbor-manifest testB/round_003/execution/reference/harbor/manifest.json --source-manifest testB/round_003/execution/source_hashes.json --expected-train-rows 3887069 --allow-production
python -B testB/round_003/execution/round003_runner.py --stage gap --partition train --batch-rows 8192 --scratch testB/round_003/execution/scratch --output testB/round_003/execution/reference/gap --source-manifest testB/round_003/execution/source_hashes.json --expected-train-rows 3887069 --allow-production
```

위 CLI는 계획 인터페이스일 뿐 현재 파일에서 지원되지 않는다. 각 실행 전 fresh RAM gate에서 harbor ≥4.0 GiB, density ≥7.0 GiB, gap ≥4.5 GiB를 재확인하고 512 MiB 여유/불확실성 및 V 독립검산·별도 감독 승인을 충족해야 한다. 출력은 execution/reference/와 execution/scratch/만, stdout/stderr/exit/RSS/free RAM/입력·산출 SHA-256을 execution/logs/receipt에 남긴다. 공통 참조 summary(기존 gap/jump 각 3,879,693 pairs, gap p50 1h, jump p50 약 85.723526m, density 102,053/9,174, fishing 1,376,741)는 일관성 비교값일 뿐 전체 수치 동등성 증명이 아니다. 세 단계 산출 후 독립 재계산자는 전체 참조의 sorted values/maps/cells 또는 hash-addressed canonical serialization을 독립 비교해야 하며 summary만 맞는 것으로 통과시키면 안 된다. 그 검산과 RAM 계획 검토 후 별도 supervisor dispatch가 있어야 score 단계로 넘어갈 수 있다.

사고파일/Testfit/보정/임계값/B/C/사고판정/성능/제출/외부수집/push 및 원자료/canonical/cache/선행라운드 변경은 수행하지 않았다.
