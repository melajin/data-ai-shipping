# Round005 E — 작은 안전 경로 구현과 검증

당신은 실행자 E이며 별도 실제 Orca gpt-6-luna/xhigh로 요청/launch된다. provider 내부 실제 model/effort는unknown이다. 감독은codex_3420efaa_9881_48b8_b7f4_4985bdf027b2, Run run_6df8333350eb. 사용자 승인/ACK/단일소유권 활성화가 끝났다. 내부subagent로 대체하지 않는다.

먼저 AGENTS.md, testB/USER_DIRECTIVE_20261105.md, ROUND_PROTOCOL.md, SUCCESS_CRITERIA.md, round_005/ROUND_PLAN.md, round_004/NEXT_ROUND.md, ROUND_REPORT.md, execution/bounded_loader.py 및 domain_and_equivalence.md, audit/dynamic_001/dynamic_review_report.md를 UTF-8로 읽는다. ORCA_CLI_COMMAND를 확인하고 선택 실행파일의 skills get orchestration/orca-cli 안내를 읽는다. 다른 작업자가 함께 있으므로 수정 소유권은 testB/round_005/execution/만이며 V audit/와 공통문서는 읽기전용이다. 남의 변경을 되돌리지 않는다.

round_004/NEXT_ROUND.md 1~3을 새 execution/에 구현하고 작은 fixture로 검증하라. 기존004를 바꾸지 않는다. admitted count로 concat offset을 전달하며 trace=None에서 index목록을 만들지 않는다. debug도 bounded 요약/명시 상한/stream sink를 정한다. 전체 frame을 RAM에 모아 원자성을 만들지 않는다. 실제 안전 caller는 새 격리 scratch에 순차 batch를 쓰고 전체 성공 뒤 최종 경로에 atomic commit한다. 실패 시 최종manifest/result 미게시, quarantine 표시와 영수증 보존. 정상 뒤 unsupported/일반 예외/commit 실패/최종경로 이미 존재/경로탈출 등 부정시험을 포함한다. 경로·stage·Testfit/defaultdeny를 실제 실행 전에 강제하고 builder 없는 이전 stub을 완성품이라 하지 않는다. final 공개 경계와 commit point를 명시하고 실패하면 기존 공개 결과를 변경하지 않는다.

원본 pinned load_rows AST와 엄격 DataFrame비교로 빈month/전체empty의 열·순서·dtype/index 및 무탈락 RangeIndex/숫자drop후 Index와 구멍을 확인한다. stream과 전체 materialization의 계약을 구분하고 disk manifest에 재구성 metadata를 넣는 방법을 검토한다. 원본이 하는 변환/drop순서·월/물리순서·값·NA·dtype·라벨·상수를 바꾸지 않는다. 핵심 학습자 판단과 설명 질문은 보존하며 이번 범위 이상의 전체 시스템 자동완성은 금지다.

제한 domain은 ASCII정수 ID abs<=2^53/date int32/max128문자 등004의 조건을 계승한다. 지원밖은 임의제외하지 않고 whole stage중단이다. 원본 ID변환/drop/cast 뒤 남은date변환/drop/cast 순서와 key_valid후 ordinal/숫자drop구멍을 보존한다. API요청 ID/date없음·key_valid·month·월순서·빈목록ValueError를 검증한다. 필요시 실제 월1 첫16384행/10열/4096batch 고정표본을 새 경로에서 검증하되 미리 선택범위/기존 SHA/열/재검사 이유와 fresh RAM을 기록한다. 표본과全domain을 구분한다.

현재 전수Train key-only scan/참조/새점수/A/membership는 금지다. Trainfooter 3887069(497942/479290/657292/717294/761846/773405)이며 E004초안4212389는Test합계 오류다. 원본4SHA를 확인하고 원본/선행round/canonical/cache를읽기전용으로 유지한다. sourceCSV재파싱/전체object 이중로딩/stockCLI/main/stage/임계값/B/C/사고판정/성능/제출/실제split/사고파일개발사용/외부수집·연락/push금지다.

Round004 Eexit0은제한표본, V최종스크립트exit2/생산FAIL·감사succeeded다. Round003 numeric반례Eexit2/V실패재현fixtureexit0/감사succeeded·결합16384행한계와 Round002초기FAIL/metadata-onlydeltaPASS10exit0/역사44해시unknown을 보존한다. 기존Test46705행전수대조/26행합성은반복하지 않는다.

모든메모리/병렬작업직전fresh가용RAM·예상peak·타작업·추정근거/시각을기록한다. E process512MiB+여유512MiB는작은fixture/최대16384행10열/4096batch에대한계획이고보장상한아니다. V는정적검토256MiB+여유512MiB계획이다. 부족하면가능작업먼저·재개직전재확인,청크/순차/동시수축소우선. polling/watch/사용자process종료금지. 이전작은RSS를큰경로보장으로쓰지않는다.

산출물: 새 loader/caller, fixture검사, 계약/한계·정적RAM근거/실측RSS및commit구분, 실제명령·exit/stdout/stderr·버전·소스/출력해시·실패시도·격리상태 보고서와 영수증. worker_done으로 보고하라. 이 task는 수정 구현과 동등성관문 검증이 목적이므로 미해결 불일치/안전관문실패면 outcome failed와 실제exit를 보존한다. 임의로 성공처리하지 말고 독립V검산이 후속임을 명시하라. 질문은orchestration ask 후턴종료, worker_done 후턴종료.
