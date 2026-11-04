# Round 005 결과 — 입력 복구 성공, 추론 전 진단 코드 오류

원래 순서의 개발 입력 복구와 독립 배열 검산은 통과했다. 실제 pilot는 24.125초 후 `AttributeError`로 종료됐으며, 확률 추론은 호출되지 않았다. 신규 F1은 없고 목표 0.7은 아직 달성하지 못했다. 이번 오류는 `kv_cache=False`에서 없는 `cache_mode_` 속성을 진단 코드가 직접 읽은 구현 오류다. RAM 부족이나 모델 예측 실패로 분류하지 않는다.

## 실제 산출과 판정

이전 round004 대비 이번 round005의 변경은 미실행이던 원순서 입력 export를 실행하고, 잘못 연결한 집합/순서 해시 검사를 정정하며, 별도 작성·검토된 실제 입력 pilot를 시도한 것이다. **개선된 것은 입력 재현성과 실패 원인의 확인 수준이며 분류 점수 개선은 측정하지 못했다.** 다음 round006에서는 모델이 아니라 선택적 캐시 속성을 기록하는 진단 코드와 실행 전 mock 검사를 변경한다. 사용자의 추가 지시에 따라 이러한 이전/현재/다음 비교와 fresh session 인계·완료 세션 닫기 절차를 CYCLE_PROTOCOL과 NEXT_SESSION에 명시했다.

| 항목 | 관찰 결과 | 해석 |
|---|---|---|
| 입력 export | 1회, 2.672초, 종료코드0 | FIT3144×312, INNER787×312, float32, 원manifest 순서 보존 |
| 독립 입력 검산 | 1회, 2.172초, 종료코드0, PASS | 두 전체 배열 정확 일치; 역할·라벨·열·클래스·질의 순서 검산 |
| 셀/중앙값 검산 | 결측50셀·관측50셀, median 최대차2.8421709430404007e-14 | saved median 및 원결측 표시 변환과 일치 |
| 실제 pilot | 1회 시작, 24.125초, 종료코드1 | 체크포인트/문맥 fit 뒤 진단 속성 접근에서 종료 |
| 확률 호출 | 시도0, 완료0 | 원확률 차이·argmax·재현 통과 여부는 미측정 |
| 계수학습·F1·OUTER 추론 | 각각0회 | 문맥 fit은 pretrained 모델의 입력 바인딩이며 계수학습이 아님 |
| 독립/공식 점수 | 없음 | 개발·독립·공식 평가를 분리해 유지 |

역사적 비교 기준은 LightGBM `sqrt_macro` 5seed의 반복노출 개발 OUTER 5897척 micro-F1 **0.5930133966423605**, macro-F1 **0.5252719738966167**다. 과거 탐색값0.5933525521451586은 미채택이며 새 결과가 아니다. 이번 진단을 성능 개선이나 CPU/CUDA 수치 동등성 증거로 사용하지 않는다.

## 입력과 해시 정정

읽기 전용 exp01/fold_0_features.npz의 고정 SHA256과 source/metadata 연결을 확인했다. 전체7372행 표, holdout 특징·라벨·확률, Test2025, 원자료는 열지 않았다. holdout ID metadata는1475개 ID의 분리 검사에만 사용했고 `known_holdout_reused=true` 이력을 유지했다. 독립평가의 노출 이력 관문은 여전히 미해결이다.

추가 운영 메시지의 v4 검증 근거로 frozen FIT/INNER 해시는 **숫자 정렬 후 LF 연결, 끝 LF 없음**인 집합 해시임을 실행 전에 정정했다. 기존 인계의 ordered BASE JSON digest 직접일치 요구는 잘못된 의미 비교였다. PLAN_AMENDMENT_01.md는 처음 계획과 이전 회차 기록을 보존한 채 이 조건만 정정한다. 이번 회차에서 직렬화 후보를 탐색하지 않았다.

frozen FIT 집합 해시는 `2470cabe8ecbe7a063ab8303bcb66faa85cb907596c9d44f69dda3b8ee6b0ed5`, INNER 집합은 `cb82568ec4fcedf20a5706d15db6a76f84f84a23b9273aa4b18948c3014ed0c3`와 일치했다. 원순서의 JSON digest는 FIT `bdfb86ec3c99bbc783a5f0e8d3a1524b789d3c7e1101293d42805f7ccacca3f0`, INNER `54beb55ee1b36073286821b22c848ce77a18567d40ff3287794e948fec45643d`다. INNER ordered digest와 frozen 집합 digest는 예상대로 다르며, 이 불일치를 오류로 숨기거나 순서 증거로 바꾸지 않았다.

입력 NPZ 산출 SHA256은 `9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5`다. 원INNER 앞2개 질의의 ordered digest는 `7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969`, query_freeze.json 파일 해시는 `6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef`다. 질의는 정답·오류·예측을 보기 전에 고정했다. pilot는 그 이후 해당 두 행의 ID/p0..p3만 비교 입력으로 추출했다. 원본 CSV 행의 바이트에 다른 열이 포함될 수 있지만 라벨 필드는 평가·선택·모델 입력에 사용하지 않았다.

배열 해시는 X_fit `ac254509d62c1ee0093941fe462c9539b0184e8a50d762dc8e9ba69c140869dd`, X_inner `03949c49801d7ed6e609bc38eaa9702fca1343af8bed6eb3f2e9a2e0bb3be361`다. 값과 순서의 기준은 고정 개발NPZ 및 원manifest이며, 보호된 과거 전체 F156 값의 독립 재생성을 주장하지 않는다.

