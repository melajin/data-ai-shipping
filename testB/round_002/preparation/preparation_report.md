# P 준비 결과 — 새100척 입력계보·RAM

기록 시각: 2026-11-05 KST. 범위는 `testB/round_002/preparation/`입니다. 요청 모델/effort는 gpt-6-luna/xhigh이며 provider 내부 모델은 관측 근거가 없어 unknown으로 기록합니다.

## 새 명부와 데이터 계보

새 v2 ZIP 제출샘플 member의 prior 직접 재검산 산출물에서 Test B A2:A101을 원순서·원문 타입으로 옮겨 `new_testB_ids_100.csv`에 보존했습니다. 100행/100개 고유 ID/문자열 타입 100개이며 SHA는 `artifact_hashes.json`에 기록했습니다. prior direct recheck는 member와 intake workbook SHA 일치, newB 대 intakeB 100/100, oldB 대 newB 교집합 0을 확인했습니다. 이 준비 run은 XLSX를 다시 열지 않았고, CSV는 기존 감사 산출물을 이어받았습니다.

W0 입력호환 기록에서는 ZIP 내부 CSV 12개와 대응 F: 원본 12개가 바이트 동일(12/12, 양측 합계 각 13,349,258,148 bytes, CRC EOF 검증)이며 actual exit 0입니다. `parse_test_1..6.json`은 해당 Test CSV 파일의 바이트 수/SHA가 parser 실행 시 비교 일치했고, `rows_test_1..6.parquet`이 각 입력에서 파생됐다고 기록합니다. 이 연결은 새 v2 CSV → W0 대응 F: CSV → parse manifest → parquet 계보를 지원합니다. 13GB 원자료를 이번에 다시 해시하거나 파싱하지 않았습니다.

prior ID 재검산은 4,212,389 parquet 행에서 `rfid_id` 열만 순차 투영하여 새 ID 100개를 찾았습니다. 이는 ID membership 기록이며 새 v2 대상별 행 수/결측/중복/시간 범위나 값 동일성의 검산은 아닙니다. 허용된 metadata-only P 범위에서 이러한 대상별 사실은 unknown으로 남겼습니다.

## parquet·원행·시간·좌표 계약

6개 parquet의 schema/footer 통계만 확인했습니다. 스키마는 `row_index:int64`, `part_dt:string`, `rfid_id:string`, `rfid_time:int16`, `fishing_code:string`, `key_valid:bool`, `wkt_valid:bool`, `n_coords:int32`, `len_m:double`, `bbox_m:double`, `cen_lon:double`, `cen_lat:double`입니다. 원 Test 헤더는 `part_dt,rfid_id,rfid_time,geom`입니다. footer의 날짜 범위는 2025-01-01~2025-06-30, `rfid_time` 범위는 0~23이고 총행수는 4,212,389입니다. `fishing_code`는 원 Test 열이 아니며 Test cache에서는 null입니다.

parser 코드는 `row_index`를 header 이후 zero-based source data row ordinal로 부여합니다. 월 파일마다 0으로 재시작하므로 추론 때는 source month/file와 함께 보존해야 합니다. fixed scorer path는 원행 ordinal을 output에 전달하지 않으며, timestamp 정렬 후 `idxmax`의 tie 선택은 기존 입력 순서 첫 최대 규칙과 같다고 보장되지 않는다고 R 코드검토가 보고했습니다.

기존 parser는 WKT MULTILINESTRING의 x를 longitude, y를 latitude로 해석하고 좌표/길이 요약을 저장합니다. 각 line part의 내부 선분 길이는 계산하지만 part 간 연결선을 추가하지 않습니다. raw `geom`은 parquet에 저장되지 않아 원좌표 시퀀스, 투영정보, 데이터의 부분/완전 수록 상태를 복구할 수 없습니다. CRS/datum과 `rfid_time`의 시간대 의미는 unknown입니다.

## 고정 scorer·참조 연결 (R 정적 검토 반영)

R 검토(`testB/round_002/scorer_review/scorer_review.md`)에 따르면 harbor/density/gap-jump 공용 참조는 2026 train에서 만들어지고, 2025 test 행은 점수 입력과 대상 선박의 과거 이력으로만 사용됩니다. scorer 경로에 Test 기반 scaler/KDE/calibration/quantile/threshold 적합 호출은 없다고 코드 정적 검토했습니다. gap/jump 참조는 3,879,693개씩, density metadata는 fishing 1,376,741행 및 fine/coarse cell 102,053/9,174개입니다. 이는 이상 정도 탐색 점수이며 사고확률이나 사고 정답이 아닙니다.

