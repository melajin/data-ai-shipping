# 다음 Astra high 관리자 — Round 006

사용자는 학습·국소 실험·fresh manager 인계를 승인했다. 반복 승인을 요청하지 않는다. 새 사용자 지시: 매 회차 보고서에 **이전 회차 대비 변경점 → 이번 진행·개선 결과 → 다음 회차 변경사항**을 명시하고, 다음 fresh session의 수락 영수증을 확인한 뒤 완료한 회차의 세션 창을 닫고 중지한다. 이 절차로 micro-F1 0.7을 추구하되 점수 조작·무한 동일 실패·자원 관문 위반은 하지 않는다. 개발·독립·공식 점수는 구별한다. 해당 세션 하나만 닫으며 앱 전체나 다른 작업 창을 종료하지 않는다. 닫기 API가 없으면 지원 여부와 정확한 미완료 조치를 기록하고 현재 관리자는 종료한다.

## 시작·역할·제약

루트 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`에서 AGENTS/CYCLE_PROTOCOL/STATUS, round005의 ROUND_REPORT·PLAN_AMENDMENT_01·review/FINAL_REVIEW.md·final_review.json·author_notes.md, logs/pilot_01/receipt.json·stderr.txt·source/replay_inner_pilot.py를 읽는다. 인계 receipt 수신 세션과 ORCA_AGENT_SESSION_ID를 대조하고 중복 실행을 피한다.

관리자 gpt-6-astra/high, 보조 gpt-6-luna/xhigh/fork_turns=none만 사용하며 작성자와 검토자를 분리한다. 팀 호스트 총4슬롯과 보조 사용자상한4명을 지킨다. 요청값/host turn_context를 구분해 저장한다. 파일 소유자를 지정하고 타인의 수정을 되돌리지 않는다. 검토한 소스의 예상 해시를 실행 시 강제하며 승인 후 작성자가 수정하지 않게 동결한다.

새 산출·temp/cache/offload는 root 아래 rounds/round_006에 둔다. 원자료 `F:/문제 데이터_수정_1027`, 이전 저장소 `D:/repos/fishing-track-classification`, 공유자료 P는 읽기 전용이다. 전체7372행 F156/labels/components, holdout 개별 특징·라벨·확률, Test2025, 원자료를 읽지 않는다. holdout 독립성 이력·평가계획 관문은 미해결이다. 외부 업로드·공식 제출·유료자원은 제외한다.

## 이전→현재→다음

- round004는 CPU 합성 smoke와 입력 계보만 확인했고 원순서 입력 export는 미실행이었다.
- round005는 원순서 FIT3144×312/INNER787×312 float32 입력을 export 1회(2.672초)하고 독립검산1회(2.172초)로 두 배열·순서·역할·라벨·클래스·결측변환을 확인했다. **재export하지 않는다.** protected 전체 과거 원행을 재생성한 증거는 아니다.
- frozen FIT/INNER 해시는 숫자정렬+LF연결(끝LF없음)의 **집합** 해시다. ordered BASE JSON digest와 같지 않다. round005 실행 전 정정을 보존하고 직렬화 후보 탐색을 반복하지 않는다.
- pilot1회는 **24.125초 후 종료코드1**. `estimator.fit` 반환 뒤 validator의 기록 dict가 `model.cache_mode_`를 직접 읽어 AttributeError가 발생했다. pinned classifier는 `kv_cache=False`일 때 이 속성을 만들지 않는다. 앞의 getattr guard와 기록 접근의 불일치를 작성·검토가 놓쳤다. 모델 예측 실패나 RAM 부족이 아니다.
- checkpoint/문맥fit1회, 계수학습0, predict_proba 시도0/완료0, F1 0이다. CPU/CUDA 확률 차이는 미측정이다. RAM시작3.572868GiB/최저3.077396GiB, sampled process-tree peak572891136bytes, timeout/RAMkill없음, 최종 소유프로세스0. 이는 추론 전 비용이다.
- 다음 round006은 **선택적 진단 속성 처리 오류를 고쳐 검증한 뒤, 동일한 두 질의의 원출력을 한 번 재현**한다. M4/모델학습/성능평가는 아직 하지 않는다.

역사적 반복개발 기준은 micro0.5930133966423605/macro0.5252719738966167, 탐색0.5933525521451586은 미채택이다. 독립·공식 점수는 없다. 참고 docs/20261105_검증자료_PDF반영_기술진단_보강보고서.md의 .628/.669/.708은 미측정 제안이다.

## 실행 전 유한 예산

- 관리자 최대30분, 동시 큰 계산1개, threads≤3.
- source 수정1세트·별도검토. 모델 패키지/체크포인트를 불러오지 않는 validator mock 검사1회≤30초. 실패 시 근거 있는 수정+검사1회만 추가 허용한다.
- 실제 pilot **최대1회/600초**, 프로세스 생성부터 종료 확인까지. FIT3144 전부, 원INNER 앞2개, seed42, estimators8, batch1, CPU FP32, AMP/FA3false, n_jobs3, offloadauto, kv_cachefalse, 자동다운로드false.
- 직전 가용RAM≥3GiB, 실행중<1.5GiB시 소유 자식트리만 중단. 다른 사용자 프로세스 종료 금지. RAM미달/timeout/API오류면 이번회차 pilot 재시도0회.
- checkpoint load1, pretrained 문맥fit1, predict_proba1호출. 새계수학습/F1/OUTER추론/질의재선정/탐색/설치다운로드/기존 합성smoke반복0회.

환경 `environments/round_004_tabicl_cpu/Scripts/python.exe`(Python3.12.14/TabICL2.2.0/Torch2.6.0+cpu)을 재사용한다. checkpoint는 root/model_cache/tabicl-classifier-v2-20260212.ckpt, 110368038bytes, SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`이다.

