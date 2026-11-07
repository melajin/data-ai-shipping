# Round 027 (독립 트랙) — 「자망·통발·채낚기 특화 검출 + 그 외 연안복합(Fallback)」 가설 검토 및 실행 계획서

- **작성 시각**: 2026-11-05T14:26+09:00
- **전용 격리 폴더**: `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_027_fallback_ovr`
- **세션 운영 방식**:
  - **총괄 구성 및 지시 (Parent Session)**: **Gemini 4 Argon High (`gemini-4-argon-high`, effort `high`)**
  - **실행 및 병렬 실험 워커 (Subagent Workers)**: **Gemini 3.8 Flash High (`invoke_subagent` with `Model="flash"`)**
  - **격리 원칙**: 현재 별도 세션에서 마무리 중인 `round_026`을 일체 방해하지 않도록, 모든 코드·확률·보고서를 `rounds/round_027_fallback_ovr` 내부에만 저장한다 (`round_026`의 이미 완료된 `track1_spatial_knn/probabilities_track1.npz`, `track2_s2_segments/probabilities_track2.npz`, `track3_ensemble/probabilities_track3.npz`는 **읽기 전용**으로만 참조 가능).

---

## 1. 사용자 제안 가설에 대한 기술적·물리적 타당성 검토

### 1.1 핵심 가설
> **기존 방식 (4-클래스 대등 분류)**:  
> "~면 연안복합(0), ~면 자망(1), ~면 통발(2), ~면 채낚기(3)" (4개 클래스를 동등한 배타적 원형으로 가정)  
> **제안 방식 (3개 전문 어구 특화 검출 + 나머지 연안복합 Fallback)**:  
> **"확실히 자망이면 자망(1), 확실히 통발이면 통발(2), 확실히 채낚기면 채낚기(3), 그 이외(애매하거나 복합적인 패턴)는 모두 분포 수가 가장 많은 연안복합(0, 49.5%)으로 정의하여 판정"**

### 1.2 왜 이 가설이 본 데이터셋의 핵심 병목을 정조준하는가? (3가지 수학적·도메인 근거)

1. **도메인적 실체 (연안복합은 '단일 어구'가 아니라 '복합·여집합 면허')**:
   - `자망(Class 1, 34.2%)`, `통발(Class 2, 14.2%)`, `채낚기연승낚시(Class 3, 2.1%)`는 어구 투망·양망 메커니즘과 조업 수역·시간대가 뚜렷한 **단일 전문 어구**다.
   - 반면 `연안복합(Class 0, 49.5% = 2,920/5,897척)`은 계절·어기에 따라 여러 어구를 혼용하거나 단일 어구 기준에 전형적으로 속하지 않는 선박들의 집합이다.
   - 따라서 연안복합을 하나의 "양성 특징 원형(Positive Prototype)"으로 정의해 학습시키면 클래스 내부 분산이 너무 커서 결정 경계가 흐려진다. 반대로 **자망·통발·채낚기 3개 전문 어구의 고유 조건(Positive Signature)을 먼저 정의하고, 세 조건을 모두 충분한 확신도로 통과하지 못하는 선박을 연안복합(Fallback)으로 귀속**시키는 것이 물리적 정의와 정확히 일치한다.

2. **오분류 행렬(Confusion Matrix) 실측 근거**:
   - 기존 기준선(`LightGBM seed42`, 3,476척 정답)의 혼동행렬을 보면:
     - 실제 `연안복합(2,920척)` 중 **464척이 자망으로, 58척이 통발로, 9척이 채낚기로(합계 531척)** 잘못 빠져나가고 있다 (`False Positive` 유출).
     - 특히 `sqrt_macro` 가중치나 세그먼트 특징(`S2`)을 넣으면, 비조업 대기일이나 애매한 항적을 가진 연안복합 선박들이 자망(`609척`)이나 통발(`92척`)로 대거 오분류되면서 전체 `micro-F1`을 깎아먹었다.
   - 만약 **자망·통발·채낚기 판정에 엄격한 확신도/전문가 임계치($\tau_1, \tau_2, \tau_3$ 및 마진 조건)를 부여하고 미달 시 전부 연안복합(Class 0)으로 회수(Fallback)**하면, 이 531척의 연안복합 유출 중 상당수를 즉시 정답으로 되찾아올 수 있다!

3. **학습 단계(Training Objective)에서의 이점 — 2단계 분해 가능**:
   - **결정 규칙 수준 (Decision-Level Fallback)**:
     - 다중모델 결합 확률 $P(c \mid x)$에서 단순 $\arg\max_{c \in \{0,1,2,3\}} P(c \mid x)$를 쓰지 않고:
       1. **Specialist Gate**: $c \in \{1, 2, 3\}$ 중 $P(c \mid x) \ge \tau_c$ 이고 $P(c \mid x) - P(0 \mid x) \ge \delta_c$ 인 후보들만 전문 어구 후보집합 $S(x)$에 진입.
       2. **Specialist Competition**: $S(x) \neq \emptyset$ 이면 $\arg\max_{c \in S(x)} \frac{P(c \mid x)}{\tau_c}$ 로 자망/통발/채낚기 결정.
       3. **Default Fallback**: $S(x) = \emptyset$ 이면 **무조건 `연안복합(Class 0)`** 으로 결정!
   - **모델 학습 수준 (Model-Level One-vs-Rest + 3-Class Specialist)**:
     - 기존 4-클래스 Softmax 트리는 노드 분할 시 연안복합(49.5%)의 불순도를 줄이는 데 대부분의 가지를 소모한다.
     - 이를 분리하여:
       - **(A) 3개의 전담 이진 검출기 (One-vs-Rest Binary Specialists)**:
         - $M_1$: `자망(1) vs 나머지(0,2,3)` 이진 분류기 (자망 고유 특징·공간 이웃 집중 학습)
         - $M_2$: `통발(2) vs 나머지(0,1,3)` 이진 분류기 (통발 고유 특징·공간 이웃 집중 학습)
         - $M_3$: `채낚기(3) vs 나머지(0,1,2)` 이진 분류기 (채낚기 야간·집어·특정 해역 집중 학습)
       - **(B) 전문 어구 전용 3-클래스 분류기 (Specialist 3-Class Model)**:
         - 오직 `자망(1), 통발(2), 채낚기(3)` 선박(`FIT` 중 약 1,580척)만으로 학습하여, 연안복합 노이즈의 방해 없이 **자망 vs 통발 vs 채낚기 간의 순수 경계**만 날카롭게 학습하는 모델 $M_{123}$!
       - **(C) 비전문 어구(연안복합) 이탈 판별**:
         - $M_1, M_2, M_3$의 이진 확률 및 $M_{123}$의 엔트로피/최대확률이 임계치에 미달하면 **연안복합(Class 0)** 으로 Fallback!

