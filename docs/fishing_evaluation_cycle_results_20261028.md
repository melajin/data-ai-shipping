# 실제자료 항적 분류 주기 결과 — 2026-10-28

갱신일: 2026-10-29  
용도: 본인 학습자용 결과·검증 기록  
상태: Train 입력 감사·안전한 특징 캐시·고정 절차에 따른 내부 모델 평가 완료. Test 및 실무 적용 적합성은 미확인이다.

## 1. 이번 단계의 범위

실제 CSV의 구조와 입력 적합성을 스트리밍 방식으로 확인하고, 사전 고정된 규칙으로 제한된 특징 표본을 만들었다. 저장된 합성 shape9 모델의 세 생성 유형을 실제 조업 라벨에 대입하지 않고, 실제 라벨로 별도 재학습·내부 평가를 마쳤다. 이 보고서는 해당 내부 평가와 그 한계를 기록한다.

이번 자료 흐름은 `CSV 행(선박·일자·시간대·WKT·Train 라벨) → 유효성 점검·비공개 ID hash → 선박/월별 제한 표본 → 경위도 부분선별 shape9 → 내부 선박 단위 학습/평가`이다. 좌표별 시각은 제공되지 않으므로 실제 속력·가속도·체류시간은 계산하지 않는다.

## 2. 자료와 전체 스트리밍 검사

`F:/문제 데이터_수정_1027`에 있는 CSV 12개의 원본 파일 크기 합은 **11,834,630,398 bytes**이며, 이 파일들에 스트리밍 검사를 수행했다. Train 6개 파일은 EOF까지 읽고 byte hash를 완성한 것이 확인됐다. Test 6월 파일은 CSV 파싱 오류로 조기 종료되어 파일 전체 행 검사가 미완료다. v1 scan의 읽은 byte 수/hash EOF 기록에는 알려진 집계 오류가 있어 실제로 읽고 hash한 Test byte 범위와 12개 전체 byte 완독 여부는 확인할 수 없다. 정정된 공개 보고서에는 원문 ID와 개별 좌표를 표시하지 않고, 모델 입력은 파생 특징이다. 원본 전체 WKT를 복사하지 않았지만, 원본 v1 SQLite는 수정하지 않고 감사 증거로 보존했으며 그 안에는 구조 오류 행의 오염 라벨 문자열 일부가 남아 있다.

| 구분 | 파서 처리 행 수 | 보유 원본 파일 크기 합 | 해석 |
| --- | ---: | ---: | --- |
| Train 1~6월 | 3,887,069 | 5,863,777,667 bytes | 여섯 월 파일 모두 CSV 파싱 종료, byte hash 존재, 검사 중 원본 변경 없음 |
| Test 계열 1~6월 | parser가 읽은 3,365,197 | 5,970,852,731 bytes | 다섯 파일은 파싱 종료. 여섯 번째 파일은 CSV 파싱 오류 뒤 61,586행까지 읽혀 Test 전체 검사는 미완료 |
| 전체 파서 실행 | 7,252,266 | — | 파일별 내부 경과 합 약 29분 6초. 크기 합은 원본 파일 크기이지 실제 읽은 byte 수가 아니며, 마지막 Test 파일의 물리 행 총수로 해석하지 않는다. |

공식 안내에서 확인한 내용은 X=경도, Y=위도, `rfid_time`은 0~23 시간대, 한 행은 선박·일자·시간대의 항적이며 Train `fishing_code`는 실제 조업형태 정답이라는 점이다. 정확 EPSG/측지 datum과 점별 관측시각은 미확인이다. 이 확인 근거는 [자료 설명 및 평가 범위 조사](real_support_evidence_20261028.md)에 기록했다.

### Train 라벨 집계와 입력 제외

공식 네 조업 범주의 Train 행 집계는 다음과 같다. 본문 라벨은 선박 단위 평가에서 의미가 있으므로 공식 네 범주만 표시한다.

| Train 라벨 | 유효 라벨 행 |
| --- | ---: |
| 연안복합 | 1,682,455 |
| 자망 | 1,422,675 |
| 통발 | 601,059 |
| 채낚기연승낚시 | 180,878 |

