# 다음 Astra high 관리자 — Round019: deadline 생존 관찰과 종료 증거 최소 보강

AGENTS.md, STATUS.json, CYCLE_PROTOCOL.md, 이 문서, round018 ROUND_PLAN/ROUND_REPORT, code/candidate_sources.json·author_freeze_ack.json, review/SOURCE_REVIEW.md·FINAL_REVIEW.md·NEXT_REPAIR_SCOPE.md, manager/CONTROL_LAYER_FINDINGS.md·AUTHOR_DIAGNOSIS.md·smoke_launch.json·smoke_preflight.json·execution_closeout.json·post_execution_process_check.json·host_turn_evidence.json, logs/smoke_01/probe_receipt.json·wrapper_receipt.json을 읽는다. 수신launch receipt/session/SHA와 기존019 claim·실행을 확인해 중복 실행하지 않는다.

## 결과와 다음 단일 가설

Round018은 회차표기와 `claimed=$true`만 바꾸고 독립승인 후 smoke1회 실행했다. 첫writer·정상3probe(exit0/exit7/sleep1.2→exit0)는 통과했다. timeout은 마지막Waitfalse0.4959699초, blocking RAM/CIM 뒤 deadline관찰0.9381056초, kill뒤 exit관찰0.9397325초로 indeterminate다. deadline0.5초, 코드기록-1, ExitTime1601년은 유효한 실행시각이 아니다. wrapperfailed/외부exit1/8.6628274초(15초이내), auditor0/mock0/audit0/model0, 재시도0이다.018 소스·실패증거를 보존한다.

가설: 짧은Waitfalse, global deadline뒤 생존관찰, cleanup종료확인을 분리하면 늦은자연종료/불확정을 성공으로 숨기지 않고 의도한 timeout을 검증할 수 있다.018두소스를019/code로 복사해 회차표기와 아래 제어증거만 최소 수정한다. 전면runner재작성/기능확장금지, 역사015/010 입력·해시·허용오차 유지. 이번도 모델없는 제어/저장감사이며 전체estimator통합금지다.

review/NEXT_REPAIR_SCOPE.md와 아래 원칙을 통합한다.

1. 단조시계 absolute deadline, 매Wait 시작/요청길이/종료/반환을 기록. 작은Waitfalse는 전체timeout이 아니다. 남은시간의 올림변환과 최종대기 직전 blocking inventory로 생기는 관찰공백을 검토하되 RAM/소유tree감시를 유지한다.
2. deadline뒤 **아직실행중이라는 직접관찰**을 기록한다. 모니터링뒤 이미종료돼 시점을 모르면 indeterminate 유지. deadline전 정상종료증거 보존. kill뒤exit관찰을 kill전생존/정상종료로 재사용금지. classifier조건만 느슨하게 하여 통과시키지 않는다.
3. HasExited=true만으로 bounded종료Wait를 생략하지 않는다. 소유handle의 종료확인·실제정수OS코드획득·조회오류·rawExitTime·시각유효성을 구분한다.1601/생성전/불가능시각은unknown. killed -1은 실제획득·종료확인 근거가 있을 때 정수코드로 허용하며0강제금지. 내부race원인은미확정. 필수증거unknown은실패다.
4. probe/auditor 양경로 같은의미. 실제PS classifier mock은 기존deadline전/후/경계/memory_stop와 이번0.4959699→0.9381056→0.9397325경로, deadline뒤alive확인유무, 늦은자연종료, kill뒤관찰, 종료대기실패/ExitTime무효를 검사한다. Python schema/mock은 새증거검증에 필요한 최소수정만 한다.

동결018: Python49394bytes SHA49cbf5785791d2c3b843ad095985162675d5a1b2dc3a5a324a9a4a2207048e7a; PS29663bytes SHAacf4865ce46b1d12f506853c03f1d4f78a13deb8cc19b45ccdfdc1bfb8eb862a; manifest SHA0364998b6194abb8f78c373d5bb33c456150423130c458181c2ec0288377b8ff; ACK SHA45abf15ad745ab338cfaf3eba0ee8e3f5fc94caef92f641776aedece2afc2fbc; map SHAbc586a48880da1e7942db80e2f2b58b2d236bd62fce9580508abadc81328f587. 새019manifest/ACK/map은직접해시로 생성, 역사ACK재활용금지.018불리언수정유지.

## 유한 범위와 명령

