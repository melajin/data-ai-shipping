# Round 009 결과 — ROW chunk8 합성 의미 보존 통과

고정 합성 FIT32×312/질의2×312에서 column16 기준 경로와 column16+row8 후보 경로의 확률이 정확히 같았다. 최대절대차0, 두 argmax [1,2] 일치, 허용오차1e-5 통과다. mock1회와 합성pair1회만 실행했다. 실제자료 재현·새 F1은 없으며 목표 micro-F1 0.7은 아직 미달이다.

## 이전 → 현재 → 다음

round008은 실제 FIT3144/INNER2 컬럼분할 재현 중 RAM 관문으로 중단됐다. 첫 컬럼호출14청크 완료는 확인했지만 ROW 진입은 계측하지 않아 정확한 중단연산은 미확정이다. 이번에는 동일 실제실험을 반복하지 않고 ROW 독립 행배치축의 분할 가설을 소스·mock·작은 합성에서 검증했다.

독립 소스검토는 ROW의 B,T가 배치축이고 feature/register token 축이 attention sequence임을 확인했다. LayerNorm은 마지막 임베딩 축에 적용된다. ICL은 전체 T의 FIT 문맥을 사용하므로 그대로 유지했다. 이번 성공은 이 고정 합성의 의미 보존 증거다. 다음 round010은 기존 실제 FIT/고정 두 질의에 두 어댑터를 적용하는 별도 bounded 재현1회이며 새 학습/F1은 포함하지 않는다.

## 조건과 실제 계산값

| 항목 | 결과 |
|---|---|
| 합성 입력 | default_rng(20261105), normal float32 FIT32×312/query2×312, y=tile(arange(4),8) |
| 모델 | 고정110368038byte checkpoint, TabICL2.2.0/Torch2.6.0+cpu, seed42/estimators8/batch1/n_jobs3, CPU FP32, AMP/FA3/KV false, offload auto |
| 호출 | checkpoint/contextfit1회, predict_proba2시도/2완료, 계수학습0 |
| mock | mock_01, 0.532초, exit0, 소유트리 clear/잔존0 |
| 합성 실행 | pair_01, wrapper49.187초, child46.979초, exit0, stop_reason=null |
| RAM | wrapper 시작4.4418907166GiB, 관측최저3.9340019226GiB, sampled 소유트리 peak556965888bytes |
| 확률 | 양쪽2×4 float32, finite/[0,1], 행합최대오차1.1920928955e-7 |
| 동등성 | 최대절대차0, exact=true, tolerance1e-5통과, argmax [1,2] 일치 |
| 상태 | 입력/shuffle/실행관리자 설정불변, COL/ROW 원관리자복원true, ICL 관리자불변 |
| 종료 | 정상완료, owned_tree_remaining=[], owned_tree_status=clear; 강제종료 없음 |

두 예측의 컬럼 manager 호출 합계16회/청크320개가 완료됐다. 후보 ROW는8회 호출, 각 입력(1,34,316,128)→출력(1,34,512), 청크5개(8+8+8+8+2), 총40청크 완료다. feature/register sequence316과 embedding128을 보존했다. 전체 T ICL은 분할하지 않았으며 추가 독립 forward는 없다. ROW 출력값 자체를 별도 대조하는 hook은 추가하지 않았고 최종 확률과 원래 호출의 shape/청크 기록으로 검증했다.

현재 RAM 관측을 round007/008과 빼서 통제된 절감량으로 주장하지 않는다. 작은 입력에서의 전체 실행 sampled peak이며 실제3146문맥 peak나 OS 전체 최대수요의 상한이 아니다.

## 검토·예산·출처

관리자는 Astra high, 작성자·검토자는 각각 Luna xhigh로 요청했다. 실제 호스트 turn_context도 이 설정을 기록하며 manager/*evidence.json에 보존했다. 내부 모델 인증은 아니다. 인계 SHA와 수신세션ID가 round008 수락영수증에 일치했고 중복계산은 없었다.

독립 검토에서 unknown tensor/output dtype-device 검사, 실행직후 PID조회 실패 시 직접 생성한 Popen 핸들로 종료하는 경로, 식별불가 자손의 unverified 상태보존을 보강했다. 이 수정은 실행 전에 이루어졌다. 실패 mock/모델실행은 없었다. PLAN_AMENDMENT_01에 따라 pair 총상한300→180초(170+10)로 실행 전에 축소했다. mock 추가재시도0, pair재시도0이다.

승인manifest review/approved_sources.json은22개 소스해시를 고정한다. column bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded, row d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b, pair dcf056bb5772a1bd31b17194ed680655e427b9914ddef953eb7b291723213c19, wrapper b8e5d7de47ba070ed9df52badb1002f1955d67798e679e240e295a05ba87a439. logs에는실행사본/stdout/stderr/RAM곡선/PID와종료영수증을보존했다. source·mock·최종 독립 검토는 review/에 있다.

원자료/이전저장소/과거회차/venv를 수정하지 않았다. 실제 배열·실제확률·OUTER·holdout 읽기0, 공식제출·외부업로드·패키지설치0이다. 기준 개발OUTER5897 micro0.5930133966423605/macro0.5252719738966167 유지, 탐색0.5933525521451586 미채택, 독립·공식점수없음.

## 학습과 인계

기술목표인 소스 독립성·mock계약·합성확률 의미보존은 통과했다. 학습목표는 ROW 배치축과 ICL 문맥축, exact/tolerance, 합성과 실제재현/F1, 정상복원과 강제종료를 구분하는 것이다. LEARNING_NOTES.md에 설명질문을 남겼으며 학습자이해·하드웨어동작은 미측정이다.

최종 NEXT_SESSION.md는 성공분기의 실제재현1회 계획이다. 완료상태·ledger·NEXT를 저장한 후 automation/Start-NextSession.ps1 -FromRound round_009로 fresh Astra high에 인계하고 수락영수증을 확인한 뒤 현재 관리자는 종료한다. 영수증은 automation/receipts/round_009_launch.json에 저장된다. CLI에 structured-chat닫기명령이 없어 필요하면 완료세션 codex_f8781e21_ce60_45bc_b218_028699479bf4 탭만 수동으로 닫는다. 앱전체/무관세션은 닫지 않는다.
