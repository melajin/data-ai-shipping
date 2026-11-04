# 다음 Astra high 관리자 — Round020: 저장확률 결합으로 실제 F1 비교

최우선은 사용자가 다시 강조한 다음020·021 두 회차의 실제 성능실험이다. 제어·재현 검증의 누적을0.7목표 달성으로 대체하지 않는다. 채택된성능개선0, 역사개발baseline micro.5930133966423605/macro.5252719738966167, 미채택탐색.5933525521451586, 독립/공식null이다. 개발5897척은반복노출이며 새독립평가가아니다.0.7은최소4128정답이고미측정도달을주장하지않는다.

## 시작과필수읽기

root AGENTS/STATUS/CYCLE_PROTOCOL, 본문, round019 ROUND_REPORT·review/SOURCE_REVIEW·FINAL_REVIEW·artifacts/result.json·manager/host_turn_evidence/PRIORITY_CORRECTION/PERFORMANCE_NEXT_PLAN 및 orchestration_message_01~06을읽는다.019 제어실패나미실행은M4경로의국소제약이며 기존성능경로의필수관문이아니다. M4 전체estimator/제어수리 후속은보류하고020에서실제개발F1을산출한다.

수신launch receipt의accepted/newsession/SHA와현재세션일치를확인하고020폴더/claim/계산프로세스확인후배타claim한다. 동일회차관리자있으면중복실행금지.019동결소스/실패receipt는보존한다. 요청관리자gpt-6-astra/high, 보조작성·독립검토각gpt-6-luna/xhigh/fork_turns=none 명시, root+2≤host4와사용자보조4상한. 파일단독소유/추가child금지. model/effort요청과host turn_context를분리기록.

## 성능가설·입력·실행

정확계약은 **round019/manager/PERFORMANCE_NEXT_PLAN.md의Round020전체**다. round002 ROUND_REPORT/configs/experiment.json/code/run_round002_resume.py/artifacts의split·모델·확률manifest, round003 ROUND_REPORT/code/run_round003.py/configs 및 provenance/review를읽는다. 원본code를 import해서역사출력경로에쓰지말고 필요한함수만020/code로옮긴다.

고정후보: seed42의 round002 LGBM sqrt_macro 및CatBoost, round003 TabICL A 원확률. 각fold의동일INNER_SELECT394ID만사용해logclip1e-6확률12열→SELECT-onlyStandardScaler→L2다항LogisticRegression(C1,lbfgs,max_iter1000,class_weightNone,seed42)적합. basefit0/metafit3/grid0/재시도0. ES/OUTER로메타fit·선택금지. 원확률만사용하고통발배수·decision_score제외. SELECT에서만상보성진단;top1oracle은hardselector설명용이며전체메타모델상한/예상성능이아니다.후보변경을위한무제한탐색금지.

비교기준은동일round002seed42LGBM(3476/5897=.5894522638629812,macro.519210304310862),보조대조는동일3모델고정동일가중평균. 역사5seedbaseline과분리한다. 사전source/config·입력명부·021분기동결→3foldmetafit/저장/reload→OUTER1회평가→독립저장확률검산. 비교후다시가중치고르지않는다. 기존6source평균·통발배수탐색과다른규칙임을기록한다.

LightGBM/CatBoost入力はround002/artifacts/probabilities의fold_{f}_{baseline_lightgbm|candidate_catboost}_{inner_select|outer}.npz,명부inner_split_roster.csv/inner_split_manifest.json. TabICLpackage는round003 INPUT_ROOT가가리키는읽기전용공유패키지에서seed42fold별inner_predictions.csv와original_oof_predictions.csv만허용한다. 원자료F:와holdout개별행/2025Test를읽지않는다. 패키지allowlist/hash·FIT/ES/SELECT/OUTER·ID/year/label/확률4열순서를먼저확인한다. OUTERbytes hash확인은가능하나개별값해석/점수는동결후다.

기존모델들의학습정보범위와동일선박명부를확인한다. 다른feature수(F304/F156)를동일특징이라고하지않는다. T5/local_rel population조건, TabICL전처리문서한계/기존저장확률검증범위는보고한다. 입력없음/정합성실패시없는OOF를만들려고전체TabICL재추론하지않는다. 기존학습경로로실행가능한대안성능실험을선택하되점수노출전새가설·변경변수·총fit예산을계획에고정한다. 제어실행기개발회차로돌아가지않는다.

`round020/code/run_performance.py`와config를작성·독립검토하고계획에실제Python환경/argv를확정한다. 기존environments/round_002_catboost에NumPy/sklearn/LightGBM/CatBoost가있다. 새패키지설치나M4체크포인트는필요없다. 실행예시형식: `& '<확인한 round002환경 Python>' -B './rounds/round_020/code/run_performance.py' --config './rounds/round_020/configs/experiment.json'`. stdout/stderr/OSexit/시각/PID·소유/해시/RAM/결과를남기는작은실행경로를재사용하고검증기기능확장금지.

## 예산·인수조건

관리45분중마지막5분문서,계산≤30분/실제020job≤600초,meta각≤120초/3fit,동시1/threads≤3. 예상peak≤1GiB(약1만행×12확률+소형모델+라이브러리여유)로계산전가용≥2GiB·다른작업확인. RSS>1GiB또는가용<.5GiB시소유작업중단. 부족하면코드/명부metadata/문서후직전재확인,RAMpolling/사용자프로세스종료금지. 출력/temp/cache/모델/확률은020아래만.

명부5897고유척/OUTER중복0/라벨0~3/finite/[0,1]/행합1e-6,저장reload확률差≤1e-12. baseline/candidate/fixedmean의correct/micro/macro/클래스recall/F1/통발/관측일1–7·8–30·31–90·91+/foldとgain/loss/net、선박bootstrap5000(seed20261105)95%CI를남긴다. 조건progress는micro+.005·pairedCI하한>0·macro/각classrecall/F1/각구간micro하락≤.03·계보/reload통과. .7실제도달/이진행관문/독립·공식도달을따로기록한다. fallback예외·미평가값은null,새학습자이해/하드웨어실측을꾸미지않는다.

##021분기와마감

020micro≥.7이면서보호·계보통과면021seed2026확인(새LGBM3/CatBoost3/meta3최대9fit,기존TabICLseed2026확률,관리45/계산30분,동시1/threads3).0.7미달이면소폭개선확인seed만으로021을소진하지말고더풍부한형태/지역/시간표현의한가설+동일조건baseline비교최대6fit로전환한다.021표현후보는현재미확정이며분석세션정적근거가추가전달될수있다.020관리자는SELECT진단과캐시계보/가용성/기존실험노출을확인하여 **020OUTER를열기전에** 정확열목록/loader/모델/예산을사전분기표에고정한다. monthly35는과거+26/INNER음수,exp04/08은큰악화라기본재실행후보가아니다. sqrt_micro도이미실행되어핵심에서제외한다.

완료round020 REPORT/STATUS(current_round=round_020,handoff.ready=true,active_workers=[])/LEDGER/NEXT에실제F1·채택여부·미달최대병목·다음근거를저장하고 Start-NextSession.ps1 -FromRound round_020으로freshAstra high021에인계수락확인즉시중지. 승인반복질문불필요. 새session+prompt수락은receipt로확인하고공유상태사후수정금지. structuredchat닫기지원없으면완료탭만수동닫기제한을남긴다.
