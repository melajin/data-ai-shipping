# 다음 Astra high 관리자 — Round 008

사용자는 학습·국소 실험·fresh manager 인계를 승인했다. 반복 승인을 요청하지 않는다. 관리자 gpt-6-astra/high, 작성자와 별도 검토자 gpt-6-luna/xhigh/fork_turns=none만 사용한다. 사용자 보조상한4명과 호스트 총4슬롯 중 낮은 한도를 지키고 파일별 수정 담당자1명을 지정한다. 타인의 수정을 되돌리지 않는다. 모델 요청과 host turn_context 증거를 구분한다.

Round007은 소스·mock·작은 합성 비교를 통과했다. FIT32×312/query2×312에서 같은모델 predict2회 확률 최대절대차0.0, exact numeric equality=true, argmax[1,2]일치. 30.078초, wrapper시작RAM4.787761688GiB/관측최저4.139598846GiB, sampled소유트리peak780906496bytes, 잔존0개다. 8컬럼호출 각각(1,316,34,3), chunk16×19+12로20개씩 총160forward였다. 원관리자복원·입력/shuffle상태일치를 기록했다. 이는 실제선박재현·전체문맥메모리절감·F1 증거가 아니다.

mock01 검사는 통과했으나 종료된 root커널객체를 살아있는것으로 오인한 wrapper결함이 있었다. WaitForSingleObject 실행상태검사를 더한 wrapper로 mock02 정상종료를 확인했다. 원기록은 보존돼 있다.

채택기준 sqrt_macro5seed의 반복노출 개발OUTER5897 micro0.5930133966423605/macro0.5252719738966167은 유지한다. 탐색최고0.5933525521451586은 미채택이며 독립·공식점수는 없다.

## 다음 변경 변수

round006의 동일 FIT3144/고정 INNER2 재현에 round007 컬럼chunk16 어댑터만 추가한다. 원경로 전체문맥 재추론은 하지 않는다. 모델 head/estimators/precision/전처리/질의/문맥/확률허용오차를 바꾸지 않는다. 새 계수학습·F1·OUTER·보호자료 접근은0회다.

## 필수 시작 자료

AGENTS/CYCLE_PROTOCOL/STATUS/NEXT, round007 ROUND_REPORT·author_notes·review/FINAL_REVIEW·artifacts/synthetic_pair_result·logs/pair_01/receipt와 round006/manager/incoming_NEXT_SESSION.md를 읽는다. round007 수신영수증의 세션/해시를 확인한다. 이전 저장소와 원자료는 읽기 전용. 모든 새 파일/temp/cache는 round008 아래다.

## 입력·환경 동결

재export/전체재검산0회. round006/artifacts/context_export_attempt_001/fold0_seed42_context.npz SHA9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5 및 query_freeze.json SHA6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef를 바이트복사·stream해시 확인한다. 고정ID[36001915,31703435], ordered digest7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969. y_inner 접근 금지. 참고 export_result와 round005 독립입력검산은 읽기 전용 근거다.

기존 environments/round_004_tabicl_cpu/Scripts/python.exe, TabICL2.2.0/Torch2.6.0+cpu, checkpoint110368038bytes/SHA bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0. seed42/8estimators/batch1/CPU FP32/AMPfalse/FA3false/n_jobs3/offloadauto/KVfalse/다운로드false. native10출력head와 활성4클래스변환 유지.

## 구현 관문

작성자·별도검토자는 Luna xhigh/fork_turns=none, 관리자는 Astra high; 요청/host증거 구분. round006/code/replay_inner_pilot.py를 새 round008/code로 복사해 round경로와 어댑터 설치·복원·event기록만 수정한다. 입력 freeze 역사schema는 무차별 치환하지 않는다. round007 검증 adapter는 SHA `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded`를 확인해 복사한다. round007 합성소스 SHA `67f74942b38c4c2ee42c6a0509c39997828c0e98658bc04adb2ca96850f445b3`와 설정/진단을 비교한다. wrapper는 round007/manager/run_bounded.py SHA `2820871e8884a0fd642e550301154c16039d6c85c6168bda32cbf67340f3bee4`를 시작점으로 kind=pilot/600초/회차경로/one-attempt claim을 명시적으로 바꾸고 별도검토한다. 과거회차는 수정하지 않는다. ROW/ICL·전역클래스·venv 불변.

중요: `fit()` 직후 원컬럼관리자는 아직 configure되지 않아 기존 adapter 설치조건을 충족하지 않을 수 있다. 원경로 predict를 먼저 호출하지 말고, pinned embedding.py와 동일하게 `original_col_manager.configure(**estimator.inference_config_.COL_CONFIG)`를 호출한다. resolvedCPU/AMP/offload조건을 검사한 다음 설치한다. 실제 ColumnEmbedding은 호출 때 같은configure를 다시 수행한다. 이 순서의 의미/동일설정을 별도소스검토하고 pure mock으로 fit상태→configure→install→call→finally restore를 검증한다. 설치 시점에 임의설정을 추가하지 않는다.

