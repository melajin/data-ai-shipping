# 팀원 관찰 기반 이름표 재검사

`ROUND_PLAN.md`는 실행 전 고정 기준이고, `run_experiment.py`가 학습·선택·동결·평가를 수행한다.
기존 Round026·027은 수정하지 않는다. 팀원 수치는 이 실험의 가설 근거만으로 쓴다.

PowerShell, 프로젝트 루트에서 실행:

```powershell
python -X utf8 11_04_final/rounds/round_027_team_recheck/run_experiment.py
python -X utf8 11_04_final/rounds/round_027_team_recheck/verify_results.py
```

실행 전 가용 RAM>=1.5GiB 필요. 실행기는 시작/각 fold/평가 전 RAM을 검사하고
1개 프로세스·1스레드·BelowNormal로 실행한다. 부족하면 계산을 중단하고 기록한다.
검산기는 표준 라이브러리만으로 저장 예측·지표·명부 분리·선택 규칙·입력 해시를 확인한다.

이 실험은 기존에 노출된 개발 선박 5,897척의 진단이며, 독립 성능 검증이나 최종 모델 채택이 아니다.
