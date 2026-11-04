# 다음 Astra high 관리자 — Round 011

승인된 후속이다. AGENTS/CYCLE_PROTOCOL/STATUS, round010 ROUND_REPORT·PLAN_AMENDMENT_01·review/SOURCE_REVIEW·MOCK_REVIEW·INCIDENT_REVIEW·FINAL_REVIEW·approved_sources, artifacts/result, logs/mock_01·pilot_01/receipt, manager/source_freeze_incident·post_execution_hash_check를 읽고 인계SHA/수신session을 대조한다. 중복실행금지. 관리자Astra/high, 별도작성자·검토자Luna/xhigh/fork none; host4슬롯 우선. 모든새출력round011아래, 과거회차/원자료/이전저장소/venv읽기전용.

round010 실제FIT3144×312/고정INNER2 COL16+ROW8 재현1회215.485초, maxabs1.8446231598301388e-6≤1e-4, argmax[0,1]일치/exactfalse, fit1/predict1/전체문맥유지/모두복원/잔존0. 시작RAM4.562309/min3.300785GiB, sampledpeak1265553408bytes. 새F1없음. 기준개발OUTER5897 micro0.5930133966423605, 탐색미채택0.5933525521451586, 독립/공식null,0.7미달.

하지만 작성자가 실행중19:57:09.149UTC에 wrapper를수정했다. 승인/mock/pilot실행사본 SHA c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210, live c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867. root_identity_capture_failed 조기반환 진단2줄이며 이번분기미진입. 모델source/adapter/입력/실행사본불변. postcheck가검출하여 wrapper failed_or_stopped/commandexit4, childexit0/PILOT_COMPLETE. 수치재현true,전체관문false. 과거manifest/receipt/live파일을고치거나 clean으로소급재명명하지않는다.

## 이번회차 실제작업: 출처복구와 M4 계약, 모델 재실행0

manager20분. raw/NPZ/reference추가읽기0, checkpointload0, fit/predict/forward/계수학습/F1/OUTER/holdout0, 업로드/설치0. 저장JSON의이미계산된2×4확률·reference확률과소스/metadata만읽는다.

1. 작성자는 round011/code/verify_frozen_run.py와순수mock을작성한다. stdlib만사용해 round010 승인map·실행사본·receipt·source diff·진입기록·저장확률을검산한다. 실행사본동일성과live원본불변을별도필드로보존하고 원래 source-freeze실패를통과로바꾸는옵션을두지않는다. 검토자는 review/*를소유하여독립검토·승인한다. 관리자는입력/실행/공유문서. 타인수정보존,파일별담당1명.
2. 순수mock은 clean fixture와live-wrapper-drift fixture에서사본보존과원본동결실패가분리되고drift가전체clean으로오인되지않는지검증한다. 최초1회≤30초+결함수정후최대1회. torch/numpy/실자료없음,fixture는round011아래만. 승인hash동결후관리자가실행. 실제저장기록검산1회≤30초(streaminghash;checkpoint전체hash재계산불필요). 같은모델재실행금지.
3. 동결규칙을명문화한다: 작성자는candidate전달후쓰기중지,검토자는승인map,관리자는승인후변경을다음버전/회차로이관. 실행중변경시사본/변경본/영수증과실패표시보존. 필요한수정은실행전새승인·새mock을거쳐야한다. 기존회차덮어쓰기금지.
4. 소스·기존문서만으로M4준비계약작성: round002/IDEA_REVIEW_AND_ROUND003.md와references/algorithm_variant_ideas.md, round003/m4_readiness/READINESS.md, round004/runtime_author/replay_contract.json, pinnedTabICL2.2.0 learning.py/classifier.py/preprocessing소스. 최종Linear정확shape/사용class출력/클래스shuffle역변환/temperature·average_logits/gradient차단/FIT-only문맥과학습대상분리를근거행으로정리. M4-a weight만/bias고정과M4-b rank2/bias고정의 다음tiny합성 무변경·gradient·merge/reload검증에필요한입력/호출수/판정/예상RAM을설계한다. 이번회차모델실험0, 미확정은추측구현하지않는다.

RAM: 실행/병렬작업전시각·가용량·예상peak·다른작업확인. stdlib검산예상≤100MiB, streamingbuffer1MiB, 큰계산동시0. 부족하면소스/문서후재확인,단순RAMpolling/조회만하는새세션금지,사용자프로세스종료금지. 학습비용을이번추론215초에서단순추정하지않는다.

예정명령(아직파일없음;구현/독립검토후확정):
```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_011/code/test_verify_frozen_run.py'
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_011/code/verify_frozen_run.py' --source-round round_010 --output './rounds/round_011/artifacts/provenance_audit.json'
```
완료는실행사본/live/수치/실패원인의분리검산,동결규칙,근거있는M4다음계약이다. 과거전체관문실패영구보존. 기술목표출처검증과후속계약,학습목표수치정확성/실행출처/성능평가구분. 학습자이해/장치검증주장금지.

ROUND_REPORT(이전→현재→다음),EXPERIMENT_LEDGER,STATUS(current_round=round_011,handoff.ready=true,active_workers=[]),NEXT_SESSION갱신후실행가능후속이면아래수락영수증확인후중지. 다음tiny합성M4는소스계약확정후에만구체화한다.
```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_011'
```
지원닫기명령없으면완료세션탭만수동닫는방법을남긴다. 외부제약은정확한재개조건을기록한다. 반복승인을묻지않는다.
