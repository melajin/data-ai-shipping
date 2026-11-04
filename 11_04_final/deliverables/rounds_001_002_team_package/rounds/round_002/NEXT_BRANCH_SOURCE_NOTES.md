# 후속 월별 특징 후보의 소스 메모

이 파일은 Round 002 결과를 보기 전 읽기 전용 코드/문서 조사이며 후속 실험 실행 또는 채택 결정이 아니다.

- 원 저장소 prefix: D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104.
- reports/temporal_final.md에 기존 monthly_repeat 35열의 seed42 none_micro 대비 개발 +26척, micro delta .004409, bootstrap CI [-.001696,+.010853]가 기록돼 있다. 이번 sqrt_macro 및 분리 ES 기준선과 직접적인 같은 조건 비교가 아니다.
- experiments/exp03_temporal_ablation.py와 code/temporal_cache_adapter.py의 load_vessel_block을 읽었다. 기존 loader는 temporal_vessel_features.parquet 전체를 pd.read_parquet로 읽은 뒤 year/ID 필터를 적용한다. 현재 holdout 경계에 그대로 사용하지 않는다.
- 후속 개발 특징 추출이 허용되면 manifest의 monthly_repeat 열 목록을 먼저 확인하고, Arrow dataset의 year=2026 및 개발5897 ID predicate와 필요한 열 projection을 적용한 뒤 결과를 materialize하는 새 loader를 작업루트에 작성한다. 전체 표를 읽어 놓고 나중 필터하지 않는다. 사용할 라이브러리 API와 실제 반환 명부를 검증한다. 전체 파일 bytes SHA256 검사는 개별 특징 해석과 구분한다.
- 기존 v3 cache 경로: artifacts/temporal_cache_v1_20261104_v3/temporal_vessel_features.parquet; 문서 SHA256 7ee125a78076ec0c57615b5c4ca745141bf56914920651556c41cea076cc663a. manifest 문서 SHA256 bdc90db88ec50574e19ae0ec6ed1d20eab7a7f4ec1f43d6ce411e88a5717bfb8. 이 회차에서는 파일을 다시 해시하거나 표를 읽지 않았다.
- 부분선 연결, 실제 속력/가속도 계산, 구간 행동 정답 생성은 추가하지 않는다. 월별 결측 mask와 0관측 구분을 보존한다.
