$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $taskRoot
$a=Get-Content -Raw -Encoding UTF8 'rounds/round_011/artifacts/provenance_audit.json'|ConvertFrom-Json
$m=Get-Content -Raw -Encoding UTF8 'rounds/round_011/logs/mock_01/receipt.json'|ConvertFrom-Json
$r=Get-Content -Raw -Encoding UTF8 'rounds/round_011/logs/audit_01/receipt.json'|ConvertFrom-Json
$mismatches=@($a.live_source_checks|Where-Object {-not $_.match})
$branch=$a.wrapper_source_diff_and_branch_progress.root_identity_capture_failed_branch
$report=@"
# Round 011 — 출처 검산 완료와 M4 합성 계약

round010의 실행사본 보존과 저장 확률 재현 통과를 확인했고, live wrapper 변경에 따른 과거 전체관문 실패를 그대로 보존했다. 모델 재실행·새 F1은 0회다. 목표0.7은 미달이며 기존 반복노출 개발 OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 탐색미채택0.5933525521451586을 유지한다. 독립·공식 점수는 null이다.

## 이전 → 현재 → 다음

이전 round010은 실제 FIT3144×312/INNER2 수치재현을 얻었지만 실행 중 wrapper가 바뀌었다. 이번에는 모델을 돌리지 않고 승인map·실행사본·live·receipt·진행journal·저장2×4확률을 독립 검산했다. 다음 round012는 검토된 M4-a/b 마지막 층의 합성 무변경·gradient·병합·head-only 재로드를 한정 실행한다. 실제 선박 학습·전체 모델 integration·F1 평가는 아직 아니다.

## 실행 조건과 실제 결과

관리자20분, 순수mock 최대2회(두 번째는 결함수정 때만), 저장기록 프로그램 검산1회, 각각30초 상한을 실행 전에 고정했다. 실제 mock은 최초1회, 저장기록 검산1회이며 추가mock/실제재시도0이다. 실행 전 작성자가 쓰기중지를 ACK하고 독립 검토자가 새3파일 승인map을 작성했다. 관리자 PowerShell wrapper와 두 Python 파일을 snapshot·전후hash로 확인했다. Windows venv redirector를 피하기 위해 pyvenv.cfg의 같은 기반 Python3.12.14를 직접 -B -S로 실행했다. 모델패키지 import0, venv수정0.

| 검산 | 실제 계산값 |
|---|---|
| mock | exit $($m.exit_code), $($m.elapsed_seconds)초, clean-live/history-fail 및 live-drift fixture 2개 |
| 저장기록 audit | exit $($r.exit_code), $($r.elapsed_seconds)초, integrity=$($a.audit_integrity_passed) |
| 승인 실행사본 | $($a.executed_snapshot_matches_approved) |
| 현재 live 소스 불변 | $($a.live_source_unchanged), 재해시 $($a.live_source_checks.Count)개 중 불일치 $($mismatches.Count)개 |
| 현재 소스 관문 | $($a.current_source_gate) (허용된 재해시 소스 범위만) |
| 저장 수치 관문 | $($a.saved_numeric_replay_passed), maxabs1.8446231598301388e-6≤1e-4 |
| 과거 전체 관문 | $($a.historical_overall_gate), 소급 변경 없음 |
| 확률 세부 | argmax[0,1] 일치, exact=false, float64 행합 최대오차5.541369318962097e-8≤1e-5 |
| RAM 실행 직전 | mock $($m.available_ram_gib_before)GiB / audit $($r.available_ram_gib_before)GiB |
| 소유 프로세스 종료 | mock $($m.owned_process_exited) / audit $($r.owned_process_exited) |

stdlib 예상peak≤100MiB는 작은JSON/1MiB streaming buffer 근거의 계획 가정이며 실제peak 측정값이 아니다. 초기 가용4.2701GiB, 실행준비 재확인4.1974GiB였고 다른Python계산0이었다. RAM부족 보류는 발생하지 않았다. audit은 NPZ와checkpoint를 읽거나 재해시하지 않았으며 그 항목은 not_reverified로 남겼다. 별도 PowerShell의 저장JSON 산술 교차확인도 동일 수치였으나 새 추론이 아니다.

