# Round 001 독립 검토 수신 기록

이 파일의 작성자는 관리자 Astra high다. 독립 검토자 `/root/next_step_decision/round001_independent_review`(요청: GPT-6 Luna xhigh)가 collaboration 메시지와 최종 `review/review.json`으로 전달한 검토 내용을 읽기 쉬운 형태로 보존한다. 리뷰어가 직접 쓴 원본은 `review/preliminary_review.md`와 `review/review.json`이다. `review/review.md`도 존재하지만 JSON과 같은 내용으로 저장돼 있으므로 구조화된 최종 원본은 review.json을 따른다. 이 수신기록을 리뷰어가 작성한 문서로 주장하지 않는다.

검토 작업은 2026-11-04 약13:55 UTC에 시작했고 약30분 예산 뒤 마감했다. root가 관리자 소유 수신기록 보존을 승인했고, 관리자는 리뷰어를 interrupt하여 추가 쓰기·탐색·프로세스 시작을 중지했다. 마감 시점에 최종 JSON 저장이 확인돼 내용과 판정을 읽었다. 리뷰어 원본을 수정하지 않았다.

## 수신한 독립 검토 내용

1. **T5 의미와 원배열 한계:** 원 S6는 `_fishing_mask_global()` 및 T5 함수로 동적 특징을 만들고, exp01은 CSV를 읽어 만든 X304를 사용한다. 원 class reference는 fold FIT이며 공용 항구 geometry는 Train+Test population이다. 동적 재구성은 전체 Train 7,372척의 개별 geometry를 읽으므로, holdout 이력이 미확인인 현재 경계에서 실행할 수 없다. Train-only 항구 집계를 대체하면 별도의 의미 변화가 되어 round-trip 비교가 아니다.
2. **안전한 계산 범위:** 실행기는 개발 NPZ 5,897척과 해당 T5 CSV에서 T5 slice만 바꾼다. 코드 검토상 holdout/raw 직접 읽기 또는 학습은 없다. CSV parser/재직렬화 검사는 원 동적 메모리 배열과의 일치 증명이 아니다.
3. **주 계산:** 3fold의 NPZ T5와 기본 CSV reader는 finite 값과 NaN mask를 포함해 exact 일치한다. 기본/round_trip 차이는 fold별 약27.7천 값에서 max abs8.881784197001252e-16이다. ULP 수는 계산하지 않았으며 절댓값만으로 모든 항목이 1 ULP라고 단정하지 않는다. 현재 15모델의 개발 전체 확률 max차이는0.004175이지만 개별 OUTER argmax변경은0이다.
4. **독립 검토자가 직접 확인한 보조 JSON:** 저장 15개 seed OUTER 확률과 모델 재추론은 각각 max abs0으로 일치한다. 5seed 평균과 기존 저장 평균 확률의 max차이는2.22e-16이며 tolerance1e-12를 통과한다. 기존 저장 argmax 5,897/5,897과 일치하고 micro0.5930133966423605, macro0.5252719738966167을 재현한다.
5. **parser 민감도와 평균 예측:** round_trip 평균도3,497/5,897 정답, 같은 macro, 평균 argmax변경0, gain/loss0이다. 확률 자체는15척에서변하고 max abs0.0012018578769440735다. 이를 “확률동일” 또는 “동적 원배열과 동일”로 확대하지 않는다.
6. **실패 복구·기록:** 보조 첫 시도의 fold2 expected1966은 실제1965와 달라 harness assertion이 실패했다. 실패코드/로그를 보존하고 실제 역할표 개수로 수정한 attempt2가 복구했다. attempt2 시작/종료 코드해시가 같고 actual exit0이 확인됐다. 주실행 exitcode는unknown으로 표시해야 하며 완료 stdout·빈 stderr가 exitcode를 대신하지 않는다. 이 지적을 받아 관리자가 main manifest에unknown 및 사후 코드해시/미기록 launch hash를 명시했다.
7. **다음 설계 검토:** INNER_ES와 INNER_SELECT를 나누고 기준선도 ES만 쓰도록 다시3fits 하는 구조, fold별 SELECT alpha 및 OUTER 미사용은 타당하다. 후보가 학습 목적/가중치까지 다르면 pipeline 비교이며 순수 모델 계열의 인과효과라고 해석하지 않는다. 전체7,372 cache를 먼저 읽고 나중 필터하는 loader는 사용하지 않아야 한다.
8. **가용성:** TabICL 소스의 FIT→INNER 예측 경로와 environment metadata는 있으나 조사 경로에서 checkpoint/runtime이 없었다. S4는 기존 OOF oracle 조합으로 새 모델 생성 경로가 아니다. active Python3.13의 sklearn1.6.1/LightGBM4.7.0 및 CatBoost/Torch/TabICL 부재를 확인했지만 이것을 모든 환경에 대한 부재 증명으로 확대하지 않는다.

## 관리자 판정과 조건

리뷰어의 최종 판정은 **CONDITIONAL**이며, 관리자는 **허용된 재현 진단 완료, full dynamic 원배열 비교 미완료**로 채택했다. 최종 JSON은 다음 고정 캐시 기반 개발 후보 탐색을 `not_blocked_for_bounded_development_candidate_exploration`으로 판정한다. 고정 입력의 현재 baseline 재현을 무효화하는 수치 모순은 보고되지 않았다.

다음 모델 비교는 현재의 고정 NPZ·소스/환경·분할 계약을 유지하는 조건으로 진행할 수 있다. 옛 .59183의 원인, 원 dynamic parity, 독립 holdout 성능은 해결했다고 쓰지 않는다. 주실행의 종료코드/launch hash 이력 공백도 보존한다. 모든 결과는 반복 노출된 개발자료 계산이며 독립 일반화·공식점수·하드웨어 검증이 아니다.
