# 다음 Astra high 관리자 — Round 009

사용자는 국소 실험과 fresh manager 인계를 승인했다. 반복 승인을 요청하지 않는다. 관리자 gpt-6-astra/high, 작성자와 독립검토자는 gpt-6-luna/xhigh/fork_turns=none. 요청/host turn_context 증거를 구분하며 사용자 보조4명과 호스트총4슬롯 중 낮은 한도를 지킨다. 파일별 담당1명, 타인수정 되돌리기 금지. 모든 새 산출/temp/cache는 rounds/round_009 아래, 원자료/이전저장소/과거회차/venv는 읽기전용.

## 시작과 이전 결과

AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round008 ROUND_REPORT·PLAN_AMENDMENT_01·author_notes·review/SOURCE_REVIEW·review/FINAL_REVIEW·artifacts/result·logs/pilot_01/receipt·POST_COLUMN_SOURCE_AUDIT와 round007 합성자료/소스 계약을 읽는다. round008 수신영수증의 세션ID/인계해시를 대조하고 중복실행을 피한다.

round008은 컬럼chunk16으로 동일FIT3144/INNER2 실제재현1회 실행했으나25.64초 후RAM관문으로 중단됐다. 시작4.144317627/관측최저1.379962921GiB, sampled tree peak3,182,952,448bytes, termination_confirmed=true/잔존0. 첫컬럼call0 입력(1,223,3146,3)→출력(1,223,3146,128),14청크(16×13+15)가 완료됐고 다음컬럼시작은 없다. predict1시도/0완료, 확률null, F1없음. 정확한실패연산은 미계측이므로 ROW OOM으로 확정하지 않는다. finally복원은 강제종료로 관측되지 않았다. 로컬프로세스는 종료됐다.

mock01은FakeManager.__call__누락으로실패했고 mock02는0.266초exit0으로통과했다. 모델실패가아니다. 실제pilot재시도0. 결과정리/소스대체작업후19:00:25UTC RAM4.392494GiB로회복했으나 같은경로를 다시실행하지 않았다. 600초 상한은 실제실행전420초로축소됐으며 시간초과가아닌RAM중단이다.

채택기준 반복개발OUTER5897 sqrt_macro5seed micro0.5930133966423605/macro0.5252719738966167 유지. 탐색0.5933525521451586은미채택. 독립/공식점수없음, 목표0.7미달.

## 다음 변경 가설과 범위

가설: 컬럼 이후 ROW interaction에서 독립적인 선박관측행 배치축을 분할하면 의미를 유지하면서 중간배열 크기를 제한할 수 있다. 현재 증거는 소스가설과 마지막컬럼완료경계이며 실제메모리절감 증거가 아니다. **동일 전체문맥 재현은 round009에서0회**. 새로운 계수학습/M4/F1/OUTER/holdout/실제특징배열/실제확률/원자료읽기0회.

먼저 pinned source로 컬럼return→ROW→ICL 경로를 검토한다. ROW의 attention/normalization이 행배치축을 섞지 않는지, feature/register-token축과 전체T문맥을 보존하는지 증명한다. source hash/줄근거/가정을 남긴다. 독립성을 입증하지 못하면 임의분할하지 말고 구체적인 미해결계약과 다른다음가설을 문서화한다. 현재단계전체시스템 자동완성 금지.

독립성이 확인되면 로컬 인스턴스의 row_interactor.inference_mgr만 감싸는 고정rowchunk8 어댑터를 새로 작성한다. 기존columnchunk16과 ICL/전역클래스/모델head/정밀도/venv는 바꾸지 않는다. 원manager._prepare_inputs/_run_forward 및 CPU/no_grad/AMP 의미를 보존한다. 모든 feature/register token의 sequence축은 유지하고 leading independent row batch축만 자른다. 입력tensor의 공유/슬라이스 계약을 명시하며 미인식tensor는거부한다. 원순서재조립/짧은마지막chunk/output_repeat/설정전달/복원을 검증한다. 전역monkeypatch나환경파일수정 금지.

작성자는code/* 및 필요한manager/run_bounded.py, 검토자는review/*/승인manifest, 관리자는계획/실행/공유문서 담당. 작성/검토분리, 동일파일동시쓰기금지. 과거소스에무차별문자열치환금지. mock에는호출가능한FakeManager와설정상태를포함한다. 설치뒤모든진단을try안에두고finally는기록보다먼저원관리자를복원한다. wrapper는Popen직후첫기록쓰기전에PID/생성시각확보, WaitForSingleObject 실행상태와함께소유트리정리한다.

## 고정 합성 비교

round007의합성생성과모델계약을재사용: default_rng(20261105), 표준정규float32 FIT32×312/query2×312, y=tile(arange(4),8). 실제자료NPZ는열지않는다. checkpoint기존110368038bytes/SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0. Python환경environments/round_004_tabicl_cpu/Scripts/python.exe, TabICL2.2.0/Torch2.6.0+cpu. seed42/estimators8/batch1/n_jobs3/CPU FP32/AMPfalse/FA3false/KVfalse/offloadauto/다운로드false, native10출력head/활성4클래스 그대로.

