# Round022 S1 선행 CV — 입력 계보 사전 검토

상태: **전체 게이트 승인 없음; cache-builder source review 중**. 입력 cache와 manifest는 아직 생성되지 않았고, `run_gate.py` 및 합성 checker 해시도 동결되지 않았다. 학습·평가·합성 검사는 실행하지 않았다.

## 범위와 결과

- 읽은 작업 기준: `AGENTS.md`, `CYCLE_PROTOCOL.md`, `docs/20261105_CODEX_인계_0.7_실행계획.md`, `rounds/round_022/ROUND_PLAN.md`, `rounds/round_022/configs/experiment.json`.
- 원본 코드와 생성 스크립트는 읽기 전용으로 조사했다. 학습 라벨·NPZ 값·개별 ID·원자료 행은 출력하지 않았다. 2025/holdout 원자료 행은 읽지 않았다. `testB/first_results/harbors.json`은 train-only 산출물임을 생성 코드로 확인하고 점 개수·메타 키만 확인했으며 좌표는 열람·출력하지 않았다. 이후 사용자는 기존 CYCLE#5와 같은 **Train2026+Test2025 정박기하의 공용 항구 aggregate만** 명시 허용했다. 이는 2025/holdout 라벨·예측·평가·개별 출력 허용으로 확대하지 않는다.
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

## 01:52 UTC 사용자 경계 갱신 및 cache-builder 정적 검토

사용자 승인 경계는 Train2026 전체와 Test2025의 정박(stop) 기하를 기존 공용 항구 aggregate에만 사용하도록 한정한다. Train2026+Test2025의 `key_valid`, `wkt_valid`, `len_m`, `bbox_m`, 좌표, 항구 distinct-vessel 집계 목적의 ID만 허용 범위에 들어간다. query/T5 profile은 2026 fold0 FIT에 한정한다. Test2025 label·prediction·evaluation·개별 출력과 동일 선박 라벨 승계는 계속 금지다.

`prepare_t5_cache.py` 정적 검토 결과:

- source는 `rows_train_1..6.parquet`와 `rows_test_1..6.parquet`를 32,768행 batch, `use_threads=False`로 스캔한다. 항구 집계 projection은 train에 `rfid_id, cen_lon, cen_lat, rfid_time`, test에 `rfid_id, cen_lon, cen_lat`만 요청하며, stop predicate는 `key_valid && wkt_valid && len_m<=50 && bbox_m<=100`이다. Label이나 output/probability input은 참조하지 않는다.
- SQLite primary key `(cell_x,cell_y,vessel)`로 동일 격자·선박 중복을 제거하고 cell별 unique vessel 수≥20을 유지한다. 8방 연결, cell-center 평균, 모든 stop row를 가중한 기준 위도, cKDTree 및 haversine 검산은 기존 helper의 정적 알고리즘과 맞는다.
- train의 FIT 3,144 ID만 own-mooring 및 query profile 용도로 제한한다. own mooring은 동일 FIT vessel의 night stop rows에서 상위 3개 셀을 사용한다. query filter는 Train2026 `len_m>50` + validity이며, 결과 profile에는 FIT row index·월·fine/coarse grid·record count만 적재한다.
- 3144 FIT 행의 기존 `t5_log1p_fishing_rows`와 새 fishing-row count를 비교하는 것은 검증 가능한 count equivalence다. 행별 mask pointwise equivalence는 검증하지 않는다. `fishing_mask_equivalence_verified=true`라는 이름은 evidence보다 넓으므로 `fishing_row_count_equivalence_verified=true`, `pointwise_mask_equivalence_verified=false`로 바꾸고 `t5_rebuild.prepare_t5` 계약도 맞춰야 한다.
- `harbor_distinct.sqlite`에 train/test의 raw vessel key와 spatial cells를 임시 저장한다. 정상 성공 경로는 `DROP TABLE`+`VACUUM`을 해 aggregate table을 버린 뒤 FIT-only profile table을 남긴다. 예외·deadline kill에서는 정리가 보장되지 않으므로 owned-stage launcher의 실패 후 exact-path/sidecar cleanup을 추가해야 한다.
- source parquet/BASE NPZ hash는 현재 scan 이후 기록되며 before/after 일치 검사가 없다. scan 전후 source SHA 재검증을 더한다. `BASE` feature index 165의 이름도 NPZ `feature_names`에서 `t5_log1p_fishing_rows`인지 확인한다. `np.nanmax`는 비교값 전체가 NaN일 때를 별도로 처리한다.

