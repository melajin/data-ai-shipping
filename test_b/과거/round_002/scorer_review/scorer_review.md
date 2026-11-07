# R 검토: 기존 고정 Test B scorer

작성: 2026-11-05 KST. 범위: 읽기 전용 정적 코드·문서 검토. 새 점수, 캐시, 모델, 테스트 및 실제자료 실행은 하지 않았다.

## 판정

**조건부 적용 가능성은 있으나, 현재 정보로 새 v2 Test B 100척 점수를 바로 실행할 준비는 되지 않았다.** 고정 `scores` 경로의 참조 생성은 2026 `train` 입력을 사용하고, 점수 행 입력은 2025 `test` 입력을 사용한다. scorer 안에는 2025 데이터에서 공용 참조·스케일러·KDE·분위수·분류 임계값을 새로 적합하는 호출이 없다. 다만 기본 CLI의 대상 명부는 1027 제출샘플 Excel의 `테스트B` 시트이고 출력은 canonical의 `results/work_008/`로 고정되어 있다. Round001 manifest도 `1103_v2_not_read_or_verified`를 선언한다. 따라서 그 CLI를 그대로 쓰면 새 v2 100척 명부/순서를 보장하지 못하며, canonical 쓰기 부작용도 있어 실행하면 안 된다.

조건부 다음 단계는 P가 새 v2의 정확한 ID 100개·순서와 필요한 행/열·원행 식별자를 확인하고, 감독이 입력 명부, 고정 참조 계보/적합 범위, A 동점 및 시간 계약, 출력 경로, 청크/RAM 예산을 동결한 뒤 별도 생산 실행자를 지정하는 것이다. 100척 모두의 2025 Test 행 존재와 전체 제공 기간 유효 행 범위는 이 검토에서 새 명부로 직접 검증하지 않았으므로 unknown이다.

## 호출 그래프와 부작용

| 순서 / 함수 | 입력·호출 경로 | 출력·부작용 / 근거 |
|---|---|---|
| CLI 선택 | `__main__`가 `--stage scores`를 `stage_scores`에 매핑 | `diag0`, `t1`, `submit`, `audit4`와 분리된 stage 선택. [run_008:812-822](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py) |
| 명부 | `stage_scores → target_ids → pd.read_excel(SAMPLE_XLSX, sheet_name="테스트B")` | `SAMPLE_XLSX`는 1027 원본 데이터 폴더의 `제출샘플.xlsx`; sheet 순서를 리스트로 반환. [run_008:38-42,71-74,533-535](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py) |
| 고정 항구 참조 | `build_train_harbors → remeasure.load_rows("train", …) → 유효 정지행 → 0.005° 격자에서 선박 수 ≥20 → 8방향 연결 셀 군집 → nearest-distance 함수` | 모든 `train` 행 기반. 공유 항구 지점·KD tree는 메모리에 생성되며 이 함수가 캐시 파일을 저장하지 않는다. [run_008:197-246](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py) |
| 고정 밀도 지도 | `build_train_fishing_density_dicts → m._train_arrays() → featac._load_year_arrays("train")`; 이어 `build_train_harbors`, `remeasure._build_own_moorings("train")`, `m.load_labels → m._build_t5_dicts(all label IDs, fishing_mask, None)` | fishing mask는 2026 train의 길이/항구/자기 정박지 조건. 밀도 dict는 라벨이 있는 train ID 7,372척의 fine/coarse 격자 방문 집합을 세어 만든다. 선박별 한 셀 중복 방문은 1회로 센다. [run_008:361-386](D:/repos/fishing-track-classification/code/tools/run_005_F156_merge_20261101.py), [_build_t5_dicts:358-389](D:/repos/fishing-track-classification/code/tools/run_005_F156_merge_20261101.py), [_load_year_arrays:70-104](D:/repos/fishing-track-classification/code/tools/run_cycle4_3_featAC_20261101.py) |
| 공백/점프 정규화 | `build_gap_jump_reference → remeasure.load_rows("train", cols) → valid 행 → 같은 ID 내 ts 정렬 후 인접 gap/jump 배열 → build_quantile_normalizer` | empirical CDF는 정렬된 train 값에 `searchsorted(side="right") / N` 적용. `scores_meta`에는 두 참조 각각 3,879,693개, gap p50=1h, jump p50≈85.724m. [run_008:350-358,399-413,538-540](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py), [scores_meta.json](D:/repos/fishing-track-classification/results/work_008/scores_meta.json) |
| 2025 대상 행 | `stage_scores → remeasure.load_rows("test", required cols) → wkt_valid → ts 생성 → target별 (ts, rfid_time) 정렬 → score_vessel` | `remeasure`에서 `train`은 2026 원자료 폴더, `test`는 제출샘플의 테스트셋 폴더를 가리킨다. 월 parquet를 열 투영해 읽고 월 순으로 이어 붙인다. 필요한 열 8개는 scorer 호출부에 명시된다. [remeasure:29-37,442-477](D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py), [run_008:544-560](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py) |
| 결과 저장 | `stage_scores → pd.to_pickle(results, REPO/results/work_008/scored_rows.pkl)` 및 `scores_meta.json` | canonical에 고정 경로 쓰기. score stage를 실행하지 않았고, 이 부작용 때문에 읽기 전용 검토에서 실행하지 않았다. [run_008:38-39,564-579](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py) |
| A 출력 | `stage_submit → read_pickle → valid.score.idxmax()` | 추가 고정 출력 경로는 `results/submission_20261101`; 이 stage는 현재 작업에서 금지된 제출 출력 부작용이다. `idxmax`는 첫 동점을 선택하지만 입력은 이미 시간 정렬되어 있고 원본 source row 순번을 전달받지 않는다. [run_008:38-39,592-620](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py) |

