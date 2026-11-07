# E bounded 행 조사 및 격리 runner 보고

수정 기록: 2026-11-05 KST. 소유권은 `testB/round_002/execution/`이며, 이번 보수는 코드·보고서·manifest의 수정과 기존 격리 산출물의 작은 lineage-column 확인에 한정한다. 전체 parquet 스캔, reference 구축, 실제 점수 계산은 다시 실행하지 않았다.

## 행 조사 결과

- 입력 명부는 원문 문자열 ID 100개/순서/SHA `d7c5affc53473cc45a3372c9bc7b82eb0466cdb99a77e2f4996b6cc8325d3ec4`와 일치한다.
- 기존 clean run은 2025년 1–6월 test parquet 6개를 필수열 projection 및 `iter_batches(batch_size=16384)`로 전체 4,212,389행 스캔했다. 각 월 `row_index`는 0부터 연속하고 이전 parse manifest의 월별 행수와 일치했다. 이는 parquet 스캔 결과이며 CSV 재해시·재파싱이나 WKT 원본 재검증이 아니다.
- 100척 모두 행이 확인되어 합계 46,705행이 월별 `selected_rows/month_NN.parquet`에 있다. 기존 `wkt_valid` 유효행 46,705, 점수 입력 필드 finite 및 날짜 검사를 통과한 행 46,705, 제외 0이다. 관측 날짜 범위는 20250101–20250630, `rfid_time`은 0–23이다. 시간대와 좌표 CRS/datum은 unknown이다.
- timestamp key `(rfid_id, part_dt, rfid_time)` 46,705행을 disk-backed SQLite unique key로 확인했고 중복 재등장 0이다. 원행을 합치거나 제거하지 않았다. `source_ordinal`은 선행 월 parquet 실제 행수 합+월내 0-based 원 `row_index`다. 기존 parquet에 raw WKT가 없어 재생성하지 않았다.

| 월 | 스캔 행 | 월 내 `row_index` | 추출 행 | 이전 parse 행수 일치 |
|---:|---:|---:|---:|:---:|
| 1 | 592,013 | 0–592,012 | 6,258 | 예 |
| 2 | 442,715 | 0–442,714 | 5,387 | 예 |
| 3 | 624,514 | 0–624,513 | 6,625 | 예 |
| 4 | 755,491 | 0–755,490 | 7,907 | 예 |
| 5 | 888,878 | 0–888,877 | 10,099 | 예 |
| 6 | 908,778 | 0–908,777 | 10,429 | 예 |

선박별 `target_row_summary.csv`에는 월 행수, 날짜범위, raw/valid/scorable/제외, 필드별 결측·비유한/날짜불능, 동시간 중복 재등장 수, 시간·좌표·길이·bbox 범위가 있다.

### 원본 파일명·경로 보존 확인

이번 리뷰에서 `scan_result.json` 및 `execution_manifest.json`의 `source_file`/`parquet_path` 문자열에 Unicode replacement character가 있어 깨진 것을 확인했다. 이 필드만 preparation manifest의 `source_path`/`parquet_path`에서 직접 복구했다. 콘솔 stdout을 JSON으로 왕복하지 않았다.

선택 Parquet은 6개의 월별 파일 각각에서 `source_file` 열만 투영해 준비 manifest의 해당 월 파일 basename과 비교했다. 6/6 파일명이 문자열 단위 완전 일치했고, 따라서 선택 Parquet lineage 열은 손상되지 않았다. selected Parquet 파일은 수정하지 않았다. 원본 source 경로는 `execution_manifest.json`의 월별 `parquet_path`에 UTF-8로 보존했다.

## ID 원문·숫자형 membership 정책

제출 명부 원문 문자열과 행 순서는 그대로 유지한다. train parser 배열은 `int64`이므로 reference membership 조회에만 ASCII decimal 문자열을 base-10 정수로 변환한다. 따라서 `"001"`은 원문 출력/label membership에서는 `"001"` 그대로 남고, train 숫자형 ID 조회에서는 숫자 1로 대응한다. 서로 다른 원문 ID가 같은 숫자로 정규화되는 경우(예: `"01"`과 `"1"`)에는 모호성을 감추지 않고 거부한다. 점수 출력 ID에는 numeric 변환 결과를 덮어쓰지 않는다.

`membership_from_preloaded_ids`는 미리 준비된 train ID 배열과 작은 label map만 받아 비교하고 직접 train loader를 부르지 않는다. 합성 경계 검사에서 no-train-load stub 전달을 거부하면서 stub이 호출되지 않는지, 원문 ID/순서 및 leading-zero 정책을 확인했다. `build_train_references`의 잘못된 `load_inputs()` tuple unpack도 `(manifest, ids, hash)` 순서로 고쳤다. 이 함수는 이번 작업에서 gate에 의해 거부됐으며 실행되지 않았다.

