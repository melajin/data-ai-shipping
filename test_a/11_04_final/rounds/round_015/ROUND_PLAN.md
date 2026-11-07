# Round015 — 동결 M4 합성 실행

시작 2026-11-04T21:25:12Z. 관리자 종료 21:55:12Z, 문서·인계 3분 확보를 위해 실행 마감 21:52:12Z. 합성은 늦어도 21:49:12Z에 시작한다. round014 인계 SHA C50148C876BAF83B9D1F124EC7A6DC21278584908F967F74475FC5AF7BB25FE2 일치. 현재 수신 세션과 launch receipt 일치, 직전 관리자 done, 같은 회차 중복 관리자 없음.

가설: round014 승인된 tiny 합성 구현이 고정 TabICL target 표현에서 M4-a/b gradient, 클래스 복원, 병합 및 head-only 재로드 정합성을 통과한다. 이번 변경은 회차 경로·문구·schema의 014→015만이다. 실제 차단 결함 외 재설계하지 않는다.

범위는 받은 NEXT_SESSION.md 및 round014 ROUND_PLAN의 고정 합성 계약을 그대로 적용한다. context16×8/target4×8, seed20261112, FP32 CPU threads3, estimator4, checkpoint1/contextfit1/predict1/nativeforward4/head평가12/backward4, a/b 각 SGD2step, 원raw≤1e-5/prob≤1e-6 및 argmax 일치, upstream/비활성행/bias 불변, hook finally 제거를 요구한다. CE는 선택 기준이 아니다. 실제자료·NPZ·OUTER·holdout·F1·설치·네트워크·외부업로드·유료 사용 0.

유한 실행: smoke 1회≤10초(exit0/7), mock 1회≤30초, synthetic 1회≤180초(170+10). 성공 뒤 추가 실행0, 합성 재시도0. mock 결함시 최대1 추가라는 상한은 유지하되 새map에 필요한 smoke가 소진되면 후속회차로 넘긴다. 각 단계는 동일 독립승인map/live/snapshot 불변·정수exit·stream drain·소유트리 종료를 확인한 뒤에만 진행한다.

작성자는 code/* 단독, 독립검토자는 review/* 단독, 관리자는 계획/실행/상태/결과 소유. 작성·검토 모두 명시 gpt-6-luna/xhigh/fork none, 추가child 금지. 부모+2보조=3≤host4, 보조2≤사용자4. ACK 뒤 코드쓰기 중지. 직접 해시로 64자리 map 검산.

자원: 초기 21:25:36UTC RAM 약5.638GiB, 다른 Python 없음. 병렬 소스·문서작업 예상200MiB, tiny peak≤1.5GiB는 checkpoint105MiB/로딩사본/Torch/target cache<1MiB에 근거한 가정이다. 매 계산 전 현재 RAM과 다른 계산 확인. synthetic 시작≥3GiB/실행중<1.5GiB 중단, 동시 큰 계산1. 부족하면 문서·소스 작업 후 재확인, polling 대기 및 사용자 프로세스 종료 금지. 과거회차·환경·원자료·이전repo 읽기전용.

독립승인 후 관리자가 아래를 별도 순차 호출한다. 실행 직전 map SHA는 manager 검산기록에 확정한다.

```powershell
& './rounds/round_015/code/run_m4.ps1' -Mode smoke
& './rounds/round_015/code/run_m4.ps1' -Mode mock
& './rounds/round_015/code/run_m4.ps1' -Mode synthetic
```

기술 목표는 실제 합성 동적 관문 통과, 학습 목표는 p[y]/out[...,p], B=0 첫 Agradient0, context/target 분리와 head 검증/F1 구별이다. 학습자의 이해·하드웨어 검증은 미평가. baseline 개발0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 독립·공식null 유지. round010 역사·현재 source gate false 보존.

성공시 사전선택 M4-a 전체estimator 통합·저장재로드를 round016에서 검토한다. 실패시 환경/shape-view/gradient/병합/자원/process 원인과 최소수정가설을 기록하고 소진실험 재시도 없이 fresh 회차로 인계한다. 완료시 REPORT/STATUS(current_round=round_015,handoff.ready=true)/LEDGER/NEXT 저장 후 Start-NextSession.ps1 -FromRound round_015 수락 확인 즉시 종료한다.
