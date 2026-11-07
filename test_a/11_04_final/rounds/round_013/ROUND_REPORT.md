# Round013 — 실행기 동적 검증·저장기록 검산 완료

승인된 실행기의 smoke, fixture mock, 저장기록 audit를 각 1회 실행해 모두 완료했다. 종료코드 수집 결함의 수정은 이번 유한 실행 범위에서 동적으로 확인됐다. 새 모델 추론·학습·F1 평가는 없으며 목표 micro-F1 0.7은 여전히 미달이다.

## 이전 → 현재 → 다음

Round011은 fixture stderr가 OK여도 exit_code=null/completed=false여서 본 검산을 수행하지 못했다. Round012는 ProcessStartInfo/Process 실행기의 정적 승인을 완료했으나 마감 때문에 동적 실행은 0회였다.

이번에는 round012의 승인 소스 세 파일을 round013으로 복사하고 회차명·출력경로·schema·함수명만 바꿨다. 작성자는 20:47:28UTC에 쓰기를 동결했고 별도 검토자가 원본 승인 해시, 최소 diff, 최종 파일 직접 해시를 확인해 승인했다. 코드를 재설계하지 않아 첫 실행을 세션 시작 약 6분 10초 뒤 시작했다. 다음 명령은 직전 영수증과 동일 승인 map을 관리자가 확인한 후에만 실행했다.

다음 Round014는 round011/M4_CONTRACT와 독립 M4_REVIEW, round012/M4_NEXT_CHECKLIST에 근거한 tiny 합성 head 학습·병합·head-only 재로드 검증이다. 원자료 학습이나 F1 비교로 확대하지 않는다. 현재 저장기록 검산을 반복하지 않으며, 새로운 모델 실행기에 필요한 유한 process smoke/mock만 별도 승인 아래 수행한다.

## 실제 실행 결과

| 단계 | 실행 | 정수 종료코드 | 계산 구간 | 결과 |
|---|---:|---|---:|---|
| process smoke | 1회, 자식2개 순차 | 자식0/7, wrapper0 | 0.2565873초 | 출력 marker·종료·잔존없음 통과 |
| pure fixture mock | 1회 | child0, wrapper0 | 0.4048464초 | clean-live/history-fail 및 live-drift 두 테스트 OK |
| 저장기록 audit | 1회 | child0, wrapper0 | 0.3333715초 | 예상한 여섯 관문과 일치 |

세 단계 모두 completed=true, approval map/live/snapshot 전후 해시 불변, stdout/stderr 수집 완료, owned_process_exited=true, owned_process_residual=false다. timeout·강제 종료·재시도는 0회다. 시간은 runner가 기록한 자식 계산 구간이며 도구 호출 전체 시간이 아니다. 실행 시각은 20:50:23→20:51:00UTC이며 고정 실험마감21:01:14UTC보다 이르다.

승인 map SHA256: `ccb8ada4a66760bfd1a6ae970f395f47f779b9a1829d8011034a7964f624de26`. 로그·실행 사본·claim은 `logs/smoke_01`, `logs/mock_01`, `logs/audit_01`에 있다. 상세 통합값은 `manager/execution_summary.json`, 검산 결과는 `artifacts/provenance_audit.json`이다.

## 저장 검산의 의미와 한계

| round010에 대한 관문 | 예상 | 계산 결과 |
|---|---|---|
| 실행 사본이 승인 소스와 일치 | true | true |
| 현재 live 소스 불변 | false | false |
| 현재 출처 관문 | false | false |
| 저장된 수치 검산 | true | true |
| 감사 기록의 정합성 | true | true |
| 역사 전체 관문 | false | false |

저장 JSON의 2×4 확률을 재계산한 maxabs는 **1.8446231598301388e-6**, 원래 허용오차1e-4 이내이며 두 질의 argmax가 일치한다. float64 해석 후 exact equality는 false다. 이는 기존 확률의 검산이며 새로운 추론이나 선박 분류 성능 평가가 아니다.

