# Round021 — 저장 확률 결합에 현재 공간분포 8열 추가

실험 전 고정: 2026-11-05 00:07 UTC. 인계된 round020 미실행 코드를 최소 수정한다. 기술 목표는 실제 3-fold 통제 비교와 저장 예측 검산이며, 학습 목표는 확률 결합과 FIT-only 공간 참조가 각각 무엇을 학습하는지 설명하는 것이다. 학습자 이해 달성이나 장치 실측을 주장하지 않는다.

## 가설과 유한 실행

동일 seed42 LightGBM/CatBoost/TabICL 원확률 12열을 clip[1e-6,1] 후 log 변환한 기준선과, 여기에 현재 2026 공간 Bhattacharyya 8열을 추가한 후보를 비교한다. 두 모델 모두 fold별 SELECT394에만 StandardScaler와 L2 multinomial LogisticRegression(C=1,lbfgs,max_iter=1000,class_weight=None,random_state=42)를 적합한다. 추가 basefit/TabICL 추론/그리드/재시도는 0, meta 최대6회다. argmax 동률은 클래스 순서0,1,2,3의 첫 항목이다.

단계1: 전체 INNER787의 ID/라벨/관측일 정합 후 SELECT394 원확률만 구성하는 무학습 preflight 및 독립 소스 검토. 단계2: 승인된 소스에서 기준선3 fit/save/reload를 먼저 수행한다. 단계3: 공간추출과 후보3 fit/save/reload. 단계4: 모든 사용모델 reload 및 소스 동결 후 OUTER 평가 한 번. 공간이 실패하면 원인을 보존하고 기준선만의 실제 결과를 보고할 수 있지만 후보성능을 만들거나 다른 모델로 우회하지 않는다. 어느 단계든 실패한 학습을 재시도하지 않는다. OUTER 점수를 본 뒤 설정/threshold/행별 예측 선택을 하지 않는다.

## 입력과 접근

정확한 입력 경로는 round020/configs/experiment.json 및 manager/ROUND021_FIXED_BRANCH.md를 계승하며 round021/configs에 고정한다. 3-fold FIT=3144/3144/3145, ES=393, SELECT=394, OUTER=1966/1966/1965. SELECT TabICL은 해당 fold INNER 파일에서만 추출하며 global OOF를 대체 입력으로 사용하지 않는다. 확률의 2026 표기는 코호트 출처 가정이지 행별 실측연도가 아니다. OUTER5897은 반복 노출된 개발 평가이며 독립/공식 성능은 null로 남긴다. holdout 및 2025 개별행은 읽지 않는다. T5/local_rel 기존 transductive 조건과 역사 TabICL 전처리 불확실성을 보존한다.

공간 원본 SHA256=b732e2d87f795885426abbc805381e29bcad466e8be7abf37fc4c361bd853131. pyarrow dataset에 year2026/blockfull/res.01,.05/개발5897 ID predicate와 필요한 열 projection을 먼저 적용한 뒤 materialize한다. 저장 parquet 한 rowgroup의 디코딩은 내부적으로 다른 행을 다룰 수 있으나 반환/분석/저장되는 행은 이 predicate에 한정한다. 원생성 소스를 import/실행하거나 원자료를 재스캔하지 않는다. 기존 Python313+pyarrow24에서 필터추출, 기존 round002 환경에서 sklearn 적합한다.

각 선박·해상도 weight를 비음수 finite 합1로 정규화하고, 해당 fold FIT의 클래스별 동일선박가중 평균분포 q를 재정규화한다. SELECT/OUTER 쿼리 p와 sum sqrt(p*q)를 8열로 계산하며 query label은 사용하지 않는다. FIT/query disjoint를 검사한다. 누락은 NaN→constant0 imputer(add_indicator=False), SELECT-only scaler, 분모 유지. sparse 처리이며 전체 dense profile 행렬을 만들지 않는다.

## 판정과 저장

후보 대 12열 기준선 micro 개선 ≥.005, 선박 단위 paired bootstrap5000(seed20261105) 95%CI 하한>0, macro 및 각 class F1·비보호 recall·관측일수별 micro 하락≤.03를 요구한다. 보호0/3 recall하락은0이며 역사5seed TP=[2381,908,116,92]와 round002 seed42 TP=[2389,889,108,90]를 각각 보호한다. support=[2920,2016,835,126], 합친 정수 하한 TP0≥2389,TP3≥92다. 실험 기준선은 보호 reference를 대체하지 않는다. 역사예측 CSV는 해시/header만 사전에 확인하고 모든 모델 적합/reload 후 행을 읽어 동일5897 ID/y/fold와 TP를 검산한다.

각 모델 correct/micro/macro/class precision/recall/F1/TP 및 fold, 1–7/8–30/31–90/91+일, reference별 gain/loss/net, trueclass별 prediction transition 및 자망/통발 FP출처를 저장한다. row-keyed SELECT/OUTER 원확률, 모델, 재로드 오차≤1e-12, 확률 행합오차≤1e-6, 입력/소스/설정 해시와 명령·PID·exit·로그를 저장한다. 개발.7 관찰, 후보채택, 독립검증, 공식점수는 별도다.

## 자원과 종료

회차 시작00:03:07UTC, 계산마감00:43:07UTC, 관리마감00:48:07UTC(45분 중 마지막5분 문서). 계산총30분, job1200초, 공간600초, 각 meta fit120초 실제상한. 동시계산1/threads3. 예상peak≤1.5GiB: parquet 압축8.35MB/전체 비압축17.9MB, sparse profiles+8-column queries+small sklearn/import reserve에 근거한 미측정 보수 추정. 시작가용≥2.5GiB를 각 단계 직전 재확인하고 다른 Python 계산도 기록한다. 부족하면 소스검토·문서 등 독립 작업 후 재확인하며 RAM 대기 polling이나 사용자 프로세스 종료를 하지 않는다. 실행 중 메모리 상한은 소유 프로세스에만 적용한다. 모든 출력/temp/cache는 round021 안에 둔다.

작성 code/config는 Luna author 단독, review는 별도 Luna reviewer 단독, 관리·실행·공유상태는 manager 단독. 요청 모델/effort와 호스트 turn_context 증거를 분리한다. root+2=3/host4, 보조 추가생성 금지. 완료 후 REPORT/STATUS/LEDGER/NEXT 저장, current_round021 유지 및 handoff.ready=true. 미달이면 실제 오류·보호손실에 근거한 다음 한 가설과 유한 예산을 기록하고 새 Astra high 수락 영수증 확인 후 종료한다.

예상 결과는 공간정보의 증분 신호 여부를 판별하는 것이며 F1 상승이나 .7 달성을 가정하지 않는다. 실패 계층은 입력/계약/특징/메타모델/평가로 구분한다. 설명 질문: 전체 INNER와 SELECT를 왜 구분하는가? 클래스 prototype에 query가 섞이면 어떤 누수가 생기는가? micro 상승과 보호 TP 하락이 동시에 생기면 왜 기각하는가?