참조 관련 파일 위치는 `D:/repos/fishing-track-classification/results/work_008/scores_meta.json`, `train_harbors.json`, `scored_rows.pkl`, scorer source `code/tools/run_008_testB_20261101.py`입니다. 다만 완전한 재사용 static reference bundle이 확인된 것은 아닙니다. score 실행 코드가 train reference arrays/maps를 빌더로 재구성하고, `scored_rows.pkl`은 legacy 100대상 점수 출력이라 신규 ID에 재사용할 수 없습니다. metadata JSON은 요약값만 보존합니다.

R이 제시한 8개 test scorer input 열은 `rfid_id,part_dt,rfid_time,wkt_valid,cen_lon,cen_lat,len_m,bbox_m`입니다. 원행 연결을 위해서는 `row_index`와 source month/file도 추가로 보존해야 합니다. 개별 새 ID의 행 수·전체기간 유효행·결측·중복·2026 reference membership은 unknown입니다. R은 legacy CLI가 1027 workbook 명부를 읽고 canonical `results/work_008/`에 쓰며, 원행 순서를 보존하지 않아 그대로 실행하면 안 된다고 판정했습니다.

## RAM과 권장 청크 계획

시작 RAM 확인(2026-11-05 03:42:13 KST)은 가용 4,310.1 MiB/총 14,140.9 MiB였습니다. schema metadata 직전(03:43:53)은 4,359.7 MiB, footer 통계 직전(03:46:01)은 4,399.3 MiB였습니다. 각 조사 증분 peak는 256 MiB 이하로 추정했으며 실측 peak는 아닙니다. Orca/Codex와 OS 프로세스가 병행 중이었고 세션 오버헤드는 별도 unknown입니다.

추론 메모리 상한은 측정/보증값이 아닌 보수적 계획치입니다. train parquet 3,887,069행과 scorer input 8열 기준으로 문자열 ID/date의 offset+짧은 payload, int16 시간, boolean, float64 4열을 약 59 bytes/행으로 가정하면 단일 Arrow payload는 229.3MB(218.7 MiB)입니다. Pandas 변환 한 벌을 약 0.62 GiB로 가정하고 sort/concat 복사, 참조 arrays/maps, 임시 공간을 더해 별도 실행 프로세스 증분 2 GiB를 계획합니다. 실제 peak는 pandas 문자열 보관, 정렬 복사와 밀도 지도 작성 방식에 달려 있으므로 미측정이며 R도 production peak를 unknown으로 남겼습니다. 실행 직전 RAM 및 병행 작업을 다시 확인해야 합니다.

권장 별도 runner는 stock CLI를 호출하지 않고, 감독 실행 gate 후 train parquet를 월별 순차 `iter_batches(batch_size=16384)`·열 투영으로 읽어 고정 2026 train 참조를 만든 뒤 scratch/mmap에 두고, test 파일 역시 순차 투영·청크 처리하면서 100 ID만 남겨 선박별 처리합니다. 원행은 월/file+row_index로 보존합니다. 전역 dataframe concat을 피하고 exact sorting/quantile이 필요하면 배열을 별도 scratch에 순차 정렬합니다. 확정되지 않은 조건은 실행 전 명시해야 하며, 현재 단계에서는 참조 재구축·점수 생성을 하지 않습니다.

## 실제 검사와 미실행 / 종료 코드

- prior W0 input compatibility exit 0, prior v2 ID recheck exit 0을 기존 기록에서 확인했습니다.
- 이번 parquet schema/footer metadata 검사 exit 0, row-group footer min/max/null 통계 검사 exit 0입니다. 첫 inline metadata 호출은 Python quoting syntax error exit 1로 데이터 접근 전에 실패했고, 수정 호출은 성공했습니다.
- 이번에는 XLSX 재열기, 전체 CSV 해시, parquet row scan, pickle/DataFrame/cache load, score/feature/model 생성은 실행하지 않았습니다. 실제 하드웨어 검증도 수행하지 않았습니다.

산출물은 `manifest.json`(machine-readable 계보·제약·미확정·RAM 계획), `parquet_schema_metadata.json`(footer 검사), `new_testB_ids_100.csv`(순서 명부), `environment.json`, `inspection.log`, `validation_summary.json`입니다. SHA-256은 `artifact_hashes.json`입니다.
