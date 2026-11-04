# Round017 — 종료 관찰 최소 수정과 저장 감사

시작 2026-11-04T22:14:20Z. 관리자 25분, 실행마감 22:36:20Z, 종료목표 22:39:20Z. 문서·인계 3분을 확보한다. incoming_NEXT_SESSION.md의 입력·검증 조건 전체를 본 계획의 일부로 동결한다. 수신 문서 SHA256과 launch receipt의 session ID가 현재 세션과 일치했다. manager/manager_claim.json을 배타 생성했다.

가설: round016 실행기의 deadline/종료관찰과 CIM 생성시각 처리를 최소 수정하면 모델 재실행 없이 정상 종료, 실제 timeout, 저장 감사를 구분할 수 있다. round016과 역사 round015/010은 변경하지 않는다. 작성자는 code/*, 검토자는 review/*, 관리자는 나머지 계획·실행·상태·인계를 단독 소유한다. 별도 Luna xhigh 두 명, fork none, 추가 child 금지. root+2=3, 호스트 총 슬롯4 및 사용자 보조상한4 준수. 요청과 host turn_context 증거를 구분한다.

상한: smoke 1회(순차4child 포함 전체15초), mock 1회 전체30초, audit 1회 전체30초, 재시도0, 동시 계산1. 정리시간 포함. smoke: 즉시exit0, 즉시exit7, sleep1.2초→exit0/대기5초, sleep5초/대기0.5초/정리1초. killed timeout은 정수 OS 종료코드를 요구하되0을 요구하지 않는다. 각 모드에서 승인map/live/snapshot 전후해시, 배타 claim, PID+생성시각, argv, 단조시계 경과, deadline/종료관찰/Wait 결과, 스트림 drain, 소유트리 잔존, RAM을 남긴다. 이전 전체 실행기 성공과 동일 소스map 없이는 다음 모드로 진행하지 않는다. 소스 승인 전에는 동적 실행하지 않는다.

mock는 실제 분류 함수에 deadline 이전/이후/불확정 경계 및 memory_stop을 입력한다. 실제 strict validator로 BOM/빈루트key를 수용하고 중복key/NaN/Infinity/누락/type/허위completed를 거부한다. audit는 원바이트와 고정 JSON/receipt/map/live/snapshot 해시, 저장 수치6비교(raw≤1e-5/prob≤1e-6), finite/범위/행합/argmax, gradient/inactive/bias/reload/upstream/hooks/config/seed/shape/permutation/callcount를 확인한다. 과거 wrapper=false, round010 gate=false는 보존하며 round010 summary digest는 관찰값이라는 한계를 명시한다.

고정 명령: `& './rounds/round_017/code/run_saved_m4_audit.ps1' -Mode smoke`, 성공 후 `-Mode mock`, 성공 후 `-Mode audit`. 관리자 실행 stdout/stderr와 exit를 별도 보존한다. 실패하면 해당 claim/receipt를 보존하고 반복하지 않는다. 동적 실행 전 실제 승인 소스와 호출 인터페이스를 확인해 부록에 기록한다.

RAM 시작22:14:49UTC 5.200GiB. 예상peak≤200MiB는 작은 stdlib JSON/직렬해시/PS+Python 기반 가정이며 실측이 아니다. 두 보조는 텍스트 작업만 한다. 각 실행과 probe 직전 가용≥0.5GiB 및 다른 작업을 확인한다. 부족하면 문서/소스 작업 뒤 재확인한다. RAM대기 polling과 사용자process종료는 하지 않는다. 실행 중 제어 감시는 별개다.

model0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt 역직렬화0, 실제자료/OUTER/holdout/F1/외부/설치0. 저장 head 두 파일은 opaque bytes의 크기와 streaming SHA만 허용한다. bytecode/tmp/cache/log/output은 round017 아래. 원자료와 이전repo는 이번 접근 불필요.

기술 목표는 제어/저장감사 관문 완료이며 학습 목표는 종료관찰·시한·프로세스 소유·JSON소비·저장검산과 새 성능평가의 차이를 설명하는 것이다. 이해평가와 하드웨어검증은 미실시. 반복노출 OUTER5897, baseline micro0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 독립/공식null 유지.

성공시에만 round018의 사전선택 M4-a 전체estimator 저장/재로드 검토로 진행한다. 이번 통합은 금지한다. 실패하면 구체적인 control/parser/schema/provenance/numeric 원인과 최소수정 가설을 인계한다. 완료시 REPORT/STATUS(current_round=round_017,handoff.ready=true)/LEDGER/NEXT를 저장하고 fresh Astra high 전달 수락 후 종료한다.
