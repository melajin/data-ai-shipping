# 다음 Astra high 관리자 — Round 005

사용자는 학습·국소 실험·새 관리자 인계를 승인했다. 반복 승인을 요청하지 않는다. 먼저 인계 receipt의 수신 세션과 ORCA_AGENT_SESSION_ID를 대조하여 중복 실행을 피한다.

## 시작과 역할

작업 루트는 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`이다. AGENTS/CYCLE_PROTOCOL/STATUS, round004 ROUND_REPORT, review 최종 검토, lineage/result.json과 LINEAGE_REPORT.md를 읽는다.

관리자는 gpt-6-astra/high, 보조는 gpt-6-luna/xhigh/fork_turns=none만 사용한다. 작성자와 검토자를 분리하고 파일 소유자를 지정한다. 타인의 변경을 되돌리지 않는다. 사용자 보조 상한4명과 호스트 총4슬롯 중 더 작은 한도를 따른다. 요청값과 host turn_context 증거를 별도로 저장한다.

원자료 `F:/문제 데이터_수정_1027`, 이전 저장소 `D:/repos/fishing-track-classification`, 공유 package P는 읽기 전용이다. 모든 새 산출·temp·cache·bytecode는 작업 루트 아래에 둔다. round004 산출은 수정하지 않는다. 보호 holdout의 개별 특징·라벨·확률, 전체7372행 F156/train_labels/components train표, Test2025, 원자료는 읽지 않는다. 전체표를 파싱한 후 개발행만 필터하지 않는다. 외부 업로드·공식 제출·유료 자원·실선 운용은 없다.

## 완료 결과와 사용 가능한 자원

- 환경: `environments/round_004_tabicl_cpu/Scripts/python.exe`. Python3.12.14, Torch2.6.0+cpu, TabICL2.2.0, NumPy2.3.5, sklearn1.7.2. 설치150.437초, pip check 정상. freeze·라이선스·wheel 해시는 round004/environment에 있다. 재설치하지 않는다.
- 체크포인트: `model_cache/tabicl-classifier-v2-20260212.ckpt`, 110368038bytes, SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`.
- 합성 probe: `rounds/round_004/code/probe_tabicl_runtime.py`, SHA256 `7dee24ee5cc215733450be17db34b10a5e9d9adacc5c7ba33021bac3ecf4a0b2`. 독립 코드검토는 통과했지만 모델 로드·합성 실행은0회다. 실행 직전 가용RAM2.196254730GiB가 최소3GiB에 못 미쳐 wrapper가 시작을 거부했다.
- 세 개발 NPZ의 해시, 첫156열 이름/순서, 명부/역할/라벨, vocabulary FIT-ID 범위가 맞았다. 여섯 saved median 비교는 최대차2.84217e-14로 허용1e-10 내였다. 결측 표시를 붙인 float32 312열 FIT/INNER 후보12개의 hash를 저장했다. 원래 FIT/INNER 순서·원확률·모든 과거 원행 값의 일치는 아직 미확인이다.
- 역사 LightGBM5seed 개발 기준은 micro .5930133966423605 / macro .5252719738966167이다. round003 TabICLraw 평균micro .593013은 숫자만 같은 별도 결과다. round003 선택 .5933525521451586은 미채택이다. 신규·독립·공식 점수는 없다.

## 목표와 실행 전 동결할 한도

이번 회차는 **원래 FIT/INNER 순서와 전처리·추론 설정을 확정하고, 개발 전용 재현 입력을 저장**한다. 메모리 조건이 회복된 경우에만 미실행 합성 smoke를 수행한다. 실제 선박 추론·F1·계수학습·M4 수정은 이번 범위가 아니다.

- 관리자 최대35분, 입력 복구/검산 계산 최대10분, 큰 계산 동시1개, threads<=3. 설치·다운로드0회.
- 개발 입력은 fold0/seed42의 FIT3144+INNER787로 고정한다. 작성자 산출1회와 별도 검토자 검산1회가 기본이다. 오류 수정은 원인과 변경을 기록한1회까지만 허용한다.
- 합성 smoke 최대1회/180초. 실행 직전 RAM>=3GiB가 필수다. 미달이면 모델 로드0회, 같은 회차 자원관문 재확인0회, 타 프로세스 중지0회다. API 오류가 생기면 이번 회차에 반복 실행하지 말고 원인과 재개 조건을 기록한다.
- 새 계수학습0회, 실제 선박 모델추론0회, F1평가0회, 특징/하이퍼파라미터 탐색0회.

## 1. 원문맥 순서와 개발 전용 입력

P=`D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료`.

허용 입력은 P/code·metadata, seed42/2026 training/preprocessor/parent_fingerprint, development_roles_long.csv, 기존 개발 확률/명부다. 사용할 NPZ는 `D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/artifacts/exp01/fold_0_features.npz`, SHA256 `858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95`다.

이번에 추가 확인할 명부 metadata는 **P/splits/splits_original.json**(파일 목록상497418bytes)이다. 원래 분할 생성코드/manifest와 대조하여 ID목록·분할설정 파일임을 확인하고, fold0의 순서 있는 fit_ids/inner_ids를 추출한다. holdout 명부ID가 포함되어 있어도 특징·정답·예측 열람이나 독립 평가가 아니다. 만약 ID명부가 아닌 holdout 개별값을 포함한 구조라면 그 필드는 읽지 말고 개발 전용 ID export가 필요함을 기록한다.

