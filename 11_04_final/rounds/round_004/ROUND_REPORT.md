# Round 004 결과 — CPU 환경 설치와 개발 입력 재현 준비

작성: 2026-11-05 KST. **고정 패키지 환경 설치·의존성 검사, 개발 전용 입력 감사, CPU 합성 모델 검사를 완료했다. 최초 RAM 관문은 미달했지만 사용자의 재확인 지시 후 가용 메모리가 회복되어 합성 실행이 13.047초에 통과했다. 신규 F1은 없으며 목표0.7은 미달 상태다.**

## 결과와 의미

| 항목 | 실제 결과 | 의미와 한계 |
|---|---|---|
| 격리 환경 | Python3.12.14 / Torch2.6.0+cpu / TabICL2.2.0 / NumPy2.3.5 / sklearn1.7.2 | 설치와 별도의 합성 모델 검사 모두 완료 |
| 설치·검사 | 150.437초, 모든6단계 종료코드0, pip check 정상 | 900초 한도 이내; 설치 오류 재시도0 |
| 다운로드 저장물 | 35 wheel, 283,019,957bytes (269.909MiB) | 1GiB보다 작음; HTTP header/metadata 전체 전송량의 계측은 아님 |
| 체크포인트 | 기존캐시110,368,038bytes를 root/model_cache에 복사; 지정SHA256 일치 | 새 모델 다운로드0, 합성 실행에서 로드1회 |
| RAM 관문 | 최초2.196GiB로 미실행; 사용자 재확인 후 실행 직전4.045GiB | 두 관문을 보존; 타 프로세스를 종료하지 않음 |
| 합성 smoke | 13.047초, 종료코드0, CPU/FP32, 확률4×4·행합·재호출 검사 통과 | 실제 선박 성능 검사는 아님 |
| 모델 구조 | 계수27,552,258개, decoder512→1024→10 | 역사 기록과 일치; 계수학습0회 |
| 개발 입력 | 3개 NPZ 고정해시·첫156열 이름/순서·개발5897척 명부/역할/라벨 대응 확인 | 원본 전체7372행·holdout 개별행을 읽지 않음 |
| FIT 중앙값 | seed42/2026 ×3fold의6개 비교 모두 허용1e-10 내; 최대차2.84217e-14 | 집계 일치; 모든 과거 원행 값의 동등성을 입증하지 않음 |
| 변환 | 저장156median+원결측156표시로 재구성한 FIT/INNER float32 312열 hash 기록 | 재구성 후보입력; 원모델 재추론이 아님 |

유지하는 역사적 개발 기준은 `sqrt_macro` LightGBM5seed micro-F1 **0.5930133966423605**, macro-F1 **0.5252719738966167**이다. 과거6source 탐색값0.5933525521451586은 미채택이다. round003 TabICL 원확률/판정변경 결과는 별도이며 같은 숫자가 나타났다는 이유로 동일모델로 합치지 않는다. 이번 회차는 실제자료 F1평가·모델추론·계수학습을 각각0회 수행했다. 독립 평가값과 공식 제출 점수는 여전히 없다.

## 실행·자원·출처

관리자 시작16:45:47 UTC, 상한17:30:47 UTC. ROUND_PLAN의 분단위 동결 표시는16:48이며 실제 파일 생성/수정시각은16:47:42.1038898 UTC다(initial_file_times.json). 계획·예산·코드검토를 설치 시작16:50:58.265 UTC 전에 남겼다. wrapper 소스는 실행 전 snapshot과 같고 SHA256 `381f20fd24f2de465643c2ec8b648a6332c5632e21f4c8d1fa05073e32602750`이다.