### 적합 범위와 2025 사용 여부

- **코드에서 확인:** 공용 항구·fishing mask·밀도 참조·gap/jump CDF 입력은 `train`만 읽는다. `train`은 `F:\문제 데이터_수정_1027\vpass_26년(1월_6월) 데이터\...`이고 `test`는 별도 테스트셋 폴더다. `stage_scores`의 2025 test 행은 점수 입력이며 공용 참조 생성 함수에 전달되지 않는다. score stage에는 `.fit()`/보정/테스트 분위수/임계값 선택 호출이 없다.
- **구성요소:** StandardScaler나 KDE는 사용되지 않는다. 항구의 연결 셀 군집은 train 정지 격자만으로 만드는 규칙 기반 공간 집계다. 밀도 지도는 train 라벨 참조의 격자 방문 선박 수다. 분위수 정규화는 train 인접 행의 gap/jump 배열만 쓴다. 과거 미방문 거리 `dist_km / 20km`와 clip은 고정 상수다.
- **대상 자기 이력:** `score_vessel`은 각 test 선박을 순차 처리하며 과거 방문 격자, 이전 행 gap/jump, 과거 24행 이상의 길이·직선도·상태 기록으로 점수를 계산한다. 각 행 점수에는 미래 행을 넣지 않지만 전체 기간 점수 중 A를 선택하는 것은 사후 전체기간 탐색이며 실시간 경보 평가가 아니다. 야간 정지 셀은 행 계산 뒤 누적되어 다음 행부터 자기 정박지 판단에 반영된다. 이 사용은 공용 참조를 test로 재적합하는 것과 다르다.
- **같은 ID의 고정 참조 membership:** Round001 보존자료는 기존(legacy) 100척 중 train 라벨 참조 ID가 겹치는 수를 95라고 적고, 이것을 membership으로만 해석하며 격자 기여/점수 희석 증거가 아니라고 명시한다. 이는 새 v2 100척의 membership 결과가 아니다. 새 명부별 교집합과 cell 기여는 P 자료 전에는 unknown이다. 같은 RFID의 2026 train 이력이 고정 참조에 포함될 수 있어도, 그것만으로 2025 test 항적을 이용한 참조 재적합이나 calibration으로 볼 수는 없다.
- **보존 한계:** Round001 `input_split_manifest.json`은 `run_008` 해시와 기존 cache/제출 파일 해시를 연결한다. 다만 그 manifest는 `legacy_inputs_only; 1103_v2_not_read_or_verified`라고 명시하고, 이전 cache의 `source_row_id`/원자료 원행 순번은 검증되지 않았다고 기록한다. 본 검토는 pkl, parquet, 원자료, 전수 CSV를 열거나 해시하지 않았다.

## 고정 점수식과 경계 동작

