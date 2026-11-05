# 다음 Astra high 관리자 — Round021 실제 확률+공간 통제비교

020은학습0/점수0/코드미완료로45분예산마감했다. 새F1없으며역사baseline.5930133966423605유지,독립/공식null이다. 제어수리반복으로돌아가지말고이번021에서실제동일조건성능비교를수행한다. 원본및020미완료소스는보존한다.

## 시작과입력
AGENTS/STATUS/CYCLE_PROTOCOL, 본문, round020 ROUND_REPORT, artifacts/result.json, review/*, manager/USER_PROTECTION_AMENDMENT.md, historical_protection_reference.json, ROUND021_FIXED_BRANCH.md, round021_source_evidence.json, round021_parquet_metadata.json, host_turn_evidence.json을읽는다. incomingreceipt accepted/session/SHA와중복021claim/process확인후배타claim. 관리자Astra high와작성/독립검토Luna xhigh/forknone, root+2≤host4, 파일별단독소유,추가child금지. 모델요청과host증거를분리한다.

## 고정실험과수정할부분
round020/code/run_performance.py(미승인)와configs를021로필요부분복사한다. 알려진결함: TabICLINNER787행파일의전체INNERID/label/day를검사한후SELECT394만추출해야한다. 현재394개를전체CSV와비교하는버그가있다. source/config보호규칙일치, ConvergenceWarning실패, fit당120초실제상한, SELECT/OUTER rowkey원확률저장을완성한다. M4/제어framework확장금지. 020은prepare도실행하지않았다. metadata/SELECT무학습preflight와소스검토후동결한다.

baseline은020에서정의한seed42 LGBM/CatBoost/TabICL원확률12열clip1e-6→log→SELECT-onlyStandardScaler→L2multinomial LogisticRegression C1/lbfgs/maxiter1000/classweightNone/seed42다. 후보는동일12열+현재2026공간prototype8열(20열)이며나머지동일하다. 020저장모델이없으므로baseline3+candidate3=최대6meta fit, 새basefit0/TabICL추론0/grid0/재시도0. 모든모델저장/reload후OUTER1회평가하며사후threshold조정없음.

기본입력: round002/artifacts/probabilities/fold_{f}_{baseline_lightgbm|candidate_catboost}_{inner_select|outer}.npz 및inner_split_roster/manifest; readonly TabICLv2_F156_공유자료의seed42/fold별inner_predictions.csv와original_oof_predictions.csv. 정확경로는020config. INNER는해당fold파일만사용하고globalOOF대체금지. 각foldFIT3144/3144/3145,ES393,SELECT394,OUTER1966/1966/1965와라벨/ID/class순서검사. 확률year가없어2026출처가정임을표기하고공간자료year2026와정확key대조.

공간입력은 D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/26_11_2/work/재식별_투트랙_001r1/s6_fingerprint_grid.parquet (SHA b732e2d87f795885426abbc805381e29bcad466e8be7abf37fc4c361bd853131). 020manager/ROUND021_FIXED_BRANCH.md의정확계약: year2026/blockfull/res.01,.05/개발5897ID predicate와필요열projection을적용후materialize,2025/holdout1475행노출금지. 기존system C:/Users/dlehs/AppData/Local/Programs/Python/Python313/python.exe에pyarrow24.0.0이있다. 이환경에서필터추출만하고round002환경에서sklearn학습가능;전역환경변경금지. 각선박비음수finiteweight합1,각foldFIT만의class별동일선박가중prototype q, Bhat=sum sqrt(pq)8열(spatial_bhat_r001_c0..c3,r005_c0..c3). SELECT/OUTER는FIT와disjoint,querylabel사용금지. 누락profile은NaN→constant0 imputer(add_indicatorFalse),SELECT-onlyscaler,분모5897유지. 전체dense행렬금지,sparse/순차fold. 생성소스import/top-level실행및S3재스캔금지.

## 사용자보호와채택
자망1·통발2개선에집중. 역사5seedTP=[2381,908,116,92],sameconditionround002TP=[2389,889,108,90],support=[2920,2016,835,126]. 보호0/3각각정수TP비감소를두reference모두에요구해최소TP0≥2389,TP3≥92다. 020stacker는미채택이므로021baseline은증분효과비교용이며사용자보호reference를대체하지않는다. 각reference별protected gain/loss/net,전체/trueclass별예측전이,표적1/2TP recall precision F1 FP출처를보고한다. baselineprediction0/3전체잠금이나OUTER정답별예측골라끼우기금지.
historical prediction CSV는 D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/artifacts/exp01/sqrt_macro/outer_predictions.csv SHA dfdf805f5c60cff019400e3b16f57f5d03aa6d24277e31c3cdfb2c5b2f4992a4. bytes/header만동결전에확인,행은모든meta적합/reload뒤읽어같은5897ID/y/fold검산과보호gainloss보고에만사용한다.
기존진행관문micro+.005/paired95%CI하한>0/macro·각classF1·나머지recall·일수구간micro하락≤.03는유지하고보호classrecall은0으로강화한다. 후보대baseline12열의증분관문과역사/seed42절대보호를모두보고. .7도달과채택/독립/공식을분리한다. 개발평가반복노출,holdout미개방,독립/공식null. 실제correct/micro/macro/class/1–7,8–30,31–90,91+일/fold 및gainloss,선박bootstrap5000seed20261105,확률행합1e-6/reload1e-12.

## 예산·실패·마감
관리45분중마지막5분문서,계산30분중job1200초,feature600초/meta각120초/6fit최대,동시1/threads3. 예상peak≤1.5GiB,실행직전가용≥2.5GiB확인. RAM부족시코드/문서/검토후재확인,메모리대기polling/사용자process종료금지. 모든출력/tmp/cache021안. feature不가용시원인과baseline계산여부를정직하게보존하고무제한추가모델/전체TabICL우회금지. 성능미달시실제오류/보호손실을근거로다음한가설을유한계획으로고정한다;samefailure반복금지.
완료REPORT/STATUS(current_round021,handoff.readytrue,activeworkers[])/LEDGER/NEXT갱신후 Start-NextSession.ps1 -FromRound round_021로freshAstra high인계하고accepted영수증확인즉시종료. structuredchat닫기CLI없으면완료탭수동닫기제한기록. 분석회신주소 orca_session_id:codex_6b307c5a_55da_483c_b425_0031c6f730b8에실제correct/micro/net/보호/.7여부/다음세션ID+receipt회신. 반복승인질문불필요.
