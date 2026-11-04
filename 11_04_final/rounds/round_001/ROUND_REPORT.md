# Round 001 — T5 읽기 정밀도와 기준선 재현 진단

상태: **조건부 완료(CONDITIONAL)**. 허용된 계산·ensemble 검산·독립 검토를 마쳤고 full dynamic 원배열 비교는 미측정으로 남겼다. 목표 micro-F1 0.7은 미달이며 이번 회차에서 새 모델을 학습하지 않았다. 현재 고정 기준선은 **3,497/5,897 = 0.5930133966423605**로 재현됐다.

## 결정과 이유

현재의 고정 X304 NPZ를 다음 실험의 입력 기준으로 유지한다. 기존 CSV를 기본 reader로 읽은 T5와 NPZ의 T5가 3fold 모두 정확히 일치했다. CSV `round_trip` reader로 바꾸는 것은 입력 값을 바꾸며, 작은 값 차이도 일부 모델 확률에 영향을 줬다. 더 정밀한 reader라는 이유만으로 기존 입력을 자동 교체하지 않는다. 독립 검토는 현재의 고정 개발 캐시를 사용하는 제한된 후보 비교를 진행할 수 있다고 판정했다.

원래 동적 T5 메모리 배열과 CSV의 완전한 직접 대조는 끝내지 못했다. 원 생성기를 다시 돌리면 7,372척 전체 Train 및 Test geometry를 읽고 기존 holdout의 개별 자료까지 읽는다. 또한 모듈 import에 source 저장소 경로를 만드는 부작용이 있다. 동일한 원 T5 공용 항구 집계·mask의 저장본은 조사 범위에서 찾지 못했다. 발견된 `work_008/train_harbors.json`은 Train-only 집계여서 원 T5의 Train+Test 집계와 바꿔 쓸 수 없다.

따라서 이번 완료 범위는 **개발자료의 CSV parser/재직렬화 비교·현재 저장모델 추론·환경 고정 진단**이다. 이를 동적 원배열 재현이나 옛 .59183 차이의 원인 확정으로 확대하지 않는다. 고정 입력의 현재 기준선 재현이 통과하면 옛 이력의 불확실성을 남긴 채 다음 새 모델 통제 비교로 진행할 수 있다.

## 조건·예상·계산값

- 입력: fold마다 개발 5,897척×304열, 그중 T5 10열. FIT/INNER/OUTER는 기존 명부와 동일하다. 클래스 순서와 T5 열 순서를 대조했다.
- 환경: Python3.13.3, NumPy2.2.5, pandas2.2.3, LightGBM4.7.0, Windows11. 추론 threads1. 모델은 기존 sqrt_macro 3fold×5seed=15개다.
- 예상: decimal→float reader 차이가 있을 수 있으나 크기와 예측 영향은 미확인이었다. 입력 tolerance 통과와 예측 불변은 서로 다른 검사다.
- 실제 실행: `execution/run_t5_csv_roundtrip.py`, 시작 PID1012, 주요 계산 33.48초. stdout/stderr와 시작 manifest, 환경·입력/소스 hash를 저장했다. 학습은 0개다.

| 계산 항목 | 결과 |
|---|---|
| NPZ T5 vs 기존 CSV 기본 parser | 3fold 모두 ID/열/NaN mask 일치; finite 값 bitwise 동일 |
| fold별 finite T5 값 | 53,060개, NaN 5,910개 |
| 기본 parser vs round_trip 변경 finite 값 | fold0 27,705개 / fold1 27,888개 / fold2 27,831개 |
| parser 차이 최대 절댓값 | 8.881784197001252e-16 |
| parser 차이 abs1e-12, abs1e-10 검사 | 3fold 모두 통과; bitwise 일치는 아님 |
| 읽은 값을 CSV로 재저장한 비교 | 기본→기본 및 round_trip→round_trip은 exact 일치; 교차 reader의 일부 조합은 기존 정밀도 차이를 유지 |
| 현재 15모델의 개발 전체 추론확률 최대 변화 | 0.004175363752329006 |
| 개별 15모델 OUTER argmax 변화 | 0 / 29,485 model-row instances(5×5,897) |

확률 변화 최대값은 개발 전체(FIT/INNER/OUTER) 추론 범위다. 29,485는 서로 다른 선박 수가 아니라 모델별 OUTER 행수의 합이다. 실제 독립 선박 분모는 개발 5,897척이다. 개별 모델 argmax가 같다는 사실만으로 5seed 평균의 argmax까지 같다고 결론내리지 않아 별도 검산을 추가했다.

추가 검산은 `execution/replay_ensemble.py`로 수행했고 계산시간19.23초, foreground 실행의 실제 종료코드0을 확보했다. 시작·종료의 실행기 SHA-256이 같았다.

| 추가 검산 항목 | 결과 |
|---|---|
| 기존 15개 seed별 저장 확률 vs 고정 NPZ 재추론 | OUTER 전 행 exact 일치, max abs0 |
| 다시 계산한 5seed 평균 vs 기존 저장 평균 확률 | max abs2.220446049250313e-16, 사전 tolerance1e-12 통과 |
| 기존 저장 평균 argmax vs 이번 재추론 | 5,897/5,897 일치 |
| 기본 입력 5seed 평균 micro / macro | 0.5930133966423605 / 0.5252719738966167 |
| round_trip 입력 5seed 평균 micro / macro | 0.5930133966423605 / 0.5252719738966167 |
| round_trip 입력의 OUTER 5seed 평균 확률 변화 | 최대0.0012018578769440735, 15척의 확률행 변화 |
| round_trip 입력의 OUTER 평균 argmax / gain / loss / net | 모두0 |

