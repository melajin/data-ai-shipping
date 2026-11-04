# 다음 Astra high 관리자 — Round 012

사용자가 승인한 후속이다. 먼저 AGENTS.md/CYCLE_PROTOCOL.md/STATUS.json, round011 ROUND_REPORT.md/ROUND_PLAN.md/FREEZE_PROTOCOL.md, review/SOURCE_REVIEW.md/FINAL_REVIEW.md/M4_REVIEW.md, artifacts/provenance_audit.json, m4_contract/M4_CONTRACT.md/source_evidence.json, incoming launch receipt SHA·수신 session을 확인한다. 다른 동일 회차 관리자가 있으면 중복 실행하지 않는다. 관리자 gpt-6-astra/high 요청·호스트 증거 분리. 작성자/검토자 별도 gpt-6-luna/xhigh/fork none, 보조최대4 및 host4슬롯 우선. 모든 새 출력 round012, 공유 STATUS/LEDGER/NEXT만 관리자 갱신. 과거회차/venv/원자료/이전저장소 읽기전용.

목표0.7 미달. 반복노출 개발 OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 탐색미채택0.5933525521451586, 독립/공식null. round010 고정 실제두질의 maxabs1.8446231598301388e-6, argmax일치, exactfalse이나 wrapper live변경으로 전체관문false다. round011 검산은 그 역사적 실패를 소급수정하지 않는다. holdout 노출이력 확인 전 열람금지. 이번 후속 실제자료/F1/외부업로드/공식제출/설치/유료0.

## 실제 할 작업: M4-a/b tiny 합성 readout 관문

정확한 계약은 rounds/round_011/m4_contract/M4_CONTRACT.md에 있다. 관리자30분, stdlib mock1회≤30초+결함수정후최대1회, synthetic1회 총180초(170+10), retry0. 가용RAM 시작≥3GiB/실행중<1.5GiB 중지, 예상peak≤1.5GiB는 가정이다. 현재값은 실행직전 확인, 다른 계산과 병행0,threads3. 부족하면 소스/문서 선행후 다시 확인; polling만 하는 세션/사용자process종료 금지.

1. 작성자는 round012/code/readout_variant.py, tiny_m4_probe.py 및 순수mock을 작성한다. 관리자는 실행wrapper/입력계약/logs, 검토자는 review/*. 작성자 candidate ACK 후 쓰기중지→검토자 승인map→관리자 exactmap 사본mock→같은 map synthetic. 실행 중 변경은 전체실패로 보존, 사후수정금지. 타인파일수정·복원금지. 이번 모델 실행 전에 전체수치·경계·hook복원·원본상태 불변을 static 검토한다.
2. 합성 seed20261112, context16×8/target4×8 FP32 정규난수. context라벨0..3각4개,target0..3, ID분리. pinned TabICL2.2.0/Torch2.6cpu/checkpoint110368038bytes SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0. CPU/FP32,AMP/FA3/KV false,downloadfalse,estimators4,batch1,norm['none'],feat none,class shift,temp0.9,average_logits true. checkpointload1/fit1/predict1/full forward최대4. 기존실제NPZ/reference/원자료읽기0.
3. icl_predictor.decoder[2] W[10,1024],b[10] assertion. 원모델eval/frozen, read-only pre/forward-hook으로 H와logit capture(입출력변경0), finally복원. target4행 H만 복사, member순서+permutation기록. base재계산과 predict canonical probability 비교. p[y_target]과 out[...,p] 대응, 처음4logit만활성. hidden축재정렬금지. target라벨은context에 절대전달하지않음.
4. 외부head사본만학습: a W만,bias고정; b rank2 A std.01/B0/scale1,W0+b고정. 동일H/target/view,SGD lr.001/momentum0/weight_decay0,각2step. head평가최대12/역전파4,추가fullforward0. a유한비영gradient,b첫B비영/A0·둘째A비영확인,unused6행/bias/원모델param-buffer불변. head-only merge한번/save/reload검증,중복merge거부. rawlogit maxabs≤1e-5,prob≤1e-6,행합≤1e-6,argmax일치,exact별도. 전체모델통합/성능검증으로부르지않음.
5. 모델실행은 승인+mock통과+현재RAM+소스동결을 확인한 다음 한 번만. shape/view수/gradient/수치/출처/hook/자원 실패를 분리하고 결과/프로세스/자원곡선 보존. 불명확하면 추측구현·자동확대하지않고 실패원인 및 다음 유한 가설을 기록한다.

예정 실행명령은 아직 미구현이므로 실제 작성·독립검토 후 확정한다:
```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_012/code/test_readout_variant.py'
# 실제 tiny_m4_probe.py는 검토된180초/RAM/PID 소유권 wrapper를 통해서만 한 번 실행
```

산출: code·승인map·source snapshot·stdout/stderr·receipt·입력/변경범위/gradient/수치·head state·독립검토·ROUND_REPORT(이전→현재→다음). 기술목표head정합성,학습목표class shuffle와gradient/캐시누출구분;이해/하드웨어달성주장0. 다음단계는 결과에따라 전체수정모델integration smoke 또는 실패원인한개수정이다. 실제FIT학습/INNER선택/OUTER평가는 아직실행하지않는다.

완료시 STATUS.current_round=round_012,active_workers=[],handoff.ready=true, EXPERIMENT_LEDGER/NEXT_SESSION 갱신. 실행가능후속이면 아래 명령의 수락영수증과 새session ID/prompt delivery를 확인한 즉시 이 관리자는 종료한다. 불확실한 launch는 같은명령무작정반복금지.
```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_012'
```
지원 structured-chat닫기명령이 없으면 완료한 본 세션탭만 수동닫는 제한을 기록하고 종료한다. 외부제약은 정확한 재개조건/명령을 남긴다. 반복승인은 불필요하다.
