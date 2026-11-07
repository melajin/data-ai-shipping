# Round005 V 후속 — 고정 E snapshot 독립 동적검산

이 spec은 감독이 최신 E후속 ctx_8f62e408a6cd/task_6ff53dda043c의 worker_done·최종hash를 확인한 뒤 실행한다. 최초 E보고 msg_cbcb59256816만으로 진입하지 않는다. E/V각각실제별도Orca gpt-6-luna/xhigh 요청/launch, provider내부 model/effort unknown. 감독codex_3420efaa_9881_48b8_b7f4_4985bdf027b2,Run run_6df8333350eb. 원자료/canonical/cache/선행round읽기전용이며 수정소유권은새 testB/round_005/audit/dynamic_001/뿐이다. E코드·공통문서를수정하거나다른작업자편집을되돌리지않는다.

AGENTS.md/RAM규칙, USER_DIRECTIVE_20261105.md, ROUND_PROTOCOL.md, SUCCESS_CRITERIA.md, round005계획·기존V정적계약/동적계획, E최신보고·receipt·hash목록·loader/caller/fixture코드와round004최종실패보고를읽는다. ORCA_CLI_COMMAND선택실행파일의skills get orchestration/orca-cli 안내를확인한다. E최신후속의최종hash를직접비교하고 실행전후에도고정snapshot을확인한다. 해시모순/파일변경이면동적검사를중단·보고한다.

E비교기를그대로재실행하지말고 pinned canonical load_rows AST, Ehelper를재사용하지않는독립 whole-column oracle, 명시손계산expected를먼저상호대조한뒤 E새loader와실제caller를비교하라. 먼저정적계획행렬을사용하되 index class/label/dtype/이름과전체frame columns/order/values/dtypes/NA/drop mask를엄격비교하라. 원본ID전체변환/drop/cast후남은date전체변환/drop/cast순서, key_valid선처리/global admitted concat index와구멍을보존한다. no numeric keys/IDonly/dateonly/both/key_validTrueFalse/월순서와경계/month요청/빈batch·빈month·전체empty·무배치/allNone/empty월목록을분리한다. empty_template가canonical의정확한빈schema인지검증하고 잘못된dtype/index/template를신뢰하는지한계를분리한다. 모든행이numericdrop되는경우와무탈락RangeIndex의경계를확인한다. 제한domain의±2^53/dateint32/부호/leadingzero/null/nonnumeric과unsupporteddecimal/scientific/공백/Unicode/범위·길이초과를검사하며silentdrop성공을허용하지않는다. ID실패행의unsupporteddate는원본순서상미검사다.

trace=None은row/index목록생성·월누적0임을구조및동적으로확인한다. debuglist는명시cap/streamsink는caller소유자비축불가계약을구분한다. stage receipt의filesメ타데이터목록은O(batch수)일수있으니trace와별도로분석·예산근거를남긴다. 전체framebuffering없음을확인하고작은RSS를전체상한으로표현하지않는다.

actualcaller를독립실행해part저장/정확index재구성/manifest성공의미/atomic게시경계를검사한다. 정상1batch뒤unsupported/일반예외/쓰기실패/stage생성실패/commit실패/기존final/commit직전target생성경쟁을구별한다. 기존sentinel/hash불변,실패후불완전final없음,quarantine/receipt보존을직접관측한다. stage/dataset비testfit/root자체/외부경로/traversal/중복요청열/reservedindex열/link·junction을거부하는지검사한다. quarantine루트가link인경우와동적경로변경위협은고정신뢰root계약및실제지원범위와구분해보고한다. symboliclink생성이권한으로불가하면실제동적검증으로표현하지말고junction대체의범위를기록한다. 사용자자료삭제/OS-temp삭제/이전E임시폴더정리는이task에서하지않는다. 모든검사scratch는audit/dynamic_001하위만.

새adapter/caller변경은실제multi-batch재검사의새근거다. 작은독립fixture가모순없을때다음고정표본만허용한다: Train월1 rows_train_1.parquet,기존SHA7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140,물리첫16384행,최대4096batch4회,projection row_index/rfid_id/part_dt/rfid_time/key_valid/wkt_valid/len_m/bbox_m/cen_lon/cen_lat. 선택·hash·명령·RAM을사전기록하고별도sourcebatch를직접읽어새E경로로각각처리·격리commit·재구성후 AST/독립oracle와엄격비교한다. sample전체E한번변환으로batch검증을대체하지않는다. source전체hash스트리밍은입력식별이고전체domainscan이아니다. 전수Train keyscan/참조/실점수/A/membership는금지다.

모든메모리작업직전현재가용RAM/예상processpeak512MiB+hostreserve1024MiB/타작업/추정근거·시각을기록하고최소가용1536MiB를작은검사시작기준으로한다. 보장값아니며넘으면중단·보고한다. 부족하면정적작업우선·재개직전재확인,청크/순차/동시수축소우선,polling/watch/사용자process종료금지. RSS/commit/hostfree를구분한다.

Round004 Eexit0제한표본과V최종exit2생산FAIL·감사succeeded,Round003Eexit2/V실패재현fixtureexit0·감사succeeded·결합16384행한계,Round002초기FAIL/metadata-onlydeltaPASS10exit0/역사44hashunknown을보존한다. 기존Test46705행전수대조/26행합성은반복하지않는다. Trainfooter3887069(497942/479290/657292/717294/761846/773405),E004초안4212389는Test오류,전체domainunknown이다. sourceCSV재파싱/stockCLI/main/stage/임계값/B/C/사고여부/성능/제출/실제split/사고파일개발사용/외부수집·연락/push금지. 사고신원/정상근거/개발사용/공식수식부재를후보/합의로대체하지않는다.

최종산출물: 독립검산script/사전fixture·표본계약/실제명령exitstdoutstderr·모든실패시도/버전·pinnedsource및E고정hash·검사출력hash·RAM/RSS/commit/격리·quarantine상태/판정과한계. 실패를정확히발견·기록하는것도감사task완료succeeded일수있으나검사script실제exit비0과production gateFAIL을명시적으로분리한다. worker_done으로정확최신task/dispatch에보고하고턴종료한다. E수정은하지말고결함을감독에게보고한다. 후속domaingate는이task단독PASS로자동실행하지않는다.


진입 증거를 감독이 확인했다: 최신 E worker_done msg_70525506a270, task task_6ff53dda043c, dispatch ctx_8f62e408a6cd succeeded이며 같은handle 활성후속은 없었다. 2026-11-05 07:38:36+09:00 직접 SHA 검산이 다음 최종값과 일치했다. bounded_loader.py 0c60af2d4453c4ffb0a640410006e09247218a96633075cdd89567e4ae6f3cee; isolated_stage.py 76f3f7f8e3a39a27d8c24f1d3532b83181bf2e20470da38b7543b55a04795fea; verify_fixtures.py 61c7b9c3acddce4e904bf3b368ff8c3828a78f6344d5cfd2aee072c9219ed57f. E최종 fixture는 frame14/atomic17 exit0이며 실제표본·전수domain은미실행이다. V는 자기 실행 직전 fresh RAM을 다시 확인한다.