따라서 이번 reader 변경은 현재 고정모델의 개발 정답 수를 개선하지 않았다. 모든 확률이 같다는 결론은 아니다. 기존 6후보 평균의 탐색 최고0.5933525521451586은 이번에 재실행한 후보가 아니며, 순증2·macro하락·CI의0포함이라는 기존 제한과 함께 별도로 유지한다.

## 해석과 남는 불확실성

확인 사실은 고정 NPZ가 기존 기본 CSV reader의 T5를 담고 있고, parser 선택에 따른 수치 차이 및 일부 확률 차이가 실제로 계산됐다는 것이다. 입력 `allclose` 통과가 모델의 확률 동일성을 보증하지 않는다. 트리 경계에서의 분기 민감도는 가능한 설명이지만 이번에 개별 tree split을 추적해 확정한 것은 아니다.

현재 저장모델에 입력을 바꾼 추론 검사와, 그 입력으로 모델을 다시 학습했을 때의 변화는 별개다. 이번에는 재학습하지 않았으므로 parser 차이가 옛 S6 학습 결과 .59183과 현재 .593013의 차이를 만들었다거나 만들지 않았다고 단정할 수 없다. 원 동적 배열·정확한 원 aggregate/mask·옛 학습 모델/환경·일부 source snapshot 부재가 남는다.

현재 실험은 실제자료의 개발 계산 및 코드 검산이다. 하드웨어 실측, 새 독립 holdout 평가, 공식 점수, 실선 운용 검증이 아니다. 원자료 CSV를 전량 재해시·재파싱하지 않았고 기존 입력 감사 전체를 다시 수행했다고 하지 않는다. 나열한 입력·소스 파일에 대한 전후 hash 검사는 변경 0건이었다. 이 검사를 원본 디렉터리 전체 무변경 증명으로 확대하지 않는다.

실행 기록의 한계도 남겼다. 주실행은 detached process handle이 보존되지 않아 실제 종료코드가 unknown이다. 완료 JSON/stdout과 빈 stderr는 있지만 이를 exit0으로 바꾸지 않았다. 첫 보조실행도 종료코드unknown이며 fold2의 OUTER 개수를1966으로 잘못 가정한 assertion 오류가 stderr에 남았다. 실제 계약1966/1966/1965로 수정한 코드를 보존했고, 관리자 인수 후 foreground 보조실행에서 실제 exit0·출력·해시를 확보했다. 이 실패는 검증 harness의 분할 개수 가정 오류이며 원자료·학습모델·역할 명부를 바꾼 것이 아니다. 주실행 코드 hash는 사후 현재 파일의 hash로 표기하고 미기록 launch-time snapshot이라고 주장하지 않는다.

## 다음 회차와 학습 질문

다음은 같은 fold FIT로 다른 모델 확률을 새로 확보하는 bounded 비교다. CatBoost의 기존 환경을 확인하고 필요하면 작업루트에 격리 설치하며, 설치 실패 시 사전 지정한 ExtraTrees로 진행한다. 현재 active Python 환경의 패키지 부재와 모든 머신 환경 부재를 구별한다. TabICL은 조사한 경로에서 runtime/checkpoint가 없고 S4는 기존 OOF oracle 결합이므로 이번 즉시 실행 후보가 아니다.

새 회차는 INNER_ES와 INNER_SELECT를 사전 분리하고 기준선도 새 ES에 맞춰 다시 학습한다. 기존 모델의 전체 INNER 사용 이력을 무시한 채 일부를 SELECT라고 이름만 바꾸지 않는다. 다음 실행 예산은 기준선3+후보3 최대6fits, 계산30분이다. 구체적 입력·경로·조건·실패 분기는 루트 NEXT_SESSION.md에 저장했다.

학습자가 직접 설명할 질문:

1. 입력 차이가 1e-15보다 작아도 예측 확률이 더 크게 바뀔 수 있다는 결과를 어떻게 해석하는가?
2. “확률이 바뀌었다”, “argmax가 바뀌었다”, “정답 수가 바뀌었다”는 어떤 차이가 있는가?
3. 현재 저장모델 추론 검사가 과거 재학습의 점수 차이를 완전히 설명하지 못하는 이유는 무엇인가?
4. 어떤 자료가 더 있어야 원 동적 T5와 CSV의 직접 일치를 입증할 수 있는가?

문서·코드·계산 완료와 사용자의 설명 역량 달성은 별개이며, 학습자의 답변은 아직 확인하지 않았다.

## 근거

- `execution/result.json`, `environment.json`, `launch_manifest.json`, `stdout.log`, `stderr.log`, `run_t5_csv_roundtrip.py`
- `execution/supplemental_ensemble.json`, `supplemental_attempt2_launch_manifest.json`, `supplemental_attempt2_stdout.log`, `supplemental_attempt2_stderr.log`, `replay_ensemble.py`; 실패 원문은 `failed_attempts/replay_ensemble_attempt1.py` 및 `supplemental_stderr.log`
- 독립 최종 원본 `review/review.json`, 사전 검토 `review/preliminary_review.md`, 관리자 수신·해석 기록 `REVIEW_RECEIPT.md`. `review/review.md`는 최종 JSON과 같은 내용으로 보존돼 있다.
- `ROUND_PLAN.md`, `MANAGER_RECORD.md`, 루트 CYCLE_PROTOCOL/STATUS/LEDGER/NEXT_SESSION
- 원 보고: `D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/reports/final_report.md`
