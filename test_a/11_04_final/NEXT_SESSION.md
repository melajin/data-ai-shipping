# 2026-11-05 최신: Round028→029 원시 궤적 순서 특징 실험 완료

- 사용자 요청의 새 방법은 이름표 재현이 아니라 WKT 부분선 내 방향 전환 부호와
  이전 위치로의 비국소 복귀를 나타내는 2개 고정 특징이다. 구현은 Luna worker에
  `gpt-6-luna/max`로 위임했다. 요청된 `ultra`는 현 호스트 Luna 지원 범위 밖이다.
- `rounds/round_028_domain_features/ROUND_REPORT.md`: Train2026 6개월
  3887069행 streaming 추출. Round028의 첫 8fit은 `float32` 변환 때문에
  과거 기준선 재현에 실패하여 무효로 기록했다.
- `rounds/round_029_domain_features_dtype_correction/ROUND_REPORT.md`:
  원본 `float64` 보존 후 기준선 저장 예측 완전 재현. FIT3144 내부 4CV에서
  기준선1811→후보1822(+11), micro .576018→.579517, macro
  .491289→.495259. 자망 TP+10, 통발+2, 연안복합−2. 새정답113/새오답102.
- 사전 관문 후보≥1833·순증≥16·연안복합 TP 비감소에 실패해 **미채택**.
  OUTER·holdout·Test 확장 0, 독립 또는 공식 점수 없음. 0.7 목표 미달.
- 특성 CSV와 원시 입력 계보는 Round028 `worker/`에 있다. 다음에는
  기존 결과를 재선택하지 말고 별도 고정 가설을 검토한다. 계산 작업 없음.

---

# 2026-11-05 이전: 팀원 관찰 기반 Round026→027 재검사 완료

- 최신 회차: `round_027_team_recheck`. 기존 `round_027_fallback_ovr`와 구분하며 기존026/027 파일은 수정하지 않았다.
- 사용자 지시: 팀원 이름표 결과는 가설 참고만. 원래 이름표 재현은 불필요.
- 보고서: `rounds/round_027_team_recheck/ROUND_REPORT.md`; 코드/고정계획/예측/선택동결/입력해시/검산을 같은 폴더에 저장.
- 3개 원래 fold의 SELECT 각394척, 내부3CV, 총36개 작은 로지스틱 재검사 적합. SELECT에서 고른 절차를 동결하고 개발 OUTER5897 평가.
- primary:3538/5897, micro0.5999660844, macro0.5161167059. 같은조건 base:3538, macro0.5174847814. 새정답24/새오답24, net0.
- TP primary[2547,798,101,92], base[2538,801,106,93]. 기존 절대 보호 하한 둘은 통과하지만 같은base TP3-1 및 자망/통발 감소. **채택하지 않는다**.
- 단독이름표확정3488→단독재검사3516, 여전히base3538보다낮음. 무표=0은3439(-99), 강제통합3412(-126).
- 이번 proxy 이름표(이진점수>=.5)에서 단독4283, 무표1498,0·1동시110(실제통발10),정확히0·2는3척뿐. 팀원 집계와 같은 모집단이라고 주장하지 않는다.
- 별도검산:5897행/11예측열/34입력해시통과. 독립성/원모델 INNER조기종료 노출/WorkerA 과거ID sidecar 부재는 보고서에 명시.
- 실제가용 RAM 재확인:첫진입1.493<1.5로학습0중단; metadata검토후다시1.530에서진입성공. 관측최대RSS.156GiB, 단계별최저가용1.396GiB. thread1/BelowNormal/계산동시1.
- 자동 재실행·OUTER최고값 채택·목표지표 변경 없음. micro0.7 목표는 미달. 새 후보는 별도 가설과 고정 기준으로 다룬다.

---

아래는 갱신 전 Round026의 역사 인계 내용이다. 그 안의 ‘공식 돌파/검증된 황금비율’ 표현은 후속 독립 검토의 선택 누출 지적을 함께 읽어야 하며 최신 확정 결론으로 사용하지 않는다.

# Round 026 완료 — micro-F1 0.60 벽 공식 돌파 및 다음 회차 인계서

작성일: 2026-11-05T05:25:00Z  
완료 회차: `round_026`  
회차 상태: `completed_verified_grand_fusion_success`  
공식 최고 채택 점수: **3,552 / 5,897 (micro-F1: 0.602340, macro-F1: 0.521552)**  
역사 기준선(3,497) 대비: **+55척 순증** (paired bootstrap 95% CI: `[+0.002709, +0.016619]`, p < 0.001)  
클래스 보호 조건: **`TP0 = 2,541 >= 2,389`**, **`TP3 = 92 >= 92` (완벽 충족)**  
독립 평가 / 공식 제출 점수: 미측정 (null)

---

## 1. Round 026 완료 요약 및 핵심 성과

