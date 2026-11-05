# Round022 S1 선행 CV — 입력 계보 사전 검토

상태: **전체 게이트 소스 승인 보류**. 이 검토는 소스·메타데이터와 합성 엔진의 정적 코드만 조사했다. 현재 S1 공간 프로필 입력 캐시와 생성 manifest가 없고, `run_gate.py` 및 실행 입력의 해시 동결도 완료되지 않았다. 학습·평가·합성 검사는 실행하지 않았다.

## 범위와 결과

- 읽은 작업 기준: `AGENTS.md`, `CYCLE_PROTOCOL.md`, `docs/20261105_CODEX_인계_0.7_실행계획.md`, `rounds/round_022/ROUND_PLAN.md`, `rounds/round_022/configs/experiment.json`.
- 원본 코드와 생성 스크립트는 읽기 전용으로 조사했다. 학습 라벨·NPZ 값·개별 ID·원자료 행은 출력하지 않았다. 2025/holdout 원자료 행은 읽지 않았다. `testB/first_results/harbors.json`은 train-only 산출물임을 생성 코드로 확인하고 점 개수·메타 키만 확인했으며 좌표는 열람·출력하지 않았다.
- 독립 T5 엔진은 코드만 정적으로 검토했다. 라벨 자기제외는 전역 카운트, 스무딩 prior, fine/coarse 셀 카운트, 전역 폴백에 적용되어 있다. 의미 있는 합성 불변 검사는 아직 실행되지 않았다.
- 관리자 메시지 기준 2026-11-05 01:44 UTC 가용 RAM은 0.475 GiB이며 `s4_score_dev.py`가 실행 중이었다. 이 리뷰는 읽기 전용 문서·코드 조사로 제한했고 실행하지 않았다. 이는 관리자가 제공한 자원 증거이며 이 리뷰의 호스트 재측정값이 아니다.

## T5 계보 및 누출 발견