| 성분 | 기존 코드 규칙 | 결측/상태 |
|---|---|---|
| `s_zone` | `0.5*comp_a + 0.5*comp_b`. `comp_a=min(현재 격자와 과거 방문 격자 중심의 최소거리 km / 20, 1)`, 방문 이력 없는 첫 행은 0. `comp_b=1-min(density/3,1)`; density=0/없으면 1. Fine 0.01° 셀 참조가 3척 미만이면 coarse 0.05° 셀로 fallback. | 첫 행에서도 계산 가능. `floor(lon/grid), floor(lat/grid)` 격자화. |
| `s_change` | 과거 행 수 ≥24일 때 계산. 길이·직선도 robust z: `abs(x-median)/scale`; scale은 IQR/1.349, 0이면 std, 둘 다 0이면 1. `squash(z)=1-exp(-abs(z)/2)`. 상태 surprise=`1-과거 동일 상태 비율`. 사용 가능한 항목 평균. | 24개 미만이면 NaN. straight가 NaN이면 해당 z 항목 제외. |
| `s_gap` | 첫 행 이후 `0.5*CDF(gap_h)+0.5*CDF(jump_m)`. gap은 이전 정렬행과 정수 시간차, jump는 두 중심 간 haversine m. | 첫 행 NaN. |
| 합성 | 세 성분 중 비결측 평균(`nanmean`). 전 성분 결측이면 NaN 유지. 그 외 `[1e-6,1.0]` clip. 높을수록 이상하다는 방향. | 0은 1e-6로 바뀐다. 소량 행으로 score가 생기거나 clip floor를 받은 것을 정상 근거로 해석하면 안 된다. floor의 사고판정 의미/근거는 미확정. |

코드 근거: [run_008:420-529](D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py). 입력 `ts`는 `datetime64[h](part_dt)+rfid_time` 정수 시간 인덱스다. [remeasure:699-701](D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py); 원 timezone 변환 근거는 Round001 manifest에서도 미확인이다.

## A·시간·원행 계약 연결 및 차이

Round001 `preparation_contract.md` §점수·시각 규칙은 A를 기존 score 최대 시각, 동점이면 기존 입력 최초 등장으로 둔다. 기존 legacy A 재현 100척·8열 mismatch=0은 이미 완료되어 전수 재검사할 필요가 없다([readiness_report:7-9](../../round_001/timing/readiness_report.md), [preparation_contract:21](../../../26_11_5/testb_next_experiment_20261105/contract/preparation_contract.md)). 하지만 scorer 코드는 test 행을 `(ts, rfid_time)`로 먼저 정렬하고 `stage_submit`에서 그 결과에 `idxmax`를 적용한다. `source_row_id` 또는 월/파일/원행 ordinal이 score 함수 입력·출력에 포함되지 않으며, 같은 key의 중복행 충돌/정렬 안정성 정책도 고정 계약과 연결되어 있지 않다. 따라서 “원본 순서의 첫 최대”가 보장된다고 코드만으로 입증되지 않는다.

Round001 `timing_interface`는 A/B/C를 분리하고 source row ID를 받도록 되어 있으며, 원본 입력 순서 A, B/C만 timestamp+source ordinal 정렬, 중복 점수 충돌 `data_conflict`, 누락/NaN 구간 분리 등 경계 규칙이 있다. 이 interface는 scorer를 실행하거나 점수 행을 보존하지 않는다. 따라서 새 추론 contract에는 scorer 행마다 원자료 source key/ordinal을 부착하고, A 동점 해석을 둘 사이에 명시적으로 고정한 뒤, B/C는 감독 gate 전 계산 금지로 두어야 한다. B/C 임계·간격·지속 조건이나 floor의 사고 의미를 새로 선택하지 않는다.

## 새 v2 100척 적용 가능 조건 / 미확인

**조건부 가능:** P가 v2 명부/순서를 제공하고, 100개 ID가 `test` 입력의 전체 제공 기간 행으로 존재하며, `required columns`에 대해 유효/결측/시간 상태를 설명할 수 있고, test 행이 점수 참조를 다시 만드는 경로로 흘러가지 않도록 하면 `score_vessel` 계산 자체는 고정 train 참조로 재사용 가능하다. 계산 준비는 별도 생산 코드/복사된 고정 reference와 독립 출력 폴더에서 해야 한다.