Train 6월의 file ordinal 5 / data record ordinal 127,862 한 행은 날짜·시간대가 유효하지 않고 geometry prefix도 맞지 않으며, 라벨 필드에는 네 공식 범주가 아닌 값이 들어갔다. 이 행은 라벨·선박 집계와 특징 표본에서 격리했다. 원문 라벨과 좌표는 보고서에 복사하지 않았다. 같은 파일에 빈 라벨 행 1개도 확인됐지만 특징 입력에는 포함되지 않았고, 위치는 캐시에 없어 추정하지 않는다. 빈 라벨 행은 unknown-label quarantine과 다른 집계다.

Train의 열 수 불일치는 0건이다. 6월 파일에는 빈 헤더 열 아래 비공백 셀이 68개 있어 그 의미를 확인할 수 없다. Train 6월에서 잘못된 날짜·시간 형식은 각각 1건이다. 알려진 WKT 표본에서는 다중 부분선을 서로 연결하지 않는다.

### 평가 입력 게이트

- Train 여섯 파일: 파일별 hash가 있고 검사 중 변경 없음. 내부 개발 학습·검증 입력으로 사용할 수 있다.
- Test 여섯 번째 파일: CSV parse error 때문에 전수 입력 적합성 게이트를 통과하지 못했다. 공식 Test A/B 역할도 파일 목록만으로 확정하지 않았다.
- 사고현황 XLSX는 CSV의 선박 ID와 결합할 식별자가 없어 실제 사고 정답으로 쓰지 않는다.

root의 별도 선박 ID 교차 집계에서는 parsed 무라벨 선박 7,621척 중 6,750척이 Train ID와 겹쳤다. 제출샘플의 Test A ID 100개 중 91개, Test B ID 100개 중 95개도 Train과 겹쳤다. 따라서 파일명이나 제출 템플릿만으로 공식 Test A 신규 선박 분할이라고 확정하지 않으며, 이번 성능은 별도 내부 선박 holdout으로 해석한다. 세부 교차 집계는 `outputs/submission_id_coverage_audit_20261029.json`을 참조한다.

따라서 아래 모델 평가가 완료되어도 **Train에서 분리한 신규 선박의 내부 평가**다. 제출 Test 성능이나 사고 탐지 성능으로 부르지 않는다.

## 3. 월별·선박별 제한 특징 캐시

각 labeled Train 월 파일에서 선박별로 `SHA256(salted_vessel_hash || file_ordinal || record_ordinal)` 순위가 가장 작은 행을 최대 4개 선택했다. 월별 최대 4개, 6개월이면 선박당 최대 24개다. 선택 순위는 라벨과 geometry 내용에 의존하지 않는다. 잘못된 geometry 표본도 유효성 상태와 함께 남기며, 학습·평가 시에는 invalid 행을 유효한 특징으로 대치하지 않는다.

geometry는 선택 표본에 대해서만 파싱·계산했다. 전체 Train의 약 3.89M행 각각에 대해 특징을 만들었다는 뜻이 아니다. 초기 캐시에서 월이 모두 1월로 표시되는 상위 폴더 매치 버그를 발견해 CSV basename의 월과 각 표본 `part_dt` 월을 대조해 수정했다. 수정 후 선택 표본 월 불일치는 0건이다.

교정된 입력은 [vessel_features_v2.json](../outputs/evaluation_cycle_20261028/vessel_features_v2.json), 변경 근거와 SHA-256은 [cache_repair_audit.json](../outputs/evaluation_cycle_20261028/cache_repair_audit.json)에 있다. 원본 CSV와 v1 SQLite는 수정하지 않았고 11GB를 다시 읽지 않았다. 안전한 집계 보고서는 [full_scan.json](../outputs/evaluation_cycle_20261028/full_scan.json)에 있다. 위치가 캐시에 없는 빈 라벨 행 집계는 hash-frozen 산출물과 분리한 [cache_quality_supplement.json](../outputs/evaluation_cycle_20261028/cache_quality_supplement.json)에 기록했다.

| 조업형태 | 일관 라벨 선박 수 | 선택 표본 행 | 유효 shape9 | 유보 행 |
| --- | ---: | ---: | ---: | ---: |
| 연안복합 | 3,650 | 62,568 | 55,456 | 7,112 |
| 자망 | 2,520 | 44,354 | 39,838 | 4,516 |
| 통발 | 1,044 | 19,579 | 17,584 | 1,995 |
| 채낚기연승낚시 | 158 | 2,641 | 2,422 | 219 |
| **합계** | **7,372** | **129,142** | **115,300** | **13,842** |

