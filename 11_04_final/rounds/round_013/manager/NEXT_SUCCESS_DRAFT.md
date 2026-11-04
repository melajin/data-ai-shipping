# 다음 Astra high 관리자 — Round014: M4 tiny 합성 head 학습·병합 관문

이 문서는 round013 종료관문과 독립 최종검토가 성공한 경우에만 NEXT_SESSION으로 승격할 초안이다. 아직 실행지시가 아니다.

먼저 AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round013 ROUND_REPORT/ROUND_PLAN/FREEZE_PROTOCOL, review/SOURCE_REVIEW/FINAL_REVIEW 및 round012/review/M4_NEXT_CHECKLIST, artifacts/provenance_audit.json 및 logs smoke/mock/audit 영수증을 읽는다. 인계SHA와 수신session을 확인하며 같은회차 관리자가 있으면 중복실행하지 않는다. 관리자 Astra/high, 별도 코드작성자와 독립검토자 Luna/xhigh/forknone만 사용한다. 사용자 보조상한4/host총4를 우선하고 요청과 host turn_context 증거를 분리한다.

기존 개발 OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택 탐색0.5933525521451586, 독립/공식null. 목표0.7미달. round013은 프로세스·저장기록 검산이며 새F1이 아니다. round010 수치재현 통과와 역사 source-freeze 전체false는 영구보존한다. 현재 소스 관문과 검산 프로그램 정상종료를 역사성공으로 바꾸지 않는다.

다음 구현의 정본은 rounds/round_011/m4_contract/M4_CONTRACT.md, source_evidence.json과 round011/review/M4_REVIEW.md이며 round012/review/M4_NEXT_CHECKLIST.md의 최신 구현 주의점을 함께 적용한다. 옛 계약의 'round012에서 실행'은 지연된 일정 표기이며 이번 round014에서만 실행한다. 과거회차/원자료 F:/문제 데이터_수정_1027/이전repo D:/repos/fishing-track-classification/기존venv는 읽기전용. 모든 신규코드·tmp·cache·logs·artifacts는 round014 아래, 공유문서와 인계receipt만 정해진 루트위치에 갱신한다.

관리자30분, 마감 문서3분 선확보. 새runner process smoke1회≤10초(exit0/7 두child순차,재시도0), stdlib mock최초1회≤30초+결함수정 후최대1회. 합성모델 본실행1회≤180초(계산170+정리10), 재시도0. checkpoint load1/context fit1/predict_proba1/native full forward≤4, 외부 head평가≤12, backward4(a/b각2step). 실제자료·NPZ·reference·OUTER·holdout·F1·공식제출·네트워크·설치·유료0. 모델 또는 장비 실선 검증이 아니다.

