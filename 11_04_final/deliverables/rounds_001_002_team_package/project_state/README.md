# micro-F1 0.7 목표 — 회차별 실험과 새 세션 인계

2026-11-04 사용자 지시로 이 폴더부터 후속 작업을 진행한다. 관리자와 보조의 모델 요청은 **GPT-6 Astra high / GPT-6 Luna xhigh**로 고정한다. 보조는 최대 4명이며 호스트의 더 낮은 동시성 한도를 따른다. 설정 파일이 이미 실행 중인 세션의 모델을 바꾸는 것은 아니다.

## 경로와 현재 출발점

- 새 산출물: 이 폴더의 `rounds/round_NNN/`.
- 원자료 읽기 전용: `F:\문제 데이터_수정_1027`.
- 이전 코드·결과 참조: `D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104`.
- 현재 개발 기준선: `sqrt_macro` 5-seed micro-F1 **0.593013**. 탐색 최고값 **0.593353**은 순증 2척으로 확정 개선이 아니다.
- micro-F1 **0.7은 목표이며 현재 달성값이 아니다.** 반복 관찰한 개발 OUTER 점수와 독립 평가 점수를 분리한다.

## 읽는 순서

1. [작업 규칙](AGENTS.md)
2. [현재 상태](STATUS.json)
3. [회차·평가 계약](CYCLE_PROTOCOL.md)
4. [실험 장부](EXPERIMENT_LEDGER.csv)
5. [다음 세션 작업](NEXT_SESSION.md)

첫 회차는 T5 동적 입력과 CSV 캐시의 수치 대조 및 재현성 진단이다. 실험 결과와 구체적인 후속 작업은 Astra 관리자가 위 상태 파일과 회차 보고서에 기록한다. 학습자의 설명 질문을 포함하고, 계산 검산과 성능 개선을 구분한다.

## 새 세션으로 이어가기

회차가 끝나고 관리자 보고서·상태·다음 작업이 저장된 다음 아래 스크립트를 **해당 완료 회차당 한 번** 실행한다.

```powershell
& '.\automation\Start-NextSession.ps1' -FromRound 'round_001'
```

`-InspectOnly`를 붙이면 프롬프트와 경로만 확인하며 새 세션을 시작하지 않는다. 실제 실행은 Orca의 기존 `DATA AI SHIPPING` workspace에서 새 Codex 세션을 `--model gpt-6-astra --effort high`로 시작하고, 절대 작업 루트를 이 폴더로 전달한다. 이 폴더는 독립 Git 저장소가 아니므로 기존 workspace를 사용한다. 새 Git 저장소를 만들거나 원자료를 복제하지 않는다.

영수증은 `automation/receipts/round_NNN_launch.json`에 저장한다. `accepted=true` 및 `prompt_delivered`는 프롬프트 전달 증거이며, 후속 실험 완료나 목표 달성 증거가 아니다. 같은 출발 회차를 다시 호출하면 이미 성공한 영수증을 반환하고 새 세션을 중복 생성하지 않는다. 실패·모호한 결과는 원본 출력 및 operationId를 확인한 뒤 복구하며 무작정 재실행하지 않는다.

인계 당시의 `NEXT_SESSION.md`와 `STATUS.json`도 같은 영수증 폴더에 회차명으로 보존한다. 이후 최신 상태 파일이 갱신돼도 어떤 작업을 넘겼는지 확인할 수 있다.

현재 회차 관리자가 인계 수락을 확인하면 기존 세션은 종료한다. 새 세션이 다음 회차를 완료한 후 같은 과정을 반복한다. 사용자의 중지 요청이나 실제 외부 차단 조건은 상태와 인계 파일에 남긴다.

## 실행 증거

- `.codex/config.toml` 및 `.codex/agents/`는 새 세션용 요청 기본값이다.
- 회차 관리자 기록은 실제 sub-agent 생성 요청·역할·산출물·확인 한계를 남긴다.
- 새 관리자 세션 생성의 호스트 응답은 `automation/receipts/`에 보존한다.
- 이 구성은 성능 0.7을 보장하지 않으며, 데이터 누출이나 평가자료 재명명으로 점수를 높이지 않는다.
