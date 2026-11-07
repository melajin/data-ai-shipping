# Test B Round004 결과

2026-11-05 KST. **제한 정수 도메인의 작은 비교와 실제 여러 batch의 값/index 라벨 일치는 확인했지만, 전체 단계 fail-closed·메모리 관문은 실패했다.** 전수 Train domain 검사, 참조, 새점수, 후보A, membership는 실행하지 않았다. 다음 라운드는 안전한 호출자와 bounded trace·빈 입력 계약을 수정하고 독립 재검산한다.

## 질문과 이전 비교

기술 질문은 좁은 정수 도메인과 key_valid 뒤 global concat ordinal로 원본 변환을 보존할 수 있는가였다. 학습 목표는 값 동등성·스트리밍 메모리·최종 산출물의 원자성·실제 사고 성능을 구분하는 것이다. 설명 질문: 뒤 batch에서 오류가 나도 앞 batch를 이미 최종 파일에 썼다면 전체 실패라고 안전하게 말할 수 있는가?

| 항목 | Round003 | Round004 |
|---|---|---|
| 숫자 값 | 단순 batch 변환은2^53+1/소수 혼합 반례로 실패 | 좁은 도메인의 AST/독립oracle/adapter 비교 통과. 전체 coverage unknown |
| 실제 표본 | 두 batch 결합 후 한 번 변환 | E와 V 각각 첫16,384행을4회4096행 호출. 값/열/dtype/NaN/index라벨 일치 |
| 출력 index | batch local index 차이 | 합성에서 global ordinal·숫자제외 구멍 확인. 실제 표본 index class는RangeIndex/Index 차이 |
| 메모리 | 큰 builder peak unknown | trace=None도 월별 index목록 O(월행수) 보유 확인, bounded 주장 실패 |
| 미지원 | 실패반례를 생산사용에서 기각 | 첫 batch 거부는 확인. 뒤 batch 실패 전에1행 yield, 전체 fail-closed 미완성 |
| 빈 입력 | 미검증 | 빈 months 오류는일치. 빈 month/전체empty의 schema있는0행 반환은 미완성 |
| 실제참조/점수/A/성능 | 없음 | 없음. 생산관문닫힘 |

Round002 새100척46,705행/source4,212,389행 전수대조와26행합성은 반복하지 않았다. 초기감사FAIL/exit1과metadata-only deltaPASS10/exit0, 역사44해시 의미/시점/바이트unknown을 계승했다.

## E 실행과 V 독립검산

E 최초ctx_5c62c63dcf5d/task_90c7d3fb7fca는worker_done msg_dd0fa18d7756 succeeded, 최신정적사항확인후속ctx_94f3ac9fe789/task_98ff809b03bc는msg_cf5c24f09425 succeeded다. E최종경량명령exit0이며 최초 injection keyword 오류exit1과중간exit0시도를보존했다. 범위는 좁은 ASCII정수(ID abs<=2^53/date int32), 최대128문자, null/명백한nonnumeric의원본coercion과미지원전체중단, 작은합성 및 실제월1표본이다. 이자료의전체domain성공을주장하지않았다.

V정적ctx_a8eef931ac8d/task_15389efe1b37는msg_0b8b1f7b1d7a succeeded다. 후속독립동적ctx_80f1e954bee2/task_a0f4ea39b854는msg_360d11f17db7 succeeded로감사산출물을완료했으나 **감사스크립트최종exit2/생산gateFAIL**이다. E의exit0과V의exit2를같은성공으로합치지않는다. V는E비교기를그대로재실행하지않고원본AST·별도whole-column oracle·명시기대값·Eadapter를대조했다. 원본4SHA와고정E21산출물해시는일치했다.

두달/key_valid True·False, key요청조합·열순서, null/NaN, ID제외후date검사, 부호/leadingzero/범위양끝/빈batch의제한비교가통과했다. 19개문자열미지원검사는첫yield전중단했다. V실제표본은같은고정월1물리첫16,384행/10열/4096행배치4회를직접읽어비교했으며제외0이다. 원본·adapter CSV직렬화SHA는0e70ea62112fc29e1feda89cb61e620c5b40e4558a99ae235a3fe08ad364c581이다. index라벨/dtype은같지만pandas container class는RangeIndex대Index여서strict DataFrame비교는false다. 원본과정확한class까지같다고표현하지않는다.