## 1. 검증된 입력 복사

round005/artifacts/context_export_attempt_001의 다음 두 파일을 round006/artifacts/context_export_attempt_001로 바이트 복사하고 해시 보존을 확인한다. export_result.json과 review/independent_context_check.json도 provenance 참고로 보존한다. exporter와 전체 배열 재검산은 반복하지 않는다.

| 파일 | SHA256 |
|---|---|
| fold0_seed42_context.npz | 9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5 |
| query_freeze.json | 6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef |

고정 queryIDs는 `["36001915","31703435"]`, ordered query digest는 `7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969`다. 이미 원확률 두 행을 읽은 이력을 보존한다. 다른 질의로 바꾸지 않는다.

## 2. API 수정·검증

실제 실행사본 round005/logs/pilot_01/source/replay_inner_pilot.py(SHA256 `b57f6c764d4b833451714d4dfcfa328ed3facecaf6f9a93a0198da8b17c4b860`)를 round006/code로 복사한다. round005는 수정하지 않는다.

`cache_mode_` 기록을 안전한 getattr로 바꾸고 hasattr 여부도 남겨 부재와 명시적None을 구별한다. model_kv_cache_ 등 다른 진단 속성도 pinnedsource의 상태별 생성 조건과 대조한다. **모델 구조·estimator설정·shuffle·확률계산은 변경하지 않는다.** fit 반환 직후 별도 staged 기록을 저장해 후속 진단 오류가 완료 단계 증거를 지우지 않게 한다.

ROUND 경로 상수만 round006으로 변경한다. copy한 freeze의 역사 schema `round005_frozen_inner_queries.v1`은 입력계약으로 유지하거나 명시적 호환처리를 한다. 파일 전체의 round005 문자열을 무차별 치환해 schema/근거까지 바꾸지 않는다. 경로 검사를 통과하도록 위의 복사된 round006 입력을 사용한다.

mock은 진단함수만 가져와 모델 패키지/체크포인트 없이 검사한다. 정상 kv_cacheFalse/model_kv_cache_None/**cache_mode_부재**가 성공해야 한다. present-but-None도 구별해 기록한다. 잘못된 CPU/AMP/FA3/offload/KV 설정은 거부해야 한다. 최소 부재·명시적None·실제설정위반을 포함하고 검토자가 기대동작을 독립확인한다. 이를 모델 forward 성공이나 새로운 합성smoke로 부르지 않는다.

실제 MgrConfig는 `.items()`로 읽는다. COL offload='auto', ROW/ICL offload=False, 세stage CPU/AMPfalse/FA3false, estimator kv_cacheFalse가 pinnedsource 계약이다. 과거 명시 설정/버전 기본값 구분은 round004/runtime_author/replay_contract.json을 유지한다.

## 3. 한 번의 고정 replay

round005/manager/run_bounded.py(SHA256 `a7ebf611656675404d221e24172f58384bd5f6b046839e59bddb298ae8abab1d`)를 round006/manager로 복사하고 ROUND 경로만 변경한다. source snapshot을 직접 실행하고, 실제 승인 SHA를 호출부 또는 argument로 강제한다. venv launcher와 실제Python의 PID·생성시각·프로세스트리를 추적하며 stdout/stderr/RAM곡선/종료후시간/종료코드를 보존한다. 실행별 기록을 덮어쓰지 않는다.

최종검토 후 실제 SHA를 넣어 다음 명령을 한 번 실행한다.

```powershell
$expected = '<round006 최종승인 pilot SHA256>'
if ((Get-FileHash './rounds/round_006/code/replay_inner_pilot.py' -Algorithm SHA256).Hash -ne $expected) { throw 'Frozen source changed' }
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_006/manager/run_bounded.py' --kind pilot --run-id pilot_01 --script './rounds/round_006/code/replay_inner_pilot.py'
```

context/freeze hash와 두 ID 검사 뒤 공유 P/evaluation/seed_42/fold_0/inner_predictions.csv의 해당2행 p0..p3만 읽는다. 앞2행 ID가 다르면 검색·교체하지 말고 중단한다. INNER 라벨은 모델/선택/F1에 사용하지 않는다. 통발배수/decision score가 아닌 원확률을 비교한다.

finite/범위/행합오차≤1e-5/클래스순서가 맞고 두질의 모두 **최대절대차≤1e-4 및 argmax일치**면 작은replay PASS다. exact equality와 tolerance를 구별한다. 원확률/새확률/질의별차이/호출시도·완료수를 저장하고 재호출하지 않는다. 이것은 F1/성능채택 관문이 아니다.

## 종료·다음 인계

보고서에 이전 대비 변경점/이번 결과와 개선/다음 변경을 명시한다. ROUND_REPORT·독립검토·EXPERIMENT_LEDGER·STATUS(current_round=round_006,handoff.ready=true,active_workers=[])·NEXT_SESSION을 실제 결과로 갱신한다. 재현 통과 후에만 M4-a의10출력head 유지/활성4클래스slice/shuffle역변환/무변경·gradient·reload를 별도 유한회차로 설계한다. 이번에 자동확장하지 않는다.

자원부족이 반복되고 다른독립작업이 없으면 같은RAM확인만 하는 세션을 만들지 말고 외부제약·재개조건을 남긴다. 목표미달이고 실행가능한 다음작업이 있으면 아래 명령으로 새Astra high에 인계, 수락영수증 확인, 완료세션만 닫고 중지한다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_006'
```
