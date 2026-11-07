# Test B Round003 결과

2026-11-05 KST. **batch별 numeric 변환 prototype은 원본과 동등하지 않아 생산 사용을 기각했다.** 실제 train 참조·새100척 점수·후보A·membership는 생성하지 않았다. 실패 반례와 index 차이를 별도 실제 Luna가 검산했고, 유효한 다음 설계로 진행한다.

## 질문·기술 목표·학습 목표

원본의 월별 object frame/concat 비용을 줄이면서 값·순서·dtype·제외집합과 계산 규칙을 보존할 수 있는가를 검증했다. 기술 목표는 bounded loader와 단계별 RAM 계획의 관문을 마련하는 것이었다. 학습 목표는 표본 일치, dtype 일치, 전수 동등성과 사고 성능의 차이를 설명하는 것이다. 설명 질문: 최종 열이 모두 int64인데도 왜 같은 raw ID가 다른 선박 번호로 바뀔 수 있는가?

## 이전과 비교

| 항목 | Round002 | Round003 |
|---|---|---|
| 새100척 항적 | 46,705행 전수독립대조 완료 | 계승. 동일스캔 반복 없음 |
| 점수식/26행 합성 | 격리함수와 성분 검산 | 계승. 같은검사 반복 없음 |
| 참조 loader | 큰 object frame 중첩 peak unknown | batch numeric 반례 재현, 현 prototype 동등성 실패 |
| 실제 train 표본 | 미실행 | 첫16,384행 결합표의 단일변환 비교만 일치. 청크별 동등성 검증 아님 |
| index | 미검증 | key filter 후 concat index와 batch local index의 차이 확인 |
| 실제 새점수/A | 없음 | 없음. 생산 gate 닫힘 |
| 사고 신원·정답·성능 | 외부근거 부족 | 새 근거 없음. 개선·악화 비교 불가 |

## 실행·실패·독립검산

E는 원본4모듈 SHA 일치를 확인하고 새 execution/에 prototype·비교기·default-deny runner 및 RAM 계획을 작성했다. 실제 표본은 train1 물리입력 첫16,384행, 필수10열이다. Arrow에서8,192행씩 두 번 읽었으나 두 batch를 한 Table로 합쳐 원본 AST loader와 transform_batch에 각각 한 번 전달했다. 제한 표본의 값/NaN/열/행수/dtype/제외집합 일치만 인정한다. 청크별 parsing이 검증됐다는 해석은 독립검산에서 기각했다.

합성 경계에서 원문9007199254740993과1.5가 전역 Series에 같이 있으면 numeric 추론이 float64가 되어 첫값의 정수cast가9007199254740992다. 한 행씩 batch로 변환하면 첫값은9007199254740993이다. 최종 dtype이 int64로 같아도 값이 다르다. 이는 합성 반례이며 실제 train에 이 문자열들이 있다는 증거가 아니다. 원본의 반올림 동작을 임의로 고쳐 같은 알고리즘이라고 주장하지 않는다.

E attempt01은 pyarrow.parquet.Table 오류로exit1, attempts02~05는 경계불일치 기록에도exit0인 중간시도였다. 최종attempt06은 불일치를exit2로 반환했고 E worker_done msg_f7d45da31bf0은failed다. 최초/중간/최종 로그를 보존했다.

V는 처음 정적 필요조건을 정리해worker_done msg_7decbffa1ec9로 보고했다. 후속 별도 task에서 원본 load_rows AST+계약 기반 독립 oracle+prototype을 작은 합성으로 대조했다. 숫자반례를 재현했고 key_valid_only True/False 및 ID실패행 제외 후 date변환 순서를 확인했다. 원본 index [0,3,5]/[0,3,4,5,7]와 월별batch의 local index가 다르다는 점도 확인했다. 후속fixture 자체exit0은 **실패 재현 검산 성공**이며 생산loader 성공이 아니다. worker_done msg_119d074b1fd3은 해당 감사task succeeded다.

V는 canonical4해시, round002 pinned6개 해시, E의 기재5개 파일 및 summary/report 영수증 해시를 확인했다. 검사한 범위만 불변으로 인정하며 전체 파일시스템 불변이라고 확대하지 않는다. V는 실제표본/전체source를 재읽지 않았다. 사고파일은 사용하지 않았다.

runner는 builder가 없는 stub이며 허용인자를 줘도 실패한다. 실제 Testfit/출력 경로/pycache/progress 런타임 gate가 완성됐다고 부르지 않는다. E의 AST 표본경로와 python -B 실행은 별개 제한증거다.

## RAM 계획·보류 이유

시작 전 감독은05:15:28KST 가용4,800,744KiB/총14,480,244KiB, Python 미관측을 기록했다. E 경량증분512MiB, V256MiB와 각세션512MiB여유를 계획했고 큰실행은 금지했다. E/V는 작업직전재확인을 남겼다. V 합성직전05:31:22 가용4,234.6MiB, 예상증분32MiB이하/여유512MiB였다. peak는 실측하지 않았다. 사용자process종료나 polling/watch는 없었다.

E의 기존 builder 경로 추정은 harbor1.5~3GiB, density3~6GiB, gap1.5~3.5GiB 단독 후보이며, 같은 프로세스에서 앞cache/지도/closure와 겹치면6~12+GiB 가능성을 적었다. 보장상한이 아니다. 향후 청크 loader로 바뀐 실제 경로의 peak는 다시 산정해야 하며 이 추정이나 이전2GiB를 실행허가로 쓰지 않는다. 단순 RAM 부족과 변환동등성 실패를 구분한다. 이번 생산보류의 확정 원인은 **동등성 실패와 미구현 경로**, 큰 실행peak의 불확실성이다.

## 성공 기준·역할·정리

입력계보(기준1)는 round002 범위를 계승하며 실제참조/점수는미완료다. 사고신원/정상정답(2), 실제독립분할(3), 최종사고출력(4), 사고성능(5)은미충족이다. 별도검산(6)은 실패범위·실제exit·해시·원인 검산을 완료했으나 생산계산 성공으로 바꾸지 않는다. 보고/쉬운설명/다음검증(7)을 작성했고 후속감독 ACK/활성화는 HANDOFF_RECEIPT를 따른다. 학습자의 설명능력과 실제선박안전도 검증하지 않았다.

감독은codex_4269e9a1_ce56_4684_9e30_794fd12ed5b7, Run run_202dfeeb8d64다. 요청/기록된Orca launch는gpt-6.1-sol/high, E/V는각각별도실제Orca gpt-6-luna/xhigh다. provider내부 모델/effort는모두unknown이다. 내부subagent로대체하지않았다.

E는failed로settled/released·liveness exited다. V최신후속ctx_d19e5fc43cd8의 활성후속이없음을 확인하고 release했다. 응답released/closed_agent_terminal·exit0, 이어worker-list는최신V와E를exited/released로확인했다. 옛V dispatch만보고현재후속을닫지않았다. Round001 user_kept/identity_unproven창은건드리지않았다. 별도 E 늦은메일 전달실패는Run binding에 대한escalation으로보존했고 run-use 뒤 V후속이ready로시작됐으며 E계산재개를추정하지않았다.

근거: [E 보고](execution/preflight_report.md), [E 최종 영수증](execution/execution_receipt.json), [V 정적검토](audit/independent_static_review.md), [V 실패독립감사](audit/failure_001/failure_audit.md), [정리관측](integration/worker_cleanup_observation.json), [다음검증](NEXT_ROUND.md).