## 확정 결함과 미확인

1. transform_months는trace=None이어도local_trace를항상만들어각batch의output_index를월말까지보유한다. V합성에서보유index수1→2→3증가를관찰했다. 최대월773,405행에CPython정수28byte+pointer8byte만잡아도약26.55MiB후보이며header/allocator제외·실측peak아님이다. 동작량은O(월행수)다.
2. 정상1행batch후ID1.5batch를주면1행yield뒤UnsupportedDomain이다. generator자체의예외는이미전달한결과를회수하지않는다. 호출자의격리scratch/quarantine·전체검증후atomic commit/실패시미게시계약과실제부정검사가필요하다. 현재생산caller는없다.
3. 빈월/전체empty는원본schema있는0행frame과달리chunk가없다. 빈결과schema와materialization계약을정해야한다. 빈months목록ValueError일치는별개다.
4. E전수scan초안의4,212,389는Test총행수였다. V의Train6footer합은3,887,069행(497,942/479,290/657,292/717,294/761,846/773,405)으로기존Train계보와같다. 초안오류를보존하며그초안으로scan하지않았다. 실제key도메인은계속unknown이다.

## RAM과 범위

초기05:52:59가용4,530,664KiB/총14,480,244KiB에서E512MiB/V256MiB증분및각세션512MiB여유를계획했다. 이후06:08:31가용2,007,920KiB와귀속불명powershell RSS약2.34GiB를관측해V에fresh RAM/예상process512MiB+여유1GiB/최소가용1.5GiB조건을전달했다. 당시값을미래허가로사용하지않았다.

V최종합성·표본실행직전06:42:34가용5,906.4MiB/총14,140.9MiB였다. 실행후5,897.9MiB, process peak RSS125.46MiB, peak commit618.65MiB다. RSS/commit/hostfree는구분하며큰경로의보장상한이아니다. Vattempt01 AST주입오류, attempt02 comparator중간결과, attempt03최종원인검산을보존했다. 사용자process종료나polling/watch는하지않았다. 원본/선행round읽기전용,사고파일개발사용/외부수집·연락/임계값/B/C/사고판정/성능/제출/실제split/push미수행이다.

## 성공기준과 정리

기준1은기존입력계보와제한표본/Trainfooter확인범위에서만확장됐다. 기준2~5(사고신원·정상정답·독립split·최종사고출력·성능)는미충족이다. 기준6은이번변경의독립실패검산완료범위다. 기준7의보고/쉬운설명/다음검증을작성했고후속감독ACK·활성화는HANDOFF_RECEIPT에남긴다. 기술실패원인확인과학습자의설명능력달성은별개이며후자는평가하지않았다.

감독codex_8df5a67b_34a4_4a72_b561_d45861870f6f/Run run_a4759578d2ef,요청및기록된Orca launch gpt-6.1-sol/high다. E/V는각각별도실제Orca gpt-6-luna/xhigh이며provider내부model/effort는모두unknown이다.

E최신후속은settled/released/exited다. V최신동적후속을정확식별해release했고closed_agent_terminal응답및뒤worker-list exited/released를확인했다. 최초release에미지원--run옵션을넣은오류영수증과정정성공영수증을둘다보존했다. 같은handle의옛E행retained/unverifiable은최신후속의현재상태와구분한다. Round001user_kept/identity_unproven창은종료하지않았다.

근거: [E보고](execution/preflight_report.md), [E영수증](execution/execution_receipt.json), [V정적](audit/independent_static_review.md), [V동적감사](audit/dynamic_001/dynamic_review_report.md), [최종V실행](audit/dynamic_001/attempt03_python_run_receipt.json), [정리관측](integration/final_worker_list.json), [후속검증](NEXT_ROUND.md).
