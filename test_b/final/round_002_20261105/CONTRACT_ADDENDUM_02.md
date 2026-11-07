# 계약 보충 02 — 후보군별 무작위 기대 집계 복구

원래 계약의 pool별 random 기대를 별도로 집계한다. 정확 확률식 자체는 변경하지 않는다.

- base: 각 사건의 전체 base 풀과 B0_full의 실제 Kcap으로 계산한다.
- common: 각 사건의 common 풀과 min(K,common_n)으로 계산한다. 없는 경우 n=0,p=0임을 명시하고 common 존재 조건부 평균도 별도로 제시한다.
- C_matched: common이 존재하면 common의 확률, 없으면 fallback이 실제 사용하는 base의 확률로 계산한다. U에도 같은 pool이 적용된다.
- 전체100과Tier01=60 각각 pool별 event확률과 평균을 보존한다. 서로 다른 pool 레코드들을 섞어 평균내지 않는다. 주 random 관문에는 Tier01 C_matched top1을 쓴다.
- event_results의 B0_common candidate_count는 항상 common_n이며, 빈 풀에서0이다. U/C의 fallback과 B0_full은 base_n이다.

fixture는 common 1개와3개인 사례, common0으로basefallback인사례를섞어각pool평균을독립계산한기대와대조한다. 기존 routing fixture는 유지한다. 수식·기간·분모·기존 성과기준·case선택은 바꾸지 않는다.
