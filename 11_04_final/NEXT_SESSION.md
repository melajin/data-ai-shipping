# 다음 Astra high 관리자 — Round017: 동결 제어 결함 최소수정 후 모델 없는 저장 감사

먼저 AGENTS.md, CYCLE_PROTOCOL.md, STATUS.json, 이 문서와 round016 ROUND_PLAN/ROUND_REPORT, code/candidate_sources.json·author_freeze_ack.json, review/SOURCE_REVIEW.md·FINAL_REVIEW.md, manager/execution_closeout.json·DRAFT_FINDINGS.md·host_turn_evidence.json을 읽는다. 현재 수신 session/launch receipt/SHA를 확인하고 중복관리자·claim이 있으면 중복 실행하지 않는다. Round016은 코드 작성과 정적 수정만 했다. smoke/mock/audit/model 각0회, 소스 독립승인없음. 문법검사 통과는 실행통과가 아니다. round015 wrapper=false와 round010 gate=false는 영구보존한다.

## 다음 단일 가설과 변경 범위

가설: 동결 round016 실행기의 deadline/종료관찰 순서와 Windows CIM 생성시각 처리를 최소 수정하면, 모델 재실행 없이 정상/실제timeout/저장감사를 유한 검증할 수 있다. 새 runner를 처음부터 재설계하지 않는다. round016은 읽기전용 보존하고 round017/code에 복사한다. 회차 표기·경로는 016→017만 바꾸되 역사입력은 round015/round010 그대로다. candidate manifest와 ACK/승인map은 새 직접해시로 만든다.

필수 수정은 review/SOURCE_REVIEW 지적을 따른다. Invoke-Probe가 루프 뒤 HasExited=true이면 deadline 뒤 종료도 정상으로 취급하는 경계를 없앤다. 단조시계 경과, 종료관찰시각, Wait 반환, 종료시각·실제 deadline 도달을 분리하고 관찰된 정상종료를 소급하여 지우지 않는다. 종료가 deadline 이전인지 입증할 수 없는 경계는 정상으로 추정하지 않고 명시적 불확정/실패로 둔다. 실제 제한시간 초과 시 owned child를 중단하고 정수 OS exit를 저장한다. 합성 상태 반례로 deadline 전/후/경계 및 memory_stop을 실제 분류 함수에 입력하여 확인한다.

Get-CimInstance Win32_Process.CreationDate는 DateTime일 수 있다. DateTime과 DMTF 문자열을 구분해 UTC 정규화하고 PID+생성시각으로 소유를 확인한다. 실패를 빈 생성시각이나 tree-clear로 숨기지 않는다. root 종료 후 새/기존 descendant 잔존을 확인하며 unknown이면 실패다. 사용자 프로세스는 종료하지 않는다. 현재 코드의 다른 최종 지적도 확인하되 범위를 넓히지 않는다.

동결 원본: Python saved_m4_audit.py 47747bytes SHA9d1ea2816a382b9c8134095543d504a1f21345b1decdbeff9692c13cf11edd18; PS run_saved_m4_audit.ps1 18841bytes SHAf553e7aee06cd85acbc84cfc8a7c75a2e96f45b59c38c09837d383f5511752ac; candidate SHA43443b8628b6cb6ce831f01bbd5a823bccfadbc0b0a1525b8a2de6221f078b5a; ACK SHA45dc16fc164ae51869a2a8fcfd822d0f713296f38edd97a100e18c14c7971010. 다른 새 원인 없이 전면 재작성하지 않는다.

## 고정 유한 계획

관리자25분, 문서3분, 실행마감시작+22분. 작성·검토를 즉시 각각 gpt-6-luna/xhigh/fork_turns=none으로 배정한다. 작성자 round017/code, 검토자 review, 관리자는 계획/실행/상태/인계 단독소유. 추가child금지, 다른 수정 되돌림금지. root+2=3≤host4, 보조2≤사용자4. 요청과 실제 host turn_context를 별도 기록한다. 8분 내 최소수정 ACK 목표, 12분 내 직접해시 독립검토 목표. 승인 없는 실행금지. model0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt 역직렬화0, 실제자료/OUTER/holdout/F1/외부/설치0.

