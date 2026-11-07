# 모델·담당·시작 증거

| 역할 | 생성 요청 | 호스트 관찰 | 수정 담당 |
|---|---|---|---|
| 현재 관리자 | gpt-6-astra / high | 현재 turn_context의 model/effort 일치 | ROUND_PLAN, manager/, logs 실행, 공유 상태, 보고서와 인계 |
| round005_author | luna_worker, gpt-6-luna / xhigh / fork_turns=none | turn_context 일치 | code/, author_notes.md |
| round005_reviewer | luna_worker, gpt-6-luna / xhigh / fork_turns=none | turn_context 일치 | review/ |

증거는 manager/model_runtime_evidence.json 및 assistant_host_evidence.json이다. 요청값과 실제 호스트가 보고한 설정을 구분하며 이는 모델 내부의 독립 인증이 아니다. 이 작업의 활성 팀은 관리자와 보조 2명이다. 호스트가 제공한 이 팀의 총 4슬롯 중 3슬롯을 사용한다. 사용자 보조 상한 4명을 넘지 않는다. 다른 독립 세션의 전역 활동과 이 팀의 슬롯 수는 구분한다.

인계 영수증은 round004에서 현재 ORCA_AGENT_SESSION_ID로 prompt_delivered/accepted=true를 기록했고 두 인계 문서 해시가 지정 해시와 일치했다. manager/session_inventory.json의 직전 관리자는 새 사용자 요청인 PDF/기술 문서 검토를 진행하며 같은 round005 실험을 수행한다는 증거는 없었다. Python 실험 프로세스도 시작 검사에서 없었다. 현재 세션만 round005 실행을 담당한다. 무관한 다른 세션이나 프로세스를 중단하지 않는다.

원자료/이전 저장소/공유자료는 읽기 전용이다. 코드 작성과 독립 검토 담당자를 분리하며 타 담당자의 변경을 되돌리지 않도록 지시했다. 전체 보호 표와 holdout 개별 값은 읽지 않는다.

시작 환경 조사에서 orca worktree ps에 지원하지 않는 --worktree 옵션을 한 번 사용하여 invalid_argument를 받았다. 도구가 제공한 유효 옵션을 따라 worktree ps --json으로 읽기 전용 재조회했다. 이는 실험 실행·데이터 읽기 또는 학습 재시도가 아니다.
