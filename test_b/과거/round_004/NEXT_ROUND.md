# Round005 — bounded trace와 전체 단계 원자성·빈 입력 계약

새실제Sol/high감독ACK·단일소유권활성화뒤새round_005/에서수행한다. E/V는각각별도실제Orca gpt-6-luna/xhigh,worker_done으로보고한다. 원자료/canonical/cache/선행round(004포함)는읽기전용이다.

## 질문과 고정 근거

질문은제한정수변환의값/원index를유지하면서trace보유량을bounded로하고늦은미지원입력에서부분결과가최종게시되지않게할수있는가다. Round004의제한AST/독립oracle/adapter및실제16,384행4batch값·index라벨동등성은계승한다. 생산gate는FAIL/V최종exit2,감사task succeeded다. E최종exit0을전체성공으로표현하지않는다. RangeIndex/Index차이와빈schema는미해결이다. 실제전체domain은unknown이며참조/점수/A/membership는없다.

1. E는새execution/만소유한다. Round004실패snapshot을읽고새버전으로옮겨수정하며원004파일은변경하지않는다. transform_months의local_trace전체누적을없앤다. offset은admitted-row수만으로전달하며caller가trace=None이면index목록을만들지않는다. 디버그trace도행수에비례하는목록을자동보유하지않도록요약/상한/스트리밍sink를정한다. list에서offset을역산하지않는다. 월/배치/빈batch/숫자drop뒤구멍을유지한다.
2. generator와전체단계호출자의계약을분리해실제안전caller를구현한다. 전체지원범위확인전yield결과는신규격리scratch에만둔다. 성공시명시된출력경로에atomic commit하고미지원/오류시최종manifest/result를게시하지않는다. 실패scratch는격리표시·영수증보존하며사용자자료를삭제하지않는다. 정상뒤unsupported/예외/commit실패·기존최종경로존재·부적절경로의부정시험을작은fixture로검증한다. 전체frame버퍼링으로원자성을만들지않는다. stage파라미터·쓰기격리·Testfit/defaultdeny를실제호출전에강제하고구현되지않은builder를완성품으로부르지않는다.
3. 빈month/전체empty에서원본과같은열/순서/dtype/index를반환/재구성할schema계약을구현한다. 빈months목록ValueError는보존한다. 무탈락RangeIndex와숫자제외후원index형식을원본AST와엄격비교한다. 단순reset_index로구멍을없애지않고기존값/변환순서/NA/제외/정렬동점/라벨/상수를바꾸지않는다. 원본API의ID/date요청유무·key_valid/month열추가·월순서를지킨다.
4. 별도V는audit/만소유하며정적설계/도메인논증과새fixture의AST·독립oracle·원자성·bounded보유량·빈schema·indexclass를검산한다. 이전원인검산을그대로반복하지않고수정차이를직접구별하는부정검사를고정한다. adapter변경에대한제한실제multi-batch재검사가필요하면선택범위/해시/최대16384행/4096batch/열을사전고정하고fresh RAM후진행한다. 반복필요근거를기록한다.
5. 위관문통과뒤2026Train key-only전수domain검사사전계약을새로고정한다. 정확행수는6footer합3,887,069(497942/479290/657292/717294/761846/773405)이다. E004초안4,212,389는Test합계였으므로채택금지/이력보존이다. 입력hash/schema/필요열/key_valid population/ID제외 후 date검사/원행·admitted concat offset/mask/실제exit/출력/예산을고정한다. source CSV재파싱/전체objectframe동시로딩금지다. domain지원밖은임의삭제하지않고전체중단한다. V는독립전수domain·mask/index·hash·RSS를 검산한다. 전체도메인unknown을검사전pass로추정하지않는다.
6. B방식미지원발견또는논증불가이면A방식(전체ID Series원본전역pd.to_numeric→ID제외/cast→남은date전체Series원본변환;feature청크)과새RAM계획으로전환한다. 원본반올림/overflow를교정하지않는다. 두raw키열을무조건함께로딩하지않고copy/mask/allocator/pagecache도계상한다.
7. loader/원자성통과후harbor/density/gap전체 중첩RAM(이전cache/closure/정렬/groupby/dict/set/KDTree/scratch/serializer포함)과train-onlyfit/쓰기·pycache/progress동적관문을갖춘새경로에서만조건부참조/고정탐색score/A를허용한다. Round003생산runner는stub이다. summary일치는일관성검사이지전체동등성이아니다. 점수는기존46,705행/100원문ID순서/전제계약A·floor·충돌·naivetime를보존하며사고시간으로기간을자르지않는다.

## RAM·금지·보고

모든메모리/병렬작업직전현재가용RAM·예상peak·타작업·추정근거/시각을기록한다. 부족하면가능한작업우선·보류재개직전재확인,청크/순차/동시수축소우선이다. polling/watch·사용자process종료금지다. Round004 V최종표본peakRSS125.46MiB/commit618.65MiB는작은검사관측이며큰경로의예산보장이아니다.

기존Round002Test46,705행전수대조/26행합성은반복하지않는다. 초기FAIL/metadata deltaPASS10exit0·역사44해시unknown을 보존한다. 임계값/B/C/사고여부/성능/제출/실제split/사고파일개발사용/외부수집·연락/push금지다. 사고신원/정상근거/개발사용/공식수식부족은blocked_external_evidence이며후보/합의로대체하지않는다.유효로컬가설을계속진행하고매round상세보고/쉬운설명/성공기준차이/다음실제Solhigh감독ACK·단일소유권인계를유지한다.

Round004 E최신ctx_94f3ac9fe789와V최신ctx_80f1e954bee2는worker_done으로settled/released/exited다. 같은handle옛dispatch와활성후속을혼동하지않고Round001user_kept/identity_unproven창은우회종료하지않는다.


