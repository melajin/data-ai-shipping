# E: 새100척 실제행 청크 조사·격리 runner 구현

별도 실제 Orca gpt-6-luna/xhigh 작업자. 감독Run run_a0639d5ac36a. AGENTS RAM규칙, 설치버전 orchestration guide, round002 ROUND_PLAN, preparation/와 scorer_review/ 보고/manifest, contract/EXPLORATORY_EXECUTION_CONTRACT.md를 읽는다. provider내부 모델은 unknown으로 구분하며 worker_done 보고한다.

소유권은 testB/round_002/execution/만. 당신만 있는 코드베이스가 아니므로 다른 담당 수정 되돌리기/공통파일 수정 금지. 원자료/canonical/기존캐시/선행라운드 읽기전용이다. 출력 격리는 새 실제 runner·scratch·logs 모두 포함한다.

이번 허용범위:
- 시작 RAM·예상peak·병행작업 점검 후 parquet 필수열/row_index를 batch16384로 투영하여 새100척 전체2025기간 행을 추출한다. ID순서/해시, source month/file/ordinal, raw/valid/scorable·누락/중복/월/범위·시간·finite 상태를 선박별 표로 남긴다. parquet 전체를 DataFrame으로 올리지 말고100척만 보존·선박별 처리한다. 행조사 프로세스 예상 증분<=512MiB; 추정 초과가 필요하면 작은 코드작업을 먼저 하고 보고한다. 통계는 실제 스캔한 범위만 주장한다. 메모리 부족시 다른작업후 재개직전 다시 확인한다.
- 원본 함수/상수/참조생성 정확한 재사용을 우선하는 격리 runner를 구현한다. import 부작용을 검토하여 canonical 쓰기와 자동파싱/모델출력 경로를 차단한다. 필요시 AST로 기존 함수정의를 읽어 가져오고 lineage hash를 보존한다. Test→공용ref fit 호출을 막는 입력계약/검증을 둔다. train label membership은 작은 label 파일로 명부와 비교할 수 있다. 원본builder 호출의 실제 load/copy/cache 규모를 추적해 단계별 예상peak·보존배열·재사용/scratch계획을 보고한다.
- 실행기의 원행/A동점/중복충돌/결측, output격리, Test입력이 참조함수에 들어가지 않는 경계에 의미 있는 소규모 합성 검사와 문법검사를 한다. 이는 실제자료 성능이 아니다. 원본score함수 소규모 합성호출은 허용하되 실제train참조/새100척점수를 계산하지 않는다.

금지: 이번에 train reference 재구축/전체점수계산/기존stockCLI 실행/캐시생성/전체CSV재해시·재파싱/임계값·B/C·사고예측·성능·제출·외부연락. 감독은 runner/실제100척 요약/RAM계획 검토 뒤 다음 생산지시를 별도 보낸다. 함수/참조변경 또는 복잡성을 임의 추가하지 말고 불확실을 보고한다.

deliverables: runner code + 사용명령(후속실행용, 미실행 구분), target_row_summary.csv, 원행trace 포함 selected rows parquet/partitioned files, preflight_report.md, execution_manifest.json, 환경/RAM/실제검사exit/stdout/stderr/산출물SHA. 첫 실패도 보존한다. peak는 측정/추정을 분리한다. bounded row scan 결과와 runner 준비 범위가 완료되면 worker_done으로 보고 후 감독 관문을 기다린다.
