import csv,datetime,hashlib,json,math
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
result=read(R/'artifacts/evaluation_round021.json');verification=read(R/'review/verification.json')
assert verification['passed'] is True
a=result['methods']['Stacker12_Baseline'];b=result['methods']['Stacker20_Spatial'];hist=result['methods']['Historical_sqrt_macro_5seed'];paired=result['baseline12_vs_candidate20'];ci=result['paired_bootstrap95']['ci95_percentile']
receipts=[read(p) for p in sorted((R/'logs').glob('*_receipt.json'))]
assert len(receipts)==7 and all(x['exit_code']==0 and x['stop_reason'] is None for x in receipts)
compute_seconds=sum(x['wall_seconds'] for x in receipts);peak=max(x['sampled_peak_family_rss_bytes'] for x in receipts);minfree=min(x['sampled_min_available_bytes'] for x in receipts)
decision=dict(round='round_021',decided_at_utc=now,baseline12_adopted=False,candidate20_adopted=False,reason='Both below historical adopted baseline; baseline12 TP3=75<92; candidate20 TP0=2317<2389 and TP3=86<92; candidate loses44 vessels vs12 and CI includes0',historical_adopted_baseline_unchanged=True,independent_saved_prediction_verification='review/verification.json',next_hypothesis='Replace raw spatial Bhat8 by within-resolution centered log affinities; same20 columns and fixed meta model;3 new fits only',hypothesis_is_unproven=True,learning_understanding_assessed=False,hardware_verified=False)
save(R/'manager/DECISION.json',decision)
decision.update(user_stop_next_execution=True,next_hypothesis_status='unexecuted_proposal_only_cancelled_as_next_action',next_action='Explain current degradation only; no new round, experiment or fresh-manager launch')
save(R/'manager/DECISION.json',decision)
canonical={**result,'manager_decision':decision,'independent_numerical_verification':verification}
save(R/'artifacts/result.json',canonical)
report=f'''# Round021 — 실제 6회 적합 완료, 공간 후보 기각

**개발 OUTER 5,897척에서 12열 결합은 3,407정답 / micro-F1 {a['micro_f1']:.9f}, 공간8열을 추가한 후보는 3,363정답 / {b['micro_f1']:.9f}였다. 후보는 순감44척이며 보호조건도 실패했다. 둘 모두 채택하지 않고 역사 기준선0.593013397을 유지한다. 0.7은 미달이다.** 저장된 선박별 예측의 독립 검산을 통과했으며 이는 독립 데이터 평가가 아니다.

## 이전 → 현재 → 다음

020은 코드 미완료로 학습·평가0회였다. 021은 INNER787 전체 계약을 검사한 뒤 SELECT394의 확률을 정확한 ID로 재정렬하도록 수정했다. 검토 통과 후 기준선3fit을 먼저 완료하고, 필터된 현재기간 공간분포를 이용한 후보3fit을 추가했다. 실제OUTER 평가는 한 번, 모델/파라미터 재시도·그리드·새basefit·TabICL추론은0이었다. 다음022는 공간8열의 절대 유사도를 해상도별 중심 로그비율로 바꾸는 한 가지 표현 가설이다. 021의 나쁜 점수를 새 기준성능으로 채택하지 않는다.

## 실제 계산값

| 모델 | 정답/5897 | micro-F1 | macro-F1 | 보호 TP0/TP3 |
|---|---:|---:|---:|---:|
| 역사 채택5seed | 3497 | 0.593013397 | 0.525271974 | 2381 / 92 |
| round002 seed42 LightGBM | 3476 | 0.589452264 | 0.519210304 | 2389 / 90 |
| 이번 12열 결합 | 3407 | 0.577751399 | 0.481602586 | 2428 / 75 |
| 이번 공간20열 후보 | 3363 | 0.570289978 | 0.497077582 | 2317 / 86 |

후보 대12열: 새정답245, 새오답289, 순증-44, micro차이 {paired['micro_delta']:.9f}. 선박paired bootstrap5000, seed20261105의95% 구간은 [{ci[0]:.9f}, {ci[1]:.9f}]이다. 개발 데이터 반복 사용·선택 편향·지리 의존성을 없애는 구간이 아니다. 후보는 역사 기준선보다134척, 같은seed42보다113척 적게 맞혔다. 목표0.7에는 최소4128정답이 필요하다.

| 표적 클래스 | 12열 TP / precision / recall / F1 | 공간20열 TP / precision / recall / F1 |
|---|---|---|
| 자망1 | 800 / .572246 / .396825 / .468658 | 844 / .542765 / .418651 / .472697 |
| 통발2 | 104 / .392453 / .124551 / .189091 | 116 / .370607 / .138922 / .202091 |

공간후보는12열보다 자망·통발 TP를44/12 늘렸지만 연안복합 TP를111 잃었다. 자망 FP는598→711, 통발 FP는161→197로 늘었다. 연안복합에서 자망으로의 오분류는402→495, 통발로는80→97이었다. 역사 기준선 대비 자망 TP는64 적고 통발 TP는같지만 정밀도가낮아져, 표적클래스의 역사 기준 대비 개선도 확인되지 않았다.

사용자보호는 정수TP0≥2389 및TP3≥92다. 후보는72척·6척 부족하다. 역사 기준 대비 class0 gain197/loss261/net-64, class3 gain6/loss12/net-6; seed42 대비 class0 gain191/loss263/net-72, class3 gain8/loss12/net-4다. 12열 기준선 역시class3 TP75로 보호실패다. 후보의 클래스별·참조별 전체전이/FP출처, fold별·1–7/8–30/31–90/91+일 지표는 evaluation_round021.json에 저장했다. 모든 일수구간에서 micro가 하락했으며 변화는 -.013514/-.001548/-.008990/-.006121이다.

## 실행과 검증

- 기존원확률12열 log(clip1e-6), SELECT-only StandardScaler, L2multinomial LogisticRegression(C1,lbfgs,maxiter1000,classweightNone,seed42). 후보만 FIT-only Bhat8을 추가했고 나머지 동일하다.
- 각fold FIT3144/3144/3145, ES393, SELECT394, OUTER1966/1966/1965. fit총6,각모델 저장전 SELECT확률과 저장후 재로드확률의 최대절대차는 모두0(허용1e-12)이었다.
- 00:11:17UTC SELECT사전검사통과; 첫기준선모델저장00:17:48, 기준선3fit완료00:18:01; 후보3fit완료00:28:00; OUTER평가완료00:36:11. 최초F1 저장시각은00:36:10UTC이며 사용자/분석세션에 검산전 값으로 즉시통지했다.
- 공간원본은 year2026/blockfull/res.01,.05/개발5897ID predicate+projection 후 반환행만 처리했다. 370056행,각해상도5897프로필, 모든FIT 및 SELECT/OUTER query 프로필누락0. FIT만으로 클래스별동일선박가중prototype을 만들고 query라벨은특징계산에쓰지않았다.
- 7개실행단계 exit0, 총프로세스관찰벽시계합 {compute_seconds:.2f}초. 가장큰관찰familyRSS {peak/2**30:.3f}GiB, 실행중최소가용 {minfree/2**30:.3f}GiB. 시작전가용2.5GiB와 예상peak1.5GiB 기준을각단계확인했고 RAM보류/강제중단은없었다. 샘플링peak이며 진짜연속최대치 보장은아니다. 다른사용자프로세스를종료하지않았다.
- 호스트turn_context는관리자gpt-6-astra/high, 작성·검토각gpt-6-luna/xhigh다. 요청과호스트메타데이터를 manager/host_turn_evidence.json에분리했으며 내부모델인증이라고하지않는다. 동시이팀root+2/host4, 추가child0.
- 소스별독립승인→단계별해시동결→실행로그→저장예측검산 순서이며 reviewer/FINAL_REVIEW.md와 review/verification.json이최종검산근거다. 모델/입력/소스변경으로점수를높이지않았다.

## 해석·한계·학습

기술적 목표인 실제 통제비교와 검산은 완료했다. 성능개선·보호·0.7 목표는 달성하지 못했다. 실패는 이번 데이터 계약이나 실행이 아니라 선택된 표현·메타모델의 개발 성능 계층에 있다. 394SELECT에20열을적합하는표본민감성과 절대공간겹침의영향은 원인후보일뿐 입증된원인이아니다. 다음회차는해상도별상대공간친화도변환을한변수로검증한다. 추가작은SELECT분할진단은 희소class3와 직접적인성능비교우선순위때문에이번후속으로선택하지않았다.

OUTER5897은반복노출된개발자료다. 독립검증과공식점수는null,holdout개별행/2025반환행/원자료F드라이브접근0,외부업로드/공식제출/유료신규자원0이다. parquet내부디코딩과필터후반환행의분석을구분한다. 사전계약검사에서전체개발y/role/day 메타데이터를읽었으므로 새맹검 또는OUTER라벨무접근이라고하지않는다. 2026표기는확률파일행별실측연도가아닌Train코호트출처다. 기존T5/local_rel transductive조건과TabICL역사전처리문서한계를보존한다.

SELECT공간파일 spatial_features_select_outer.npz는이름과달리CSV내용이며명시적CSVreader+header+sidecar해시로검증했다. 기준선config해시를보존하려고경로를유지했고 실제포맷을숨기지않는다. 후속은명시적CSV읽기를사용한다.

학습질문과활동은 LEARNING_NOTES.md. 학습자의설명·구현능력은아직평가하지않았으며하드웨어실측은없다. 종료후새세션수락은 automation/receipts/round_021_launch.json을확인한다. 현재orca agent CLI에는structuredchat닫기명령이없으므로수락후이관리자작업을종료하고필요하면완료탭만수동으로닫는다.
'''
report=report.replace('reviewer/FINAL_REVIEW.md','review/FINAL_REVIEW.md')
report=report.replace('다음022는 공간8열의 절대 유사도를 해상도별 중심 로그비율로 바꾸는 한 가지 표현 가설이다.', '사용자의 최신 지시로 다음 회차 실행·인계를 중지했다. 공간 로그비율 변환은 검토했던 미실행 제안일 뿐이다.')
report=report.replace('다음회차는해상도별상대공간친화도변환을한변수로검증한다.', '원인 가설의 추가 실험은 하지 않는다.')
report=report.replace('종료후새세션수락은 automation/receipts/round_021_launch.json을확인한다.', '사용자 지시로 다음 세션은 시작하지 않았고 round_021 launch 영수증도 만들지 않았다.')
report=report.replace('수락후이관리자작업을종료하고','현재 정리를 마친 뒤 이 관리자 작업을 종료하고')
report+='\n## 최신 사용자 중지와 설계상의 문제\n\n사용자: “다음 실행하지말고, 현재 왜 낮아졌는지 정리만 진행”. 따라서 다음 회차·추가 학습·새 세션 인계는 실행하지 않는다. STATUS는 현재완료회차021을유지하고 handoff.ready=false/사용자중지를기록한다.\n\n이번 학습은 class_weight=None인 일반 4클래스 LogisticRegression의 log-loss와 L2 규제였다. 자망·통발 전용 손실/전문가나 연안복합·채낚기 recall을 보존하는 학습 제약은 없었다. **보호 규칙은 학습 중 강제 조건이 아니라, 평가 후 후보를 기각하는 채택 관문으로만 구현됐다.** 관문은 실제로 실패 후보를 막았지만, 원하는 제약을 만족하도록 학습하는 설계까지 구현한 것은 아니다. 또한 log-loss 최소화가 micro-F1 상승을 직접 보장하지 않는다. 이는 확인된 설계 한계이며, 작은 SELECT 표본의 과적합이나 공간 특징의 원인 효과는 이번 한 비교만으로 입증하지 못했다. 상세 원인 정리는 WHY_PERFORMANCE_DROPPED.md를 따른다.\n'
(R/'ROUND_REPORT.md').write_text(report,encoding='utf-8')
next_doc='''# Round022 새 Astra high 관리자 — 공간 친화도 상대 로그비율 한 변수

021 실제6fit/OUTER1회/저장예측검산완료. 12열3407/5897=.577751399016449, 공간20열3363/5897=.5702899779548923(순감44,CI[-.0152662371,.0001695778]). 두모델기각. 역사채택3497/.5930133966423605유지,독립/공식null. 후보TP=[2317,844,116,86],보호0/3모두실패. 자세한실패·최초통지는021REPORT/result/manager DECISION과review를읽는다. 반복통제수리로돌아가지말고작은새표현비교를수행한다.

## 시작·역할
AGENTS,STATUS,CYCLE_PROTOCOL,본파일,round021ROUND_REPORT,artifacts/result.json,review/FINAL_REVIEW.md/verification.json,manager/DECISION.json,host_turn_evidence.json을읽는다. incomingreceipt accepted/session/SHA와동일round022claim/process를확인후배타claim. 관리자Astrahigh/보조작성자와독립검토자Lunaxhigh(forknone,명시model/effort)만,root+2≤host4/사용자보조최대4,추가child금지. 원자료F:/와이전D:/repos는읽기전용;모든새출력round022안. 실행증거와모델요청을분리한다.

## 단일가설·변수·고정설정
021공간후보는자망/통발recall을낮은12열비교군대비올렸지만precision이하락하고class0TP111척을잃었다. 절대공간겹침정도에반응하는대신해상도별상대클래스친화도로표현하면이tradeoff가달라지는지가새가설이며미검증이다. 같은실패설정을재실행하지않는다.
기준은021의rawBhat20모델/저장예측을그대로재사용한다(3363정답). 후보는동일logprob12열에각해상도의4개Bhat를 z_c=log(max(B_c,1e-6))-mean_{k=0..3}(log(max(B_k,1e-6)))로변환한8열을붙인20열이다. 해상도.01,.05각각따로center,순서r001c0..3,r005c0..3. 원Bhat의[0,1]검사후변환하며z는[0,1]범위가아니므로그검사를잘못적용하지않는다. 원블록에NaN있으면그4열을NaN으로보존→constant0imputer(add_indicatorFalse),SELECT-onlyStandardScaler. 원12열 clip/log/order는그대로다. L2multinomialLogisticRegression C1/lbfgs/maxiter1000/classweightNone/seed42,fitSELECT394만,최대신규3fit. baseline재fit0/basefit0/TabICL0/공간원자료재스캔0/grid0/재시도0. argmax동률은0,1,2,3첫순서.

## 정확한 입력·재사용
- round021/artifacts/select_raw_probabilities.csv (fold,id,year,role,model,p0..3,y_true,observed_days),3sources×394×3fold=3546행. 원sourceorder는LightGBM_sqrt_macro,CatBoost,TabICL_A_raw. 같은foldID순서를키로정렬하고12열재구성.
- SELECT공간: round021/artifacts/spatial_features_select_outer.npz **내용은CSV** 및 .npz.manifest.json. CSVreader/header로읽고출력SHA8308177f51206a07ae82c81197d105f3dd19fa6e1f7aae97ff54d0f12b7d8148검증. 단순np.load금지.
- OUTER공간: round021/artifacts/spatial_features_OUTER.csv 및 .csv.manifest.json,5897행. 원공간은이미foldFIT-only이며query라벨을특징에쓰지않는다. prototype재생성불필요.
- OUTER기본확률및기준모델확률: round021/artifacts/outer_predictions_round021_long.csv,5methods×5897=29485행. 원3source+Stacker12_Baseline+Stacker20_Spatial. 마지막것을rawBhat20통제기준으로사용한다. 같은5897ID/y/fold/year/role와원확률행합을검사한다. 학습/변환/설정동결전에는OUTER확률행을다시읽지않는다.
- 기존모델/계보는round021/artifacts/baseline_fit.json,candidate_fit.json,models/* 및manager/snapshot_fit_candidate, snapshot_evaluation의해시. 준비단계에는바이트SHA만확인. 원모델과기존결과는수정하지않는다.
- SELECT명부는round002/artifacts/inner_split_roster.csv 및manifest. 역사5seed참조는round021/manager/historical_protection_reference.json의readonlyCSV경로/SHA(dfdf805f5c60cff019400e3b16f57f5d03aa6d24277e31c3cdfb2c5b2f4992a4);새3fit/save/reload완료후행을읽어5897ID/y/fold대조와gainloss에만사용한다. rawseed42LightGBM은저장longCSV의원확률로재현한다.

## 구현과 실행 순서
round021/code의작은fit_meta_worker.py(정확C1/20열),CSV읽기·metrics·bootstrap함수와평가기능을필요부분만round022로복사/재사용한다. 021runner전체실행이나baseline재fit을호출하지않는다. 새작성자는round022/code/run_round022.py와configs만소유,검토자는review만소유. 관리자상태·통합·실행전계획을소유한다. 옛config전체SHA동일성검사를억지로통과시키지말고021원모델/설정/입력SHA와변환한변수의명시적계약을새config에묶는다. 기존원본파일을고치지않는다.
1. 후보transform/설정/입력SHA/유한예산을ROUND_PLAN에동결. SELECT무학습검사에서키/394×20/그룹중심합≈0/유한성/원12열동일성을확인하고정확소스독립검토.
2. 승인후아래CLI를작성된run_round022.py에연결하여실행: `environments/round_002_catboost/Scripts/python.exe -B -X utf8 rounds/round_022/code/run_round022.py --prepare`, 이어 `--fit`, 이어 `--evaluate`. 이CLI는다음작성자가구현해야하는계약이며현재실행가능파일이라고주장하지않는다. 실제args/config는기록한다.
3. 신규후보3fit만순차실행,ConvergenceWarning실패/각fit120초상한,저장전SELECT확률과재로드비교≤1e-12. 모델3개모두완료후OUTER1회추론/저장/점수,threshold·행별예측선별0. 기존rawBhat20기준은저장예측만재사용. 입력실패는원인분리하고실패fit재시도·다른모델우회금지.
4. 결과즉시사용자와분석주소orca_session_id:codex_6b307c5a_55da_483c_b425_0031c6f730b8에최초계산·검산대기를명시해correct/micro/net/0·3TP와보호/1·2precision-recall-F1/.7여부를통지. 저장예측독립검산후확정통지. gate실패해도측정값을먼저보존한다.

## 보호·판정·실패분기
historicalTP=[2381,908,116,92],seed42=[2389,889,108,90],support=[2920,2016,835,126],합친최소TP0≥2389/TP3≥92. 두reference각각classgain/loss/net,전체/trueclass별전이,1/2FP출처보고. 기준rawBhat20대비micro≥+.005,pairedbootstrap5000(seed20261105)95%CI하한>0,macro/각classF1/비보호recall/일수micro하락≤.03,보호0/3recall하락0. 나쁜21기준을이기는것만으로채택하지않고historicalmicro≥.5930133966423605도요구한다. .7관찰/채택/독립/공식은분리한다. OUTER는반복개발이며holdout과2025행접근0,독립/공식null유지.
변환이유효하지않으면source/계약실패로종료하고구체원인보존. 점수/보호가실패하면같은raw/CLR공간stacker미세조정과C/seed/grid반복을다음회차로자동나열하지말고,실제FP손실/표현부족또는표본제약에근거해다른한가설을관리자가설계한다. 0.7은보장하지않는다.

## 자원·마감·인계
관리45분(마지막5분문서),계산총30분/단일job≤1200초/fit각120초/신규fit3/동시1/threads≤3. 작은cached CSV+394×20+sklearn모델로예상peak≤1GiB(미측정추정),시작가용≥2.5GiB를실행직전확인하고다른Python작업도기록. RAM부족은독립코드/문서/검토후재확인,연속polling/사용자process종료금지. 출력/tmp/cache모두022안. 동일실패retry0.
REPORT/STATUS(current_round022,handoff.readytrue,activeworkers[])/LEDGER/NEXT를실제결과로갱신하고미달·실행가능후속은`& .\automation\Start-NextSession.ps1 -FromRound round_022`로freshAstrahigh인계,accepted영수증확인후종료한다. 구조화채팅닫기CLI부재면완료탭수동닫기한계만기록하고무관세션/앱은닫지않는다.
'''
next_doc='''# 실행 중지 — 현재 회차 하락 원인 정리만 완료

사용자의 최신 직접 지시: “다음 실행하지말고, 현재 왜 낮아졌는지 정리만 진행”.

**다음 회차, 추가 학습/실험, 새 관리자 세션 인계를 시작하지 않는다. Start-NextSession.ps1을 호출하지 않는다.**

완료회차는round_021이다. 개발5897척에서12열3407정답/micro.577751399016449, 공간20열3363정답/.5702899779548923(순감44)이며 독립 저장예측 검산은통과했다. 후보보호TP0=2317<2389,TP3=86<92. 두새모델기각,역사3497/.5930133966423605유지. 독립데이터/공식점수는null이고.7미달이다.

읽을문서: rounds/round_021/WHY_PERFORMANCE_DROPPED.md, ROUND_REPORT.md, artifacts/result.json, review/FINAL_REVIEW.md, review/verification.json, manager/DECISION.json. 모든정답/예측/모델/소스해시는보존했다. 원자료/이전저장소수정없음.

확인된문제는연안복합TP111손실이자망44+통발12+채낚기11증가를초과한것,자망/통발FP113/36증가와정밀도하락,12열결합자체가기존seed42보다69척낮은것이다. 학습은일반4클래스logloss+L2이며보호는사후채택gate만이었다. 과적합/공간표현영향은미검증가설이다.

검토했던공간중심로그비율변환및작은SELECT분할진단은모두미실행제안이다. 이를승인된다음작업으로해석하지않는다. 사용자에게새로운명시적실행지시가있을때만재개범위·유한예산을다시정하고,중복세션/claim과RAM을확인한다. 현재는자동재개명령을실행할상태가아니다.
'''
(ROOT/'NEXT_SESSION.md').write_text(next_doc,encoding='utf-8')
s=read(ROOT/'STATUS.json');s.update(updated_at_utc=now,current_round='round_021',round_status='completed_evaluated_rejected_protection_and_micro_failed',manager_session=read(R/'manager/manager_claim.json')['orca_session_id'],current_task='Completed6fits/one development evaluation/independent numerical verification; bothnewmodelsrejected',next_task='Round022 fixed centered-log-ratio spatial8 transform vs frozen021rawBhat20;3newmetafits',active_workers=[],goal_status='in_progress_not_achieved')
s['assistant_model_policy']['current_runtime_assistants']=0;s['paths']['round']='rounds/round_021'
s['scores']['round_021']={'evaluation_population':'repeatedly exposed development OUTER5897; not independent','baseline12':a,'candidate20':b,'paired':paired,'paired_ci95':ci,'protected_true_positive_counts':result['protected_true_positive_counts'],'candidate_adopted':False,'baseline12_adopted':False,'new_meta_fits':6,'outer_evaluations':1,'independent_numerical_verification':True,'result':'rounds/round_021/artifacts/result.json'}
s['scores'].update(independent_micro_f1=None,official_micro_f1=None,development_observed_ge_070=False,independently_verified_ge_070=False,official_score_ge_070=False)
s['handoff'].update(ready=True,next_session_launched=False,next_round='round_022',launch_receipt='automation/receipts/round_021_launch.json',completed_session_id=s['manager_session'],next_session_id=None,accepted_at_utc=None,pause_reason=None,note='Authority is round021 launch receipt. Stop this manager after accepted handoff; do not modify sharedstate afterward.',close_completed_session_status='orca agent help exposes launch/hooks only; no structured-chat close. End current work after acceptance; manually close only completed tab if needed.')
s['budget'].update(actual_new_meta_fits=6,actual_outer_evaluations=1,actual_compute_stage_wall_seconds=compute_seconds,sampled_peak_family_rss_bytes=peak,sampled_min_available_bytes=minfree)
s.update(goal_status='paused_by_user_not_achieved',next_task='No next execution: summarize why current performance decreased; resume only on new explicit user instruction')
s['handoff'].update(ready=False,next_session_launched=False,next_round=None,launch_receipt=None,pause_reason='User explicitly requested no next execution; explain current degradation only',note='Do not launch any new manager or experiment. Round021 is complete; no round021 launch receipt was created.')
s['blockers']=['User stopped further execution; not a resource or technical failure'];save(ROOT/'STATUS.json',s)
ledger=ROOT/'EXPERIMENT_LEDGER.csv'
with ledger.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f));fields=list(rows[0])
assert not any(x['round_id']=='round_021' for x in rows),'Ledger already finalized'
with ledger.open('a',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writerow(dict(round_id='round_021',started_at_utc='2026-11-05T00:03:09.189Z',finished_at_utc=now,status=s['round_status'],hypothesis='Saved probability stacker12 vs same+FIT-only current2026 spatialBhat8;actual6fits',baseline_micro=a['micro_f1'],candidate_micro=b['micro_f1'],evaluation_kind='repeated_development_OUTER5897_independently_recomputed_saved_predictions',new_fits=6,result_report='rounds/round_021/ROUND_REPORT.md',next_task='USER STOP: no next experiment or fresh session; current degradation explanation only'))
save(R/'manager/closing_snapshot.json',dict(utc=now,current_round='round_021',handoff_ready=False,user_stopped_further_execution=True,meta_fits=6,outer_evaluations=1,compute_stage_seconds=compute_seconds,source_readonly=True,raw_F_access=False,goal070=False,report=str(R/'ROUND_REPORT.md'),next_sha256=hashlib.sha256((ROOT/'NEXT_SESSION.md').read_bytes()).hexdigest(),verification=verification))
print(json.dumps({'finalized':True,'utc':now,'baseline12_micro':a['micro_f1'],'candidate20_micro':b['micro_f1'],'compute_seconds':compute_seconds,'handoff_ready':False,'next_execution':'stopped_by_user'}))
