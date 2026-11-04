# 다음 Astra high 세션 — Round 003

사용자 최신 지시를 반영한 후속: `rounds/round_002/IDEA_REVIEW_AND_ROUND003.md`와 원문 사본 `references/algorithm_variant_ideas.md`를 먼저 읽는다. 3차 계획은 사용자에게 이미 설명했다. **R0: TabICLv2 A의 저장 확률에 대한 판정 규칙 손익 비교**를 수행하고 M4 출력층 변형의 실행 준비를 확인한다. 이전 월별35 특징 우선 분기는 이번 사용자 지시로 뒤로 미뤘다. 새 허가를 반복 요청하지 않는다.

## 시작 및 소유권

AGENTS/CYCLE_PROTOCOL/STATUS/round002 보고서·review·인계 receipt를 확인한다. 현재 세션이 receipt 수신자임을 대조하고 중복 관리자를 만들지 않는다. 관리자 gpt-6-astra/high, 보조 gpt-6-luna/xhigh/fork_turns=none 명시 요청, 실행·검토 담당을 분리한다. 호스트 동시 최대4슬롯을 우선하며 모든 출력은 11_04_final 아래, 원자료와 기존 코드·공유자료는 읽기 전용이다. 보조에게 타인 변경을 되돌리지 말라고 전달한다. 담당 범위는 round003/code+artifacts+logs(실행), review(검토), 공유 상태/계획/보고서(관리자)다.

이번 R0는 신규 신경망 학습·새 원모델 추론 없이 저장된 개발 확률의 판정만 비교한다. 완료된 round002를 반복 학습하지 않는다. historical TabICL의 context/model binary 부족은 유지하며 저장 확률 검산을 원모델 재현으로 부르지 않는다.

## 입력과 사전 감사

입력 prefix P = `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료`.

- seed42/2026 각각 `P/evaluation/seed_{seed}/original_oof_predictions.csv`, `oof_decisions.csv`, `fold_{0,1,2}/inner_predictions.csv`.
- `P/evaluation/trap_factors.csv`, `final_fixed_decision_rule.json`, `P/metadata/classes.json`, `run_settings.json`, `package_validation.json`, `P/splits/development_roles_long.csv`, MANIFEST_SHA256/SOURCE_SHA256. 개발 명부 파일이 없으면 round002 고정 NPZ의 ID/role/y와 대조한다.
- OOF 원본 헤더: rfid_id,p0,p1,p2,p3,y_true,observed_days,fold. INNER에는 fold 열이 없으므로 경로의 fold를 붙인다. 출력 판정 파일에는 기존 배수/원argmax/선택label이 있다.
- 파일 hash를 기존 manifest 및 final_fixed_decision_rule의 INNER hash와 비교한다. ID hash 직렬화는 과거 코드에서 확인하고 임의 규칙으로 불일치를 선언하지 않는다. 5897척 OOF 정확히1회, fold1966/1966/1965, INNER787, 기존 역할·정답·observed_days 일치, 클래스 순서, finite/sum, seed간 명부 일치를 검증한다.
- 기존 배수 2/3/2가 두 seed의 저장 판정을 재현하는지 전체 개발 선박으로 확인한다. 오류 전용 CSV로 전체 F1을 계산하지 않는다.
- 이 자료는 기존에 노출된 개발자료다. holdout 개별 특징·정답·확률, 전체7372 F156/라벨 표, Test2025는 읽지 않는다. 모델·확률 외부 업로드/공식 제출/유료 자원은 제외한다.
- 특징 정의 모순(F156+missing 설명, README의 no-missing-flags, replay_query_shape312)을 코드·메타데이터로 좁혀 기록한다. R0에 F156 행을 읽을 필요는 없다. 원모델 재추론·M4 입력 확정은 별도 검증이다.

## 실행 전 고정할 비교

`rounds/round_003/ROUND_PLAN.md`, `configs/experiment.json`과 source/input hash를 점수 계산 전에 저장한다. 주 질문: **원래 확률은 고정한 채 micro 우선 판정으로 바꾸면 몇 척을 고치고 몇 척을 새로 틀리는가?** 학습 질문: 모델 학습 손실·확률·최종 판정은 어떻게 다르며, 보정 제거의 순손익을 왜 전체 선박에서 봐야 하는가?

비교군은 3개뿐이다: A_raw(argmax), A_old(저장된 fold 배수), A_micro_select(아래 새 정책). 두 seed를 따로 계산하며 평균은 두 seed 지표의 산술평균이다. 확률 평균 앙상블로 바꾸지 않는다.

