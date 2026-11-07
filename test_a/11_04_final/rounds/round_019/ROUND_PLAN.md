# Round019 — deadline 생존 관찰과 종료 증거

시작 2026-11-04T22:52:11Z, 실행 마감23:14:11Z, 문서·인계 종료목표23:17:11Z. 총25분 중 마지막3분은 문서·인계다. 수신 SHA D5955B87EFAA069CA8C6AE8BB4A148486CEA408DE306EEAD436F84A710C14D92 및 accepted receipt의 세션이 현재 ORCA 세션과 일치했다. round019 디렉터리와 Python 계산이 없는 것을 확인하고 배타 디렉터리/manager claim을 생성했다.

단일 가설: 짧은 Waitfalse, 절대 단조시계 deadline 뒤 생존 관찰, cleanup 종료확인을 분리하면 round018의 timeout 관찰 공백을 해결하면서 늦은 자연종료를 성공으로 오인하지 않는다. 비교 기준은018의 Waitfalse0.4959699/관찰0.9381056/kill뒤종료0.9397325초, indeterminate 및1601년 ExitTime이다. incoming_NEXT_SESSION.md 전체와017/manager/incoming_NEXT_SESSION.md 저장입력·감사 계약을 계승한다. 변경은018 두 소스의 회차표기와 필요한 제어증거·검증뿐이다.

각 Wait 시작/길이/종료/반환, deadline 뒤 kill 전 직접 생존, bounded 종료wait, 정수코드 조회와 오류, raw ExitTime 및 유효성을 분리한다. 늦은 자연종료/경계/필수증거 unknown은 실패다. -1은 실제 조회된 정수로 보존하고0으로 고치지 않는다. 무효 ExitTime을 유효시각으로 쓰지 않는다. probe/auditor에 같은 의미를 적용하며 실제 PS classifier 반례로018 timing/생존증거유무/kill후관찰/종료wait실패/무효시각을 확인한다. RAM/소유트리 감시를 유지한다.

작성자 code/*, 독립 검토자 review/*, 관리자 나머지 파일의 단독 소유다. 작성·검토는 gpt-6-luna/xhigh/fork_turns=none 명시 요청, root+2=3≤host4/보조2≤사용자4. 추가child 금지, 타인수정 되돌림 금지. host turn_context와 요청을 분리해 기록한다. 동결ACK 목표8분, 직접해시 승인목표12분이며 독립승인 전 동적실행 금지다.

실행 상한은 smoke1회15초(4probe+auditor+정리+최종화), mock1회30초, saved-audit1회30초, 재시도0, 동시계산1이다. probe는 즉시exit0/즉시exit7/sleep1.2초 대기5초/sleep5초 대기0.5초 정리1초를 유지한다. 소스·manifest·ACK 직접해시 동결/독립승인 뒤 `manager/Invoke-ApprovedMode.ps1 -Mode smoke`, 성공시 mock, 성공시 audit. 다음 단계는 Python completed + wrapper completed + 외부exit0 + 전체상한 + 같은map을 모두 만족해야 한다. runtime 실패 뒤 수정재실행은 없다.

매 mode/probe 직전 가용RAM≥0.5GiB와 다른 계산을 확인한다.22:52:38UTC 가용5.36799GiB는 최초관찰일 뿐 재사용하지 않는다. 예상peak≤200MiB는 stdlib 소형JSON·직렬hash·PS+Python 가정이며 실측이 아니다. 부족하면 독립 문서/코드 작업 후 재확인한다. RAM대기polling/사용자process종료 금지. 소유PID+생성시각·argv·stdout/stderr·drain·tree·전후 source/map/snapshot 해시를 보존한다. TEMP/TMP/cache/output 모두019 아래다.

model0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt 역직렬화0, 원자료/이전repo/OUTER/holdout/F1 접근0, 외부전송/설치/공식제출0. head는 opaque 크기/streamingSHA만 허용한다. strict parser와 저장수치6비교/raw1e-5/prob1e-6/finite/범위/행합/argmax 및 기존 provenance 계약을 보존한다. tensor 재계산이 아니다. numeric/provenance/current source와 역사015wrapper=false/010gate=false를 분리한다.

기술목표는 프로세스 제어 및 저장감사 관문 검증이다. 학습목표는 짧은Wait와 global deadline, 관찰과 실제종료, 종료코드와 종료시각, 저장감사와 F1을 구분하는 것이다. 설명 질문: 왜 kill 이후 exit 관찰이 kill 이전 생존을 증명하지 못하는가? 왜 저장된 수치 검산이 모델 재현이나 독립 성능 평가가 아닌가? 학습자 이해와 하드웨어는 미평가다.

모든 관문 성공시에만020의 사전선택 M4-a 전체estimator 저장재로드 새 계획을 검토한다. 현재통합/b·CE선택 금지. 실패시 계층·증거·변경된 최소가설만 인계한다. 기존 개발OUTER5897 micro0.5930133966423605/macro0.5252719738966167와 미채택탐색0.5933525521451586, 독립/공식null 유지. 완료REPORT/STATUS(current_round019,handoff.ready=true)/LEDGER/NEXT 저장 후 새 Astra high 인계수락 확인즉시 종료한다.
