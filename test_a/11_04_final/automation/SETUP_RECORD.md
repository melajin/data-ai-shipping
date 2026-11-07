# 초기 운영 구성 기록

기준일: 2026-11-04. 이 문서는 실험 결과가 아닌 폴더·모델 요청·인계 구성의 증거다.

## 사용자 요청

- 기존 데이터는 `F:\문제 데이터_수정_1027`.
- 앞으로 작업할 위치는 `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final`.
- 회차 완료 후 결과 문서를 파일로 저장하고 다음 세션에서 할 작업을 작성하여 새로운 세션에서 재진행한다.
- 목표 micro-F1 0.7 이상.
- 관리자: GPT-6 Astra high. 보조: GPT-6 Luna xhigh, 최대 4개.

## 실제 구성과 확인 범위

- 초기 실험 관리자 `/root/next_step_decision`은 생성 시 `agent_type=astra_decision`, `model=gpt-6-astra`, `reasoning_effort=high`, `fork_turns=none`을 명시했고 생성 도구가 해당 작업을 수락했다. 기존 읽기 검토 담당에 후속 작업을 보내 round_001의 관리 책임을 배정했다.
- 관리자는 Luna xhigh 두 작업을 생성했다: `round001_t5_execution`, `round001_independent_review`. 관리자의 실행기록은 `rounds/round_001/`에 별도로 저장한다.
- 현재 호스트는 root 포함 동시 4개 agent 슬롯이므로 초기 구성은 연결 담당 root + Astra 관리자 + Luna 2명이다. 사용자 상한 4명을 채우기 위해 호스트 제한을 넘기지 않는다.
- root는 폴더·설정·인계 스크립트만 통합하며 실험 판단과 결과 작성은 Astra 관리자 소유다. 현재 root의 모델이 바뀌었다고 주장하지 않는다.
- `.codex` TOML 세 파일은 Python `tomllib` 파싱을 통과했다. 이 검사는 파일 문법 검증이며 모든 설정 키에 대한 호스트 적용 증거는 아니다.
- `Start-NextSession.ps1`은 PowerShell 구문 검사를 통과했다. 실제 세션 시작은 회차 종료 후 수행하고 수락 영수증을 별도로 보존한다.
- `Start-NextSession.ps1 -FromRound round_001 -InspectOnly`는 실제 세션을 만들지 않고 정상 실행됐다. 작업 루트, 기존 workspace 경로, `gpt-6-astra/high`, 이전 영수증·claim 부재를 확인했다.
- `Test-SessionLauncher.ps1`의 모의 실행에서 미완료 회차 시작 차단, 수락 영수증 파싱, 동일 회차 재호출 시 세션 중복 방지가 통과했다. 모의 CLI 호출 1회, 실제 생성 세션 0개이며 결과는 `launcher_smoke_result.json`에 저장했다.
- round_001 실제 계산 시작은 `rounds/round_001/execution/launch_manifest.json`에 PID 1012, 2026-11-04T14:06:24.5035211Z, Python 명령, stdout/stderr 및 작업루트 내부 temp 설정으로 기록됐다. 계산 완료 여부는 회차 보고서를 따른다.
- Orca `agent launch --help`에서 `--model`, `--effort`, `--prompt`, `--worktree`, `--json`, `--retry-launch` 지원을 확인했다.
- `orca repo add --path ...\11_04_final --json`은 `Not a valid git repository`로 실패했다. 새 Git 저장소를 만들지 않고 기존 `DATA AI SHIPPING` workspace에서 fresh manager를 띄우고 새 작업 루트를 프롬프트로 지정하는 경로를 선택했다.

## CLI 경로

`C:\Users\dlehs\AppData\Local\Programs\orca\resources\bin\orca.exe`

Orca가 제공한 기존 workspace ID:

`694309e1-3a51-45ba-b9c8-19f164cfd785::D:\obsidian\claude\obsidian_export\DATA AI SHIPPING`

사용 스킬: 로컬 `orca-cli` 및 `orchestration`의 version-matched CLI 안내. 새 세션 인계는 `agent launch` 경로이며 별도의 반복 polling 작업이나 예약 작업을 만들지 않는다.

## 2026-11-04 후속 실행 상태·인코딩 보완

- 이전 목표 turn은 첫 회차 완료와 새 세션 전달을 실제 수행한 progress로 분류했다. 이어진 점검에서 Orca `worktree ps`가 대상 structured session `codex_99fb7c51_baa2_42b7_96ab_1a4835df7e28`을 `working`, `structuredHostOwned=true`, `subagentObservation=live`로 보고했다. terminal show의 stale 응답은 이 structured chat의 종료 증거로 사용하지 않았다.
- 이 세션의 초기 프롬프트 한글이 깨진 것을 runtime 상태에서 확인했다. Windows PowerShell 5.1이 BOM 없는 UTF-8 `.ps1`의 한글 리터럴을 ANSI로 읽는 문제로, `Start-NextSession.ps1`을 **UTF-8 BOM 포함**으로 보존했다. 향후 이 파일을 수정해도 BOM을 유지해야 한다.
- mock CLI에 실제 전달된 인수를 저장하고 한글 지시문 시작과 `F:` 원자료 경로를 검사하도록 테스트를 확장했다. 수정 후 readiness·수락 파싱·중복 방지·Unicode 인수 검사가 모두 통과했다. `launcher_smoke_result.json`의 `unicode_prompt_and_raw_path_passed=true`를 확인했다.
- 첫 프롬프트 원문/기존 영수증은 수정하지 않았다. 새 관리자는 실제 로컬 NEXT_SESSION과 보고서를 읽어 Round 002 범위를 인식한 것이 runtime assistant message로 확인됐다. 기존 세션을 다시 만들거나 실험을 중복 실행하지 않았다.
