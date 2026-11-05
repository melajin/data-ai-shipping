# Round024 인계 — 사용자 지시 기반 저메모리 순차 S1 선행 비교 복구

최종 재확인 2026-11-05T02:52:34.363497+00:00: RAM 2.311GiB / 필요 1.5GiB (`allowed=true`, `other_python_jobs=0`).
사용자 명시 지시(2026-11-05 11:42 KST): **“시간이 조금 걸려도 메모리 조금씩 써서 작업하는걸로 해 나 딴것도 해야함...”**

직전 결과: `rounds/round_023/ROUND_REPORT.md`. Round023은 준비캐시와 승인 소스를 재사용하여 1회 실행했으나 기존 `2.5GiB` 단계 가드(`2.465GiB < 2.5GiB`)에서 25.10초 만에 중단됐다. **0/8fit, 새 점수·관문 모두 미판정**이다. 이전 022의 2fit을 보존한다. 성능 실패로 기각하지 않고 S2로 건너뛰지 않는다.

사용자의 명시적 저메모리·백그라운드 병행 지시에 따라, 이전 `round_023`이 설정했던 과도한 `4.5GiB` 진입 / `2.5GiB` 단계별 가용 RAM 기준을 폐기하고 **단계별 메모리 즉시 해제(`del` + `gc.collect()`)·단일 스레드(`threads=1`, `n_jobs=1`)·낮은 프로세스 우선순위(`BELOW_NORMAL_PRIORITY_CLASS`)** 기반의 저메모리 순차 실행 계약(`rounds/round_023/manager/next_resource_contract.json`)으로 전환했다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/automation/Start-NextSession.ps1' -FromRound 'round_023'
```

수락 영수증은 `automation/receipts/round_023_launch.json`이다. `accepted=true`인 영수증이 이미 있으면 다시 launch하지 않고 해당 owner를 확인한다. 새 관리자는 기존 receipt/session/claim/livePython 중복과 `round_024` 존재부터 확인한다. `round_024`가 이미 있으면 setup을 다시 실행하지 않는다.

## 시작 조건과 저메모리 setup

새 회차 입장·launch 가용 RAM >= **1.5GiB**, 각 단계 가용 RAM >= **1.0GiB**, 작업 예상 peak <= **0.5GiB**(강제 RSS 상한 **0.75GiB**, 시스템 비상 중단 하한 **0.5GiB**). 동시 큰 계산 0 상태에서 시작하며 학습은 동시 1 / `threads=1` (`n_jobs=1`) / `BELOW_NORMAL_PRIORITY_CLASS`다. 사용자의 다른 프로세스는 절대 종료하지 않는다.

관리자는 Luna xhigh 작성 담당과 별도 검토 담당을 둔다(호스트 총 4슬롯 우선). 요청 model/effort와 host turn_context를 분리 기록한다.

루트를 작업 디렉터리로 설정 후:

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_023/manager/prepare_round024.py
```

`prepare_round024.py`는 먼저 `1.5GiB` 가용 RAM과 다른 Python 작업을 검사하고, 통과하면 `round_023`의 승인된 소스·캐시 해시를 검산한 뒤 `rounds/round_024`로 복사하고 아래 **사용자 지시 기반 저메모리 순차 패치**를 적용한다(수학적 특징 정의·분할·하이퍼파라미터·판정 기준 변경 0, 원자료 재스캔 0):
1. `configs/experiment.json`: `threads=1`, `lgbm.n_jobs=1`로 설정하여 CPU 및 스레드별 히스토그램 버퍼 사용량 최소화.
2. `code/t5_rebuild.py`: 중복 검사용 56.7만 건 `seen` 집합을 루프 직후 즉시 `del seen`으로 해제.
3. `code/s1_features.py`: 각 기간(`month 0..6`) 계산 직후 `del period_profiles, counts_by_res` 및 `gc.collect()` 호출.
4. `code/run_gate.py`: 4개 CV fold의 `t5_matrix`(`4×3144×10`, 약 1MB)만 먼저 계산한 뒤 약 100MB 규모의 `rebuild_t5` 클로저를 `del rebuild_t5; gc.collect()`로 즉시 해제하고, 이후 S1 특징 생성 및 각 단일 모델(`baseline`, `candidate`) 학습 직후마다 `del model, proba, pred; gc.collect()` 수행. 단계별 가용 RAM 검사는 `1.0GiB`(예상 peak `0.5GiB`).
5. `manager/launch.py` & `manager/runtime_contract.json`: `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`, `BELOW_NORMAL_PRIORITY_CLASS`, 진입 가용 RAM `1.5GiB`, 작업 RSS 상한 `0.75GiB`, 시스템 비상 가용 하한 `0.5GiB`.
6. `review/verify_gate_result.py`: `round_022/` 접두사 하드코딩을 `f"{round_dir.name}/"`로 수정하여 `round_024` 승인 소스 해시를 직접 대조.
7. `review/reinfer_saved.py`: 8개 저장 모델을 1개씩 순차 로드·재추론(`del model; gc.collect()`)하여 저장 확률(절대오차 `1e-7` 이하)·argmax·클래스 순서·모델 해시를 검산하는 스크립트 포함.

