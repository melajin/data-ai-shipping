# 실제 실행 전 통합 확인

총괄은작업자 msg_340896711ce1와msg_47c0b2fd136b를받고명시시간변환과저장순서를직접확인했다. 정수는unit=h,datetime은시간경계검증이며ledger에source_ts_hour를남긴다. 평가기의크기기반단위추정은제거됐고유효하지않은선택시각은오류로처리한다. censored close_ts의결측은유지한다. geometry유효성은좌표와분리됐다.

run_duration은규칙반환후예측/pools/runregistry/ledger를먼저저장하고frozen_predictions해시를기록한다. 이후에만사건CSV를parse한다. 모델수식·기간·최소표본·후보예산·관문은변경하지않았다.

2026-11-06 01:18:04 KST 직전가용RAM3671.8MiB,추정추가768MiB+여유640MiB,병행데이터작업0을확인한뒤실제execution_001을시작했다. runner자체도직전RAM을재확인한다. 이문서는통합API확인기록이며아직성과검증완료를뜻하지않는다.