90척은 선택된 모든 행이 invalid여서 모델 적용에서 유보한다. 소수 클래스는 158척이므로 클래스별 불확실성과 최종 holdout 크기를 함께 해석해야 한다.

### 형상 특징의 단위와 가정

실제 extractor는 아홉 무시간 특징을 계산한다. 각 레코드 안에서 관측점 평균을 원점으로 둔 국소 접평면 근사를 사용한다:

```text
x = (lon - lon0) * pi/180 * cos(lat0*pi/180)
y = (lat - lat0) * pi/180
```

지구반경을 곱하지 않으므로 좌표는 미터가 아니며 실제 거리·속도 추정값이 아니다. `degree_control`도 같은 행의 비교용 민감도 분석 입력이다. WKT subset 및 공간 폭/위도 제한 때문에 유보된 표본의 이유를 별도로 보존한다. 정확 EPSG/datum은 확인되지 않았고 WGS84라고 주장하지 않는다.

## 4. 실제 모델 반복 결과

이 평가는 Train 선박 hash로 만든 **내부 신규 선박 holdout**이다. 개발의 세 seed는 동일 원자료를 공유하므로 서로 독립된 세 시험이 아니다. 개발 분할마다 train/validation/calibration은 4,127/884/888척이었고, final은 별도 선박 1,473척을 잠갔다. 유효 geometry 행이 전혀 없는 선박은 예측 유보로 유지했다.

사전 후보 네 개를 세 개발 분할에서 비교했다. R0 대비 Macro F1 평균 개선이 +0.03 이상이고, accuracy/NLL/Brier 제한과 3개 분할 중 적어도 2개 개선 기준을 모두 통과한 후보는 R2 ExtraTrees 하나뿐이었다. 따라서 final에 확인적으로 올린 후보는 이 모델 하나다.

| 개발 후보 | 평균 Macro F1 | R0 대비 | 선택 |
| --- | ---: | ---: | --- |
| R0 mean9 MLP16 | 0.166075 | 기준 | 비교 기준 |
| R1 distribution36 MLP16 | 0.174048 | +0.007974 | 적격 아님 |
| R2 distribution36 linear | 0.193729 | +0.027654 | +0.03 기준 미달 |
| R2 distribution36 ExtraTrees(256, leaf=2) | 0.335753 | +0.169678 | **유일 적격 후보** |

잠금 final에서 공통 scorable 선박 1,453척에 대해 계산한 지표다. baseline은 R0 mean9 MLP다. CI는 seed가 아니라 선박을 단위로 한 층화 paired bootstrap 2,000회, seed 20261028의 Macro F1 차이 95% 구간이다.

| 지표 | R0 baseline | 선택 후보 | 차이 |
| --- | ---: | ---: | ---: |
| Macro F1 | 0.166900 | 0.299575 | **+0.132676** (95% CI 0.085371~0.175674) |
| Accuracy | 0.496903 | 0.498968 | +0.002065 |
| NLL | 1.056009 | 1.040390 | −0.015619 |
| Brier | 0.613261 | 0.611048 | −0.002213 |

최종 roster 1,473척 중 1,453척은 점수화됐고 20척은 유효 geometry 행이 없어 유보됐다. 전체 roster 정확도는 baseline 0.490156, 후보 0.492193이다. 후보는 전체 예측 중 연안복합 1,143척, 자망 293척, 채낚기연승낚시 11척, 통발 6척으로 예측했다. 비교 기준은 연안복합 1,451척, 자망 2척으로 거의 한 범주만 예측했다. 공통 scorable 분모에서는 다수 클래스 상수 예측 정확도 0.496903 대비 후보 0.498968로 개선 폭이 작다. 전체 1,473척을 분모로 보면 상수 예측 0.495587이 후보 0.492193보다 높으며, 이는 유보 20척을 상수 예측은 맞히고 후보 평가는 유보를 오답으로 세는 전체-roster 분모 차이도 반영한다. 따라서 macro-F1 개선은 클래스 편중을 완화했지만, 실제 분류 수준은 여전히 낮다.

