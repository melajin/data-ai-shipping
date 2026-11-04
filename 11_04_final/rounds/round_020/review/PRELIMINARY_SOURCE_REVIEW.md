# Round020 사전 입력·계보 검토

검토 시각: 2026-11-05 08:22:30 KST. 범위는 저장된 seed42 입력의 역할·명부·클래스 순서 확인이다. 당시 round020의 `run_performance.py`와 `configs/experiment.json`은 아직 없어 실행 소스 승인이나 OUTER 열람 승인은 하지 않았다.

## 자원 및 접근 범위

- 작은 메타데이터와 선택확률 확인 직전 가용 RAM 4.67 GiB / 총 13.81 GiB. 상위 관찰 프로세스는 Orca 0.44/0.35/0.16 GiB, Explorer 0.43/0.16 GiB, Codex 0.27/0.21/0.19 GiB 등이며, 이번 검토에서 새 프로세스나 학습은 시작하지 않았다. 예상 최대 메모리 <1 GiB는 압축된 ID/역할/라벨과 394×4 선택 확률 배열만 읽는 범위 추정이고 실제 peak RSS는 측정하지 않았다.
- 읽기 전용 자료: round002의 설정·보고서·FIT/INNER 분할 manifest/roster·학습 코드·INNER_SELECT 확률 NPZ, round003의 설정·보고서·독립 검토·TabICL 생성 코드·클래스/개발 역할 메타데이터·seed42 fold별 INNER CSV.
- 원자료 `F:` 경로, Test2025/holdout, round003 `original_oof_predictions.csv`, 저장된 OUTER 확률/예측은 열지 않았다. TabICL INNER CSV의 확률값은 INNER_SELECT 394행만 검사했다. ES 행에서는 ID/라벨만 확인하고 확률 열은 수치화하지 않았다.

## 확인된 결과

1. round002의 `run_round002_resume.py`는 fold별 모델 fit index를 `roles == FIT`로 만들고, 조기종료 평가자료로만 INNER_ES를 전달한다. LightGBM과 CatBoost 모두 INNER_SELECT은 예측·저장에만 사용한다. 모델 클래스는 `[0,1,2,3]` 순서인지 명시적으로 검사한다. 4개 클래스 이름은 round002 코드와 round003 `metadata/classes.json`의 0–3 매핑이 일치한다.
2. `inner_split_manifest.json`/`inner_split_roster.csv`는 seed 20261105, 층화된 50% INNER 분할을 기록한다. 각 fold에 INNER 787, ES 393, SELECT 394행이 있다. 선택 명부와 라벨의 분할 hash가 보존되어 있다.
3. 읽기 전용 교차 대조에서 round002 feature-cache의 ID/role이 round003 개발 역할 명부와 fold별로 일치했다. FIT/INNER/OUTER 수는 fold0=`3144/787/1966`, fold1=`3144/787/1966`, fold2=`3145/787/1965`다.
4. 세 fold 모두 저장된 LightGBM 및 CatBoost `INNER_SELECT` 파일은 정확히 같은 394개 SELECT ID와 라벨을 갖는다. TabICL의 해당 fold `evaluation/seed_42/fold_{f}/inner_predictions.csv`는 787개 INNER ID/라벨과 일치하고, 그 안의 394개 SELECT ID/라벨도 두 저장 모델과 일치한다. 세 모델의 SELECT 확률은 유한·[0,1] 범위·행합 검사를 통과했다. TabICL SELECT 최대 행합 오차는 2.22e-16이었다.
5. round003 독립 검토와 확인한 source text에 따르면 TabICL 생성 경로는 `model.fit(fit_x, fit_y)`를 사용하고 INNER를 fit/early-stop/선택에 쓰지 않았다. 저장 probability schema의 `p0..p3`는 class metadata의 0–3 순서다. `original_oof_predictions.csv`는 이번 INNER 구성의 대체 입력으로 쓰면 안 된다.

