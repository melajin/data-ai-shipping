# 실행 전 정정 — frozen ID 해시는 순서 해시가 아님

기록: 2026-11-04T17:29Z. exporter 및 모델 실행 전 정정이다. 최초 ROUND_PLAN과 round004 문서는 보존한다. 이 문서가 ROUND_PLAN의 frozen INNER digest 해석에 우선한다.

사용자가 확인을 요청한 Orca 운영 메시지(msg_1644256c7067, 직전 관리자)는 round003/verification_20261105/v4_idhash.py와 JSON을 근거로 frozen FIT/INNER 해시가 **ID를 정수로 정렬하고 십진 문자열을 줄바꿈으로 연결하되 마지막 줄바꿈이 없는 SHA256**이라고 알렸다. 관리자가 두 파일을 읽어 확인했다. 메시지 원문은 manager/incoming_correction_message.json에 보존했다. 생성 검증 코드의 후보 탐색은 이번 회차에서 재실행하지 않는다.

- v4_idhash.py SHA256: 8655f7a1d265b790828505695128141d9e4ca113e2fea0ce4a5cfe47f208dd13
- v4_idhash.json SHA256: 285ff5d653eccf50cebec61ca6b9801f8c90e8e37cb406d1c412c58577fbea85
- frozen fold0 INNER 집합 SHA256: cb82568ec4fcedf20a5706d15db6a76f84f84a23b9273aa4b18948c3014ed0c3
- frozen fold0 FIT 집합 SHA256: 2470cabe8ecbe7a063ab8303bcb66faa85cb907596c9d44f69dda3b8ee6b0ed5

기존 `BASE.digest_json(inner_ids)==frozen_rule.inner_ids_sha256` 요구는 다른 직렬화·순서 의미를 비교하므로 부적절하다. 작은 재현 실험의 데이터나 질의를 선택하기 위한 변경이 아니라 입력 검증 코드의 의미 오류 정정이다.

## 수정한 관문

1. 원래 manifest 목록의 BASE JSON digest와 frozen hash를 한 번 비교하여 값과 불일치 사실을 보존한다. 이를 ordered 검증 통과라고 부르지 않는다.
2. 위의 사전 확정한 단일 numeric-sort/newline 공식으로 frozen FIT/INNER **집합** 해시를 직접 검산한다. 불일치하면 중단한다. 여러 정렬·직렬화를 탐색하지 않는다.
3. 실제 모델 입력은 정렬하지 않는다. 정확히 해시로 연결된 원본 manifest의 `fit_ids`/`inner_ids` 목록과 원코드 `.loc[fold[...]]` 순서를 따른다. ordered JSON digest를 별도로 저장하고 독립 검토자가 목록·배열 순서를 직접 대조한다. frozen 집합 해시만으로 역사 행순서를 입증했다고 하지 않는다.
4. vocabulary FIT 해시는 별도 source의 sorted string BASE JSON 방식이므로 그 검사는 기존대로 유지한다.

export 1회 + 필요시 근거 있는 수정 1회, 독립 배열검산 1회, 실제 pilot 1회/600초, RAM 관문, FIT/질의/seed/모델 설정과 보호자료 금지는 모두 유지한다. source/metadata 정정 확인은 F1평가나 모델실행이 아니다.

직전 관리자는 별도 문서 검토만 수행하며 실험 및 공유 STATUS를 수정하지 않는다고 명시했다. PDF의 제안 성능은 실측값이나 실험범위 변경 승인으로 취급하지 않는다.
