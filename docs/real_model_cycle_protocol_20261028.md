# 실제 선박 분류 재학습·평가 계약

고정일: 2026-10-28. 사용자가 **실제자료 점검 후 재학습·평가**를 명시 승인했다. Sol medium 감독, Luna high 반복 구현·실행으로 진행한다. 본 문서는 모델 학습 전에 고정한 내부 연구 계약이며 공식 대회 점수 산식이나 실선 운용 기준이 아니다. 실제자료 파일 근거는 [첨부 확인](real_support_evidence_20261028.md), 역할·경계는 [감독 기록](evaluation_cycle_supervision_20261028.md)을 따른다.

## 질문과 학습 목표

기존 shape9의 형상 표현과 MLP 학습 코드를 실제 조업 라벨로 다시 학습했을 때, 처음 보는 선박을 구분할 수 있는가? 한 선박의 평균 형상만 보는 모델에 형상의 분포를 더하면 분류·확률·월별 자료 누락에 대한 안정성이 개선되는가?

기존 저장 가중치는 합성 `straight/sweep/turn`의 세 생성 유형에 학습됐다. 실제 조업 범주와 대응하는 정답이 아니므로 그대로 실제 fishing_code 성능을 계산하지 않는다. 실제 라벨 수에 맞춰 출력층을 구성하고 전처리·모델·보정을 새 train에만 적합한다. 기술 목표는 재현 가능한 실제자료 내부 평가이며 학습 목표는 입력 가정, 선박 분할, 평균과 분포의 차이, 남은 오분류를 설명하는 것이다.

## 입력 점검과 계산 범위

CSV 전체 metadata/해시는 스트리밍으로 점검한다. 모든 행의 WKT를 검사했다고 주장하지 않는다. labeled Train 각 월 CSV에서 선박별 `SHA256(vessel_hash || file_ordinal || record_ordinal)` 순위가 가장 작은 4개 행을 선택한다. 6개월 최대 24개 행/선박이며 라벨값·geometry값·예측결과로 선택하지 않는다. 이는 계산량을 제한하고 월별 자료 기회를 맞추는 연구 가정이다. 원본 파일과 record ordinal로 추적하며 ID는 salted hash로 대체한다.

전체 metadata에서 라벨 누락·복수 라벨 선박을 집계하고 **유일한 비어 있지 않은 조업 라벨 하나를 가진 선박만** primary 모집단에 포함한다. 라벨 충돌을 다수결 정답으로 덮지 않는다. 제외 선박·행과 원래 class/ship counts를 보고한다. 각 클래스 선박이 10척 미만이면 해당 계약의 분할·평가를 보류한다. Test의 무라벨 파일은 학습·선택·보정·성능평가에 사용하지 않는다.

공식 X=경도/Y=위도 설명을 근거로 레코드 관측점 평균 `(lon0,lat0)`에서 `x=(lon-lon0)·π/180·cos(lat0·π/180)`, `y=(lat-lat0)·π/180`인 국소 접평면 각좌표를 사용한다. exact EPSG/측지 datum은 미확정이다. 무차원 특징이므로 공통 지구반경을 생략한다. 경위도 유한 범위 밖, 경도 또는 위도 span>20도, |lat0|>85도는 명시적으로 유보한다. 이 span/극점 경계는 설계 가정이며 장치 허용값이 아니다. 부분선을 연결하지 않고 점별 시각·속력·가속도·미터 거리를 만들지 않는다.

각 선택 행에서 기존 shape9 순서의 무차원·각도 특징 9개를 계산한다. 동일 선택 행에서 cos 보정 없는 degree_control도 개발 민감도용으로만 계산한다. 잘못된/빈/길이0 기하와 누락 특징은 이유를 보존한다. 유효 행이 하나도 없는 선박은 최종에서 제외해 점수를 올리지 않고 유보와 coverage를 남긴다. 지표의 평가가능 선박 분모는 후보 사이 동일해야 한다.

## 고정 모델과 최대 반복

