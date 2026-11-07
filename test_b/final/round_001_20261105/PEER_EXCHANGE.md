# 중간 책임자 교차 검토 — 마지막 설계 점검

두 보고서는 MID_TERRA.md와 MID_SONNET.md에 있고 총괄 정정은 각 문서 끝에 있다. 감사는 종료한다. 추가분석없이 아래 한 번의 bounded experiment를 검토하고, 치명적문제만 지적하거나 승인하라. 상대안의 장점과 한계를 각각1개씩밝히고15줄이내로반환. 파일수정/데이터적재 금지.

실제분모: cohort_counts.json. 전체100사건82척, Tier0–1=60사건55척.49는과거별도항차적격subset일뿐현재분모아님.

총괄 제안 Round2:
- 원천은 Round008 두parquet, positiveCSV. 양parquet를82후보RFID로필터. 원행source_ordinal동일값이서로다르면오류로보고. RFID/ts중복은최소ordinal시간대표행. 유효len/bbox유한비음수. 사고시각/좌표는feature로사용금지.
- 과거기준은각현재t이전30일,동일RFID,유효24시간대이상·관측날짜3개이상. 미달행은새방법후보에서제외하되,그RFID에적격행이하나도없을때만기존score최고시각으로fallback. 무관측은무예측.전체분모고정과적격후보군공통비교를둘다보고한다.
- U(위치없는행동기준): log1p(len),log1p(bbox)의과거경험백분위p=(less+0.5*equal)/n,각two-tailrarity r=1-2*min(p,1-p), U=(rlen+rbbox)/2. 상수이력의같은값은p=.5→r=0. 실제속력/사고확률아님.
- C(단일변경위치맥락): floor(lon/.05),floor(lat/.05) 각도격자. 현셀내과거유효행8개이상이면그셀의분포로U와동일한r을계산. 부족/좌표무효이면동일RFID전체과거분포U로backoff. 지리거리/항구/어구경계로부르지않음. 단순히희귀셀이라는이유만으로높은점수를주지않음.
- baseline B0는기존score최고시각. 추가로후보군공통B0와U대C를paired비교. 정답을보고좋은기존규칙을선택하지않음. 동점score는빠른ts,그후ordinal.
- primary각1시각,secondary동일규칙의상위4distinct시간(간격최적화없음),RFID당같은예측을모든해당사건에공유. 4슬롯은내부탐색지표이며공식채점으로주장금지.
- 전체100/Tier01=60각분자분모및historycoverage·사고±6h관측가능여부·조건부common比較. 새로운Cvs기존B0의Tier01top1을주개선으로,전체100과UvsC를보조로고정.실용+5%p목표와선박pairedbootstrap95%CI,필요시동일후보수random기준. 반복사용dev는탐색.

판단에필요한질문: 1) CvsU가위치맥락기여를검사하는가? 2) fallback·기간·동점이후행정보나정답에의존하는가? 3) 코드구현후결과를보기전에고쳐야할치명적인정의가있는가? 새가설확대·추가감사는제안하지말라.
