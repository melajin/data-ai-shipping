import csv,datetime,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
progress=json.loads((R/'artifacts/gate/fit_progress.json').read_text(encoding='utf8'))
audit=json.loads((R/'review/partial_gate_audit.json').read_text(encoding='utf8-sig'.replace('utf8','utf-8')))
assert progress['fits_completed']==2 and audit['approved_hashes_match_before_and_after']
decision=dict(round='round_022',status='completed_partial_gate_budget_stop',fits_completed=2,fits_required=8,gate_evaluated=False,gate_pass=None,baseline_cv_micro=None,candidate_cv_micro=None,full3fold_fits=0,s2_fits=0,axis_rejected=False,goal_achieved=False,reason='Fixed wall-clock cutoff before all4CV folds; not a performance rejection',next_round='round_023',next_action='Reuse prepared caches and reviewed source for one fixed8fit procedural replay; current runner has no resume API',prior_two_fits_preserved=True,independent_partial_audit_pass=True,finished_utc=now)
save(R/'manager/DECISION.json',decision)
save(R/'logs/s1_gate_launch_failure.json',dict(stage='s1_gate',error='WinError2 CreateProcess relative Python executable',child_created=False,fits_started=0,correction='absolute Python executable used for s1_gate_absolute',model_search_retry=False,claim_preserved=True))
report='''# Round022 — 준비 완료, 선행 비교 2/8fit에서 예산 종료

**T5·S1 자료 준비와 누출 검산은 완료했지만 4-fold 비교는 2/8fit만 끝났다. 전체 CV 점수와 +0.5%p 관문은 미판정이다. 성능 실패나 S1 축 기각으로 처리하지 않는다.**

이전021의 공간 메타스태커 대신304열 LightGBM+24열 S1 선행비교를 구현했다. 기존304열의 지도T5도 매CV 학습분할 안에서 재계산하고 자기 라벨을 local counts·global prior·fallback 모두에서 제외한다. 다음023은 코드/원자료 조사를 반복하지 않고 준비된 캐시와 동결 코드를 사용해 동일8fit 비교를 완료한다. 현재CLI에resume가없어 한 번의고정8fit replay를절차복구로사전고정하며,이전2fit중복을공개하고보존한다. 튜닝재시도가아니다.

## 확인한 결과

- T5준비41.74초: 공용항구129개, FIT3144척 fishing567869행. 기존log1p_fishing_rows와결측패턴모두일치, 유효2835개최대차8.88e-16. 행별mask독립대조는하지않았다.
- S1준비25.97초:2026FIT 반환1655397행, 유효좌표/날짜1655395행,누락2행. SQLite606004행/36286464bytes. 다른연도/ID반환위반0. centroid관측레코드proxy이며실제체류시간이나부분선전체격자점유가아니다.
- 합성6선박 검사통과: 자기라벨변경·검증라벨순열불변, 다른학습라벨변경시특징변화, donor순서불변. 실제데이터성능검증과구분한다.
- 실제gate02:08:40시작→02:10:02 deadline_stop. fold0baseline14.60초/후보15.21초, 모델2개와438624byte분할특징증거보존. aggregate/prediction파일없음. 독립partial검토가2개모델해시와승인/실행전후소스일치를확인했다. 모델재추론/최종지표검산은다음회차에서완료해야한다.

고정참고1817/3144와엄밀기준선은아직비교할수없다. 관문은후보>=1833과동일절차기준대비>=16정답을모두요구한다. 이번전체3fold/S2는각0회다. TP·precision/F1·FP전이·paired·관측일구간전체지표도미산출이며부분fit를전체점수로확대하지않는다. 기존비교기준LightGBMseed42는3476/5897,TP2389/889/108/90을유지한다. 진단보호2389/90과최종5seed보호2381/92는사용자승인정책으로분리하며미평가다. 개발0.7/독립검증/공식점수달성증거없음.

## 실행 경계와 한계

사용자는기존T5조건유지를위해Train2026(holdout포함)+Test2025의정박위치공용항구집계만명시허용했다. 라벨/예측/평가접근없음. 공유집계projection3열과필터만사용,own-mooring/activequery는FITpredicate를반환전에적용했다. 임시공용distinct키SQLite는정리했다. 원자료/이전repo수정0,외부전송0,하드웨어실측0이다.

01:44가용RAM0.475GiB로footer검사를로딩전에보류했다. 코드작업후01:49재확인3.78GiB에서재개했고polling루프는없었다. 세실행합150.40초,관측peak최대0.427GiB/실행중최저가용약2.78GiB. 진짜연속peak가아닌1초샘플이다. 학습동시1/threads3,다른프로세스종료0. 작업/계산벽시계마감을연장하지않았다.

준비첫snapshot은helper codec/hash대소문자오류와PowerShell독립줄실행때문에실행중생성됐다. 승인hash=실행시작hash=종료hash로활성코드무변경을확인했으며실행전snapshot이라고주장하지않는다(manager/FREEZE_EXCEPTION.md). 이후S1와gate는실행전동결성공확인후별도호출했다. 첫gate호출은상대Python경로CreateProcess실패로child/fit0이었고절대경로로원인수정했다. 잘못된PowerShell문자표시를소스오류로오인한검토지연도있었다. 실제UTF8codepoint는정상이었고문자literal→Unicodeescape변경은의미동일했다.

관리Astrahigh,보조Lunaxhigh2명의요청과hostturn_context를manager/host_turn_evidence.json에분리했다. 내부모델인증이나설정파일로부모모델변경을주장하지않는다.

실패계층은성능이아니라실행계획/시간배분이다. 원천추적·경계확정·검토에시간을많이사용해실제학습은마감80초전에시작했다. 다음회차는준비완료상태를재사용해야한다. 기술적완료는부분이며학습자이해는미평가다. 학습질문: 지도전처리를왜매CV분할에서다시만드는가? 전역prior에자기라벨이남으면무슨문제가생기는가? 관측proxy와실제체류시간은왜다른가? 부분fold결과로전체관문을판정할수없는이유는무엇인가?
'''
(R/'ROUND_REPORT.md').write_text(report,encoding='utf8')
next_text='''# Round023 인계 — 준비캐시 재사용, S1 선행8fit만

Round022는2/8fit에서고정02:10UTC계산마감으로종료했다. 성능실패아님,전체점수/관문미판정. reports/ROUND_REPORT는 rounds/round_022/ROUND_REPORT.md. 2개모델과fold0feature증거는보존하며 현재runner에resume기능없으므로 **동일고정8fit한번 replay**를절차복구로사전고정한다. 이전2fit중복을숨기지않으며튜닝/새변형/원자료재수집0.

새관리자Astrahigh는기존claim/liveprocess중복확인후다음setup을1회실행한다(이미round023있으면중단하고owner확인). Root만새Orca세션launch한다. 아직다음세션수락전이다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_022/manager/prepare_next_round.py
```

setup은reviewedcode4개+config+T5cache/manifest+S1SQLite/manifest+checker를round023로복사하고해시동일성을확인한다. 기존gate승인해시를재사용하며새로운모델코드고치지않는다. 새manager/runtime_contract.json은현재시각기준45분관리/40분벽시계계산마감(누적계산30분),job900초,동시1/threads3/free>=2.5GiB/peak추정1.5GiB,8fit1회/탐색0을고정한다. 새launcher차이는hardcoded과거deadline을새runtimecontract에서읽는1줄뿐이다. 코드재조사대신이차이와복사해시,새plan을검토하고gate승인/동결을새경로로기록한다.

검산checker의원래round_dir은round022로하드코딩되어있다. **복사된round023 checker에서만 `round_dir = root / "rounds" / "round_022"`를 `round_dir = out.parents[1]`로변경**, 새review/gate_approved_sources.json의경로/현재hash를확정하고독립검산담당자가검토한다. 원본022는수정하지않는다. 정확한실행명령:

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_023/manager/launch.py --stage s1_gate --seconds 900 --python 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' --script rounds/round_023/code/run_gate.py -- --run-gate
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_023/review/verify_gate_result.py rounds/round_023/artifacts/gate
```

검산명령은성공8fit+gate_result존재를확인한뒤실행한다. source→freeze→execution 순서를각tool결과성공확인으로분리하며PowerShell오류뒤다음줄을실행하지않는다. pytest나새단계코드를추가하지않고기존independentchecker로저장metrics/확률/8modelreload를확인한다. 완료후paired/관측일/FP전이보완지표를보고한다. 저장결과검산은독립데이터평가가아니다.

gate기준은동일3144명부 후보>=1833(고정1817+16) AND 후보−엄밀동일절차baseline>=16. 304열T5는각CVtrain에서재계산,selfcounts/prior/fallback제외. S1은centroid/record-time-binproxy임을유지하고원래모든geometryS1/0.7의이론적상한으로확대하지않는다. 023의전체3fold/S2는0회; 숫자관문결과로다음사전로드맵단계를정한다.

사용자의공용항구집계무라벨자료승인은유지되지만다음은이미준비캐시를쓰므로새Test/holdout읽기불필요. 진단보호TP2389/90,최종5seed2381/92정책과RAM보류→독립작업→실행직전재확인,사용자프로세스종료금지를계승한다. 중단시부분산출보존/실제fit수기록,동일오류무작정재실행금지. 목표0.7미달/독립공식null.
'''
(ROOT/'NEXT_SESSION.md').write_text(next_text,encoding='utf8')
s=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8-sig'))
s.update(updated_at_utc=now,current_round='round_022',round_status=decision['status'],goal_status='active_not_achieved',round_completed_at_utc=now,latest_result_report='rounds/round_022/ROUND_REPORT.md',execution_summary=decision,active_workers=[])
s['assistant_model_policy']['current_runtime_assistants']=0
s['handoff'].update(ready=True,next_session_launched=False,next_round='round_023',launch_receipt='automation/receipts/round_022_launch.json',next_session_id=None,accepted_at_utc=None,pause_reason=None,launcher_owner='root',note='Ready for root-only fresh Astra launch. Receipt path pending; next manager records acceptance. No new session claimed yet.')
s['next_round_budget']=dict(manager_minutes_max=45,compute_minutes_max=30,job_seconds_max=900,production_fits_max=8,threads_max=3,concurrency=1,available_ram_gib_min=2.5,expected_peak_gib=1.5,retries=0,full3fold=0,s2=0)
s['comparison_reference']=dict(name='LightGBM sqrt_macro seed42',correct=3476,n=5897,tp=[2389,889,108,90])
s['review']=dict(source='rounds/round_022/review/gate_approved_sources.json',final='rounds/round_022/review/partial_gate_audit.json',scope='partial source/model hash audit; complete saved-output score verification pending')
save(ROOT/'STATUS.json',s)
with (ROOT/'EXPERIMENT_LEDGER.csv').open('a',newline='',encoding='utf8') as f:
 csv.writer(f).writerow(['round_022','2026-11-05T01:30:00Z',now,decision['status'],'Strict fold-localT5+S1 centroidproxy; preparationcomplete;2of8fits budgetstop','','','partial_FIT_CV_no_aggregate_score',2,'rounds/round_022/ROUND_REPORT.md','Round023 fixed8fit procedural replay usingpreparedcaches; no full3fold/S2'])
print(json.dumps(dict(finalized=True,handoff_ready=True,next_session_launched=False,finished_utc=now,fits=2,gate_evaluated=False)))
