# 모델·실행 증거

## 22:42 갱신 — 두 중간 책임자 모두 실제 시작

초기 계정 목록의 `activeAccountId=null`만으로 Claude를 배정하지 않기로 한 판단은 충분하지 않았다. 실제 worker-start는 성공했다. 현재 실행 증거를 우선한다.

- Terra: `ctx_b30290b5847d`, task `task_f483e5e6120c`, agent codex, model `gpt-6.1-terra`, effort high, structured, ready.
- Sonnet: `ctx_ef73925e6f1c`, task `task_b16860bace23`, agent claude, model `claude-sonnet-5`, effort high, structured, ready.
- 시작 직전 22:42:15 KST 가용 RAM4.30GiB. 두 정적 검토 추정 추가1GiB와 여유0.625GiB로 판단했으며 데이터 처리 작업은 병행하지 않았다.
- 현재 개발자 런타임 지시는 부모 모델을 `gpt-6.1-sol`로 명시한다. 이는 저장 기본 설정과 별개이며 effort의 별도 실행 증거는 없다.

아래는 초기 확인 당시 기록이다. Claude 미배정 및 부모 모델 미확인 상태는 위 갱신으로 대체한다.

확인 시각: 2026-11-05 22:33 KST. 런타임이 반환한 모델 이름과 effort는 Orca 요청·반환 증거다. provider 내부에서 실제로 처리된 모델의 독립 인증으로 확대 해석하지 않는다.

## 총 책임자

- 사용자 요청 역할: GPT-6.1 Sol high.
- 현재 부모 세션의 실제 모델 설정은 이 작업에서 변경되거나 재검증되지 않았다. `.codex/config.toml`은 후속 세션의 기본값으로 `gpt-6-astra / high`를 적고 있으며, 이를 현재 부모 세션의 실행 모델 증거로 쓰지 않는다.

## 하위 작업자

| 역할 | Orca 요청 및 반환 | 상태 |
|---|---|---|
| Luna 결과 계보 감사 | agent `codex`; `gpt-6-luna`; effort `xhigh`; dispatch `ctx_bc9f8a627f63`; task `task_35e74fd20fd3`; mode `structured`; state `ready` | 실행 중 |
| Gemini 사례 의미 감사 | agent `antigravity`; `gemini-3.8-flash`; effort `high`; dispatch `ctx_7594caa8a8ab`; task `task_e95efd14892b`; mode `terminal` (structured chat 불가 반환); state `ready` | 실행 중 |

## 중간 책임자

- 요청 후보: `gpt-6.1-terra / high` (`teta`를 `terra`로 해석). 하위 작업 두 건이 완료된 뒤 독립 검토를 시작한다.
- Claude Sonnet 5: 2026-11-05 22:25 KST 전후 `orca account list` 응답에 `claude.activeAccountId=null`이었다. 이번 라운드에서 Claude 실행을 시도하거나 계정 로그인을 하지 않았다. 따라서 이 모델의 실제 실행 증거는 없다.

## 메모리·병렬 실행

- 최초 확인: 2026-11-05 22:27:02 KST, 가용 RAM 2.66 GiB.
- 작업자 2명 병렬 시작 직전 확인: 2026-11-05 22:33:33 KST, 가용 RAM 2.85 GiB. 대형 실행 프로세스는 없었고 상위 메모리 사용 프로세스는 Explorer 743 MiB, Obsidian 623 MiB, Orca 444/343 MiB, Phone Experience Host 292 MiB, Command Palette 268 MiB, Claude 259 MiB, PowerPoint 250 MiB였다.
- 추정: 정적 문서·코드 검토 worker별 최대 추가 512 MiB, 2명 합계 1 GiB; 운영 여유분 640 MiB. 현재 가용량에서 허용해 병렬 시작했다. 추정은 보장 상한이 아니다.
- 대형 원자료 적재·학습·재계산은 하지 않았다. 하위 작업 결과 뒤 중간 검토자 시작 직전에 RAM을 다시 확인한다.
