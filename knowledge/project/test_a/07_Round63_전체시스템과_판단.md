# Test A Round63: 문제부터 제출 결과까지

이 문서는 2026-11-06 제출 압축파일에 들어 있던 Round63 패키지와 그 코드·검증 기록을 읽어 정리한 것이다. 기존 [Round29까지의 기록](06_현재상태.md)과 평가 모집단·분할이 다르다. Round30~62의 각 시도와 Round29에서 Round63으로 넘어간 원인 관계는 이번에 확인한 자료만으로 복원하지 못했다. 빈 구간을 추측하지 않는다. 패키지 경로는 이 문서에서 `P`라고 부르며, [P의 안내와 원본 링크](../../../test_a/deliverables/README.md)에서 볼 수 있다.

## 1. 무엇을 풀려 했나

입력은 선박별로 묶인 제공 항적이고 출력은 연안복합·자망·통발·채낚기연승낚시 중 하나와 선택 클래스의 점수다. 이 문제는 사고 탐지 자체가 아니라 선박의 조업형태 분류다. Test B의 사고 후보 분석에 유형 정보가 도움이 될지는 별도 가설이다. ([모델 설명](../../../test_a/deliverables/round63_submission_20261106/docs/과제1_모델설명.md), [Test B 분석](../test_b/03_final_round001_012_재구성.md))

이전 Round26 검토에서는 OUTER로 여러 후보를 선택해 성능을 보고한 절차가 문제였다. Round63 원본은 FIT에서 학습·문맥 구성, TUNE에서 계수·체크포인트 선택, REPORT에서 개발 평가를 했다고 설명한다. 이 문서들은 서로 다른 실험·분할을 말하며, Round63 설계가 Round26 검토 때문에 만들어졌다는 인과는 확인하지 못했다. ([Round26 검토](../../../test_a/11_04_final/rounds/round_026/review_20261105/REVIEW_ROUND026_0.60돌파_검증_20261105.md), [Round63 모델 설명](../../../test_a/deliverables/round63_submission_20261106/docs/과제1_모델설명.md))

## 2. 한 선박의 데이터가 결과가 되기까지

```text
제공 CSV: 관측일·시간키·선박 ID·MultiLineString
  → 제출 대상 ID 선별, 라벨 열 제외
  → 부분선별 형상 계산 + 관측 시간·공간·상태 요약
  → 선박별 337개 특징과 순서 검사
  → 고정 FIT 문맥 + Round63 가중치
  → compact 150열 및 state 337열 각각 4분류 1개 + 쌍 비교 6개
  → 14개 과제의 점수 결합·클래스 가중치·softmax
  → 대상 ID 순서의 유형·선택 클래스 점수 CSV
  → 기존 Test B 후보표와 같은 제출 엑셀의 별도 영역에 병합
```

원본 설명에 따르면 월별 입력 4,212,389행을 순차 조회해 대상 100척의 22,733행을 추출했다. 필수 열은 `part_dt`, `rfid_id`, `rfid_time`, `geom`이고 대상 이외의 선박 이력을 추가하지 않는다. 원래 나뉜 부분선을 잇지 않으며 좌표마다 시각을 부여하거나 실제 속도를 새로 계산하지 않는다. ([원본 README](../../../test_a/deliverables/round63_submission_20261106/README.md), [특징 생성 진입점](../../../test_a/deliverables/round63_submission_20261106/scripts/build_features.py))

337개 특징은 원본 분류에 따라 형상 요약 98개, 공간 배치 52개, 상태·시간 187개다. 길이·직진성 같은 형상, 방문 격자와 범위, 실제 관측 시각과 인접 구간 상태를 숫자로 요약한다. 공간 특징 설명에는 EPSG:5179 투영이 명시돼 있다. 관측 구간의 시간키가 있다는 사실과 각 좌표의 시각을 안다는 것은 다르다. ([모델 설명](../../../test_a/deliverables/round63_submission_20261106/docs/과제1_모델설명.md), [특징 스키마](../../../test_a/deliverables/round63_submission_20261106/model/feature_schema.json))

추론 코드는 특징 이름과 순서가 다르거나 열이 337개가 아니면 중단한다. 대상 ID 집합을 제출 스키마와 비교하고 순서를 맞춘 뒤, 각 과제의 FIT 문맥을 사용한다. 두 특징 묶음과 4분류·쌍별 점수는 각각 0.5씩 결합하고 클래스 가중치 `(1, 1, 1, 0.8)`을 적용한다. 결과는 softmax로 정규화한 선택 클래스의 값이지, 별도 확률 보정이 검증된 값이라고 확인된 것은 아니다. ([추론 코드](../../../test_a/deliverables/round63_submission_20261106/src/round63/model.py), [입출력 코드](../../../test_a/deliverables/round63_submission_20261106/src/round63/pipeline.py), [정책](../../../test_a/deliverables/round63_submission_20261106/model/policy.json))

## 3. 모델은 어떻게 만들어졌나

