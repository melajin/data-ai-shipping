# Round026 → 027 팀원 관찰 반영 재검사 실험

2026-11-05. 기존 round_026 및 round_027_fallback_ovr는 읽기 전용으로 보존한다.

## 범위와 가설

사용자: 팀원 결과는 참고만 한다. 원래 이름표의 재현을 요구하지 않는다.
외부 관찰(단독 정확도 약64%, 무표195 중0번76, {0,1}302 중1번156,
{0,2}43 중2번21)은 모집단/선택 절차 미확인인 가설 근거이며 본 실험의 측정값이 아니다.
39.0%, 51.7%, 48.8%는 확정 판정이나 다른 클래스를 배제할 근거가 아니다.

기술 목표: 저장 검출 확률만 사용하는 작은 재검사기로 단독/무표/복수 후보 오류를 줄일 수 있는지 판단한다.
학습 목표: 후보집합과 정답을 구별하고, 단독 후보의 확신과 실제 정확도가 다른 이유 및 강제 배제 손실을 설명한다.

## 입력과 이름표

- round027 Worker A의 raw 4개 이진 점수 `[1-P(specialist), P(1 OVR), P(2 OVR), P(3 OVR)]`.
- 각 점수 >=0.5이면 이름표를 붙인다. 독립 이진 점수이며 합이 1인 확률이 아니다.
- 이 이름표 정의는 팀원 정의와 동일하다고 주장하지 않는다.
- 비교 base는 Round026의 사전 고정 Trio: .45 LGB5 sqrt_macro + .45 TabICL42 + .10 CatBoost,
  alpha=[1.033,1,.983,1.5]. 혼합비/승수를 새 OUTER로 조정하지 않는다.
- 과거 선택 이력이 있는 base와 kNN/OVR를 재사용하므로 전체 실험은 반복 노출 개발 진단이다.
- holdout/Test/원자료/대용량 특징을 읽지 않는다.

## 재검사기와 선택

각 원래 fold에서 INNER_ES는 새 학습/선택에 사용하지 않고 INNER_SELECT만 사용한다.
SELECT 내부 stratified 3-fold로 재검사 예측을 교차적합한다. 다른 원래 fold 자료로 학습하지 않는다.
각 fold SELECT 선박 ID 유일성 및 FIT/INNER/OUTER 무교집합을 검사한다. 같은 선박의
복수행이 있으면 중단한다. scaler도 각 OOF 학습 부분에서만 fit하며 최종에는 해당 SELECT 전체에서 재적합한다.
고정 regularized logistic regression C=.3, StandardScaler, max_iter=400, seed=2705.
입력: base 확률4, 이진점수4, M123 조건부 확률3, 이름표4, 후보수1.
전체 4클래스 재검사기와 {0,1}, {0,2} 이진 재검사기를 각각 학습한다.
이진기는 SELECT 중 해당 실제 두 클래스만 학습한다. 질의는 사전 정의 이름표 그룹으로 라우팅한다.
원칙적으로 정답 이름표가 누락될 수 있으므로 soft 통합안은 2/3을 강제 제외하지 않는다.

사전 고정 후보:

1. baseline
2. singleton_trust: 단독이면 이름표 그대로
3. singleton_recheck: 단독이면 4클래스 재검사
4. empty_zero: 무표면0
5. empty_recheck: 무표면4클래스 재검사
6. pair01_hard_base: 0,1 둘 다 포함하면 base의0/1만 비교
7. pair01_recheck: 0,1 둘 다 포함하면0/1 이진 재검사(2/3 강제 제외)
8. pair02_recheck: 정확히{0,2}이면0/2 이진 재검사
9. combined_hard: 단독 재검사+무표0+위 두 이진 재검사
10. combined_soft: 모든 네 대상 그룹에서4클래스 재검사; 재검사기 자체의 분포 q에서
    q(재검사기 argmax)-q(base argmax)>=.15일 때만 변경. 서로 다른 모델의 확률을 빼지 않는다. 2/3 제외 없음.

각 fold의 SELECT OOF에서 baseline 대비 TP0,TP3 모두 감소하지 않는 후보 중
micro 최대, 동점 macro 최대, 최종 동점 위 후보순으로 선택한다. baseline은 항상 비교 대안이다.
SELECT 전체에 재적합하고 해당 fold OUTER에 적용한다. 모든 fold 선택 및 예측을 파일로 동결한
뒤 OUTER 정답을 평가한다. 평가 후 선택을 바꾸지 않는다.
OOF 선택 자체의 낙관성 및 기존 모델의 INNER/특징 노출 이력은 남는다.
특히 LGB5 등 일부 원모델은 예전 INNER 전체를 조기종료에 썼으므로 SELECT가 원모델의
완전히 미노출된 자료라고 주장하지 않는다. Worker A 소스는 FIT만 학습하고 kNN gallery도 FIT만 사용한다.
명부 기준 FIT/INNER/OUTER 무교집합은 provenance_roster_static.json에 기록했다.
Worker A 저장 확률에는 ID가 없으므로 실행 시 feature NPZ의 ID/role 메타데이터로 소스의
정렬을 검증하고 canonical label/크기도 대조한다. 과거 실행의 모델 snapshot 증명은 별도 한계다.

## 평가/인수조건

전체 micro/macro, 클래스별 precision/recall/F1/TP/FP, 그룹별 이름표 정답 포함률,
단독 정답률, 무표 class0 비율, {0,1}에 실제2/3인 강제배제 수,
{0,2}에 실제1/3인 강제배제 수, 변경 gain/loss/net, fold별 변화,
seed42 및5seed 각각의 class0/3 gain/loss/net, 관측일 구간(기존 파일에 있으면),
paired McNemar/척수 bootstrap CI를 남긴다. 각 후보 평가표는 사전 고정된 보조 진단이다.

단일seed 절차 판정: TP0>=2389 AND TP3>=90. 역사5seed 참조 판정: TP0>=2381 AND TP3>=92.
두 판정은 별도 표시하며 본 재검사기는 새 후보5seed 확인이 아니므로 최종 채택을 주장하지 않는다.
목표 micro .7 유지. 팀원 수치나 이 진단만으로 목표 지표를 변경하지 않는다.

## 자원/상한/실패

계산 동시1, 모든 수치 라이브러리 thread1, Windows BelowNormal.
저장 확률/CSV 수MiB와 수백행×16열 logistic fitting: 예상 peak <=.35GiB,
소유 프로세스 RSS 강제상한 .75GiB; 진입가용>=1.5GiB, 단계별>=1.0GiB, 비상<.5GiB.
부족하면 문서/코드/정적검토를 먼저 진행하고 실행 직전 다시 확인한다. polling 없음.
최대1개 고정 실행, 실행20분/전체45분. 실패 수정은 원인 기록 후1회까지.
메타 모델 상한 3 원래fold × (3 OOF+1 최종) ×3종 =36개 작은 회귀모델.
단일 클래스/부족 표본이면 해당 이진 재검사만 base 판정으로 돌아가고 원인을 기록한다.
격자가 없다는 이유로 임의 상수로 채택하지 않는다. 무응답/과거 원문을 승인으로 취급하지 않는다.

결과물: 코드, 입력 SHA256/환경/자원 로그, 선택 동결 JSON, 예측 NPZ/CSV, results.json,
ROUND_REPORT.md, 독립 검산. 학습자 설명 질문: 단독 후보 왜 틀리는가? 76/195로
무표=0이 최적인가? 이진 재검사의 학습 분모와 적용 분모는 왜 다른가? 잘못된 배제는 무엇인가?
