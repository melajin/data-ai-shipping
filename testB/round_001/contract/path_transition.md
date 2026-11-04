# Round 001 경로·버전 전환 부칙

2026-11-05 사용자 최신 지시를 인계 메시지 msg_d3797d517a55 및 msg_97727ae23e76으로 수신했다. 기존 준비 계약은 읽기전용 계보로 계승하고 새 산출물은 testB/round_001/ 아래 작성한다.

- 선행 계약: ../../../26_11_5/testb_next_experiment_20261105/contract/preparation_contract.md 및 W1_spec.md, W2_spec.md.
- 기존 산출물은 삭제·이동·덮어쓰기하지 않는다. 기존에 작성한 파일은 manifest에 경로와 해시로 연결한다.
- 신규 수정 소유권: 감독 contract/, integration/, round STATUS 및 최종 보고서; W1 linkage_review/; W2 timing/; 후속 W3 audit/.
- W1/W2는 안전한 현재 단계 경계에서 신규 쓰기 경로를 이 라운드로 전환한다. 이미 완료한 계산·파일을 단순 경로 변경 때문에 반복하지 않는다.
- 새 입력: C:/Users/dlehs/Downloads/문제 데이터_수정_1103_v2.zip. 기존 입력과 구분한다. 부모 세션이 testB/intake/1103_v2/에서 압축목록과 작은 XLSX의 구버전 비교를 담당한다. worker는 ZIP 대량 추출·별도 중복 비교를 하지 않는다.
- ZIP 비교 전에는 기존 캐시를 v2에서 생성됐거나 v2로 검증된 것으로 표시하지 않는다. XLSX가 동일하더라도 CSV·캐시까지 같다고 확대하지 않는다. 기존 자료를 사용한 결과는 legacy input으로 명시한다.
- 임계값 적합·실제자료 B/C·사고 성능 평가는 기존 감독 게이트를 유지한다. W1/W2 범위는 변경하지 않는다.
- 완료 보고는 기존과 같이 이 감독 Run run_131763108c81에 worker_done으로 보낸다. 새 위치·이미 보존된 선행 위치를 함께 명시한다.
- 이 부칙은 같은 감독의 진행 중인 Round 001에 대한 경로 전환이다. 라운드가 끝난 뒤 비교·현재 결과·후속 검증을 기록하고 새 Sol high 감독 세션을 실제 생성하여 인계 ACK 뒤 다음 라운드 소유권을 넘긴다.

부모 단독 소유: testB/ROUND_PROTOCOL.md, testB/USER_DIRECTIVE_20261105.md, testB/intake/1103_v2/. 감독 단독 소유: testB/STATUS.json, LEDGER.md, NEXT_SESSION.md, SUCCESS_CRITERIA.md 및 round_001/. 서로의 파일을 수정하지 않는다.
