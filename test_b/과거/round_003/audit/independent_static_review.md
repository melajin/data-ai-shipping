# Round003 V 독립 정적 검토 — 2026-11-05

## 범위와 실행 상태

이번 산출물은 원본 loader/builder와 계약의 독립 정적 검토다. `AGENTS.md`, round003 계획, round002 다음 단계·계약·preflight·격리 runner·scorer review/manifest를 UTF-8로 읽었고, 원본 canonical 4개 모듈의 관련 함수/상수를 읽었다. 큰 parquet, 원CSV, pickle, train/test 전체 스캔, 참조 생성, 실점수/A, 테스트/시뮬레이션은 실행하지 않았다. 이 보고서에는 동적 동등성, 메모리 peak 안전, Testfit 차단의 런타임 PASS가 없다.

- Orca CLI: `ORCA_CLI_COMMAND=C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe`; 설치 버전 `1.4.246.0`. 실제 `skills get orchestration --json`, `skills get orca-cli --json` 안내를 확인했다. 이 dispatch의 요청·launch는 `gpt-6-luna/xhigh`(launch receipt exit 0); provider 내부 model/effort telemetry는 unknown이다.
- 메모리 시작 관측 2026-11-05 05:15:50 +09:00: 여유 4,283.1 MiB / 총 14,140.9 MiB. 정적 검토 증분 최대 256 MiB 추정, 실제 peak 미계측, 허용 세션 여유 512 MiB. 검토/보고서 작성 전 05:17:38 관측: 여유 4,354.1 MiB, 총 14,140.9 MiB, 프로세스 331, Python 프로세스 관측 없음. E의 dispatch는 동시 작업으로 간주(추가 세션/실행 상태와 동시 agent 수는 프로세스 관측으로 확정 불가). 이는 큰 실행 승인이나 peak 보증이 아니다.

## 원본 경로와 해시

모든 원본은 읽기 전용으로 확인. SHA-256은 파일 전체 바이트 해시이며 지정된 round002 manifest 기록과 일치했다.

| 모듈 | SHA-256 | 정적 확인점 |
|---|---|---|
| `D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py` | `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c` | `load_rows` |
| `D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py` | `cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8` | harbor, density, gap/jump/CDF builders, reference calls |
| `D:/repos/fishing-track-classification/code/tools/run_005_F156_merge_20261101.py` | `e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4` | `_train_arrays`, `_build_t5_dicts`, import/progress/cache |
| `D:/repos/fishing-track-classification/code/tools/run_cycle4_3_featAC_20261101.py` | `8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3` | `_load_year_arrays`, retained arrays/bounds/cache/closures |

근거 계약: `testB/round_002/contract/EXPLORATORY_EXECUTION_CONTRACT.md`; 원 실행/preflight 계보: `testB/round_002/execution/preflight_report.md` 및 `execution/isolated_runner.py`; 스코어·builder manifest: `testB/round_002/scorer_review/manifest.json`.

## Loader 동등성의 필요조건

원본 `remeasure.load_rows`는 월 목록 순서대로 각 parquet에 `pq.read_table(columns=list(needed))` 후 Pandas 변환, `key_valid_only=True`이면 그 월에서 `key_valid` 필터, 요청된 월 열을 `np.int8`로 붙이고 프레임을 리스트에 유지한다. 마지막에 `pd.concat(frames, ignore_index=True, copy=False)` 한 뒤 전체 연결 결과에 `rfid_id`, `part_dt`를 각각 `pd.to_numeric(errors="coerce")` 한다. 실패/NaN 행을 제외하고 각각 `int64`, `int32`로 캐스팅한다. 반환 열 순서는 요청한 `columns`에서 `month`를 빼고 필요한 경우 끝에 `key_valid`를 추가한 뒤 `month`를 끝에 붙인 순서다. 입력 행 순서는 요청된 월 순서와 parquet의 물리 행 순서이며 loader 자체에서 정렬하지 않는다. `_load_year_arrays`는 그 다음 `wkt_valid` 행만 뽑고 RFID 기준 `np.argsort(kind="stable")` 한다.

