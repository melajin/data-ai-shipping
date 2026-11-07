# V 후속 검산 — manifest hash-map metadata delta

- 결과: **PASS (metadata-only delta 검산)**
- 기존 V 결과는 보존: `preparation_001/review.json`의 status는 **FAIL**, aggregate exit는 **1**입니다. 이번 PASS는 그 전 결과를 다시 쓰거나 취소하지 않습니다.
- 범위는 execution manifest의 hash-map 정정과 이전 검산 결과의 불변 확인입니다. 이 작업은 전체 parquet scan, synthetic fixture, reference builder, 실제 점수를 **재실행하지 않았습니다**.
- 요청 모델/effort: `gpt-6-luna` / `xhigh` (dispatch와 E manifest의 요청 설정). provider 내부 모델/effort는 **unknown**입니다.

## 확인 결과

1. **Snapshot 및 manifest 해시:** 사전 백업 `logs/execution_manifest_before_hashmap_repair_20261105T044752909863p0900.json`를 직접 해시해 `8f4533ca1efa2a0a1ff8d8bb4d49151344cf1e9d4569c51ac0b8a3469f7b0c9a`을 확인했습니다. 이는 repair receipt와 원 V 검산의 repair 전 execution manifest SHA 및 pre-change SHA `8f4533ca1efa2a0a1ff8d8bb4d49151344cf1e9d4569c51ac0b8a3469f7b0c9a`와 일치합니다. 현재 manifest SHA는 `a8bb74a10936572ad152aabeacc5f741a036d922e3a86fdd2f0dbcb494117e42`이며 receipt의 post-change SHA `a8bb74a10936572ad152aabeacc5f741a036d922e3a86fdd2f0dbcb494117e42`와 일치합니다. receipt는 백업을 pre-change manifest와 byte-identical이라고 기록하고, V의 hash manifest가 기록한 당시 manifest SHA와도 일치합니다.

2. **역사적 44 해시:** 백업 manifest의 `artifacts_sha256` 44개 값을 새 `historical_artifacts_sha256_before_runner_repair`와 항목별 대조했습니다. 이름을 역사 필드로 옮겼을 뿐 digest 문자열은 전부 동일합니다. repair receipt/manifest는 이 값들이 현재 무결성 대상이 아니며 원 source bytes를 복원하거나 예전 정합성을 입증하지 않는다고 한정합니다. 따라서 그 44개 값의 최초 의미, 생성 시점, 원 코드/파일과의 대응 및 복원 가능성은 **unknown**으로 둡니다.

3. **현재 단일 canonical map:** 현 manifest의 현재 해시 맵은 `artifact_sha256` 하나이며 **56/56** 항목이 디스크의 현재 파일 SHA-256과 일치합니다. 이전 `artifact_sha256` 53개는 값 그대로 부분집합으로 보존되었고, 그 53개도 현재 항목을 직접 재검증해 53/53 일치했습니다. 추가 항목은 receipt가 명시한 backup 포함 정책과 맞습니다.

4. **Self-hash/receipt 정책:** current map에는 사전 snapshot이 포함되며 snapshot의 자기 map에는 자기 경로가 없습니다. `execution_manifest.json`은 self-reference 때문에, `manifest_hashmap_repair_receipt.json`은 final manifest hash를 담기 때문에 current map에서 빠져 있습니다. 이 정책을 current manifest의 policy 필드 및 실제 map key와 비교했습니다.

5. **이전 검산 산출물의 불변:** 이전 독립 hash manifest와 현재 파일을 대조했습니다. `isolated_runner.py`, `preflight_report.md`, `scan_result.json`, 그리고 selected month 01–06 parquet 총 9개가 모두 이전 SHA-256 및 크기와 일치합니다. 기존 독립 scan의 4,212,389행 / 선택 46,705행 결과와 26행 synthetic fixture pass 기록은 기존 JSON/보고서 그대로이며 다시 실행하지 않았습니다. preparation_001의 모든 파일도 검산 전후 SHA, 크기, mtime이 같아 읽기 전용이 유지됐습니다.

6. **UTF-8 및 metadata repair 종료:** repair receipt와 현재 manifest를 UTF-8로 직접 읽고 JSON parse했습니다. UTF-8 report의 replacement character는 0입니다. repair receipt의 operation process exit는 **0**이며 성공 stdout과 빈 stderr를 확인했습니다. 별도 exit-code sidecar는 없으므로 exit code 근거는 producer receipt입니다. 이번 독립 delta validator 실제 exit는 **0**입니다. 기존 V aggregate exit 1은 별도로 보존했습니다.

## RAM 및 환경

worker 시작 재확인(2026-11-05 04:51:06 KST) 당시 가용 RAM은 4,706,536 KiB였습니다. 해시 검산 직전(04:57:48 KST) 가용 3,481,292 KiB / 전체 14,480,244 KiB였고, 약 319개 전체 프로세스와 45개 Python/Orca/Codex/Node 관련 프로세스가 보였습니다. 이 중 다른 Python 프로세스 RSS는 약 1,194.8 MiB였습니다; 동시 agent 수는 unknown입니다. 작업 예상 peak 증분은 최대 128 MiB, 세션 여유 512 MiB를 별도로 남겼습니다. 실제 delta validator RSS는 시작 23.5 MiB, 단계 표본 최대 24.1 MiB, 표본 증가 0.6 MiB였습니다. 이는 작은 metadata/hash 작업 표본이며 system 전체 peak 계측은 아닙니다. 파일 해시 계산은 current manifest가 가리키는 작은 artifact 범위에만 적용했고 생산 파일은 수정하지 않았습니다.

## 남은 불확실성

역사적 digest 44개의 최초 의미·기록 시점과 원래 해당 파일의 복원/검증 여부는 unknown입니다. provider 내부 모델/effort, 사고 정답·정상 근거·개발 사용·threshold·split·실제 성능 및 full production peak RAM도 unknown입니다. 이번 산출은 manifest metadata 정정의 범위 검산이며 실제 점수나 성능을 인증하지 않습니다.

## 파일

- `metadata_delta_validator.py`, `metadata_delta_result.json`, `review.json`
- `environment.json`, `hash_manifest.json`
- validator stdout/stderr 및 actual exit file
- Preserved validator attempts 01-04 and report-finalize attempts 01-02, including stdout/stderr/exit logs; final runs exited 0.
