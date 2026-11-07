# Round 004 결과 — CPU 환경 설치와 개발 입력 재현 준비

작성: 2026-11-05 KST. **고정 패키지 환경 설치·의존성 검사와 개발 전용 입력 계보 감사를 수행했다. 합성 모델 실행은 가용 RAM 2.196GiB로 사전 최소3GiB에 못 미쳐 시작하지 않았다. 신규 F1은 없으며 목표0.7은 미달 상태다.**

## 결과와 의미

| 항목 | 실제 결과 | 의미와 한계 |
|---|---|---|
| 격리 환경 | Python3.12.14 / Torch2.6.0+cpu / TabICL2.2.0 / NumPy2.3.5 / sklearn1.7.2 | 설치 성공; 모델 실행 성공을 뜻하지 않음 |
| 설치·검사 | 150.437초, 모든6단계 종료코드0, pip check 정상 | 900초 한도 이내; 설치 오류 재시도0 |
| 다운로드 저장물 | 35 wheel, 283,019,957bytes (269.909MiB) | 1GiB보다 작음; HTTP header/metadata 전체 전송량의 계측은 아님 |
| 체크포인트 | 기존캐시110,368,038bytes를 root/model_cache에 복사; 지정SHA256 일치 | 새 모델 다운로드0, 실제 로드0 |
| 합성 smoke | 16:56:49.810 UTC 자원관문에서 중단, 가용2.196254730GiB <3 | 모델 subprocess 시작0; 모델/확률/계수수 검증 미실행 |
| 개발 입력 | 3개 NPZ 고정해시·첫156열 이름/순서·개발5897척 명부/역할/라벨 대응 확인 | 원본 전체7372행·holdout 개별행을 읽지 않음 |
| FIT 중앙값 | seed42/2026 ×3fold의6개 비교 모두 허용1e-10 내; 최대차2.84217e-14 | 집계 일치; 모든 과거 원행 값의 동등성을 입증하지 않음 |
| 변환 | 저장156median+원결측156표시로 재구성한 FIT/INNER float32 312열 hash 기록 | 재구성 후보입력; 원모델 재추론이 아님 |

유지하는 역사적 개발 기준은 `sqrt_macro` LightGBM5seed micro-F1 **0.5930133966423605**, macro-F1 **0.5252719738966167**이다. 과거6source 탐색값0.5933525521451586은 미채택이다. round003 TabICL 원확률/판정변경 결과는 별도이며 같은 숫자가 나타났다는 이유로 동일모델로 합치지 않는다. 이번 회차는 실제자료 F1평가·모델추론·계수학습을 각각0회 수행했다. 독립 평가값과 공식 제출 점수는 여전히 없다.

## 실행·자원·출처

관리자 시작16:45:47 UTC, 상한17:30:47 UTC. ROUND_PLAN의 분단위 동결 표시는16:48이며 실제 파일 생성/수정시각은16:47:42.1038898 UTC다(initial_file_times.json). 계획·예산·코드검토를 설치 시작16:50:58.265 UTC 전에 남겼다. wrapper 소스는 실행 전 snapshot과 같고 SHA256 `381f20fd24f2de465643c2ec8b648a6332c5632e21f4c8d1fa05073e32602750`이다.

