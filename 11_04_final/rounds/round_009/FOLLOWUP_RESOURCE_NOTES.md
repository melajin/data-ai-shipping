# 실제 재현 후속의 자원·계약 메모

작성 시점에는 round009 합성 실행 전이며 후속 실제재현 실행 승인은 별도 NEXT_SESSION 최종 계약에 따른다. 실제 배열을 읽거나 추가 추론하지 않았다.

round008 마지막 증거는 첫 column manager 호출 완료이며 ColEmbedding 전체 return/ROW 진입 증거가 아니다. 다음 실제재현을 설계할 경우 ROW와 ICL의 진입·완료를 기존 호출 안에서 기록해야 한다. 관측용 독립 forward를 추가하지 않는다.

정적 소스 learning.py:241–282에서 ICL은 R(B,T,D)에 FIT 라벨을 더하고 전체 T를 tf_icl에 전달한다. learning.py:326–337은 ICL 호출 이후 query 확률만 잘라낸다. 따라서 rowchunk8만으로 전체 실행 메모리 안전을 보장하지 못한다. ICL의 전체 문맥, feature grouping/조립, 입력 복사와 라이브 텐서는 남아 있다. ICL T를 임의 분할하는 후속은 금지한다.

round008 실제 column call0 출력 1×223×3146×128×4bytes는 약0.335GiB다. 이는 출력 한 텐서의 계산된 크기일 뿐 전체 모델 peak가 아니다. rowchunk8은 각 ROW forward의 행배치를 제한하지만 column 출력 자체를 줄이지 않는다. 앞선 sampled tree peak 약2.96GiB와 시작RAM약4.14GiB에서의 중단을 실제 재현 자원 계획의 위험 근거로 유지한다. tiny synthetic peak를 그대로 전체문맥 예상 peak로 쓰지 않는다.

성공 후 다음 실제 재현은 고정 FIT3144/INNER2, 동일 checkpoint/settings/feature/순서를 유지하고 col16+row8만 적용하는 1회 제한 비교가 적절하다. 시작 RAM뿐 아니라 수정 경로와 남은 메모리 위험을 검토한다. 부족하면 문서/계절특징 소스·metadata 계약 검토 후 재확인한다. 실행 중 RAM 중단이면 자원 회복만을 이유로 같은 실험을 재시도하지 않는다. 정확한 단계 기록을 근거로 다음 가설을 바꾼다.

계절 가설은 round008/SEASONAL_FOLLOWUP_DESIGN.md를 그대로 별도 후속으로 보존한다. 월관측량과 월별 형태/지역 변화를 분리하는 비교, 결측mask, 선박단위 분할, native hour/timezone 미확정, 반년자료 한계를 유지한다. 현재 입력에 계절특징을 섞지 않는다.
