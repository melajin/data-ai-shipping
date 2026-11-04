# Round003 V E 실패 독립 감사 — 2026-11-05

## 판정

**E bounded loader는 실제 train 표본 범위의 일치만 보였고, batch별 numeric 추론 동등성은 입증하지 못했다.** 더 강하게 말하면, 그 실제 표본 비교 코드는 두 8,192행 Arrow batch를 `pa.Table.from_batches`로 합친 뒤 `transform_batch`를 한 번만 호출했으므로 batch별 parsing을 시험하지 않았다. E가 별도 작성한 경계 fixture는 mismatch를 냈고 최종 비교는 실제 exit 2다. 생산 loader/참조/점수 생성이 완료된 것은 아니다.

## 실행·범위·해시 증거

- Orca CLI는 `ORCA_CLI_COMMAND`가 지정한 `orca.exe`, version `1.4.246.0`이다. 실제 `skills get orchestration`과 `skills get orca-cli` 안내를 확인했다. E launch receipt에는 요청/launch `gpt-6-luna/xhigh`, launch CLI exit 0가 기록되어 있다. provider 내부 model/effort는 unknown이다.
- E 최종 receipt/summary의 primary command는 `python -B testB/round_003/execution/compare_loader_sample.py`, exit 2이며 stdout/stderr/receipt가 `execution/`에 있다. E worker_done은 failed (`msg_f7d45da31bf0`)로 지시된 대로 보존했다.
- 시도별 실제 exit: attempt01 exit 1 (`pyarrow.parquet`에 없는 `Table` 사용); attempts02–05 exit 0; attempt06 최종 exit 2. attempts02–05 결과 JSON에는 boundary unequal이 기록되어 있는데도 exit 0이었던 중간 시도들이 있다. attempt06은 mismatch를 실패로 반환했다. 최종 stderr는 빈 로그이며 불일치의 구체값은 stdout/JSON에 남는다.
- 이 감사 시작 시각 05:29:45 KST 여유 RAM 4,120.6 MiB / 총 14,140.9 MiB, process 351, Python worker 미관측. 작은 합성 직전 05:31:22 여유 4,234.6 MiB / 총 14,140.9 MiB, process 342; 예상 증가량 ≤32 MiB, 요구 여유 512 MiB, E는 settled failed이며 별도 귀속 불가 Orca/host 프로세스는 남아 있었다. peak는 실측하지 않았다. 합성은 메모리 내 Arrow/pandas 표만 사용했고 원본 파일/데이터를 읽지 않았다.
- canonical 4개 source SHA가 `round_002/scorer_review/manifest.json` 고정 SHA와 전부 일치한다. round002 preparation/execution/scorer-review 6개 read-only artifact도 E summary의 SHA와 전부 일치한다. E가 자체 기재한 현재 execution 파일 5개 SHA 및 `execution_summary.json`/`preflight_report.md` 영수증 SHA도 다시 계산해 일치했다. 파일별 값은 `manifest.json`에 보존했다. 따라서 이 감사는 고정 source 및 round002 근거와 일치한다. 다만 전체 파일시스템의 모든 생산 경로를 재해시한 것은 아니다.

## E 실제 비교 코드와 결과 범위

`compare_loader_sample.py:50–61`은 `ParquetFile.iter_batches(batch_size=8192)`에서 16,384행을 두 번 읽지만, 이후 `pa.Table.from_batches(batches)`로 하나의 Arrow Table을 만든다. 원본 `load_rows` AST에도 이 결합 table을 한 번 주입하고, bounded 쪽도 `transform_batch(injected, ...)`를 한 번 호출한다. `transform_batches()`는 이 실제 표본 경로에서 호출되지 않는다. 그러므로 이 표본은 1월 Parquet의 처음 16,384 물리 입력 행에 대한 **결합 전체-Series 변환** 비교다. 원본 전체 loader는 호출하지 않았고, 이 제한 표본에서 열/행수/dtype/값/NaN/제외집합이 같았다는 사실만 유지한다. 보고서의 “실제 표본이 batch별 전환을 검증했다”는 식의 해석은 코드로 뒷받침되지 않는다.

같은 스크립트 `:74–76` 경계 fixture의 `original_whole`은 AST 추출 loader 호출이 아니라 `whole = boundary.to_pandas()` 다음 변환 순서를 수동 재작성한 계산이다. 이 때문에 E의 fixture는 production source와 완전히 독립한 계산은 아니지만, 원본 loader AST 자체로 합성 사례가 검산된 것도 아니다. 이 감사의 `independent_fixture_check.py`는 canonical `load_rows` 함수 AST를 exact source hash 확인 후 in-memory Arrow reader에 주입하여 실제 함수 본문을 실행하고, 별도의 계약 기반 whole-column oracle 및 bounded batch 변환과 비교했다.

