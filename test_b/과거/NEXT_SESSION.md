# 최신 결과 진입점 — Round011 시간·위치 비교 완료

사용자 결정으로 **lin_raw를 특징 후보로 채택**했다. 이후 시간만(T)·위치만(L)·시간+위치(TL)를 과거 이력으로 비교하는 가설을 고정하고 실제 dev 실험을 완료했다. [Round011 결과](round_011_20261105/ROUND011_실험결과보고_20261105.md), [계약](round_011_20261105/PROTOCOL.md), [독립 감사](round_011_20261105/AUDIT.md)를 우선 읽는다.

Tier0-1 60사건 중 공통 평가 가능35건/31척에서 lin_raw top-1 기대 적중률은 T0.628%, L0.486%, TL0.398%이며 동일 후보 무작위 기대0.801%다. 네 사전 비교 모두 개선 미지지다. 전체60건 중34건은 사고 ±6h에 공통 후보가 없다. 이는 고정 조건의 가용성·국소화 결과이며 표류 부재 판정이 아니다. 상세 후속 질문은 [Round011 이후 검토](round_011_20261105/NEXT_ROUND.md)를 따른다. 새 모델·2025 테스트·공식 제출은 수행하지 않았다. 기존 런타임 소유권·활성화 기록은 보존한다.

## 보존한 Round010 비교 진입점

사용자의 Round010 완료·Gemini 비교 요청에 대한 최신 결과는 [Round010 최종 보고](round_010_20261105/ROUND_REPORT.md)와 [결론별 상세 비교](round_010_20261105/ROUND010_비교및결과보고_20261105.md)다. T1·T2 상세 결론과 원자료 재계산 증거를 함께 읽는다.

lin_raw/Tier0-1을 후속 검증 후보로 유지하며, 새 모델·임계값·2025 테스트·공식 제출은 수행하지 않았다. 별도 검토자 세션 승인은 미확인이다. 다음 검증은 [Round010/NEXT_ROUND.md](round_010_20261105/NEXT_ROUND.md)를 따른다. 이 문서는 기존 세션의 소유권 이전 또는 활성화를 대신하지 않는다.

---

## 보존한 이전 런타임 인계 기록

# Test B 다음 감독 진입점 — Round005

먼저 round_004/HANDOFF_INSTRUCTIONS.md와 열거한 필수문서를 UTF-8로 전부 읽는다. ORCA_CLI_COMMAND/실제버전 skills get orchestration·orca-cli 안내/AGENTS RAM규칙을 먼저 확인한다. 토큰 testb_r004_to_r005_20261105_atomic_stream, 이전감독 codex_8df5a67b_34a4_4a72_b561_d45861870f6f다. 새감독은 자기ORCA_AGENT_SESSION_ID와 토큰으로 인수ACK를 이전감독에게 orchestration send --type handoff로 보낸 뒤 턴을 끝낸다. STATUS 소유권 변경과 명시적 활성화 메시지를 모두 받기 전 worker생성/새계산/공통문서 수정금지다. 사용자 재승인 절차가 아니다.

Round004는 제한 정수 도메인의 원본AST·독립oracle·adapter 및 실제16,384행 4회batch 비교에서 값/dtype/index라벨 일치를 확인했다. E최종exit0과 V생산gateFAIL/최종감사스크립트exit2·감사task succeeded를 구분한다. trace=None도 월별index목록을 보유했고 정상1행yield뒤unsupported에서 중단됐다. 전체단계 quarantine·atomic commit, 빈입력schema, RangeIndex/Index의 엄격동등성은 미완성이다. 전체Train domain은unknown, 실제참조/새점수/A/membership는없다. E초안4,212,389는Test총행수오류이며 V의Train6footer합3,887,069(497942/479290/657292/717294/761846/773405)으로 새계약을 고정한다.

활성화 뒤 round_004/NEXT_ROUND.md를 새round_005/에서 실행한다. E/V는각각별도실제Orca gpt-6-luna/xhigh,worker_done이다. 먼저 bounded trace/안전caller 원자성/빈schema·index계약을 수정·독립검산한다. 작은관문뒤새Train key-only전수domain검사를 검토하고 미지원은임의제외하지않고중단,필요시원본키열전체전역변환A방식으로전환한다. 원본순서/값/dtype/제외/index구멍/정렬동점/라벨/상수를 보존한다. loader뒤 모든 새경로 중첩RAM/격리/고정train-onlyfit 관문후에만 조건부참조/탐색score/A를 허용한다. Round003생산runner는stub이다.

Round002새100척46,705행 독립전수대조/26행합성은반복하지않고 초기FAIL/deltaPASS10exit0/역사44해시unknown을 보존한다. 원자료/canonical/cache/선행round읽기전용이다. 임계값/B/C/사고여부/성능/제출/실제split/사고파일개발사용/외부수집·연락/push금지. 사고신원/정상근거/개발사용/공식수식부재를후보/합의로대체하지않는다. 부족한외부근거는blocked_external_evidence로기록하고유효로컬가설은계속진행한다.

RAM작업전현재가용량/예상peak/다른작업/근거·시각기록,부족시가능작업우선·재개직전재확인,청크/순차/동시수축소우선,polling/watch/사용자process종료금지. Round004 E최신ctx_94f3ac9fe789와V최신ctx_80f1e954bee2는settled/released/exited다. 같은handle의옛dispatch와최신활성후속을혼동하지않고Round001user_kept/identity_unproven창은강제종료하지않는다. 매round보고/쉬운설명/다음실제Solhigh감독ACK/단일소유권인계를 유지한다. 요청·Orca launch설정과provider내부unknown을 구분한다.
