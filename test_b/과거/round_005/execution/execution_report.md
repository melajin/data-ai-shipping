# Round005 E — 제한 fixture 실행 보고

2026-11-05 KST. 요청 설정은 별도 Orca GPT-6 Luna/xhigh이며 provider 내부 model/effort는 unknown이다. 원본 `load_rows` AST hash는 `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c`로 고정 검증했다. 이 결과는 작은 합성 fixture의 제한 도메인 검증이며 실제 Train domain 확인이나 생산 승인이 아니다. 별도 V 동적 재검산은 후속이다.

## 구현

- `bounded_loader.py`는 admitted 행 수를 누적 concat ordinal로 사용한다. `trace=None` 경로는 trace 레코드나 index 목록을 만들지 않는다. trace list는 `trace_limit`(기본 100) 이하로만 보유하며 callback은 이벤트를 즉시 넘기는 streaming sink다. 이벤트는 행별 인덱스가 아니라 batch 요약, index class/dtype, 첫·마지막 label만 담는다.
- 키 검증 뒤 ordinal을 먼저 확정하고 ID 변환·drop·int64 cast를 수행한 다음 남은 행에만 date 변환·drop·int32 cast를 수행한다. 무탈락에서는 canonical처럼 `RangeIndex`를 유지하며 drop이 있을 때만 원 ordinal hole을 남긴 `Index`를 만든다. `transform_months`는 앞 월의 admitted count를 다음 월로 전달하며 빈 month-list는 canonical `ValueError: No objects to concatenate`를 유지한다.
- `isolated_stage.py`는 명시한 `stage=dataset="testfit"`만 허용한다. 요청 중복열, `__canonical_index__` 예약열, root 자체·root 밖·symlink·다른 volume·기존 final을 출력 전 차단한다. 각 batch는 한 번에 하나씩 새 scratch에 Parquet으로 쓰며 명시 `__canonical_index__`와 batch별 schema/dtype/index 재구성 metadata를 저장한다. 각 batch의 열과 pandas dtype이 달라지면 전체 단계를 중단한다.
- 출력과 quarantine root는 caller 사전검사에서 symlink/junction, root 밖, root 자체 및 다른 volume 여부를 확인한다. quarantine 수행 때도 root containment 및 quarantine target을 다시 검사하며, 기존 quarantine root가 junction이면 실제 호출 전 거부한다. 고유 stage path를 quarantine 아래로 no-replace rename하고 marker/receipt를 보존한다. Windows 권한으로 symbolic link 자체 생성은 불가능했으나 directory junction escape를 출력경로와 quarantine root 각각에 대해 동적으로 거부했다. 검사와 사용 사이의 악의적 동시 filesystem 교체를 OS handle 기반 no-follow API로 막는 보장은 없다.
- 성공 경계는 같은 volume의 Windows no-replace directory `os.rename(stage, final)` 한 번이다. 완성 manifest와 모든 part가 들어 있는 directory만 이 시점에 공개된다. 최종경로 충돌 및 rename/변환/write 예외에서는 final result/manifest가 생기지 않으며 scratch와 `QUARANTINED.json`/`receipt.json`을 보존한다. 앞 batch yield를 취소한다고 가정하지 않는다.
- stream 입력이 0 batch이면 loader는 schema를 추론하지 않는다. caller에 exact zero-row canonical `empty_template`이 있을 때만 empty schema 결과를 쓰며, 없으면 `EmptySchemaUnavailable`로 격리한다. 스트림의 “0개 frame”과 materialized DataFrame의 “schema를 가진 0행 frame”은 manifest/호출 계약에서 별개다. 저장 metadata의 원 index class·dtype·name·label, 각 part의 경계, explicit index field로 재구성한다. 전 part가 연속 `RangeIndex` 조건을 만족할 때만 전체 `RangeIndex(0, rows)`로 복원하고, 그렇지 않으면 explicit labels로 `Index`를 복원한다.
- `empty_template`는 행 수 0과 canonical output 열순서를 확인한다. feature dtype provenance를 코드가 원천 schema까지 역검증하거나 cryptographic attestation으로 증명하지는 않는다. 호출자는 canonical empty output의 `.iloc[:0].copy()`처럼 출처와 dtype이 확인된 frame만 넘겨야 한다. 이번 strict fixture는 pinned AST의 실제 빈 month/all-empty 결과를 템플릿으로 사용했으며 임의 template의 feature dtype 정확성이나 실제 Parquet의 empty schema를 검증한 것은 아니다.
- 매 batch의 hash·행수·dtype·index class/범위는 manifest 생성 전까지 `receipt["files"]` 목록에 보유된다. 따라서 frame 보유는 batch 단위지만 metadata RAM은 batch 수에 비례하며 최대 batch 수 제한은 구현하지 않았다. 명시 `trace_limit` list는 K개 이하이고 callback은 streaming 호출하나 callback이 받은 이벤트를 저장하거나 지연 처리할지 여부는 callback 소유자의 책임이다. caller가 sink memory/backpressure/durability를 강제하지 않는다. 이 caller의 final output index 복원 metadata가 필요한 환경에서는 manifest metadata 상한 또는 on-disk index sidecar가 후속 보완점이다.

## 검증 결과