E attempt06의 final boundary mismatch와 이번 독립 검산은 같은 알려진 반례를 지지한다. `rfid_id` 원문 `9007199254740993`과 `1.5`를 같은 전역 Series에 두면 `pd.to_numeric`은 `float64`로 추론하여 첫 값이 `9007199254740992.0`이 되고 `int64` cast 결과도 `9007199254740992`다. 각 한 행 batch로 나누면 첫 batch는 `int64`로 정확한 `9007199254740993`, 두 번째는 `float64`로 `1.5`를 만들며 최종 정수 ID는 `9007199254740993`, `1`이다. 최종 열 dtype은 양쪽 모두 int64여도 값은 다르다. 이 값은 **합성 경계 반례**이며 실제 Train에 해당 문자열이 있다고 주장하지 않는다.

## 독립 합성 결과

`fixture_result.json`은 `independent_fixture_check.py`의 전체 JSON stdout 사본이다. 코드의 actual exit는 `fixture.exit_code.txt`의 `0`; stdout/stderr는 별도 파일이며 stderr는 0 byte다.

- 독립 fixture는 canonical `load_rows` AST (고정 SHA 확인)를 in-memory Arrow에 실행했다. 별도 참조 계산은 계약의 월별 `key_valid` admission → concat 및 연속 index 부여 → 전체 `rfid_id` 변환/실패 행 제거 → 남은 행에서만 전체 `part_dt` 변환/실패 행 제거 → int64/int32 cast 순서로 작성했다. 생성 코드 복제 한 쪽만으로 결과를 판정하지 않고 AST·독립 oracle·`bounded_loader.transform_batch`의 출력과 명시 값 assertion을 함께 비교했다.
- 작은 2행 반례에서 canonical AST = independent whole-column oracle는 true, batch 변환과 값은 다르다. canonical ID는 `9007199254740992, 1`, batch ID는 `9007199254740993, 1`이다. 비교 전 dtype은 global numeric 결과 float64, batch numeric 결과 int64/float64; 정수 cast 후 각 DataFrame 열 dtype이 같아지는 것이 값 동등성을 뜻하지 않음을 확인했다.
- 별도 2개월 loader fixture는 `key_valid_only=True/False`를 둘 다 실행했다. bad ID/null ID 제외 후에 date 변환이 이뤄지고, date 실패가 추가로 제거되는 순서가 canonical AST와 oracle에서 일치한다. 월 순서, numeric 출력 dtype(int64/int32), `month:int8`, 열 순서를 확인했다. `key_valid_only=True`에서는 key filter가 월 frame concat 전 일어나므로 최종 pandas index는 `[0,3,5]`; `False`에서는 `[0,3,4,5,7]`이다. 월별 batch transform을 단순 concat하면 각각 `[0,0,3]`, `[0,3,0,1,3]`로 canonical index를 보존하지 않는다(행 값은 index reset 후 일치). 다음 adapter가 정확 frame equality를 계약한다면 key-filter 뒤 concat 위치의 global loader index를 들고 가야 한다.
- 이 fixture의 `rfid_id`/date에는 null·nonnumeric를 포함했다. 전역 numeric Series는 둘 다 float64로 승격되지만, 남은 정수 ID를 절댓값 2^53 이내로, date를 int32 범위로 제한하면 `int64`/`int32` 최종값은 같은 synthetic domain에서 batch 처리와 일치했다. 이는 조건부 반례 가능성을 시험한 소량 합성일 뿐 실제 도메인 coverage나 전체 equivalence를 보이지 않는다.

## Testfit 차단·출력 부작용·생산 불변의 범위

`round003_runner.py`는 실제 production loader가 아니라 stub이다. 함수들은 기본 `allow_production=False`에서 deny하고, True여도 “production path intentionally unimplemented”로 끝난다. CLI `main`은 인자를 파싱한 뒤 항상 default-deny 종료하므로 현재 코드에는 builder 호출·source load·output write 구현이 없다. 이는 코드를 읽어 확인한 설계 상태다. runner를 실행해 runtime Testfit 차단, 출력 격리, `__pycache__`/progress 부작용을 시험하지 않았다. 따라서 런타임 gate 완성 또는 생산기능 통과로 보고하지 않는다.

E 표본 코드는 canonical 모듈 전체 import 대신 고정 SHA 확인 후 loader AST만 실행하고, `python -B`로 시작했다. E가 사용한 표본이 읽혔고 execution 산출물이 써졌다는 사실은 보존한다. 원자료의 full scan, full reference build, score/A/membership 생성은 E와 V 이번 후속에서도 실행되지 않았다. 원본 canonical 4개와 round002 pinned artifact SHA는 현재 재해시에서 일치하여 본 감사가 변경하지 않았음을 확인한다.

## 후속 설계 두 가지와 조건

### A. 키 열 전체 변환을 유지하고 나머지를 batch 처리

월 순서/물리 행 순서대로 (필요 시 `key_valid` 우선 적용) raw key와 전역 ordinal만 scratch로 모은다. `rfid_id` 전체 pandas Series에 원본과 같은 한 번의 `pd.to_numeric(errors="coerce")`를 적용하고 bad-ID row를 제거한다. **그 후에만** 남은 행의 `part_dt` Series를 원본 전체 Series 방식으로 변환하고 bad-date를 제거, int64/int32 cast 결과와 keep/ordinal map을 고정한다. 나머지 열은 bounded batch로 읽어서 이 keep map을 적용한다. 단순 파일별/월별 numeric conversion은 금지한다. canonical output index를 유지하려면 `key_valid_only=True`인 경우 월별 key filter 적용 후의 concat ordinal을 별도 저장하고, 이후 숫자 drop의 구멍을 유지한다.

