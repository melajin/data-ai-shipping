# Round 001 최종 변경 독립검산: W0 호환성 + W2F 수정

당신은 기존 W0/W2F 생산자와 다른 Luna xhigh 독립 감사자다. gpt-6-luna/xhigh 유지, run_131763108c81에 worker_done 보고. AGENTS.md의 RAM 지시, ROUND_PROTOCOL.md, round_001/contract/timing_guard_contract.md를 읽는다. 이전 감사의 독립 결과를 필요한 범위에서 재사용한다. 원본 명부 ID0·새100척 legacy 항적 존재는 당신의 audit/v2_id_recheck_001 직접 재검산에서 이미 완료했으므로 다시 대용량 스캔하지 않는다.

소유권: testB/round_001/audit/final_001/만 생성·수정. 생산 timing/·input_compatibility/·기존 감사·계약·원본·canonical은 읽기전용이며 수정/되돌리기 금지. Python dont_write_bytecode 적용. 다른 workers의 파일을 쓰지 않는다.

1. W2F 수정 검산: timing/의 최신 interface·generator·manifest·readiness·summary·lineage와 fix_20261105_w2f/의 전후스냅샷/해시/실제 exit0·RAM확인을 읽는다. 이전 실패2(동점 계약 불일치, 미관측 시간 연결 가능)를 독립 사례로 재검산한다. >1 maxgap 거부, hour0/2 단절, 원입력 최초 최대 tie, B/C 동일구간과 C=B, NaN분절, 동일중복 추적·고유시각 지속행수, 상충중복 및 결측/유효충돌 data_conflict+A/B/C공란을 검사한다. 생산자의 selfcheck만 호출하는 것으로 대신하지 말라. 현재 manifest와 생성기를 모두 확인한다. positive floor·provider 내부 actual runtime 미확정은 여전히 미확정으로 보존한다. 14자체검사/문법검사는 합성 코드 검사이지 사고 성능이 아니다.

2. W0 호환성 독립 검산: input_compatibility/의 수정된 report·summary·manifest·csv_identity·workbook snapshots·코드·metadata_correction(실제 이름은 rg로 확인)·전후 스냅샷과 실제 exit를 확인한다. 12 CSV 짝짓기·전체 streaming SHA/EOF CRC 계산 구현·입력 경로/크기/사전후 SHA 집계가 올바른지 검토한다. 12개 행의 hash/bytes/count 합계·서로일치·기존 parse manifest에서 사용 가능한 원본SHA를 대조한다. 원본 명부 직접 재검산 결과를 재사용해 100ID교집합0·newB100/cache0·oldA/newB13·항적존재100과 일치하는지 본다.

3. W0 metadata 수정: 원래 dict와 문자열 비교로 false가 된 원시 증거가 보존됐고, 수정이 임의 true 채우기가 아니라 구조화된 before/after bytes/mtime를 같은 필드로 대조한 것인지 독립 확인한다. old14파일의 content-posthash 일치와 metadata 같음을 별개로 확인한다. artifacts hashes가 현행 파일과 맞는지 점검한다. 모델 설정 증거는 integration/runtime_receipts/W0_start.json의 Orca launch gpt-6-luna/xhigh와 provider내부 unknown을 구분한다.

4. 필요한 직접 원본 검산은 XLSX member/구원본의 셀·헤더/서식·ID변경·열너비 차이 및 CSV train1/test1 두 파일의 streaming 해시 표본까지만 한다. 이미 독립 ID검산이 완료된 부분은 재사용한다. 13GB 전체 재해시는 하지 않는다. 직접 내용 표본과 전체 저장표/코드 검토 범위를 보고서에서 명확히 구분한다. 12개 전체가 독립 재스트리밍됐다고 표현하지 않는다. 표본 전체해시가 메모리/시간상 불필요하거나 부적합하면 검사생략/대체근거를 명시하고 metadata만 보고 직접 내용확인을 했다고 하지 않는다.

5. 입력·생산파일·실행코드의 검사범위 전후해시, 환경·실제exit와 RAM 가용/예상피크를 남긴다. 소규모 검산과 필요 표본 streaming 4MiB 청크로 예상RAM128MiB 이내지만 작업 직전 현재량을 확인한다. 부족하면 다른 가벼운 항목부터 수행하고 다시 확인한다. 사용자의 메모리 지시를 실측과 추정으로 구분한다.

산출물: audit_report.md(한국어), review.json(항목별 pass/fail/unknown와 범위), 독립 verifier·로그·실제 exit·hash manifest. blocker 발견은 생산파일을 고치지 말고 정확한 위치·재현·영향을 보고한다. verifier exit2 findings는 정직한 감사 산출 완료일 수 있으나 passed로 표시하지 말라. 남은 지적이 없으면 그 범위만 passed로 보고한다. 사고 평가·실선·새2025대상점수생성·2026평가·임계값 적합은 하지 않는다.

worker_done에 수정2개 재검산 판정·v2 호환성 판정과 직접검사 범위·실제exit·남은unknown·경로를 보고한다.
