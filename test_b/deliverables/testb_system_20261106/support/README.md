# 시간순 입력 계약 검증

이 폴더는 사후 점수 계산과 분리된 입력 검증 도구입니다. 실제 이상점수나 경보를 만들지 않습니다. `example.jsonl`의 9행은 전부 가공한 시험 데이터이며 `archive` 행도 미확인 메타데이터 처리를 시험하기 위한 예제입니다.

이 폴더에서 Python 표준 라이브러리만으로 실행합니다.

```powershell
python -m fishing_demo.causal_replay --config config.json --check-config
python -m fishing_demo.causal_replay --config config.json --input example.jsonl --output replay_new
python -m unittest discover -s tests -p test_causal_replay.py -v
```

출력은 `decisions.jsonl`과 `summary.json`입니다. 예제는 입력 수락 3·중복 1·격리 3·판단 유보 2이며 점수와 경보는 모두 비활성입니다. 이미 존재하는 출력 폴더에는 쓰지 않습니다. 미래 시각·역순·상충 중복은 격리하며 가용 시각·시간대가 미확인인 실자료는 유보합니다. 같은 선박의 가장 최근 수락 행만 중복 판정에 보존하고, 이전 시각의 재전송은 격리합니다.

이 파일들은 상위 프로젝트의 `fishing_demo/causal_replay.py`, `tests/test_causal_replay.py`, `configs/testb_realtime.json`, `examples/testb_causal_contract.jsonl`을 복사했습니다. 외부 시스템 연결·실선 실험·실제 탐지 성능을 증명하는 자료가 아닙니다.