parent의 01:52 UTC 경계 update에 따라 기존 “Test2025/holdout 범위 불명” 문장은 superseded다. 전체 gate 승인 여부와 별개로, cache-builder의 위 blocking issues가 해결될 때까지 source approval을 보류한다. 수정을 확인한 뒤 이 단계만 `prepare_approved_sources.json`으로 hash-bound 승인할 수 있다. 이 승인은 cache generation만 허용하며 CV score run이나 전체 gate를 승인하지 않는다.

## 현재 판정

`t5_rebuild.py` 정적 검토상 global prior를 포함한 leave-self-out 흐름은 타당해 보인다. 다만 입력 cache가 없고 Test2025/holdout 범위와 cache 생성 규칙이 미확정이며, S1 runner 및 synthetic assertion 소스가 아직 동결되지 않아 **전체 게이트 실행 승인 없음**이다. 다음 검토는 manager의 cache builder와 writer의 CV runner/synthetic check가 준비된 후, 소스 해시와 입력 manifest를 읽기 전용 검증하는 것이다.


## 02:10 UTC ?? ? ????? ????? ??? ??

? ??? ?? ?cache ?? / source approval ?? / ?? ?? ???? ?? ??? ????. ?? ?? ??? ?? ?? ??? ???.

- ???? Train2026 ? Test2025? ?? ?? ?? ?? ??? ????. ? ??? ????????, Test/holdout ?? query/profiles? ???? ???. ??3fold? S2? ?? ???? ??? ???? 0??.
- ?? ??? ???? review/s1_prepare_approved_sources.json?? --prepare-s1 ???, review/gate_approved_sources.json?? FIT 3,144??? ?? 4-fold 8-fit gate? ????. ??3fold/S2 ?? ??. run_gate.py? T5 class literals? UTF-8? ???? ?? ?? 4? class-name codepoint? ???? ????. ? PowerShell ??? mojibake? ANSI ?? ????? ?? defect? ????; ?? writer? ?? ??? ???? ?? ???? Unicode escape? ????.
- T5 cache preparation receipt? exit 0, 41.74?, sampled peak family RSS 0.301 GiB, sampled minimum available RAM 3.04 GiB? ????. ?? audit? 3,144 FIT ?? log1p_fishing_rows ??, ?? ??? 8.88e-16; pointwise_mask_equivalence_verified=false??? ?? mask ???? ???? ???. ?, launcher? T5 ?? receipt?? run_gate.py ??? ?? ??/?? ?? ???? (dd5c... ? ec863...). T5 producer ??? ??? ???? ?? ??? ????? receipt ??? ????. ? ??? gate ?? ?? ?????, ?? gate ??? ?? ??? ??? ?? ????.
- S1 cache preparation receipt? exit 0, 25.97?, sampled peak family RSS 0.427 GiB, sampled minimum available RAM 3.07 GiB?? ?? ?? ?? source hash ???? ????.
- manager/synthetic_checks.py? ?? JSON? ???? ????. ??? ?? ??? 6-vessel synthetic fixture?? T5/S1 self-label change ??, fixed-train validation-label permutation ??, donor-label positive control, donor ?? ??? ???? real data/fits? 0??. ? ???? ?? checker? ?? ????? ???.
- ??? gate launcher? 02:10 UTC cutoff? ????. receipt? deadline_stop, exit 15, 82.69?, ??/?? ?? source hash ?? ? ?? hash? ????. fit_progress.json?? 2? ??/??? ???? ?? fold 0 baseline/candidate ?? ? ??? ??? progress ??? ???. fold 0 private evidence archive? header? ??? (2026-11-05 ?? ?? ? RAM available 3.65 GB, ?? Python ?? 0): train 2,358, validation 786, train labels 2,358, T5 3,144?10, S1 3,144?24. ?? ?????ID? ???? ???.
- gate_result.json? ? prediction NPZ? ??. ??? ?? cutoff? ?? ??? ???? score ??? ??? ?? ???paired delta?numeric gate ??? ????. ??? 6 fits, ?? reload, aggregate/per-fold score ?? ??? ???? ???. ?? ??? review/partial_gate_audit.json??.
