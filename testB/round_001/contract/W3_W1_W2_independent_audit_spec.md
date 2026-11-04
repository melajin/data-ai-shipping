# W3: W1·W2 독립 검산 — 실제 Luna xhigh

당신은 생산 담당과 다른 실제 Orca Luna xhigh worker이며 run_131763108c81 감독에게 worker_done으로 보고한다. 모델/effort는 gpt-6-luna/xhigh를 유지한다. Orca 실제 가이드·AGENTS.md·testB/ROUND_PROTOCOL.md·SUCCESS_CRITERIA.md·round_001/ROUND_PLAN.md·기존 준비 계약을 읽는다. 구현자가 아닌 독립 검산자로 근거와 새 변경을 검증한다.

소유권: testB/round_001/audit/w1_w2_001/만 생성·수정한다. 다른 workers가 함께 작업한다. W1/W2 코드/문서/출력·공통 계약·기존 캐시·canonical·원자료·제출물은 읽기전용이며 수정/되돌리기 금지. Python import 시 dont_write_bytecode를 적용해 타인 폴더에 __pycache__도 만들지 말라. 새 v2 입력은 W0가 별도 검증 중이므로 중복 13GB 해시·대량추출·학습은 하지 않는다.

입력: testB/round_001/linkage_review/ 및 timing/의 완료 결과. 선행 감사 43+31은 완료 근거로 인수하며 전량 재검산하지 않는다. 필요한 해당 원행·요약만 독립 확인한다.

검산 범위:
1. W1 30개 사건과 우선 합집합10건이 기존 표와 정확히 대응하는지, 9조건 관계·안정1/시간확대7/다선박3·0건 신원확정 및 사용범위 unknown·정상근거 없음이 근거와 일치하는지 독립 집계한다. 사고 원행·선택 캐시의 직접 검토는 E0023 및 필요 최소 표본으로 제한하고 수치·단위·추적관계를 확인한다. 공간거리/시간 연결 잔차를 탐지 오차로 사용하지 않았는지 본다.
2. W1 입력/코드 전후 해시·최종 실제 exit0·실패시도 기록·환경을 확인한다. 파일 부재/증거 불일치는 추정 성공으로 넘기지 않는다. 로컬 조사범위를 전세계 부재나 확정 정상/신원으로 확대하지 않았는지 검토한다.
3. W2 100척 준비표의 고유 ID·순서·A 값/출처가 기존 제출 CSV와 일치하는지 확인하되 scored_rows.pkl에서 A 전량 재계산은 하지 않는다. B/C·차이칸은 실제 미계산/공란이며 사유·상태가 정직한지 확인한다. 자료부족/기준미확보를 미사고 정답으로 표시하지 않아야 한다.
4. timing_interface.py의 A 원입력 최초 최대값 동점 계약, B/C 동일 후보구간·C 통과시 B=C, NaN/시간 누락 분절·중복시각 지속시간·파라미터 출처 필수·계산불가 처리를 독립 작성 합성 사례로 검사한다. 생산자의 self_check만 다시 호출해 독립검증으로 대신하지 않는다. 실제 점수 임계값을 고르지 않는다. params가 허용하는 max_gap이 미관측 시간 연결 금지와 충돌하는지, 중복/충돌 시각 정책 및 floor 점수 처리의 미확정 한도를 구분해 보고한다.
5. W2 입력/분할 manifest·코드·readiness_report·summary·code_lineage·로그 간 정합성을 확인한다. 감독이 이미 발견한 input_split_manifest.json의 ties_and_duplicates/정렬 서술에 이전 'earliest maximum'이 남아 있는 문제가 있다. 변경 후 코드와 모든 현재 계약의 일치 여부를 확인하고 수정 필요 위치를 명시한다. 실제 split pending을 수행된 분할로 말하지 않았는지, 참조 기여95척을 점수희석으로 단정하지 않았는지 확인한다.
6. 현재 source 해시 및 근거 경로 유효성·관찰 실제 종료코드·환경·모델 요청 영수증을 확인한다. 원자료 전체·디스크 전체 불변 인증으로 확대하지 않는다. 실제자료 평가/합성 코드검사를 분리한다.

산출물: 독립 verifier 코드, audit_report.md, review.json(항목별 pass/fail/unknown 및 근거), stdout/stderr, 실제 프로세스 종료코드·환경·검사대상 전후해시. 결과가 막히면 actionable issue 목록(파일/위치/재현/영향/수정 제안)을 만든다. 생산 파일은 수정하지 않는다. blocking finding이면 verifier exit2 등 실제 코드를 보존해도 감사 task 산출 완료로 보고할 수 있으나 verification status를 passed로 만들면 안 된다. task 성공은 감사 결과를 정직하게 전달한 것이고 제품 검증 통과와 다르다.

worker_done에는 핵심 검산 결과, 발견문제/한계, 실제 exit, 파일 경로, 모델/effort 영수증을 보고한다. 이 작업은 W0 v2 비교의 독립 검산을 포함하지 않는다. W0 완료 후 감독이 별도 후속 범위를 준다.
