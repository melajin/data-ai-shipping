# Round019 — 선박 단위 판정력 실측

이 폴더의 최종 결론은 `ROUND019_보고서.md`, 계산 결과는 `execution_001/summary.json`에서 확인한다. 계산이 완료되기 전에는 `score_metadata.json`의 status와 로그를 확인한다. 실행 중 체크포인트는 최종 결과가 아니다.

- `PROTOCOL.md`: Round019 결과 확인 전 지표·방향·매칭·검정·판정 기준·시나리오를 고정한 문서.
- `score_fleet.py`: 허용된 2026 월별 요약을 청크로 파티션하고, 선박별 전체 이력을 고정 함수로 점수화.
- `evaluate.py`: 잠정 연결 목록을 이용한 미통제/관측 수 통제 비교, CI, 고정 임계값 sweep 및 F1 시나리오.
- `test_score_fleet.py`, `test_evaluate.py`: 합성 자료를 이용한 구현 검증. 실제 선단 성능과 구별한다.
- `execution_001/vessel_peaks.csv`: 라벨을 보지 않고 산출한 선박별 지표.
- `execution_001/evaluation_vessels.csv`: 제공된 잠정 연결 소속 여부를 더한 평가용 표.
- `execution_001/auc_results.csv`, `matched_sets.csv`, `distributions.csv`: AUC·매칭·분포 근거.
- `execution_001/threshold_sweep.csv`, `expected_f1.csv`: 사전 지정 임계값 및 p 가정별 계산. 공식 F1이나 배포 임계값 아님.
- `execution_001/score_progress.jsonl`, `stdout.log`, `score_metadata.json`: 실행 진행·RAM·완료 근거.
- `execution_001/source_checksums_before.json`, `source_checksums_after.json`: 입력·고정 함수·기준자료 보존 검증.
- `AUDIT.md`, `run_record.json`: 독립 검토 및 요청 모델/effort·계획 동결 기록.

새 점수화는 저장소 루트에서 새 execution 번호로 실행한다. 기존 입력은 수정하지 않는다.

```powershell
python -B testB/final/round_019_vessel_discrimination_20261106/score_fleet.py --output testB/final/round_019_vessel_discrimination_20261106/execution_002
```

점수화가 완료되고 오류가 없으면 같은 새 실행 폴더를 평가한다.

```powershell
python -B testB/final/round_019_vessel_discrimination_20261106/evaluate.py --output-dir testB/final/round_019_vessel_discrimination_20261106/execution_002
```

이번 `execution_001`은 순차 실행 827척 이후 `score_fleet_parallel.py`로 전환했다. 원 코드는 보존했고, 완료 체크포인트를 4개의 서로 다른 파티션 작업에 배정했다. 전환·기존 프로세스 종료·단일 감독 프로세스·기존 오류 없음 검증은 `parallel_migration.json`, `parallel_runtime_guard.json`에 있다. helper는 이번 실행 전용으로 `execution_001`에 고정돼 있으므로 일반 재실행 명령으로 사용하지 않는다. 새 실행은 위 순차 명령을 기준으로 한다. helper의 일반 재사용 잠금·오류 전파·worker 수 변경 제약은 `AUDIT.md`에 공개한다.

장시간 실행은 숨김 백그라운드로 실행하고 stdout/stderr를 새 실행 폴더에 남긴다. 메모리 부족으로 보류되면 다른 작업 뒤 실행 직전에 RAM을 다시 확인한다. 체크포인트 재개는 동일 코드·입력·기준자료 해시가 유지될 때에만 `--resume`을 사용한다. RAM 확보를 위한 polling/watch나 사용자 프로세스 종료는 하지 않는다.

범위는 제공된 2026 요약과 이미 제공된 잠정 연결 관계의 평가까지다. 새 선박 재식별·다른 자료와 ID 조인·2025 테스트 적합·실시간 서비스·공식 제출은 수행하지 않는다. 사고 미연결은 확정 정상과 같지 않다.