최종 명령은 `PYTHONDONTWRITEBYTECODE=1 python -B testB/round_005/execution/verify_fixtures.py`였고 quarantine-root 재검증을 포함한 최신 실행 exit 0, stdout은 `{"frame_cases": 14, "atomic_cases": 17, "all_pass": true, "peak_rss_mib": 107.49}`, stderr 0 byte다. `fixture_result.json`의 모든 frame 비교는 pinned canonical `load_rows` AST와 `pandas.testing.assert_frame_equal`의 exact frame/index class/type 비교를 사용했다.

Frame fixture는 no numeric keys, ID-only/date-only/both, `key_valid` 요청 및 필터 on/off, month 요청/implicit month, 월순서·월경계, 빈 month·전체 empty, empty month-list error, 무탈락 RangeIndex, numeric drop 뒤 `[0,2]` hole-bearing Index, bounded trace를 포함했다. 제한 domain의 ID `±2^53`와 date int32 양끝 및 128자 leading-zero 토큰은 허용·동등했고, ID/date 범위초과, decimal, scientific notation, 공백, Unicode 숫자, 129자는 첫 yield 전에 중단했다. `None`·NaN·`pd.NA` drop 및 ID drop 뒤 date 미검사 순서도 확인했다. 비교된 dtype 예시는 `key_valid: bool`, `month: int8`, `rfid_id: int64`, `part_dt: int32`다. month 1에서 key-valid admitted 4행 중 numeric drop 이후 2행이 남고, month 2의 첫 생존 index가 4여서 offset이 output-row 수가 아니라 admitted 수를 따르는 것을 확인했다.

Atomic caller fixture는 정상 commit 및 저장 parts의 strict DataFrame 재구성, 성공 1 batch 뒤 unsupported token, 성공 1 batch 뒤 일반 예외, scratch write 실패, stage 생성 실패, commit 실패, commit 직전 final 경로가 생긴 no-clobber 경쟁, 기존 final sentinel 보존, 경로탈출/root 자체/비-testfit/중복열/reserved열 거부, schema 없는 all-None 거부, canonical empty template commit을 확인했다. failure cases의 최종 경로는 없었고 quarantine receipt/marker를 확인했다. commit 경쟁에서 기존 sentinel `untouched`와 SHA-256은 변경되지 않았다. Windows 권한 때문에 symbolic-link 생성은 WinError 1314로 거부되었으나, 동일한 외부경로 이탈을 만드는 directory junction fallback을 생성하여 경로가 caller에 의해 거부되는 것을 동적으로 검증했다. 따라서 실제 symbolic-link object 자체 생성/검사는 미실행이다.

## 리소스와 실행 계보

2026-11-05 KST quarantine-root 재검증 suite 직전 fresh RAM은 `memory_preflight_quarantine_guard.json`에 기록했다. 계획은 process peak 512 MiB + host reserve 512 MiB이며 다른 process RSS와 추정 근거·시각도 기록했다. 최신 test process peak working set/RSS 및 peak pagefile/commit은 `fixture_result.json`과 receipt에 기록했으며 작은 fixture 관측이지 보장 상한이 아니다. 실제 sample 16,384행 및 Train 전수 scan은 실행하지 않았다.

최종 런타임은 Python 3.13.3, pandas 2.2.3, NumPy 2.2.5, PyArrow 24.0.0이다. 4개 pinned source SHA 확인값은 `pinned_source_hashes.json`에 기록했다. 실패 시도는 보존했다: 첫 시도 exit 1(empty stream에 frame을 기대한 시험 오류), 두 번째 exit 1(RangeIndex/Index strict mismatch), 세 번째 exit 1(동일 index mismatch 재현), 네 번째 exit 0(RSS 계측이 0으로 잘못 보고됨), 다섯 번째 exit 1(Windows symlink 권한 제한), 여섯 번째 exit 0(junction fallback), 이후 수정 경로와 quarantine-root junction 거부를 포함한 최종 exit 0이다. 해당 명령별 stdout/stderr/exit 및 RAM snapshot은 옆 파일들에 보존했다.

이번 작업은 합성 작은 fixture와 코드 경로의 동등성·원자성만 다뤘다. 전체 Train domain은 unknown이며 전수 key scan, 실제 sample, 참조/새 score/A/membership, stock runner, threshold, 사고 판정, 제출, 실제 split은 실행하지 않았다. 전체 실제 domain에 대한 동등성, crash/power-loss 내구성, V 독립 검산은 남아 있다. 아래의 세 task 생성 임시 폴더는 자동 safety review에서 삭제 시도 `Remove-Item -LiteralPath <경로> -Recurse -Force`가 거부되어 남아 있다. 도구가 밝힌 사유는 `blocked by policy`이며 구체 정책 설명은 확인 불가다. 우회 삭제는 하지 않았다.

- `C:\Users\Public\Documents\ESTsoft\CreatorTemp\r005-fixture-o8q6uevj`
- `C:\Users\Public\Documents\ESTsoft\CreatorTemp\r005-fixture-tm4ev3b8`
- `C:\Users\Public\Documents\ESTsoft\CreatorTemp\r005-fixture-zkaedfup`

새 최종 시도의 모든 scratch는 이 `execution/` 안에 생성했다.
