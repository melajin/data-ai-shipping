# 다음 Astra high 세션 — Round 002

현재 준비 상태: Round 001 계산과 독립 검토 수신을 마감했다. `STATUS.handoff.ready=true`를 확인한 뒤 실행한다. 모든 새 파일은 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final` 아래에 둔다. 이 문서는 새 세션에 주는 실행 지시이며 사용자에게 다시 같은 허가를 요구하지 않는다.

## 시작 시 확인

1. 이 폴더의 AGENTS.md, CYCLE_PROTOCOL.md, STATUS.json, EXPERIMENT_LEDGER.csv, `rounds/round_001/ROUND_REPORT.md`, execution 최종 JSON 및 `rounds/round_001/review/review.json`/`REVIEW_RECEIPT.md`를 읽는다. 독립 최종 판정은 CONDITIONAL이며 full dynamic 비교는 미측정이다. 관리자 수신기록과 리뷰어 원본의 작성자를 구별한다.
2. `automation/receipts/`의 실제 launcher receipt 및 `round001_NEXT_SESSION.md`/`round001_STATUS.json` 사본을 확인하고 현재 회차·관리자·실행 PID를 대조한다. 이전 작업이 남았으면 중복 실행하지 않는다. 새 세션 수락 증거를 STATUS에 동기화하되 영수증만으로 계산 시작을 주장하지 않는다.
3. 관리자는 `gpt-6-astra`/`high`, 보조는 `gpt-6-luna`/`xhigh`/`fork_turns=none`만 사용한다. host slot 제한 내에서 실행 1명과 독립검토 1명을 기본으로 배정한다. 각 소유권을 분리하고 다른 변경을 되돌리지 말라고 지시한다.
4. 이번 관리자 소유는 `rounds/round_002/**`, `environments/round_002_catboost/**`, CYCLE_PROTOCOL(필요한 사전 변경만), STATUS, LEDGER, NEXT_SESSION이다. 실행 보조에게 필요한 하위 경로를 명시적으로 배정한다. 기존 round001 및 root 소유 AGENTS/.codex/README/automation/receipt를 덮어쓰지 않는다.

보조 최대4명은 매번4명을 생성하라는 뜻이 아니다. 작은 진단은 필요한 수만 쓰고, 이미 확인한 코드·입력·평가계약·환경 증거를 재사용한다. 매 회차 동일한 탐색과 장황한 문서 재작성을 반복하지 않는다. 사전 고정은 변경점·예산·판정만 간결하게 남기고 실제 가설 검증 실행을 우선한다.

## 이번 회차의 질문과 선행조건

질문: **같은 X304·같은 fold FIT에서 다른 모델 계열로 만든 확률이 기준선과 다른 오류를 줄이는가?** 기준선의 조기 종료와 결합 선택 자료를 분리하여 새로운 계보가 있는 확률을 생성한다.

Round 001이 고정 NPZ→저장 sqrt_macro 예측의 재현을 통과하면 이 입력을 prospective 기준으로 쓴다. 옛 동적 T5와 CSV의 완전한 일치가 증명되지 않아도 현재 고정 입력과 모델 재현이 성립하면 새 통제 비교는 가능하다. 그 경우 옛 .59183의 원인은 미확인이라는 제한을 계속 표시한다. 현재 baseline 모델 재현 자체가 실패했다면 아래 학습 대신 그 입력/환경 문제를 먼저 고친다.

원자료 `F:/문제 데이터_수정_1027`와 source repo `D:/repos/fishing-track-classification`는 읽기 전용. 기존 holdout 1,475척의 개별 특징·라벨·예측은 열지 않는다. 개발 5,897척 NPZ와 기존 temporal 개발 cache만 필요 범위에서 읽는다. 기존 source loader는 import-time 쓰기 여부를 점검하고 새 경로에 안전하게 복사하거나 필요한 함수를 작성한다.

## 모델 가용성 선택 — 점수 확인 전 결정

현재 active Python3.13 환경에는 sklearn1.6.1, LightGBM4.7.0이 있고 CatBoost/Torch/TabICL은 없다. 이는 전 머신의 환경 부재를 증명하지 않는다. 기존 TabICL 코드·metadata에는 Python3.12/Torch 환경과 약110MB checkpoint가 기록됐지만 조사 경로에는 실제 checkpoint가 없다. S4는 기존 OOF oracle 결합이므로 새 학습 모델 후보로 취급하지 않는다.

1. 최대 5분 동안 알려진 Python/venv 목록과 설치 metadata를 읽어 CatBoost의 실행 가능한 기존 환경을 찾는다. 광범위한 개인 폴더 검색은 하지 않는다.
2. 없으면 작업루트 `environments/round_002_catboost/` 같은 전용 환경을 만든다. 공개 공식 PyPI의 CatBoost와 필요한 최소 의존성만 설치하고 명령·출처·정확한 resolved version·hash 가능한 배포 파일·환경 freeze를 기록한다. pip cache와 TEMP/TMP도 해당 환경 아래로 지정한다. 전역 환경과 source repo 환경은 바꾸지 않는다. 설치 최대 8분, 유료 자원/원자료 전송 없음. 현재 NumPy ABI·Python 지원 문제는 smoke test로 확인한다.
3. 기존 환경 확보 또는 설치가 성공하면 **CatBoost 후보 1개**를 선택한다. 설치 실패/호환 실패/시간 초과이면 사전 지정 **ExtraTrees 후보 1개**로 전환한다. 실패 로그를 보존한다. 이 분기는 모델 점수를 보기 전 환경 조건만으로 결정한다.
4. 이번에는 Torch/TabICL 대형 환경을 동시에 설치하지 않는다. TabICL은 후속 별도 회차의 후보로 남긴다.

CatBoost는 현재 LightGBM과 다른 학습 방식을 가진 표 모델 후보로서 새 확률 계보를 확보하기 위한 선택이다. 이번 자료에서 더 강하다는 사실은 아직 미측정이다. ExtraTrees는 이미 설치된 도구로 무작위 분할 앙상블의 다른 오류를 검증하는 제한적 대안이다.

## 실행 전 고정할 실험 계약

`rounds/round_002/ROUND_PLAN.md`와 machine-readable config를 먼저 작성하고 hash를 기록한다.

- 입력: 기존 `coach/gpt/rank1_experiments_20261104/artifacts/exp01/`의 준비된 3fold X304. 실제 NPZ 경로·keys·열순서는 round001 manifest와 source adapter를 읽어 확인한다. 같은 304열·동일 FIT·same labels·fixed population 통계로 시작한다.
- 각 fold의 기존 INNER 787척을 선박 단위 층화 분할하여 `INNER_ES`와 `INNER_SELECT`에 약 절반씩 배정한다. 고정 seed `20261105`, sklearn stratified split `test_size=0.5`; 생성 명부/라벨 집계/hash를 저장한다. OUTER를 이 결정에 쓰지 않는다.
- 기존 기준선은 전체 INNER를 조기 종료에 썼으므로 새 선택 자료 분리를 위해 seed42 기준선 3개를 다시 학습한다. 같은 FIT, sqrt inverse-frequency sample weights, macro-F1 early-stop, 기존 exp01 hyperparameters를 그대로 사용하고 eval set만 INNER_ES로 바꾼다. INNER_SELECT는 early-stop에 사용하지 않는다.
- 후보도 같은 FIT로 학습한다. CatBoost 기본 계획은 CPU, seed42, iterations≤3000, depth6, learning_rate0.03, l2_leaf_reg3, thread_count3, MultiClass loss, unweighted Accuracy early-stop200 on INNER_ES, sample weights 없음, 원확률 argmax다. NaN 처리·클래스 열 순서·평가지표 옵션은 실제 설치 API/공식 문서로 확인한 뒤 실행 전 확정한다. 변경은 점수 확인 전 기록한다.
- ExtraTrees fallback은 FIT median imputer(`add_indicator=True`, `keep_empty_features=True`)→ExtraTreesClassifier(n_estimators600,max_features0.7,min_samples_leaf2,class_weight=None,random_state42,n_jobs3). imputer는 FIT에만 적합한다. early-stop은 없고 INNER_ES를 학습에 추가하지 않는다.
- 이것은 모델·목적함수·필요 전처리를 포함한 후보 파이프라인 비교다. 성능 차이 전부를 모델 계열 하나의 인과효과라고 주장하지 않는다.
- 두 모델의 확률은 같은 class order로 INNER_ES/INNER_SELECT/OUTER에 저장하고 모델·FIT ID·입력·환경·source hash와 연결한다.
- 결합은 각 fold의 INNER_SELECT에서만 `p=(1-alpha)*baseline + alpha*candidate`, alpha `{0,0.25,0.5,0.75,1}` 중 micro 최고, 동점은 작은 alpha(기준선 우선)를 선택한다. fold INNER_SELECT들을 합쳐 전역 alpha를 선택하지 않는다.
- 기준선 단독·후보 단독·사전 선택된 blend의 OUTER를 한 번 계산한다. 기존 5seed .593013은 역사 비교로 별도 표시하고 이번 1seed/분리된 INNER 기준선과 특징 효과처럼 직접 혼합하지 않는다.

CatBoost에서는 eval set weight를 생략하고 정확도 계산이 비가중임을 확인한다. 오래된 training API 오류가 나면 제한된 코드 오류 수정만 허용하며 후보·hyperparameter를 결과에 맞춰 바꾸지 않는다. OUTER 라벨은 이미 노출된 개발용이지만 학습·모델 저장 iteration·혼합비 선택에 넣지 않는다.

## 예산과 산출물

- 전체 회차 최대45분. 환경 탐색+설치 최대13분, fit/추론 계산 합계 최대30분. 새 fit 최대6개(기준선3+후보3), 동시 학습1개, threads≤3. 가용 RAM<1.5GiB이면 큰 fit 시작 보류. 사용자 프로세스 종료 금지.
- 계획된 경로: `rounds/round_002/code/run_round002.py`, `configs/experiment.json`, `artifacts/`, `logs/`, `review/`, `ROUND_REPORT.md`. 실행기는 아직 없다. 새 세션이 코드 생성·소스검토·config 고정 뒤 실행한다. 경로를 이미 실행 가능한 파일로 오해하지 않는다.
- 실행 명령을 이 경로에 맞춰 저장하며 모든 bytecode/temp/cache와 CatBoost train_dir를 round002 또는 전용 environments 아래로 지정한다. CatBoost가 cwd에 `catboost_info`를 쓰지 않도록 명시 설정한다.
- 모델 reload에서 저장 INNER_SELECT/OUTER 확률 차이 abs≤1e-12 또는 라이브러리 제약을 설명한 사전 tolerance를 검산한다. ID/role 중복·겹침, class order, finite probability/sum, feature order를 검증한다.
- 결과는 micro/macro, 클래스별 recall/F1, 관측일수 구간, fold별 수치, paired gain/loss/net, 선박 bootstrap95%CI(5000회, seed20261105)를 남긴다. bootstrap은 개발 후보 선택 편향을 제거하지 않는다.
- 기대 결과는 미정이다. 성공 조건은 유효한 새 확률 계보와 같은 조건 비교 확보이며 .7 달성을 전제하지 않는다. 질문: “왜 기존 저장모델을 INNER_SELECT에 그대로 써서는 선택 자료 분리가 완성되지 않는가?”, “새 정답과 새 오답을 함께 세는 이유는 무엇인가?”

## 결과 판정과 다음 분기

1. 입력/계보/재추론 검증 실패면 성능 채택 금지. 원인·실패 계층과 다음 최소 수정만 인계한다. 같은 오류 무제한 재시도 금지.
2. 유효 후보 또는 fold-local blend가 개발 micro≥0.7이면 `development_observed_ge_070=true`로만 기록하고 다음 회차를 독립 평가 노출 이력 감사·동결 검증으로 정한다. 독립성 확인 전 holdout을 열지 않는다.
3. .7 미달이나 이번 동일조건 기준선 대비 micro +0.005 이상, paired CI 하한>0, macro-F1·클래스 recall·관측일수 micro 하락폭 각각≤0.03이면 다음 회차 5seed 확인 후보로 진행한다. 이 규칙은 개발 탐색 진행 기준이며 독립 개선 증명이 아니다.
4. 개선 기준 미충족이면 결과를 보존하고 다음 우선순위는 월별35 특징의 같은 seed·같은 학습규칙 5seed 통제 비교다. 그 회차에서 변경 변수·예산을 다시 사전 고정한다. 한 실패로 모델/시간표현의 이론적 상한을 선언하지 않는다.
5. 어떤 분기든 ROUND_REPORT/LEDGER/STATUS/NEXT_SESSION을 저장한다. current_round는 완료한 round_002를 유지하고 handoff.ready=true로 둔다. active_workers를 정리하고 실제 남은 프로세스가 없는지 확인한 뒤 `automation/Start-NextSession.ps1 -FromRound round_002`로 fresh Astra high 세션을 시작하고 receipt를 기록한다. 첫 round001 launch는 root가 담당하므로 현재 관리자에게 중복 호출하지 말라고 전달되어 있다.
