# S0 합성 항적 시스템 검증 기록

작성일: 2026-10-12. 사용자 요청에 따라 실제자료 수령 전 합성 샘플 시스템을 구현했다. 이 기록은 코드 테스트와 합성자료 계산 결과다. 실제 조업 분류·사고 탐지·장치 실험·학습자 성취를 확인한 기록은 아니다.

## 구현물과 재현

[실습서](fishing_sample_system_guide.md)는 생성 규칙에서 기하 특징, 전처리, 손실과 역전파, 모델 선택, 확률 보정, 거리 점수, 평가 및 후속 개선 절차까지 설명한다. [모듈 계약](sample_system_contract.md)에 입출력을 고정했고 [실행 코드](../tools/run_sample_system.py)가 전체 흐름을 연결한다.

프로젝트 루트에서 다음 명령을 실행한다. Python과 NumPy만 필요하며 실제 검증 환경은 Python 3.13.3, NumPy 2.2.5였다.

```powershell
python -m pip install -r requirements-sample.txt
python tools/run_sample_system.py demo --out outputs/sample_system
python tools/run_sample_system.py predict --data outputs/sample_system/sample_dataset.json --model outputs/sample_system/model.json --out outputs/sample_predictions
python -m unittest discover -s tests -v
```

`demo`는 같은 출력 폴더의 생성물을 갱신한다. 실험을 보존하려면 다른 `--out` 폴더를 사용한다. seed는 기본 42, epoch 상한은 400이다. 현재 demo에서는 생성과 초기화에 같은 seed 인자를 전달한다.

## 합성 실행 결과

84개 가상 선박 그룹에서 1008개 경로를 생성했다. train 432개/36그룹, validation·calibration·test·stress는 각각 144개/12그룹이다. 분할 간 선박 ID 중복은 0이다. 좌표는 지역 XY 미터이며 정답은 직진형·굴곡형·회전형 생성 규칙이다.

| 항목 | Test | Stress |
|---|---:|---:|
| 정확도 | 81.25% | 61.81% |
| Macro F1 | 0.8104 | 0.6180 |
| NLL | 0.4385 | 0.8802 |
| Brier | 0.2564 | 0.4998 |
| 정확도 95% 구간 | 76.39~87.52% | 54.17~68.75% |

95% 구간은 각 평가 분할 안에서 선박 단위 bootstrap 200회로 계산했다. 생성기 편향과 학습 seed 간 불확실성을 포함하지 않는다. Test와 stress는 선박 그룹이 다르고 배율·잡음·누락·단절 조건이 함께 달라지므로, 19.44%p 차이 전체를 교란의 순수 효과나 과적합 증거로 단정하지 않는다.

고정 후보 5개 중 validation NLL로 `mlp16_l2_0`을 선택했다. 선택된 모델의 은닉 폭은 16, L2 계수는 0이다. 다섯 후보 모두 선택 epoch가 400이므로 이번 실행에서는 조기 종료가 발생하지 않았다. 정규화나 조기 종료가 이번 점수를 개선했다고 주장할 근거는 없다. 별도 calibration 분할에서 선택한 온도는 약 0.9441이다. 온도 보정은 확률을 바꾸며 argmax 정확도를 바꾸지 않는다.

클래스별 수축 공분산을 이용한 최소 제곱 Mahalanobis 점수의 validation 95백분위 임계값은 약 17.6126이다. 이 점수는 사고 확률이 아니다. 별도 좌표 교란 검산 60쌍은 입력 오류에 대한 반응을 확인하는 실험이며 사고 탐지율을 측정하지 않는다.

원시 결과는 [report.json](../outputs/sample_system/report.json), 모델은 [model.json](../outputs/sample_system/model.json), 예측은 [predictions.json](../outputs/sample_system/predictions.json), 화면은 [dashboard.html](../outputs/sample_system/dashboard.html)에 있다.

## 테스트와 화면 확인

