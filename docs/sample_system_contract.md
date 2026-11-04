# 합성 샘플 시스템 계약

2026-10-12 사용자가 실제자료 수령 전 샘플로 모델과 시각화를 구현하도록 요청하여 S0 합성 실험을 시작한다. 실제 F1 자료 적합성과 별개이며 공식 조업 분류나 사고 판정 성능을 검증하는 단계가 아니다. CPU와 NumPy를 사용한다.

## 공통 데이터

`schema_version=fishing_sample_v1`, `source_type=synthetic`, `coordinate_system=local_xy_m`, `class_names=[straight,sweep,turn]`이다. 클래스는 생성 경로 유형이며 공식 fishing_code가 아니다. 전체 객체는 `metadata`와 `records`를 가진다. metadata에는 위 네 필드와 seed, generator_version, split_group_counts, 생성 가정을 넣는다.

레코드는 `sample_id`, `vessel_id`, `split`(train/validation/calibration/test/stress), `label`(0,1,2 또는 null), `parts`(부분선별 XY 점 배열), `sim_times`(부분선별 초 배열), `scenario`(base/shift), `quality`를 가진다. 시뮬레이션 시각은 실제 관측 시각이 아니다. 모델 입력은 parts에서 계산한 geometry만 사용한다. label/vessel_id/split/sim_times/scenario/quality는 특징에 넣지 않는다. 부분선 경계는 보존한다. 원자료용 inspect_data.py 및 기존 합성 fixture 계약은 변경하지 않는다.

## 모듈 인터페이스

- `fishing_demo/data.py`: `generate_dataset(seed=42, groups_per_split=None, samples_per_class=4) -> dict`; 기본 그룹 수 train=36, validation=12, calibration=12, test=12, stress=12. 그룹마다 세 클래스 모두 생성. 독립 RNG와 그룹별 특징 차이. stress는 사전 고정 배율/잡음/단절 변화. `validate_dataset(dataset) -> None`은 중복ID, 선박분할 중복, 좌표계, 유한수, 부분선/시뮬레이션 시각 정합성을 검사. `validate_record(record) -> None`은 개별 입력 검사. `write_dataset(dataset,path)`/`load_dataset(path)`.
- `fishing_demo/features.py`: `FEATURE_NAMES`, `FEATURE_UNITS`; `extract_features(record) -> dict`의 keys=`values`(feature 순서의 float/null), `valid`(bool), `reason`(str/null), `parts`(각 부분선 length_m/displacement_m/straightness), `quality`(관측점수 등); `feature_matrix(records) -> (np.ndarray, list[dict])`에서 결측은 NaN. 공간 회전/이동에 불변인 특징을 사용하고 집계 직선성 ΣD/ΣL는 도입하지 않는다. 모든 길이가0 또는 사용할부분선없음이면 valid=false.
- `fishing_demo/models.py`: `Preprocessor.fit(X)`, `.transform(X)`, `.to_dict()`, `.from_dict(state)`; train 관측중앙값 대치+평균/표준편차+결측mask. `Classifier(input_dim,n_classes=3,hidden=0,l2=0.01,seed=42)`; `.loss_and_gradients(X,y)` -> `(loss,dict)`; `.fit(X,y,X_val,y_val,epochs=400,learning_rate=0.03,patience=35)` -> history(list of epoch/train_nll/val_nll/train_objective); `.predict_logits(X)`; `.to_dict()/.from_dict`. 선형 또는 tanh16, 안정softmax, 완전batch GD, L2 weights만, valNLL best checkpoint. `softmax(logits,temperature=1.0)`, `classification_metrics(y,probs)`(accuracy/macro_f1/nll/brier/confusion/support), `fit_temperature(logits,y)` -> float, `AnomalyModel.fit(X,y,n_classes=3,shrinkage=0.2)`, `.score(X)`, `.to_dict()/.from_dict()`. classconditional shrinkage 공분산 최소 제곱Mahalanobis. 전처리된mask열도 사용. label 유효 subset을 먼저 선택, invalid index 계산 금지.
- `fishing_demo/pipeline.py` 및 `tools/run_sample_system.py`: root 소유. data→검사→feature→trainfit→val선택→cal보정→test/stress→JSON모델/예측/보고서→HTML. 모델 재사용 추론. 고정 후보군만 비교하고 test로 재선택하지 않는다.
- `fishing_demo/visualization.py`: 별도 담당. `write_dashboard(report, predictions, output_path)`; 자체 포함HTML, 외부 의존/네트워크없음. report 및 predictions JSON 계약은 통합담당이 제공한다.

### 화면 JSON

report keys: `schema_version`, `source_type`, `seed`, `class_names`, `feature_names`, `feature_units`, `split_summary`(split별 samples/groups/valid/abstained), `candidates`(name/hidden/l2/best_epoch/validation_metrics/history), `selected_model`, `temperature`, `metrics`(train/validation/calibration/test/stress 각각 accuracy/macro_f1/nll/brier/confusion/support, before_calibration 별도), `majority_baseline`(test/stress metric), `anomaly`(threshold/threshold_source=validation_95_percentile/score_description/각split분포), `audit`, `limitations`, `runtime`.

predictions는 list이며 각 항목 keys: `sample_id`,`vessel_id`,`split`,`source_type`,`true_label`,`predicted_label`(유보null),`probabilities`(유보null),`anomaly_score`(유보null),`anomaly_flag`(유보null),`status`(ok/abstained),`reason`,`parts`(XY arrays),`features`(float/null list),`part_metrics`,`quality`. 이 필드로 필터/항적 Canvas/클래스확률/특징값/부분선경계/혼동행렬/학습곡선/성능비교를 표시한다. 좌표는 지역미터이며실제지도아님. score는사고확률아님. 정답은syntheticclass. JSON text는script종료/XSS안전하게embed하고 textContent사용.

## 오류와 평가

빈/모두0 경로는 유보한다. 잘못된좌표/정렬/중복은 ValueError로 거절한다. split group은 겹치지 않으며 각 class가 모든 split에 존재해야 학습가능하다. 모든 모델/대치/표준화/공분산 적합은 train만 사용한다. val은 후보와epoch선택, cal은온도만, test와stress는결과산출만 사용한다. 불확실성·분포이탈·사고는 다른 개념이다. 실제자료 일반화 성능은 원자료 평가 후 판단한다.

## 실행 역할

종합 설계 Astra high, 데이터·기하 Sol xhigh, 모델·원인분석 Sol max, 검토 Sol high, 해설 문서 Luna xhigh. 각각 단일 소유 파일만 수정하며 실제 작업에서 요청한 설정을 기록한다.
