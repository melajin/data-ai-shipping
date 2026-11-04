# 준비 감사 실패와 수정 범위

V msg_f4c966d7278a / ctx_f5235ff89d75: outcome failed. 독립validator exit0, syntheticfixture exit0, aggregate review exit1이다. 실패를 완료/통과로 표시하지 않는다.

확인된 통과: 정확명부100·순서/원ZIP workbook 직접비교, source parquet 4,212,389행 독립청크스캔, selected46,705행 전수원행값/ordinal 일치·누락/추가0, 대상요약100개 모든필드 일치, 달력/hour/keyvalid/finite조건, 별도26행합성성분 scalar대조와A/floor/충돌경계, 원코드4개해시. 시간대/CRS·실제참조/점수/사고정답/성능은 미확인이다.

실패원인: execution_manifest에 최신artifact_sha25653/53 일치와 별도로 artifacts_sha25644개 중4개 stale해시가 남고 역사표시가 없다. 생산자에게 현재해시맵과 과거맵을 명시구분하고 변경전원문/한계·시점을 보존하도록 지시했다. 옛값을 현재값으로 조용히 덮거나 검증안된역사를 검증완료로 주장하지 않는다.

수정권한은E execution/에만. 코드/선별데이터/보고/scan은바꾸지 않고 manifest-only 수정+정정영수증/로그를 허용한다. 이후V가변경메타데이터/현재해시/생산불변만 독립재검산하며4.2M행과합성계산을무의미하게반복하지 않는다. 대용량참조/새100점수 gate는닫힌상태다.

E 정정 msg_860ae70e97d6 수신: 변경전manifest SHA8f4533ca1efa2a0a1ff8d8bb4d49151344cf1e9d4569c51ac0b8a3469f7b0c9a의byte동일백업 보존, 변경후a8bb74a10936572ad152aabeacc5f741a036d922e3a86fdd2f0dbcb494117e42, 역사44값 legacy분류, current56/56일치를보고했다. 감독은정정영수증을읽었다. 이는생산자보고이며 별도V ctx_069ff0f3f3bd에 audit/manifest_delta_001/ 변경검산만위임했다. 기존실패감사는보존하고 통과로덮지않는다. E최신dispatch release는released/closed_agent_terminal 반환으로닫힘을확인했다.