**현재 stock CLI 기준 불가/보류:** legacy `SAMPLE_XLSX`에서 ID를 읽고, `REPO/results/work_008/`에 쓴다. 새 v2 정확 명부라는 증거가 없고 고정 출력 경로가 금지되어 있어 실행이 허용되지 않는다.

**unknown:** P가 가져올 실제 v2 명부의 개별 항적 존재·필수열·행 수·순서·중복/동일 timestamp·결측률·구간 및 기존 95 ID 겹침 적용 여부; 이번 조사에서 생성할 새100 점수의 RAM peak; timezone의 의미. 사고 신원, 정상/미사고 근거, 사고파일 개발사용 허용, 독립 event-vessel 분할, 임계값/공식 F1도 미확보이므로 score/A는 탐색값만 가능하고 정답·성능 판정을 만들 수 없다.

## 감독 권고: 성공 판정 전에 필요한 증거

1. P 산출물에서 새 v2 ID 100개와 정확한 순서, 원본 workbook/version hash, 각 ID의 2025 전체 기간 행 존재·유효행/결측/중복 요약을 받는다. ID 교집합 95는 old legacy 명부의 결과로 분리한다.
2. 새 execution manifest에 고정 code hash(본 manifest), 고정 참조의 실제 fit population/기간/feature summary와 생성 경로, 새 대상 ID membership을 **서로 다른 필드**로 기록한다. Test rows는 score input으로만 쓴다는 실행 경로를 확인하고 Test 적합·보정·분위수·임계값 생성 부재를 기록한다.
3. 추론 계약에서 `score_vessel` 입력/출력 스키마(필수열/단위, `ts`, 원행 source ID, 결측·중복 처리), score component 공식을 동결한다. A tie는 Round001 문서의 원입력 최초 순서와 scorer의 정렬 후 `idxmax`가 같은 것인지 명시적으로 해소하고 회귀 예를 추가한다. A 선정만 생산 시 허용하며 B/C는 계속 보류한다.
4. 코드의 `REPO/results/work_008` 고정 산출 경로를 실행하지 말고, 생산 실행자가 소유한 별도 출력 폴더/스냅샷에서만 동작하게 한다. 실행 직전 RAM/동시작업/예상 peak/청크 계획을 갱신하고 실제 환경, exit code, 산출물 hash를 남긴다. 이후 별도 계산자가 명부, 몇 개 원행 추적, 점수식을 독립 계산 검산한다.

## 검토 환경 및 실행 상태

- 시작 시각/RAM: 2026-11-05 03:42:28 KST; 가용 4,295.7 MiB / 총 14,140.9 MiB, process 344개, Orca/Codex 복수 세션. 상위 관측: Explorer 661 MiB, Orca 583/384/300 MiB, Codex 222 MiB. 동시 agent 작업 수는 프로세스 관측만으로 정확히 판별할 수 없어 unknown으로 기록.
- 예상 peak: 본 review는 문서, 39KB scorer 및 3개 의존 코드, 730B metadata를 텍스트로 스트리밍하고 캐시·원자료·parquet·CSV 본문을 로드하지 않음. 리뷰 프로세스 증분 peak ≤256 MiB 추정(작은 파일 본문과 PowerShell/rg 버퍼; 실제 peak 측정 안 함). 실점수 계산 peak는 대상 원행 수를 아직 모르는 상태이므로 추정하지 않음.
- Orca 안내: 먼저 `orca skills get orchestration`에서 설치본 guide를 읽음. 작업 지시/activation에는 요청·launch가 `gpt-6-luna/xhigh`로 기록되어 있으나 provider 내부 model/effort telemetry는 unknown. 작업자의 자기 관찰로 provider 실제모델을 주장하지 않음.
- 환경: Windows PowerShell 5.1.26100.9711, Python 3.13.3; canonical git HEAD `0e1cbd583abf85cfee5746c9c492949b52848404`.
- **검증 미실행:** 테스트/시뮬레이션/실제자료 점수/하드웨어 실험을 실행하지 않았다. 코드 path 실행 exit는 없음/not run. Python version 조회와 `git rev-parse HEAD`는 exit 0. 문서·코드는 읽기/해시만 했고 수정하지 않았다.

