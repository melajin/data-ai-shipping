# 외부 코드와 모델

| 항목 | 출처 | 이용조건 | 패키지 반영 |
|---|---|---|---|
| TabICL2.2.0 | https://github.com/soda-inria/tabicl | BSD3-Clause | Python 소스와 LICENSE 보존 |
| TabICLv2 공개 초기 가중치 | https://huggingface.co/jingang/TabICL | 모델 카드 BSD3-Clause | public_init.ckpt,학습된 파생 가중치round63.ckpt |
| NumPy·Pandas·SciPy·scikit-learn·PyTorch 등 | 각 패키지 공식 배포 | 각 패키지의 이용조건 | requirements.txt에 버전 명시,설치 배포본의 고지 유지 |

TabICL 소스 변경은 정규화 방법의 그룹 순서를 요청 순서로 고정한 한 곳입니다. 모델의 뒤4개 FFN 게이트와 고정 배치 추론 관리자는 `src/round63/model.py`에 구현했습니다. 나머지 공개 소스의 저작권 고지는 유지했습니다.

공개 모델은 다음 논문에 기반합니다.

Jingang Qu, David Holzmüller, Gaël Varoquaux, Marine Le Morvan. TabICLv2 A better faster scalable and open tabular foundation model. arXiv2602.11139,2026. https://arxiv.org/abs/2602.11139

외부 웹 자료 확인일은2026년11월6일입니다. 데이터는 대회에서 제공된 자료이며 추가 외부 데이터는 사용하지 않았습니다.
