# 다음 Astra high 관리자 — Round 004

사용자는 학습·국소 실험·새 관리자 인계를 승인했다. round002 일시정지는 해제됐다. 반복 승인을 요청하지 않는다. round003은 완료됐으며 후속은 아래 유한한 환경/재현 준비다. 인계 receipt 수신 세션과 ORCA_AGENT_SESSION_ID를 대조하고 중복 실행을 피한다.

## 시작·역할·제약

작업루트 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`. AGENTS, CYCLE_PROTOCOL, STATUS, round003 ROUND_REPORT, review/review.json, m4_readiness/READINESS.md와 readiness.json을 읽는다. 관리자 gpt-6-astra/high, 보조 gpt-6-luna/xhigh/fork_turns=none만 요청하고 작성자와 독립 검토자를 분리한다. 호스트 총4슬롯/사용자보조최대4명 중 더 작은 한도를 적용한다. 파일별 소유자를 지정하고 타인 변경을 되돌리지 않는다. 실제 turn_context 모델·effort 증거를 남긴다.

모든 출력·venv·pip cache·temp·bytecode는 작업루트 안에 둔다. 원자료 F:/문제 데이터_수정_1027, D:/repos/fishing-track-classification, 공유 package, 전역/번들 Python은 읽기 전용이다. 다른 과제2/TestB 세션을 건드리지 않는다. 외부 업로드·공식제출·유료자원·동일 선박 과거 프로필 경로는 제외한다.

## 완료 결과

개발 OUTER5897척의 두seed 평균 micro/macro: A_raw .5930133966423605/.5155580319500959; A_old .5748685772426658/.5372271285505399; INNER선택 .5933525521451586/.520562845334023. 선택배수는 seed42=[1,1.5,1], seed2026=[1,1,1]. raw 대비 정답순증+4/0, 평균micro+.0003392, paired5000회95%CI[-.00093268,.00161099]. 사전 확인후보 기준 실패로 채택하지 않는다. 기존 배수 대비 이득과 macro 손실은 별도로 기록했다.

이번 raw .593013과 역사 LightGBM5seed .593013은 수치만 같고 동일모델 결과가 아니다. 기존6source .593353과 이번선택 .593353도 별개다. 반복 노출된 개발자료이며, OUTER 선박이 같은fold FIT/INNER에서 제외됐다는 사실도 유지된다. 저장 확률 검산은 원모델 재추론이 아니다. 독립·공식 점수는 없다.

## 목표·예산 — 실행 전에 ROUND_PLAN/config로 고정

**M4 변경 전에 전용 CPU runtime을 확보하고, 체크포인트의 작은 실행과 개발 전용 입력 재현 가능성을 확인한다.** 출력층 학습·전체 실제자료 추론·신규F1·판정 재탐색은 이번 범위가 아니다.

- 관리자45분, 설치·다운로드 합계15분/신규다운로드1GiB.
- 큰 계산 동시1개, threads<=3. 모델 로드/smoke 전 가용RAM>=3GiB; 미달이면 조사·문서화만 하고 다른 프로세스를 중지하지 않는다.
- 합성 smoke 최대2회/각180초. 두 번째는 구체적 API수정 근거가 있을 때만. 새 계수학습0회, 실제자료 F1평가0회.
- 설치는 같은 오류 무한반복 금지. 근거 있는 수정 최대1회. 상한 전에 산출·오류·재개 명령을 남긴다.

## 확인된 자원

Python3.12.14 실행파일: `C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`. 시스템/round002 Python은3.13.3이다. 세 환경 모두 Torch/TabICL은 없었다. 해당 기반 Python을 변경하지 않고 root 전용 venv를 만든다.

체크포인트: `C:/Users/dlehs/.cache/huggingface/hub/models--jingang--TabICL/snapshots/4dcd344ece2c00be9e831fdd35bed57b5ad83e19/tabicl-classifier-v2-20260212.ckpt`, 110368038bytes, SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0` 직접 일치. 원캐시 수정 없이 root/model_cache로 복사·해시 확인한다. 새 모델 다운로드는 필요 없다.

WMI GPU는 AMD Radeon780M, nvidia-smi는 PATH에 없다. 문서의 RTX3060Ti는 역사 장비다. CPU를 명시하고 CUDA/AMD가속 설치로 확대하지 않는다.

## 전용 환경 명령

다음 명령을 실행 전 검토·로그·timeout wrapper로 감싼다. PIP_CACHE_DIR/TEMP/TMP/TMPDIR/HF_HOME을 root 아래로 지정하고 PYTHONDONTWRITEBYTECODE=1, threads3으로 둔다. 환경이 이미 있으면 먼저 상태를 확인하고 삭제·덮어쓰지 않는다. 설치 원본·최종freeze·라이선스·용량/hash·명령·PID·실제 종료코드를 저장한다.

