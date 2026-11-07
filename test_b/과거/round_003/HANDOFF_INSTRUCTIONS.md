# Round003 → Round004 감독 인계

토큰 testb_r003_to_r004_20261105_numeric_domain. 이전감독 codex_4269e9a1_ce56_4684_9e30_794fd12ed5b7, Run run_202dfeeb8d64. 새감독은실제Orca gpt-6.1-sol/high로launch한다. 요청/Orca launch설정과provider내부unknown을구분한다.

## 최초 인수 ACK 후 턴 종료

ORCA_CLI_COMMAND와실제버전 `skills get orchestration`, `skills get orca-cli` 안내, AGENTS RAM규칙부터확인한다. 다음필수문서를UTF-8로전부읽는다.

- AGENTS.md, testB/USER_DIRECTIVE_20261105.md, ROUND_PROTOCOL.md, SUCCESS_CRITERIA.md, STATUS.json, LEDGER.md, NEXT_SESSION.md.
- round_003/ROUND_PLAN.md, ROUND_REPORT.md, EASY_EXPLANATION.md, NEXT_ROUND.md, 본문서, HANDOFF_RECEIPT.json.
- round_003/execution/preflight_report.md, execution_summary.json, execution_receipt.json, bounded_loader.py, compare_loader_sample.py, round003_runner.py.
- round_003/audit/independent_static_review.md 및 audit/failure_001/failure_audit.md, manifest.json, fixture_result.json.
- round_002/contract/EXPLORATORY_EXECUTION_CONTRACT.md, ROUND_REPORT.md, NEXT_ROUND.md.

자기ORCA_AGENT_SESSION_ID와토큰을이전감독에게 `orchestration send --to orca_session_id:codex_4269e9a1_ce56_4684_9e30_794fd12ed5b7 --type handoff --subject 'Round004 인수 ACK' --body '토큰 ..., 내 session ID ..., 필수문서인수완료·활성화대기' --json`으로보내고턴을끝낸다. STATUS소유권변경과명시적활성화메시지를모두받기전worker생성·새계산·공통문서수정금지. 사용자재승인절차가아니다.

## 활성화 뒤 범위

NEXT_ROUND.md를새round_004/소유권별로실행한다. 제한도메인fail-closed와원본outputindex보존을먼저작은fixture/실제여러batch로검증하고별도Luna검산뒤새train key-only전수domain검사를기술관문으로허용한다. 실패시전역키열변환A방식과새RAM계획을검토한다. loader통과뒤조건부참조/탐색score/A까지가능하며큰실행을미리강행하지않는다. 실제실행·독립검산은각각별도Orca gpt-6-luna/xhigh, worker_done이다.

계승: 새100척46,705행은round002독립전수대조완료. round003의단순batch prototype은정밀도반례로실패했고E최종exit2/workerfailed다. E실제표본은결합한16,384행한번변환이므로청크동등성증거가아니다. V는원본AST+별도oracle로반례및index차이를검산했고fixtureexit0/감사task succeeded다. 이검산성공을생산성공으로부르지않는다. production runner는미구현defaultdeny stub,실제참조/새점수/A/membership는없다.

원자료/canonical/기존cache/선행round읽기전용. 기존전수Test스캔/26행합성은근거없이반복하지않는다. round002초기FAIL/metadata-only deltaPASS10/exit0와역사44해시unknown을보존한다. 임계값/B/C/사고여부/성능/제출/split/외부수집/연락/push금지,후보/합의를정답으로만들지않는다. RAM부족시다른작업우선·재개직전재확인,작업전peak/병행작업·근거/시각기록,polling/사용자process종료금지.

round003 E/V최신task는worker_done으로settled다. E는released/exited, V최신ctx_d19e5fc43cd8은release응답closed_agent_terminal및후속worker-list exited/released를확인했다. 같은handle의옛dispatch가아닌최신후속기준이다. Round001 user_kept/identity_unproven은강제종료하지않았다. 이전감독/완료창도정확식별·최신dispatch/활성후속을확인하고retained/unknown을닫힘으로주장하지않는다.

사용자는조건충족까지연속round/실제새Solhigh감독/별도실행·검산/완료창정리를승인했다. 유효로컬작업을지속하고외부근거부재는구체blocked_external_evidence로기록한다. 매라운드재승인이나같은실험반복없이보고/쉬운설명/다음검증·ACK/단일소유권인계를유지한다.
