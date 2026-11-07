# Round014 — M4 tiny 합성 head 학습·병합 관문

시작 2026-11-04T20:55:19Z. 관리자 마감21:25:19Z, 실행마감21:22:19Z(문서·인계3분 확보). 인계 SHA256 D6036C250D4629D85E2DED7E07270867058A5E3A81B3592C8EAF11C668C6BE6E가 현재 NEXT와 보존본에 일치하고, round013 launch의 수신 session은 현재 codex_a64a16a7_215f_4304_a93c_6c6b60b86467이다. 직전 관리자 done, 같은 회차 다른 관리자 없음. Test B의 별도 작업은 보존한다.

가설: 동결한 TabICL의 target-only 표현을 사용하면 외부 readout의 전가중치(M4-a)·rank2(M4-b) 학습, 클래스 복원, 병합, head-only 재로드를 엄격 오차 내 검증할 수 있다. 변경은 외부 head 사본뿐이다. round011 M4_CONTRACT/source_evidence/M4_REVIEW와 round012 M4_NEXT_CHECKLIST를 정본으로 적용한다. 계약의 옛 실행 회차명은 일정 지연이며 이번 round014에서 실행한다.

## 사전 고정 범위와 판정

- smoke1회≤10초(exit0/7 두 child 순차), 재시도0. stdlib mock 최초1회≤30초, 결함 수정 후 최대1회 추가이나 새 map에 필요한 smoke가 소진됐으면 다음 회차로 이관. 합성모델1회≤180초(계산170+정리10), 재시도0. 실행 중 소스 수정0.
- checkpoint load1/context fit1/predict_proba1/native full forward≤4/head evaluation≤12/backward4. a/b 각 SGD2step, lr0.001/momentum0/decay0. 후보선택0.
- seed20261112, FP32 정규난수 context16×8/target4×8, context [0,1,2,3]×4, target [0,1,2,3]. target 라벨은 외부head loss에만 사용. 실제자료/NPZ/reference/OUTER/holdout/F1/설치/네트워크/외부전송/유료0.
- CPU FP32 threads3, TabICL2.2.0/Torch2.6cpu, estimator4/batch1/norm none/feature shuffle none/class shift/temperature0.9/average_logits true, AMP·FA3·KV·auto download false. 기존 환경 읽기전용. checkpoint SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0를 단일 스트리밍 검증.
- decoder[2] W[10,1024]/b[10] assertion. hook H[B,20,1024], logits[B,20,10]에서 앞16 context 제외 후 target H[4,4,1024]/logits[4,4,10]만 캐시. member/permutation 순서 확인. finally hook제거, upstream eval/frozen/hash/grad 불변. inference mode 밖 detached clone.
- canonical out[...,p], loss target p[y], 첫4출력만loss. M4-a W만 trainable/b고정. M4-b A[2,1024] std0.01/B[10,2]=0, W0/b고정. 첫 Bgrad 비영·첫 Agrad0·두번째 Agrad비영, inactive6행과 bias exact불변. CE는 진단값이며 성능선택 아님.
- 원head/초기a/b, 공식확률 재구성, a head-only save/reload와 b unmerged/한번merge/reload 비교: raw logit maxabs≤1e-5, probability≤1e-6, finite/range/행합오차≤1e-6/argmax전부일치. exact별도. 중복merge거부. 사후 오차완화0. 전체수정 모델 재predict/재로드는 별도 후속 관문.

## 소유권·자원·실행 통제

작성자 /root/round014_author는 code/* 단독, 검토자 /root/round014_reviewer는 review/* 단독, 관리자는 계획·실행·공유문서 소유. 각각 gpt-6-luna/xhigh/fork_turns=none 명시 요청. root+보조2=3≤host4, 보조2≤사용자4. 다른 수정 되돌림 금지. candidate ACK/쓰기중지 후 검토자가 직접 해시 승인map 작성. manager는 exact-map smoke→mock→synthetic 순서를 직접 확인. map/live/snapshot 전후SHA, 정수exit, stdout/stderr, 소유종료/잔존없음 보존.

가용RAM 3.867046GiB(20:56:25UTC), 병렬 문서·소스 예상200MiB와 tiny 실행 예상peak≤1.5GiB는 가정이며 실측아님. checkpoint약105MiB/로딩사본/Torch여유, 전체H320KiB·targetH64KiB 근거. 각 계산 전 RAM/다른프로세스 확인. synthetic 시작≥3GiB, 실행중<1.5GiB시 소유child만정리. 동시큰계산1. 부족하면 독립문서/소스작업 뒤 실행직전 재확인하며 반복RAM대기loop·사용자프로세스종료0.

모든 새 코드/tmp/cache/log/artifact는 round014 아래. 공유 STATUS/LEDGER/NEXT와 정해진 automation receipt만 루트위치 갱신. 원자료 F:/문제 데이터_수정_1027, D:/repos/fishing-track-classification, 과거회차·기존venv 읽기전용. Python 단일process/기존 site-packages 진입경로와 정확 명령은 독립소스승인 뒤 아래에 확정한다. 실행 전에 명령을 기록한다.

## 실행 명령 — 독립 승인 후에만 순서대로 수행

runner의 최종 승인map과 live source를 대조하고 매 단계 영수증을 확인한다. 각 명령은 작업루트 cwd의 별도 PowerShell 호출로 실행한다. runner가 source snapshot을 만들며 자식은 base Python 3.12의 -B -S와 명시 기존 site-packages를 사용한다. 새 환경 설치는 없다.

```powershell
& './rounds/round_014/code/run_m4.ps1' -Mode smoke
& './rounds/round_014/code/run_m4.ps1' -Mode mock
& './rounds/round_014/code/run_m4.ps1' -Mode synthetic
```

이 명령 기록은 소스 승인이 아니다. 최종 map SHA는 review/approved_sources.json 및 각 실행 receipt에 고정한다. 선행단계가 실패하면 다음 명령을 실행하지 않는다.

## 해석·학습·종료

기술 목표는 마지막층 복사·순서·gradient·병합·head-only reload 정합성. 학습 목표는 p[y]/out[...,p], B=0의 첫 Agrad0, support/target 분리, head 학습과 F1 개선의 차이를 설명하는 것이다. 학습자 이해·하드웨어 검증은 미평가.

개발 OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택 탐색0.5933525521451586 유지. 독립/공식null, 목표0.7미달. round010 current/historical gate false 보존. 실패는 환경/소스/shape-view/gradient/merge/자원/process 계층으로 나눠 기록한다. 1회 소진후 같은 실험 재시도0. 성공하면 전체head integration 또는 실제FIT 평가계약 중 한 후속을 근거로 정하며 자동실자료학습으로 확대하지 않는다.

완료시 ROUND_REPORT/STATUS(current_round=round_014,handoff.ready=true,active_workers=[])/LEDGER/NEXT 저장. 다음 실행 가능하면 Start-NextSession.ps1 -FromRound round_014 수행, 수락receipt/newsession/promptdelivery 확인 즉시 현재관리자 종료. structured chat 닫기 지원없으면 완료탭 수동닫기 제한 기록.