## 사건 검산과 동결 규칙

승인/mock/pilot wrapper사본 SHA c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210, live SHA c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867를 분리했다. diff는 기존 root_identity_capture_failed 분기 안에 진단2줄이 추가된 것이다. saved progress의 predict_proba_complete/managers_restored와 child PILOT_COMPLETE로 해당 조기반환 미진입 판정($($branch.entered_by_pilot))을 뒷받침한다. 이 사실은 소스동결 위반을 없애지 않는다.

mock의 clean은 현재live만 승인본인 조건이다. fixture가 담은 과거실패는 clean-live에서도 false로 유지한다. 따라서 검산프로그램 성공, 현재소스관문, 과거전체관문은 서로 다른 값이다. 기존회차/manifest/receipt/live를 복구·수정하지 않았다. FREEZE_PROTOCOL.md는 candidate전달후 쓰기중지, 독립승인, exact-map mock, 실행사본·live 전후대조, 실행중변경은 다음버전으로 이관하는 규칙을 명문화한다.

## M4 준비 계약과 한계

소스와 과거 smoke metadata로 마지막 Linear W[10,1024],bias[10], 활성첫4출력, p[y]와 out[...,p] 복원, logits평균후 temperature0.9 softmax, 추론no_grad 차단을 확정했다. 현재 source hashes와 근거행은 m4_contract/source_evidence.json 및 M4_CONTRACT.md에 있다. incoming의 references/algorithm_variant_ideas.md는 rounds/round_002/references 아래 실제사본으로 찾았다.

다음은 context16×8/target4×8 합성, checkpointload1/fit1/predict1/최대4 native forward로 H를 얻고 외부head사본만 학습한다. a는 W만, b는 rank2 A/B만, bias고정·SGD각2step·head평가최대12회·backward4회. 전체180초와 시작RAM3GiB/중단1.5GiB, 모델실행1회/재시도0이다. head-only merge/reload로 검증하며 실제FIT학습/전체모델통합/성능상승을 주장하지 않는다. 소스기반 계약은 review/M4_REVIEW.md에서 독립 승인했다.

## 학습과 인계

기술목표는 출처검산과 다음구현계약 완성이다. 학습목표는 수치정확성·출처무결성·성능평가가 다른 관문임을 설명하는 것이다. 질문: 수치가 맞아도 변경된 실행원본을 실패로 남기는 이유는? p[y]와 out[...,p]는 왜 짝인가? B=0에서 첫 A gradient0이 정상인 이유는? context/target을 나눈 뒤 표현을 만드는 이유는? 학습자이해·하드웨어동작은 평가하지 않았다.

호스트 turn_context는 관리자 gpt-6-astra/high, 별도작성자·검토자 gpt-6-luna/xhigh를 기록한다. 요청값과 호스트메타데이터를 manager/delegation.json과 host_turn_evidence.json에 보존했으며 내부모델인증으로 표현하지 않는다. 원자료/이전저장소/과거회차/venv변경, 외부업로드·공식제출·설치·유료사용0이다.

STATUS.current_round=round_011, handoff.ready=true, active_workers=[] 및 LEDGER/NEXT_SESSION을 갱신한 뒤 fresh Astra high를 시작한다. 수락의 정본은 automation/receipts/round_011_launch.json이다. 수락 확인 뒤 기존 관리자는 중지하며 shared STATUS를 다시 쓰지 않는다. 현재 CLI에 structured-chat닫기명령이 없어 필요하면 완료세션 $env:ORCA_AGENT_SESSION_ID 탭만 수동으로 닫는다.
"@
$report|Set-Content -Encoding UTF8 'rounds/round_011/ROUND_REPORT.md'
Write-Output 'ROUND_REPORT.md saved from actual audit receipts'
