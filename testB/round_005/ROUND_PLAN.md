# Round005 실행 전 계획

2026-11-05 KST. 유일 감독 `codex_3420efaa_9881_48b8_b7f4_4985bdf027b2`, Run `run_6df8333350eb`. 최초 ACK `msg_36301489099a`, 이전 감독 활성화 `msg_9e2e1ac7e48e` 및 STATUS의 자신 소유권을 모두 직접 확인했다. 요청/기록된 Orca launch 설정은 gpt-6.1-sol/high, provider 내부 실제 model/effort는 unknown이다.

기술 목표는 원본 변환과 원 index를 보존하며 trace 보유량을 제한하고, 전체 입력 성공 전 결과를 격리해 실패한 단계의 부분 결과가 게시되지 않게 하는 것이다. 학습 목표는 generator yield, 최종 게시, 값 동등성, index 형식과 메모리 상한을 구분하는 것이다. 설명 질문: 앞 batch의 계산이 맞아도 뒤 batch가 실패하면 왜 전체 결과를 공개할 수 없는가?

## 계승·고정

- Round004 E최종 exit0은 제한 fixture 및 실제 월1 첫16,384행/4096batch 네 번의 값·dtype·index 라벨 일치다. V 감사 task succeeded와 최종 감사스크립트 exit2/생산gate FAIL을 구분한다. trace=None 월별 index 누적, 정상1행 yield 뒤 미지원 중단, 빈 schema 및 RangeIndex/Index 엄격차이는 미해결이다.
- Round003 단순 batch numeric 반례 실패/Eexit2와 V 실패 재현 fixture exit0/감사 succeeded, 결합16,384행 단일변환 한계를 보존한다. 생산 runner는 builder 없는 stub이다.
- Round002 새100척46,705행 전수독립대조/26행합성은 반복하지 않는다. 초기FAIL/metadata-only deltaPASS10exit0/역사44해시unknown을 보존한다.
- Train 6footer 합은3,887,069행(497942/479290/657292/717294/761846/773405). E004초안4,212,389는Test합계 오류로 채택하지 않는다. 실제 전체 Train domain은unknown이다. 실제 참조/새점수/A/membership는 없다.
- 원본 변환 순서/값/dtype/NA/제외/월·물리순서/index구멍/정렬동점/라벨/상수는 바꾸지 않는다. 사고신원·정상근거·개발사용·공식수식 부족은blocked_external_evidence이며 후보/합의로 대체하지 않는다.

## 이번 작업과 순차 관문

1. 실제 별도Orca E(gpt-6-luna/xhigh)는새 execution/만 소유한다. 004를 읽기전용으로 계승한 새 버전에서 admitted count로 offset을 전달하고, trace=None이면 index 목록을 만들지 않는다. debug도 요약/명시 상한/stream sink로 제한한다. 실제 안전 caller가 격리 scratch에 batch를 순차 저장하고 전체 성공 뒤 atomic commit한다. 전체 frame RAM buffering은 금지한다. 실패 scratch/영수증은 quarantine으로 남기고 결과/manifest를 최종 게시하지 않는다. stage/경로/Testfit/default-deny 제약을 실제 호출 전에 강제한다.
2. 작은 fixture에서 정상 뒤 unsupported/일반 예외/commit 실패/기존 최종경로/부적절 경로를 구별한다. 빈 month/전체empty의 schema·열순서·dtype와 무탈락/숫자탈락의 정확 index class를 원본 AST와 엄격 비교한다. month목록 empty의 ValueError는 보존한다. generator와 materialization의 계약을 명시한다. 단순 reset_index로 구멍을 없애지 않는다.
3. 별도 실제Orca V(gpt-6-luna/xhigh)는audit/만 소유하며 우선 정적 설계/원본 계약/독립 부정검사 계획을 작성한다. E완료 후 별도 followup에서 원본AST+독립 whole-column oracle+명시 expected+새 E경로로 직접 동적 검산한다. E코드/비교기를 oracle로 재사용하지 않는다. E의 파일은 수정하지 않는다.
4. 수정으로 실제 adapter의 경로가 달라졌으므로 필요하면 월1 첫16,384행/10열/4096batch/기존 고정 SHA 표본을 새 경로에서 재검사할 수 있다. 실제 비교 전에 선택·hash·열·행수·필요근거와 fresh RAM을 고정한다. 표본은 전수 증명이 아니다.
5. 작은 수정·독립검산·원자성·RAM 관문 뒤 감독이 새 Train key-only 전수 domain 계약을 별도 고정한다. 아직 전수scan은 금지다. unsupported를 행삭제하지 않고 전체 중단한다. 필요시 원본 키열 전체 전역변환 A방식과 새RAM계획을 검토한다.
6. 참조/새점수/A/membership는 아직 실행하지 않는다. loader 뒤 새 경로 전체 중첩 RAM/cache/closure/정렬/groupby/set/dict/KDTree/scratch/serializer 및 고정train-onlyfit/쓰기·pycache/progress 동적관문이 필요하다.

## RAM·소유권·종료 분기

07:06:49.9439301+09:00 CIM 가용5,918,468KiB/총14,480,244KiB. 이어 프로세스 표본 Orca 468.9/381.6MiB, explorer275.7MiB, codex219.6/209/186.2/184.9MiB 등이며 정확한 세션별 부하 귀속은unknown이다. E작은 fixture/선택표본 process계획512MiB, V정적검토256MiB와 각각512MiB여유 합계1,792MiB는 계획치이고 실측peak/보장값이 아니다. 근거는 텍스트 검토, 작은 합성 및 최대16,384행10열/4096batch이다. launch 및 각 메모리 작업 직전 다시 가용/예상peak/병행작업/근거/시각을 기록한다. 부족하면 가능한 작업 우선, 재개 직전 재확인, 청크/순차/동시수 축소를 우선한다. polling/watch 및 사용자process종료 금지다.

공통문서와 integration/은 감독만 소유한다. 서로의 편집을 되돌리지 않는다. 원자료/canonical/cache/선행round는읽기전용이며 신규 산출물은round005 소유권별 아래만 쓴다. 원CSV재파싱/전체objectframe 이중로딩/stockCLI/main/stage 금지. 임계값/B/C/사고여부/성능/제출/실제split/사고파일개발사용/외부수집·연락/push금지다. 실제 exit/stdout/stderr/hash/환경/실패를 보존하고worker_done으로 보고받는다. 감사에서 실패를 찾은 task완료와 생산성공을 구분한다. 이후 결과비교/쉬운설명/다음검증/실제새Solhigh감독ACK·단일소유권인계를 유지한다.
