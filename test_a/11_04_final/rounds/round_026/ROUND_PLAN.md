# Round 026 — 3대 병렬 트랙(S1/kNN 공간, S2 선박-일 세그먼트, 클래스 보호 앙상블) 및 통합 실험 계획

작성 시각: 2026-11-05T04:40:00Z  
회차 ID: `round_026`  
기반 브랜치: `round_025` 완료 및 사용자 병렬 에이전트 지시

---

## 1. 회차 목표 및 배경

Round 025까지 역사 기준선은 **LightGBM 5-seed sqrt_macro (3,497 / 5,897 = 0.593013, TP0=2381, TP3=92)**에 머물러 있었으며, 타 팀의 0.68~0.70 및 0.838 대비 격차 원인 규명과 0.60+ 돌파를 위한 구조적 개선이 절실했습니다.  
Round 026은 세 가지 독립적인 직교 가설을 병렬 트랙으로 나누어 동시에 탐색하고, 최종 통합(Grand Fusion)을 수행하도록 설계되었습니다.

### 3대 병렬 트랙 정의:
1. **Track 1 (`track1_spatial_knn`)**:
   - Round 025 S1 proxy 버그(균등분포 스무딩에 따른 연안복합 TP 38척 손실) 규명 및 무스무딩 Hellinger 거리 기반 k-최근접 이웃(kNN) 공간 확률 특징 추출.
   - 누수 방지 원칙: FIT 갤러리만 사용(Leave-One-Out 적용), INNER/OUTER는 순수 질의선박으로 평가.
   - 관문: Fold 0 FIT 내부 4-CV에서 기준선 대비 유의미한 개선 검증 후 3-fold 전체 확장.
2. **Track 2 (`track2_s2_segments`)**:
   - 선박-일(vessel-day) 세그먼트 단위 약지도(Weak Supervision) 교차적합 모델 탐색.
   - 단기 선박 및 정지/조업 상태별 일별 공간·동역학 요약 특징 생성.
   - 관문: Fold 0 FIT 내부 4-CV에서 통발(Class 2) 개선 및 전체 micro-F1 기준 충족 여부 진단.
3. **Track 3 (`track3_ensemble`)**:
   - Round 021 메타 스태커(로지스틱 회귀) 실패 원인(394척 고자유도 과적합 및 TabICL 2.2% Class 3 사전분포 억제) 규명.
   - INNER 3-fold OOF 교차검증(2,361척)에서 저자유도 선형 결합 + 베이즈 사후확률 보정(Prior-Shift Multipliers) + 클래스 3 듀얼 게이트 최적화.
   - 목표: `TP0 >= 2,389` 및 `TP3 >= 92` 보호 하한을 100% 만족하며 micro-F1 극대화.
4. **Grand Fusion (최종 통합)**:
   - Track 1의 다중해상도 공간 확률, Track 2 세그먼트 확률, TabICLv2 다중 시드(seed42 + seed2026), CatBoost, LightGBM 5-seed를 INNER 3-fold CV에서 통합 최적화하여 OUTER 5,897척에 단 1회 적용.

---

## 2. 자원 및 실행 제약

- **RAM 제약**: 가용 RAM 약 1.8~2.2 GiB 환경.
- **실행 규칙**:
  - 모든 Python 스크립트 실행 전후 `psutil.virtual_memory().available` 확인 및 `resource_checks.json` 기록.
  - 프로세스 RSS 상한 150 MB 엄수, `n_jobs=1`, 명시적 `gc.collect()` 호출.
  - 트랙별 디렉터리 엄격 격리 (`track1_spatial_knn`, `track2_s2_segments`, `track3_ensemble`).
  - **절대 규칙**: 모델 가중치 및 승수 튜닝 시 절대 OUTER 정답(`y_outer`)을 보지 않고, 오직 각 fold의 INNER (787척) 또는 INNER 3-fold CV (2,361척)에서만 수행.
