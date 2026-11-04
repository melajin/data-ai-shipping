# 사용자 우선순위 교정 — 2026-11-05

Orca 메시지 msg_17b582e8a8ba와 msg_49e433720914를 사용자 알림에 따라 수신했다. 원문은 orchestration_message_01.json 및02.json이다. 전달자는 orca_session_id:codex_6b307c5a_55da_483c_b425_0031c6f730b8이며 수신·판단 회신은 orchestration_reply_01.json이다.

사용자는 micro-F1 0.7 성능 목표를 검증 회차 누적으로 대체하지 말라고 명확히 했다. 현재까지 채택된 F1 개선은0이고,004–018은 새 F1이 없다. 기존 개발5seed micro0.5930133966423605를 유지한다. 제어 관문 통과를 성능 향상으로 표현하지 않는다.

관리 판단: 현재019의 동결 전 제어수정·승인·유한실행 계약은 그대로 마무리한다. 다음020은 X304/기존 LightGBM 경로에서 같은조건의 실제F1 비교를 우선한다. M4 전체estimator 저장재로드나 이 제어실행기 수리는 해당 M4 경로의 국소 관문이며, 기존 LightGBM 성능 실험의 필수관문이 아니다. M4는 별도 보류할 수 있다.

검토 중인 가장 짧은 가설은 동일 FIT-only sqrt 가중치·LightGBM 용량·seed42·3fold에서 INNER_ES 조기종료 지표를 macro에서 micro로 바꾸는 것이다. 기존 exp01 실행이력과 round002 ES/SELECT 분리조건을 확인해야 한다. 동일조건 이미 완료된 경우 단순재실행하지 않는다. 기존 round002 monthly_repeat35 소스메모는 다른 가설의 근거이며, 결과를 보고 후보를 고르는 방식으로 사용하지 않는다. 최종 후속 가설·정확입력·횟수·판정·실패분기는 NEXT_SESSION.md에 확정한다.

holdout 개별행은 여전히 금지하고 개발OUTER 반복노출·T5/local_rel transductive조건을 유지한다. 새 성능 실험은 최대fit수·시간·RAM·동시1·threads3, 같은조건 기준선·순증·micro/macro·클래스·관측일별 지표와 채택 여부를 남겨야 한다. 0.7 달성이나 미측정 성능은 보장하지 않는다.
