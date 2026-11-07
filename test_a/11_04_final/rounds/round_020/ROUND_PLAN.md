# Round020 — 저장 원확률의 고정 Logistic 결합

실행 전 계획. 기술 목표는 동일 5,897척 개발 OUTER의 실제 F1 비교, 학습 목표는 ES/SELECT 분리·fold별 확률 계보·결합 오류의 순손익을 설명하는 것이다. 학습자의 이해 달성은 별도 미평가다.

## 고정 가설과 비교

서로 다른 모델의 class별 확률 정보를 결합하면 단순 평균과 달리 조건부 오류를 줄일 수 있다는 한 가설이다. 성능 예상값은 없다. 입력은 round002 seed42 LightGBM sqrt_macro와 CatBoost, round003가 감사한 TabICL A 원확률이다. 각 fold INNER_SELECT394척에서만 12확률을 clip[1e-6,1]→log→StandardScaler→L2 multinomial LogisticRegression(C1,lbfgs,max_iter1000,class_weightNone,seed42) 적합한다. basefit0/meta3/grid0/retry0. 동일 fold INNER CSV를 사용하며 global OOF로 INNER를 대체하지 않는다.

기준선은 같은 seed42 LightGBM 3476/5897=.5894522638629812, macro .519210304310862. 보조 대조는 세 원확률의 고정 동일가중평균이다. 역사5seed .5930133966423605는 별도 참고이며 조건효과와 혼동하지 않는다. 기존 배수·decision_score·사후 가중치 선택은 없다.

소스/config/입력 SHA와 역할명부·후속분기를 고정한 후 meta3 적합·저장·reload를 완료하고 OUTER를 한 번 평가한다. SELECT 상보성은 설명용 진단이며 후보/C 변경에 쓰지 않는다. top1 정답 union은 hard selector 설명용으로, 전체 meta모델의 상한이 아니다.

## 평가와 제한

FIT/ES/SELECT/OUTER·ID/year/label/클래스0..3을 확인한다. F304와 F156 표현은 다르며 동일 특징 비교라고 하지 않는다. T5/local_rel의 기존 transductive population과 TabICL 전처리 계보의 기록상 한계를 보존한다. 원자료 F:, holdout 개별값,2025Test 접근0; 새 TabICL 추론0; 외부업로드/공식제출/설치0.

5897 고유 OUTER, 중복0, finite 확률[0,1], 행합오차≤1e-6, 저장재로드≤1e-12. correct/micro/macro/class precision recall F1/통발/1–7·8–30·31–90·91+일/fold, gain/loss/net 및 선박 bootstrap5000(seed20261105)95% CI를 보고한다. 진행관문: micro+.005, pairedCI하한>0, macro·각class recall/F1·각일수구간micro하락≤.03, 계보/reload 통과. 개발.7 도달, 진행관문, 독립/공식.7을 각각 구분한다. 독립/공식은 미평가 null이다.

관리45분(문서5분 예약), 계산총30분 중 본job600초, meta각120초·총3fit, 동시1/threads≤3. 예상peak≤1GiB는 약1만행×12열과소형모델/라이브러리 여유 추정. 직전 가용≥2GiB, RSS>1GiB 또는 가용<.5GiB면 소유job만 중단. 메모리 부족시 코드/문서/계보검토 후 직전 재확인하며 RAM polling하지 않는다. 출력/temp/cache는020 아래. 정확 argv/config/hash는 manager/execution_freeze.json에 실행 전 확정한다. 데이터나 정합성 실패시 실패 계층과 남은 단계 기록, 파라미터 변경 재시도 금지.

## OUTER 이전 확정된 Round021 분기

round019/manager/ROUND021_FIXED_BRANCH.md를 그대로 채택해 manager/ROUND021_FIXED_BRANCH.md에 보존한다. .7 이상이며 보호·계보 통과면seed2026확인(최대9fit). .7 미달이면 동일stacker12열 대12+현재Jan–Jun2026공간prototype8열 통제비교,basefit0/meta≤6(020모델 정확 재사용시3),grid0/retry0. 생성원본 읽기전용, s6_fingerprint_grid.parquet의2026/full/.01,.05/개발5897만 projection/predicate 후 읽는다. FIT 클래스별 동일선박가중 prototype, SELECT/OUTER query만, 자기기여없음. spatial_bhat_r001_c0..c3,r005_c0..c3, NaN→constant0 imputer(add_indicatorFalse), SELECT-onlyscaler. 원본전체2025/holdout행 로딩 금지. 원본 경로/생성source·정확 예산은 보존 분기문서가 권위다. 020 OUTER를 본 뒤 이 분기를 고르거나 바꾸지 않는다.

작성자·검토자는 각각 Luna xhigh, 관리자 요청 Astra high. 호스트 turn_context는 별도 증거이며 내부 모델 인증과 구분한다. 파일 담당은 manager/delegation.json. 결과/STATUS/LEDGER/NEXT를 마감하고 새 Astra high 수락 영수증 확인 후 이 관리자는 종료한다.

## 평가 전 사용자 우선 정정

manager/USER_PROTECTION_AMENDMENT.md가 보호class0/3의 .03 recall 하락허용을 **0**으로 대체한다. 역사5seed와같은조건seed42를모두보호해정수TP class0≥2389,class3≥92를요구한다. class1/2TP·recall·precision/F1·FP전이,각보호class의기준별gain/loss/net를보고한다. 고정모델·3fit예산은바꾸지않으며점수확인후튜닝은없다. 021도이규칙을계승한다.
