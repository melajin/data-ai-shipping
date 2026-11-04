# 다음 Astra high 관리자 — Round 005

사용자는 학습·국소 실험·새 관리자 인계를 승인했고, round004 도중 “램 확인하고 할수있는거 다해”라고 지시했다. 반복 승인을 요청하지 않는다. 인계 receipt의 수신 세션과 ORCA_AGENT_SESSION_ID를 대조하고 중복 실행을 피한다.

## 시작·역할·제약

작업 루트 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`에서 AGENTS/CYCLE_PROTOCOL/STATUS, round004 ROUND_REPORT 및 review 최종검토, context_recovery의 코드/준비결과, runtime_author/replay_contract.json을 읽는다. 관리자 gpt-6-astra/high, 보조 gpt-6-luna/xhigh/fork_turns=none만 사용하며 작성자와 검토자를 분리한다. 관리자 포함 호스트4슬롯, 사용자 보조 상한4명을 지킨다. 파일 소유자를 지정하고 타인 변경을 되돌리지 않는다. 요청과 host turn_context 증거를 기록한다.

모든 새 산출·cache·temp·bytecode는 root 아래, 새 산출은 rounds/round_005에 둔다. 원자료 `F:/문제 데이터_수정_1027`, 이전 저장소 `D:/repos/fishing-track-classification`, 공유 P는 읽기 전용이다. round004 결과를 덮어쓰지 않는다. 보호 holdout 개별 특징·라벨·확률, 전체7372행 F156/train_labels/components train표, Test2025, 원자료는 읽지 않는다. 전체표를 읽은 후 개발행만 거르지 않는다. 외부 업로드·공식 제출·유료 자원·실선 운용은 없다.

## 완료 상태

- Python 환경: `environments/round_004_tabicl_cpu/Scripts/python.exe`. Python3.12.14/Torch2.6.0+cpu/TabICL2.2.0/NumPy2.3.5/sklearn1.7.2. 설치150.437초, pip check 정상. freeze/라이선스/wheel해시는 round004/environment에 있다. 재설치하지 않는다.
- 체크포인트 `model_cache/tabicl-classifier-v2-20260212.ckpt`, 110368038bytes, SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`.
- 처음 RAM2.196GiB로 실행하지 않았으나 사용자 재확인 후 실행 직전4.045GiB로 회복됐다. 합성16FIT+4query/312float32/4클래스/1estimator 검사는 **13.047초에 종료코드0**. CPU/FP32, 계수27,552,258개, decoder512→1024→10, 확률행합 허용1e-5, 클래스역변환, 반복확률 최대차0, gradient없음을 확인했다. peak working set726.20MiB다. 실제3144행 FIT 문맥의 비용으로 외삽하지 않는다. **이미 통과한 합성 smoke는 반복하지 않는다.**
- 개발5897척 NPZ 세fold의 해시·첫156열 이름/순서·역할/라벨·vocabulary FIT-ID가 맞았다. 여섯 saved median 비교는 최대차2.84217e-14로 허용1e-10 내다. raw156+missing156의 float32 후보변환12개 hash가 있다. 이것은 roster 순서이며 모든 과거 원행 값과 원확률의 재현은 아니다.
- P/splits/splits_original.json은 ID명부 metadata다. SHA가 frozen decision rule의 split_manifest_sha256 및 seed42 parent-fingerprint의 work/splits.json SHA와 일치하는 근거를 찾았다. 이 파일의 순서 있는 fold0 fit_ids/inner_ids로 원문맥을 복구할 수 있다. 알려진 holdout 재사용 flag는 true이며 새 독립 평가자료라고 부를 수 없다. 상세 노출 이력 확인과 평가계획 없이 holdout 개별값을 읽지 않는다.
- `rounds/round_004/context_recovery/build_context.py`가 준비 중 검토에서 fold별명부 dict 덮어쓰기 등을 지적받았다. 그 결과와 최종수정·precheck 상태는 해당폴더와 review/context_precheck*를 우선 확인한다. **round004에서는 이 exporter를 실행하지 않았고 export NPZ도 아직 없다.** 이전 진단처럼 로그를 덮어쓰지 말고 실행별 소스/입력hash·PID·종료코드·stdout/stderr를 보존한다.
- 역사 LightGBM5seed 기준은 반복개발 OUTER micro .5930133966423605/macro .5252719738966167. round003 TabICL의 유사 수치는 별도 결과이며 판정변경은 미채택이다. 이번까지 신규 F1·독립·공식 점수는 없다.