평가가능 정답 지원과 후보 정분류 수는 다음과 같다. 후보는 통발 정답 204척 중 **0척을 맞혔고**, 통발로 예측한 6척도 모두 오분류했다. 채낚기연승낚시는 전체 final 31척 가운데 29척만 점수화됐고, 점수화된 정답 29척 중 5척을 맞혔다. 이는 희소 클래스에 대한 신뢰 한계가 큰 표본이다.

| 정답 | 평가가능 지원 | 채낚기 예측 | 통발 예측 | 자망 예측 | 연안복합 예측 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 채낚기연승낚시 | 29 | 5 | 2 | 8 | 14 |
| 통발 | 204 | 4 | **0** | 43 | 157 |
| 자망 | 498 | 1 | 3 | 121 | 373 |
| 연안복합 | 722 | 1 | 1 | 121 | 599 |

대표 행 위치는 내용 값을 공개하지 않고 원본 file ordinal/data record ordinal로만 기록한다. 예를 들어 통발 정답을 연안복합으로 예측한 사례는 `(file 0, record 42,454)`이며, 채낚기연승낚시 정답을 연안복합으로 예측한 사례는 `(file 3, record 320,316)`이다. R0의 상수에 가까운 연안복합 예측에서 벗어나 자망을 맞힌 사례는 `(file 1, record 248,850)` 등으로 추적할 수 있다. 위치는 평가 예측 파일의 익명화된 추적용 참조다.

최종 Macro F1 개선은 사전 수치 기준을 통과했고 paired CI 하한도 0보다 크다. 그러나 성공 기준 통과가 높은 절대 성능이나 운용 준비를 의미하지 않는다. 통발 recall은 0/204이고 모델 예측에서도 통발이 6건뿐이어서 **실무 준비 상태가 아니다**. 학습 Train support 자체가 클래스별로 86/580/1,395/2,016척으로 불균형하며, 대부분을 차지하는 연안복합 쪽으로 예측이 기운다.

1월 자료를 제외한 사전 강건성 진단에서는 공통 roster 중 1,432척만 점수화되고 41척이 유보됐다. 선택 후보 Macro F1은 같은 scorable 선박에서 0.299690에서 0.280211로 **0.019479 하락**해 사전 허용폭 0.03 안에 있었다. 이는 특정 월 자료 누락 민감도만 검사하며 미래 시점 일반화 증거는 아니다.

모델 재적재 검증은 재학습 없이 저장 가중치와 입력 결과를 다시 계산했고, 저장 결과와 최대 절대 차이는 0이었다(허용오차 1e−12). root 독립 감사는 final prediction/split/result hash를 고정한 뒤 지표·혼동행렬·분모·bootstrap 구간을 재계산했으며 최대 차이 0으로 일치했다. 캐시 독립 감사도 v2 해시, 월 일치, unique source row, 특징 불변을 통과했다. 이 감사는 upstream feature leakage 부재나 전체 WKT 완전성을 증명하지 않는다.

## 5. 학습자 설명·검증 질문

1. 왜 같은 선박의 여러 월 행을 무작위 행 단위로 학습·평가에 나누면 안 되는가?
2. 선택 표본에서 invalid 행을 유보할 때 전체 행 수와 유효 특징 분모를 어떻게 구분했는가?
3. 국소 접평면 근사에서 `cos(lat0)`와 degree control의 차이는 무엇이며 정확 EPSG 미확정이 어떤 주장을 제한하는가?
4. 공식 Test 파일의 CSV parse error와 Train 내부 성능 평가 결과를 어떻게 구분해 보고할 것인가?
5. 통발 0/204 정분류와 채낚기연승낚시의 작은 지원 수를 고려할 때, Macro F1 개선만으로 배포 결정을 내릴 수 없는 이유는 무엇인가?
6. 상수에 가까운 baseline에 비해 후보 Macro F1은 크게 개선됐지만 accuracy는 거의 그대로인 이유를 혼동행렬과 클래스 분포로 설명할 수 있는가?

## 6. 생성·검증 구분