Round 026에서는 3대 병렬 트랙(Track 1: 공간 kNN, Track 2: S2 세그먼트, Track 3: 클래스 보호 앙상블)을 완수하고 전 트랙 통합 Grand Fusion을 성공적으로 수행했습니다:

1. **Track 1 (`track1_spatial_knn`)**:
   - Round 025 S1 proxy 스무딩 결함 규명 및 수정 (FIT 4-CV `1,781 -> 1,814척`, +33척 반등).
   - 무누수 FIT 갤러리 다중해상도 Hellinger kNN 구축: FIT 4-CV 관문 통과 (`1,811 -> 1,836 / 3,144척`, +25척).
   - OUTER 3-fold 단독 성능: 3,466 / 5,897 (기존 304 대비 +62척, 자망 TP 927 달성).
2. **Track 2 (`track2_s2_segments`)**:
   - 선박-일 세그먼트 약지도 교차적합 진단: 통발 TP는 54 $\to$ 64척으로 늘었으나, 정지/대기일 약지도 노이즈로 자망/연안복합 $\to$ 통발 오분류(FP)가 35척 증가하여 FIT 4-CV 점수 하락(-9척), 관문 미달로 단독 채택 기각.
3. **Track 3 (`track3_ensemble`)**:
   - Round 021 메타 스태커 실패 원인(394척 과적합 및 TabICL 2.2% Class 3 사전분포 억제) 규명.
   - INNER 3-fold OOF 교차검증(2,361척)에서 클래스 보호 조건(`TP0 >= 958`, `TP3 >= 38`)을 만족하는 베이즈 사후확률 보정 승수 $\vec{\alpha} = [1.033, 1.000, 0.983, 1.500]$ 도출.
   - OUTER 단독: **3,538 / 5,897 (micro-F1: 0.599966, 기준선 대비 +41척, TP0=2538, TP3=93)**.
4. **Grand Fusion (`T3_Grand_Fusion_BothTab_T1_w10`)**:
   - LGB 5-seed(35%) + TabICL42(22.5%) + TabICL2026(22.5%) + CatBoost(10%) + Track1 kNN(10%) + 사전분포 보정.
   - **프로젝트 최초 0.600 돌파: 3,552 / 5,897 (micro-F1: 0.602340)**!

---

## 2. 생성 및 갱신된 공식 파일 목록

- 종합 회차 보고서: `rounds/round_026/ROUND_REPORT.md`
- 회차 계획서: `rounds/round_026/ROUND_PLAN.md`
- 전체 프로젝트 현황 보고서: `reports/20261105_round026_FULL_STATUS_REPORT.md`
- Track 3 전담 보고서: `rounds/round_026/track3_ensemble/TRACK3_REPORT.md`
- Track 1 전담 보고서: `rounds/round_026/track1_spatial_knn/TRACK1_REPORT.md`
- Track 2 전담 보고서: `rounds/round_026/track2_s2_segments/TRACK2_REPORT.md`
- 재사용 앙상블 모듈: `rounds/round_026/track3_ensemble/protected_ensemble.py`
- 확률 및 예측 아티팩트: `rounds/round_026/track3_ensemble/probabilities_track3.npz`
- 상세 메트릭 JSON: `rounds/round_026/track3_ensemble/track3_results.json`, `grand_fusion_results.json`
- 실험 대장: `EXPERIMENT_LEDGER.csv` (round_026 행 추가)
- 프로젝트 상태: `STATUS.json` (`current_round: round_026`, `adopted_best: 0.602340` 갱신)

---

## 3. 다음 회차(Round 027)를 위한 전략적 제언 (0.65 ~ 0.70 도약 로드맵)

현재 0.602340 점수는 **전체 7,372척 중 42.6%(3,144척)만으로 학습된 모델들의 앙상블**이라는 표본 제약 하에서 달성된 것입니다. 0.65~0.70으로 도약하기 위한 다음 단계 핵심 과제:

1. **학습 표본 크기 확장 (3,144척 $\to$ 5,897척 / 7,372척)**:
   - 3-fold Nested CV에서 5-fold CV로 전환하여 fold당 학습 표본을 3,144척 $\to$ 5,897척으로 87.5% 확대.
   - 소수 클래스(채낚기 67 $\to$ 126척, 통발 446 $\to$ 668척) 표본을 2배 이상 확보하여 분류기 학습력 극대화.
2. **Grand Fusion 최적 결합비율 전면 적용**:
   - Round 026에서 검증된 황금 비율 `(LGB 35% : TabICL 45% : Cat 10% : kNN 10%)`과 사후확률 보정기(`alpha_3 = 1.425`)를 5,897척/7,372척 풀 트레이닝 모델에 이식.
3. **자원 및 누수 방지 원칙 유지**:
   - 가용 RAM >= 1.5 GiB 확인, thread=1, below-normal priority 유지.