## 이번 회차 목표·실행 전 한도

**원래 순서의 개발 입력을 저장한 후, 고정 소수 INNER 질의의 원확률 재현과 CPU 자원비용을 한 번 측정한다.** 성능 튜닝이나 출력층 학습 회차가 아니다.

- 관리자 최대35분. 입력 export1회와 필요시 근거 있는 수정1회(각60초), 독립검산1회.
- 실제 데이터 원모델 pilot **최대1회/600초**. FIT는 fold0의3144척 전체, 질의는 원래 INNER 순서 앞2척, seed42,8estimators,batch1,threads<=3. 다른query나seed로 다시 고르지 않는다.
- 실행 직전 가용RAM>=3GiB, 동시 큰 계산1개. 실행 중 가용RAM<1.5GiB면 해당 자식 프로세스만 중단하고 이유·부분결과를 저장한다. 타 프로세스를 중지하지 않는다. 프로세스 생성부터 시작하는 timeout, 종료 후 실제 경과 확인, stdout/stderr와 staged 결과를 보존한다.
- 새 계수학습0, F1평가0, 하이퍼파라미터 탐색0, OUTER 원모델 추론0, 설치·다운로드0. 실제 INNER2개 확률 비교만 허용한다.
- 자원관문 미달, timeout, API 오류 시 같은 pilot를 이번 회차에 재실행하지 않는다. 입력복구가 실패하면 모델 pilot0회로 끝내고 정확한 원인을 남긴다.

## 1. 원래 순서의 개발 전용 입력 산출

P=`D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료`.

허용: P/code·metadata, seed42/fold0 training/preprocessor/parent_fingerprint, development_roles_long.csv, ID 전용 splits_original.json, evaluation/final_fixed_decision_rule.json. 기존 개발 확률은 질의가 고정된 뒤 비교용으로만 읽는다.

특징 입력: `D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/artifacts/exp01/fold_0_features.npz`, SHA256 `858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95`.

round004 exporter를 round005/code/build_context.py로 복사하고 **출력 OUT 경로를 round005/artifacts로 바꾼다**. ROOT/P를 정확하게 확인한다. 명부는 outer_fold/fold==0으로 먼저 제한한 뒤 ID dict를 구성해야 하며 라벨 인덱스와 역할 인덱스를 혼동하지 않는다. 미해결 precheck 지적을 모두 수정하고 별도 검토를 받는다. 입력 NPZ의 고정hash, ID중복/분할서로소/dev-holdout ID비중첩/역할/라벨/열순서/median kind를 강제한다. ID명부의 holdout ID는 분리 확인에만 쓰며 특징·정답·확률을 읽거나 export하지 않는다.

원코드 `.loc[fold['fit_ids']]`/inner_ids 순서를 사용한다. split manifest의 정확한SHA 연결과 fold0INNER 목록의 BASE.digest_json 결과를 frozen rule의 inner_ids_sha256와 **한 번** 직접 비교한다. 맞출 때까지 정렬을 바꿔 탐색하지 않는다. 실패하면 중단한다.

saved median156개로 `missing=~isfinite(x)`, `where(missing,median,x)`, `c_[imputed,missing].astype(float32)`를 수행한다. FIT3144×312, INNER787×312, ordered IDs/labels/feature_names/classes와 manifest를 저장한다. 원래 INNER 앞2개 ID를 정답·예측·오류 여부와 무관하게 고정하고 query ID hash를 남긴다. 검토자는 원NPZ에서 일부 대치값·결측표시, 전체배열bytehash, 순서/멤버십/클래스 대응을 별도 계산한다. 원래순서와 roster순서의 해시 차이는 값 차이와 행순열 차이를 분리한다.

예정 명령(복사·OUT 수정·검토 후 실행):
```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_005/code/build_context.py'
```

