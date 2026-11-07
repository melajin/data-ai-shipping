# Round 003 독립 검증 보고서 (Verification 2026-11-05)

## 1. 검증 범위 및 프로토콜 준수

- **대상 라운드**: `rounds/round_003` (TabICLv2 저장 확률 기반 의사결정 정책 R0 감사: `A_raw` vs `A_old` vs `A_micro_select`, development OUTER 5,897척 × 2 seeds `[42, 2026]`)
- **데이터 경계 준수**:
  - Holdout(1,475척) 개별 행 열람: **0건**
  - 전체 7,372척 `F156_train.csv` / `F156_test.csv` / `train_labels.csv` 열람: **0건**
  - `Test2025` 및 원시 궤적/특징 행 열람: **0건**
  - 신규 모델 적합(fit) 또는 추론(inference): **0회**
- **검증 스크립트 및 산출물 (`verification_20261105/`)**:
  1. `v1_integrity.py` → `v1_integrity.json`: 화이트리스트 20개 파일 SHA256, INNER 예측 파일 해시, 5,897척 ID/라벨/관측일/폴드 정합성 검증
  2. `v2_recompute.py` → `v2_recompute.json`, `v2_frames.npz`: INNER 배수 선택, OUTER 예측(`A_raw`, `A_old`, `A_micro_select`), 1,680개 지표 필드, 전이 행렬, `predictions.csv` 11,794행 독립 재계산
  3. `v3_bootstrap_gate.py` → `v3_bootstrap_gate.json`: 5,000회 쌍대 선박 부트스트랩(`seed=20261105` 재현 + `seed=777000777` 교차검증), 확률 품질(logloss, Brier, 10-bin ECE, 고신뢰 오류), 채택 게이트 검증
  4. `v4_idhash.py` → `v4_idhash.json`: `ROUND_REPORT.md` 한계 #1(`final_fixed_decision_rule.json`의 INNER/FIT ID 리스트 SHA256 미복원 건) 원인 규명 및 100% 복원
  5. `v5_split_and_scores.py` → `v5_split_and_scores.json`: `splits_original.json` ↔ `development_roles_long.csv` 분할 정합성, `oof_decisions.csv` 정규화 점수 표현(한계 #2), M4 체크포인트(`bdc7dbd5...`) 준비도 검증
  6. `v6_manifest.py` → `v6_manifest.json`: `completion_manifest.json`, `result.json` 참조 해시, 런처 스냅샷, 실행 PID 및 `STATUS.json`/`EXPERIMENT_LEDGER.csv` 정합성 검증

---

## 2. 핵심 검증 결과 요약

| 검증 항목 | 결과 | 세부 근거 |
|---|---|---|
| 화이트리스트 20개 입력 및 소스 SHA256 | **PASS** | `MANIFEST_SHA256.json` 및 `source_hash_manifest.json` 대비 20/20 정확히 일치 (`v1_integrity.json`) |
| 모집단·역할·확률 무결성 | **PASS** | Development 5,897척(fold `1966/1966/1965`), INNER 각 787척, 확률 유한성·범위·행합 오차 $\le 4.44\times 10^{-16}$ |
| INNER 배수 선택 (`A_micro_select`) | **PASS** | `seed 42: [1.0, 1.5, 1.0]`, `seed 2026: [1.0, 1.0, 1.0]` 독립 재계산 100% 일치 (`v2_recompute.json`) |
| OUTER 지표 (1,680개 필드) 및 전이 행렬 | **PASS** | 모든 스코프(`all`, `fold_0..2`, `days_1_7` 등 10개) × 3개 정책의 지표 최대 절대 오차 $2.22\times 10^{-16}$, 혼동행렬·전이행렬 불일치 0건 |
| `predictions.csv` (11,794행) | **PASS** | 5,897척 × 2 seeds 전 행 일치, SHA256 `34c84db1...` 일치 |
| 쌍대 부트스트랩 (5,000회, `seed=20261105`) | **PASS** | `paired_bootstrap_draws.npz` (450개 키) 전 셀 재현(micro diff `0.0`, macro diff `3.33e-16`), 별도 시드(`777000777`)에서도 결론 동일 (`v3_bootstrap_gate.json`) |
| 채택 게이트 (`selected_vs_raw_progress_gate`) | **PASS (기각 확인)** | 2-seed 평균 micro-F1 `0.593013 -> 0.593353` (`+0.000339 < +0.005`), seed 2026 변화 `0`, 95% CI `[-0.000933, +0.001611]` (0 포함) → **미채택(REJECT) 정당** |
| 확률 품질 (`logloss`, `Brier`, `ECE`) | **PASS** | Seed 42 (`logloss 0.892751`, `Brier 0.525724`, `ECE 0.036513`, $\ge 0.9$ 오류 77척), Seed 2026 (`logloss 0.892055`, `Brier 0.525343`, `ECE 0.035568`, $\ge 0.9$ 오류 71척) 정확히 일치 |
| M4 준비도 조사 (`m4_readiness/readiness.json`) | **PASS** | 체크포인트 `bdc7dbd5...` (110,368,038 bytes) 존재 및 로컬 환경 3종 내 `torch`/`tabicl` 미설치 사실 확인 (`v5_split_and_scores.json`) |

---

## 3. 한계 사항(Limitations) 심층 규명 및 추가 발견

### 3.1 `ROUND_REPORT.md` 한계 #1 해결: INNER/FIT ID 리스트 SHA256 100% 복원 (`v4_idhash.json`)
- **기존 보고**: `run_round003.py`는 CSV 행 순서 리스트에 `json.dumps(..., sort_keys=True)`를 적용하여 `final_fixed_decision_rule.json`의 `inner_ids_sha256`와 불일치하자 원본 정렬 순서를 알 수 없다고 기록함.
- **검증 결과**: `splits/splits_original.json`의 `inner_ids`(787개)와 `fit_ids`(`3144/3144/3145`개)를 **정수 오름차순 정렬 후 개행 문자(`\n`)로 결합**(`"\n".join(str(x) for x in sorted(map(int, ids)))`)하면 6개 seed/fold의 `inner_ids_sha256`와 `fit_ids_sha256`가 모두 100% 일치함을 확인:
  - Fold 0 INNER: `cb82568ec4fcedf20a5706d15db6a76f84f84a23b9273aa4b18948c3014ed0c3`
  - Fold 1 INNER: `c18b275a64434d25a3c111cadc2dc15483dc1a2e6980c500466cbce566bb89c2`
  - Fold 2 INNER: `524c88b188f67a50844d33c01c27f06a055f262f06492ceb3c02585155c33e59`
  - Fold 0 FIT: `f7ba0bc2850be60e8c8c5b6e8aa10be2942c66d4a8a5f0fa33262e101c112d84`
  - Fold 1 FIT: `7c1c1274e53844406e5f5d155f71c2294003dc4cccb7991944408f3051660bb9`
  - Fold 2 FIT: `4d7ff364c4518423ab00201f3ba887f8b0fd018723be7bb7f84e3efbf5c1b869`
  - `split_manifest_sha256`: `b99a81c740f7348be4fb2de67e2fb14155d6e7b31a752016c17471ffec589a0c` (`splits/splits_original.json` 바이트 해시와 일치)

### 3.2 `ROUND_REPORT.md` 한계 #2 확인: `oof_decisions.csv`의 `decision_score0..3` 정규화 (`v5_split_and_scores.json`)
- 공유된 `oof_decisions.csv`의 `decision_score0..3`는 $p_2$에 배수를 곱한 뒤 행합이 1이 되도록 정규화한 값(오차 $\le 6.66\times 10^{-16}$)인 반면, 아카이브된 `apply_frozen_decision.py`의 `scores_for`는 비정규화 점수를 반환함.
- 양수 상수배 차이므로 `argmax` 및 선택 클래스는 5,897척 전수에서 불변(불일치 0건)임을 확인.

### 3.3 매니페스트·프로세스 체인 점검 (`v6_manifest.json`)
1. **`decision_policy_frozen.json` 해시 방식**:
   - `result.json["policy_sha256"]` (`ee938b6ad2887e883ad5fd7a5b90982d3156d6e70460584b17708a03837c337a`)는 `run_round003.py:create_policy_artifact()`가 `"policy_sha256_before_hash_field"` 필드를 삽입하기 직전 `json_compact_bytes(policy)`로 계산한 정규화 사전 해시이며, 파일에서 해당 필드를 제거한 뒤 재계산하면 100% 일치함(디스크의 들여쓰기된 전체 파일 바이트 SHA256은 `06dac0581974c2856d3e29ccc5cf49555e543f4ee55215ba1dda5c54640aa289`).
2. **`completion_manifest.json` 대비 `STATUS.json` 해시 변경**:
   - `completion_manifest.json`의 나머지 5개 파일(`EXPERIMENT_LEDGER.csv`, `NEXT_SESSION.md`, `ROUND_REPORT.md`, `review/review.json`, `artifacts/result.json`)은 바이트 단위로 100% 일치함.
   - `STATUS.json`만 `baf7903e...` → `58e4e72e...`로 변경되었는데, 이는 Round 003 완료(16:45:24Z) 직후 후속 세션(Round 004, `updated_at_utc: 2026-11-04T16:48:33.3182088Z`)이 시작되면서 `"round_status": "round_004_in_progress"` 및 `"active_workers"`가 갱신되었기 때문이며, `STATUS.json["scores"]["round_003"]` 블록은 `result.json`과 100% 동일함.
3. **런처 영수증(`runner_pid: 440`) vs 런타임 로그(`pid: 19052`) 차이**:
   - `launch_round003.ps1`가 Windows 가상환경 스텁 실행 파일(`environments\round_002_catboost\Scripts\python.exe`)을 `Start-Process -PassThru`로 기동함에 따라, 파워쉘 영수증에는 스텁 리다이렉터 PID(`440`, preflight는 `10204`)가 기록되고 파이썬 내부 `os.getpid()`에는 실제 인터프리터 자식 프로세스 PID(`19052`, preflight는 `31748`)가 기록된 정상적인 Windows `venv` 동작임을 확인함.
