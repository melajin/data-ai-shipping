# 모델 요청과 호스트 증거

관리자: Orca 세션 codex_53b6ac45_0a2c_4a1a_b5d5_2624c7a28d9e. 요청 gpt-6-astra/high. 호스트 turn_context도 동일(model_runtime_evidence.json). 이는 호스트가 기록한 설정 증거이며 모델 내부를 독립 인증한 것이 아니다.

| 담당 | 요청 | provider ID | 수정 소유권 |
|---|---|---|---|
| runtime_author | gpt-6-luna/xhigh, fork_turns=none | 01a1a774-7d04-7623-be0c-9abfa93b0515 | code/probe_tabicl_runtime.py, runtime_author/ |
| lineage_author | gpt-6-luna/xhigh, fork_turns=none | 01a1a774-a4b4-7a12-8920-f74f9185ef40 | lineage/ |
| reviewer | gpt-6-luna/xhigh, fork_turns=none | 01a1a774-c7a5-7d71-9402-312b5b7f7f77 | review/ |

세 보조 turn_context도 각각 Luna/xhigh이다. session_inventory.json의 providerId·description으로 역할을 연결했다. 관리자 포함4슬롯, 보조3명이며 사용자 상한4명 및 호스트 총4슬롯을 지켰다. 각 담당에게 타인의 수정사항을 되돌리지 않도록 명시했다.

인계 원본 SHA256 B726E9CD58F3AC6828C38396F5ED7F4D5EACBEB63A979FD1A539342BBE849894와 현재 문서가 일치했다. launch receipt의 수신 세션과 현재 ORCA_AGENT_SESSION_ID도 일치. 이전 관리자 codex_72aeaa5c_d706_4426_8c38_be2ff5da2bd9는 host state=done. 다른 회차 계산 프로세스는 발견되지 않았다. 원본 인계/상태를 INCOMING_*에 보존했다.

초기 model metadata 읽기는 FileShare 기본값 때문에 활성 JSONL 읽기 실패가 났다. FileShare.ReadWrite의 읽기 전용 stream으로 모델/effort 필드만 추출해 복구했다. 이 운영상 실패는 모델 실험 실패나 모델 변경이 아니다.