모든 모델의 관측 단위·정답·평가 단위는 **선박**이다. 행수 많은 선박에 학습 가중치가 자동으로 커지지 않는다. 각 선박의 선택 유효행을 요약한다. 특징별 available 값만 집계하고 없는 값은 결측으로 남긴다.

| 단계 | 모델 | 선박 입력 | 고정 학습 조건 |
| --- | --- | --- | --- |
| 기준 R0 | mean9 MLP | 행별 shape9 평균 9개 | hidden16, L2=.01, max400 epoch |
| 변경 R1 | distribution36 MLP | 평균9 + 모집단 표준편차9 + 25%분위수9 + 75%분위수9 | hidden16, L2=.01, max400 |
| 변경 R2 | distribution36 linear | 같은 36개 | hidden0, L2=.01, max400 |
| 변경 R2 | distribution36 ExtraTrees | 같은 36개 | 256 trees, min_samples_leaf=2, max_features=1.0(실수: 전체 입력 특징), n_jobs=1, class_weight=None |

MLP/선형은 기존 NumPy full-batch GD, learning_rate=.03, patience35, validation NLL best checkpoint다. train 중앙값 대치·표준화·원래 결측 mask를 사용한다. 별도 calibration에서 각 초기화 모델의 양의 온도를 정하고 확률을 평균한다. 트리는 확률 class 순서를 확인하고 `log(clip(p,1e-15,1))`에 동일 온도 보정을 적용한다. 시간·좌표 원문·선박ID·라벨·월·행수는 입력 특징에 넣지 않는다.

변경 라운드는 최대 두 번(R1, R2)이며 위 후보 네 개 밖으로 확장하지 않는다. 개발 결과를 분석하되 최종을 보며 특징·후보·기준을 고치지 않는다. R1도 적격이어도 사전 고정된 R2 비교를 끝내고 개발 규칙으로 하나만 선택한다. 오류 수정이 필요하면 원인을 기록하고 최종 개봉 전만 재실행한다. 최종 후 계산 결함 수정은 원래 평가를 무효화한 별도 정정으로 기록하며 성공으로 바꾸기 위한 튜닝에 사용하지 않는다.

## 분할·선택·보정

먼저 라벨별 선박 hash의 seeded 순위(seed=20261028)로 final `max(2,floor(.2*n_class))`척을 잠근다. 나머지 개발 선박에서 seed 3201, 3202, 3203별 라벨층화 hash 순위로 train 약70%, validation 약15%, calibration 나머지를 구성한다. 정수 정책은 개발 클래스 수 d에서 validation=`max(2,floor(.15*d))`, calibration=`max(2,d-floor(.7*d)-validation)`, train=`d-validation-calibration`이며 각 분할 클래스 최소 2척을 확인한다. 예를 들어 전체 10척이면 final2/train4/validation2/calibration2다. 작은 클래스에서는 최소 지원을 위해 비율이 달라진다. SHA-256 직렬화는 runner protocol JSON에 보존한다. 선박 중복은 허용하지 않는다.

각 개발 분할에서 init seed 42·137로 각각 학습·보정한 뒤 두 확률을 평균해 하나의 선박 예측을 만든다. 세 개발 분할은 같은 원자료를 공유한다. 이를 독립 표본 3개나 선박 수가 세 배인 자료로 계산하지 않는다. 개발 비교는 방향성·선택용이며 seed별 결과도 함께 남긴다.

개발 후보 비교 지표는 해당 validation 선박에서 계산한다. validation은 epoch 선택에도 쓰이므로 이 결과는 선택용 탐색이며 독립 최종 성능이 아니다. calibration 지표로 후보를 고르지 않는다.

후보 개발 적격은 기준 R0 대비 3분할 평균 Macro F1 차이 ≥+.03, accuracy 차이 ≥−.01, NLL 차이 ≤+.02, Brier 차이 ≤+.01, 세 분할 중 둘 이상 Macro F1 차이>0, 동일 분모·유한 지표다. 적격 중 평균 Macro F1 개선이 큰 순 → NLL 작은 순 → 선언 순서로 하나를 선택한다(1e−12 동률). 조건부 degree_control은 R0와 동일 개발 조건의 민감도 진단이며 공식 후보 선택에 쓰지 않는다.

