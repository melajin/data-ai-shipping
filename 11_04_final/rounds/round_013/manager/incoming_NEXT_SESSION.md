# 다음 Astra high 관리자 — Round013: 승인 실행기의 유한 동적 검증과 저장기록 검산

사용자가 승인한 후속이다. AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round012 ROUND_REPORT/ROUND_PLAN/FREEZE_PROTOCOL, review/SOURCE_REVIEW/FINAL_REVIEW, code/candidate_sources.json와approved_sources.json, manager/candidate_freeze_ack/prelaunch_deadline_block/EXECUTION_COMMANDS/host_turn_evidence를 읽고 인계SHA·수신session·중복관리자 여부를 확인한다. 관리자Astra/high, 별도작성자·검토자Luna/xhigh/forknone만,host4슬롯/사용자보조4우선. 요청과host기록은내부모델인증아님.

Round012는 ProcessStartInfo 기반PS5.1실행기와audit/fixture의독립소스승인을완료했다. 그러나실제smoke시작전20:42cutoff로차단되어smoke/mock/audit모두0,claim없음이다. 코드검토를동적성공으로보지말것. round011의null exit실패와round010의historyfalse는영구보존. 기존개발OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167,미채택탐색0.5933525521451586,독립/공식null,목표미달. 이번새F1평가도0.

이번은 새실행기설계가아니라승인소스의동적검증이다. 관리자20분,실험마감17분/문서3분. 작성자최초4분안최소사본/ACK,검토자그뒤3분안diff중심검토목표,계산은시작10분이내착수목표. 불충분하면강제승인하지않되 M4재연구/불필요추가기능으로현재검산을다시지연하지않는다. 독립작업은코드사본과이미완료된소스계약확인만.

1. 모든과거회차/원자료 F:/문제 데이터_수정_1027/이전repo D:/repos/fishing-track-classification/venv읽기전용. 신규출력round013(code/review/logs/artifacts/manager/temp)만. 작성자는round012/code의auditor/test/runner를round013/code로복사하고round012/round_012의출력경로·schema·함수명을round013로최소치환한다. 기존 round010 원천경로/역사관문/검산논리를바꾸지않는다. reviewer는원래승인SHA확인+변경diff+최종파일직접해시로새approved_sources.json생성. 관리자실행/공유상태만소유. 타인변경되돌림금지. 작성자ACK후수정금지.
2. 정확실행명령(소스복사와검토후): & './rounds/round_013/code/run_audit.ps1' -Mode smoke; 성공후같은runner -Mode mock -MockNumber 1; 성공후 -Mode audit. 작업cwd루트고정. 기존round012 runner를그대로실행하면옛회차에쓰므로실행하지않는다. Python은기존base C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B -S,stdlib만. 새로그/claim/영수증은round013에남긴다.
3. smoke1회≤10초(명시exit0/7 child각1개순차),retry0. 정수exit0/7·stdout/stderr·owned종료·잔존없음·hash불변필수. 실패면mock/audit금지. null을0으로int강제변환금지. PS5.1의Arguments안전quoting/EnvironmentVariables,동시ReadToEndAsync/시간제한,승인map전후SHA를보존한다.
4. pure fixture mock최초1회≤30초(28+2),실제결함수정후최대1회추가만. 단,새map으로retry할때이미소진된smoke재실행없이충족할수없는관문이면차단하고후속회차로넘긴다. 승인map을사후수정해서통과시키지않는다. clean-live/historyfail과live-drift 두fixture에서current/historical분리. 정수exit0/completed/hash/owned종료전부true후다음단계.
5. 실제저장기록audit1회≤30초,retry0. source round010의approvedmap/실행사본/mock·pilotreceipt/source diff/progress/저장JSON2×4확률만. output rounds/round_013/artifacts/provenance_audit.json. 예상snapshottrue/livefalse/currentgatefalse/numerictrue/auditintegritytrue/historicalfalse. 실패는프로세스/출처/수치계층분리. NPZ/checkpoint재해시0(작은source는1MiB streaming),원래sourcefreeze실패를통과시키는옵션금지.

checkpointload/fit/predict/forward/backward/F1/NPZ/reference/raw/OUTER/holdout/설치/업로드/유료0. 이번에는M4모델실행하지않는다. RAM병렬/실행전시각·가용·예상peak·다른작업기록,stdlib예상100MiB/시작가용≥0.5GiB. 부족시소스/문서먼저후직전재확인;반복polling/사용자process종료금지. 마지막4.4427GiB는과거값이며재사용금지.

성공하면다음fresh회차에서round011/m4_contract/M4_CONTRACT.md/source_evidence와round011/review/M4_REVIEW,round012/review/M4_NEXT_CHECKLIST를근거로tiny합성head검증진행. round012/manager/NEXT_SUCCESS_DRAFT.md는미실행성공조건부초안이며이번실행지시가아니다;검산성공후다음회차번호를바꿔승격가능. hook full20행중앞16 label-bearing context를제외하고target4행만캐시한다는소스검토는이미완료되어재연구불필요. 불성공이면새원인과정확재개방법만구체인계하며같은실패무한반복금지.

완료시ROUND_REPORT(이전→현재→다음),STATUS.current_round=round_013,handoff.ready=true,active_workers=[],LEDGER,NEXT갱신. 목표미달·다음실행가능이면 & 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_013' 실행하고수락receipt/newsession/promptdelivery확인즉시현재관리자중지. structured-chat닫기지원없으면완료탭만수동닫는제한기록. 반복승인불필요.
