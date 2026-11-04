# 다음 Astra high 관리자 — Round016: 종료 판정·JSON 호환성과 저장 M4 결과 감사

사용자가 승인한 후속이다. 먼저 AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round015 ROUND_PLAN/ROUND_REPORT, code/candidate_sources.json·author_freeze_ack.json, review/SOURCE_REVIEW·FINAL_REVIEW 및 저장 감사 결과, manager/saved_result_inspection.json·execution_closeout.json, logs/{smoke_01,mock_01,synthetic_01}/receipt.json을 읽는다. JSON 전체를 Windows PowerShell ConvertFrom-Json으로 읽으면 빈 문자열 key 때문에 실패할 수 있으므로 모델 결과는 base Python -B -S stdlib json으로 읽는다. 인계 SHA와 새 session 수신 일치, 중복관리자·이미실행 claim을 확인한다.

Round015 실제: smoke1회 성공(exit0/7), mock1회/4시험 성공, 합성Python1회 exit0/status completed, checkpointload1/contextfit1/predict1/fullforward4/head평가12/backward4. 합성 wrapper completed=false: Python 결과 JSON의 upstream_model.module_training_before_after에 루트 모듈 키 ""가 있고 PowerShell 변환 계층에서 invalid name 예외. 기존 source/map/snapshot 불변, stream drain/owned tree clear. 추가 독립발견: process.wait_finished=false/timed_out=true인데 elapsed16.7639027초<170초, memory_stop=false/kill_attempted=false/exit_confirmed=true/exit0이다. 실제170초 제한 도달이라고 주장하지 않는다. runner의 while 뒤 WaitForExit(1) 거짓값만으로 timedOut을 설정하는 판정은 deadline을 별도로 확인하지 않는다. 정확한 동적발생경로는 미확정이며 manager/CONTROL_LAYER_FINDINGS.md를 읽는다. JSON만 해결해 전체gate를 통과시키지 않는다. 수치 저장값은 6비교 통과, raw최대차0/public확률차5.960464477539063e-08, gradient/inactive/bias/upstream/hooks 통과. 전체wrappergate=false를 사실대로 영구보존한다. round010 역사·현재gatefalse도 그대로다. 새 F1없음: 반복노출 개발OUTER5897 baseline0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586, 독립/공식null, 목표0.7미달.

## 다음 회차의 단일 가설과 범위

가설: 모델·텐서 계산을 바꾸지 않고 실행 제어의 종료 판정과 JSON 판독을 고치면 저장 M4 증거를 일관되게 소비할 수 있다. **모델 재실행0, torch/numpy/tabicl import0, checkpoint read/hash/load0, .pt 역직렬화0, 학습0.** 원본 결과·receipt·source·map을 수정하지 않는다. 이번 wrapper 실패를 소급해서 completed=true로 고치지 않는다. 모델을 다시 돌려 파서 오류를 시험하지 않는다.