## 제한 및 사전 동결 전 접근 기록

- round003의 기존 lineage 검토는 이전 INNER ID-hash의 원래 직렬화/행 순서를 복구하지 못해 해당 historical hash를 `unverified`로 남겼다. 이번 검토는 fold 역할과 SELECT membership을 ID로 직접 대조했으며, 그 역사적 serializer 불확실성 자체를 해소한 것은 아니다.
- 제한을 정확히 기록한다. 교차 대조 스크립트가 round002 입력 NPZ에서 `y` 벡터를 읽어 INNER 라벨 대조에 사용했으므로, **5,897개 개발 라벨 중 OUTER 라벨도 메모리에 로드됐다**. OUTER 확률·예측·feature 값은 읽거나 해석하지 않았고, 라벨로 후보·파라미터를 변경하지 않았다. 따라서 이 사전 검토를 새 맹검 평가 또는 OUTER 값 무접근으로 표현하지 않는다.
- 개발 명부는 반복 노출된 자료이며 독립 평가가 아니다. 2026년 코호트라는 명시적 출처 정보는 있으나 예측 확률 CSV 자체에는 `year` 열이 없으므로, 이후 2026 연도 표시는 row-wise 측정값이 아니라 출처 기반 cohort 가정으로 써야 한다.
- F304와 F156의 입력 표현은 다르므로, Round020은 같은 특징 비교가 아니라 동일 SELECT 선박의 저장 확률 결합이다. 기존 T5/local_rel 모집단 조건과 TabICL 전처리 폭의 과거 문서 불일치는 별도 제한이다.

**판정:** 저장된 확률의 역할 및 SELECT 명부 정합성은 지원된다. 실행 소스·설정 SHA 동결, 독립 코드 검토, manager 승인, OUTER 1회 열람은 별도 미완료 관문이다. Round020의 성능이나 OUTER 지표에 대한 판정은 하지 않았다.

## 실행 전 추가 하드 게이트 — 2026-11-05 사용자 수정

관리자에게 전달된 사전 집계에서 class-0/3 보호 기준이 강화됐다. round020 동일조건 baseline의 TP0=2,389 및 historical 5-seed의 TP3=92를 각각 하한으로 고정한다. 지원수가 `[2920, 2016, 835, 126]`이면 후보는 TP0≥2,389, TP3≥92를 모두 만족해야 한다. 이산 TP와 함께 class별 precision/recall/F1, FP 및 baseline↔candidate confusion-transition gain/loss/net을 보고하고, class-1/2 변화도 상세히 보존한다. 같은 TP는 서로 다른 선박의 정답 교체로 바뀔 수 있으므로 ID별 transition도 검산한다.

참고 집계는 `manager/historical_protection_reference.json`의 출처·해시와 기존 aggregate다. 역사적 per-vessel prediction의 ID/y/fold 대조는 동결 후 수행하는 것으로 보존한다. 이 리뷰는 해당 per-vessel 파일을 열지 않았다. 강화 게이트의 config/code 반영과 독립 검토는 아직 대기 중이다.

## 근거 경로

- `rounds/round_002/configs/experiment.json`
- `rounds/round_002/artifacts/inner_split_manifest.json`, `inner_split_roster.csv`, `fit_accounting.json`
- `rounds/round_002/code/run_round002_resume.py`
- `rounds/round_002/artifacts/probabilities/fold_{0,1,2}_{baseline_lightgbm,candidate_catboost}_inner_select.npz`
- `rounds/round_003/configs/experiment.json`, `ROUND_REPORT.md`, `review/FINAL_REVIEW.md`
- `rounds/round_003/code/run_round003.py`, `verification_20261105/VERIFICATION_REPORT.md`
- Read-only package metadata: `metadata/classes.json`, `splits/development_roles_long.csv`, `evaluation/seed_42/fold_{0,1,2}/inner_predictions.csv`
