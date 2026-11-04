# Round 003 — 저장 확률의 판정 손익 감사

동결 시점: 2026-11-04 16:15 UTC, 점수 계산 전. 인계 NEXT_SESSION SHA256 1E440F52259CB33011A567C9BF6AC083BDEAD3110D1912AA3E62D00D6921D66E의 R0를 수행한다.

기술 목표: 동일 선박·원확률에서 A_raw, A_old, A_micro_select의 정답 이득과 손실을 검산한다. 학습 목표: 학습 손실·원확률·최종 판정, macro와 micro의 손익, 선박 분리와 반복 개발 노출의 차이를 설명한다. 성능 상승을 예상값으로 고정하지 않는다.

## 범위와 자원

- 관리자 세션 시작 2026-11-04T16:13:25Z, 종료 상한 16:58:25Z(45분).
- R0 계산 누계 최대 15분, M4 준비 조사는 계산 후 최대 10분. 신규 fit=0, 새 원모델 추론=0, 큰 계산 동시1개, threads<=3, 큰 계산 전 가용 RAM>=1.5GiB.
- 원자료/이전 저장소/공유 package 읽기 전용. holdout 개별 행, 전체7372 F156/라벨표, Test2025는 열지 않는다. 외부 업로드·공식 제출·유료 자원·이번 환경 설치/모델 다운로드 없음.
- 코드·실행: r003_implementation; 독립 검토: r003_review. 두 보조 gpt-6-luna/xhigh/fork_turns=none 요청. 관리자만 계획·설정·공유상태·보고서 수정.

## 고정 입력과 사전검사

NEXT_SESSION에 지정된 TabICLv2_F156_공유자료의 seed42/2026 OOF 및 fold0/1/2 INNER, 기존 판정 파일, 역할 명부, 메타데이터와 소스만 사용한다. OOF 5897척 정확히1회, fold1966/1966/1965, INNER각787, ID/정답/관측일/역할/클래스 순서/finite/sum/seed정렬을 검증한다. 원소스의 ID 직렬화와 manifest hash를 확인한다. 필요 시 round002 NPZ의 ID/role/y만 참조한다. 특징행은 읽지 않는다.

실제 생성 코드와 metadata의 고정 context/zero-shot 근거를 조사한다. INNER가 신경망 학습/조기 종료에 사용되지 않았다는 근거가 부족하면 정책 결과는 탐색 진단으로만 남기고 원모델 재현이라 부르지 않는다. 불일치는 숨기지 않고 검증 범위를 축소 또는 중단한다.

## 세 비교군과 선택

A_raw=원확률 argmax, A_old=fold 통발 p2 배수2/3/2, A_micro_select=seed/fold별 INNER만으로 선택. grid=[1,1.5,2,2.5,3], 나머지 클래스 배수1. 클래스 [0,1,2,3], zero_division=0. 두 seed를 앙상블하지 않고 각 지표의 산술평균을 보고한다.

가능 후보는 INNER raw 대비 macro 하락없음, 클래스별 F1 하락<=.01, 자연1–7일 macro 하락<=.01이다. micro 최대, 동점이면1에 가까운 값, 다시 동점이면 작은 값. 수치 비교 허용오차1e-12. raw는 항상 기본 후보다.

지원 부족의 사전 정의: 전체 INNER 또는 자연1–7일 INNER 집단에서 정답 클래스 하나라도 support=0이면 해당 fold/seed는 raw로 복귀한다. 정답이 존재하지만 예측이 없는 클래스의 F1=0은 그대로 계산한다. 별도 최소 표본수는 사후 도입하지 않는다. 0일/비유한/음수/기타 미지원 관측일은 별도 집계한다.

6개 선택 배수와 근거를 JSON으로 저장·해시 동결한 뒤 OOF 판정을 계산한다. 원확률을 고치거나 배수 점수를 calibrated probability로 부르지 않는다.

## 출력·진행 기준

seed/fold/전체의 micro·macro·weighted F1, 정답수, 클래스 precision/recall/F1/support, 혼동행렬, 관측일1–7/8–30/31–90/91+ 및0/미지원, 연안↔자망·통발 변화, old→raw/old→selected/raw→selected gain/loss/net을 보존한다. 원확률 logloss/Brier/10bin ECE 및 max>=.9 높은확신오답도 보고한다.

bootstrap은5000회 seed20261105, 같은 선박 인덱스를 두 seed에 동시에 적용하여 seed별 차이의 평균을 구한다. 두 seed를11794척으로 취급하지 않는다. 95% percentile CI는 반복 개발선택/해역 의존을 제거하지 않는다.

selected를 raw보다 나은 확인 후보로 진행하려면 평균micro>=+.005, 각seed 양수, paired CI 하한>0, 평균macro 하락없음, 각seed 클래스F1/자연1–7일macro 하락<=.01을 모두 만족해야 한다. R0 완료 자체는 개선 여부와 무관하게 감사·검산 완료로 판정한다. 역사 LightGBM .593013은 별도 파이프라인 참고값이다.

## M4와 후속

R0 계산 후 알려진 프로젝트·환경·캐시만 최대10분 조사한다. tabicl2.2.0/Torch/실제GPU/지정checkpoint SHA256/FIT 문맥·클래스변환·전처리 증거를 확인한다. 준비되면 다음 회차는 M4-a(weight만,bias고정) 대 M4-b(rank2,bias고정)의 무변경 출력/gradient/병합/reload와 한fold INNER pilot로 한정한다. 부족하면 다음 회차는 부족한 환경/원본 replay 복구의 유한 계획으로 한정한다. M1/M3/M5나 새 특징을 섞지 않는다.

실패 시 원자료·계약·전처리·모델·전달/표시 계층을 구분하고 같은 무정보 실패를 반복하지 않는다. 결과 보고/ledger/status/다음 명령을 저장한 뒤 fresh Astra high 수락 영수증을 확인하고 종료한다. 학습자 이해·독립 평가·공식 성능·하드웨어 검증은 이번 완료와 별개다.