## 실행과 실패 원인

pilot의 입력은 전체FIT3144, 고정INNER2, seed42, 8estimators, batch1, threads3, CPU/FP32, AMP/FA3/자동다운로드 비활성이다. 기존 pinned CPU 환경과 checkpoint를 재사용했고 설치·다운로드·합성 smoke 반복은0회다. CPU와 역사 CUDA, 2질의와 역사787질의의 조건 차이는 남아 있다.

실행 직전 가용RAM은 **3.572868347GiB**, 실행 중 최저는 **3.077396393GiB**였다. 600초 제한 또는1.5GiB 중단 기준에 닿지 않았다. 샘플링한 소유 프로세스 트리 working set 최고는572,891,136bytes(약546.35MiB), 실제 Python PID1020의 OS peak working set은569,446,400bytes였다. 이 수치는 **확률 추론 전** 비용이며 전체 문맥 추론 또는 backward의 메모리로 외삽하지 않는다. CPU 시간도 샘플 기반 마지막 관찰치이며 완전한 종료 시점 계측이 아니다.

프로세스 시작은17:44:18.304982 UTC, 종료확인은17:44:42.429237 UTC다. launcher PID27684와 자식19204/1020을 process creation identity로 추적했으며 최종 남은 소유 프로세스는0개다. 다른 프로세스를 종료하지 않았다. 실행된 소스와 로그·자원곡선·receipt는 logs/pilot_01/에 보존했다.

Traceback은 `estimator.fit(fit_x, fit_y)`가 반환한 뒤 `validate_resolved_inference_state`의 기록 dict에서 `model.cache_mode_`를 읽다 실패했음을 보여준다. 앞의 조건은 `getattr(..., None)`으로 선택 속성을 허용했지만 기록 단계는 직접 속성 접근을 사용했다. 사전검토도 이 차이를 놓쳤다. 확률 호출 전의 단계이므로 예측 품질이나 CUDA/CPU 차이를 원인으로 판단할 수 없다. 마지막 staged JSON은 exception이며, 실제 확률·비교값은 없다. 같은 회차의 수정 재실행 금지 계약을 지켰다.

## 기록의 한계와 검토

관리자 호스트 turn_context는 gpt-6-astra/high, 작성자·독립검토자는 gpt-6-luna/xhigh로 보고됐다. 요청값과 호스트 관측을 manager/의 evidence에 분리했다. 이는 호스트 설정 기록이며 모델 내부 인증이 아니다. 관리자+보조2명으로 팀의4슬롯 한도 안에서 수행했다.

exporter의 승인 해시는 DAB03947…였으나 실행 직전에 stdout 문구가 수정되어 실제 소스는08F48082…였다. 별도 검토자가 실행사본과 현행 소스의 동일성을 확인하고, stdout 세 줄만 되돌린 바이트 해시가 승인 DAB와 정확히 일치함을 재구성했다. 값 계산·입력 선택 변경은 없었지만 승인 해시와 실행 해시가 달랐다는 이력은 보존한다. 재export는 하지 않았다. pilot는 최종승인 B57F6C76…와 실제사본이 일치한다.

작성 중 exporter 파일이 한 번 상위 디렉터리에 잘못 생성됐다가 지정루트로 이동됐다. 관리자가 비어 있음을 확인한 해당 외부 하위 디렉터리만 비재귀 삭제했고, 무관한 비어 있지 않은 부모 디렉터리는 유지했다. 현재 실험 산출·실행 temp/cache·로그는 지정루트 아래다. 원자료와 이전 저장소는 수정하지 않았다.

사전검토와 결과검산은 review/precheck.json, pilot_precheck.json, independent_context_check.json에 있다. 최종 독립검토는 review/FINAL_REVIEW.md 및 review/final_review.json을 따른다. 보강된 PDF 검토 문서는 docs/20261105_검증자료_PDF반영_기술진단_보강보고서.md를 참고한다. 그 문서의0.628/0.669/0.708 제안값은 측정값이나 이번 회차 성공 기준이 아니다.

## 다음 작업과 학습

다음 round006은 **선택적 캐시 속성의 상태별 진단 코드 수정**을 먼저 검증하고, 동일 입력·질의·모델 설정으로 한 번의 replay를 수행한다. 계수학습·F1평가·OUTER 추론은 아직 진행하지 않는다. 동결된 round005 입력을 해시 확인해 복사하며 재export·질의 재선정은 하지 않는다. 모델을 불러오지 않는 작은 fake-object 검사에서 캐시 비활성/속성 부재가 허용되고 실제 설정 위반은 거부되는지 먼저 확인한다. 고정 소스 사본과 예상 해시를 실행 직전에 확인한다.

기술 산출은 입력 복구 완료와 추론 전 API 기록 오류의 국소화다. 학습 목표는 집합/순서 해시, 문맥 fit/계수학습, 재현/F1, RAM 관문/실제 추론비용을 구분하는 것이다. 학습 질문은 LEARNING_NOTES.md에 있으며 학습자의 이해나 하드웨어 동작을 검증했다고 주장하지 않는다. 세부 재개 명령과600초/1회 예산은 NEXT_SESSION.md에 있다.
