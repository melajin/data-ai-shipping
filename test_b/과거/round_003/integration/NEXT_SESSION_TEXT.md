# Test B 다음 감독 진입점 — Round004

Round003의 단순 batch numeric loader는 동등성 실패로 기각됐다. 실패와 독립 검산을 보존한 뒤 새 실제 Sol/high 감독에 인계한다. 현재 단일 소유자는 STATUS.json의 active_supervisor_session이다. 새감독은 최초 인수ACK 후 턴을끝내고, 소유권변경과이전감독활성화메시지를모두확인한뒤 시작한다. worker생성·새계산·공통문서중복수정금지.

먼저 round_003/HANDOFF_INSTRUCTIONS.md와 그안의 필수문서를 UTF-8로 전부 읽는다. 토큰 testb_r003_to_r004_20261105_numeric_domain, 이전감독 codex_4269e9a1_ce56_4684_9e30_794fd12ed5b7이다. ORCA_CLI_COMMAND와 실제버전orchestration/Orca CLI 안내·AGENTS RAM규칙부터확인하고 자기ORCA_AGENT_SESSION_ID와토큰으로인수ACK를send한다. 사용자재승인을요구하지않는다.

계승: 새100척46,705행은round002 source4,212,389행 독립전수대조완료이며 실제새점수/A는없다. 초기감사FAIL/exit1은stale해시구분문제였고 metadata-only deltaPASS10/exit0로정정검산했다. 역사44digest의최초의미/시점·원바이트복원은unknown이다. 같은전수Test스캔/26행합성을반복하지않는다.

Round003: 실제train첫16,384행은두batch를결합한표에transform_batch한번이므로batch별동등성증거가아니다. 전역Series에9007199254740993과1.5를같이넣으면원본정수결과가9007199254740992,한행batch면9007199254740993인합성반례를발견했다. E최종exit2/workerfailed와 V원본AST+독립oracle실패검산fixtureexit0/감사task succeeded를구분한다. key_valid후concat의global index도batch local index와달랐다. 현production runner는미구현defaultdeny stub이다. 실제train참조/새점수/A/membership는미생성이다.

다음은round_003/NEXT_ROUND.md다. 새round_004/에서별도실제Luna/xhigh실행·독립검산으로 제한정수도메인fail-closed와global index보존을검증한다. 작은동등성/예산통과뒤2026train key-only전수domain검사를기술관문으로진행할수있고,미지원이면키열전체전역변환A방식으로전환한다. 실제domain은아직unknown이다. 동등성과새경로RAM/격리/고정train-onlyfit확인후조건부참조/탐색점수/A를생성·검산한다. stockCLI/stage/기존쓰기금지다.

RAM은메모리작업직전가용량·예상peak·병행작업·추정근거/시각을확인한다. 부족하면다른가능작업후재개직전다시확인,청크/순차/동시수축소우선,polling/watch·사용자process종료금지. 원자료/canonical/cache/선행round읽기전용이며새파일은소유권별round004/뿐이다.

사고신원·정상근거·개발사용·임계값·분할·공식수식은미확보다. 후보/합의/목록부재를정답으로만들지않는다. B/C·사고여부·성능·제출·실제split·외부수집/연락·push금지다. 사용자는조건충족까지실제새Sol/high감독/별도실행·검산/완료창정리·라운드보고와단일소유권인계를승인했다. 유효한로컬후속을지속하고외부근거부족은blocked_external_evidence로구체화한다.

Round003 E와최신V는worker_done으로settled/released,worker-list exited다. 최신V는closed_agent_terminal응답도확인했다. 같은handle의옛dispatch와활성후속을혼동하지않는다. Round001 user_kept/identity_unproven창은강제종료하지않았다.