1. 작성자는 round014/code/*와 runner 소유, 검토자는 review/*, 관리자는 실행/공유문서. round013의 검증된 ProcessStartInfo/Process 경로를 복사하여 새 source freeze/claim/output 경로와 모델자원관문을 구현한다. Python환경은 기존 environments/round_004_tabicl_cpu 사용; base Python -B -S는 stdlib전용이므로 Torch실행에 그대로 쓰면 안 된다. venv redirector 자식 경로 및 소유트리 종료증거를 source-review에서 확정하거나 기반Python에 승인된 site-packages를 명시하는 단일process 방식을 정한다. 설치본 수정금지.
2. 합성seed20261112, context16×8/target4×8 FP32 정규난수, context라벨[0,1,2,3]×4/target[0,1,2,3]. target라벨은fit/predict 입력0, 외부head loss만. TabICL2.2.0/Torch2.6cpu, CPU FP32 threads3, estimators4/batch1, norm none/feat shuffle none/class shift, temperature0.9/logits평균, AMP/FA3/KV false/download false. checkpoint 경로는 기존 replay_contract/smoke/config metadata에서 읽기전용 확인하고 SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0를 단일 스트리밍 검증한다. 실제 데이터파일은 열지 않는다.
3. decoder[2] W[10,1024],bias10 shape assert. read-only decoder[2] hooks는 source상 context+target 20행 H[B,20,1024]/logits[B,20,10]을 관찰한다(learning.py265–280). public inference는 이후 target4행만 자른다(326–339). 실제 shape와 view순서/permutation을 확인하고 hook결과의 앞16 context행을 제외해 H[4,4,1024]/logits[4,4,10]만 캐시한다. source-review와 실제 shape가 어긋나면 실패. hook finally제거, upstream frozen/eval/hash/grad 불변, inference텐서는 모드밖 detached clone. canonical복원 out[...,p]와 target p[y], 첫4출력만loss.
4. 동일H에 M4-a W만trainable/b고정, M4-b rank2 A[2,1024] std0.01/B[10,2]=0/W0,b고정. SGD lr0.001 momentum0 decay0 각2step. 첫B gradient 비영/첫A0정상/두번째A비영, a/B의 inactive6행 및 bias exact불변. 평균 unweighted CE는 진단이며 성능선택0.
5. 원head재계산과초기a/b, 공식확률재구성 비교: logit maxabs≤1e-5/prob≤1e-6,finite/range/행합≤1e-6/argmax일치, exact별도. a head-only save/reload와 b 한 번 merge/save/reload를 같은H로 비교, 중복merge거부. 전체수정모델 재predict/save/reload 검증으로 확대하지 않는다. 허용오차 사후완화0.
6. 작성자 candidate ACK/쓰기중지 → 독립소스승인map 직접생성 → process smoke → 순수mock → 같은map 본실행. live/실행사본/map 전후SHA/종료코드/owned tree clear를모두확인. 실행중코드수정금지. mock는 클래스복원·target격리·호출상한·merge guard 등 핵심계약을 모델없이 검증한다.

매 병렬/계산전 RAM시각·가용·예상peak·다른작업 기록. tiny모델 예상peak≤1.5GiB는 가정(checkpoint약105MiB/로딩사본/Torch여유, H약320KiB, targetH64KiB)이며 실측peak아니다. 시작가용≥3GiB, 실행중<1.5GiB시 소유child만정리. 동시큰계산1. RAM부족이면 소스/문서 먼저후 실행직전재확인; 반복RAM대기loop/사용자process종료금지. 이전큰문맥peak를 tiny상한으로오인하지 않는다.

산출: round014/code 실행파일+명령, review 승인map/독립검토, logs/mock_01와synthetic_01 receipt/stdout/stderr/progress/resources/source snapshots, artifacts/m4_synthetic_result.json 및 head-only상태, ROUND_REPORT. exact명령은 구현·승인후확정하여 실행전 ROUND_PLAN에 저장한다. 현재계약만으로 기존runner를 즉시실행하지 않는다.

실패는환경/소스/shape-view/gradient/merge/자원/프로세스계층별로 분리한다. 합성1회소진후같은실험을재시도하지않고 바뀐가설을 다음fresh회차로넘긴다. 성공시후속은 전체head integration/save-reload 또는 실제FIT평가계약 중 하나를 소스·자원근거로 선택하여 구체화하며 자동실자료학습으로확대하지 않는다.

학습질문: p[y]와out[...,p]는 왜짝인가? B=0에서A gradient0은왜정상인가? target캐시를만들기전 문맥/목표를나눠야하는이유는? head학습성공이F1상승을증명하지못하는이유는? 기술산출/학습자이해/장치검증을분리한다.

완료시 REPORT/STATUS(current_round=round_014,handoff.ready=true,active_workers=[])/LEDGER/NEXT 갱신. 목표미달·다음작업실행가능이면 & 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_014' 실행, 수락receipt/newsession/promptdelivery 확인즉시현재관리자종료. structured-chat닫기지원없으면 완료탭만수동닫는제한 기록. 반복승인불필요.