## 격리 runner와 합성 회귀 검사

`safe_score_namespace`는 원 run_008의 함수/상수만 AST로 추출하며, run_008과 remeasure 원문 SHA가 고정값과 다르면 추출 전에 중단한다. remeasure helper는 `SimpleNamespace`에 저장해 함수가 bound method가 되지 않게 했다. 기존 1행 합성 검사를 유지하고, 새 2행 합성 회귀는 첫 야간 정지 행의 누적 mooring과 이전 방문격자에서 두 번째 행까지 실제 `haversine_m` 호출이 일어나는 경로를 통과했다. 유한한 점수 2개와 실제 haversine 호출 3회 이상을 검사했다. 전부 합성값이며 실제 자료 점수가 아니다.

다른 합성 검사: 시간정렬과 source ordinal 분리, A의 원입력 첫 최대, 동일 timestamp 상충 및 valid/missing 혼합 보류, 전체 결측 `no_valid_score`, Test reference-fit 차단, gate 없는 reference builder 차단, execution 밖 출력 거부, source hash 불일치 거부다. 최종 문법검사와 합성검사 exit code는 `logs/`에 기록한다.

## 원본 import 및 쓰기 부작용 검토

원본 4개 모듈(run_008, run_005, featAC, remeasure)을 AST로 정적으로 검토했다. 모듈 import 시 함수 몸체 안의 `mkdir`, progress 파일 append, output 저장은 실행되지 않는다. `run_005`는 import 시 작은 `classes.json`을 읽어 class map 전역을 만든다. run_008은 `sys.path`를 조정하고 모듈 객체에 canonical output 경로 상수를 설정한다. `main`/stage 함수는 `__main__` 가드에 있어 자동으로 호출되지 않는다. 현재 runner의 점수 검사 경로는 stock 모듈을 import하지 않고 AST 추출만 한다.

후속 gate builder 경로는 명시적으로 허용될 때만 동적 import한다. 호출될 생산 함수는 `build_train_harbors`, `build_train_fishing_density_dicts`, `build_gap_jump_reference`이며 그 아래 `load_rows`는 기존 parquet를 열 뿐 CSV 파싱/Parquet 저장을 하지 않는다. remeasure `stage_parse`는 `OUT_DIR.mkdir`와 Parquet·manifest 기록이 있으나 호출하지 않는다. run_008의 stage 함수는 `OUT_WORK`/`OUT_SUB`를 만들고 pickle/JSON/submit 출력을 기록하나 호출하지 않는다. `run_005`/featAC progress 함수도 특정 stage에서만 경로를 만들고 append한다. 그 stage를 실행하지 않는다.

원본 전역 cache는 `run_005._TRAIN_ARRAYS`다. gate builder는 새 프로세스에서 이를 `None`으로 시작하고 `_load_year_arrays("train")` 결과를 harbor/density/gap build 동안 보유한 뒤 대상 membership을 읽고 `None`으로 지운다. 이 배열은 전역에 복사/보존되므로 독립 비용이다. 실제 stage 실행은 없었으므로 import/경로 쓰기 차단 검증도 정적 검토에 한정한다.

## RAM 계측과 미실행 reference 단계 계획

작업 시작 RAM 확인(04:17:36 KST): 가용 4,631.9 MiB/총 14,140.9 MiB, 전체 프로세스 315, Python 1. 기존 clean scan 내부 계측은 시작 가용 3,824.2 MiB, process count 358, 해당 Python RSS 82.4 MiB 시작 및 batch 경계 표본 최대 150.7 MiB(RSS 차 68.3 MiB)였다. RSS sampling은 배치마다 관찰했으므로 짧은 transient peak를 놓칠 수 있다. 현재 작업은 작은 열 projection과 정적 파일 처리만 했고 새 parquet 전체 스캔은 없었다.

다음 표는 원본 코드 흐름을 읽고 만든 **추정 범위**다. 단계 최고 RAM을 보장하지 않으며, 감독은 이것만으로 생산 실행을 승인하지 않아야 한다.