원코드 comparison_models.py:316–319는 `.loc[fold['fit_ids'], columns]`와 각 INNER/OUTER의 순서 있는 목록을 쓴다. roster 순서가 같다는 것만으로 원 FIT 순서를 확정하지 않는다. 원ID 목록의 순서·source hash·생성원리를 남기고 개발 멤버십, 역할, 서로소, 길이, 중복, 라벨 대응을 검사한다. 과거 INNER-ID digest는 정확한 serializer/원순서로 비교한다. 맞을 때까지 임의 정렬을 탐색하지 않는다.

작성자는 `rounds/round_005/code/build_replay_inputs.py`를 작성하고 별도 검토 후 다음 인터페이스로 실행한다. 이 파일은 현재 미구현이며 이번 관리자가 완성해야 한다.

```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' './rounds/round_005/code/build_replay_inputs.py' --fold 0 --seed 42 --output './rounds/round_005/artifacts/replay_inputs_fold0_seed42.npz'
```

허용된 개발 NPZ에서 확인한 ID순서로 행을 선택하고 첫156열 정의·순서를 재확인한다. saved preprocessor의156median으로 `missing=~isfinite(x)`, `where(missing,median,x)`, `c_[imputed,missing].astype(float32)`를 구현한다. 다른 통계나 정규화를 추가하지 않는다.

산출은 ordered fit_ids/inner_ids, y_fit과 필요시 개발 y_inner, raw156열 및 transformed312열의 이름·단위·결측규약, X_fit/X_inner, shape/dtype/hash/provenance다. OUTER 확률과 성능은 계산하지 않는다. 검토자는 일부 행의 대치값·결측 표시와 전체 bytehash를 독립 검산한다. round004 roster-order hash와 달라지면 행순열 차이와 정밀도/값 차이를 구분한다. 원순서가 끝내 불명확하면 임의 정렬을 정확 재현으로 부르지 않는다.

## 2. 추론 설정과 후속 질의 동결

P의 fingerprinted comparison_models.py, training/parent metadata, 설치된2.2.0 소스를 읽는다. n_estimators8, batch1, seed42, FP32, CPU, normalization, feature/class shuffle, softmax, average-logits, outlier, 클래스 역변환 조건을 기록한다. 과거 metadata에 없는 값은 원실행 확정값과 버전고정 재구성 가정을 구분한다. 질의 묶음이나 querybatch가 출력에 영향을 줄 수 있는지도 확인한다.

후속 원출력 replay용 질의는 **정답·예측·오류 여부를 보지 않고 원래 INNER 순서의 앞2개 ID**로 고정하여 hash를 저장한다. 이번에는 실제 모델에 넣거나 새 확률을 계산하지 않는다.

## 3. 자원 조건부 합성 smoke

round004 probe를 round005/code로 복사하고 source hash를 유지한다. 출력경로는 실행인수로 지정한다. 새 wrapper는 기존 venv만 호출하고, root 내부 cache/temp/HF_HOME/bytecode/thread 설정, expected checkpoint hash, 단일회180초, 실행 직전 RAM>=3GiB를 강제한다. round004 manage_runtime.py의 install 모드를 다시 실행하거나 round004 로그를 덮어쓰지 않는다. 새 wrapper와 복사 probe를 별도 검토자가 검토한 후 다음 명령을 wrapper 안에서 실행한다.

```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' './rounds/round_005/code/probe_tabicl_runtime.py' --checkpoint './model_cache/tabicl-classifier-v2-20260212.ckpt' --output './rounds/round_005/artifacts/smoke.json'
```

합성 조건은 seed20261105,16+4행,312열,4클래스,1estimator다. 코드/입력해시, PID, 종료코드, stdout/stderr, 실제 device·계수수·head, 확률·행합·재호출, 시간·메모리를 남긴다. 아직 실측하지 않은27552258계수와512→1024→10을 확인 사실로 쓰지 않는다.

## 결과·실패분기·인계

산출은 ordered 개발입력 NPZ/manifest, 원순서 근거, 추론설정 계약, 고정2질의 목록, 독립검토, 조건부 smoke 또는 미실행 자원관문 증거, ROUND_REPORT/ledger/STATUS/NEXT_SESSION이다. 기술 완성과 학습자 설명 능력을 구분한다.

입력과 합성 smoke가 모두 준비되면 다음 회차에 고정2개 INNER의 원출력 replay와 CPU자원 pilot를 유한 예산으로 계획한다. CPU/GPU 확률차이와 querybatch 차이를 확인하고 통과 후 M4-a/b를 별도 회차로 계획한다.

**입력 준비를 끝냈는데 RAM이 여전히3GiB 미만이면 동일 관문만 확인하는 새 회차를 계속 만들지 않는다.** 외부 메모리 제약, 미실행 명령, 재개 조건을 남긴다. 재개 조건은 사용자가 다른 작업을 정리해 가용RAM>=3GiB가 된 뒤 새 관리자로 시작하는 것이다. 실제로 남은 독립 작업이 있을 때만 그 작업을 명시하여 인계한다. 원ID순서 metadata가 없으면 누락 자료와 필요한 개발 전용 ID목록 계약을 정확히 남긴다.

완료 시 STATUS.current_round=round_005, handoff.ready=true, active_workers=[]로 저장한다. 목표 미달이고 실행 가능한 다음 작업이 있으면 아래 명령으로 fresh manager에게 인계하고 수락 receipt를 확인한 뒤 종료한다. 외부 제약으로 실행 불가하면 이유와 정확한 재개 방법을 저장한다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_005'
```