| 작업 | 상태 | 증거 |
| --- | --- | --- |
| scanner 구조/프라이버시 검사 코드 | 완료 | `tests/test_evaluation_cycle_20261028.py` 5개 통과 |
| 전체 CSV byte/hash/메타데이터 검사 | Train 완료, Test 일부 미완료 | `full_scan.json` 및 v1 cache를 읽기 전용으로 교정한 repair audit |
| 실제자료의 선택 geometry 특징 계산 | 완료, 제한 표본만 | `vessel_features_v2.json` |
| 실제자료 모델 학습·내부평가 | 완료, 연구용 내부 holdout | `model_cycle/results.json`, `final_predictions.json`, root 독립 감사 |
| Test A/B 제출 성능·사고 탐지 | 미검증 | Test parse/역할 및 사고 결합 규칙 미확정 |
| 실제 장치·센서 실험 | 수행하지 않음 | 장치 연결 없음 |

이번 성능은 공식 Test A 또는 사고 탐지 성능이 아니다. 제출 ID 교차 집계에서 무라벨 선박과 Test A/B 템플릿 ID가 Train ID와 상당히 겹쳤으므로, 공식 Test A의 역할은 별도 확인이 필요하다. Test 계열 6월 파일은 parse error로 미완료이며, 사고현황 XLSX를 CSV 선박과 연결할 식별자도 확인되지 않았다. exact EPSG/datum 미확정, 선택 geometry 표본만 파싱, 90척 all-invalid 유보, 클래스 불균형 및 소수 클래스 지원 제한도 결과 해석 경계다.

### 저장된 모델의 추론 재사용

선택 후보의 저장 상태는 [final_model_audit.json](../outputs/evaluation_cycle_20261028/model_cycle/final_model_audit.json)에 있다. 이 약 243 MB 파일에는 두 초기화의 `model_state`, 전처리기, 온도, ExtraTrees 직렬화 문자열(`estimator_pickle_hex`)이 들어 있다. 클래스 확률의 순서는 [protocol.json](../outputs/evaluation_cycle_20261028/model_cycle/protocol.json)의 `class_names` 순서다. 모델 재적재 검증에서 두 초기화의 저장 예측과 재생성 예측은 최대 절대 차이 0이었다.

아래 예시는 프로젝트 루트에서 PowerShell로 실행한다. 입력은 고정 계약으로 만든 [vessel_features_v2.json](../outputs/evaluation_cycle_20261028/vessel_features_v2.json)이며, 같은 계약의 선박들을 일괄 추론하고 첫 3개 선박의 클래스 확률만 표시한다. `fit`이나 재학습을 호출하지 않으며 선박 ID, hash, 좌표, 원본 행 위치를 출력하지 않는다. 새 입력도 같은 선박/월별 표본 선택과 geometry 특징 계약을 지켜야 한다.

```powershell
@'
import json
from pathlib import Path
import numpy as np
from fishing_demo.real_model_cycle_20261028 import (
    _aggregate_rows, _predict_state, _validate_vessel_rows,
)

root = Path.cwd()
out = root / "outputs/evaluation_cycle_20261028/model_cycle"
features = json.loads((root / "outputs/evaluation_cycle_20261028/vessel_features_v2.json").read_text(encoding="utf-8"))
protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
audit = json.loads((out / "final_model_audit.json").read_text(encoding="utf-8"))
candidate = "distribution36_extratrees256_leaf2"
class_names = protocol["class_names"]
states = audit[candidate]
vectors = []

for vessel in features["vessels"]:
    rows = _validate_vessel_rows(vessel)
    vector, selected = _aggregate_rows(rows, "distribution36")
    if not selected or not np.isfinite(vector).any():
        continue
    vectors.append(vector)

X = np.asarray(vectors, dtype=np.float64)
if X.ndim != 2 or not len(X):
    raise ValueError("no scorable vessels")
init_probabilities = []
for entry in states:
    state = entry["model_state"].copy()
    if entry.get("estimator_pickle_hex"):
        state["estimator_pickle"] = bytes.fromhex(entry["estimator_pickle_hex"])
    _, probabilities = _predict_state(candidate, state, X)
    init_probabilities.append(probabilities)
mean_probabilities = np.mean(init_probabilities, axis=0)

print(json.dumps({
    "scorable_vessels": len(X),
    "class_order": class_names,
    "first_three_probability_rows": mean_probabilities[:3].tolist(),
}, ensure_ascii=False))
'@ | python -
```
