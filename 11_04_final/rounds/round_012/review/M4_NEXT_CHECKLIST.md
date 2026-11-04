# 다음 회차 tiny 합성 M4 실행 체크리스트

작성 범위: round011의 `m4_contract/M4_CONTRACT.md`, `m4_contract/source_evidence.json`, `review/M4_REVIEW.md`에 근거한 준비 체크리스트다. round012에서는 M4 모델 실행을 하지 않는다. 아래 항목은 실행 전 계약 점검이며 실행 결과나 성능 증거가 아니다.

## 착수 전 차단 조건

- [ ] 새 회차의 작성자 소유 코드와 runner가 준비되고, 파일 목록·SHA-256을 기록한 candidate ACK 뒤 쓰기가 동결됐다.
- [ ] 독립 검토자가 새 승인 map을 직접 해시로 생성했고, 관리자 실행 사본과 현재 파일이 동일 map에 맞는다. 승인 뒤 수정이 있으면 승인을 취소하고 재검토·새 mock을 한다.
- [ ] wrapper가 바뀐 fresh source freeze 후, 명시적 exit 0/7을 내는 child를 순차 최대 2개로 실행하는 process-control smoke 1회를 먼저 끝낸다(전체 ≤10초, retry 0). 각 receipt의 정수 exit code, owned-process 종료확인, stdout/stderr를 검증한다. 그 뒤 exact-map stdlib mock을 실행한다. hash pre/post와 cleanup/residual도 남기며 null은 실패다.
- [ ] source freeze, snapshot, live/current hash, numeric result, audit integrity, 역사 전체 gate를 별도 필드로 기록한다. round010의 역사 전체 gate는 계속 false다.
- [ ] 모델 실행 직전 가용 RAM이 3 GiB 이상이고, 다른 작업·예상 peak≤1.5 GiB·threads≤3·동시 계산 1개를 기록했다. 부족하면 독립 문서/소스 작업 뒤 실행 직전에 재확인한다. 실행 중 가용 RAM 1.5 GiB 미만이면 소유 child만 중지한다.
- [ ] 30분 관리자 상한, static/mock 각 최대 30초(허용된 결함수정 후 mock 1회 추가), synthetic 최대 180초(계산 170초+정리 10초), synthetic 재시도 0회를 고정했다. GPU·설치·네트워크·유료 자원은 0이다.

## 합성 입력 및 모델 경계

- [ ] Python/Torch/TabICL 버전·CPU/FP32 설정, pinned checkpoint SHA, checkpoint 자동 다운로드 금지, `n_estimators=4`, `batch_size=1`, `threads=3`, `norm_methods=['none']`, feature shuffle none, class shuffle shift, `temperature=0.9`, `average_logits=true`를 기록한다.
- [ ] seed `20261112`, context 16×8과 target 4×8의 합성 입력을 고정한다. context label은 `[0,1,2,3]` 각 4회, target label은 `[0,1,2,3]`이며 ID 범위는 context와 target로 분리한다.
- [ ] 실제 데이터·NPZ·reference·OUTER·holdout 입력은 열지 않는다. target label은 `fit` 또는 `predict_proba`에 전달하지 않고 외부 head loss에만 쓴다.
- [ ] checkpoint load 1회, context fit 1회, `predict_proba` 1회, 생성된 4 view에 대해 native full-model forward 최대 4회를 지킨다. view 수가 4가 아니면 자동 설정 변경이나 재시도 없이 실패로 기록한다.
- [ ] 마지막 Linear가 `decoder[2]`, W `[10,1024]`, bias `[10]`인지 실제 load 후 assertion한다. 이는 과거 smoke 관측에 기반한 기대 shape다. 모델 parameter/buffer hash·requires_grad·eval/frozen 상태와 hook 상태를 전후 대조하고 hook은 finally에서 제거한다.
- [ ] hook은 입력과 출력을 바꾸지 않고 관찰만 한다. 근거 소스 `learning.py:265–280`은 context `y_train`을 앞 `train_size`행에 in-place 주입하고 마지막 decoder를 전체 row tensor에 적용한다. `_predict_standard`는 decoder 뒤 `out[:, train_size:, :num_classes]`로 결과를 자르므로, decoder hook 자체는 label-bearing context 16행과 target 4행을 모두 본다. 따라서 hook 원본 tensor 전체를 학습 캐시나 loss에 넘기지 말고, 확인된 `train_size==16`으로 명시적으로 `[:, 16:]`만 취해 target-only H `[4,4,1024]`와 raw logits `[4,4,10]`를 만든 뒤 shape/ID를 assert한다. Context의 hidden state/logits는 비교·loss·head 학습에 쓰지 않는다.
- [ ] member 순서를 class permutation 순서와 대조한다. H는 target-only 분리 뒤 detached clone이며 `requires_grad=false`다. target label은 생성 즉시 head loss용 변수로 분리하고 context 입력/`fit`/`predict_proba` 인수·callback·hook capture 처리 경로에 포함되지 않았음을 코드와 실행 인수 기록으로 확인한다.