따라서 E bounded loader의 작은 표본 비교와 경계 합성은 다음을 보존해야 한다.

1. 반환 열/순서/각 dtype: 스키마 기반 열, `key_valid` bool, 숫자 변환 후 `rfid_id:int64`, `part_dt:int32`, `month:int8`; 원래 float/시간/문자 열 dtype 및 결측 표현도 동일함을 확인한다.
2. 제외집합: `key_valid_only=True`는 numeric 변환 전에 false key 행을 제외한다. `False`이면 key-invalid 행도 두 numeric key가 유효한 경우 반환될 수 있다. 그 뒤 `rfid_id` 또는 `part_dt`의 coercion 결과가 NaN인 행은 삭제한다. 양쪽 모두 실패한 행은 한 번만 삭제된다. 다른 열의 결측/WKT-valid 조건으로 loader 행을 더 제거하지 않는다.
3. 행 정체성/순서: 월별 parquet 원행 순서를 기록하거나 그에 준하는 검증 key를 사용해 값과 제외 mask를 위치별 비교한다. `ignore_index`가 만드는 0-based 출력 index와 실제 원행 key를 혼동하지 않는다.
4. batch별 `pd.to_numeric` 비교: 원본은 concat된 전체 Series에서 판다스 dtype 추론/캐스팅을 수행한다. 배치별 변환·사전할당은 batch마다 숫자/문자/결측이 섞이는 경계에서 int/uint/float/object 추론과 이후 concat promotion이 달라질 수 있다. 빈 배치, 결측, 숫자 문자열/혼합 잘못된 문자열, 부호·leading zero, 날짜 경계(예: `YYYYMMDD` 숫자), int64 경계·초과값/overflow를 합성 경계로 비교해야 한다. 전역 일괄변환과 같은 최종 값, NA 제외 mask, dtype 및 cast 결과를 증명하거나 차이를 중단 사유로 기록한다. `int64` 초과·`int32` 날짜 overflow에서 원본이 오류/변환을 내는 경우 새 loader가 조용히 wrap/round/coerce하지 않아야 한다.
5. 모집단별 명세: 2026 train loader 표본의 실제 선택 범위(월, 파일/row group, 최대 행수, 열)를 기록하고 새 E 합성은 표본 실제자료와 구별한다. 이전 46,705행 전수대조나 26행 합성은 반복하지 않는다.

## Builder 알고리즘, 중첩 보유물 및 메모리 조건

기존 preflight의 GiB 수치는 추정치이며 실 peak/상한이 아니다. 기존 코드/함수를 재사용하고 결과가 동등함을 증명하기 전 단계병렬화/계산 알고리즘을 바꾸지 않는다. 모든 단계 메모리는 앞 단계에서 살아남는 closure/cache/map을 포함해 최고 동시 보유량으로 다시 계산해야 한다.