기존 구현 경로는 `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\tools\run_005_main_20261101.py` → `run_005_F156_merge_20261101.py` → `run_cycle4_3_featAC_20261101.py` / `run_remeasure_20261031.py`다. `run_010_t5_fallback_20261101.py` 사본은 `D:\repos\fishing-track-classification\code\tools\`에 있다.

- `run_005_main`은 fold별 `FIT` ID/라벨만 `_build_t5_dicts`에 전달하고 `t5_features_for`로 FIT·INNER·OUTER 행을 계산한다.
- label-free 행 기하는 `_train_arrays()` → `_load_year_arrays('train')` → `remeasure.load_rows('train', [rfid_id, part_dt, rfid_time, len_m, bbox_m, cen_lon, cen_lat, wkt_valid])` 경로다. 월별 파일 경로는 `outputs/remeasure_20261031/rows_train_1..6.parquet`이며 `month`는 `part_dt`에서 유도된다. 라벨은 별도 `train_labels.csv`에서 읽어 fold FIT 목록에만 붙인다. 이 리뷰는 이 행 캐시를 열지 않았다.
- 구형 `_fishing_mask_global()`은 `_lean_build_harbors()`를 호출하고, 이 함수는 `_train_arrays()`와 `_test_arrays()`를 함께 로드한다. 따라서 기존 T5의 공용 항구 참조에는 Train2026 및 무라벨 Test2025 기하가 쓰인다. 기존 T5 캐시 경로는 `.../outputs/f156_merge/for_teammate/fold_{0,1,2}_t5.csv`; 이 캐시는 fold 내부 CV의 라벨 통계를 다시 계산할 수 없어 직접 대체 입력이 아니다.
- 구형 `_query_grid_distribution()`은 FIT 자신의 클래스를 지역 셀 카운트와 최종 global fallback에서는 빼지만, 호출 초기에 `prior = dicts['global'] / sum(...)`를 만들어 스무딩에 사용한다. 따라서 fine/coarse 스무딩 posterior에는 자기 라벨이 남는다. 이 동작은 S1 또는 내부 CV 기준선에 그대로 복사하면 안 된다.
- 304열 구성은 `F156(156) + T5(10) + behavior(68) + local_rel(70)`이다. 기존 T5 중 posterior 8열과 `t5_fine_grid_ok_ratio`는 FIT 라벨에 의존하므로 내부 CV의 각 학습 분할에서 재계산해야 한다. `t5_log1p_fishing_rows`는 라벨 비의존 집계다. 동일 재계산은 기준선·후보 모두에 적용해야 한다.

## 기존 공간 캐시의 가용성

- round021 config는 공간 소스를 `26_11_2/work/재식별_투트랙_001r1/s6_fingerprint_grid.parquet`로 지정한다. producer `s6_fingerprint_build.py`는 `s3_hourly.parquet`를 선박×연도별로 묶고 0.01°/0.05° 셀의 `block='full'` 가중 프로필을 만든다.
- 저장된 round021 manifest의 추출 predicate는 `year==2026 AND block=='full' AND res in {0.01,0.05}`이고 2026 개발 ID로 제한한다. 결과는 선박·해상도별 합이 1인 `spatial_profiles.csv`다. 월별 프로필과 0.10° 프로필은 이 캐시에 없다. 따라서 24개 S1 feature를 직접 만들 수 없다.
- 작업 루트의 파일명 목록 검색에서 별도의 현재기간 `.01/.05/.10 × full/month` 프로필 NPZ 및 manifest는 확인되지 않았다. `rounds/round_022/code/t5_rebuild.py`가 요구하는 `artifacts/t5_fishing_profiles.npz` 및 `.manifest.json`도 아직 없다. 실행 입력은 준비되지 않았으므로 이 경로는 fail-closed 상태여야 한다.
- `cycle4_common.load_bd_raw()`의 입력 필드는 `vessel_key/date/grid_x/grid_y/active/near_stationary/turn4`다. 이 경로는 T5 fishing mask를 저장하지 않는다.

## 확인된 train-only 항구 cache와 한계

- `D:\repos\fishing-track-classification\results\work_008\train_harbors.json`과 `testB/first_results/harbors.json`이 존재한다. 후자는 `testB/first_results/run.py`가 `run_008_testB_20261101.py::build_train_harbors()`를 불러 저장한다.
- 이 builder는 `rows_train_1..6.parquet`에서 `wkt_valid`, `len_m`, `bbox_m`, `cen_lon`, `cen_lat`, `rfid_id`를 읽고, 정박 후보를 0.005° 셀·최소 서로 다른 선박 20척으로 묶어 항구점을 생성한다. 저장 JSON은 `{meta, points}`이며 metadata에는 `grid_deg`, `min_vessels`, candidate/harbor 개수, 기준 위도가 있다. 확인한 cache는 77개 항구점이다.
- 이는 train-only aggregate이지 full row별 fishing mask 또는 선박별 own-mooring cache가 아니다. legacy T5의 train+Test2025 공용 항구점을 재현하지 않으며, 같은 이름의 폴백 입력으로 취급할 수 없다. 기존 `run_008` 코드는 own-moorings를 매번 Train 행에서 다시 만든다.

## 소스 승인 전 필수 확인

1. Test2025 기하는 CYCLE_PROTOCOL 5항의 기존 transductive 공용 항구 복원 범위에만 한정한다. row projection에 label, 테스트 예측/출력, 테스트 query profile을 포함하지 않는다. manifest는 `2025 rows=0`처럼 과장하지 말고, 예를 들어 `2025_geometry_read_for_shared_harbor=true`, `2025_labels_read=false`, `2025_query_rows_materialized=0`, `test_outputs_used=false`를 분리해 기록한다.
2. **holdout 경계**: `rows_train_1..6.parquet`에는 개발 FIT 이외의 Train2026 선박도 존재한다. 이를 전부 읽는 작업은 현재 작업 지시의 holdout 금지에 걸릴 수 있다. 2025 공용 항구 예외만으로 holdout 읽기까지 허가된 것으로 확대 해석하지 않는다. 개발 ID만으로 만들면 legacy 참조와 달라지므로 변경을 기록하고 동일절차 기준선·후보에 적용해야 한다. 관리자가 허용 범위를 결정하기 전 행 캐시 스캔을 승인하지 않는다.
3. 새 harbor producer가 legacy와 같은 필드·조건·산식을 쓰는지 검토한다: key/wkt validity, stop 조건 `len_m<=50 && bbox_m<=100`, 0.005° 셀, 셀별 unique vessel 수, threshold 20, 8방향 연결, 셀 중심 평균, 모든 stop-row의 기준 위도, nearest-harbor 거리 구현.
4. `t5_fishing_profiles.npz` 생성기는 2026 FIT query에 필요한 필드만 투영하고, FIT roster/order/hash, 원천 경로·SHA256·필드·집계 규칙·월별 범위·record_count 의미를 manifest에 묶는다. holdout/Test 행을 query profiles에 넣지 않는다.
5. 합성 검증은 충분히 비대칭인 클래스·셀 fixture로 local fine, local coarse, global-prior smoothing, global fallback 각각의 경로를 실제로 유도한다. 한 FIT query의 라벨만 바꿔 그 행의 출력이 모든 경로에서 불변인지 확인한다. validation 라벨 permutation은 CV wrapper에 검증 라벨을 전달하지 않고 결과가 불변임을 보여야 한다. 기존 점수나 실제 데이터 값으로 합성 fixture를 만들지 않는다.
6. score gate는 계획의 최신 고정값을 따른다: 전체 진행은 `candidate >= 1833/3144` **그리고** 같은 절차 기준선 대비 `candidate_correct - baseline_correct >= 16`을 모두 만족해야 한다. 한 조건만 통과하면 full run은 0회다. 이 리뷰에서 점수를 계산하지 않았다.
7. 전체 gate 승인 해시는 `code/t5_rebuild.py`, 입력 cache builder, CV runner, `configs/experiment.json`, `ROUND_PLAN.md`, `manager/launch.py`를 모두 포함해야 한다. 입력 cache builder가 완성되기 전 승인 JSON은 만들지 않는다.

## 현재 판정

`t5_rebuild.py` 정적 검토상 global prior를 포함한 leave-self-out 흐름은 타당해 보인다. 다만 입력 cache가 없고 Test2025/holdout 범위와 cache 생성 규칙이 미확정이며, S1 runner 및 synthetic assertion 소스가 아직 동결되지 않아 **전체 게이트 실행 승인 없음**이다. 다음 검토는 manager의 cache builder와 writer의 CV runner/synthetic check가 준비된 후, 소스 해시와 입력 manifest를 읽기 전용 검증하는 것이다.
