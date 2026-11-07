# 다음 Astra high 관리자 — Round018: PowerShell 불리언 최소 수정 후 모델 없는 감사

AGENTS.md, STATUS.json, CYCLE_PROTOCOL.md, 이 문서, round017 ROUND_PLAN/ROUND_REPORT, code/candidate_sources.json·author_freeze_ack.json, review/SOURCE_REVIEW.md·FINAL_REVIEW.md, manager/smoke_launch.json·smoke_preflight.json·execution_closeout.json·host_turn_evidence.json을 먼저 읽는다. 수신launch receipt/session/SHA와 기존018 claim·실행을 확인하고 중복실행하지 않는다.

Round017은 소스 승인 뒤 smoke wrapper1회만 시도했고 첫 writer에서 OSexit1/3.6515994초로 실패했다. probe child0/auditor0/mock0/audit0/model0이다. PS `Save-WrapperReceipt` 78행의 `claimed=true`가 bareword 명령 true 호출로 평가돼 CommandNotFoundException을 일으켰다. 올바른 값은 `$true`다. catch도 같은 writer를 호출해 wrapper_receipt가 없으나 manager/smoke_stderr.txt·smoke_launch.json 및 logs/smoke_01/execution.claim은 보존됐다. 문법검사는 유효 명령 표현식을 허용하므로 이 실행 오류를 못 잡았다.

## 단일 가설과 변경

동결017 두 소스를018/code로 복사하고 round_017/round017 표기만018로 변경한 뒤 `claimed=true` 한 곳을 `claimed=$true`로 고치면 기존 model-zero 관문을 실행할 수 있다는 가설이다. 역사015/010 입력과 해시·허용오차 유지. 원본017 수정/재실행금지. 새 runner 재설계금지. 예상 외 diff는 근거를 남긴다. 유사 bareword true/false/null을 정적으로 확인하고 실제 smoke 첫 writer로 검증한다. 새 원인 없이 기능확장/전면재작성하지 않는다.

동결017: Python49394bytes SHA8ca9be725be25a6d4e80d43a17a82341ef78a94ea33115ff8d3bfef10ce4b227; PS29662bytes SHAfba54fd84873430039348f8d15a6660655126df7bc19ed2bdde8f4c71c7de720; manifest SHAaff522305a7a1d8b0215caa598eaecbe3fc4596060c7afa335ee8fb5c1a29449; ACK SHAfbde4e6b3426ee3e399a82aa35e1108fc9ef388d73e4eab4c7c7f8ee4269652b; map SHA9d20b92bf696b7d6d2003c9bd34bb4105f8fd6ebc4113e357f94f5595e100fe9. 새018 manifest/ACK/map은 직접해시로 만든다. stale 복사ACK를 새freeze로 쓰지 않는다.

## 유한 계획

관리자20분, 문서·인계3분, 실행마감시작+17분. 즉시 작성·검토 각각 gpt-6-luna/xhigh/fork_turns=none 배정. 작성code/*, 검토review/*, 관리자나머지 단독소유. 추가child/타인수정되돌림금지. root+2=3≤host4, 보조2≤사용자4. 요청과 host turn_context 증거 구분. 최소수정ACK목표3분, 직접해시검토목표6분. 독립승인 전 동적실행금지.

smoke1회 전체≤15초(순차4probe+auditor+정리+최종화), mock1회≤30초, saved-audit1회≤30초, 재시도0, 동시계산1. smoke: 즉시exit0, 즉시exit7, sleep1.2초→exit0/대기5초, sleep5초/대기0.5초/정리1초. killed timeout은0이 아닌 정수OS exit도 허용. monotonic deadline/관찰/Wait/OS exit/streamdrain/소유트리 잔존을 구분하고 unknown은 실패로 남긴다. 승인map/live/snapshot 전후해시와 시작 전 배타claim 보존. 실패하면 재실행하지 않는다.

승인 후 명령: `& './rounds/round_018/code/run_saved_m4_audit.ps1' -Mode smoke`, 성공후 `-Mode mock`, 성공후 `-Mode audit`. round017/manager/Invoke-ApprovedMode.ps1 예시는018 경로와 절대마감을 새계획에 맞춰 복사하거나 동등한 외부증거를 남긴다. 각 다음단계 전 Python receipt.completed, wrapper_receipt.state=completed, 외부OS exit0, 전체상한, 같은map을 모두 확인. Python성공으로 PS실패를 덮지 않는다. TEMP/TMP/cache/bytecode/stdout/stderr/output 모두018 아래. 실제argv/PID/시각/exit/RAM기록.

model0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt역직렬화0, 실제자료/OUTER/holdout/F1/외부/설치0. 원자료 F:/문제 데이터_수정_1027와 이전repo D:/repos/fishing-track-classification 접근불필요/읽기전용. head는 opaque size/streaming SHA만 허용.

## 입력과 판정

입력별 고정크기/SHA·strict parser·저장수치 조건은 **round017/manager/incoming_NEXT_SESSION.md의 저장 입력·감사 인수조건 전체**와 동결 saved_m4_audit.py의 FIXED_INPUTS/HISTORICAL_SOURCES를 그대로 적용한다. round015 결과64851bytes SHA365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105, a head42422bytes SHAc33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0, b head42464bytes SHA8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36. source/receipt/snapshot 직접해시를 검사한다.

BOM수용/원바이트SHA/빈루트key보존 및 중복key·NaN·Infinity·누락·type·허위completed 실제validator 반례 유지. 실제PS classifier의 deadline전/후/경계/memory_stop 반례 유지. 저장수치6비교 raw≤1e-5/prob≤1e-6, finite/[0,1]/행합≤1e-6/argmax, gradient/inactive/bias/reload/upstream/hooks/config/seed/shape/permutation/callcount 확인. tensor재계산 아님. numeric_saved_checks_pass/saved_provenance_audit_pass/current_round015_source_matches와 역사015wrapper=false/010gate=false 분리. round010summary는 관찰해시이고 고정digest 미요구 한계 명시.

RAM 예상peak≤200MiB는 작은 stdlib파일/직렬해시/PS+Python 가정. 각 실행·probe 직전 가용≥0.5GiB와 다른작업 확인.017 실행전5.51049GiB는 과거값. 부족하면 문서/코드 작업 후 직전재확인, RAM대기polling/사용자process종료0. 모델재실행으로 문제를 우회하지 않는다.

모든 관문 성공시에만 후속019에서 round017/review/NEXT_GATE_SCOPE.md 및 round014/review/NEXT_INTEGRATION_CHECKLIST.md의 사전선택 M4-a 전체estimator 저장재로드를 별도계획한다. 문서의018통합은 조건부였으며 이번실패로018통합금지. b/CE선택금지. 실패시 구체적 control/parser/schema/provenance/numeric 원인과 최소후속만 기록한다.

반복노출OUTER5897, baseline micro0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 독립/공식null, 목표0.7미달 유지. 학습목표는 문법과 실행 의미·프로세스 소유·저장감사와F1 구별. 완료REPORT/STATUS(current_round=round_018,handoff.ready=true,active_workers=[])/LEDGER/NEXT 저장후 Start-NextSession.ps1 -FromRound round_018 수락newsession+prompt전달 확인즉시종료. 반복승인불필요. structured chat닫기지원없으면 완료탭만 수동닫기제한 기록.
