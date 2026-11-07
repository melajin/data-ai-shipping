# 다음 Astra high 관리자 — Round 007

사용자는 학습·국소 실험·fresh manager 인계를 승인했다. 반복 승인을 요청하지 않는다. 관리자 gpt-6-astra/high, 작성자와 별도 검토자는 gpt-6-luna/xhigh/fork_turns=none만 사용한다. 팀 총4슬롯/보조 사용자상한4명 중 낮은 한도를 지키며 파일별 소유자1명을 정한다. 요청값과 host turn_context를 분리하고 타인의 수정을 되돌리지 않는다.

## 시작·자료·제약

루트 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`에서 AGENTS.md, STATUS.json, CYCLE_PROTOCOL.md와 round006의 ROUND_REPORT.md·author_notes.md·review/FINAL_REVIEW.md·final_review.json·artifacts/result.json·logs/pilot_01/receipt.json·manager/postexit_verification.json·user_ram_recheck_01.json·ram_recheck_after_alternative_work.json을 읽는다. automation/receipts/round_006_launch.json의 수신 세션과 ORCA_AGENT_SESSION_ID를 대조하고 중복실행을 피한다.

원자료 `F:/문제 데이터_수정_1027`, 이전 저장소 `D:/repos/fishing-track-classification`, 공유자료 P는 읽기 전용이다. 새 출력·temp/cache·코드는 root/rounds/round_007 아래다. 기존 venv/site-packages·checkpoint·과거회차를 수정하지 않는다. **이번 회차는 실제자료 배열/확률을 읽거나 실행하지 않는다.** holdout/전체7372행/Test2025/원자료는 열지 않는다. 설치다운로드·외부업로드·공식제출·유료자원은 제외한다.

## 이전 → 현재 → 다음

round005는 입력 복구 후 cache_mode_ 직접접근 오류로 확률 호출 전에 실패했다. round006은 순수mock1회 통과 후 실제모델도 fit 반환과 CPU/FP32/offload/KV 진단을 통과했다. 고정 두 질의 predict_proba 시도1/완료0에서 **가용RAM1.5GiB 관문**으로 중단됐다. 시작4.283466GiB, 관측최저1.392109GiB, sampled소유트리최고3,160,498,176bytes,27.594초다. OS OOM/확률오류/수치재현실패가 관측된 것은 아니다. 후속 생성시각 검사에서 소유프로세스0개이며 child JSON의 STARTED/predict_proba_start는 강제종료 직전 상태로 보존된 것이다.

사용자 재확인에서 RAM4.201679GiB로 회복했으나 시작시와 비슷했다. 동일조건 재시도는0회다. 다음 가설은 **CPU 컬럼 계산의 독립 leading batch축만 작게 나누면 원래 모델·입력을 유지하면서 중간메모리를 줄일 수 있는가**다. pinned CPU inference manager가 자동배치/offload 선택 전에 반환하는 소스근거는 있다. 실제 할당 위치와 최종 필요RAM은 미측정이다.

역사적 반복개발 기준 micro0.5930133966423605/macro0.5252719738966167, 탐색0.5933525521451586은 미채택이다. 신규F1·독립·공식점수는 없다. M4/학습·전체문맥재현은 미해결 관문 뒤다.

## 사용자 지속 지시 — RAM 대기와 재개

모든 작업에서 RAM이 부족하면 다른 가능한 독립 작업을 먼저 진행하고, 이후 RAM을 다시 확인하여 자원 조건이 충족되면 계속한다. 대체작업·시각·가용량·판단을 기록한다. 이번 대체작업은 소스증명/코드작성/단위mock/계절특징 인벤토리/문서화다. 실행중 메모리 증가로 중단됐으면 사용경로와 절감근거도 검토한다. 유한횟수·시간상한을 유지하고 다른 사용자 프로세스는 종료하지 않는다. 대체작업까지 끝났는데 자원이 부족하면 외부제약과 정확한 재개조건을 남기고 RAM조회만 반복하는 세션을 만들지 않는다.

## 실행 전 고정 예산·비교

관리자 최대30분, 큰계산동시1개, threads<=3. 소스수정1세트+별도검토. 순수mock1회<=30초(실패시 근거수정후1회 추가). **소스관문 통과 후 작은 합성비교 프로세스 최대1회/300초**. 시작 가용RAM>=3GiB, 실행중<1.5GiB면 소유자식트리만 중단한다. 실제 계산 시작 후 실패하면 이번회차 재시도0회다. 실제FIT/INNER/OUTER추론·계수학습·F1·모델탐색은0회다.

합성비교는 checkpoint load1회, estimator fit1회, **같은 fitted estimator의 predict_proba2회(원경로1+분할1)**만 허용한다. NumPy default_rng(seed20261105) 정규분포 float32 X_fit32×312, X_query2×312, y_fit=np.tile(arange(4),8)을 만든다. 두 경로에서 같은 배열·순서를 쓴다. estimator는 round006 그대로 seed42/8estimators/batch1/CPU FP32/AMPfalse/FA3false/n_jobs3/kv_cachefalse다. 입력hash·shape·dtype·설정·shuffle을 저장한다. 작은 합성결과를 실제선박/전체3144문맥 동등성·F1로 해석하지 않는다.

환경 `environments/round_004_tabicl_cpu/Scripts/python.exe`(Python3.12.14/TabICL2.2.0/Torch2.6.0+cpu) 재사용. checkpoint `model_cache/tabicl-classifier-v2-20260212.ckpt`,110368038bytes,SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`.

## 1. 소스 관문과 로컬 어댑터