출처 실패 원인은 round010 wrapper에 실행 시작 후 두 진단 줄을 추가한 것이다. 실행 사본은 승인본과 같고 progress는 predict_proba_complete/managers_restored에 도달했다. 추가 줄이 있는 조기 실패 분기는 저장 기록상 진입하지 않았다. 이 사실이 과거 쓰기 동결 위반을 없애지는 않는다. round013 자체의 소스 동결 관문 통과와 round010의 현재/역사 실패를 별도로 기록했다.

NPZ·checkpoint 바이트는 읽거나 재해시하지 않았으며 `not_reverified`다. raw/reference CSV/OUTER/holdout 접근, checkpoint load, fit/predict/forward/backward, 설치, 외부 업로드, 공식 제출, 유료 사용은 0이다. 소스·receipt·저장 JSON만 읽었다. 과거 선택13파일의 전후 해시가 불변이며 원자료·이전repo·과거회차·venv 수정은 하지 않았다.

## 자원·역할·학습

초기 RAM4.365486GiB(20:45:18UTC), smoke 직전4.282806GiB, mock4.290630GiB, audit4.329338GiB였다. 각 단계 다른 Python 프로세스는 없었고, 별도 Test B 관리자는 무관한 작업으로 보존했다. stdlib 예상peak100MiB·문서 작업200MiB는 계획 가정이며 실측 peak가 아니다. RAM 보류 없이 순차 계산1개로 끝났다.

관리자 요청과 호스트 turn_context는 gpt-6-astra/high, 작성자·독립 검토자는 gpt-6-luna/xhigh다. 생성 호출은 fork_turns=none, root+보조2=3≤host4, 사용자 보조상한4를 준수했다. `manager/delegation.json`과 `manager/host_turn_evidence.json`은 요청·호스트 메타데이터 증거이며 내부 모델 인증이 아니다.

기술 목표인 종료코드·동시 출력 수집·정상종료 및 저장기록 검산은 달성했다. timeout 강제종료 분기의 동적 검증, 실제 모델 실행 및 전체 입력 출처 재검증까지 입증한 것은 아니다. runner 자체가 smoke 선행을 강제하지 않아 이번에는 관리자의 명시적 선행 관문을 사용했다. 다음 모델 runner의 source review에서 실행 순서와 소유 트리 정리를 명시해야 한다.

학습 목표는 실행 성공·수치 일치·현재 출처·역사 실패를 구별하는 것이다. 질문: audit exit0인데 historical gate가 false일 수 있는 이유는? 실행되지 않은 분기의 소스 변경도 왜 동결 위반인가? 저장 두 질의의 확률 검산이 micro-F1 향상을 증명하지 못하는 이유는? 학습자의 이해 달성과 하드웨어 검증은 미평가다.

개발 OUTER5897 baseline micro-F1 **0.5930133966423605**, macro-F1 **0.5252719738966167**, 미채택 탐색 최고 **0.5933525521451586**을 유지한다. 독립/공식 점수는 null이다.

## 완료·인계

독립 최종 검토는 `review/FINAL_REVIEW.md`, 공유 상태는 STATUS.current_round=round_013, handoff.ready=true, active_workers=[]로 저장한다. NEXT_SESSION은 Round014의 입력·호출 상한·RAM·합성 검증·실패 분기를 명시한다. `automation/Start-NextSession.ps1 -FromRound round_013` 실행 후 수락영수증 정본 `automation/receipts/round_013_launch.json`의 새 세션과 prompt 전달을 확인하는 즉시 이 관리자는 중지한다. 수락 전 다음 세션 실행을 주장하지 않는다.

현재 `orca agent --help`에는 structured-chat 닫기 명령이 없다(`manager/orca_agent_help.txt`). 따라서 앱 전체나 다른 세션을 종료하지 않으며, 필요하면 이 완료 세션 탭만 수동으로 닫는다.
