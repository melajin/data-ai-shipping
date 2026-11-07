# Round010 완료 결과 진입점

사용자 요청에 따라 Gemini–Codex 비교와 결론별 상세 해설, 원자료 재계산·통계 검산을 완료했다. 최신 결과는 다음 문서가 기준이다.

- [최종 결과](ROUND_REPORT.md)
- [비교 및 결과 보고](ROUND010_비교및결과보고_20261105.md)
- [T1 상세 결론](T1_결론상세보고_20261105.md)
- [T2 상세 결론](T2_결론상세보고_20261105.md)
- [검산·규율 감사](t3_audit_report.md)
- [수용 조건과 완료 범위](ROUND010_수용조건점검_20261105.md)
- [재현 방법](REPRODUCE.md)

루트 t1_report.md·t2_report.md·실행보고는 정정한 통합본이다. Gemini의 원 보고서와 당시 루트 파일 사본은 comparison_20261105/original_root_snapshot에 있고, 독립 Codex 실험은 codex_independent에 있다. 두 실행의 최초 물리 해석·다중검정 판단을 최신 판정으로 혼동하지 않는다.

루트 t1_gate_results.json·t2_state_distribution.json은 Gemini의 원 수치다. 최신 비교·판정·검산 JSON은 comparison_20261105에 있다. 루트 T1 소스·메모리·종료기록은 초기 출력 경합의 Codex 사본이므로 Gemini 원 생성 소스나 실제 종료코드 증거가 아니다. 구형 run_task.ps1 대신 REPRODUCE.md의 비교 스크립트를 사용한다.

최종 후보는 단일 Bonferroni 기준 lin_raw/Tier0-1이다. 문자 그대로의 이중 보정 분기, 별도 세션 검토자 미참여, 공식 성능 미평가도 상세 보고에 공개했다.
