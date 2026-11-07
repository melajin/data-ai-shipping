# 계약 보충 01 — 구현 오류 수정과 재현 산출물

원 PROTOCOL/CONTRACT의 수식·기간·분모·동점·Kcap·성과 관문은 유지한다.

정렬은 B0=기존score, U=U, C=C를 사용한다. U/C가RFID단위fallback이면기존score를사용한다. predictions의score는실제정렬에사용한방법점수다. 기존score와U와C가서로다른최고시각을갖는작은fixture로방법별라우팅을검증한다.

runner는후속추적을위해compute_features의반환frame을실행폴더featured_rows.parquet에저장하고해시를기록한다.같은실행의input_diagnostics.json도실행폴더에복사해보존한다.이는새특징/모델이아닌재현산출물보충이다.
