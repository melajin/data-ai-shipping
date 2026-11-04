# Round020·021 성능 목표 복귀 계획

사용자 메시지 msg_8660a1d16d5f, msg_b82fbfa3001b, msg_04d0e2bbf75f, msg_cae4bc359af7를 반영한다.019 제어작업은 현재 유한 계약에서 끝내며 다음의 성능 실험을 차단하는 관문으로 삼지 않는다. 0.7은 목표이지 예측 성능이 아니다. 기존3497정답에서0.7에 도달하려면 최소4128정답, 순증631척이 필요하다. 선택될020 같은조건 기준선은3476정답이므로 그 기준과0.7 간격은652척이다.

## 선택 이유와 기각한 지름길

기존 sqrt_micro는 fullINNER 조건3fold×5seed에서 이미 완료되고 sqrt_macro보다5척 낮았다는 정적조사 메시지를 받았다. 정확 보고서 경로를020에서 확인하되 분리ES로 같은 작은변경을 반복하는 일을 핵심전략으로 삼지 않는다. 직접 읽은 이전repo reports/temporal_final.md에서 monthly_repeat35는 none_micro 대비+26척/CI0포함/INNER delta−.004235이며, 단독으로0.7을 기대할 근거가 약하다. 월35만을020·021 기본 두 회차로 쓰지 않는다.

가장 짧은 새 성능 가설은 이미 저장된 서로 다른 모델의 확률 정보를 class-aware 결합하는 것이다. round002 LGBM/CatBoost는 FIT로 학습하고 INNER_ES에서만 조기종료했으며 INNER_SELECT394척은 메타학습에 사용할 수 있다. round003가 감사한 TabICL A 원확률은 FIT 문맥만 사용했고 INNERunused였다는 저장근거가 있다. 서로 다른 표현의 조건부오류가 다를 수 있으나 실제 개선폭은 미정이다. 과거6source mean이나 통발배수 규칙을 새 실험으로 재명명하지 않는다.

## Round020 고정 후보

모델은 seed42의 LGBM sqrt_macro, CatBoost(round002), TabICL A_raw(round003) 세 개다. 각fold의 같은 INNER_SELECT ID 순서로 원확률4열씩12열을 만든다. 입력확률을[1e-6,1]로clip하고 log를 취한 후 SELECT-only StandardScaler와 L2 multinomial LogisticRegression(C=1, solver=lbfgs, max_iter=1000, class_weight=None, seed42)를 순차적합한다. 클래스순서0/1/2/3, 새base fit0, meta fit3, hyperparameter search0, blendgrid0, 재시도0이다. 기존 저장 배수/decision_score 대신 원확률을 사용한다. 수렴실패·지원누락은 실패로 남기며 사후 파라미터 변경 금지다.

기준선은 같은조건 round002 LGBM seed42 저장 OUTER(3476/5897, micro.5894522638629812, macro.519210304310862)이다. 보조대조로 같은3모델의 고정동일가중평균을 보고한다. 역사5seed .593013과 직접 조건효과를 혼동하지 않는다. SELECT상보성 진단은 모델별정오/서로고침/세모델 모두오답/정답union을 기록한다. top1 union은 hard-selector의 설명용상한이며 logistic 전체가능성의 이론상한이 아니다. 진단을 보고 C나feature를 바꾸지 않는다. SELECT fit 점수를 일반화성능으로 부르지 않는다.

입력경로: round002/artifacts/probabilities/fold_{f}_baseline_lightgbm_inner_select.npz 및 candidate_catboost_inner_select.npz, 동일 outer.npz; round002/artifacts/inner_split_roster.csv와 inner_split_manifest.json. TabICL 원자료패키지는 round003/code/run_round003.py INPUT_ROOT의 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료`, evaluation/seed_42/fold_{f}/inner_predictions.csv와 seed_42/original_oof_predictions.csv다. 패키지는읽기전용이며 round003 allowlist/manifest/metadata검사를 필요한범위만 재사용한다. 기존 code는 top-level 실행하지 말고 필요한 함수만 새020코드로 옮긴다.

훈련자료와 선택정보범위가 일치하는지 ID/year/fold/role/label/class order를 정확조인한다. 각모델 원특징 수는다르므로 동일특징 실험이라고하지않는다. 같은선박분할·관측기간의 저장예측결합이다. T5/local_rel의 기존population 조건과 TabICL전처리기록의 역사한계는 보고한다. FIT/ES/SELECT/OUTER 혼입은 실패다. holdout/2025test/전체원자료는 읽지 않는다.

OUTER 개별값은 source/config/후속분기계획 고정과3개meta모델 적합·저장·reload 동등성 확인 뒤 한 번만 평가한다. 역사점수는이미노출된 개발자료다. fixed source/config/input SHA, OSexit/time/RAM, 저장확률과계수·클래스명부·메타input hash를 남기고 독립Luna가 지표를 재계산한다. wrapper 재설계·M4·checkpoint·새TabICL추론은0이다.

보고: baseline/candidate/고정mean의 정답수·micro/macro·클래스precision/recall/F1·통발변화·관측일1–7/8–30/31–90/91+·fold, gain/loss/net, 선박단위5000 bootstrap95%CI(seed20261105). 후보 진행관문은 동일조건micro+.005이상, pairedCI하한>0, macro와 각class recall/F1·각관측일micro 하락≤.03, provenance/reload통과다. .7달성과진행관문은별도표시하고독립/공식은null이다. 개발후보 채택만으로0.7도달·독립성능을 주장하지않는다.

예산: 관리자45분(문서5분포함), 계산30분, 동시1/threads≤3. meta fit3, fit당최대120초, 전체점수job≤600초. 예상peak≤1GiB는약1만행×12확률과소형모델/라이브러리 여유의보수추정이다. 실행직전가용≥2GiB, processRSS≤1GiB·가용<.5GiB시소유작업중단. 부족하면문서/정적정합성후재확인하며RAMpolling금지. 모든출력/temp/cache020아래, 원본수정금지. metadata/파일검사만으로입력불가가확정되면 없는TabICL OOF생성으로우회하지않고정확한제약과대체성능가설을기록한다.

## Round021 사전분기

020이 실제개발micro≥.7이고보호·계보관문도통과하면021은seed2026동일결합절차의확인으로한다. round002설정에따른새LGBM3/CatBoost3 fit와meta3 fit최대9, TabICL은기존seed2026저장확률만사용한다. 같은split/용량/분리ES/SELECT 유지, maxcompute30분/manager45분/동시1/threads3, basefit당240초, meta당120초, 총상한우선. 새확인도반복노출개발평가다.

020이.7미달이면소폭개선확인seed만으로021을소진하지않는다. 020관리자는OUTER열기전에 SELECT오류상보성·기존캐시의특징출처/메모리/과거노출근거로 **한 개의 더 풍부한 형태·지역·시간 표현 후보와 같은조건baseline의 최대6fit 비교**를 선택하고 정확feature 목록/loader/필터/파라미터를 NEXT분기표에고정해야한다. 이021표현후보는현재정적조사가진행중이므로미확정이다. monthly35단독·기존실패exp04/08재실행은관성적기본분기가아니다. 후보선택의외부근거를받아020실행전계획에확정하며OUTER결과로무제한설계를추가하지않는다. 새로운독립평가나0.7보장으로해석하지않는다.
