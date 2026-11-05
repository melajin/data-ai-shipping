# 2026-11-05 사용자 재개 지시 — RAM 확보 확인, round025 실행

사용자: "램 점유율 확보하고 실험 재개". 이전 관리자가 원인을 조사해 Microsoft SnippingTool 백그라운드 프로세스44개의 working set을 Windows EmptyWorkingSet으로 1회 회수했다. 프로세스 종료0, 앱 상태/캡처 삭제0, 원자료/이전repo 수정0. 작업집합 합계5.66GiB는 공유페이지가 포함될 수 있어 실제독점RAM과 구분한다.

회수 작업 직전 가용1.220GiB, 직후3.227GiB. 다음 실행 직전 재확인2026-11-05T03:38:52.8961425Z 가용3.422374725GiB(진입1.5GiB통과), 독립Python0. 근거: automation/recovery/20261105_capture_working_set_recovery.json 및 20261105_resume_admission.json. RAM이 예약된 것은 아니므로 새 관리자가 각 단계 직전에 다시 확인한다. 반복 trim/watch 루프를 만들지 않는다.

round024는 이미0fit 자원중단회차로 기록 완료했다. 이전 runtime cutoff를 연장하거나 round024 준비를 다시 실행하지 않는다. 이 fresh 관리자는 아래의 기존 인계대로 round025 준비 도구를 실행하고, 별도 Luna 작성자/검토자(gpt-6-luna/xhigh) 검토→새승인→동결→단1회8fit→검산/기록을 실제 수행한다. 모델/특징/분할/숫자관문/저메모리제한은 그대로다. 수락영수증 owner와 전달SHA를 확인하고 중복 관리자나 기존round025가 있으면 조사한다.

---
# Round025 재개 — 먼저 RAM 개선을 확인, S1 미판정 유지

직전 완료: round024. 보고서 rounds/round_024/ROUND_REPORT.md. round024 준비 재실행0, 소스 검토/22개 동결 완료, 진입 RAM 미달로 학습launch0/fit0/모델0/점수없음. current_round=round_024는 완료 기록이다. 새 관리자는 round025를 준비하되 이미 존재하는 round025나 accepted launch receipt가 있으면 중복 실행하지 않는다.

관리자 gpt-6.1-sol/high, 작성자와 별도 검토자 gpt-6-luna/xhigh만 사용한다. 호스트 총4슬롯이 사용자 보조상한4보다 우선한다. 모든 산출물 이 작업 루트 아래, 원자료/이전repo 읽기전용. holdout/Test 개별자료·라벨·예측·평가 추가 접근 금지. 기존 공용 항구 집계 경계 유지. 공식제출/외부업로드/새 유료자원 사용 금지.

## 외부 자원 조건과 재개 명령

가용 RAM>=1.5GiB, 다른 독립 Python 계산0을 시작 직전에 확인한다. round024 마지막 미달값과 새 수치를 시각과 함께 남겨 외부 자원이 실제로 개선됐음을 확인한다. 기준 미달이면 다른 독립 작업 후에만 재확인하고 polling/watch나 새 관리자 연쇄를 만들지 않는다. 사용자 프로세스를 종료하지 않는다. 지금까지 부족했으므로 수락 영수증 없는 다음 세션을 실행중이라고 쓰지 않는다.

RAM 조건이 충족된 뒤 새 관리자 요청:
```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_024'
```
받는 관리자는 영수증owner/수신SHA를 확인하고 아래 준비 도구를 **1회** 실행한다. prepare_round024.py는 재실행하지 않는다.
```powershell
& './environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_024/code_author/prepare_round025.py
```
도구는 round024 승인/동결·무실행 상태,진입RAM/다른Python을 확인하고 새round025에 복사한다. 새 ROUND_PLAN/runtime_contract/copied_inputs와 도구stdout을 확인한다. 목적dir가 이미 있거나 이전claim/학습흔적이 있으면 덮어쓰거나 무조건 재실행하지 말고 원인을 확인한다. 사용자 모델·예산·저메모리 제한 변경은 하지 않는다.

## 검토 → 동결 → 단1회 학습

새 Luna 작성자와 검토자가 복사·의도patch·자료경계·현재sourcehash를 검토한다. 검토자가 rounds/round_025/review/gate_approved_sources.json을 생성한 뒤에만:
```powershell
& './environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_025/manager/freeze_stage.py --stage s1_gate --approval rounds/round_025/review/gate_approved_sources.json
```
동결 성공 확인 후 별도 호출:
```powershell
& './environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_025/manager/launch.py --stage s1_gate --seconds 900 --python 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' --script rounds/round_025/code/run_gate.py -- --run-gate
```
FIT3144/4CV/seed42,304열 vs328열,8fit단1회,재시도/튜닝/원자료재스캔/full3fold/S2훈련0. 후보>=1833 AND 후보−엄밀동일절차기준>=16. 고정1817참고를새엄밀기준과혼동하지 않는다. proxy여서 원래 전체geometry S1 full실행은 자동허용되지 않는다.

진입1.5GiB/단계1.0GiB/예상peak0.5GiB/owned RSS상한0.75GiB/비상가용0.5GiB,1프로세스·thread1/n_jobs1·수치라이브러리thread1·BELOW_NORMAL_PRIORITY_CLASS·단계/월/모델별del+gc. 관리45분·합계계산1800초·학습job900초·검산각180초(3단계) 유한예산을준수한다. sourcefreezehash를각launch전재대조한다.

## 정상 완료 검산과 후속 분기

8fit와gate_result가있을때만 아래를 각각별도호출로순차실행한다. 각직전RAM확인,앞단계exit0 확인. 동일런처감독을사용한다.
```powershell
& './environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_025/manager/launch.py --stage verify_gate --seconds 180 --script rounds/round_025/review/verify_gate_result.py -- rounds/round_025/artifacts/gate
& './environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_025/manager/launch.py --stage reinfer --seconds 180 --script rounds/round_025/review/reinfer_saved.py -- rounds/round_025/artifacts/gate
& './environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_025/manager/launch.py --stage supplement --seconds 180 --script rounds/round_025/code_author/supplement_metrics.py -- rounds/round_025/artifacts/gate
```
두검산pass후에만supplement. 8개모델재추론maxdiff<=1e-7/argmax완전일치,paired gain/loss/net/5000bootstrap(seed20261105)/관측일구간/class0·3손익/class1·2 precision,F1,FP전이를보고한다. 개발FIT진단·반복노출OUTER5897·독립·공식점수를분리한다. 숫자관문미달이검증되면 다음회차S2준비전용(학습0),통과면제한proxy확장계획. 자원/코드/시간중단은성능기각이아니며부분산출/정확fit수를보존하고원인없는재시도를하지않는다.

완료시ROUND_REPORT/STATUS/EXPERIMENT_LEDGER/NEXT_SESSION갱신,current_round는완료round_025,handoff.ready=true. 다음실행가능하면Start-NextSession -FromRound round_025의수락영수증확인후작업종료. 외부제약이지속되면정확조건과재개명령을남긴다.
