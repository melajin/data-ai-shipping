# Round 006 결과 — 진단 오류 수정 확인, 실제 추론은 RAM 관문에서 중단

선택적 cache_mode_ 속성 처리 오류를 수정했고 mock 및 실제 모델의 fit 후 진단을 통과했다. 동일한 개발 INNER 두 질의의 확률 호출을 시작했으나 가용 RAM이1.5GiB 아래로 내려가 27.594초에 소유 프로세스 트리를 중단했다. 확률은 완성되지 않았고 재현 판정·새 F1은 없다. micro-F1 0.7은 아직 달성하지 못했다.

## 이전 → 현재 → 다음

round005는 입력 복구에 성공했지만 fit 반환 뒤 진단 기록의 AttributeError로 확률 호출 전에 실패했다. round006은 속성 부재와 None을 구분하고 fit 반환 사실을 먼저 저장하도록 변경했다. 모델·문맥·질의·추론 설정과 확률 비교 계산은 유지했다. 이번 개선은 **진단 결함 해소와 실제 추론의 자원 제약 확인**이다. 분류 성능 개선으로 해석하지 않는다.

다음에는 CPU 실행에서 컬럼 배치 분할이 적용되지 않는 경로를 소스 근거로 검토하고, 독립 배치축만 작게 나누는 로컬 어댑터를 작은 합성 입력의 동일 모델 비교로 검증한다. 전체 FIT3144의 재시도와 M4 학습은 다음 관문 이후다. 같은 시작 여유량으로 동일 실험을 반복하지 않는다.

## 조건과 관찰

| 항목 | 결과 |
|---|---|
| 입력 | 기존 검증 NPZ/freeze 바이트 복사·SHA 일치; 재export0회 |
| 진단 mock | 1회, 3개 test method/잘못된 설정10개 subcase 통과; 프로세스0.656초 |
| 실제 pilot | 1회, 27.594초, 자원 감시자가 중단, child exit1 |
| pretrained 문맥 fit | 1회 반환 확인; 학습된 계수 갱신0회 |
| fit 후 진단 | CPU/FP32·AMP/FA3false·offload/KV·클래스 계약 통과 |
| 선택적 속성 | cache_mode_present=false, cache_mode=null; model_kv_cache_ 존재, 값None |
| predict_proba | 시도1, 완료0; 확률·차이·argmax 비교 없음 |
| 시작 가용 RAM | 4.283466339GiB |
| 관측 최저 가용 RAM | 1.392108917GiB; 중단 기준1.5GiB 미만 |
| sampled 소유트리 working set 최고 | 3,160,498,176bytes (약2.943GiB) |
| 실제 Python OS peak working set | 3,148,410,880bytes |
| timeout | 600초에 도달하지 않음 |
| 재시도·F1·OUTER추론·설치/다운로드 | 각각0회 |

FIT3144×312 전체와 고정 INNER2 [36001915,31703435], seed42, estimators8, batch1, CPU FP32, n_jobs3를 사용했다. 환경은 기존 Python3.12.14/TabICL2.2.0/Torch2.6.0+cpu, checkpoint SHA bdc7dbd5…d0을 재사용했다. 과거 CUDA/전체INNER787과의 수치 동등성은 아직 확인되지 않았다.

## 실패 계층과 증거의 한계

이번 실패는 **실행 중 가용 메모리 관문의 중단**이다. OS OOM 예외나 모델 확률 오류가 관측된 것이 아니다. stderr는 비어 있고 staged child JSON은 강제 종료 때문에 status=STARTED, stage=predict_proba_start에 남아 있다. 이를 진행 중 프로세스로 오해하지 않도록 manager 집계 result.json은 종료된 상태로 구분한다. 확률이 없으므로 수치 재현 실패라고도 판정하지 않는다.

원시 wrapper receipt는 taskkill 직후 자식16792/2716을 remaining으로 관측했다. 원기록을 덮어쓰지 않았다. **17:58:42UTC 후속 OS 목록·PID생성시각 검사에서는 세 소유 PID가 모두 사라졌다.** manager/postexit_verification.json에 확인을 저장했고 추가 강제종료는 하지 않았다. 사용자 재확인18:00:31UTC에서도 잔존0개, 가용4.201679229GiB/총13.809436798GiB였다. 종료 뒤 RAM 회복은 전체 추론이 그 메모리 안에 끝난다는 증거가 아니다.

