# Test A — 조업형태 분류 제출 자료

사용자가 제공한 `대회_최종제출_20261106.zip`의 모델자료를 [Round63 통합 패키지](round63_submission_20261106/)에 원래 구조대로 보관했다. Test B의 [독립 실행 패키지](../../test_b/deliverables/testb_system_20261106/)와 같은 방식으로 자료, 모델, 코드, 결과와 검증 기록을 찾아볼 수 있다. Round63 폴더 자체에는 과제1과 함께 원본에 포함된 과제2 사본도 있다.

| 구분 | Test A 자료 | 내용 |
| --- | --- | --- |
| 시작 | [원본 통합 README](round63_submission_20261106/README.md), [모델 설명](round63_submission_20261106/docs/과제1_모델설명.md) | 방법, 조건과 원본 실행 방법 |
| 입력 | [data](round63_submission_20261106/data/) | Test A 특징, FIT 문맥과 재현용 데이터 |
| 모델 | [model](round63_submission_20261106/model/) | 특징 목록·정책·출처. 가중치 두 파일은 아래 제한 참조 |
| 소스 | [src](round63_submission_20261106/src/), [scripts](round63_submission_20261106/scripts/) | 특징 생성·분류·학습 재현·제출 파일 통합 |
| 분석 | [notebooks](round63_submission_20261106/notebooks/), [figures](round63_submission_20261106/figures/) | 추론과 학습 재현 노트북, 평가 그림 |
| 결과 | [outputs](round63_submission_20261106/outputs/) | 100척 예측 CSV와 통합 제출 양식 |
| 검증 | [validation](round63_submission_20261106/validation/), [licenses](round63_submission_20261106/licenses/) | 원본 검증 기록, 파일 목록·해시와 외부 모델 라이선스 |

## 원본에 기록된 방법과 결과

제공 항적에서 형상·공간·시간 특성 337개를 만들고, 고정 FIT 문맥 4,423척과 Round63 TabICL 기반 모델로 네 조업형태를 분류한다. 원본 문서에는 학습 7,372척을 FIT 4,423척, TUNE 1,474척, REPORT 1,475척으로 분할한 것으로 기록돼 있다. 원본 REPORT 결과는 903/1,475척, micro-F1 0.612203, macro-F1 0.563424다. REPORT는 여러 회차의 개발 검토에 사용됐으므로 독립 평가나 공식 대회 성적으로 해석하지 않는다. 원본의 회귀 검사 기록은 기존 예측과 2,949척의 최종 분류가 일치한다고 적고 있다. 이번 정리에서 추론이나 재학습을 다시 실행한 것은 아니다.

원본은 Python 3.12.14, NVIDIA RTX 3060 Ti 8GB 및 지정된 PyTorch/CUDA 환경에서 실행했다고 기록한다. 원자료를 이용한 특징 생성에는 별도의 주최 측 CSV가 필요하다. 실제 실행 전 장비와 가용 RAM·GPU 및 의존성을 확인한다. 서로 다른 실험 기록의 현재 상태는 작성 시점과 평가 조건을 함께 확인한다.

## 보존과 GitHub 제한

압축파일의 모델자료에서 추출한 원본 파일 250개는 제공된 `validation/manifest.json`과 크기 및 SHA-256이 모두 일치했다. 별도로 원본 최상위 리더보드 엑셀을 `outputs/leaderboard_original.xlsx`로 복사했으며, 패키지의 `outputs/제출결과_최종.xlsx`와 SHA-256이 같다.

로컬 폴더에는 `model/round63.ckpt`(118,745,364바이트, SHA-256 `6bd605c14ed880c9561908baa4cba49c35bdbd093474d226f54ef4e1d3eb69d2`)와 `model/public_init.ckpt`(110,363,492바이트, SHA-256 `a8eea5928ae4ab58cdfaffbd01df0a860e802b2fc06a148f9e205c0f6fec078c`)가 있다. 두 파일은 GitHub 일반 파일 크기 제한을 넘고 기존 대용량 바이너리 제외 설정에 해당하므로 GitHub에는 포함하지 않는다. GitHub에서 받은 패키지로 추론·재학습하려면 사용자가 제공한 원본 ZIP에서 각 파일을 같은 `model/` 경로에 복원하고 위 해시로 확인해야 한다. 다른 코드와 데이터는 그대로 보관하며, 주최 측 자료의 외부 재배포 조건은 원본 설명대로 별도 확인이 필요하다.
