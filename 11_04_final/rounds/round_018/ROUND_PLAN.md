# Round018 — PowerShell 상수 최소 수정 후 모델 없는 감사

시작 2026-11-04T22:38:50Z. 관리자 20분, 동적 실행 마감 22:55:50Z, 문서·인계 종료목표 22:58:50Z. incoming_NEXT_SESSION.md 및 round017/manager/incoming_NEXT_SESSION.md의 저장 입력·감사 인수조건 전체를 동결한다. 수신 SHA256 02D157D691A1FA67ECE0662710615AA94133D55889584D3A32B7B2132B742B3F와 round017 launch receipt의 수신 session이 현재 환경과 일치했다. 기존 round018 폴더/실행 흔적이 없었고 배타 manager_claim.json을 생성했다.

가설은 동결017 두 소스의 회차 표기와 `claimed=true` 한 곳만 `claimed=$true`로 바꾸면 model-zero 관문을 실행할 수 있다는 것이다. 비교 기준은 직전 첫 receipt writer 실패다. 역사015/010 입력·해시·허용오차는 유지한다. 새 runner 재설계·역사파일 수정·재실행은 하지 않는다. 유사 bareword 상수를 정적으로 확인하고 첫 실제 writer를 smoke에서 확인한다. 작성자 code/*, 별도 검토자 review/*, 관리자 나머지 파일 단독소유다. Luna xhigh 두 명, fork none, 추가 child 금지. root+2=3≤host4, 보조2≤사용자4. 요청과 host turn_context 증거는 별도로 기록한다.

유한 상한: smoke1회 전체15초(즉시exit0, 즉시exit7, sleep1.2초/대기5초, sleep5초/대기0.5초/정리1초의 순차4probe 및 auditor·정리·최종화 포함), mock1회30초, saved-audit1회30초, 재시도0, 동시계산1. 소스독립승인 후 smoke→mock→audit 순으로 실행한다. 이전 Python receipt.completed, wrapper.state=completed, 외부 OS exit0, 전체 시간 상한, 같은 승인map을 모두 통과해야 다음 단계에 진입한다. unknown은 실패다. PID+생성시각·argv·deadline·종료관찰·Wait·OS exit·stream drain·소유트리 잔존·전후해시·실행 전 배타 claim을 보존한다.

명령은 `& './rounds/round_018/code/run_saved_m4_audit.ps1' -Mode smoke`, 성공 후 `-Mode mock`, 성공 후 `-Mode audit`다. round017 manager/Invoke-ApprovedMode.ps1을018 경로와 새 시작마감으로 복사하여 외부 stdout/stderr/OS exit/시간/RAM을 기록한다. 정리 포함 상한을 지키고 실패한 mode는 다시 실행하지 않는다.

모델0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt 역직렬화0, 실제자료/OUTER/holdout/F1/외부/설치0. head는 opaque 크기와 streaming SHA만 허용한다. 모든 cache/temp/bytecode/output은018 아래다. 원자료와 이전repo 접근은 불필요하다.

strict parser BOM·원바이트SHA·빈루트key, duplicate/NaN/Infinity/missing/type/false-completed 반례, 실제 PS classifier의 deadline 전후/경계/memory_stop 반례를 유지한다. 저장 수치6비교 raw≤1e-5/prob≤1e-6, finite/범위/행합≤1e-6/argmax, gradient/inactive/bias/reload/upstream/hooks/config/seed/shape/permutation/callcount를 검사한다. 이는 tensor 재계산이 아니다. numeric/provenance/current-source 판정과 역사015wrapper=false/010gate=false를 분리한다. round010summary 해시는 관찰값인 한계를 명시한다.

첫 RAM 확인22:39UTC 가용5.231GiB, 다른 본회차 계산없음. 예상peak≤200MiB는 stdlib 작은JSON/직렬hash/PS+Python에 대한 가정이지 실측이 아니다. 매 mode·probe 직전 가용≥0.5GiB와 다른 계산 확인. 부족하면 문서·코드 작업 후 재확인하며 RAM대기 polling/사용자process종료는 하지 않는다.

기술 목표는 첫 writer 및 프로세스/저장감사 관문 검증, 학습 목표는 문법과 실행 의미·소유프로세스·저장감사와 F1의 차이를 설명하는 것이다. 이해평가와 하드웨어검증은 미실시. 반복노출 개발OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 독립/공식null을 유지한다.

모든 관문 성공시에만 다음019에서 사전선택 M4-a 전체estimator 저장재로드를 별도 계획한다. b/CE 선택금지. 실패시 구체적 control/parser/schema/provenance/numeric 원인과 최소후속을 남긴다. REPORT/STATUS(current_round=round_018,handoff.ready=true)/LEDGER/NEXT 저장 후 새 Astra high 인계수락 확인 즉시 이 관리자를 종료한다.