smoke process batch1회≤15초: 즉시exit0, 즉시exit7, sleep1.2초 후exit0/대기5초, sleep5초/대기0.5초/정리1초의 순차4child. 실제timeout killed exit에는 0을 요구하지 않는다. stdlib mock1회≤30초, saved-audit1회≤30초, 재시도0, 동시계산1. 각 단계 동일 approved map/live/snapshot과 이전 성공 전체 실행기 receipt를 확인한다. Python receipt 성공만으로 PS 실패를 덮지 않는다. source/map/snapshot 전후해시, 시작 전 배타 claim, PID/시각/argv/exit/stdout/stderr/drain/tree/RAM 기록. 모드 상한은 정리시간까지 포함하도록 실행 전 확정하고 실제 clock으로 지킨다. 실행 중 제어 monitor와 RAM 부족 대기 polling을 혼동하지 않는다.

독립승인 뒤 실제 경로/argv를 계획에 확정:
& './rounds/round_017/code/run_saved_m4_audit.ps1' -Mode smoke
& './rounds/round_017/code/run_saved_m4_audit.ps1' -Mode mock
& './rounds/round_017/code/run_saved_m4_audit.ps1' -Mode audit

stdlib 엄격파서는 UTF-8 BOM을 수용하되 원바이트해시 보존, 같은 바이트로 JSON/hash를 확인한다. 중복key/NaN/Infinity/누락/잘못된type/허위completed 실제 validator 거부를 mock한다. 빈 루트key를 삭제하지 않으며 PowerShell 소비용 fixed summary에 동적키를 내보내지 않는다. 실행기 오류가 남으면 claim과 실패receipt를 그대로 보존하고 재실행하지 않는다.

## 저장 입력·감사 인수조건

round015/artifacts/m4_synthetic_result.json 64851bytes SHA365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105; a head42422bytes SHAc33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0; b head42464bytes SHA8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36. 경로 prefix rounds/. 두 head는 size/streaming SHA만, load0. round015 map SHA2cede678cba53e4a92832c663bf4968b75ee63b5c1287ad25804aaf3dce59dd4; smoke receipt SHA4f9608e11d51bd70e5508ed82f746eb3c03e3319fc5e6f8da1782eff36dd9ad2; mock SHA61595d02a9297711dc47ab16569247aea0558906b7c23c58964d0e722976b2bf; synthetic SHAc6f9bc8861ffb14629cfa8ccdc84c8a0da55d3f224dc7a0ec430904b39c8affa.

receipt map/live/snapshot 직접해시와 smoke/mock historical=true, synthetic historical=false 및 childexit0/statuscompleted를 함께 검사. 수치6비교 raw≤1e-5/prob≤1e-6, finite/[0,1]/행합≤1e-6/argmax, gradient/inactive/bias/reload/upstream/hooks, 정확callcount/config/seed/shape/permutation 검사. 저장JSON 감사이며 tensor 재계산 아님. numeric_saved_checks_pass/saved_provenance_audit_pass/current_round015_source_matches와 역사round015 wrapper=false/round010 gate=false를 분리. round010 summary는 현재 코드에서 관찰해시로만 기록하며 고정digest 미요구였다는 한계도 명시한다. 과거 gate를 소급수정하지 않는다.

RAM 예상peak≤200MiB는 stdlib 작은파일/직렬hash/PS+Python 기준 가정. 각 실행·probe 직전 가용≥0.5GiB와 다른 작업을 기록한다. 과거RAM을 현재로 쓰지 않는다. 부족하면 코드/문서 먼저 후 재확인, RAM대기 polling/사용자process종료0. bytecode/tmp/cache/log/output 모두 round017 아래. 원자료F:/문제 데이터_수정_1027 및 이전repoD:/repos/fishing-track-classification은 이번 회차 접근불필요/읽기전용.

성공시에만 후속 round018에서 review/NEXT_GATE_SCOPE.md 및 round014/review/NEXT_INTEGRATION_CHECKLIST.md의 사전선택 M4-a 전체estimator 저장재로드 검토. 지금은 통합금지. head는 round015 a 고정해시, b/CE선택금지. 실패시 конкрет한 control/parser/schema/provenance/numeric 원인 및 최소후속을 작성; 무정보 모델재실행금지.

개발 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 반복노출OUTER5897, 독립/공식null, 목표0.7미달 유지. 학습목표는 deadline관찰/프로세스소유/JSON소비/저장감사와F1구분이며 이해평가미실시. 완료REPORT/STATUS(current_round=round_017,handoff.ready=true,active_workers=[])/LEDGER/NEXT 저장 후 Start-NextSession.ps1 -FromRound round_017 수락newsession+prompt전달 확인즉시 종료. 반복승인불필요. structured chat닫기지원없으면 이 완료탭만 수동닫기제한기록.
