# Round011 — M4 계약 완료, 실행 영수증 결함으로 출처 검산 보류

순수 fixture 테스트2개는 OK였으나 wrapper가 종료코드를 null로 기록하여 mock 전체관문은 실패했다. 본 저장기록 audit은 실행하지 않았다. 관리자20분 상한 내에서 코드 변경·재승인·mock을 충분히 끝낼 수 없어 추가 실행하지 않고 구체적 결함을 다음 회차로 넘긴다. 모델 실행·새F1은0이며 목표0.7은 미달이다.

## 이전 → 현재 → 다음

round010은 두질의 수치재현 통과/실행중wrapper변경에 따른 전체관문실패였다. 이번에는 stdlib 출처검산 코드와 clean-live/현재live-drift fixture, 동결절차, 소스근거 M4 계약을 작성하고 독립 검토했다. source 승인의 테스트SHA 오타를 prelaunch가 탐지하여 Python 실행 전에 검토자가 잘못된map을 별도보존하고 정정했다. 원코드는 바뀌지 않았다.

실제 mock_01은 0.4837655초에 종료했다. unittest stderr는 2tests/0.098초/OK이나 receipt exit_code=null,owned_process_exited=true,completed=false다. 실행사본/현재3소스 전후hash는 유지되었다. 종료확인은 있지만 숫자종료코드를 확인하지 못했으므로 exit0을 만들지 않는다. console의 요약필드null은 OrderedDictionary에 Select-Object를 적용한 별도표시결함이며 저장receipt에는 run_id/elapsed 등의 값이 있다. Start-Process 반환 객체의 exitcode 회수 경로가 원인후보다. 확정 원인과 해결은 다음 진단으로 검증한다.

다음 round012는 ProcessStartInfo/Process 직접생성과 핸들 유지에 기반한 종료코드 수집을 먼저 검증하고, 새 승인map/mock 성공 후 저장 round010 audit을 한 번 실행한다. M4 tiny 합성 모델실행은 이후 관문으로 미뤘다. 실패한 mock 영수증이나 과거round010은 수정하지 않는다.

## 완료 범위와 미완료

- 완료: verify_frozen_run.py/test_verify_frozen_run.py 구현·소스검토·사본보존, clean-live와drift에서 현재소스관문을 분리하는 fixture2개 실제OK, FREEZE_PROTOCOL.md, M4_CONTRACT.md/source_evidence.json 및 독립 M4_REVIEW.md.
- 미완료: 전체mock 승인관문, 프로그램에 의한 실제저장기록audit 및 최종 provenance_audit.json. 학습·F1·전체모델integration 없음.
- 별도 저장JSON PowerShell 산술교차확인: maxabs1.8446231598301388e-6, argmax[0,1]일치, exact=false, 행합오차5.541369318962097e-8. 이것은 full provenance audit 또는 새추론이 아니다.
- round010의 승인실행사본 SHA c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210와 변경live c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867, 과거전체관문false를 영구보존한다.

실행예산: mock최대2/각30초, actualaudit최대1/30초, 모델0. 사용은 mock1(실행전hash거부는별도), actualaudit0, 모델0. 초기RAM4.2701GiB, 실행준비재확인4.1974GiB/다른Python0. stdlib 예상peak100MiB는 가정이며 실측peak가 아니다. NPZ/checkpoint/reference/raw/holdout읽기0, 원본/이전저장소/과거회차/venv수정0, 설치/업로드/공식제출/유료0.

M4 소스계약은 마지막 Linear W[10,1024]/bias10, 첫4활성출력, p[y]와out[...,p], logits평균후temperature0.9, no_grad차단, context/target분리를 근거행과SHA로 고정했다. 직접W와rank2/bias고정, 합성표현캐시에서각2step·head-only병합/reload 설계이며 아직실행결과가 아니다. references 경로는 rounds/round_002/references/algorithm_variant_ideas.md로 해소했다.

기존 개발OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택탐색0.5933525521451586 유지. 독립/공식null. 기술목표는부분달성, 학습자이해/하드웨어검증은미평가. 질문: 테스트OK와종료영수증성공은 왜 다른가? 승인해시가틀리면실행전에왜중지해야하는가? 수치재현이왜출처실패를없애지않는가?

호스트turn_context는 Astra/high 관리자와 Luna/xhigh 작성자·검토자를 기록하며 내부모델인증은아니다. manager/delegation.json/host_turn_evidence.json 참조. STATUS current_round=round_011,handoff.ready=true로두고 새Astra high에 구체적복구작업을 인계한다. 수락정본은 automation/receipts/round_011_launch.json. 수락후이관리자는종료한다. structured-chat닫기명령이없어 필요하면 완료세션 codex_224a9fbc_58cf_44d2_8dc9_d56b1d8641d0 탭만수동닫는다.

마감 예외 기록: 새 실험은20:23UTC경중지했으나 최종보고·인계문서정리에20:24:05UTC 관리자상한을 넘겼다. 상한준수를완료했다고주장하지않는다. 이후모델/검산추가실행없고필수인계정리만수행했다. 다음회차는문서마감3분을선확보한다.
