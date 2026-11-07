# Round 011 실행 전 계약

시작 2026-11-04T20:04:05Z, 관리자 마감 20:24:05Z(20분). 인계 SHA256 42435C4779C85D4BCC447EC684304EF8DAE7D7BCFE82107EBEF32717B73C96DC 일치. 수신 Orca 세션 codex_224a9fbc_58cf_44d2_8dc9_d56b1d8641d0. 이전 관리자는 done이며 현재 회차 중복 실행 증거 없음. 별도 Test B 관리자는 본 회차와 무관하다.

가설: 저장 실행사본과 live 원본을 따로 검증하면 round010의 수치 재현 통과와 동결 실패를 모순 없이 재구성할 수 있다. 소스 계약으로 다음 M4의 실제로 미확인인 gradient/병합 경계를 좁힌다.

- 모델 load/fit/predict/forward/학습/F1 0. raw/NPZ/reference/OUTER/holdout 읽기 0. 저장 JSON의 2×4 확률과 소스·메타데이터만 읽는다. checkpoint 재해시도 0.
- stdlib mock 최초1회≤30초, 결함 수정 시 최대1회 추가. 실제 저장기록 검산1회≤30초. mock 실패가 지속되면 실검산 미실행으로 남긴다.
- 실행 전 확정: Windows venv redirector 하위 프로세스를 피하기 위해 pyvenv.cfg가 가리키는 동일 기반 Python3.12.14 실행파일 `C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`를 직접 사용한다. `-B -S`로 bytecode/site startup을 비활성화한다. stdlib만 사용하므로 모델 환경 차이는 없으며 기존 venv를 변경하지 않는다. 소스 승인 전 변경이며 아직 실행0이다.
- 큰 계산 동시0; stdlib 예상 peak≤100MiB(작은 JSON/1MiB 스트리밍 해시 근거), 문서작업2명 추가 로컬 메모리 추정≤200MiB. 초기 가용4.2701GiB/전체13.8094GiB, Python 계산 프로세스0. 실행 직전 재확인, 가용<0.5GiB면 작은 검산도 보류하고 문서 후 재확인. 수치는 가정이며 측정 최대값과 구분한다.
- 작성자 Luna xhigh: code/*만. 검토자 Luna xhigh: review/*만. 관리자: 계획/실행/logs/artifacts/m4_contract/공유 상태. 총 root+2보조=3슬롯≤호스트4; 사용자 보조상한4. 모든 신규 출력은 작업루트 내부.
- 판정: clean mock은 사본·live·현재소스관문 true, drift mock은 사본 true/live false/현재소스관문 false. 두 fixture 모두 과거 round010 실패 이력을 담고 있으므로 historical 전체관문 false는 복원 후에도 유지한다(실행 전 fixture 의미 명시). 실제 저장기록은 approved 사본 보존, live wrapper mismatch, numeric true, 과거 전체 false를 독립 필드로 재검산. 검산 프로그램 정상종료와 과거 모델 전체관문 성공을 혼동하지 않는다.
- 승인 전 작성자는 candidate 선언 후 쓰기 중지. 검토자만 승인 map 작성. 승인 후 코드 수정 금지; 필요하면 실행 전 승인 취소→새 버전→재검토·mock. 실행 중 변경은 실패로 보존하며 사후 복원/manifest 수정 금지. 이 회차 과거자료 수정0.

기술 목표: 출처 검산·동결절차·소스 근거 M4 계약. 학습 목표: 수치정확성, 코드 출처와 성능평가가 서로 다른 관문임을 설명한다. 학습자 이해/장치 검증은 측정하지 않는다.

완료 산출: audit JSON, mock 로그와 독립 검토, FREEZE_PROTOCOL.md, M4_CONTRACT.md, ROUND_REPORT.md 및 STATUS/LEDGER/NEXT_SESSION 갱신. 성능은 기존 개발 baseline0.5930133966423605, 미채택 탐색최고0.5933525521451586 유지; 독립·공식 null. 이후 실행가능한 유한 tiny 합성 관문만 fresh Astra high에 인계한다.
