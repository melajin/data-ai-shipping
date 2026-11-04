# W2F: 독립 검산 지적의 한정 수정

실제 Orca gpt-6-luna/xhigh worker로서 감독 run_131763108c81에 worker_done 보고한다. AGENTS.md(새 RAM 규칙 포함), round_001/contract/timing_guard_contract.md, audit/w1_w2_001/audit_report.md 및 기존 preparation_contract/path_transition을 읽는다.

단독 수정 소유권은 testB/round_001/timing/다. 이전 W2는 완료했고 당신에게 이후 수정 소유권을 넘긴다. 다른 작업자가 공유 폴더에서 읽기 검산 중이므로 timing 밖의 감사·계약·STATUS·다른 worker 파일은 수정하거나 되돌리지 않는다. 원자료·canonical·legacy 산출물은 읽기전용이다. 새 파일만으로 불필요하게 전체를 재작성하지 말고 국소 수정한다. Python bytecode는 타인 폴더에 쓰지 않는다.

수정:
1. input_split_manifest.json 및 publish_legacy_preparation.py의 A earliest-maximum 문구·정렬 설명을 원입력 최초 최대/A와 B/C 정렬 분리로 정정한다. 재실행 시 이전 잘못된 계약을 복원하지 않게 한다. 현재 생산 파일과 생성기·보고서·summary·계보·해시를 일치시킨다.
2. hourly 입력에서 max_gap_hours >1은 ContractError로 거부하도록 하고 미관측 시간대가 어떠한 허용 파라미터로도 연결되지 않게 한다. 실제자료 수치 파라미터는 선택하지 않는다.
3. timing_guard_contract의 중복시각 점수충돌 data_conflict 정책을 구현하고 원행 추적·고유시각 지속행수·C=B와 결측분절을 유지한다. 충돌 상태 A/B/C 공란을 합성 경계 사례로 검증한다.
4. 기존8검사와 의미있는 추가 검사(>1 거부, 시간0/2 단절, 동일중복 통과/상충중복 거부/결측중복 정책)를 실행하고 실제 exit·stdout/stderr·환경·전후코드해시·수정 전 스냅샷을 timing/의 새 fix 폴더에 보존한다. 기존 실패/과거 로그를 덮지 않는다. 합성검사를 실제자료 성능으로 표현하지 않는다.
5. floor의 실제 사고판정 의미는 미확정으로 명시하고 실제2026점수/B/C/임계값/사고성능을 만들지 않는다. 100척 표는 legacy 대상이며 새v2 Test B 명부와 교집합0이라는 W0 보고는 독립 확인 중이므로 새대상으로 행 이름을 바꾸거나 예측을 이식하지 않는다.

이 작업은 소규모 코드/JSON/합성검사로 예상 RAM은 128MiB 이내다. 실행 직전에 현재 가용 RAM을 확인·기록하고 부족하면 먼저 문서 검토 등 가능한 다른 일을 처리한 뒤 재확인한다. 실제 최대값을 측정하지 못하면 추정/측정을 구분한다. 대용량 캐시/원자료를 로딩할 필요가 없다.

완료 시 실제 exit·검사 수·수정 파일·해시·남은 미확정·요청 모델/Orca 영수증 한계를 worker_done으로 보고한다. 독립 감사는 다른 Luna가 후속 수행하므로 당신이 독립검산 통과를 선언하지 말라.
