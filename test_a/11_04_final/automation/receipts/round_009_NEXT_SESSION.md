# 다음 Astra high 관리자 — Round 010

round009 합성 gate가 통과하여 이 성공분기를 확정한다. 사용자 승인된 국소 실험/인계이며 반복 승인을 묻지 않는다. 먼저 AGENTS/CYCLE_PROTOCOL/STATUS, round009 ROUND_REPORT·PLAN_AMENDMENT_01·review/SOURCE_REVIEW·MOCK_REVIEW·FINAL_REVIEW·approved_sources·author_notes·artifacts/result·logs/pair_01/receipt를 읽고 수신영수증/인계 SHA/세션ID를 대조하여 중복실행을 피한다. 관리자 gpt-6-astra/high, 별도 작성자와 검토자 gpt-6-luna/xhigh/fork none만 생성하고 요청 및 host기록을 분리한다. 모든 새 출력/temp/cache는 round010 아래, 원자료/이전저장소/과거회차/venv는읽기전용. 파일별담당1명과타인수정보존을지킨다.

round010: 고정 실제 FIT3144×312와 기존 두 INNER 질의에 검증 column16+row8을 함께 적용하는 재현1회. 모델/특징/클래스/head/입력 순서/정밀도/seed/estimators/배치 설정은 기존 유지. checkpoint1/contextfit1/predict1, 원경로 추가실행0, M4/새 계수학습/OUTER/holdout/F1/원자료읽기0. 실제 입력은 이미 승인된 development context만.

입력은 round008/artifacts/context_export_attempt_001에서 새회차로 바이트복사한 후 hash 확인: context NPZ1916394bytes/9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5, query_freeze748bytes/6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef. 고정 ID [36001915,31703435], digest7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969. 보호자료·명부를 탐색하여 다른 질의를 고르지 않는다. reference는 round008 pilot의 고정경로 첫 두 행만 기존 reader로 읽으며 y_inner는 읽지 않는다.

작성자는 새 pilot/mock/wrapper, 검토자는 source/승인manifest/결과 독립검산, 관리자는 계획/입력복사/실행/공유문서. 어댑터 두 개는 round009 실행 승인본을 바이트복사한다. ROW는 실제재현에서 baseline이 없으므로 fit직후 원ROW에 resolved ROW_CONFIG를 configure한 뒤 어댑터를 설치해야 한다. COL도 기존 configure-before-install 유지. 원관리자 복원은 모든 설치 이후 진단을 포함하는 try/finally 안에서 기록보다 먼저 수행한다.

ROW/ICL 단계별 진입/완료를 기존 호출 안에서 기록하여 이후 실패를 좁힌다. 새로운 forward/predict를 추가하지 않는다. ICL 전체 T문맥·train_size를 자르지 않는다. source 객체 덮어쓰기 금지, configure_source 등 별도 키 사용. 설치 전 mock은 callable 가짜원관리자, 설정 전달, 두 어댑터 공존/복원, 짧은 청크/순서/미인식 tensor 거부를 검증한다.

통과 조건은 기존 실제재현과 동일: finite/[0,1]2×4, 클래스[0,1,2,3], 행합오차≤1e-5, 고정 historical reference와 최대절대차≤1e-4, 두argmax일치, 입력/shuffle불변. exact와 tolerance 구분. tolerance를 합성1e-5와 혼동하지 않는다. 실패 후오차완화·질의교체·재시도 금지.

고정 최대예산: 관리자30분, mock1회≤30초+결함수정후1회, 실제1회≤600초(정리10 포함), 큰계산동시1/threads≤3. 실제실행 전RAM≥4GiB, 실행중<1.5GiB에서소유PID/생성시각/실행상태확인후정리. 새경로전체peak미측정; 이전중단sampled peak약2.96GiB/실제수요상한아님, 잔존column출력/ICL위험기록. 부족하면계절metadata/소스계약·문서검산후재확인. 대체작업후에도부족하면같은RAM조회만하는후속세션을만들지말고정확한재개조건을남긴다.

성공은고정두질의재현증거뿐이다. M4 실행은자동으로추가하지않고다음별도회차에서평가계약/자원/선택규칙을검토한다. 실패는마지막ROW/ICL/column경계와자원·수치·설정계층을분리하고동일무변경실험을반복하지않는다.


## 이번 결과와 정확한 후속 명령

round009 pair1회49.187초 exit0, probabilities maxabs0/exacttrue/argmax[1,2], fit1/predict2, 양어댑터복원, 소유잔존0. 시작4.44189/min3.93400GiB, sampled peak556965888bytes. tiny 합성만이며 실제3144문맥 메모리절감/F1 주장은없다. 기준개발OUTER5897 micro0.5930133966423605, 탐색미채택0.5933525521451586, 독립/공식null, 0.7미달. 보호holdout은노출이력관문전읽지않는다.

검증어댑터 SHA: column bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded; row d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b. round009 wrapper b8e5d7de47ba070ed9df52badb1002f1955d67798e679e240e295a05ba87a439를 새회차 real_pilot/최대600초/one-pilot claim/동일승인map mock관문으로 명시적 개작·별도검토한다. PID메모리조회실패와식별조회실패를구분하고 exactPopen handle fallback 및 미확인자손unverified보존을유지한다. 무차별문자열치환금지. round008 pilot112ca09e7abba9c194421c22bd38771563636e2852c867c089cb27e985c39b0d는기존입력·reference reader/설정근거이며 source객체덮어쓰기결함을복제하지않는다.

현재 새 실행파일은 아직 없다. 구현/독립검토/mock통과/승인SHA검사 후 예정명령:
```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_010/manager/run_bounded.py' --kind pilot --run-id pilot_01 --script './rounds/round_010/code/replay_inner_pilot.py'
```
python환경·checkpoint는기존공유경로를읽기전용사용한다. raw원자료는읽지않는다. original reference경로는 D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/evaluation/seed_42/fold_0/inner_predictions.csv (round008 source P정의와정적대조완료;읽기전용)이며 header/첫두행의ID와p0..p3만읽고다른라벨/행검색없음. 실험전원본source에서정확경로를재확인한다.

이번 단계 기술목표는고정두질의실제재현, 학습목표는합성→실제관문과자원병목분리다. 각단계조건/예상/계산값/해석과설명질문을기록한다. 학습자이해/장치검증을주장하지않는다. 완료시ROUND_REPORT(이전→현재→다음),EXPERIMENT_LEDGER,STATUS(current_round=round_010,handoff.ready=true,active_workers=[]),NEXT_SESSION을갱신한다. 실행가능후속이면아래명령수락영수증확인후중지한다:
```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_010'
```
지원닫기명령이없으면완료세션ID와그탭만수동닫기방법을남긴다. RAM만반복조회하는새세션을만들지않는다. 외부제약은정확재개조건/명령을남긴다.