```powershell
& 'C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m venv './environments/round_004_tabicl_cpu'
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -m pip install --only-binary=:all: 'torch==2.6.0' --index-url https://download.pytorch.org/whl/cpu
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -m pip install --only-binary=:all: 'tabicl==2.2.0' 'numpy==2.3.5' 'scikit-learn==1.7.2'
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -m pip check
```

공식 근거: [TabICL2.2.0](https://pypi.org/pypi/tabicl/2.2.0/json), [PyTorch2.6.0 CPU wheel](https://pytorch.org/get-started/previous-versions/). PyPI 응답은 round003/m4_readiness에 보존했다. 추가 의존성은 metadata에 따라 설치하고 실제 버전을 고정한다. torchvision/torchaudio/finetune extras/대형CUDA패키지는 추가하지 않는다. pin 설치 불가면 정확한 오류와 호환 대안을 기록하고 모델 버전을 임의 대체하지 않는다.

## 체크포인트와 극소 합성 smoke

`rounds/round_004/code/probe_tabicl_runtime.py`를 작성·독립검토·해시 후 실행한다(현재 미구현). 설치 버전, CPUdevice, checkpoint 로드, 모델구조/최종Linear/계수수와 API signature를 확인한다. 역사27552258개/512→1024→10과 다르면 차이를 기록한다.

고정seed20261105로 4클래스가 모두 있는16행FIT+4행query,312열float32 합성값만 쓴다. n_estimators=1,batch_size=1,device='cpu',use_amp=False,use_fa3=False,allow_auto_download=False,명시적model_path를 사용하며 실제2.2.0 API를 먼저 확인한다. fit은 합성 문맥 바인딩이며 계수학습이 아니다. 유한한4클래스확률·행합·클래스역변환·동일입력 재호출을 확인한다. F1이나 실제 선박 성능을 계산하지 않는다. 출력층 수정/gradient학습은 후속이다. CPU시간/RAM을 남기되 전체5897척 비용을 확정하지 않는다.

## 개발 전용 입력의 최소 복구

P=`D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료`.

허용: P의 code/metadata, evaluation의seed42/2026 training/preprocessor/parent_fingerprint, development_roles_long.csv, round003 개발확률/명부. saved preprocessor.kind=`fit_median_and_raw_missing_flags`, median156개와 fingerprinted source의`np.c_[x,missing]`는312열을 지지한다. no-missing-flags 설명과의 충돌을 기록한다. 여섯fold model.pkl은 없다. FIT ID/라벨뿐 아니라 원행순서/열순서/클래스shuffle·역변환을 복구해야 한다.

대안 입력: `D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/artifacts/exp01/fold_{0,1,2}_features.npz`. 기존 개발5897척만 포함하는 파일이며 round002 config에 해시가 있다. 먼저 키/열이름/역할/생성소스와 P의F156열정의·fold별vocabulary 범위를 대조한다. 첫156열이라는 이유만으로 A입력과 같다고 가정하지 않는다. 정확한 정의·순서가 확인될 때만 FIT 부분 중앙값과 저장156median을 대조하는 유한 검사를 허용한다. NaN/정밀도/변환/hash를 남기고 불일치 원인을 분리한다. 이번 회차는 실제 선박의 원모델 추론을 실행하지 않는다.

금지: P/data/F156_train.csv·train_labels.csv 전체7372행, components/*train.csv 전체행, holdout 개별 특징/정답/확률, Test2025, 원자료. 개발행만 필터하겠다며 전체 보호행을 먼저 파싱하지 않는다. NPZ로 A입력을 복구할 수 없으면 정확히 부족한 자료/개발전용 export 계약을 남긴다. 독립 평가 노출 이력 확인 전 holdout 읽기 금지는 유지한다.

## 결과·후속·인계

산출: 설치증거/freeze, checkpoint hash, smoke출력/시간/메모리, 입력계보 일치·불일치표, 독립검토, ROUND_REPORT/ledger/STATUS/NEXT_SESSION. runtime 준비를 성능 개선이라고 부르지 않는다.

runtime+입력 충분 시 다음 회차는 정답을 보고 고르지 않은 소수INNER질의의 원모델replay(같은FIT문맥·순서·8estimators/FP32/클래스순서)와 CPU자원pilot부터다. 통과 뒤 M4-a/b 무변경/gradient/병합/reload 및 한foldINNERpilot를 별도 계획한다. runtime만 성공하면 다음은 개발전용 입력복구로 한정한다. CPU/설치 실패는 구체적 원인과 재개조건을 남기고 동일 점검을 무한 반복하지 않는다.

완료 STATUS.current_round=round_004, handoff.ready=true, active_workers=[]로 둔다. 목표 미달이고 다음 작업이 실행 가능하면 저장 후 fresh manager에게 인계하고 수락 receipt 확인 뒤 종료한다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_004'
```
