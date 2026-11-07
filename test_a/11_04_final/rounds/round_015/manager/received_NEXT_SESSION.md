# 다음 Astra high 관리자 — Round015: 동결 M4 합성 실행의 조기 검증

사용자가 승인한 후속 실행이다. Round014는 M4 tiny 합성 코드를 작성·검토했으나 30분 관리자 예산과 문서3분 확보 때문에 합성모델 실행을 시작하지 않았다. 실제 관문 결과는 ROUND_REPORT/review/FINAL_REVIEW 및 영수증을 먼저 확인한다. 목표 micro-F1 0.7미달, 기존 반복노출 개발 OUTER5897 baseline0.5930133966423605/macro0.5252719738966167, 미채택 탐색0.5933525521451586, 독립/공식null. 새 F1없음. round010 역사·현재 source gate false 영구보존.

AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round014 ROUND_PLAN/ROUND_REPORT, code/author_freeze_ack.json와 candidate_sources.json, review/SOURCE_REVIEW/FINAL_REVIEW/approved_sources.json 및 logs의 실제 영수증을 읽는다. 인계SHA/새세션 수신 일치와 다른 회차관리자 중복 여부 확인. 원자료 F:/문제 데이터_수정_1027, 이전repo D:/repos/fishing-track-classification, 과거회차/기존venv 읽기전용. 새출력/tmp/cache/logs는 round015 아래; 공유문서와 인계receipt만 루트 정해진 위치에 기록.

관리자 Astra/high, 작성자와 독립검토자 각각 Luna/xhigh/fork_turns=none을 명시. 보조는 추가 child를 생성하지 않으며 관리자가 의사결정 담당. 호스트총4/사용자보조최대4 준수. 요청과 실제turn_context 분리. Round014 reviewer의 역할명 요청 일탈과 실제 Luna상속은 manager/DELEGATION_DEVIATION.md 참고하며 반복하지 않는다.

## 이번 변경과 조기 실행 전략