적격이 없으면 확인적 primary를 선언하지 않는다. 가장 높은 개발 Macro F1 후보를 탐색 비교 대상으로 기록할 수 있으나 이를 성공 후보로 표시하지 않는다. 추가 개선은 개발 진단과 후속 과제로 남기며 이미 본 최종을 새로운 독립 평가처럼 재사용하지 않는다.

## 동결과 최종 1회

최종 선박의 전처리 통계·가중치·온도·점수는 개발에 사용하지 않는다. 원자료 구조 점검과 라벨층화용 집계·사전 특징 캐시는 가능하되 final 예측/지표는 동결 뒤에만 계산한다. 개발 후보·선택·모델 설정·소스 hash·split manifest hash·시각을 `freeze.json`에 저장한다.

최종 적합은 **미리 고정한 개발 seed3201의 train/validation/calibration**을 그대로 사용하며 가장 좋아 보이는 seed를 고르지 않는다. 기준과 선택 후보(없으면 탐색 대상 하나) 두 모델 절차만 init42·137 앙상블로 잠긴 final에서 한 번 비교한다. 최종 예측을 본 뒤 재학습하거나 모델을 교체하지 않는다.

확인적 성공은 모두 만족해야 한다: final Macro F1 개선≥+.03, accuracy≥−.01, NLL≤+.02, Brier≤+.01, 동일 평가 분모, class층화 paired **선박** bootstrap 2,000회(seed20261028)의 Macro F1 차이 95% percentile 하한>0. 초기화 두 번을 독립 선박 두 척으로 세지 않는다. 추가로 사전에 정한 1월 자료 제거 후 재집계(1월이 없으면 원형 유지)에서 후보 Macro F1 하락이 .03 이내여야 한다. 이 강건성은 특정 월 관측 누락 진단이며 시간외삽·사고 성능이 아니다.

최종 confidence interval의 단위는 선박이며 seed 통계가 아니다. 세 개발 seed의 의존성과 한 번의 실제 선박 holdout이라는 한계를 함께 보고한다. 희소 클래스와 유보 선박도 혼동행렬·support·coverage에서 드러나야 한다. 다수 클래스 상수 예측과 클래스별 지표도 맥락으로 제시한다.

primary 네 지표와 bootstrap은 양 모델이 공유하는 평가가능 선박에서 계산한다. 전체 final 선박은 manifest와 예측에 보존하고 `status=abstained`이면 확률은 null이다. 전체/평가가능/유보 수, coverage, `full_roster_accuracy=correct/all_final`을 별도 보고한다. 모델별로 유보 분모가 달라지면 비교를 중단한다. fit·보정에서도 유보 선박만 제외하며 분할은 바꾸지 않는다. 1월 제거 강건성에서도 coverage 변화를 성능과 별도로 보고한다.

## 산출물과 독립 점검

출력 기본 경로는 `outputs/evaluation_cycle_20261028/model_cycle/`다. `split_manifest.json`, `protocol.json`, `development_results.json`, `freeze.json`, `final_predictions.json`, `results.json` 및 모델 state·학습이력·개별 온도를 보존한다. final_predictions는 `vessel_hash,label,true_index,baseline_probabilities,candidate_probabilities,status,source_rows[{file_ordinal,record_ordinal}],candidate_name`을 포함한다. 원문 선박ID·좌표를 공개하지 않고 선택 원본행 위치로 실패 사례를 추적한다.

root는 저장 예측의 F1/NLL/Brier·혼동행렬, 선박 분할·같은 분모, bootstrap을 별도 코드로 다시 계산한다. Sol medium은 특징·라벨·분할·동결 흐름, 코드 검사와 실제자료 평가의 차이, 개선한 사례·남은 오류·가정 민감도를 점검한다. 구현 동작과 학습자가 그 이유를 설명하는 능력은 별도로 평가한다.