## 2. 단 한 번의 실제 소수 질의 replay

`rounds/round_004/runtime_author/replay_contract.json`의 확인값과 기본값 가정을 따른다. 원실행은 CUDA, 이번은CPU라는 변경을 명시한다. 명시된 원설정은8estimators,batch1,seed42,use_amp=false,use_fa3=false,n_jobs3,offload_mode=auto,명시적 checkpoint/auto_download=false다. tabicl2.2.0 기본값에서 norm_methods=None→[none,power], feature-shuffle latin, class-shuffle shift, softmax_temperature .9, average_logits=true,outlier4,kv_cache=false 등이 나온다. 이를 과거 metadata에 저장된 값과 구분한다. 디스크 offload 경로는 round005 아래로 지정한다.

원래는 전체INNER787행을 한 번에 질의했다. source 검토상 FIT에서 전처리를 적합하고, embed_with_test=false, attention keys/values가 FIT로 제한되어 질의별 수학적 독립성을 지지한다. batch_size1은 질의수가 아니라 ensemble-view 차원이다. 그러나 2질의CPU와787질의CUDA의 수치 동등성은 아직 미검증이다. 이번 pilot가 그 차이와 자원비용을 실제로 확인한다.

작성자는 `rounds/round_005/code/replay_inner_pilot.py`와 timeout/RAM wrapper를 구현하고 별도 검토 후 실행한다(현재 미구현). FIT라벨만 fit에 넣고 INNER라벨은 모델/선택에 넘기지 않는다. 실제 fit은 pretrained 문맥 바인딩이며 계수학습이 아니다. query IDs를 먼저 동결한 후 해당2개의 저장 원확률 p0..p3만 가져온다. 통발배수나 decision_score를 원확률로 비교하지 않는다.

**사전 판정:** finite/범위/행합/클래스순서가 맞고, 두질의 모두 원확률 대비 최대절대차<=1e-4 및 argmax 일치일 때 작은 replay 관문 통과다. 정확 bitwise일치와 tolerance일치를 구분한다. 이것은 성능 채택 관문이나 F1점수가 아니다. 불일치하면 입력·문맥순서·전처리·라이브러리/CPU-GPU·querygroup 차이를 원인 후보로 기록하고 같은회차에서 추측 수정/재실행하지 않는다.

명령 인터페이스 예시(구현 후 wrapper로 감싸기):
```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_005/code/replay_inner_pilot.py' --context './rounds/round_005/artifacts/fold0_seed42_context.npz' --output './rounds/round_005/artifacts/replay_result.json'
```

이1회 안에서 checkpoint 로드·fit·predict_proba1호출만 수행한다. GPU원출력과 비교하는 것이며 CPU동일입력 재호출을 추가하지 않는다(합성 재호출 검사는 이미 통과). full3144 FIT를 임의 축소한 값을 원모델 재현이라고 부르지 않는다. CPU시간/벽시계/RAM곡선/peak·실제device/클래스 및 feature/class shuffle 상태를 기록한다. 실제파라미터훈련·출력층수정·M4는 하지 않는다.

## 결과·후속·인계

산출: ordered context NPZ/manifest, 고정질의2개와 hash, replay코드·실행증거·확률차이/자원·독립검산, ROUND_REPORT/EXPERIMENT_LEDGER/STATUS/NEXT_SESSION. 기술검증과 학습자 이해를 구분한다.

통과하면 다음 회차의 M4-a/b 무변경/gradient/병합/reload 및 한fold INNER pilot를 별도 유한 계획으로 구체화한다. 실패하면 원인을 좁힌 새 가설만 다음 회차로 넘긴다. 자원 부족이 반복되고 가능한 다른 독립작업이 없으면 같은관문 확인만 하는 세션을 계속 만들지 말고 외부제약·정확한 재개조건/명령을 남긴다. 독립/공식점수는 여전히 분리한다.

완료 시 current_round=round_005, handoff.ready=true, active_workers=[]로 저장한다. 목표 미달이고 실행 가능한 다음 작업이 있으면 아래 명령으로 새 Astra high 세션에 인계하고 수락 영수증 확인 후 종료한다.
```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_005'
```