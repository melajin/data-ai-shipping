# W0 새 입력 호환성 비교 — Luna xhigh

당신은 run_131763108c81의 감독에게 보고하는 실제 Orca worker이며 요청 모델 gpt-6-luna / effort xhigh다. 새 subagent로 대체하지 않는다. Orca 실제 orchestration 가이드를 읽고 질문은 ask, 완료는 worker_done으로 한다.

프로젝트 D:/obsidian/claude/obsidian_export/DATA AI SHIPPING. AGENTS.md, testB/USER_DIRECTIVE_20261105.md, ROUND_PROTOCOL.md, round_001/ROUND_PLAN.md, contract/path_transition.md, intake/1103_v2/inspection_001/archive_manifest.json을 읽는다. 워크북 읽기전용 비교이므로 Spreadsheets 스킬 C:/Users/dlehs/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.1030.10813/skills/spreadsheets/SKILL.md와 references/read_only_qna.md를 적용한다. 워크북을 수정·export하지 말라. 필요한 읽기 비교는 Python zipfile/XML/openpyxl로 가능하며 authoring 제한과 구분한다.

단독 수정 소유권: testB/round_001/input_compatibility/만. 다른 workers와 감독이 작업 중이므로 타인 수정은 되돌리지 말라. intake의 기존 결과·원본ZIP·구버전 원파일·canonical·기존 캐시·제출물은 읽기전용. 새 작업 루트 외 쓰기 금지.

입력:
- C:/Users/dlehs/Downloads/문제 데이터_수정_1103_v2.zip
- testB/intake/1103_v2/inspection_001/archive_manifest.json
- 같은 폴더 reference_01_26년 1~6월 어선 사고현황(테스트 데이터).xlsx 및 reference_02_제출샘플.xlsx
- 대응 구파일 경로는 manifest.entries[*].old_exact_path에서 가져온다.

작업 1: 제출샘플 신구의 시트 이름/순서/가시성, dimensions, 모든 실재 셀의 값·타입·formula·number_format·유효 스타일/폰트/정렬/채움/테두리/보호, 병합·행열크기·숨김·freeze·유효성·조건부서식·이름정의·인쇄설정을 읽기전용 비교한다. 내부 style ID만 달라진 것을 의미 서식변화로 오인하지 말라. Test B 헤더(빈 H1 포함), ID 목록·순서, 시간 예시·표시형식·결과칸 구조를 강조한다. 바이트 차이가 저장메타/XML만의 차이인지 근거를 구분한다. 셀 위치별 변경표와 의미/서식/메타 차이 요약을 작성한다. 사고 XLSX 바이트 동일은 기존 SHA 근거를 확인하되 167건 사고 매칭을 다시 실행하지 않는다.

작업 2: 12 CSV 내용 동일성. archive manifest로 짝을 고정하고 ZIP member를 청크 스트리밍 SHA256 계산, 해당 구원파일도 청크 SHA256 계산한다. 대량 추출/메모리 전체 적재 없이 순차 수행한다. 이름·헤더·크기 일치를 내용 일치로 대신하지 않는다. 파일별 SHA/크기/판정·소요시간을 보존한다. ZIP CRC 검사가 실제 끝까지 읽힐 때 완료되는지도 실제 오류와 기록한다. 원본ZIP 및 구파일 입력을 전후 해시/메타로 확인한다. 이 결과는 v2와 구파일의 바이트 호환성 증거이며 캐시 계보/코드 정확성·탐지 성능 인증은 아니다. 이미 동일한 파일을 다시 무의미하게 해시하지 않도록 한 실행 내 증거를 재사용할 수 있으나 불변 확인 범위를 정확히 명시한다.

산출물: comparison_report.md, summary.json, workbook_cell_differences.csv 또는 JSON, csv_identity.csv, manifest.json, 실행 코드·환경·stdout/stderr·실제 exit/시작종료/코드 해시. 빈 변경표에도 헤더를 남긴다. 입력 오류는 실제 실패코드·범위·미완료를 기록한다. 실제 워크북 편집·캐시 갱신·학습·예측/임계값·외부 수집·메시지·push·공식 제출은 하지 말라.

완료는 내용/구조/유효서식 차이와 CSV별 호환성의 실측 근거, 입력 불변 범위 및 실제 exit 기록이다. worker_done으로 결과·파일·실제 exit·모델/effort 요청과 Orca 런타임 영수증 한계·미해결을 감독에게 보고한다. 전체 검사 미완료면 미완료를 정직하게 보고한다.