pinned tabicl/_model/inference.py의 InferenceManager.__call__(CPU분기 약1297행), embedding.py의 _compute_embeddings/_inference_with_feature_group/_inference_without_feature_group, encoders.py/layers.py의 batch축 처리, 모델생성부·inference_config.py 및 round004/runtime_author/replay_contract.json을 확인한다. checkpoint 로딩 전에 소스만으로 runtime 컬럼관리자를 식별하고 다음 계약을 작성·별도검토한다.

- 분할은 컬럼/feature의 **독립 leading batch축**만 한다. FIT/질의 sequence축·grouping내부축·feature값/순서·attention context축은 자르지 않는다. target-aware y_train을 해당 batch축에 맞추며 broadcast/shared 텐서는 소스계약으로 구분한다. 비텐서 train_size/embed_with_test는 보존한다.
- 컬럼별 독립계산·정규화·attention/target embedding·shuffle 재조립을 증명한다. 고정 최대chunk16만 사용한다. 순서복원/마지막불완전chunk를 검사하며 list+cat으로 여러벌 쌓지 않는 사전할당출력을 검토한다. output_repeat 의미도 보존한다.
- 해당 estimator의 **컬럼 관리자만** 로컬 래퍼로 감싼다. ROW/ICL·전역클래스·venv파일은 변경하지 않는다. 원관리자 복구가 가능해야 하고 original _prepare_inputs/_run_forward의 CPU/no_grad/AMP 의미를 보존한다. pinned 비공개API 의존성을 해시와 함께 기록한다.
- 증명이 불가능하거나 경로가 다르면 모델비교를 실행하지 말고 원인과 대안을 기록한다. 실제문맥/모델head/estimators/FP정밀도를 임의로 바꾸지 않는다.

순수mock은 분할순서·불완전chunk·공유인수·금지축·shape오류거부를 확인한다. 모델동등성 검증이라 부르지 않는다. 작성자와 검토자가 예상SHA·분할계약·mock을 승인해야 합성계산을 진행한다.

## 2. 합성비교 한 번

round006/manager/run_bounded.py를 round007/manager로 복사해 이 회차 kind/300초/3GiB시작·1.5GiB중단 계약을 구현한다. round006의 taskkill 직후 remaining 문제를 반영해 생성시각이 같은 자식 종료를 제한적으로 확인(최대10초 cleanup)하고 시도/종료확인 시간을 구분한다. 전체timeout은 생성부터 종료확인까지다. source snapshot·실행전SHA guard·PID생성시각·stdout/stderr/RAM곡선·종료코드를 보존한다.

아래 예정파일/명령은 구현·별도검토 후 사용한다.

```powershell
$expected='<round007 승인 synthetic_pair.py SHA256>'
if ((Get-FileHash './rounds/round_007/code/synthetic_pair.py' -Algorithm SHA256).Hash -ne $expected) { throw 'Frozen source changed' }
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_007/manager/run_bounded.py' --kind synthetic_pair --run-id pair_01 --script './rounds/round_007/code/synthetic_pair.py'
```

원경로1회 후 같은 estimator의 컬럼관리자만 바꿔 분할1회 확률을 저장한다. 단계별resource marker와 실제chunk호출shape/최대크기를 남긴다. 판정은 각2×4 finite/[0,1]/행합오차<=1e-5/클래스[0,1,2,3], 원경로대비 **최대절대차<=1e-5 및 두argmax일치**다. exact와 tolerance를 구분하고 실패후 허용오차를 넓히지 않는다. 작은입력의 RAM 수치는 전체문맥 절감 보장이 아니다. 모델재학습·두번째checkpoint로딩은 하지 않는다.

## 3. 사용자 계절 가설 보존

round006/SEASONAL_HYPOTHESIS.md를 읽는다. 사용자는 계절·시간대별 조업형태 차이를 검토하라고 했다. 기존 monthly_repeat는 none_micro seed42 대비 개발+0.0044090/순증26이며 CI에0포함, 현재기준선과 다르다. 자료계약은1–6월이고 date/hour는 시간별요약행 시각이지 좌표별시각이 아니다. 기존 코드·feature-name metadata만 대조해 현재 F156/F304 시간특징 인벤토리를 SEASONAL_FEATURE_INVENTORY.md에 남기는 작업은 RAM대기 중 수행가능하다. protected array/원자료/개별예측은 읽지 않는다. 월별형태·지역·시간대 변화량 가설은 기존 monthly_repeat 반복과 구분하고 이번에는 계절모델을 학습하지 않는다.

## 완료·후속 분기

ROUND_REPORT(이전/현재/다음), 독립검토, EXPERIMENT_LEDGER, STATUS(current_round=round_007,handoff.ready=true,active_workers=[]), NEXT_SESSION을 실제결과로 갱신한다. 학습목표는 batch축/sequence축, 합성동등성/실제재현/F1 차이를 설명하는 것이다.

- 소스+mock+합성동등성 통과: round008에 어댑터동결 후 **동일FIT3144/두질의 저메모리 실제재현1회**를 계획한다. 입력해시·질의·원확률·1e-4판정은 round006/manager/incoming_NEXT_SESSION.md를 따른다. 실제재현 통과 후에만 M4-a 별도설계다.
- 실패: 원인과 변경변수를 좁히며 같은시도 반복 금지. 대체작업후 RAM재확인을 수행하고 실행불가능한 외부제약이면 정확한 재개조건을 기록한다.
- 계절접근은 가설/인벤토리를 보존한 별도통제실험으로 다룬다. 0.7 도달보장·예상성능을 측정값으로 만들지 않는다.

실행가능 후속이 있으면 아래 명령으로 새Astra high에 인계하고 수락영수증을 확인한 뒤 현재작업을 중지한다. 닫기API가 없으면 해당완료세션 탭 수동닫기방법을 기록하며 앱/다른세션은 닫지 않는다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_007'
```