| 단계/원본 함수 | 유지·일시 객체 | RAM 계획에 요구되는 항목 |
|---|---|---|
| 공통 loader `load_rows` | 월별 전체 투영 Parquet table→Pandas frame 리스트, concat 출력, 필터/`to_numeric`/정수 cast의 중간 배열·복사. | 월별 frame과 결과가 겹치는 기간을 계상. 파일 row group/chunk iteration은 원본의 월+원행 순서/값/dtype/제외행을 보존해야 함. 원본 전체 DataFrame을 새 DataFrame과 동시에 복제하는 비교 금지. |
| Harbor `build_train_harbors` | 별도 train frame; valid/stops 선택; ix/iy int64; `cell_df`; groupby nunique Series; candidate tuple set; visited, stack, clusters; harbor points, cKDTree와 nearest-distance closure. | density builder가 harbor builder를 다시 호출한다. 재사용할 경우 캐시 수명/함수 출력 동일성 확인, 중복 실행이면 두 번째 전체 frame/groupby와 기존 closure/tree의 동시 유지 산정. 임시를 해제해도 반환 closure/tree/points는 후속 점수 시점까지 계산에 포함. |
| Mooring + density `build_train_fishing_density_dicts` → `_build_own_moorings`, `_train_arrays`, `_build_t5_dicts` | `_TRAIN_ARRAYS` 전역에 보관되는 유효 7개 열과 추가 month/active/bounds; filter 배열; stable argsort index와 정렬 배열의 생성 중 겹침; vessel bounds dict; harbor와 mooring full-frame/groupby 임시; `fishing_mask`; 선박별 fine/coarse cell sets, count dict, `dens_map01/05`, reference density 임시. | `_TRAIN_ARRAYS`는 다른 함수가 같은 module cache를 공유하는 전역이므로 해제 전제 금지. builder 반환 후 실제 필요한 map과 closure를 남기고 미사용 배열/중간 dict가 참조에서 제거되는 시점 확인. T5 per-vessel set/map 및 harbor와 동시 보유량, 배열 생성 peak까지 포함해 수치화. |
| Gap/jump `build_gap_jump_reference` + `build_quantile_normalizer` | train 6열 전체 frame, valid copy, ts, RFID/ts 정렬 frame과 sort temporaries, 인접 gap/jump arrays; `np.sort(np.asarray(..., dtype=float))`의 정렬 복사본을 보유하는 norm closure 두 개. 이때 앞 `_TRAIN_ARRAYS`, harbor, density가 유지될 수 있음. | 원본 정렬 key/기본 tie 순서와 pair 산출 규칙을 그대로 보존. 원본의 불안정/미명시 동일 ts 순서가 있으면 변경 없이 문서화하며 임의 stable tie를 새로 넣지 않는다. gap/jump 원본 배열을 해제할 수 있는 호출부인지 확인하고 두 CDF reference와 이전 cache 동시 보유를 계산. |

각 단계의 peak 추정은 단순 최종 배열 합이 아니다. DataFrame object/숫자 backing, boolean/index 배열, `argsort` 인덱스, 정렬된 복사, pandas groupby hash/table 임시, dict/set 오버헤드, scipy KDTree, allocator/Parquet buffer, 이전 단계 반환 closure/cache 및 OS 동시 프로세스를 포함해야 한다. 각 단계 전 RAM·다른 실행 작업·예상 최대 증가량·여유 기준을 새로 기록하고, 해제/순차화/scratch가 실제 보유 참조를 없애는지 검증한다. 추정 peak+512 MiB 안전 여유가 현재 여유를 넘거나 정량화 불가이면 실행을 보류한다. 실측 RSS/OS 여유는 각 단계 경계에 기록하되 순간 peak를 관측하지 못할 수 있음을 적는다.

## Testfit, 알고리즘·출력 격리 및 부작용

Round002 runner의 정적 조건(`assert_reference_fit_partition`은 오직 train 허용, `build_train_references` 기본 `allow_reference_rebuild=False`, 대상 output path는 `execution/` 하위, source hash 확인 및 AST namespace)을 round003 runner에 연결해 확인해야 한다. 이는 이번 V 검토에서 runner 동작/실제 builder 호출로 시험한 것이 아니다. 후속 검산에서는 test partition 또는 test frame을 전달해 builder가 호출되기 전에 예외로 차단되는 부정 시험, train만 허용되는 기본 성공 조건, test reference 호출 카운터=0, 실제 build 중 참조입력 계보=train만을 확인한다. `test_fit_calls=0` 같은 최종 상수만으로 gate가 실제 호출경로에서 강제됐다고 간주하지 않는다.