- 전체 91개 테스트: **89개 통과, 실패 0, 오류 0, 건너뜀 2**. [요약 JSON](../outputs/sample_system/test_summary.json)과 [상세 로그](../outputs/sample_system/tests.log)를 보존했다.
- 두 건너뜀은 Windows에서 심볼릭 링크 생성 권한이 없어서 발생했다. 새 CLI의 보호 경로 해석 분기는 mock으로 확인했고, hardlink에 의한 입력 덮어쓰기 차단은 실제 임시파일로 확인했다. 실제 symlink 생성 검증을 통과했다고 간주하지 않는다.
- 손계산 기하, 부분선 경계 보존, 특징 변환, softmax·tanh 수치 미분, 유효 정답 마스크, 전처리와 저장 상태 검증, 최적 epoch 복원, 후보 선택 및 분할 경계를 검사했다.
- Test/stress 좌표만 변경해도 전처리·분류 가중치·모델 선택·보정 온도·거리 기준과 임계값이 바뀌지 않는 통합 테스트가 통과했다. 정답을 제거해도 예측 확률과 거리 점수가 동일했다.
- CLI로 모델을 다시 읽어 계산한 1008개 예측은 최초 저장 결과와 완전히 일치했다. JSON 클래스 순서·단위·8→16 전처리 차원·3개 출력 클래스가 어긋난 모델은 거절한다.
- 대시보드 JavaScript 구문 검사와 외부 자원 없는 HTML 생성을 확인했다. Chrome에서 test/stress·유형 필터, 빈 검색 결과, 다음 표본, 혼동행렬 전환을 확인했다. 경로를 부분선별로 표시하고 단절을 잇지 않는 화면과 학습 곡선을 시각 점검했다. 콘솔 오류는 관찰되지 않았다.

## 역할 배정과 독립 검토

하위 에이전트 생성 시 다음 모델과 effort를 명시했다. 역할별 완료 응답과 수정 파일을 통합했다. 이는 부모 세션 모델을 변경했다는 뜻이 아니다.

[기계 판독 검증 기록](../outputs/sample_system/verification.json)에 역할별 요청 설정, 실행 근거, 소스 해시와 검증 범위를 함께 남겼다.

| 담당 | 지정 모델 / effort | 실행 결과 |
|---|---|---|
| 종합 설계·근거 | GPT-6 Astra / high | S0 범위·고정 후보·분할 결정, 일반화 해석의 최종 검토 |
| 생성기·특징 모듈 | GPT-6.1 Sol / xhigh | data.py, features.py와 검산 테스트 |
| 분류·전처리·거리 모델 | GPT-6.1 Sol / max | models.py와 수치·복원 테스트 |
| 대시보드·후속 CLI 수정 | GPT-6.1 Sol / xhigh | visualization.py, CLI 출력 보호와 테스트 |
| 독립 검토 | GPT-6.1 Sol / high | 입력 보호·모델 계약·수치 설명 검토와 수정 재확인 |
| 학습·팀 설명서 | GPT-6 Luna / xhigh | 수식·코드·실험·학습 질문 문서화 |
| 통합 | 현재 부모 세션 | 계약, pipeline, 실행 연결, 통합 테스트와 화면 점검 |

독립 검토가 발견한 CLI epoch 상한 불일치, 모델 bundle의 클래스·차원 검사 누락, hardlink 입력 별칭 보호, 문서의 train 클래스별 표본 수를 수정했다. 재검토에서 네 항목의 해결을 확인했다. Astra 검토에 따라 validation 반복 선택의 과적합과 test/stress 비교의 해석 한계를 보완했다.

## 다음 단계로 넘기는 조건

기술적으로 S0 합성 생성→학습→저장→재추론→시각화 흐름이 동작한다. 범용적 실제 어선 모델이나 정확도 개선을 입증한 상태는 아니다. 실제자료 도입에는 좌표계·시간·부분선·라벨 계약, 선박 및 시간 가용성 분할, 별도 평가가 필요하다. 외부 환경 수집, 물리 기반 가상 유닛, 시계열 모델, 3D는 이번 구현에 포함하지 않았다.

후속 개선에서는 개발 그룹 내부 교차검증 또는 미사용 개발 그룹, 사전 후보 예산·seed 목록, 한 조건씩 바꾸는 짝 실험으로 변경 근거를 만든다. 모델을 동결하고 별도 보정 뒤 미사용 평가자료에서 확인한다. 기존 test/stress 결과를 보고 반복 조정하면 새 평가자료가 필요하다. 학습자는 실습서의 손계산과 설명 질문을 수행해야 하며, 그 성취는 아직 평가하지 않았다.
