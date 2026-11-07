# 사용자 아이디어 문서 검토와 3차 결정

사용자 추가 지시(2026-11-04): 최종 보고서 전에 `C:/Users/dlehs/Documents/카카오톡 받은 파일/알고리즘 변형 아이디어.md`를 확인하고 3차 진행 방법을 먼저 설명한 뒤 넘어간다. 문서 전 구간을 읽었고 사본을 references/algorithm_variant_ideas.md에 보존했다. SHA256: 75BE0FD2F451B9E4215EC2F02A8F200B8084F26145E4FE845A22C2CBA6BE91BC.

## 결정

3차는 **R0: TabICLv2 A의 판정 규칙 손익 비교**를 먼저 수행한다. 기존 월별35 특징 5seed 우선 분기는 뒤로 미룬다. Round002의 사전 고정 실험·판정 기준은 바꾸지 않는다. 3차에서 원확률 argmax, 기존 통발 배수, 새 micro 중심 INNER 선택 배수를 동일 선박·동일 seed에서 비교한다. 그 다음 M4-a 최종 Linear 직접 조정과 M4-b rank2 수정의 준비 관문으로 간다. 이 순서를 사용자에게 3차 착수 전에 설명했다.

선택 이유는 문서가 강조한 목표 정렬이다. 기존 통발 배수는 macro를 올리면서 micro를 낮출 수 있다. 전체 정답·오답이 담긴 예측으로 이득과 손해를 먼저 계산해야 한다. 오류 전용 CSV의 복구 수만으로 보정 제거를 채택하지 않는다. 반복 오류와 검색 순위 차이가 attention 결함을 증명하지 않으므로 M1/M3/큰 구조 제거는 먼저 시행하지 않는다.

## 현재 확인한 실행 근거와 한계

- 원 저장소 `team/tabiclv2_f156`에는 코드·설정·집계가 있으나 조사한 seed/fold 폴더에는 예측 CSV와 모델 binary가 없다.
- 실제 예측은 `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/`에 있다. seed42/2026의 `original_oof_predictions.csv`, `oof_decisions.csv`, 각 fold의 `inner_predictions.csv`가 존재한다. 이 회차는 파일명·헤더와 metadata만 확인했고 새 지표는 계산하지 않았다.
- INNER 헤더: rfid_id,p0,p1,p2,p3,y_true,observed_days. OOF 원본에는 fold가 더 있다. 판정 파일에는 selected_trap_factor/uncorrected_class/chosen_class 및 decision_score0..3이 있다. 두 seed 모두 기존 fold 배수는 2/3/2다.
- 동일 package의 final_fixed_decision_rule.json에는 여섯 INNER 파일 SHA256, FIT/INNER ID hash와 split hash가 있다. 3차에서 실파일/명부와 대조한다. 명부 hash의 직렬화 규칙도 확인해야 한다.
- 과거 검토는 FIT context ID 명부와 model binary 부재로 TabICL을 새 엄격 결합 후보에서 제외했다. 이번 저장 확률 판정 감사가 그 문제를 해결하지 않는다. 원모델 재추론 성공이라고 주장하지 않는다.
- 입력 정의에 불일치가 보인다. 아이디어 문서는 F156+결측 표시라고 기술하지만 package run_settings/README는 결측 표시를 추가하지 않는다고 기술하고, evaluation의 replay_query_shape에는 312열 기록도 있다. 3차에서 코드/메타데이터로 좁히고 불명확하면 M4의 실제 입력 정의를 확정하지 않는다. 저장 확률의 단순 판정 손익 계산과 원모델 재현을 구별한다.
- 문서의 RTX3060Ti/환경/계수 수는 원 문서가 보고한 근거다. 이 머신의 가용 GPU·Torch·체크포인트로 새로 검증한 값이 아니다. 문서의 `C:/Users/User/Desktop/...` 경로를 현 머신에서 실행 가능한 경로로 취급하지 않는다.

## 후속 구조 변경의 관문

R0 뒤 M4를 진행하려면 같은 A 체크포인트 SHA256, 로컬 TabICL2.2.0 동작, F156 전처리, FIT-only 문맥 ID/라벨, 클래스 permutation/역변환, GPU 여유와 짧은 pilot 시간을 확인한다. 직접 조정과 rank2는 편향 고정·동일 학습 예시·동일 예산으로 비교한다. 무변경 출력 일치, 학습 계수 범위, gradient, 병합 전후·재로드 검산을 통과해야 한다. 45분 회차에 문서 추정3.5–9시간 전체를 자동 완성하지 않는다. 환경 확보·단위 검증·pilot·전체 비교를 별도 회차로 나눈다.

목표는 현재 사용자 지정 micro-F1>=0.7이다. 문서의 과거0.88, 제안된 .01 하락 제한, 11월6일 마감은 현재 작업의 확정 목표·새 승인·정확한 마감시각으로 자동 치환하지 않는다. 다만 3차는 업종별F1/짧은 집단의 손해를 엄격히 드러내는 정책 비교로 설계한다. 공식 제출·사고 탐지는 이번 범위에 추가하지 않는다.
