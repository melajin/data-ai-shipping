# 다음 Astra high 관리자 — Round012: 종료코드 수집 수정과 저장기록 검산

승인된 후속이다. 작업루트 AGENTS/CYCLE_PROTOCOL/STATUS, round011 ROUND_REPORT/ROUND_PLAN/FREEZE_PROTOCOL, review/SOURCE_REVIEW/FINAL_REVIEW/M4_REVIEW, manager/prelaunch_manifest_typo, logs/mock_01/receipt+stdout+stderr, artifacts/result를 먼저 읽고 인계SHA·수신session을 확인한다. 같은회차 다른관리자가있으면중복실행금지. 관리자Astra/high,별도작성자·검토자Luna/xhigh/forknone만,host4슬롯우선. 요청과hostturn_context는내부모델인증이아니다. 이전회차/원자료/이전저장소/venv읽기전용,모든신규출력round012.

round011 pure unittest2개 OK(0.098초)이나 wrapperreceipt elapsed0.4837655초,exit_code=null,owned_process_exited=true,completed=false. 따라서 전체mock실패,actual saved audit0회(영수증/claim없음). 테스트OK를exit0으로추정금지. Start-Process/Process 객체의 종료코드회수경로가원인후보다. 콘솔요약null은 OrderedDictionary에Select-Object한별도표시결함. 승인map의test SHA extra-b오타는실행전차단됐고reviewer가원본map보존후정정;코드변경없음. 과거receipt수정/사후clean소급금지.

목표0.7미달. 개발OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167,미채택탐색0.5933525521451586,독립/공식null. round010두질의수치재현true/maxabs1.8446231598301388e-6/argmax[0,1]일치/exactfalse이나livewrapperdrift로전체false영구보존. 모델재실행/F1/실제자료학습0. holdout읽기금지.

이번계약: 관리자20분(문서마감여유3분선확보), 계산모두stdlib. checkpointload/fit/predict/forward/gradient/F1/NPZ/reference/raw/OUTER/holdout/설치/업로드/유료0. 기존저장JSON2×4확률과소스/메타데이터만. M4는round011/m4_contract/M4_CONTRACT.md에독립검토된준비계약이있으나이번모델실행금지. manager/NEXT_SESSION_candidate.md는폐기된M4초안이며실행지시로쓰지않는다.

1. 작성자는 round012/code/* 및 새프로세스runner를소유,검토자는review/*,관리자는실행/공유문서. round011검산코드/테스트를버전복사하며원본불변. wrapper를직접ProcessStartInfo/Process로시작하고핸들·시작시각·WaitForExit·ExitCode를보존하도록수정한다. 표준출력/오류를동시에비동기로배출해파이프교착을피하고,30초총상한(28+2),소유프로세스정리와잔존확인,새claim·동일승인map·사본/현재파일전후hash를유지한다. null exit는실패로남긴다. `[pscustomobject]` 변환후콘솔요약하거나JSON직접출력한다. 작성자candidateACK후쓰기중지,독립승인후수정금지.
2. Process control stdlib smoke1회≤10초: 명시적exit0과exit7을각1child(최대2개순차)로발생시키고영수증정수exit0/7·소유종료·stdout/stderr를검증한다. 모델/실자료없음. 이smoke실패면본mock/audit금지,동일재시도하지않고원인기록.
3. 새승인map에서mock최초1회≤30초+결함수정후최대1회. clean-live/history-fail,currentlive-drift 두fixture의현재소스/역사전체관문분리를확인한다. mock의정수exit0/완료/hash/종료가모두true여야다음단계.
4. 실제저장기록검산1회≤30초,재시도0. round010승인map,실행사본,mock/pilotreceipt,source diff,progress,저장확률만. NPZ/checkpoint재해시0(1MiBstream),원래sourcefreeze실패를통과시키는옵션금지. snapshot/live/current source/numeric/audit integrity/historicalfalse 분리. 새output round012/artifacts/provenance_audit.json으로출력제한을새회차에맞춰소스수정·검토한다(옛코드는round011만허용). actualpilot/model재실행금지.

예정명령은구현/검토후확정: 기반python C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B -S 와검토된wrapper사용. rootcwd고정,새round012출력만. 기존run_audit.ps1을다시실행하지않는다. 승인map은직접해시생성으로오타방지.

RAM실행/병렬전시각·가용량·예상peak·다른작업확인. stdlib예상≤100MiB,큰계산0,시작가용≥0.5GiB. 부족하면소스/문서후직전재확인,반복polling/사용자process종료금지. 실패는모델수치가아닌프로세스영수증/출처계층으로좁힌다. 학습질문: 테스트OK와정수exit증거는왜다른가? 현재live복원이왜역사실패를지우지못하는가?

완료시ROUND_REPORT(이전→현재→다음),STATUS.current_round=round_012,handoff.ready=true,active_workers=[],LEDGER,NEXT갱신. source/mock/actualaudit가성공하면다음fresh회차에기존M4계약의tiny합성검증을구체인계한다. 불성공이면바뀐원인/정확재개방법,동일실패무한반복금지. 목표미달·후속실행가능이면:
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_012'
수락영수증/새session/promptdelivery확인즉시기존관리자종료. structured-chat닫기지원없으면완료탭만수동닫는제한기록. 반복승인은불필요.