이 설계는 숫자 해석 위험을 줄이고 feature table 중첩을 피하지만, 3,887,069행의 전체 key Series와 전역 numeric result가 필요하다. 대략 object pointer만 key당 31 MiB이며, 문자열 객체 payload/Arrow buffers, numeric 결과 약 31 MiB와 mask, concat/변환 복사본이 추가된다. ID/date 한 열 단계만 각각 처리해도 임시 객체와 allocator/page-cache를 포함한 peak는 보수적으로 **열당 수백 MiB, 대략 0.3–0.8 GiB 후보**로 잡아야 한다. 실제 크기·peak는 미측정이며 scratch가 RAM 부담을 없애지는 않는다. 변환기/정확 순서 proof와 fresh RAM gate 없이 실행 금지다.

### B. 제한 정수 도메인 검증 후 batch 변환, 미지원이면 fail-closed

전체 source를 처리하기 전에 key_valid admission population에서 ID와 date 문자열의 실제 domain을 bounded scan으로 증명해야 한다. 지원 가능한 좁은 grammar의 예는 ASCII `[+-]?[0-9]+`(선행 zero 포함), ID 절댓값 ≤2^53, date int32 범위다. whitespace·소수 `1.5`·scientific notation·범위 밖 integer 등 지원하지 않는 값은 “잘못된 행”으로 silently 제외하지 말고 **전체 loader 중단**으로 처리해야 한다. 원본 `pd.to_numeric`이 `1.5`를 숫자로 인정한 뒤 int cast를 truncate할 수 있기 때문이다. null과 명백한 nonnumeric는 원본처럼 `errors="coerce"` 후 제거하되, key-valid/non-numeric admission 정책을 별도로 유지한다.

동등성 논증은 global numeric inference가 null/nonnumeric 때문에 float64가 되더라도 모든 유효 정수가 절댓값 ≤2^53이면 float 변환이 정확하며, date는 int32 내에서 정확하다는 조건을 둔다. batch도 같은 bad mask를 만든 다음 정수 cast를 한다. 예제 합성은 이 제한 도메인에서 결측/nonnumeric로 전역 float가 된 경우 final value/dtype가 일치할 수 있음을 보였고, 별도 2^53+1 + 1.5 fixture는 범위를 벗어나 반드시 reject해야 함을 보였다. 날짜도 ID bad row 제거 후에만 검사/변환해 원본의 순차 제외를 보존해야 한다. 계획상 8,192행 key-only scan과 Arrow bitmap validity mask(각 3.9M행 기준 약 0.5 MiB, unpacked bool이면 약 3.9 MiB/마스크)를 쓰고 전체 feature 배열은 유지하지 않으면 배치/작업 메모리의 초기 envelope를 ≤256 MiB로 잡을 수 있다. 이는 계산 가능한 mask 크기와 8,192행 투영을 바탕으로 한 미측정 계획값이지 보증치가 아니다. 실제 Arrow/Pandas 임시 객체, row-group/page cache, 다른 프로세스를 포함한 fresh RAM gate와 계측이 필요하며 초과 시 batch 축소/중단한다. 숫자 domain actual train coverage는 unknown이므로 **전수 bounded validation이 아직 허가될 때까지 B는 미확인/사용불가**이며, unsupported 발견 시 fail-closed 테스트도 별도 필요하다.

둘 중 어느 설계도 현재 구현·전수 동등성 pass·실행 승인이 아니다. 다음 기술 게이트 전에 E의 실패 수정, loader 설계 선택, 실제 key domain 확인 권한, 독립 구현/fixture 검토, memory budget 및 감독 승인이 필요하다. 큰 train scan/reference/score/A/membership는 계속 default deny다.

## 보존된 미실행/미확인

- 이번 V fixture의 작은 인메모리 synthetic 실행만 exit 0. E attempt01의 실제 exit1 및 최종 actual sample-comparison exit2는 실패 상태로 보존했다. E attempts02–05의 exit0은 각 비교 JSON의 경계 불일치를 가리지 않는다.
- 실제 16,384 train sample은 E가 기존 로그에 기록한 제한 표본으로 구분했다. V는 표본을 재읽지 않았고 전체 parquet/CSV/pickle/train/test scan도 하지 않았다.
- full train reference, 2025 actual score/A, membership 전수 산출, Testfit runtime, 사고/성능/threshold/B/C/submit/split은 전부 미수행.
- 이전 Round002의 최초 독립감사 FAIL/exit1과 후속 metadata-only delta PASS 10/exit0는 별개 증거로 유지한다. 역사 44-hash의 최초 의미/기록 시각 및 byte restoration은 unknown이다.

