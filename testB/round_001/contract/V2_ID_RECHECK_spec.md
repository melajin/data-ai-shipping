# 사용자 요청: 신구 Test B ID 교집합 직접 재검산

감독의 '새 Test B 100척과 기존 100척의 교집합0' 설명에 사용자가 다시 확인하라고 요청했다. 당신은 기존 W0 생산자와 다른 Luna xhigh 독립 검산자다. 기존 요약을 신뢰해 숫자만 재인용하지 말고 원본을 직접 읽어 결론을 확인/정정한다. 요청 모델 gpt-6-luna/xhigh 유지, 완료는 이 run_131763108c81에 worker_done.

단독 수정 소유권: testB/round_001/audit/v2_id_recheck_001/만. 다른 담당자가 함께 작업 중이다. 타인 파일·원자료·canonical·기존 캐시·제출물은 읽기전용이며 되돌리기/수정 금지. Python bytecode를 타인 폴더에 쓰지 않는다. Spreadsheets SKILL.md 및 references/read_only_qna.md를 적용하고 워크북을 편집/save/export하지 않는다.

직접 읽을 원본:
1. C:/Users/dlehs/Downloads/문제 데이터_수정_1103_v2.zip 안의 테스트셋 및 결과제출 샘플/제출샘플.xlsx (zipfile에서 작은 member만 BytesIO로 읽어 openpyxl load; 전체 추출 금지)
2. F:/문제 데이터_수정_1027/테스트셋 및 결과제출 샘플/제출샘플.xlsx
3. testB/intake/1103_v2/inspection_001/reference_02_제출샘플.xlsx (직접 ZIP member와 SHA/명부 일치 확인)
4. D:/repos/fishing-track-classification/results/work_008/scored_rows.pkl — 알려진 로컬 기존 캐시의 키만 조회, 점수·A는 재계산하지 않는다.
5. D:/repos/fishing-track-classification/results/submission_20261101/testB_submission.csv — RFID 명부만.

검산:
- 각 원본의 sheet names/order와 테스트B A1 헤더를 확인해 엉뚱한 시트·경로를 비교하지 않았는지 기록한다.
- 테스트A/테스트B의 A2:A101을 직접 읽고 값타입·행수·고유수·공란·중복을 확인한다. 원값 보존, 공백 제거 문자열 및 안전한 정수표현 정규화의 각 결과를 구분한다. ID 자리수/선행0를 임의 보정하지 않는다. 문자열/숫자 타입 때문에 같은 ID를 다르게 세지 않았는지 검사한다.
- oldB↔newB의 행별 일치수와 set 교집합·차집합, oldB↔cache keys, newB↔cache keys, oldB/newB↔기존 제출CSV 키를 각각 계산한다. oldA↔newA, oldA↔newB, oldB↔newA도 별도 표로 남겨 시트 간 이동을 확인한다. 전수 집합 결과와 원셀 주소의 추적표를 남긴다.
- 원항적 존재와 이전100척 점수캐시 존재를 혼동하지 않도록 명확히 설명한다. 가능하면 로컬 rows_test_*.parquet 캐시를 이름으로 발견하고 캐시 manifest의 원파일·검사범위를 확인한 뒤 RFID열만 청크로 읽어 새B100척의 관측 존재수를 집계한다. 없거나 부분 캐시이면 정확한 범위를 기록하고 원항적 없음으로 결론내리지 않는다. 이 보조 커버리지는 source CSV 전수 재파싱·2026학습·score 생성 없이 수행한다. 시간이 오래 들면 필수 명부 교집합 결과를 먼저 완성한다.
- 비교 전후 입력 SHA/메타 및 실제 실행 exit·환경·코드해시를 기록한다. 13GB CSV 해시나 ZIP 전체압축을 다시 반복하지 않는다. 작은 template member·작은 cache/CSV 및 사용 parquet 범위만 확인한다.

산출물: recheck_report.md(쉬운 한국어), summary.json, source_id_rows.csv 및 set_comparisons.csv, 코드·실제 stdout/stderr/exit·환경·해시. 보고는 '무엇과 무엇이0인지', '원항적에도 없다는 뜻인지', '이전 말의 확인/정정'을 먼저 답한다. W0 요약과 차이가 있으면 구체적 원인과 올바른 숫자를 제시한다. actual model을 provider 내부 관측한 척하지 말고 Orca 시작 영수증과 요청값을 구분한다.

이전 W3 timing 이슈는 이 검산에서 수정하지 않는다. W0는 metadata 수정 중이므로 그 산출물 해시변경을 원본변경으로 오인하지 말라. 원본 직접 읽기가 검산의 중심이다. 완료 시 worker_done에 핵심 교집합·원항적/캐시 범위·경로·실제 exit를 보고한다.