작성자와 검토자를 각각 gpt-6-luna/xhigh/fork_turns=none으로 명시하고 추가child금지. 관리자gpt-6-astra/high. 요청과 실제host turn_context를 분리한다. host총4, 보조사용자최대4 준수. 작성자 round_016/code/*, 검토자 round_016/review/*, 관리자 계획/실행/상태/인계 소유. 다른 수정 되돌림금지. ACK/쓰기중지→독립직접해시map→관리자64자리hash대조를 유지한다.

추천 구현은 작은 stdlib Python 판독기/감사기가 full JSON을 그대로 파싱·검사하고 PowerShell 호환의 고정필드 summary를 별도 round016 artifacts에 쓰는 것이다. 기존 full JSON은 그대로 유지한다. JSON parser는 중복key와 NaN/Infinity 및 누락/잘못된type을 거부하며 파일크기·경로를 사전제한한다. 빈key는 루트모듈 의미를 보존한다. case변형 충돌도 summary에는 도입하지 않는다. 다른 방법을 쓰면 설치없는 로컬근거와 독립 검토를 먼저 남긴다. 과거 runner의 광범위 Read-Receipt를 임의로 다시 설계하기보다 bounded saved-audit에 집중한다. round015 code는 수정0.

실행 전 ROUND_PLAN에 고정할 상한: 관리자25분(문서3분 확보), process probe batch1회≤15초(순차4 child: 즉시exit0, 즉시exit7, 감시경로정상exit0, 실제deadline초과), stdlib mock1회≤30초(재시도0), saved-audit1회≤30초(재시도0). 동시계산1, 새source/map의 성공smoke→mock→audit 순서. probe의 정상감시child는 stdlib sleep 약1.2초 후exit0/대기상한5초, timeoutchild는 sleep5초/대기상한0.5초/정리1초로 사전고정하고 자기소유PID만 종료한다. 실제대기상한도달·HasExited·WaitForExit 반환·memory_stop·exit관찰·streamdrain을 독립기록한다. 종료이벤트를 이미관찰했다면 보존하고 deadline전에 wait1ms가false인것만으로 timeout을 만들지 않는다. 진짜deadline은 반드시중단·기록해야 한다. timeoutchild의 killed exit값은 OS의 실제정수값을 기록하며 정상exit0을요구하지 않는다. probe마다RAM/다른작업 확인, batch1회만. mock은 종료분류의 정상/시간초과/메모리중단 반례와 빈 root key를 가진 fixture 수용, duplicate-key/nonfinite/missing-field/wrong-type/허위completed 검출, 역사false 보존을 확인한다. 새코드의 실행한도·반례를 먼저 고정하고 결과를 본 뒤 오차를 완화하지 않는다. 실행 경로 예시는 아래이고 실제 소스·argv는 독립승인 뒤 계획에 확정한다:

```powershell
& './rounds/round_016/code/run_saved_m4_audit.ps1' -Mode smoke
& './rounds/round_016/code/run_saved_m4_audit.ps1' -Mode mock
& './rounds/round_016/code/run_saved_m4_audit.ps1' -Mode audit
```

기존 base Python C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B -S만 사용하고 stdlib 이외 import0. ProcessStartInfo의 정상exit/streamdrain/ownedtree 검증을 재사용하되 모델실행모드는 포함하지 않는다. 소스·map·실행snapshot 전후hash, PID/시각/정수exit/stdoutstderr/log/자원/실제command를 저장한다. 정상 종료 뒤 unexpected descendant가 남으면 실패로 남긴다.

## 고정 입력과 인수조건

- round_015/artifacts/m4_synthetic_result.json 64851bytes SHA365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105
- round_015/artifacts/m4_a_head.pt 42422bytes SHAc33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0
- round_015/artifacts/m4_b_merged_head.pt 42464bytes SHA8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36
- round_015/review/approved_sources.json SHA2cede678cba53e4a92832c663bf4968b75ee63b5c1287ad25804aaf3dce59dd4
- smoke receipt SHA4f9608e11d51bd70e5508ed82f746eb3c03e3319fc5e6f8da1782eff36dd9ad2; mock receipt SHA61595d02a9297711dc47ab16569247aea0558906b7c23c58964d0e722976b2bf; synthetic receipt SHAc6f9bc8861ffb14629cfa8ccdc84c8a0da55d3f224dc7a0ec430904b39c8affa.

경로의 공통prefix는 rounds/이다. manifest를 만들 때는 실제 경로와 직접해시로 확인한다. input lineage는 round015 manager/saved_result_inspection.json에 있다. head .pt는 크기/streaming hash만 확인하고 load하지 않는다. bytecode/tmp/cache/log/output은 round016 아래만. 원자료 F:/문제 데이터_수정_1027, 이전repo D:/repos/fishing-track-classification, 과거회차와 기존venv는 RO. 실제자료/NPZ/reference/OUTER/holdout/외부수집/F1/네트워크/설치/유료/공식제출0.

감사는 각 receipt의 map/live/snapshot과 실제 frozen source를 직접해시로 대조하고 smoke/mock historical completed=true, synthetic historical completed=false와 child exit0/statuscompleted를 동시에 요구한다. result6비교의 raw≤1e-5/prob≤1e-6, finite/[0,1]/행합≤1e-6/argmax, gradient/inactive/bias/reload/upstream/hooks, 정확call counts와 config/seed/shape/permutation을 검산한다. 저장JSON 기반 검산이므로 tensor 재계산과 구별한다. 결과 필드는 numeric_saved_checks_pass, saved_provenance_audit_pass, historical_round015_wrapper_gate=false, current_round015_source_matches, historical_round010_gate=false로 분리한다. 실제head역직렬화·전체모델저장검증·F1은 미확인으로 둔다.

자원: round015 sampled peak558.75MiB/min가용5.2198GiB는 과거 합성실행값이며 이번시작값이 아니다. 새 stdlib 감사 예상peak≤200MiB(파일수백KiB+직렬작업+PS/Python) 가정, 시작가용≥0.5GiB, 현재시각·가용·다른작업 기록. 부족하면 코드/문서 먼저 후 직전재확인, RAMpollingloop·사용자process종료0. 큰계산0.

성공하면 next round017에서 round014/review/NEXT_INTEGRATION_CHECKLIST.md의 사전선택M4-a 전체estimator 통합·save_model_weights=True/save_training_data=True/save_kv_cache=False 저장재로드를 검토한다. 소스문서의 옛회차명은 일정보기이며 사용할 head는 round015의 해시고정 a artifact다. 이번round016에 모델통합을 추가하지 않는다. 실패하면 parser/schema/provenance/수치/실행계층을 특정하고 실패출력을보존, 새가설의 유한후속으로 넘긴다. 무정보모델재실행금지.

학습목표: 유효JSON과 소비자호환성, 루트모듈 빈key의 의미, child성공/전체실행기실패/저장검산 분리, 합성수치와F1구별. 보고서에 이전→현재→다음변경, 조건/예상/계산/해석/미확인 남긴다. 완료시 REPORT/STATUS(current_round=round_016,handoff.ready=true,active_workers=[])/LEDGER/NEXT 갱신 후 Start-NextSession.ps1 -FromRound round_016 수락newsession+promptdelivery 확인즉시 현재관리자종료. structured chat닫기지원없으면 완료탭만 수동닫는제한기록. 반복승인불필요.
