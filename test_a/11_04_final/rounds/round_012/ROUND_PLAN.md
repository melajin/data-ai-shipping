# Round012 실행 전 계약

시작 2026-11-04T20:25:00Z, 관리자 마감20:45:00Z. 계산과 코드 변경은20:42:00Z 이전 종료하며 문서/인계3분을 확보한다. 인계SHA B991AA5BD7B1AE8D5F017AB7687AD8E7934B81C3AEFB54CE701E2E198F06766D 및 수신session 일치. 이전 관리자 done, 동일회차 다른 관리자 없음. 별도 Test B 작업자는 무관하며 자원경쟁 가능성만 기록한다.

가설: Start-Process 대신 직접 ProcessStartInfo/Process를 생성하고 핸들을 유지하면 빠르게 종료하는 자식의 정수 종료코드를 얻을 수 있다. stdout/stderr 동시 비동기 읽기로 파이프 교착을 피한다. 역사 실패와 현재 출처 검산을 분리한다.

- process smoke1회, exit0/exit7 자식 각1개 순차, 전체10초. 실패시 mock/audit 금지, 같은 smoke 재시도0.
- fixture mock 최초1회≤30초(계산28+정리2); 결함수정/새승인 후 최대1회 추가. 성공 후 추가mock 금지.
- 실제 저장기록 audit1회≤30초, 재시도0. smoke+exact-map mock이 모두 성공해야 실행한다.
- 모델/checkpoint load/fit/predict/forward/backward/F1/NPZ/reference/raw/OUTER/holdout 읽기/설치/외부전송/유료0. 기존 저장JSON 2×4확률과 소스·메타데이터만. checkpoint/NPZ 재해시0. SHA는1MiB streaming.
- base Python3.12 경로 C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B -S. stdlib only. 원자료/이전repo/과거회차/venv 읽기전용, 모든 신규출력round012(공유 STATUS/LEDGER/NEXT 및 인계receipt 예외).
- round012_author Luna/xhigh/forknone: code/*와 runner 단독소유. round012_reviewer Luna/xhigh/forknone: review/* 단독소유. 관리자는 계획/실행/로그/산출/공유상태. root+2=3슬롯≤host4, 보조2≤사용자4. 타인변경 되돌림금지.
- 작성자 candidate SHA/쓰기중지 ACK → 검토자 독립소스검토·직접해시 승인map → 관리자 실행. 승인 뒤 수정금지. 변경 필요시 승인취소 후 재검토. mock와audit 동일승인map, 새claim, live+snapshot 전후검사. 승인map도 전후불변. 과거기록 수정이나 사후복원 금지.
- 초기RAM4.1446GiB(20:26:06UTC), Python0. stdlib 예상peak100MiB와 작업자문서overhead200MiB는 계획가정, 실측이 아님. 각 실행 직전RAM/다른작업 확인, 가용<0.5GiB이면 소스/문서 다른작업 후 직전재확인. 반복RAM polling 및 사용자process종료금지.
- smoke 판정: 정수exit0/7, 각각 소유종료/잔존없음, stdout/stderr 예상문자, 시간상한. mock 판정: 2fixture 성공, exit0, completed true, 소스전후해시일치, 소유종료. audit 판정: 프로그램exit0/완료와 역사모델관문을 구분. snapshot true/live drift false/current gate false/numeric true/audit integrity true/historical false가 예상이다. 불일치는 기록하고 성공으로 강제하지 않는다.

기술목표: 종료영수증 수정과 출처 검산 완료. 학습목표: 테스트OK, 프로세스exit0, 수치재현, 현재소스관문, 역사전체관문의 차이를 설명. 학습자 이해달성/실제장치검증은 미평가. 성능값은 기존 개발baseline0.5930133966423605/macro0.5252719738966167, 미채택 탐색0.5933525521451586이며 새점수0, 독립/공식null.

성공하면 기존 round011 M4_CONTRACT와 독립 M4_REVIEW를 근거로 다음 fresh회차 tiny 합성 head검증을 실행 가능하게 인계한다. 실패하면 새 원인/유한 수정안을 인계한다. 완료시 REPORT/STATUS/LEDGER/NEXT 갱신, current_round=round_012,handoff.ready=true,active_workers=[]; Start-NextSession -FromRound round_012 수락확인 즉시 이관리자 중지.
