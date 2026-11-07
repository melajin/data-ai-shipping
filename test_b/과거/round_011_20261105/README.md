# Round011 시간과 위치를 고려한 행동 변화 실험

사용자 결정: **lin_raw를 특징 후보로 채택한다.** 표류의 물리적 정답을 가정하지 않고 같은 선박의 시간·위치별 과거 행동과 비교하는 가설을 고정해 실험했다.

- [실험 결과와 해설](ROUND011_실험결과보고_20261105.md)
- [결과 계산 전에 저장한 계약](PROTOCOL.md)
- [별도 검토자의 검증 범위](AUDIT.md)
- [구조화 결과](summary.json), [사건별 성과](event_metrics.csv), [시각별 특징·참조·점수](timestamp_scores.csv)
- [전체 실행 기록](execution.json), [단계별 메모리 확인](memory.json), [합성 테스트 기록](synthetic_validation.json), [검산 결과](audit.json)

T는 시간대 비교, L은 위치 비교, TL은 두 조건을 함께 적용한 비교다. 각 현재 시점까지의 후행7시간을 과거24~720시간의 서로 다른10일과 비교한다. 부족한 이력은 unknown으로 남긴다. 정확한 품질 조건과 정렬·동률·다중비교 규칙은 계약을 따른다.

lin_raw는 유효 시간행의 bbox_m/len_m 평균이다. `activity`는 낮은 관측 경로량의 상대 순위, `joint`는 그 값과 중심점 이동 상대 순위의 곱이다. 실제 표류·기관 상태·실제 속력 정답으로 해석하지 않는다. 모든 방식은 같은 공통 후보 시각에서 평가한다.

재현 시 저장된 결과를 덮어쓰지 않도록 저장소 루트에서 새 출력 폴더를 지정한다. 실행 직전 현재 RAM을 다시 확인하며 다른 실제 데이터 계산과 병행하지 않는다.

```powershell
python -B -m unittest discover -s testB/round_011_20261105 -p test_experiment.py -v
python -B -X utf8 testB/round_011_20261105/run_experiment.py --output-dir testB/round_011_reproduction_NEW
```

기존 저장 결과의 독립 검산은 위 실험 프로세스가 끝난 뒤 실행한다. 현재 검산 스크립트의 대상은 스크립트가 위치한 Round011 폴더다. 다른 출력 폴더를 검산하려면 그 폴더에 audit_round011.py, run_experiment.py, PROTOCOL.md를 복사한 뒤 그 폴더의 audit_round011.py를 실행한다. `execution.json`이 가리키는 입력과 실행 코드 해시도 함께 확인한다.

```powershell
python -B -X utf8 testB/round_011_20261105/audit_round011.py --sequential-ready
```

코드 테스트와 실제 dev 평가를 구분한다. 새 모델 학습·2025 테스트·공식 제출·장치 실험은 이 라운드의 실행 범위가 아니다. 이전 라운드 산출물의 보존 확인은 source_manifest_before.json과 source_preservation.json을 따른다.
