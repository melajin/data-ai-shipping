# M4-a/b 다음 tiny 합성 관문 계약

2026-11-05 KST(2026-11-04 UTC), round011 소스·기존 JSON 기반 설계. 이번 모델 실행은 0회다. 아래는 round012 구현·검토 후 유한 실행할 계약이며 측정 결과가 아니다. 목표는 마지막 층 수정의 기계적 정합성이다. 성능 비교나 실제 FIT 학습은 후속 관문이다.

## 근거와 확정 사실

경로 접두사 `PKG=environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/`. 소스별 SHA256은 함께 저장하는 source_evidence.json에 있다. 설치본 수정 금지.

| 항목 | 소스 근거 | 계약 |
|---|---|---|
| 마지막 층 | PKG `_model/learning.py:110–116`; `round004/artifacts/smoke.json`의 model.config/model.output_head_final_linear(실제 경로 rounds/round_004) | decoder는 512→1024→10. 경로 `model_.icl_predictor.decoder[2]`, W[10,1024], b[10]. shape는 과거 로드 관측이며 다음 로드 시 assertion 재확인 |
| 실제 쓰는 클래스 | learning.py:325–337 | context의 unique label 4개면 마지막 10개 중 :4만 사용. 마지막6행은 비활성이다 |
| 문맥 주입 | learning.py:265–280 | y_train은 앞 context행에만 주입. R을 in-place 변경하므로 원본 표현 재사용 시 clone 필요 |
| 클래스 변환 | `_sklearn/classifier.py:476–479`, `_sklearn/preprocessing.py:1214–1223` | LabelEncoder 정규화 후 member permutation p에 대해 context와 target 모두 p[y] |
| 복원 | classifier.py:749–775 | canonical logit[k]=member_logit[p[k]], 즉 `[...,p]` gather. `[...,argsort(p)]` gather로 바꾸지 않는다. 512/1024 hidden은 클래스축이 아님 |
| 확률 | classifier.py:610–619,758–775; learning.py:334–337 | average_logits=true이면 각 member :4 logit 복원→평균→softmax(/0.9)→행합 정규화. false는 member마다 softmax 후 평균이며 다음 실험은 true 고정 |
| gradient 차단 | classifier.py:610–620,655–663; `_model/inference.py:1226–1232` | 공식 추론은 no_grad 및 numpy 변환. predict_proba 결과에 loss를 붙이지 않는다 |
| 학습 분기 | learning.py:542–547; `_model/tabicl.py:305–359` | 전체 train forward는 별도 경로이나 이번 head-only 검증에서는 호출하지 않는다. full model은 eval/frozen 유지 |
| 전처리 | classifier.py:503–504,729–746; preprocessing.py:1207–1219 | support에 fit한 변환으로 target을 transform. 원래 실제 T5 통계의 transductive 조건을 FIT-only로 재명명하지 않는다 |

배경 문서는 rounds/round_002/IDEA_REVIEW_AND_ROUND003.md, rounds/round_002/references/algorithm_variant_ideas.md:192–234, rounds/round_003/m4_readiness/READINESS.md, rounds/round_004/runtime_author/replay_contract.json이다. incoming의 `references/...`는 루트 경로가 아니라 round002 아래 사본으로 해소했다. 옛 READINESS의 미확인 상태는 당시 기록이다. round010은 실제 두질의 수치재현을 얻었으나 출처 전체관문은 실패했으며 이를 해소했다고 하지 않는다.

## 고정 입력과 한 번의 표현 생성

합성 seed=20261112, FP32 정규난수 context16×8/target4×8, context 라벨 [0,1,2,3] 4회 반복, target 라벨 [0,1,2,3]. ID는 synth_context_00..15와 synth_target_00..03으로 분리한다. 실제 선박 데이터·NPZ·reference·OUTER·holdout은 읽지 않는다. target 라벨은 생성한 뒤에도 predict 경로에 넣지 않고 head loss에만 사용한다.

TabICL2.2.0/Torch2.6.0+cpu, pinned checkpoint bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0, CPU/FP32, threads3, AMP/FA3/KV false, allow_auto_download=false, n_estimators4,batch_size1,norm_methods=['none'],feat_shuffle_method='none',class_shuffle_method='shift',temperature0.9,average_logits=true. 작은8특징은 읽기 경로 검증용 선택이며 F156/312 실자료 정합성이나 성능 검증이 아니다. COL/ROW chunk adapter는 이 작은 입력에서 사용하지 않는다.

checkpoint load1/context fit1/predict_proba1, native full model forward는 실제 ensemble4개로 최대4회다. 실제 생성 view 수가4가 아니면 실패하고 자동 설정 변경/재시도하지 않는다. 마지막 Linear에 read-only forward-pre-hook과 forward-hook을 설치해 member별 H[B,20,1024]와 출력[B,20,10]을 관찰한다. 원 출력/입력을 바꾸지 않고 finally에서 hook 제거를 확인한다. capture의 member 순서와 generator의 norm/view/permutation 순서를 대조한다. target4행만 모아 H[4,4,1024]와 raw logits[4,4,10]을 만든다.