---

## 2. 병렬 작업 아키텍처 (Argon High 지시 → 3.8 Flash High 병렬 실행)

메모리 제약(현재 가용 RAM ~1.8~2.0 GiB, 프로세스당 RSS < 400 MB, `n_jobs=1`)과 파일 격리를 엄격히 지키면서, **Argon High 관리자**가 다음 **3개의 Gemini 3.8 Flash (`Model="flash"`) 서브에이전트**에 병렬로 작업을 위임한다:

### Worker A (`subagent_ovr_specialists` — Gemini 3.8 Flash)
- **작업 폴더**: `rounds/round_027_fallback_ovr/worker_a_ovr_models`
- **임무**: **학습 단계의 One-vs-Rest 이진 전문 검출기($M_1, M_2, M_3$) + 순수 3-클래스 전문어구 분류기($M_{123}$) 구축 및 평가**
  1. 3개 Fold (`fold_0, fold_1, fold_2`)의 304 기본 특징(누수 없는 T5 재구축 포함) + Track 1의 다중해상도 Hellinger kNN 특징(22열, 총 326열)을 입력으로 사용.
  2. 각 Fold의 `FIT`에서:
     - `M1_jamang_ovr`: `y == 1` 이진 LightGBM
     - `M2_tongbal_ovr`: `y == 2` 이진 LightGBM
     - `M3_chaenakgi_ovr`: `y == 3` 이진 LightGBM
     - `M123_specialist`: `y in {1, 2, 3}` 인 FIT 선박만으로 학습한 3-클래스 LightGBM (연안복합 완전 배제 상태에서 자망/통발/채낚기 구분 극대화)
  3. 각 Fold의 `INNER (787척)` 및 `OUTER (1,966척)`에 대해 위 4개 전문 모델의 예측 확률을 추출하여 `worker_a_probabilities.npz`에 저장하고, `INNER`에서 튜닝한 Fallback 임계치 규칙으로 단독 및 기존 모델 결합 성능을 검증.

### Worker B (`subagent_fallback_decision` — Gemini 3.8 Flash)
- **작업 폴더**: `rounds/round_027_fallback_ovr/worker_b_fallback_rules`
- **임무**: **다중모델(`LightGBM 5-seed + TabICLv2 + CatBoost + Hellinger kNN + S2`) 위에서의 계층적 Fallback 결정 규칙(Hierarchical Specialist-or-Fallback Rule) 최적화**
  1. 기존 디스크에 저장된 모든 모델 확률(`LGBM 5-seed`, `TabICLv2 seed42/seed2026`, `CatBoost`, `Track 1 Hellinger kNN`, `Track 2 S2`)을 로드.
  2. **4-클래스 대등 $\arg\max$ vs 제안된 Specialist-then-Fallback 규칙**을 `INNER 3-Fold OOF CV (2,361척)`에서 정밀 비교:
     - **규칙 1 (Threshold + Margin Fallback)**:
       - 채낚기 조건: $P(3) \ge \tau_3$ 및 $P(3) - P(0) \ge m_3 \implies 3$
       - 통발 조건: $P(2) \ge \tau_2$ 및 $P(2) - P(0) \ge m_2$ 및 $P(2) \ge \gamma_{21} P(1) \implies 2$
       - 자망 조건: $P(1) \ge \tau_1$ 및 $P(1) - P(0) \ge m_1 \implies 1$
       - **그 외 모든 선박 (Fallback)**: **무조건 `연안복합(0)`**!
     - **규칙 2 (Specialist Precision Gate + Unanimous/Consensus Fallback)**:
       - 다중 모델(Tree + TabICL + Spatial kNN) 중 전문 어구(1, 2, 3)에 대해 최소 2개 이상의 모델 패밀리가 동시에 확신하거나 결합 확신도가 임계치를 넘을 때만 전문 어구로 인정하고, 의견이 갈리는(불확실성/엔트로피가 높은) 선박은 전부 `연안복합(0)`으로 Fallback!
  3. 보호 제약(`TP0 >= 2,389`, `TP3 >= 92`) 하에서 `INNER` OOF 최적 파라미터를 찾고 `OUTER 5,897척`에 적용하여 정량 성적표 산출.

### Worker C (`subagent_integration_report` — Gemini 3.8 Flash)
- **작업 폴더**: `rounds/round_027_fallback_ovr/worker_c_synthesis`
- **임무**: Worker A의 신규 전문 어구 검출 확률(`M1, M2, M3, M123`)과 Worker B의 다중모델 Fallback 규칙을 결합하여 최종 성능을 검증하고, `rounds/round_027_fallback_ovr/ROUND_027_FALLBACK_REPORT.md` 종합 보고서를 작성.
