# Round 026 Track 2 최종 결과 보고서: S2 선박-일 세그먼트 수준 분포 특징 및 Out-of-Fold Cross-Fitting

**작성일시**: 2026-11-05  
**담당 에이전트**: Track 2 전담 에이전트 (S2 Segment Cross-Fitting)  
**작업 디렉터리**: `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments`  
**평가 상태**: 완료 (Phase 1 FIT 4-CV 게이트 및 Phase 2 Full 3-Fold OUTER 5,897척 전수 검증)

---

## 1. 핵심 요약 및 게이트 판정 (Executive Summary)

- **S2 가설 검증 결과**: **[게이트 기각 / 단독 채택 불가]**
  - **Phase 1 (FIT 3,144척 내부 4-CV 진단 게이트)**:
    - Standard Multiclass: 기준 1,826 / 3,144 (0.5808) → 후보 1,817 / 3,144 (0.5779) (**순증 -9척**, micro -0.0029)
    - SqrtMacro Multiclass: 기준 1,830 / 3,144 (0.5821) → 후보 1,819 / 3,144 (0.5786) (**순증 -11척**, micro -0.0035)
    - **판정: 게이트 기준(+16척 / +0.5%p) 미달로 전면 기각**
  - **Phase 2 (전체 3-Fold OUTER 5,897척 전수 검증)**:
    - Standard Multiclass: 기준 3,404 / 5,897 (0.5772) → 후보 3,384 / 5,897 (0.5739) (**순증 -20척**)
    - SqrtMacro Multiclass: 기준 3,403 / 5,897 (0.5771) → 후보 3,371 / 5,897 (0.5716) (**순증 -32척**)
    - 역사적 고정 기준선 (`LightGBM_sqrt_macro seed42` 3,476척) 대비: **-105척**
    - 보호 게이트: Class 0 TP 2,216 (< 2,389 기준 미달), Class 3 TP 77 (< 90 기준 미달) → **보호 실패**
- **주요 발견**:
  - 통발(Class 2) 재현율은 **134척 → 144척(+10척)** 으로 개선되었으나, 연안복합(Class 0, -19척) 및 자망(Class 1, -20척)이 통발로 오분류되는 False Positive가 156척에서 191척으로 +35척 급증하여 전체 micro-F1을 잠식함.

---

## 2. 자료 스키마 및 S2 특징 추출 명세 (Data Schema & Features)

### 2.1 원천 입력 및 필터링 계약
- 입력 원천: `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\26_11_2\work\재식별_투트랙_001r1\s3_hourly.parquet` (144 MB)
- 필터 조건: `year == 2026` 및 개발셋 5,897척 로스터 일치 행 (`id.isin(dev_ids)`)
- 로드 결과: 개발 5,897척 전수 100% 매칭, 3,126,507개 시간 단위 항적 행 (결측 좌표 2행 제거)
- 산출 아티팩트: `vessel_day_segments.parquet` (19.2 MB, 319,808개 선박-일 세그먼트, 척당 평균 54.23일)

### 2.2 선박-일 세그먼트 특징 (27열)
1. **활동량**: `n_active_hours`, `sum_n_points`, `stationary_ratio`, `max_gap_hours` (4열)
2. **시간대 분포**: `ratio_night` (00~05시), `ratio_morning` (06~11시), `ratio_afternoon` (12~17시), `ratio_evening` (18~23시), `mean_sin_hour`, `mean_cos_hour` (6열)
3. **공간 및 이동**: `mean_lon`, `mean_lat`, `span_lon`, `span_lat`, `bbox_diag_km`, `daily_dist_sum_km`, `daily_dist_mean_km`, `daily_dist_max_km` (8열)
4. **모항 및 격자 집중도**: 선박별 최빈 정지 격자 기반 `dist_from_home_mean_km`, `dist_from_home_max_km`, `n_unique_cells_001`, `top_cell_ratio`, `dom_cell_005` (5열)
5. **계절 및 메타**: `month`, `y_vessel` (선박 라벨 약지도), `id`, `date` (4열)

### 2.3 집계된 선박 수준 S2 분포 특징 (31열)
- **세그먼트 사후확률 분포 (20열)**:
  - 클래스 `c=0..3`별: `p_mean_{c}`, `p_std_{c}`, `p_median_{c}`, `p_p90_{c}`, `argmax_ratio_{c}`
- **예측 다양성 및 불확실성 (5열)**:
  - `mean_entropy`, `unique_pred_classes_count`, `mean_top_margin`, `top1_class_ratio`, `top2_class_ratio`
- **일간 행동 변동성 (6열)**:
  - `std_night_ratio`, `std_daily_dist`, `p90_daily_dist`, `std_dist_from_home`, `p90_dist_from_home`, `grid_transition_rate`

---

## 3. 누수 방지 설계 및 교차적합 아키텍처 (Leak Prevention Architecture)