H는 추론 완료 후 detached clone으로 일반 학습 텐서로 만들고 requires_grad=false를 고정한다. no_grad로 만든 표현은 허용한다. inference_mode 텐서 여부를 확인하고 모드 밖 clone을 한다. upstream checkpoint parameter/buffer hash·requires_grad·mode·hook 상태를 전후 대조한다. readout은 모델 밖 사본에서만 학습한다. target 라벨이 context에 들어간 표현을 캐시하는 경로는 금지한다.

## 후보·학습 예산

- M4-a: W0.clone만 trainable[10,1024](10,240개), b0는 고정. :4 손실의 직접 유효 가중치는4096개.
- M4-b: W0/b0 고정, A[2,1024] 정규 std0.01, B[10,2]=0, scale1. trainable2068개, :4 직접 유효2056개. W_eff=W0+B@A. 둘 다 동일 H/target/view, SGD lr0.001, momentum0,weight_decay0, 정확히2step, full4-view×4target batch. 후보 선택·hyperparameter 탐색0.
- 손실은 member의 첫4 logits와 해당 p[y_target]의 unweighted cross_entropy 평균이다. temperature는 평가확률 변환에만 적용한다. 초기 CE와 step별 CE는 진단값이며 감소를 성능 채택 조건으로 쓰지 않는다.
- a 첫 gradient는 유한·비영, 비활성6행 zero. b 첫 B gradient 유한·비영, A gradient zero는 정상; step2 A gradient가 유한·비영인지 확인. B 비활성6행과 a 비활성6행·모든 bias가 정확히 불변이어야 한다. optimizer 범위 밖 param에 grad가 없어야 한다.

## 무변경·병합·재로드와 호출 상한

전체 표현 추출 이후 head는 H[4,4,1024] 전체에 배치 호출한다. 독립 head 평가 최대12회: base 재계산1, a/b 초기2, a/b 학습2step씩4, a post/reload2, b post/merge/reload3. 이 밖의 full forward/predict/context fit 추가0. gradient backward 총4회. 테스트 설계상 추가 호출이 필요하면 실행 전 소스검토에서 예산을 명확히 정하고 계약을 변경해야 하며 결과를 본 뒤 확대하지 않는다.

base H@W0^T+b와 캡처 logit, reconstructed canonical probabilities와 predict 결과를 대조한다. a 초기복사와 b B=0 초기수정은 base와 같은 계약이다. raw logit maxabs≤1e-5, canonical probability maxabs≤1e-6, argmax 전부 일치, finite/[0,1]/행합오차≤1e-6. exact 여부도 별도 기록한다. 작은 합성에도 오차 문턱을 못 맞추면 관문 실패로 두고 느슨하게 변경하지 않는다.

a 학습 W/b를 head-only state_dict로 저장하고 새 Linear에 읽어 비교한다. b unmerged 출력과 새 Linear에 W0+B@A를 한 번만 병합한 출력, 그 head-only state_dict 재로드 출력을 동일 H로 비교한다. tolerance는 위와 같고 bias exact 불변. 원본 W0를 덮어쓰지 않으며 중복 merge 요청은 오류로 거부한다. 저장물에는 원 checkpoint SHA/shape/dtype/seed/permutation/temperature/average_logits/변경 범위를 기록한다. 이는 head-only reload이며 전체 수정 모델의 실제 predict/저장/reload 검증으로 확대하지 않는다. 전체 integration은 다음 별도 관문이다.

## 자원·운영·실패 분기

다음 관리자 최대30분, stdlib static/mock1회≤30초+결함 수정 뒤 최대1회, synthetic 실행1회 총180초(계산170+정리10), retry0. 실행 전 source freeze와 wrapper+실행사본 승인해시 일치, no-edit ACK, successful exact-map mock 필요. 실행 직전 가용 RAM≥3GiB, 실행 중<1.5GiB면 소유 child만 중지. threads3, 동시계산1, GPU/설치/네트워크/유료0. PID/생성시각/자원곡선/stdout/stderr/receipt를 보존한다.

예상 peak≤1.5GiB는 보수적 계획 가정이다. checkpoint110,368,038bytes/FP32 모델 약105MiB와 로딩 사본, Torch 런타임, tiny forward 임시값을 포함한 여유다. H 전체4×20×1024×4=327,680bytes, 학습 target H65,536bytes, head W40,960bytes이며 head 사본·gradient는 작다. round004 tiny16×312 관측과 round010 실문맥 sampled peak 약1.18GiB는 참고값일 뿐 이 실행 상한이나 학습 시간 예측이 아니다. round010의215초로 학습비용을 환산하지 않는다.

RAM 부족이면 wrapper/소스/문서 작업 후 실행 직전 재확인한다. 반복 polling 금지, 사용자 프로세스 종료 금지. source 검토 미완료·view/shape 불일치·gradient 실패·hook 미복원·hash drift·timeout/RAM 중단은 각각 다른 원인으로 기록한다. 허용1회 소진 후 같은 실행을 반복하지 않는다. 전체 모델 학습/F1/실자료 확대는 없다.

기술 성공은 readout 복사·순서·gradient·병합·head reload 정합성뿐이다. 학습 질문: p[y]와 out[...,p]는 왜 짝인가? B=0일 때 A gradient0은 왜 정상인가? head parameter가 적어도 표현 생성 비용은 왜 남는가? 캐시를 만들기 전에 support/target을 나누는 이유는? 학습자 이해 달성은 별도 확인한다.