공식 [PyTorch CPU 배포 안내](https://pytorch.org/get-started/previous-versions/)와 [TabICL2.2.0 metadata](https://pypi.org/pypi/tabicl/2.2.0/json)를 근거로 공개 wheel만 내려받고, root wheelhouse에서 오프라인 설치했다. TabICL wheel SHA256은 보존한 PyPI metadata와 일치한다. requirements.freeze.txt, pip install report,35개 wheel hash/크기,33개 설치배포 metadata 및 라이선스 파일을 environment/에 저장했다. 기반 Python과 원본 저장소 환경은 수정하지 않았다.

체크포인트 SHA256은 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`이다. 동일 revision의 [공식 모델카드](https://huggingface.co/jingang/TabICL/blob/4dcd344ece2c00be9e831fdd35bed57b5ad83e19/README.md)를 저장했으며 bsd-3-clause 표기를 확인했다. 모델카드1170bytes는 부가 metadata이며 모델 가중치 다운로드가 아니다. 모델카드 web 도구 접근 실패 후 직접 HTTPS 읽기로 보존했다.

모든 새 venv/cache/temp/로그/산출은 작업루트 아래다. 설치 subprocess timeout, 다운로드 도중 및 종료후 용량검사, 종료후 시간검사를 적용했고 해당 자식 프로세스만 종료하는 정책이었다. 실제 timeout/강제종료는 없었다. 다운로드 용량은 wheel/temp 파일의 보수적 관찰값이고 엄밀한 네트워크 계측이 아니다. 최종 설치총시간도900초 미만임을 별도로 확인했다.

독립 검토된 합성 probe는 고정seed20261105, 16FIT+4query, 312float32, 4클래스, 1estimator/batch1, CPU/FP32, AMP/FA3/자동다운로드 비활성 조건이다. 소스해시 `7dee24ee5cc215733450be17db34b10a5e9d9adacc5c7ba33021bac3ecf4a0b2`를 유지했다. 최초 가용RAM2.196GiB에서는 모델을 호출하지 않았다.

사용자가 “램 확인하고 할수있는거 다해”라고 지시한 뒤17:06:32 UTC에 가용RAM3.986GiB를 확인했다. 기존 관문·검토·보고서 초안을 pre_user_recheck/에 보존하고 USER_STEERING_AMENDMENT.json에 범위 변경을 기록했다. 실행 직전 wrapper 측정은4.045330048GiB였다. 동일한 검토 코드로 **처음 실행한 합성 smoke 1회**가17:06:50.106–17:07:03.145 UTC, PID4060,13.047초에 종료코드0으로 완료됐다. timeout과 강제종료는 없었다.

체크포인트 로드와 합성 문맥 바인딩은0.315초, 첫확률/반복확률/라벨 호출은 각각1.645/1.625/1.610초였다. 계수27,552,258개, 실제 CPU 배치, floating parameter의FP32, 이름으로 찾은 decoder512→1024→10을 확인했다. requires_grad가 켜진 계수가 있어도 실제 gradient 축적과 계수학습은0이다. 4×4 확률은 유한하고 각 행합은1과 허용오차1e-5 내에서 일치했다. 저장된 십진수를 float64로 합한 독립 검산에서는 최대 약6e-8의 차이가 있었다. 같은 입력의 두 확률 배열 최대차는0, 클래스 역변환과 라벨 argmax가 일치했다. 합성 질의에는 정답을 부여하거나 F1을 계산하지 않았다.

프로세스 peak working set은761,470,976bytes(약726.20MiB), 최종 private bytes는949,067,776bytes였다. 이는 작은 합성 입력의 관측이며 전체5897척이나3144행 FIT 문맥 비용으로 외삽하지 않는다. 결과와 확률은 artifacts/smoke.json, 실행 증거는 logs/smoke_01.receipt.json 및 stdout/stderr에 있다. 최초 자원 부족은 환경 계층 제한이었으며 사용자 재확인 이후 해소됐다. 다른 프로세스를 종료하지 않았다.

## 입력 감사의 확인 범위

`exp01/fold_{0,1,2}_features.npz`는 각5897×304 float64이며 round002에 동결한SHA256과 일치했다. 생성코드는 F156156열 다음 T510열,behavior68열,local_rel70열을 붙인다. 첫156이란 위치만으로 채택하지 않고 P의 feature_columns/사전 이름·순서,생성코드의 F156블록,fold별vocabulary범위와 FIT-ID 해시,개발명부/역할/라벨을 대조했다. source/metadata 정합성과 특징 의미·모든 과거 원값의 독립 재생성을 구별한다.

3fold FIT수3144/3144/3145,INNER 각787,OUTER1966/1966/1965가 맞았다. 첫156열의 NaN수43352/36389/36620,Inf0이다. 모든 조건을 확인한 뒤 FIT에 한정한 nanmedian156개와 seed42/2026의 saved preprocessor를 비교했다. saved kind와 코드의 `np.c_[x,missing].astype('float32')`는312열을 지지하며, run_settings의 no-missing-flags 설명과 충돌한다. 여섯median과12개FIT/INNER변환 hash는 lineage/result.json에 있다. 변환 배열을 모델에 넣지는 않았다.

남은 한계:

1. NPZ·두 개발명부의 행순서만으로 원코드의 `.loc[fold['fit_ids']]` 순서를 증명할 수는 없다. 추가 조사에서 원래 순서 있는 목록의 manifest와 해시 연결을 찾았다. 그 순서로 배열을 export하고 과거 INNER-ID digest와 실제 비교하는 단계는 후속에 남았다.
2. metadata/생성코드/중앙값의 일치는 전체 과거7372행 원특징 값이나 vocabulary값의 독립 재생성이 아니다. 보호된 전체표를 열어 비교하지 않았다.
3. 합성1estimator의 클래스 역변환은 확인했지만 실제 개발입력의 내부 feature/class shuffle·정규화·8estimators 조건은 아직 재현하지 않았다. 여섯fold model.pkl 부재는 남는다.
4. 재구성 가능한 개발입력 후보를 확보한 것이며 원GPU 확률과 CPU 확률의 동등성,실제선박 성능향상을 입증하지 않았다.

사용자 추가 지시 후 ID명부 수준의 원문맥 연결도 확인했다. `P/splits/splits_original.json`의 SHA256 `b99a81c7573acbc65ab4b8780790dfc2377252893a0947ac760eedc510dae686`은 고정 판정 규칙과 seed42 parent fingerprint의 원래 `work/splits.json` 해시와 일치한다. 이 명부는 개발5897개·holdout1475개 ID와3fold의 순서 있는 ID목록을 담으며, 특징·정답·예측을 담은 데이터표가 아니다. `known_holdout_reused=true`, selection_scope=`development exploratory nested early-stop evaluation` 표시를 확인했다. 이는 과거 사용 이력의 추가 단서이며 새로운 독립 평가의 근거가 아니다. holdout ID metadata는 구조·분리 확인에만 썼고 holdout 특징/라벨/확률은 읽지 않았다.

원순서로 fold0 FIT3144×312와 INNER787×312를 저장하는 `context_recovery/build_context.py`를 준비했다. 검토에서 fold별 명부 dict 덮어쓰기와 라벨 인덱스를 바로잡고, 정확한 NPZ해시·개발/holdout ID비중첩·고정manifest연결을 강제했다. 최종 소스해시는 `1e87753eda6e5253cf248c1abbde6e1155d7eee3693d91495d8e78c8ac884c6d`이며 정적검토를 통과했다. 추가 작업의 사전 실행마감17:15 UTC 전에 최종 검토가 끝나지 않아 **export는 실행하지 않았다**. 원INNER digest의 실제 비교, 원순서 배열의 저장/검산도 아직 남았다. 기존12개 배열hash는 계속 roster 순서 결과다. 준비결과는 context_recovery/result.json 및 CONTEXT_READINESS.md, 별도 검토는 review/context_precheck.json에 있다.

원추론 설정도 소스와 metadata로 정리했다(runtime_author/replay_contract.json). 원실행은 CUDA,8estimators,batch1,seed42,AMP/FA3=false,n_jobs3였다. normalize `[none,power]`,feature latin/class shift,temperature.9,average_logits=true 등의 버전 기본값과 명시적 설정을 구별했다. batch1은 질의 수가 아닌 ensemble-view 묶음이다. FIT에서 전처리를 적합하고 attention keys/values를 FIT로 제한하는 소스는 질의별 수학적 독립성을 지지하지만, CPU2질의와 과거CUDA787질의의 수치 동등성은 측정 전이다.

## 역할·검토·학습

관리자는 codex_53b6ac45_0a2c_4a1a_b5d5_2624c7a28d9e다. host turn_context의 gpt-6-astra/high를 저장했다. 작성자·입력감사자·별도검토자의 gpt-6-luna/xhigh 요청/호스트기록/역할ID를 MODEL_AND_OWNERSHIP.md와 model_runtime_evidence.json에 연결했다. 관리자 포함4슬롯을 지켰다. 이 기록은 호스트가 보고한 설정 증거이며 모델 내부 인증이 아니다.

인계 해시·수신 세션을 검증했고 직전관리자 done/중복계산 없음도 확인했다. 코드검토에서 종료후시간·용량관문,실제CPU/dtype검사,확률단계별보존,출력head별비교를 보완한 후 실행을 동결했다. 설치 전검토와 합성코드 전검토는 review/install_precheck.json,review/precheck.json에 있다. 최종 독립 결과검토는 review/의 최종 산출을 따른다.

입력 감사의 이력 보존에는 한계가 있다. 작성자의 도구 이력 재확인은 감사 스크립트의 성공 실행8회를 세지만 최종 result.json의 수동 iteration 표시는7이다. 계산값을 바꾸거나 다시 실행하지 않고 DIAGNOSTIC_HISTORY.md에 정정했다. 일곱 이전 진단 산출·실행시점 소스 snapshot은 따로 보존되지 않았으며, 현재 최종 코드/입력과 최종 결과만 완전히 대조할 수 있다. 이 감사들은 코드·기록 보완을 위한 반복이며 모델 학습이나 점수 탐색이 아니다. 누락된 과거 PID/시각/해시는 추정하여 채우지 않는다. 최종 수치의 독립 검산과 과거 실행 이력 보존의 한계를 구분한다.

기술목표는 환경과 입력재현 준비였다. 학습목표는 설치/합성실행/원출력재현/F1평가를 구별하고,결측표시·문맥순서·정밀도의 의미를 설명하는 것이다. 질문과 실패 계층은 LEARNING_NOTES.md에 남겼다. 학습자 이해와 실제 하드웨어 동작은 평가하지 않았다.

## 다음 회차

round005는 준비된 exporter를 새 회차 경로에 복사·검토하여 원래 순서의 개발입력을 한 번 저장하고 검산한다. 입력관문이 통과하면 정답/오류 여부를 보지 않고 고정한 원INNER 앞2개에 대해 단 한 번의 원출력 재현·CPU 자원 pilot를 수행한다. 전체FIT3144척,seed42,8estimators,600초,실행직전RAM>=3GiB/실행중<1.5GiB시자식중단으로 고정했다. 확률 최대차<=1e-4와 argmax일치를 작은 재현 관문으로 삼고 F1을 계산하지 않는다. 설치와 합성 smoke는 반복하지 않는다. 새F1·M4 gradient학습은 후속이며 원출력 재현을 건너뛰어 성능을 주장하지 않는다.

입력계약이 완성됐지만 RAM관문이 계속 미달이면 동일준비회차를 연쇄생성하지 말고 자원제약과 정확한 재개방법을 남긴다. 구체 범위·예산·명령·인수조건은 NEXT_SESSION.md에 있다.