새 Luna 검토 담당이 복사본과 저메모리 순차 패치 내용(`copied_inputs.json` 기록 포함), `ROUND_PLAN.md`, `runtime_contract.json`, `verify_gate_result.py`, `reinfer_saved.py`를 검토하고 **새 `round_024` 경로/hash로** `rounds/round_024/review/gate_approved_sources.json`을 작성한다. 작성자와 검토자 파일 소유 분리, 다른 사람 변경 되돌리기 금지. 다음 단계는 이전 명령의 성공을 확인한 별도 호출로 진행한다.

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_024/manager/freeze_stage.py --stage s1_gate --approval rounds/round_024/review/gate_approved_sources.json
```

동결 성공 확인 뒤:

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_024/manager/launch.py --stage s1_gate --seconds 900 --python 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' --script rounds/round_024/code/run_gate.py -- --run-gate
```

## 유한 범위·완료와 실패 분기

동일 3144 FIT / 4CV / seed42 / 304열 vs 328열, 8fit 단 1회, 튜닝 0 / 재시도 0 / full 3fold 0 / S2 훈련 0. 지도 T5와 S1은 각 CV train 라벨로 다시 계산하고 query 자기 라벨을 counts/global prior/fallback에서 제외한다. 선행 AND 관문은 `후보 >= 1833/3144`와 `후보 − 엄밀동일절차기준 >= 16`. 고정 1817 참고와 엄밀 기준을 별도로 보고한다. 특징은 centroid/record-time proxy이며 실제 체류시간/원래 모든 geometry 점유가 아니다.

정상 종료 8fit와 `gate_result.json`이 존재할 때만 순차 검산을 실행한다(가용 RAM >= 1.0GiB 확인):

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_024/review/verify_gate_result.py rounds/round_024/artifacts/gate
```

이어서 검토 담당이 `review/reinfer_saved.py`를 실행하여 8개 모델 순차 재추론(`max_abs_proba_diff <= 1e-7` 및 argmax 일치)을 검증하고 `rounds/round_024/review/saved_output_verification.json`에 결과를 남긴다:

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_024/review/reinfer_saved.py rounds/round_024/artifacts/gate
```

두 검산이 모두 pass한 후에만 setup이 복사한 보완 도구를 실행한다:

```powershell
& 'D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final/environments/round_002_catboost/Scripts/python.exe' -B -X utf8 rounds/round_024/code_author/supplement_metrics.py rounds/round_024/artifacts/gate
```

paired gain/loss/net, 5000 bootstrap(seed 20261105), 관측일 구간, class 1/2 precision/F1/FP 전이와 class 0/3 손익을 보고한다.

실패 시 부분 산출과 정확한 fit 수를 보존하며 같은 명령을 무작정 다시 실행하지 않는다. 숫자 관문 통과 시 다음 회차의 제한된 S1 확장(저메모리 순차 방식 유지)을 계획하고, 미달 시 승인 로드맵 S2의 누출 없는 선박-일 준비/중첩 교차적합 계약(역시 청크·순차·저메모리 방식)으로 이동한다.

완료 시 `ROUND_REPORT.md`, `STATUS.json`, `EXPERIMENT_LEDGER.csv`, `NEXT_SESSION.md` 갱신; `current_round`는 완료 `round_024`, `handoff.ready=true`. 다음 실행이 가능하면 `Start-NextSession.ps1`로 fresh Astra high 수락 영수증 확인 후 종료한다.