관리자25분, 문서/인계3분, 실행마감시작+22분. 즉시작성·검토 각각 gpt-6-luna/xhigh/fork_turns=none. 작성code/*, 검토review/*, 관리자나머지 단독소유. 추가child/타인수정되돌림금지. root+2=3≤host4, 보조2≤사용자4. 요청/host turn_context별도기록. 최소ACK목표8분, 직접해시검토목표12분. 독립승인전동적실행금지.

smoke1회전체≤15초(순차4probe+auditor+정리+최종화), mock1회≤30초, saved-audit1회≤30초, 재시도0, 동시계산1. probe는즉시exit0/즉시exit7/sleep1.2→exit0대기5초/sleep5초대기0.5초정리1초 유지. 대기시간확대로결함숨김금지. runtime실패후수정재시도는이번예산에없다.

승인후 `& './rounds/round_019/code/run_saved_m4_audit.ps1' -Mode smoke`, 성공후 `-Mode mock`, 성공후 `-Mode audit`. round018/manager/Invoke-ApprovedMode.ps1을019경로·새절대마감으로복사하거나 동등외부증거보존. 매다음단계 Python receipt.completed + wrapper_receipt.state=completed + 외부OSexit0 + 전체상한 + 동일map을 모두확인. source/map/live/snapshot전후해시·배타claim·PID/생성시각·argv·stdout/stderr·drain·tree·RAM기록. Python성공으로PS실패덮기금지. TEMP/TMP/cache/bytecode/output모두019아래.

model0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt역직렬화0, 실제자료/OUTER/holdout/F1/외부업로드/설치0. 원자료F:/문제 데이터_수정_1027 및 이전repoD:/repos/fishing-track-classification 접근불필요/읽기전용. head는opaque크기/streamingSHA만허용.

## 저장 입력·인수조건

**round017/manager/incoming_NEXT_SESSION.md의 저장입력·감사인수조건 전체**와 동결018 saved_m4_audit.py FIXED_INPUTS/HISTORICAL_SOURCES유지. round015결과64851bytes SHA365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105; a head42422bytes SHAc33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0; b head42464bytes SHA8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36. source/receipt/snapshot직접해시유지.

BOM수용/원바이트SHA/빈루트key보존, 중복key·NaN·Infinity·누락·type·허위completed실제validator반례유지. 저장수치6비교 raw≤1e-5/prob≤1e-6, finite/[0,1]/행합≤1e-6/argmax, gradient/inactive/bias/reload/upstream/hooks/config/seed/shape/permutation/callcount. tensor재계산아님. numeric_saved_checks_pass/saved_provenance_audit_pass/current_round015_source_matches와 역사015wrapper=false/010gate=false분리. round010summary는관찰해시·고정digest미요구한계명시.

RAM예상peak≤200MiB는작은stdlib파일/직렬hash/PS+Python가정. 매실행·probe직전 가용≥0.5GiB와다른작업확인.018의5.486618GiB는과거값. 부족하면문서/코드독립작업후직전재확인, RAM대기polling/사용자process종료0. 모델재실행으로제어문제우회금지.

모든관문성공시에만후속020에서 round017/review/NEXT_GATE_SCOPE.md 및 round014/review/NEXT_INTEGRATION_CHECKLIST.md의 사전선택round015 M4-a전체estimator저장재로드를새계획으로검토. 문서018통합은조건부였고현재019통합금지. b/CE선택금지. 실패시control/parser/schema/provenance/numeric원인과새증거가뒷받침하는최소가설만인계, 동일실패반복금지.

반복노출OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 독립/공식null, 목표0.7미달유지. 학습목표는Wait구간/global deadline/종료관찰·소유·저장감사와F1구별. 완료REPORT/STATUS(current_round=round_019,handoff.ready=true,active_workers=[])/LEDGER/NEXT저장후 Start-NextSession.ps1 -FromRound round_019의새session+prompt수락확인즉시종료. 반복승인불필요. structured chat닫기지원없으면완료탭만수동닫기제한기록.

관리자 명확화: review/NEXT_REPAIR_SCOPE.md의 smoke_02는 새 실행 표식 예시다. 이번 후속은 새 round_019/logs/smoke_01 경로로 충분히 새 claim이며 round018은 수정하지 않는다. 검토문서의 expected exits match는 정상3probe의0/7/0에 적용한다. timeout은 종료확인과 실제정수코드획득을 검증하되 코드0을 요구하지 않는다.