- 고정 harbor/density/gap-jump 함수, 상수, 라벨 ID/label map, train membership과 원행/ID 표현을 변경하지 않는다. label membership은 원문 문자열 label lookup, reference membership은 명시한 정수 ID 정규화/중복충돌 정책으로 별개 기록한다.
- 점수 수식·clip/floor·기간·행 삭제/병합 금지, source ordinal attach, scorer에 전달하는 시간 정렬과 A의 원입력 최초 최대 tie를 별도로 보존한다. gap builder의 `(rfid_id, ts)` tie와 모든 기존 groupby/정렬 순서를 인위적으로 안정화/재정렬하지 않는다. 작은 동점·중복·결측 비교를 별도 회귀 사례로 확인한다.
- 원자료/canonical/cache/선행 round는 read-only. subprocess working directory 및 모든 새 파일은 소유 `execution/` 또는 audit/에 국한. `main`, stock CLI, stage, submit 및 기존 출력경로는 호출 금지. canonical import가 `__pycache__` 쓰지 않게 bytecode를 비활성화하거나 순수 정의 AST로 제한한다. `run_005`의 import-time 작은 class map read, path/sys.path 조정 등은 코드에서 확인하고, progress 함수가 `mkdir`/고정 파일 append를 하지 않도록 호출 전 차단/치환하거나 해당 모듈을 import하지 않는다. 실제 실행 전에 결과 경로와 side effect를 부정 검사한다.
- 참조 생성 없음/표본 불일치/원본 해시 불일치, 스코어러 참조 오염, 생성 산출물 외부 경로, `__pycache__`/progress/canonical 변경이 발견되면 보류하고 수정은 소유 실행자에게 요청한다. 생산불변 확인 범위(경로/stat/hash)를 명시하며 미검증된 전체 불변으로 넓히지 않는다.

## 판정 및 후속 검산 계획

이 dispatch의 판정은 `정적 필요조건 정리 완료; 구현/동등성/메모리 안전 검산 보류`다. 원본 코드로부터 loader의 동작/중첩 객체를 정리했지만, E 구현의 변경범위와 결과가 아직 없으며 큰 실행 가능성은 알 수 없다. 앞서 보고된 최초 독립감사 FAIL/exit 1과 metadata-only delta PASS 10/exit 0는 서로 다른 사건으로 모두 보존한다. 역사 44 해시의 최초 의미/기록 시점과 바이트 복원 여부는 unknown이다.

E 산출물이 준비되면 별도 dispatch에서 (1) 변경 파일이 execution/에 한정되고 생산 원본/기존 산출물 hash가 불변인지, (2) 위 loader schema/order/dtype/NA 제외 조건이 선택 범위가 분명한 표본과 합성 overflow/혼합형/결측/날짜 경계에 모두 맞는지, (3) runner Testfit 차단·경로 차단·pycache/progress 부작용 차단이 실제 호출 전에 작동하는지, (4) train reference의 원래 함수/라벨/정렬/tie/closure 수명이 유지되는지, (5) 모든 단계의 동시 보유물과 실행 전 RAM 재확인이 상한을 충족하는지 독립 검토한다. 그 뒤에도 표본·summary 일치는 전체 참조의 수치 동등성 증명이 아니다. full-train reference / full score / A 생성은 감독의 별도 gate 전 금지 상태다.

## 결함/확인 요청 전달

E bounded loader에서 batch 단위 `pd.to_numeric`의 dtype 추론과 원본 전체-concat 변환이 동일하다는 증거가 없으므로, 구현 보고서에 int64/int32 overflow, 혼합 문자열/결측 및 월·날짜 경계 fixture 결과를 값·dtype·제외집합별로 기록하도록 요청한다. 또한 density에서 harbor build가 재호출되고 `_TRAIN_ARRAYS` 전역 cache 및 CDF closure가 살아남으므로, peak 계획이 반환된 이전 단계 객체와 중복 harbor 계산까지 포함하는지 명시해야 한다. Testfit/출력/pycache/progress 항목은 이번에는 source/이전 runner의 정적 검토만이며, round003의 새 runner 실제 동작은 미확인이다.