새 설계나 합성 모델 수학을 다시 작성하지 않는다. 작성자는 round014 승인된 code/m4_synthetic.py, test_m4_mock.py, run_m4.ps1을 round015/code로 복사하고 회차경로·메시지·schema의 round_014/round014/Round014를 round_015/round015/Round015로 바꾸는 최소diff만 수행한다. round014 최종 검토에 실제 차단결함이 있으면 해당 결함만 고치고 이유를 기록한다. 정적승인만으로 동적성공을 주장하지 않는다. 작성자파일단독소유·ACK/쓰기중지, 검토자는 역치환diff/원본승인해시/최종직접해시 확인 후 새 승인map 작성. 코드 소유는code/*, 검토는review/*, 관리자는계획/실행/공유문서. 타인수정 되돌림0.

관리자30분, 문서3분 선확보. 후보복사·직접승인 첫5분 목표, 늦어도180초모델실행과문서시간을전부확보할수있는시각에만 시작. smoke1회≤10초(exit0/7순차,재시도0) → stdlib mock1회≤30초(성공뒤추가0; 결함수정후최대1추가이나 새map이소진된smoke를요구하면다음회차) → synthetic1회≤180초(170+10,재시도0). 같은 승인map을 유지하고 각 영수증 completed/int exit0/map·live·snapshot불변/stdoutstderr drain/owned tree clear 확인후 다음단계. 실행중소스수정0. 정확명령은 새독립승인뒤 실행전 ROUND_PLAN에 확정한다:

```powershell
& './rounds/round_015/code/run_m4.ps1' -Mode smoke
& './rounds/round_015/code/run_m4.ps1' -Mode mock
& './rounds/round_015/code/run_m4.ps1' -Mode synthetic
```

## 고정 합성 계약

round011/m4_contract/M4_CONTRACT.md·source_evidence.json·review/M4_REVIEW.md, round012/review/M4_NEXT_CHECKLIST.md, round014 승인코드가 근거다. 오래된 회차명은 일정표기다. seed20261112 context16×8/target4×8 FP32정규난수, context[0,1,2,3]×4/target[0,1,2,3]. target라벨은predict완료후외부headloss에만생성, fit/predict입력0. TabICL2.2.0/Torch2.6cpu/NumPy2.3.5, 기존basePython3.12 -B -S + 명시venv site-packages/DLL경로, 설치본수정0. CPU FP32 threads3, estimator4/batch1/norm none/featshuffle none/class shift/temp0.9/logits평균, AMP/FA3/KV/download false. checkpoint model_cache/tabicl-classifier-v2-20260212.ckpt, 110368038bytes/SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0 단일stream검증.

checkpoint load1/contextfit1/predict1/nativeforward4/head평가12/backward4. decoder[2]W[10,1024]/bias10, hook20행에서앞context16제외하고 targetH[4,4,1024]/logit[4,4,10]만캐시. 실제view순서/순열확인, canonical out[...,p]/loss p[y] 첫4출력. upstream eval/frozen/hash/grad/hooks불변, finally제거/inference모드밖clone. M4-a W만trainable/b고정, M4-b A[2,1024]std0.01(코드의고정seed20261113)/B[10,2]=0/W0,b고정; SGD0.001/momentum0/decay0 각2step. 첫Bgrad비영/첫A0/두번째A비영, inactive6/bias exact불변. CE는진단이며선택0. 원head/초기a,b/공식확률재구성/a학습직후vsreload/bunmergedvsmergevsreload raw전체view·10출력maxabs≤1e-5/prob≤1e-6/finite/range/행합≤1e-6/argmax일치/exact별도. 중복merge거부. 전체수정모델재추론/전체저장검증으로확대0.

매병렬/계산전 RAM시각·가용·예상peak·다른작업 기록. 예상tiny peak≤1.5GiB는checkpoint105MiB/로딩사본/Torch여유/H320KiB-target64KiB에기반한가정이며 아직실측없음. synthetic시작≥3GiB/실행중<1.5GiB소유child만정리/동시큰계산1. 부족하면소스·문서먼저후직전재확인, 반복RAM대기loop·사용자process종료0. 실제자료/NPZ/reference/OUTER/holdout/F1/설치/네트워크/유료/공식제출0.

산출은 source/ACK/map/review, logs/smoke_01/mock_01/synthetic_01의receipt/stdout/stderr/resources/progress/snapshots, artifacts/m4_synthetic_result.json와head-only상태, REPORT다. 실패는환경·shape/view·gradient·병합·자원·프로세스로분리하고소진된실행재시도0. 성공시 round014/review/NEXT_INTEGRATION_CHECKLIST.md의사전선택M4-a 전체estimator통합·저장재로드를 다음Round016으로검토한다(문서에Round015라쓴향후통합일정은이번모델실행지연으로한회차이동). 실제FIT학습자동확대0. 실패시구체원인과최소수정가설을다음fresh회차로이관.

학습질문은p[y]/out[...,p],B=0첫Agrad0,context/target분리,합성성공과F1차이. 기술산출과학습자이해·장치검증분리. 완료시 REPORT/STATUS(current_round=round_015,handoff.ready=true,active_workers=[])/LEDGER/NEXT 갱신후 & './automation/Start-NextSession.ps1' -FromRound 'round_015'. 수락receipt의newsession/promptdelivery확인즉시현재관리자종료. 닫기지원없으면완료탭만수동닫는제한기록. 반복승인불필요.

Round014 확정: smoke/mock/synthetic 모두0회. 첫map runner해시63자리 전사오류를 manager가 실행전차단, 잘못된map은 review/invalid_approved_sources_attempt_01.json 보존. 직접해시수정map SHA256 872d5eba99b7d3a3bdc1dcfd89b857a1b781a527cde676652573d7c5e5455d24이며 manager/final_map_verification.json의3파일일치를확인. 다음회차map도각값길이64와직접파일일치를실행전확인한다. 정상exit후예외적잔존child는현재runner가완료실패로남기며자동종료하지않음; 단일Python경로정적검토한계와재시도0을보존한다.

