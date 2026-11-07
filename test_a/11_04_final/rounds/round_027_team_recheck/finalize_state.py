"""Finalize UTF-8 administrative records without shell-pipe text encoding."""
import csv
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=HERE/'EXECUTION_STATUS.json'
e=json.loads(p.read_text(encoding='utf-8'))
e['user_steering']='팀원 결과는 참고만 하며 이름표 원본 재현은 불필요'
if (HERE/'INDEPENDENT_RESULT_REVIEW.md').exists():
    e['independent_result_review']='INDEPENDENT_RESULT_REVIEW.md'
    e['independent_result_review_complete']=True
p.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf-8')

p=ROOT/'NEXT_SESSION.md'
old=p.read_text(encoding='utf-8-sig')
marker='# Round 026 완료'
assert marker in old
historical=old[old.index(marker):]
prefix='''# 2026-11-05 최신: 팀원 관찰 기반 Round026→027 재검사 완료

- 최신 회차: `round_027_team_recheck`. 기존 `round_027_fallback_ovr`와 구분하며 기존026/027 파일은 수정하지 않았다.
- 사용자 지시: 팀원 이름표 결과는 가설 참고만. 원래 이름표 재현은 불필요.
- 보고서: `rounds/round_027_team_recheck/ROUND_REPORT.md`; 코드/고정계획/예측/선택동결/입력해시/검산을 같은 폴더에 저장.
- 3개 원래 fold의 SELECT 각394척, 내부3CV, 총36개 작은 로지스틱 재검사 적합. SELECT에서 고른 절차를 동결하고 개발 OUTER5897 평가.
- primary:3538/5897, micro0.5999660844, macro0.5161167059. 같은조건 base:3538, macro0.5174847814. 새정답24/새오답24, net0.
- TP primary[2547,798,101,92], base[2538,801,106,93]. 기존 절대 보호 하한 둘은 통과하지만 같은base TP3-1 및 자망/통발 감소. **채택하지 않는다**.
- 단독이름표확정3488→단독재검사3516, 여전히base3538보다낮음. 무표=0은3439(-99), 강제통합3412(-126).
- 이번 proxy 이름표(이진점수>=.5)에서 단독4283, 무표1498,0·1동시110(실제통발10),정확히0·2는3척뿐. 팀원 집계와 같은 모집단이라고 주장하지 않는다.
- 별도검산:5897행/11예측열/34입력해시통과. 독립성/원모델 INNER조기종료 노출/WorkerA 과거ID sidecar 부재는 보고서에 명시.
- 실제가용 RAM 재확인:첫진입1.493<1.5로학습0중단; metadata검토후다시1.530에서진입성공. 관측최대RSS.156GiB, 단계별최저가용1.396GiB. thread1/BelowNormal/계산동시1.
- 자동 재실행·OUTER최고값 채택·목표지표 변경 없음. micro0.7 목표는 미달. 새 후보는 별도 가설과 고정 기준으로 다룬다.

---

아래는 갱신 전 Round026의 역사 인계 내용이다. 그 안의 ‘공식 돌파/검증된 황금비율’ 표현은 후속 독립 검토의 선택 누출 지적을 함께 읽어야 하며 최신 확정 결론으로 사용하지 않는다.

'''
p.write_text(prefix+historical,encoding='utf-8')

r=json.loads((HERE/'results.json').read_text(encoding='utf-8'))
x=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8'))
if (HERE/'INDEPENDENT_RESULT_REVIEW.md').exists():
    x['team_recheck_experiment']['independent_result_review']='rounds/round_027_team_recheck/INDEPENDENT_RESULT_REVIEW.md'
    x['team_recheck_experiment']['independent_result_review_complete']=True
    (ROOT/'STATUS.json').write_text(json.dumps(x,ensure_ascii=False,indent=4)+'\n',encoding='utf-8')
assert x['team_recheck_experiment']['primary_micro_f1']==r['selected']['micro_f1']
assert e['fits_completed']==36 and not e['adopted']
assert x['current_round']=='round_027_team_recheck'
with (ROOT/'EXPERIMENT_LEDGER.csv').open(encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f))
assert sum(z.get('round_id')=='round_027_team_recheck' for z in rows)==1
assert '채택하지 않는다' in (HERE/'ROUND_REPORT.md').read_text(encoding='utf-8')
assert '??' not in prefix
print('UTF-8 state/report/ledger consistency checked.')