```
[Fold FIT 3,144척]
       │
       ▼ StratifiedGroupKFold (n_splits=5, vessel_id 기준 완전 분리)
 ┌─────────────────────────────────────────────────────────┐
 │ Fold k 학습: 나머지 4개 fold의 세그먼트 학습               │
 │   - dom_cell_005 공간 사전확률 Laplace smoothing (alpha=5) │
 │   - LightGBM (200 trees, lr=0.05, num_leaves=31)       │
 └─────────────────────────────────────────────────────────┘
       │
       ▼ Fold k 선박의 세그먼트 확률 out-of-fold 예측
 [FIT 3,144척의 완전 누수 없는 OOF 확률 테이블 (p_seg 4열)]
       │
       ▼ 선박별 31열 분포 통계 집계
 [FIT 3,144척 S2 특징 행렬 (3,144 x 31)]

[INNER / OUTER 검증 선박]
       │
       ▼ FIT 5개 세그먼트 모델 앙상블 평균 예측
 [INNER/OUTER S2 특징 행렬 (2,753 x 31)]
```

- **누수 방지 검증 증명**:
  - Phase 1 FIT 4-CV 내부에서도 각 CV fold의 학습 분할 선박(2,358척)만으로 5분할 세그먼트 모델을 다시 학습하고 검증 분할 선박(786척)을 예측함으로써, 전체 FIT 라벨이 검증 분할로 단 1비트도 새어 들어가지 않도록 통제함.
  - 세그먼트 모델의 FIT OOF 정확도는 51.0% ~ 53.6% 수준으로 안정적으로 형성됨.

---

## 4. 자원 사용 및 메모리 프로파일 (Resource & Memory Profile)

| 단계 | 시작 시각 (UTC) | 가용 RAM | 프로세스 RSS | 허용 여부 | 비고 |
|---|---|---|---|---|---|
| initial_test | 2026-11-05 04:52:11 | 2,222.8 MB | ~50 MB | Allowed | 정상 |
| extract_segments | 2026-11-05 04:52:54 | 1,987.8 MB | ~180 MB | Allowed | 4.72초 소요 |
| phase1_gate_4cv | 2026-11-05 04:57:08 | 2,074.7 MB | ~290 MB | Allowed | 4-CV 완료 |
| phase2_full_3fold | 2026-11-05 05:07:34 | 2,050.2 MB | ~310 MB | Allowed | 3-Fold 완료 |
| finished | 2026-11-05 05:17:41 | 2,042.8 MB | ~110 MB | Allowed | 전체 1,234.9초 |

- 모든 연산은 `n_jobs=1`, `float32`, 명시적 `del` 및 `gc.collect()`를 적용하여 가용 RAM 1.0 GiB 임계치를 상시 1.0 GiB 이상 여유 있게 상회함 (최저 가용 RAM: 1,987 MB). 타 프로세스 종료 없이 무충돌 완료.

---

## 5. Phase 1: Fold 0 FIT (3,144척) 4-CV 게이트 평가 결과

### 5.1 종합 성적표
| 모델 변형 | 정답 수 (3,144척) | Micro-F1 | Macro-F1 | 기준선 대비 증감 | 게이트 판정 |
|---|---|---|---|---|---|
| 304열 Baseline (Standard) | 1,826 | 0.580789 | 0.498727 | 기준 | - |
| **304+S2 Candidate (Standard)** | **1,817** | **0.577926** | **0.501119** | **-9척 (-0.29%p)** | **기각** |
| 304열 Baseline (SqrtMacro) | 1,830 | 0.582061 | 0.508987 | 기준 | - |
| **304+S2 Candidate (SqrtMacro)** | **1,819** | **0.578562** | **0.508937** | **-11척 (-0.35%p)** | **기각** |

### 5.2 4-CV 분할별 상세 (Candidate Standard vs Baseline)
- CV Fold 0: 456 → 446 (-10척)
- CV Fold 1: 455 → 453 (-2척)
- CV Fold 2: 467 → 470 (+3척)
- CV Fold 3: 448 → 448 (0척)
- **합계**: 1,826 → 1,817 (-9척)

---

## 6. Phase 2: Full 3-Fold OUTER (5,897척) 전수 검증 결과

### 6.1 전체 5,897척 OUTER 성적표
| 평가 지표 | 기준선 Standard | **후보 Standard** | 기준선 SqrtMacro | **후보 SqrtMacro** | 역사적 기준선 (seed42) |
|---|---|---|---|---|---|
| **정답 수 (척)** | 3,404 | **3,384** | 3,403 | **3,371** | **3,476** |
| **Micro-F1** | 0.577243 | **0.573851** | 0.577073 | **0.571647** | **0.589452** |
| **Macro-F1** | 0.509288 | **0.511455** | 0.522909 | **0.521951** | **0.525272** |
| Class 0 TP (연안복합) | 2,302 | **2,276** | 2,235 | **2,216** | 2,389 |
| Class 1 TP (자망) | 918 | **917** | 954 | **934** | 889 |
| Class 2 TP (통발) | 109 | **117** | 134 | **144** | 108 |
| Class 3 TP (채낚기) | 75 | **74** | 80 | **77** | 90 |

