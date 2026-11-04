# Round016 — 모델 재실행 없는 종료 판정과 저장 증거 감사

시작 2026-11-04T21:50:03Z. 관리자 상한25분, 실행마감22:12:03Z, 문서/인계3분 확보. 수신 SHA와 round015 launch receipt의 현재 session 일치. round016 기존 폴더/실행 없음을 확인하고 배타 생성 claim을 저장했다.

가설: 실제 deadline과 종료 관찰을 분리하고 엄격한 stdlib JSON 판독/고정필드 요약을 사용하면 모델 재실행 없이 기존 M4 증거를 일관되게 감사할 수 있다. 입력/인수조건은 manager/incoming_NEXT_SESSION.md 전체를 본 계획의 일부로 고정한다. 이전 모델 source/result/receipt/map 수정0, checkpoint 접근0, torch/numpy/tabicl import0, .pt 역직렬화0, 실제자료/holdout/F1/외부전송/설치0. head 두 파일은 크기와 streaming SHA256만 허용한다.

실행 상한: smoke process probe batch1회≤15초, 순차4child(즉시exit0, 즉시exit7, sleep1.2초→exit0/상한5초, sleep5초/상한0.5초/정리1초). mock1회≤30초, saved-audit1회≤30초, 재시도0. 새 소스와 독립 승인map이 동일한 smoke→mock→audit 성공 순서로만 진행. source/map/snapshot 전후64자리해시, PID/정수exit/시각/실제argv/stdout/stderr/streamdrain/소유트리종료 저장. 종료관찰을 보존하며 wait1ms false만으로 timeout을 생성하지 않는다. 실제 deadline 도달 및 memory stop은 독립 판정한다. 정상종료 뒤 unexpected descendant가 있으면 실패한다.

mock 반례: 정상/실제시간초과/메모리중단 분류, 빈 root key 수용, 중복key/NaN/Infinity/누락/잘못된type/허위completed 거부, 역사false보존. audit는 고정입력 SHA/크기, receipt map/live/snapshot 실제해시와 역사 smoke/mock=true·synthetic=false 및 childexit0/statuscompleted, 6수치비교(raw≤1e-5/prob≤1e-6), finite/확률범위/행합≤1e-6/argmax, gradient/inactive/bias/reload/upstream/hooks, config/seed/shape/permutation/call counts를 검사한다. numeric_saved_checks_pass·saved_provenance_audit_pass·current_round015_source_matches와 역사 round015/010 gate false를 분리한다. 원tensor 재계산으로 주장하지 않는다.

RAM: 시작 확인21:50:42UTC 가용5.661GiB/총13.809GiB, 다른Python없음. stdlib JSON 수백KiB와 streaming hash/PS/Python의 예상peak≤200MiB는 가정. 두 보조 텍스트작업은 실행 계산과 분리. 각 child/실행 전 RAM≥0.5GiB와 다른 작업 확인. 부족시 소스/문서 후 직전 재확인, 반복 polling대기·사용자process종료0. 동시계산1.

소유: Luna 작성자 code/*, 별도 Luna 검토자 review/*, 관리자 계획/실행/상태/인계. 각 gpt-6-luna/xhigh/fork none, 추가child금지. root+2=3≤host4, 보조2≤사용자4. 작성 ACK 후 쓰기정지→검토자 직접해시 승인map→관리자 직접해시 대조→실행. 요청과 host turn_context 증거를 구분한다.

독립승인 후 고정 명령: `& ./rounds/round_016/code/run_saved_m4_audit.ps1 -Mode smoke`, 이어 `-Mode mock`, 이어 `-Mode audit`. 실제 인터페이스가 달라지면 실행 전에만 경로/argv를 부록에 확정한다.

기술목표: 제어계층과 저장증거 감사 통과. 학습목표: 유효JSON/소비자호환성, 빈루트키, child성공/실행기실패/저장검산의 구별. 이해평가·하드웨어검증은 미실시. 개발baseline0.5930133966423605, macro0.5252719738966167 및 미채택탐색0.5933525521451586 유지; 독립/공식null.

성공시 round017은 사전선택 M4-a 전체estimator 통합과 저장재로드를 별도 검토. 실패시 구체적 parser/schema/provenance/numeric/control 원인과 바뀐 가설만 후속화. 완료 REPORT/STATUS(current_round=round_016,handoff.ready=true,active_workers=[])/LEDGER/NEXT 갱신 및 fresh Astra high 수락 즉시 종료한다.