동일fitted estimator에서 딱2predict:
1. baseline=검증columnchunk16만 적용, ROW원경로.
2. candidate=같은columnchunk16 + 새rowchunk8.

fit직후COL_CONFIG로원컬럼관리자를configure하고설치하는round008계약을사용한다. baseline이원ROW관리자를configure한뒤candidate에서row어댑터를설치한다. 기준예측을추가하지않는다. 두호출입력shape/dtype/hash·shuffle상태불변, 클래스[0,1,2,3], 확률2×4 finite/[0,1]/행합오차≤1e-5, 최대절대확률차≤1e-5와두argmax일치를통과조건으로동결한다. exact와tolerance분리. 재호출/오차완화금지. column/row실제shape·chunk수·각stage시작/완료·복원·RAM/시간을남긴다. 작은합성통과로전체문맥메모리절감/F1을주장하지않는다.

검증column adapter round008/code/column_chunk.py SHA bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded 그대로복사. round007/code/synthetic_pair.py SHA67f74942b38c4c2ee42c6a0509c39997828c0e98658bc04adb2ca96850f445b3는합성생성/환경/진단참고다. round008 pilot SHA112ca09e7abba9c194421c22bd38771563636e2852c867c089cb27e985c39b0d는configure/복원참고이며실제입력로딩부분은가져와실행하지않는다. round008 wrapper SHA6962c94fa07a36cd7b3429eaeb27ac851aee3104e9b77758d7a99c0fc1a48e1d를새round경로·kind=synthetic_pair·300초·one-pair claim으로명시변경후별도검토한다. 원round008은수정하지않는다.

## 유한 예산과 실행

관리자30분. source/mock관문후작은합성pair1회≤300초(정리10포함), checkpoint1/문맥fit1/predict2, 재시도0. puremock1회≤30초+결함수정후1회만. 큰계산동시1/threads≤3. 시작RAM≥3GiB, 실행중<1.5GiB이면PID/생성시각일치소유트리만중단. 사용자프로세스종료금지. 기대메모리는round007합성peak약0.73GiB를참고하되새경로peak미확인; 보수적으로1–2GiB를계획추정하고실행직전RAM/다른작업을확인한다. 부족하면소스검토/계절후속설계/문서검산후재확인. 단순RAM polling/무한재시도금지.

예정명령(파일은아직없고구현후승인SHA로검사):
```powershell
$expected = '<독립검토 승인 round009 synthetic_pair.py SHA256>'
if ((Get-FileHash './rounds/round_009/code/synthetic_pair.py').Hash -ne $expected) { throw 'Frozen source changed' }
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_009/manager/run_bounded.py' --kind synthetic_pair --run-id pair_01 --script './rounds/round_009/code/synthetic_pair.py'
```
승인manifest에adapter/합성script/mock/wrapper/pinnedsource hash, source snapshot과실제실행경로/환경/종료receipt를남긴다. 성공하면다음별도회차에서동일실제FIT/두질의에col+row경로를적용하는bounded설계를한다. 합성실패면수치/설정/shape/자원계층을분리하고다른가설로전환한다. 실제재현통과전M4금지. 계절가설은독립후속후보로유지하며이번입력에섞지않는다.

## 완료·인계

기술목표는소스독립성+mock+합성의미보존확인, 학습목표는컬럼/행배치/attention문맥축과자원병목구분이다. 학습자이해·장치동작은측정하지않는다.

ROUND_REPORT(이전→현재→다음),독립검토,EXPERIMENT_LEDGER,STATUS(current_round=round_009,handoff.ready=true,active_workers=[]),NEXT_SESSION을실제값으로저장한다. 목표미달이고실행가능한후속이면아래명령으로fresh Astra high에인계하고수락영수증확인후중지한다. 외부제약이면정확한재개조건/명령을남기고동일실패/RAM조회만하는세션을만들지않는다.
```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_009'
```
CLI에structured-chat닫기수단이없으면완료세션ID와그탭만수동닫기방법을남기고중지한다. 앱전체/다른세션은닫지않는다. 수락영수증은모델인증이아니며새관리자가자기host기록을확인한다.

진단기록 주의: round008 pilot의 stage(..., source=...)가 top-level source 객체를 덮었다. 실행정본은receipt/승인manifest/snapshot에보존됐으나 새소스에서는 configure_source 등별도키로기록하고 source객체를보존한다. 이진단결함을고치려고실제replay를반복하지않는다.

ROW후속소스근거는round008/POST_COLUMN_SOURCE_AUDIT.md다. tabicl.py:422–440,column→ROW→ICL; interaction.py:215–253의ROW는(B,T,H+C,E)에서H+C가attention sequence이고B,T가batch다. learning.py:241–282의ICL은T가문맥sequence이므로분할하지않는다. tiny비교시ROW출력을추가확인하려면정해진두predict내에서출력을기록하고추가forward/predict를만들지않는다. 실제ROW진입계측이없어이번중단위치는미확정이라는한계를유지한다.

호출수해석: predict_proba는총2회이며각호출의기존8estimators 내부COL/ROW/ICL호출수는그대로유지한다. ICL을하나로합치거나추가독립forward를만들지않는다. 앞서말한전체sequence ICL은각기존estimator경로의문맥을자르지않는다는뜻이다.
