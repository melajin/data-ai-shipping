# 규칙 API 수정 확인

작업자 msg_340896711ce1이원소스보존과수정을보고했다. 총괄은_normalize_hour_timestamps에서정수→unit=h,datetime→hour-alignment검증,source_ts_hour계보를직접확인했다. geometry는좌표결측과분리됐다. 추가fixture는정수/동등datetime결과일치·나노초오해거부·좌표NaN허용을포함하며작업자검사가통과했다.

실제개발자료는아직실행하지않았다. evaluator/runner의명시단위변환·사건parse전예측저장수정완료보고를받고연결한다.
