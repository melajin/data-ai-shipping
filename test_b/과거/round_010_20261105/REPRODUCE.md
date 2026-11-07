# Round010 비교 재현

현재 루트의 t1_decompose.py는 초기 경합의 Codex 사본이며 Gemini 원 생성 소스로 쓰지 않는다. 루트 원 보고서는 comparison_20261105/original_root_snapshot에 있다. 원 수치·코드를 덮어쓰는 구형 실행 대신 아래 새 비교 스크립트를 쓴다.

작업공간 루트에서:
```powershell
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" compare_results.py
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" audit_report_claims.py
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" t3_recompute.py --evidence-only
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" write_final_reports.py
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" closeout_round.py
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" validate_final_artifacts.py
```

원 parquet 재계산은 RAM을 실행 직전에 확인하는 아래 명령이다. 메모리 미달이면 raw_status=deferred_memory로 돌아오며 전체 원자료 완료로 세지 않는다. 선택 로딩·변환은 순차 실행이고 사용자 프로세스를 종료하지 않는다.
```powershell
python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" t3_recompute.py
```

가정: Python 표준 라이브러리, 원자료 재검산에는 현재 환경의 PyArrow. 검산은 생산 함수와 SciPy의 검정 함수를 import하지 않는다. 과거 Codex 2000회 사건 bootstrap은 원 NumPy 결과를 보존하고, 별도 군집 bootstrap은 Python Random seed20261105의 사후 민감도다.
메모리 예산의 변경 근거·실제 관측 RSS·가용 RAM은 t3_memory.json에 모두 남겼다. 초기에 보수적 512MiB 추가 여유를 중복 요구한 시도와 총 RSS 기반·관측 보정 예산을 구분한다. 가용 RAM reserve 1GiB는 대용량 검산에서 유지한다.
별도 세션 T3 승인은 이 재현 명령이 대신하지 않는다.