| 단계 | 원본 load/copy/cache 흐름 | 현재 보수 추정 및 처리 계획 |
|---|---|---|
| 공통 train 로드 | `remeasure.load_rows`는 월별 parquet 전체를 `pq.read_table(columns)`→Pandas로 바꾼 frame들을 list에 유지하고 끝에 concat한다. 유효행 필터, numeric cast 과정도 추가 복사할 수 있다. | 3.89M행·6–8열 DataFrame payload 약 0.6–1.3 GiB, concat/변환 중 겹침을 포함하면 1.5–2.5 GiB 후보. 미측정. |
| Harbor | `build_train_harbors`가 별도 전체 train frame, valid/stops view/copy, cell DataFrame, groupby 결과/candidate set, cluster 및 KDTree를 구성한다. density builder 안에서 harbor builder가 한 번 더 실행된다. | 일시 DataFrame/group 공간이 추가 1–2+ GiB일 수 있음. harbor closure/tree와 metadata는 이후 scoring 동안 보존. 미측정. |
| 정박지·density | `remeasure._build_own_moorings`가 train을 다시 로드해 stop/night mask, cell DataFrame, value_counts/groupby/top3 임시를 만든다. `_train_arrays`의 8열 로드도 filter 배열, stable argsort index, 정렬 배열을 만든 뒤 `_TRAIN_ARRAYS`로 유지한다. 이후 `_build_t5_dicts`는 선박별 fine/coarse visited-cell set 및 map을 쌓는다. | dtype 단순합 기준 정렬된 3.89M train 배열은 약 0.18 GiB이며 생성 시 원 arrays/index/frame이 함께 남는다. map과 전역 arrays 보유. 단계 peak 1.5–3+ GiB 후보, 상한 미확정. |
| Gap/jump 및 CDF | 원본 gap builder가 전체 6열 train frame을 새로 load/filter/copy/sort하고 두 연속쌍 배열을 만든다. quantile normalizer는 각 배열을 다시 sort해 closure에 보유한다. 이때 `_TRAIN_ARRAYS`, Harbor 및 density maps도 builder가 반환/보유 중이다. | DataFrame·sort buffer·기준 arrays 복사 1–2+ GiB 후보가 앞 단계 잔여물과 겹칠 수 있다. 여러 GiB 누적 가능성, 상한 미확정. 원 알고리즘을 청크화하지 않음. |
| 선택행 scoring (후속) | 46,705행 대상만 로드하고 한 척씩 기존 scorer에 전달. Harbor/tree, 두 density map, gap/jump 정렬 reference arrays는 유지. | 대상행 표는 상대적으로 작지만 총 peak는 reference 단계에 좌우된다. 단계별 RSS를 측정하고 충분한 사전 여유를 확인한 뒤 감독이 별도 gate를 결정해야 한다. |

기존 2 GiB 예산은 이 단계별 중첩 보유를 정확히 상한화하지 않는다. production peak는 unknown이며, 감독이 새 RAM preflight/계측·순차 실행·scratch 계획을 검토하기 전 실행 금지다. 이번에는 train 참조, membership 결과, 실제 점수를 생성하지 않았다.

## 실패·복구 및 미실행 범위

- 첫 scan exit 1은 명부 CSV 실제 열 `raw_value` 대신 `rfid_id`를 찾은 header lookup 오류이며 parquet 접근 전에 멈췄다. 코드 수정과 후속 run 로그를 보존했다.
- 이전 attempt03은 scratch SQLite를 재사용하여 과거 run key가 중복처럼 계산될 수 있어 폐기했다. unique scratch DB를 쓰는 attempt04 결과만 채택한다(실제 중복 0).
- 최초 synthetic fixture 오류 로그도 보존하며, 동시간 상충 fixture를 정정 후 검사했다.
- 이번 수정 후 `py_compile` exit 0 및 synthetic regression exit 0이며, stdout/stderr/exit를 UTF-8 `logs/syntax_repair.*` 및 `logs/synthetic_repair.*`로 보존했다. 합성 두 행 경로에서 `haversine_m` 호출은 3회 이상이었다.
- 이 보고서는 direct UTF-8 patch로 다시 썼다. legacy 손상본은 별도 보존했다. 새 report/JSON의 replacement character·치환 흔적을 검사하고 JSON parse를 재확인한다.
- CSV 전체 재해시/파싱, 실제 reference fit/score, stock CLI, cache 생성, 모델·임계값·B/C·사고 판정·제출은 실행하지 않았다.

## 산출물 무결성

각 최종 소유 산출물 SHA-256은 `execution_manifest.json`에 기록되어 있다. 깨진 기존 보고서/manifest는 변경 전 원문을 `logs/*_mojibake_legacy.*`로 보존했다. 이번 수정 후 runner의 최종 syntax·synthetic exit, JSON UTF-8 parse, Markdown Unicode replacement scan, 6개 source-file lineage 비교 결과와 새 manifest SHA를 기록한다.
