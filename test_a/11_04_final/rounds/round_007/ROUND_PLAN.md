# Round 007 — 실행 전 고정 계획

기술 목표: pinned TabICL CPU 컬럼 계산의 독립 leading batch축만 최대16으로 나누는 로컬 어댑터의 의미 보존을 소스·mock·작은 합성 비교로 확인한다. 학습 목표: batch축과 attention sequence축, 합성 수치동등성과 실제자료 재현·F1 평가를 구분해 설명한다. 학습자의 이해는 아직 평가하지 않았다.

이전 회차의 실제 FIT3144 추론은 가용 RAM1.5GiB 미만에서 중단됐다. CPU 자동분할 우회가 중간 메모리 증가 원인일 수 있다는 가설이며 정확한 할당 위치와 최종 peak는 미측정이다. 이번에는 실제자료 배열·확률·원자료·holdout을 읽지 않는다.

## 동결 조건

- 관리자 30분: manager/start_evidence.json의 시작·마감시각 기준. 큰 계산 동시1, threads≤3.
- 작성자와 독립검토자: GPT-6 Luna xhigh, fork_turns=none. 관리자 요청 GPT-6 Astra high. 호스트 turn_context 증거와 요청값을 구분한다. 소스 작업 예상 추가 RAM<0.2GiB, 모델 비교 예상 peak 1–2GiB(미측정 추정; checkpoint 약105MiB, 34행×312 입력과 CPU Torch 기본량; 전체3144행 peak를 작은 입력에 적용하지 않음). 실행 직전 RAM≥3GiB, 실행 중<1.5GiB 중단.
- 소스수정1세트와 독립검토. pure mock1회≤30초; 실패하면 근거 수정 후 추가1회만. 합성 비교 최대1회/총300초(종료 확인 포함), 실제 계산 시작 뒤 재시도0회. 종료 cleanup 최대10초를 전체300초 안에 예약한다.
- checkpoint load1, pretrained estimator fit1(계수학습0), 동일 fitted estimator predict_proba2회: 원경로1+컬럼분할1. 모델/데이터/F1 탐색0회.
- NumPy default_rng(20261105), normal float32 X_fit(32,312), X_query(2,312), y=np.tile(arange(4),8). seed42, estimators8, batch1, CPU FP32, AMP/FA3/KV=false, n_jobs3 및 round006 설정 보존.
- chunk16은 컬럼 독립 leading batch축만. FIT/query sequence·feature grouping내부·attention문맥축은 보존. 원관리자 prepare/run_forward 사용, 해당 estimator 컬럼관리자만 감싸고 복원. ROW/ICL·전역클래스·venv 불변.
- 두 확률 각각2×4, finite/[0,1], 행합오차≤1e-5, 클래스[0,1,2,3]. 최대절대차≤1e-5 및 argmax2개 일치. 실패 후 tolerance 변경 금지. exact 일치 별도 표기.

## 책임과 관문

code_author는 code/*·author_notes.md, reviewer는 review/*, 관리자는 manager/*·공유계약·실행·결과문서 담당. 원자료/이전저장소/과거회차 수정 금지. 작성자 소스증명·SHA와 별도 검토·mock 통과 전 모델 실행 금지. pinned source hash, snapshot, PID 생성시각, stdout/stderr, RAM곡선, 종료코드 보존.

RAM 부족 시 소스검토·코드·계절특징 인벤토리·문서부터 진행하고 재개 직전 다시 확인한다. RAM polling만 반복하지 않는다. 사용자 프로세스는 종료하지 않는다.

## 완료와 다음 분기

합성 통과 시 다음 회차에 동일 FIT3144/고정두질의의 어댑터 실제재현1회를 별도 계획한다. 합성 통과는 실제자료 동등성/F1/전체문맥 메모리 절감 입증이 아니다. 실패 시 실패 계층과 변경변수를 좁힌 다음 가설을 작성한다. 실제재현 통과 전 M4-a 학습 금지. 사용자 계절 가설은 코드와 특징명 metadata만으로 인벤토리화하며 계절모델학습은 이번 범위 밖이다.

보고서·ledger·STATUS(current_round=round_007,handoff.ready=true)·NEXT_SESSION을 저장하고 실행가능 후속이 있으면 지정 Start-NextSession.ps1로 새 관리자에게 전달해 수락영수증을 확인한다.