## Head mechanics 및 엄격한 판정

- [ ] canonical 복원은 member output `[..., p]`로 하고 `argsort(p)`를 쓰지 않는다. 첫 4 logit만 loss에 포함하며 마지막 6개 output row는 비활성 상태를 확인한다.
- [ ] base logits, 캡처 logits, canonical probabilities와 `predict_proba`를 비교한다: raw-logit maxabs≤1e-5, 확률 maxabs≤1e-6, argmax 완전 일치, finite/[0,1]/행합오차≤1e-6. exact equality도 별도로 기록한다. 문턱을 결과 확인 뒤 완화하지 않는다.
- [ ] M4-a는 W0 clone만 학습하고 bias를 고정한다. M4-b는 W0/bias 고정, A `[2,1024]` 정규 std 0.01, B `[10,2]=0`, scale 1로 `W_eff=W0+B@A`를 쓴다. 두 후보 모두 같은 H·target·view, SGD lr 0.001, momentum 0, weight decay 0, 정확히 2 step이며 후보 탐색은 없다.
- [ ] 손실은 view별 첫 4 logit과 `p[y_target]`의 unweighted cross entropy 평균이다. temperature는 평가 확률 변환에만 쓴다. 초기/step별 CE는 진단값이고 채택 기준이 아니다.
- [ ] gradient 계약: M4-a 첫 gradient는 finite/nonzero, 비활성 6행은 zero. M4-b 첫 B는 finite/nonzero이고 A=zero는 정상, step 2의 A는 finite/nonzero. 비활성 B행과 모든 bias는 정확히 불변이며 optimizer 밖 parameter의 gradient는 없어야 한다.
- [ ] 추출 후 head-only 평가 최대 12회, backward 총 4회다. M4-a state_dict reload와 M4-b unmerged/1회 merge/head-only reload를 같은 H로 비교한다. bias 불변은 exact로 검사하고, 재요청 merge는 오류로 처리한다. 원 W0를 덮어쓰지 않는다.
- [ ] 산출물은 head-only state와 checkpoint/config/seed/permutation/변경 범위 증거다. 전체 수정 모델의 predict·저장·reload integration 검증으로 확대하지 않는다.

## 실패 분기와 해석 한계

- [ ] shape/view/order 불일치, target label leakage, gradient invariant 위반, hook 미복원, checkpoint/source hash drift, timeout, RAM 중단을 서로 다른 원인으로 기록한다. 계약 실패 뒤 실행 재시도는 없다.
- [ ] 구현·실행 중단 시 코드 수정이 필요하면 다음 source-freeze 절차로 넘긴다. 승인된 파일을 실행 시작 뒤 수정하거나 과거 receipt를 고치지 않는다.
- [ ] 결과는 합성 head 복사·순서·gradient·merge·head-only reload의 기계적 정합성으로만 해석한다. 실제 FIT 통합, 성능 향상, F1, 독립/공식 점수, runtime 성능을 입증하지 않는다.
- [ ] 학습자가 설명할 질문: 왜 `p[y]`와 `out[...,p]`를 짝지어야 하나? B=0에서 첫 A gradient가 0인 이유는? head parameter가 적어도 표현 추출 비용은 왜 남나? support와 target을 cache 전에 분리하는 이유는?

## 근거·미확인 사항

근거 파일은 `rounds/round_011/m4_contract/M4_CONTRACT.md`, `rounds/round_011/m4_contract/source_evidence.json`, `rounds/round_011/review/M4_REVIEW.md`다. 이전 검토는 설치 소스와 저장된 smoke metadata의 SHA·내용을 확인한 source review이며 checkpoint를 새로 load하지 않았다. 다음 회차의 실제 process exit, RAM, checkpoint load 결과, tensor shape, gradient, tolerance 결과 및 head reload 결과는 아직 미확인이다. 요청 모델/effort와 host가 실제 확인한 세션 메타데이터는 구분해 기록해야 하며, 문서 설정만으로 실행 모델을 인증하지 않는다.