공식 [PyTorch CPU 배포 안내](https://pytorch.org/get-started/previous-versions/)와 [TabICL2.2.0 metadata](https://pypi.org/pypi/tabicl/2.2.0/json)를 근거로 공개 wheel만 내려받고, root wheelhouse에서 오프라인 설치했다. TabICL wheel SHA256은 보존한 PyPI metadata와 일치한다. requirements.freeze.txt, pip install report,35개 wheel hash/크기,33개 설치배포 metadata 및 라이선스 파일을 environment/에 저장했다. 기반 Python과 원본 저장소 환경은 수정하지 않았다.

체크포인트 SHA256은 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`이다. 동일 revision의 [공식 모델카드](https://huggingface.co/jingang/TabICL/blob/4dcd344ece2c00be9e831fdd35bed57b5ad83e19/README.md)를 저장했으며 bsd-3-clause 표기를 확인했다. 모델카드1170bytes는 부가 metadata이며 모델 가중치 다운로드가 아니다. 모델카드 web 도구 접근 실패 후 직접 HTTPS 읽기로 보존했다.

모든 새 venv/cache/temp/로그/산출은 작업루트 아래다. 설치 subprocess timeout, 다운로드 도중 및 종료후 용량검사, 종료후 시간검사를 적용했고 해당 자식 프로세스만 종료하는 정책이었다. 실제 timeout/강제종료는 없었다. 다운로드 용량은 wheel/temp 파일의 보수적 관찰값이고 엄밀한 네트워크 계측이 아니다. 최종 설치총시간도900초 미만임을 별도로 확인했다.

독립 검토된 합성 probe는 고정seed20261105,16FIT+4query,312float32,4클래스,1estimator/batch1,CPU/FP32,AMP/FA3/자동다운로드 비활성,확률/행합/클래스역변환/재호출/gradient확인을 구현한다. 최종 소스해시 `7dee24ee5cc215733450be17db34b10a5e9d9adacc5c7ba33021bac3ecf4a0b2`를 동결했다. 그러나 RAM 관문에서 probe를 호출하지 않았으므로 이 검사들은 코드검토만 통과했다. 역사27552258계수/512→1024→10 head의 실제확인,CPU시간·모델메모리·확률 결과는 없으며 전체5897척 실행비용도 추정하지 않는다. 자원 부족은 환경 계층 제한이지 모델 정확도 실패가 아니다. 다른 프로세스를 종료하지 않았고 같은 관문을 이번 회차에서 반복하지 않았다.

## 입력 감사의 확인 범위

`exp01/fold_{0,1,2}_features.npz`는 각5897×304 float64이며 round002에 동결한SHA256과 일치했다. 생성코드는 F156156열 다음 T510열,behavior68열,local_rel70열을 붙인다. 첫156이란 위치만으로 채택하지 않고 P의 feature_columns/사전 이름·순서,생성코드의 F156블록,fold별vocabulary범위와 FIT-ID 해시,개발명부/역할/라벨을 대조했다. source/metadata 정합성과 특징 의미·모든 과거 원값의 독립 재생성을 구별한다.

3fold FIT수3144/3144/3145,INNER 각787,OUTER1966/1966/1965가 맞았다. 첫156열의 NaN수43352/36389/36620,Inf0이다. 모든 조건을 확인한 뒤 FIT에 한정한 nanmedian156개와 seed42/2026의 saved preprocessor를 비교했다. saved kind와 코드의 `np.c_[x,missing].astype('float32')`는312열을 지지하며, run_settings의 no-missing-flags 설명과 충돌한다. 여섯median과12개FIT/INNER변환 hash는 lineage/result.json에 있다. 변환 배열을 모델에 넣지는 않았다.

남은 한계:

1. NPZ·두 개발명부의 행순서가 같아도 원코드의 `.loc[fold['fit_ids']]` 순서를 자동 증명하지 않는다. 원래 FIT/INNER 순서와 과거ID digest는 후속에서 복구해야 한다.
2. metadata/생성코드/중앙값의 일치는 전체 과거7372행 원특징 값이나 vocabulary값의 독립 재생성이 아니다. 보호된 전체표를 열어 비교하지 않았다.
3. 내부 feature/class shuffle,클래스 역변환,정규화 및8estimators 조건을 실제 추론으로 확인하지 않았다. 여섯fold model.pkl 부재는 남는다.
4. 재구성 가능한 개발입력 후보를 확보한 것이며 원GPU 확률과 CPU 확률의 동등성,실제선박 성능향상을 입증하지 않았다.

## 역할·검토·학습

관리자는 codex_53b6ac45_0a2c_4a1a_b5d5_2624c7a28d9e다. host turn_context의 gpt-6-astra/high를 저장했다. 작성자·입력감사자·별도검토자의 gpt-6-luna/xhigh 요청/호스트기록/역할ID를 MODEL_AND_OWNERSHIP.md와 model_runtime_evidence.json에 연결했다. 관리자 포함4슬롯을 지켰다. 이 기록은 호스트가 보고한 설정 증거이며 모델 내부 인증이 아니다.

인계 해시·수신 세션을 검증했고 직전관리자 done/중복계산 없음도 확인했다. 코드검토에서 종료후시간·용량관문,실제CPU/dtype검사,확률단계별보존,출력head별비교를 보완한 후 실행을 동결했다. 설치 전검토와 합성코드 전검토는 review/install_precheck.json,review/precheck.json에 있다. 최종 독립 결과검토는 review/의 최종 산출을 따른다.

입력 감사의 이력 보존에는 한계가 있다. 작성자의 도구 이력 재확인은 감사 스크립트의 성공 실행8회를 세지만 최종 result.json의 수동 iteration 표시는7이다. 계산값을 바꾸거나 다시 실행하지 않고 DIAGNOSTIC_HISTORY.md에 정정했다. 일곱 이전 진단 산출·실행시점 소스 snapshot은 따로 보존되지 않았으며, 현재 최종 코드/입력과 최종 결과만 완전히 대조할 수 있다. 이 감사들은 코드·기록 보완을 위한 반복이며 모델 학습이나 점수 탐색이 아니다. 누락된 과거 PID/시각/해시는 추정하여 채우지 않는다. 최종 수치의 독립 검산과 과거 실행 이력 보존의 한계를 구분한다.

기술목표는 환경과 입력재현 준비였다. 학습목표는 설치/합성실행/원출력재현/F1평가를 구별하고,결측표시·문맥순서·정밀도의 의미를 설명하는 것이다. 질문과 실패 계층은 LEARNING_NOTES.md에 남겼다. 학습자 이해와 실제 하드웨어 동작은 평가하지 않았다.

## 다음 회차

round005는 보호자료를 열지 않는 **개발전용312입력 산출·원문맥순서 복구·추론설정 동결**을 수행한다. 설치를 반복하지 않는다. 가용RAM조건이 충족된 경우에만 이번에 실행하지 못한 합성smoke를 한 번 수행한다. 실제선박 추론·새F1·M4 gradient학습은 아직 후속이다. 원출력 재현을 건너뛰어 M4 성능을 주장하지 않는다.

입력계약이 완성됐지만 RAM관문이 계속 미달이면 동일준비회차를 연쇄생성하지 말고 자원제약과 정확한 재개방법을 남긴다. 구체 범위·예산·명령·인수조건은 NEXT_SESSION.md에 있다.
