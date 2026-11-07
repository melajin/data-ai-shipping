# Round021 최종 사전분기 — 019 말미 추가근거 반영

020 평가 전 사용자 정정: USER_PROTECTION_AMENDMENT.md를 계승한다. 역사채택5seed와동일조건seed42양쪽대비보호class0/3 recall하락0, 합친TP하한2389/92. 자망·통발개선과FP전이를함께검사한다. .7이상이라도보호실패면seed확인확대하지않고아래공간8열통제비교에강화보호를적용한다. 020stacker가미채택이면021에서그것은표현효과분리용experimental baseline이며사용자보호reference는계속역사5seed및round002seed42다.

이 문서는 PERFORMANCE_NEXT_PLAN 및 next_round_brief의021미확정/최대6basefit 표현후보 문단을 대체한다. 근거는 orchestration_message_07~10이며 파일 내용/개별특징은019에서읽지않았다. 전달근거와실제다음회차확인을구분한다.

020이개발micro≥.7이고보호·계보통과면기존계획의seed2026확인으로간다. .7미달이면 **같은stacker12열 대 같은stacker12+현재기간 공간분포8열**의통제비교다. baseline메타3+후보메타3fit최대6, 새basefit0/TabICL추론0/S3재스캔0, grid0/재시도0. C1/lbfgs/maxiter1000/seed42/SELECT-onlyscaler와동일명부를유지한다. baseline저장모델을정확해시·입력동등성검증후재사용하면새fit3만한다.

정정된입력절대경로는 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/26_11_2/work/재식별_투트랙_001r1/s6_fingerprint_grid.parquet`(전달size8,353,532bytes), 생성source는같은디렉터리code/s6_fingerprint_build.py다. 이전메시지D:/repos prefix는오류이므로사용하지않는다. schema(id,year,block,res,cell,weight),year2026/blockfull/res.01,.05/개발5897 ID predicate+필요열projection을먼저적용한다. 2025/holdout1475개별행읽기금지. 생성소스를import/top-level실행하지않고작은metadata/hash/현재기간Jan–Jun2026계보를검증한다. query정답이나동일선박2025profile검색을하지않는다.

각선박·해상도의비음수finite weight를합1로정규화한다. FIT선박만으로각class의동일선박가중평균분포q_c를만들고재정규화한다. query p_v와 Bhat=sum sqrt(p_v*q_c)를계산한다. 컬럼은spatial_bhat_r001_c0..c3,r005_c0..c3의8개,유한값[0,1]. 메타query는INNER_SELECT/OUTER만이므로FIT와disjoint이며자기기여없다. FIT행을메타학습에추가하지않는다. 만약FITquery생성이필요하도록범위를바꾸려면FIT내교차적합이필요하므로이번계약에서는금지한다.

profile없는선박도분모5897유지,해당8열NaN→사전고정constant0imputer(add_indicatorFalse)로처리하고지원수·누락패턴을보고한다. scaler는SELECT만fit한다. 결측으로query정답을유추하거나분모제외금지. prototype의label소스는현재foldFIT명부만이고SELECT/OUTERlabel은feature계산에금지다.

020은row-keyed(id,year,fold,role)×model×p0..p3/y/observed_days 및sourcehash를보존한다. TabICLINNER는반드시해당fold/inner_predictions.csv, globalOOF를INNER로대체금지(다른foldFIT문맥예측이다). OUTER만해당foldrole의원OOF를쓴다.021은키·값동등성후8열만추가하며증분효과를비교한다.

관리45분/계산30분/동시1/threads3. 소형sparseprofile처리와meta모델peak≤1.5GiB보수추정,가용≥2.5GiB직전확인·저메모리시독립작업후재확인. largefullmatrix금지,sparse/streaming/순차fold. feature생성≤600초/모든job≤1200초/관리마감우선,각metafit≤120초. 실제size/cardinality를metadata에서확인해예상RAM이초과하면시작전에더보수예산을명시하며사용자프로세스종료금지. 관문/지표는020과동일,후보0.7기대값을만들지않는다.

사용자분석세션회신주소 `orca_session_id:codex_6b307c5a_55da_483c_b425_0031c6f730b8`를020/021인계에보존한다. 각완료관리자는실제correct/micro/net/.7여부/다음새세션ID와accepted receipt를status로회신한다.중복학습을요청하지않는다.
