# 통합 보충 01 — 명시적 시간 단위와 예측 고정 시점

실제 실행 전 총괄이 API 경계를 확인했다. 원 ts는정수 epoch-hour다. 규칙모듈의unit없는pd.to_datetime은이정수를나노초로해석할수있다. runner는unit=h로변환하고있어그경로에서는맞지만공개API와계약이불일치한다. 평가기의작은Timestamp값을시간정수로재해석하는휴리스틱도제거한다. 결과나임계값을보고변경하는것이아니다.

정수ts입력은명시적unit=h,이미datetime입력은시간정렬/alignment를검증한다. 규칙모듈의내부/반환ts는정규화된hour-aligned datetime으로명시하고ledger에source_ts_hour정수도남겨원단위계보를보존한다. predictions/run_registry의시간필드도같은정규화표현이다. evaluator는명시적epoch-hour변환만사용한다. NaT나시간경계밖선택시각을0/다른단위로추정하지않고명시오류로처리한다. censored close_ts의NaT는원래의미대로남긴다.

geometry_valid는원계약대로len/bbox의유한·비음수다. 위치가없는행도지속길이를관찰할수있으며좌표는순위에사용하지않으므로좌표결측을추가탈락조건으로넣지않는다.

runner는build_rules뒤predictions/pools/runregistry/ledger를저장하고예측파일해시를기록한후사건표를parse한다. 기존순위와후보수계약은유지한다. 원완성소스를각담당자가implementation_fixes에보존하고필요한작은입출력단위fixture만추가한다.
