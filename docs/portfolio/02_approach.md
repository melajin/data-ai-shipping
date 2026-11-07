# 접근: 입력 계약과 비교 조건을 고정한다

## 조업형태 분류

Round63은 선박별 관측을 337개 특징으로 변환한다. 형상 요약 98개, 공간 배치 52개, 상태·시간 187개를 사용하며 공간 계산에는 투영 좌표를 쓴다. Test A 대상 100척에 대해 원본 월별 4,212,389행 중 22,733행을 추출한 기록이 있다. 라벨 열을 입력에 사용하지 않았다. ([특징·입력 감사](../../test_a/deliverables/round63_submission_20261106/data/testA/features.audit.json), [구현](../../test_a/deliverables/round63_submission_20261106/src/round63/features.py))

공개 TabICLv2를 출발점으로 학습한 본체와 FIT 문맥 4,423척을 고정한다. 추론 시 150열·337열 두 특징 묶음에서 각각 4분류와 6개 쌍 비교를 실행하고, 점수와 클래스 가중치를 결합한다. 입력 특징 순서와 제출 대상 ID가 계약과 다르면 중단한다. FIT는 문맥·학습, TUNE은 계수와 체크포인트 선택, REPORT는 개발 평가에 사용된 것으로 기록돼 있다. REPORT의 반복 노출은 별도 한계다. ([모델](../../test_a/deliverables/round63_submission_20261106/src/round63/model.py), [입력 계약](../../test_a/deliverables/round63_submission_20261106/src/round63/pipeline.py), [학습 경로](../../test_a/deliverables/round63_submission_20261106/src/round63/training.py))

원본은 전체 네트워크 교체 대신 본체 일부와 게이트를 학습하고, 본체 반영 비중 0을 대조군으로 뒀다고 기록한다. 다만 이번 조사에서는 Round30~62의 선택 과정을 충분히 복원하지 못했으므로 이 구조가 모든 대안보다 우수해 선택됐다고 주장하지 않는다. ([AI 활용과 검토](../../test_a/deliverables/round63_submission_20261106/docs/AI_활용과_검토.md))

## 이상점수와 평가

Test B의 고정 점수는 위치 희소성 `s_zone`, 이력 대비 형상·상태 변화 `s_change`, 관측 간 시간과 중심점 거리의 참조분포 `s_gap`을 결합한다. `s_change`는 과거 관측이 24행 이상일 때 사용한다. 계산 불가 성분은 정상으로 바꾸지 않고 유효한 성분의 평균을 사용한다. 선박별 기간 전체 최고점과 동점 처리 규칙을 고정하여 검토 후보를 만든다. ([점수 함수](../../test_b/deliverables/testb_system_20261106/src/frozen_baseline.py), [선정 코드](../../test_b/deliverables/testb_system_20261106/src/run_analysis.py))

실험은 잠정 연결 사고와 동일 조건의 기준선 B0를 중심으로 새 규칙을 비교한다. 정렬이나 행 대응이 달라지면 방법의 효과가 아니라 구현 차이를 비교하게 된다. Round002의 U/C 실행본은 새로운 점수 열이 정렬에 연결되지 않은 것으로 확인돼 무효화됐으며 수정 실행은 별도로 보존됐다. 동일 사건에 대한 짝 비교, 다중 비교 보정, 결측과 평가 가능 건수의 구분을 사용한 후속 재채점도 기록돼 있다. ([무효 기록](../../test_b/final/round_002_20261105/execution_001/INVALID_COMPARISON.md), [재채점](../../test_b/final/round_013_metric_rescore/RESCORE.md))

## 결합 경계

Round63 패키지의 통합기는 Test A 예측과 보관된 Test B 후보표를 제출 양식에 합친다. 분류 모델의 출력을 이상점수의 입력으로 사용하지 않는다. 따라서 조업형태별 사고 탐지 개선은 현재 구현의 측정 결과가 아니라 후속 가설이다. ([통합 코드](../../test_a/deliverables/round63_submission_20261106/scripts/export_integrated.py))