mock1회≤30초(결함수정후1회추가만). 소스/SHA/검토/mock 관문 후 실제 추론1회≤600초, 생성부터 종료확인까지(마지막10초cleanup 예약). checkpoint load1/문맥fit1/predict_proba1; 큰계산동시1, threads≤3. 시작RAM≥3GiB, 실행중<1.5GiB면 소유PID·생성시각 일치트리만 중단. 실행 시작후 재시도0회. 관리자30분.

## 판정·분기

입력/freeze/ID검사 후 이전 공유P/evaluation/seed_42/fold_0/inner_predictions.csv의 헤더와 처음2행 p0..p3만 읽는다. ID불일치 시 검색·대체하지 않는다. INNER레이블·다른확률행을 읽지 않는다. 두확률2×4 finite/[0,1]/행합오차≤1e-5/클래스[0,1,2,3], 역사 원확률대비 최대절대차≤1e-4 및 두argmax일치. exact/tolerance 구분. 재호출·허용오차확대 금지.

동작·차이·RAM·시간·실제chunkshape·소유PID종료·복원을 기록한다. 작은합성의 메모리 사용량으로 전체문맥 절감을 보장하지 않는다. RAM부족 시 다른독립작업 후재확인, 이전실패와 비교하고 단순 polling 금지. 실패 시 단계/자원/수치오류를 분리해 가설변경; 실행불가 외부제약이면 정확한 재개조건을 남긴다. 실제재현통과 전 M4-a 금지; 통과해도 M4-a는 별도 bounded설계다.

계절 가설은 round007/SEASONAL_FEATURE_INVENTORY.md를 보존한 별도후속후보로 유지한다. 현재재현에 특징을 추가하지 않는다. 개발/독립/공식 점수 분리, 목표0.7미달이며 미측정성능을 만들지 않는다.


## 실행 명령과 산출

다음은 작성·별도검토·mock 후 실제 승인 SHA를 넣고 한 번 실행할 예정 명령이다. 현재 round008 파일은 아직 없으며 구현했다고 간주하지 않는다.

```powershell
$expected = '<round008 독립검토 승인 replay_inner_pilot.py SHA256>'
if ((Get-FileHash './rounds/round_008/code/replay_inner_pilot.py' -Algorithm SHA256).Hash -ne $expected) { throw 'Frozen source changed' }
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_008/manager/run_bounded.py' --kind pilot --run-id pilot_01 --script './rounds/round_008/code/replay_inner_pilot.py'
```

승인manifest에 adapter/pilot/wrapper 및 pinnedsource 해시를 포함한다. source snapshot을 실행하고 stdout/stderr/RAM곡선/PID생성시각/실행 및 종료확인시각/종료코드를 보존한다. 실제자원확인에는 확인시각·추정peak근거·다른실행작업을 기록한다. 입력 raw행렬만으로 peak를 추정하지 않는다. 분할컬럼 외 ROW/ICL도 큰중간배열을 가질수 있으므로 전체메모리절감은 미확인이다. 중단되면 마지막완료컬럼/현재단계로 원인을 좁히고 똑같은경로를 다시실행하지 않는다.

RAM부족 시 먼저 계절인벤토리 후속설계·소스검토·문서/입력계약 검산처럼 가능한 독립작업을 수행한 뒤 실행직전에 RAM을 다시확인한다. 자원이 부족하고 다른작업도 없으면 정확한외부제약/재개조건을 남긴다. RAM확인만 반복하는 세션/무한재시도는 만들지 않는다. 소유프로세스 외 종료 금지. 원자료 F:/문제 데이터_수정_1027, 이전 D:/repos/fishing-track-classification 및 공유P는 읽기전용. holdout/전체7372행/Test2025 접근 금지, 설치다운로드·외부업로드·공식제출·유료자원은 이번범위 제외.

기술목표는 고정 실제두질의 재현, 학습목표는 작은합성동등성과 실제자료재현/F1, 계산축과 자원병목을 구분하는것이다. 학습자이해와 장치동작을 측정했다고 하지 않는다.

완료 시 rounds/round_008/ROUND_REPORT.md(이전→현재→다음), 독립검토, EXPERIMENT_LEDGER.csv, STATUS.json(current_round=round_008, handoff.ready=true, active_workers=[]), NEXT_SESSION.md를 실제결과대로 저장한다. 목표미달이고 실행가능한후속이 있으면 다음명령을 실행해 prompt수락영수증을 확인한 뒤 현재관리작업을 종료한다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_008'
```

CLI에 structured-chat 닫기수단이 없으면 해당완료세션ID와 수동탭닫기방법을 남기고 중지한다. 다른세션/앱전체는 닫지 않는다. 다음관리자의 수락은 요청모델의 실제실행인증이 아니며 새관리자가 자기host증거를 확인해야 한다.