원본은 공개 TabICLv2를 출발점으로 ICL 중간 4블록을 학습하고 뒤 4블록 FFN에 게이트를 추가했다고 설명한다. 총 4회 업데이트 후 epoch 1·update 2 가중치를 선택했다. 학습은 20개 과제를 사용했으나, 최종 정책의 관계 분기 비중이 0이므로 배포 추론은 관계 과제를 제외한 14개만 실행한다. 학습에 쓰였다는 사실을 최종 추론의 직접 기여로 해석하지 않는다. ([모델 설명](../../../test_a/deliverables/round63_submission_20261106/docs/과제1_모델설명.md), [선택 기록](../../../test_a/deliverables/round63_submission_20261106/model/provenance.json), [정책](../../../test_a/deliverables/round63_submission_20261106/model/policy.json))

학습 7,372척은 선박 단위 FIT 4,423척, TUNE 1,474척, REPORT 1,475척으로 나뉜다. 원본에 따르면 FIT는 문맥과 특징 기저, TUNE은 선택, REPORT는 개발 평가에 사용됐다. REPORT 자체도 여러 회차의 개발 검토에 쓰였으므로 새로 보지 않은 독립 시험 성적으로 취급할 수 없다. ([모델 설명](../../../test_a/deliverables/round63_submission_20261106/docs/과제1_모델설명.md), [원본 README](../../../test_a/deliverables/round63_submission_20261106/README.md))

## 4. 확인된 결과와 그 범위

| 확인 대상 | 원본 기록 | 의미와 한계 |
| --- | --- | --- |
| 개발 REPORT | 1,475척 중 903척 정답, micro-F1 0.612203, macro-F1 0.563424 | 반복 개발 평가 조건의 점수; 공식 성적 아님 |
| 클래스별 성능 | 통발 F1 0.264286, 재현율 0.177033 | 전체 점수와 소수 유형의 성능을 따로 확인해야 함 |
| 특징 생성 회귀 | 네 클래스 각 1척, 337개씩 1,348개 값 차이 0 | 4척의 선택된 비교이며 모든 입력에 대한 증명은 아님 |
| 추론 회귀 | TUNE·REPORT 2,949척의 최종 예측 변경 0, 로그점수 최대 차 약 6.89e-7 | 기존 Round63 결과와 코드 일치성 기록; 독립 일반화 성능 아님 |
| 노트북 | 각 7개·6개 코드 셀 실행 기록, 선택적 재학습 미실행 | 기록된 환경에서의 실행; 이번 세션에서 재실행하지 않음 |
| 제출 양식 | 과제별 100척과 통합 내보내기 검사 통과 기록 | 양식 검사이지 주최 측 수신·채점의 증거는 아님 |

([모델 설명](../../../test_a/deliverables/round63_submission_20261106/docs/과제1_모델설명.md), [특징 회귀](../../../test_a/deliverables/round63_submission_20261106/validation/feature_regression.json), [추론 회귀](../../../test_a/deliverables/round63_submission_20261106/validation/report_regression.json), [노트북](../../../test_a/deliverables/round63_submission_20261106/validation/notebook_execution.json), [제출 검사](../../../test_a/deliverables/round63_submission_20261106/validation/submission_checks.json))

## 5. Test B와 어떻게 연결되나

`export_integrated.py`는 Test A 예측 CSV와 이미 저장된 Test B 후보표를 같은 엑셀에 병합한다. 읽은 연결 코드에서 Test A의 예측 조업형태를 Test B 점수 계산에 입력하지는 않는다. Test B는 위치 희소성·이력 대비 변화·관측 공백의 점수를 계산하고 전체 제공 기간 최고점을 고른다. 따라서 통합 엑셀이 존재해도 조업형태별 사고 기준선이 실제로 연결되었다거나 실시간 경보가 검증되었다는 뜻은 아니다. ([통합 코드](../../../test_a/deliverables/round63_submission_20261106/scripts/export_integrated.py), [Test B README](../../../test_b/deliverables/testb_system_20261106/README.md))

Test B의 어업별 기준 G는 잠정 연결된 개발 100사건에서 1건 적중해 B0의 3건보다 낮았다. 이 사례는 조업형태가 무용하다는 증명이 아니라, 당시 정의한 규칙과 자료에서 개선이 확인되지 않았다는 결과다. 새로운 Round63 예측을 사용한 연결의 효과는 별도 평가가 필요하다. ([Test B 회고](../test_b/03_final_round001_012_재구성.md))

## 6. 아직 풀리지 않은 질문

- Round30~62에서 어떤 가설이 실패하고 왜 Round63으로 바뀌었는지: 원본 라운드별 기록과 선후관계 미확인.
- 337개 특징 각각이 어떤 조업 현상과 연결되는지, 유형별 오분류가 어떤 조건에서 생기는지: 대표 사례와 실제 원자료를 묶은 별도 검토 필요.
- Round63의 공식 대회 점수와 독립 일반화 성능: 확인한 패키지에 결과 없음.
- Test A 예측의 오류가 Test B에서 어떤 영향을 주는지: 두 과제의 같은 선박 연결 조건과 정답을 갖춘 평가 필요.
- 개인 학습 점검: 왜 좌표별 시각이 없으면 실제 속도를 얻을 수 없는가? FIT·TUNE·REPORT의 역할은 무엇인가? 전체 F1이 올라가도 통발 재현율을 따로 봐야 하는 이유는 무엇인가?

관련 재사용 원리와 다른 분야에 적용하기 위한 조건은 [도메인·문제 해결 지식](../../personal/2026-11-07%20Round63%20도메인과%20문제해결%20지식.md)에 연결했다.