소스에서 tabicl/_model/inference.py의 InferenceManager.__call__은 CPU일 때 automatic batch/offload 선택 이전에 _run_forward로 반환한다. embedding.py는 컬럼/feature를 leading batch축으로 전달한다. 이 경로는 큰 일괄 중간 텐서가 원인일 수 있다는 **소스 기반 다음 가설**이다. 실제 할당 위치를 프로파일링한 것은 아니며 전체 추론의 최종 peak와 필요한 RAM은 아직 모른다. offload='auto'가 CPU 작업 메모리를 자동 제한한다고 가정하지 않는다.

## 변경 관리·평가 분리

독립 검토된 pilot SHA는 `a4d10bba93f3fe07ea7188aba216c1211e13eba24cec334fc19d7b985d681505`, mock SHA는 `237edc8867af5e1684d8ba99bd3cfd7c8d8aa1404e3956ecabaa10ef32a010b5`다. 실행 직전 pilot와 wrapper SHA를 강제했고 실제 snapshot과 같았다. wrapper는 이전 버전에서 ROUND 경로만 바꿨으며 receipt schema의 round005 명칭은 기존 직렬화 버전으로 남아 있다. 입력 freeze schema도 역사 계약 그대로 유지한다.

관리자 호스트 turn_context는 gpt-6-astra/high, 작성자와 별도 검토자는 gpt-6-luna/xhigh였다. manager/model_runtime_evidence.json과 assistant_host_evidence.json은 요청과 호스트 관측을 분리한다. 내부 모델 인증을 주장하지 않는다. 팀은 관리자+보조2명이며 호스트 총4슬롯 한도 이내다.

보호된 전체7372행, holdout 개별 특징/라벨/확률, Test2025, 원자료는 열지 않았다. 비교용 두 INNER 확률은 이미 round005에서 읽은 개발자료다. INNER 라벨은 사용하지 않았다. 역사 채택 기준 sqrt_macro 5seed의 반복노출 개발 OUTER5897 micro0.5930133966423605/macro0.5252719738966167과 미채택 탐색0.5933525521451586은 바뀌지 않았다. 독립·공식 점수는 없다.

## 사용자 추가 가설과 운영 지시

계절·시간대 가설을 SEASONAL_HYPOTHESIS.md에 기록했다. 과거 monthly_repeat 집계 보고서는 개발 micro 차이+0.0044090, 새정답176/새오답150/순증26, paired95%구간[-0.0016958,+0.0108530]를 기록한다. 기준은 none_micro seed42이며 현재 sqrt_macro5seed와 혼합 비교하지 않는다. 이는 과거 보고서 확인이며 새 평가도 계절 인과 효과 입증도 아니다. 월별 형태·지역·시간대의 변화가 전체집계에서 사라지는지 후속 검토할 가치가 있다. 기존1–6월 계약만으로 사계절 일반화를 주장하지 않는다.

사용자는 앞으로 RAM이 부족하면 다른 가능한 작업을 먼저 수행하고 다시 확인하여 진행하라고 지시했다. AGENTS.md와 CYCLE_PROTOCOL.md에 지속 규칙으로 반영했다. 이번 중단 후 소스 검토·계절 가설 정리·보고/인계를 진행하며 RAM을 재확인한다. 재개는 기존 유한 예산과 실행 중 중단 이력을 함께 고려한다.

대체 작업 후 **18:05:53UTC 재확인에서 가용 RAM4.511840820GiB, 소유 프로세스0개**였다. manager/ram_recheck_after_alternative_work.json에 완료한 대체 작업과 판단을 저장했다. 이번 실제pilot1회 상한은 소진돼 동일재실행하지 않고, 새 회차의 소스 관문과 작은 합성비교로 진행한다. 다음 모델실행 직전에도 RAM을 다시 확인해야 한다.

## 검토·학습·인계

precheck.json/REVIEW.md는 실행 전 독립 승인, FINAL_REVIEW.md/final_review.json은 결과 검토다. manager 집계는 artifacts/result.json, 원시 실행/자원곡선은 logs/pilot_01, mock은 logs/mock_01에 있다. 기술 목표 중 진단 수정은 달성했고 작은 실제자료 재현은 미완료다. 학습자의 설명 능력과 하드웨어 동작은 검증하지 않았다. LEARNING_NOTES.md에 단계별 판단 질문을 남겼다.

NEXT_SESSION.md는 다음 bounded CPU 컬럼 분할 검증의 입출력·자원·실패 분기를 지정한다. 새 세션 수락 증거는 automation/receipts/round_006_launch.json에 저장한다. 현재 structured chat의 닫기 기능은 CLI terminal 목록/도움말에서 지원되는 핸들이 발견되지 않았다. 다른 터미널/앱은 닫지 않는다. 인계 후 현재 관리 작업을 종료하며, 수동 정리가 필요하면 세션ID codex_192eb310_5ae3_440c_97ef_28aaef23603d의 완료 탭만 닫는다.