- 새 정책 grid는 통발 p2 배수 `[1,1.5,2,2.5,3]`, 다른 업종은1이다. seed별·fold별 INNER에서만 고른다. 여러 fold INNER를 풀링하거나 OUTER로 고르지 않는다. 동점은1에 가장 가까운 값, 다시 동점이면 작은 값이다.
- INNER에서 raw 대비 macro-F1 감소없음, 각 클래스F1 감소<=.01, 자연1–7관측일 macro-F1 감소<=.01인 후보 중 micro최고를 고른다. raw(배수1)는 기본 가능후보다. 지원 부족/집단 결측은 숨기지 말고 raw로 복귀한다. label order [0,1,2,3], absent class zero_division=0을 고정한다.
- 과거 training metadata는 고정 zero-shot/context 모델이고 INNER를 신경망 학습/조기 종료에 쓰지 않았다고 기록한다. 이 근거와 실제 생성 코드를 먼저 감사한다. 확인되면 full INNER로 위 정책을 선택한다. 조기 종료/학습에 사용한 흔적이 있거나 불명확하면 새 정책은 탐색 진단으로만 기록하고 원모델 계보의 복구를 우선한다. 단순히 INNER 이름을 나눠 과거 노출을 없앴다고 하지 않는다.
- 선택한6개 배수를 JSON으로 저장·해시 고정한 뒤 OOF에 적용한다. 원확률을 변경하지 않고 decision scores를 calibrated probability로 부르지 않는다.
- 출력: 전체/seed/fold별 micro/macro/weighted F1, 정답수, 네 클래스 precision/recall/F1/support, 혼동행렬, 관측일1–7/8–30/31–90/91+ 구간 및0/미지원 별도, 양방향 연안↔자망·통발 변화. old→raw, old→selected, raw→selected의 gain/loss/net.
- 5000회 seed20261105 vessel bootstrap: 한 번 뽑은 선박 인덱스를 두 seed에 함께 적용하고 각seed 지표차이를 계산한 뒤 평균한다. 동일 선박을 seed마다 독립된2척으로 세지 않는다. paired95%CI는 탐색 편향/해역 의존을 모두 보정하지 않는다.
- 원확률 logloss/multiclass Brier/고정10구간 ECE와 높은 확신오답(원확률max>=.9) 수는 지원 범위에서 진단한다. 판정만 바뀐 실험의 원확률 보정 품질이 개선됐다고 하지 않는다.

## 판정 및 M4 준비

R0 완료조건은 동일 확률·동일 명부 판정 손익의 정확한 검산과 계보 한계 기록이다. 신경망 개선 성공을 전제하지 않는다. 새 정책을 raw보다 나은 확인 후보로 진행할 기준은 두seed 평균micro +.005이상, 두seed 모두 양수, pairedCI 하한>0, 평균macro 감소없음, 각seed 클래스F1/자연1–7일macro 감소<=.01이다. old 대비 이득과 raw 대비 이득을 각각 표시한다. 기준 미충족이면 원확률 또는 기존 정책의 손익을 보고하고 개선을 확정하지 않는다.

계산 후 최대10분만 M4 준비를 조사한다. 알려진 프로젝트/패키지 경로·환경 목록에서 tabicl2.2.0, Torch, checkpoint SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`, FIT 문맥/클래스변환/전처리 증거, 실제 GPU를 확인한다. 광범위한 개인 폴더 검색이나 대형환경 설치·모델 다운로드는 이번 회차에 추가하지 않는다. 문서의 C:/Users/User/Desktop 위치나 RTX3060Ti를 현 머신 증거로 쓰지 않는다.

R0 다음 구조 실험 우선순위는 M4-a(최종 Linear weight만, bias고정) 대 M4-b(rank2, bias고정)다. 충분한 runtime/체크포인트/입력 계보가 있으면 다음 회차를 동일 조건 무변경 출력·gradient·병합/reload 검사와 한fold INNER pilot로 고정한다. 없다면 정확히 부족한 파일/환경·공식 출처·호환계획을 남기고 다음 회차를 유한한 환경 확보/원본 replay로 제한한다. 지원되지 않는 source로 성능을 만들지 않는다. M1/M3/M5나 월별 특징을 동시에 추가하지 않는다. M4 전체3.5–9시간 추정을 한 회차로 압축하지 않는다.

## 예산·종료·인계

관리45분, R0 계산15분, M4준비조사10분, 신규fits0, 동시큰계산1, threads<=3. 이미 설치된 round002 Python 환경을 사용하면 추가 설치 없이 실행 가능하다. 실행기 계획 경로 `rounds/round_003/code/run_round003.py`는 아직 미구현이며 작성/검토/해시 후 실행한다. logs에 명령·PID·실제종료코드·환경·stdout/stderr, artifacts에 정책/명부/예측/결과를 저장한다. reviewer는 별도 코드로 저장확률의 지표와 선택규칙을 검산한다.

데이터/계보 실패면 같은 실패를 반복하지 말고 최소복구 범위만 정한다. 정상 완료 시 ROUND_REPORT/EXPERIMENT_LEDGER/STATUS/NEXT_SESSION을 갱신, current_round=round_003, handoff.ready=true, active_workers 비움. 사용자에게 결과와 다음 검증을 설명한 뒤 실행 가능하면 `& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_003'`를 실행하고 수락영수증 확인 후 종료한다. 유효 개발 .7 관찰은 독립성 감사로 분기하며 official/independent 성능과 구분한다.
