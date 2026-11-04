# Test B ID 교집합 독립 재검산

## 먼저 답

기존 제출샘플의 Test B ID 100개와 새 ZIP 제출샘플의 Test B ID 100개를 직접 비교한 교집합은 **0개**입니다. 이 0은 제출샘플 두 시트의 ID 명부 교집합만 뜻하며, 원항적 파일에 새 ID가 없다는 뜻은 아닙니다.

- **oldB_vs_newB**: 교집합 0개, 왼쪽만 100개, 오른쪽만 100개
- **oldA_vs_newA**: 교집합 2개, 왼쪽만 98개, 오른쪽만 98개
- **oldA_vs_newB**: 교집합 13개, 왼쪽만 87개, 오른쪽만 87개
- **oldB_vs_newA**: 교집합 0개, 왼쪽만 100개, 오른쪽만 100개
- **newB_vs_intakeB**: 교집합 100개, 왼쪽만 0개, 오른쪽만 0개
- **oldB_vs_submission_csv**: 교집합 100개, 왼쪽만 0개, 오른쪽만 0개
- **newB_vs_submission_csv**: 교집합 0개, 왼쪽만 100개, 오른쪽만 100개
- **oldB_vs_score_cache_keys**: 교집합 100개, 왼쪽만 0개, 오른쪽만 0개
- **newB_vs_score_cache_keys**: 교집합 0개, 왼쪽만 100개, 오른쪽만 100개

## 시트·타입 확인

- ZIP 내부의 작은 제출샘플 member를 ZIP에서 직접 읽어 openpyxl read_only 모드로 열었다. 전체 ZIP 추출이나 ZIP 전체 해시는 하지 않았다.
- ZIP member SHA-256과 intake의 reference_02_제출샘플.xlsx, archive manifest의 크기/SHA/CRC/경로를 대조했다. 결과: 일치.
- 원본 F: 제출샘플과 ZIP 내부 workbook 각각 sheet 순서, A1, A2:A101 값·타입·공백·중복을 확인했다. 비교 CSV에는 원값, 타입, 공백 제거값, 선행0를 변경하지 않는 안전한 정수표현, 비교키를 함께 남겼다.
- oldB/newB 같은 행 위치 ID 일치: 원값 0/100; 안전 정규화 후 0/100.

## 기존 캐시와 원항적 해석

- scored_rows.pkl은 점수/A를 재계산하지 않고 rfid_id 키만 읽었다. 이는 기존 점수 캐시에 키가 존재하는지 뜻하며 원항적 전체 존재와 같은 주장이 아니다.
- parquet coverage: scanned_projected_rfid_only; 100/100 newB 고유 ID가 이 legacy rows_test parquet에서 보였다. 해당 parquet은 parse manifest에 기재된 F: 1027 CSV 입력 기반 캐시이며 v2 ZIP 원항적을 검증하지 않는다.
- parse_test_1..6 명부의 각 원본 경로/기록 SHA는 1027 입력을 가리키고, 각 행수와 현재 parquet 투영 스캔 행수의 대응을 summary에 보존했다. 원본 CSV SHA는 재계산하지 않았다.
- W0의 구/신 Test B ID 교집합 0 주장은 직접 workbook 재검산으로 확인됐다.
- ZIP 메타데이터 변경 여부: 변경 없음. 비교 입력 SHA 전/후 변경: 없음.
