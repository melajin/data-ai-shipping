# 보조 생성 명세 일탈 기록

2026-11-04 약21:07UTC 관리자 list_agents에서 reviewer가 추가 생성한 `/root/round014_reviewer/integration_scope_decision`을 확인했다. 검토자 진술은 agent_type=astra_decision, fork_turns=all, 명시 model/effort 없이 역할 기본값을 의도했다는 것이다. 현재 루트의 모든 보조 Luna/xhigh 명시·forknone 규정보다 상위 옛 역할 지시를 적용한 오류다.

관리자가 child의 호스트 session_meta/turn_context를 직접 확인한 결과 실제 기록은 **gpt-6-luna/xhigh**였다. 증거는 unapproved_child_host_evidence.json이다. 역할명이나 검토자의 추정으로 실제 Astra 실행이었다고 주장하지 않는다. 호스트 기록상 모델 변경은 관측되지 않았다. root+author+reviewer+추가child=4로 호스트총4, 사용자보조상한4를 넘지 않았다.

추가 child는 발견 시 완료 상태였으며 후속 통합 범위에 대한 읽기전용 자문이었다. 자문을 채택하지 않고 관리자의 사전 M4-a 범위를 유지했다. 추가 생성 금지를 전달했다. 이 기록은 코드·실험 source-freeze 판정과 별도로 보존하며 생성 절차가 완벽히 준수됐다고 보고하지 않는다. 모델 실행 증거와 요청 명세를 구분한다.
