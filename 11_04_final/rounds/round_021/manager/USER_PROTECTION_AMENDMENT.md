# 사용자 지시 반영 — OUTER 확률·점수 열람 전

2026-11-04 23:29–23:31 UTC. 분석세션에서 전달한 msg_67983631ae95 및 msg_101222d85c7f를 반영한다. 기존 .03 허용하락보다 이번 명시 지시가 우선한다. 자망(class1)·통발(class2)을 개선하되 연안복합(class0)·채낚기연승(class3)의 recall은 낮추지 않는다.

같은5897명부·support=[2920,2016,835,126]에서 보호class TP를 정수로 비교한다. 역사 채택 sqrt_macro5seed의 TP=[2381,908,116,92], 같은조건 seed42의 TP=[2389,889,108,90]다. 따라서 후보는 역사 기준의0/3 TP≥2381/92 및 같은조건 TP≥2389/90를 모두 만족해야 하며, 합친 최소치는 **class0≥2389, class3≥92**다. 허용epsilon으로 한 척 손실을 숨기지 않는다. 역사TP는 기존 aggregate recall×support에서 복원했고, 해당행별예측의ID/y/fold 정합과TP는 소스/config동결·meta3저장재로드 후에만 다시 검산한다.

두기준 각각에 대해 보호class gain/loss/net TP를 보고한다. recall 총량이 같더라도 맞히던 배를 잃고 다른 배를 고쳤으면 둘을 각각 표시한다. 자망·통발 TP/recall·precision/F1·FP 출처와 trueclass별 prediction transition을 함께 보고한다. 단순 예측량 증가를 개선으로 부르지 않는다. micro+.005/pairedCI/기타class F1·recall/관측일수 관문은 유지하되 보호class recall .03 예외는 이번0하락 규칙으로 대체한다.

현재 OUTER 확률·예측·점수 열람/새fit0. reviewer의 역할명부 대조에서 original NPZ 전체 y가 로드된 한계는 PRELIMINARY_SOURCE_REVIEW에 기록했으며 새맹검으로 표현하지 않는다. 라벨을 이용한 후보변경·선박별예측선별은 없다.

020의 사전고정12열logistic/3fit/grid0/retry0는 유지한다. 하드보호를 실패하면 기각한다. 점수를 본 뒤 임의 예측 잠금/threshold조정/추가fit은 하지 않는다. 021의공간8열분기도 이보호규칙을 계승한다. .7도달해도 보호조건실패면 채택하지 않는다. .7미달은 기존021 통제비교로 진행한다. .7이상이나보호실패일경우에도 확인seed확대 대신 같은021표현비교에강화보호를적용한다.

역사baseline source/path/hash는 historical_protection_reference.json. 이번 원확률과 역사baseline 자료는읽기전용이며 sourcehash·명부·검산결과를보존한다.