### 6.2 클래스 보호 게이트 판정
- **Class 0 보호**: 2,216 < 2,389 (**-173척 부족, 실패**)
- **Class 3 보호**: 77 < 90 (**-13척 부족, 실패**)
- **판정 결론**: S2 세그먼트 특징은 micro-F1 및 클래스 보호 조건을 모두 충족하지 못함.

---

## 7. 혼동행렬 변화 및 오차 전이 심층 분석 (Confusion Analysis)

### 7.1 OUTER 5,897척 SqrtMacro 혼동행렬 대조
#### 기준선 혼동행렬 (3,403척 정답)
```
[실제 \ 예측]    0 (연안복합)  1 (자망)  2 (통발)  3 (채낚기)  Support
0 (연안복합)        2,235       609        69         7      2,920
1 (자망)              966       954        78        18      2,016
2 (통발)              476       220       134         5        835
3 (채낚기)             17        20         9        80        126
```

#### S2 후보 혼동행렬 (3,371척 정답)
```
[실제 \ 예측]    0 (연안복합)  1 (자망)  2 (통발)  3 (채낚기)  Support
0 (연안복합)        2,216       607        92         5      2,920
1 (자망)              978       934        91        13      2,016
2 (통발)              461       224       144         6        835
3 (채낚기)             16        25         8        77        126
```

### 7.2 왜 통발 TP가 올랐는데 전체 micro는 하락했는가?
1. **통발(Class 2) 신호 포착**:
   - 일별 세그먼트 모델 도입으로 통발 TP가 134 → 144척으로 10척 증가하고, 재현율이 16.0%에서 17.2%로 향상됨.
2. **연안복합 및 자망의 역방향 오염 (False Positive 폭증)**:
   - 연안복합(Class 0)이 통발로 잘못 분류된 선박: 69척 → 92척 (**+23척 증가**)
   - 자망(Class 1)이 통발로 잘못 분류된 선박: 78척 → 91척 (**+13척 증가**)
   - 통발 전체 False Positive는 156척에서 191척으로 무려 **+35척 급증**함.
3. **근본적 원인 (약지도 라벨의 한계)**:
   - 연안복합 선박도 비조업일이나 정지 대기 중인 날에는 통발과 유사한 패턴(저속, 고정 정지)을 보이며, 세그먼트 분류기는 이 날들을 통발 확률이 높은 날로 판정함.
   - 선박 수준으로 분포를 요약할 때 `p_mean_2`, `argmax_ratio_2`가 0보다 크게 잡히면서, 다수 클래스인 연안복합(2,920척) 중 상당수가 통발 쪽으로 끌려가 오답화됨.
   - 단 19척의 연안복합 손실과 20척의 자망 손실이 통발의 10척 이득을 압도하여 순손실 -32척이 발생함.

---

## 8. Track 3 앙상블 및 후속 트랙 인계 권고사항

1. **S2 단독 모델의 채택 불가**:
   - `S2` 단독 특징 추가(304+31열)는 기각 조건을 충족하였으므로, 단독 base 모델로 304열을 대체하지 않는다.
2. **Track 3 (앙상블) 활용 가치**:
   - `probabilities_track2.npz`에 저장된 S2 세그먼트 기반 예측 확률(`cand_outer_probs_sqrt`, `cand_outer_probs_std`)은 통발(Class 2)에 대해 기존 모델이 놓치는 10척의 고유 정답(unique true positives)을 포함하고 있음.
   - Track 3에서 다양성 확보용 블렌딩 소스로 극소 가중치(예: 0.05~0.10) 결합 또는 클래스 2 전용 선택 게이트로만 조건부 테스트할 것을 권고함.

---

## 9. 산출물 및 무결성 해시 (Artifacts Integrity)

| 산출물 경로 | 크기 | 설명 |
|---|---|---|
| `vessel_day_segments.parquet` | 19.2 MB | 5,897척 319,808개 선박-일 특징 테이블 |
| `probabilities_track2.npz` | 278 KB | 전체 5,897척 3-Fold OUTER/INNER 예측 확률 |
| `track2_results.json` | 134 KB | 4-CV 및 3-Fold 전수 혼동행렬/지표 JSON |
| `resource_checks.json` | 6.8 KB | 단계별 가용 RAM 및 프로세스 스냅샷 로그 |
| `extract_segments.py` | 7.2 KB | 일별 세그먼트 저메모리 추출 스크립트 |
| `s2_models.py` | 8.8 KB | 세그먼트 교차적합 및 선박 집계 모듈 |
| `run_s2_gate.py` | 14.5 KB | 4-CV 게이트 및 전체 3-Fold 자동 실행기 |
| `TRACK2_REPORT.md` | 본 문서 | Track 2 최종 결과 및 기술 진단 보고서 |
