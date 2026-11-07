"""Write the Korean report from frozen results; standard library only."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
r=json.loads((HERE/'results.json').read_text(encoding='utf-8'))
s=json.loads((HERE/'selection_frozen.json').read_text(encoding='utf-8'))
v=json.loads((HERE/'verification.json').read_text(encoding='utf-8'))
resources=json.loads((HERE/'resource_checks.json').read_text(encoding='utf-8'))
names={
'baseline':'동일조건 Round026 Trio', 'singleton_trust':'단독 이름표 확정',
'singleton_recheck':'단독 재검사', 'empty_zero':'무표=연안복합',
'empty_recheck':'무표 4클래스 재검사', 'pair01_hard_base':'0·1 동시 후보 → base 0/1 한정',
'pair01_recheck':'0·1 동시 후보 → 이진 재검사', 'pair02_recheck':'정확히0·2 → 이진 재검사',
'combined_hard':'네 그룹 강제 통합', 'combined_soft':'4클래스 보수적 재검사 통합'}
lines=['# Round026 → 027 팀원 관찰 반영 재검사 결과', '',
'사용자 요청: 팀원 관찰 네 가지를 참고하여 기존 Round026 결과에 이름표 재검사를 추가한다.', '',
'## 결과와 판정', '',
f"SELECT 내부 교차적합으로 선택한 절차의 개발 OUTER 결과는 **{r['selected']['correct']}/5897, "
f"micro-F1 {r['selected']['micro_f1']:.6f}, macro-F1 {r['selected']['macro_f1']:.6f}**다.", '',
'팀원 이름표의 원래 정의를 재현한 결과가 아니다. 이번 이름표는 저장 OVR 이진점수 각각에 0.5를 적용했다. '
'팀원의 64%, 195/76, 302/156, 43/21은 별도 모집단의 참고 가설로만 사용했다.', '',
'각 원래 fold의 SELECT에서만 새 재검사기를 학습/선택했다. SELECT 내부3-fold마다 scaler도 다시 적합했다. '
'각 OUTER의 선택·예측을 동결한 뒤 정답을 읽었고, OUTER 결과에 따른 선택 변경은 없다.', '',
'**판정: 이번 재검사 절차는 채택하지 않는다.** 정답 수의 개선이 없고 macro-F1이 낮아졌으며, '
'같은 조건 base 대비 채낚기 TP가 1척 줄었다. 기존 절대 TP 보호 하한을 통과한 사실은 '
'이 손실이나 자망·통발 개선 실패를 상쇄하지 않는다. micro-F1 0.7 목표는 미달이다.', '',
'| 비교안 | 정답 척수 | micro-F1 | macro-F1 | 자망 F1 | 통발 F1 | TP0/TP3 | base 대비 순증 |',
'|---|---:|---:|---:|---:|---:|---|---:|']
for name,m in r['candidates'].items():
 p=r['candidate_vs_same_baseline'][name]
 lines.append(f"| {names[name]} | {m['correct']} | {m['micro_f1']:.6f} | {m['macro_f1']:.6f} | "
              f"{m['f1'][1]:.4f} | {m['f1'][2]:.4f} | {m['tp'][0]}/{m['tp'][3]} | {p['net']:+d} |")
m=r['selected']; p=r['selected_vs']['same_condition_baseline']
lines += [f"| **SELECT 선택 절차** | **{m['correct']}** | **{m['micro_f1']:.6f}** | **{m['macro_f1']:.6f}** | "
          f"{m['f1'][1]:.4f} | {m['f1'][2]:.4f} | {m['tp'][0]}/{m['tp'][3]} | **{p['net']:+d}** |", '',
'전체 후보표는 사전 고정한 보조 진단이다. 표에서 OUTER 점수가 가장 높은 안을 새로 채택하지 않는다.', '',
'단독 이름표 그대로 3,488척 → 단독 재검사 3,516척으로 28척 회복했지만, '
'기존 확률결합 base 3,538척보다 22척 낮다. 이 비교는 재검사가 전혀 작동하지 않는다는 '
'뜻이 아니라 현재 base를 대체할 이득이 없다는 뜻이다.', '',
f"SELECT 선택 절차 vs 같은 base: 새 정답 +{p['gain']}, 새 오답 −{p['loss']}, 순증 {p['net']:+d}척. "
f"쌍대 척수 bootstrap 95% 구간 {p['ci95_correct_count']}, McNemar p={p['mcnemar_p']:.5g}. "
'이는 반복 노출 개발 비교의 기술통계이며 다중 비교를 보정한 독립 개선 증거가 아니다.', '',
'## 네 가지 가설의 실제 관찰', '']
g=r['groups']
for name,title in [('singleton','1. 단독 이름표'),('empty','2. 이름표 없음'),('pair01','3. 0·1 동시 포함'),('pair02','4. 정확히0·2')]:
 t=g[name]; n=t['n']
 lines += [f'### {title}', '',f"대상 {n}척. 실제 클래스별 척수 [연안복합, 자망, 통발, 채낚기]={t.get('true_counts',[])}."]
 if n:
  if name=='singleton': lines.append(f"이름표 그대로의 정확도는 {t['singleton_trust_correct']}/{n}={t['singleton_trust_correct']/n:.1%}.")
  if name=='empty': lines.append(f"전부 연안복합으로 정하면 {t['true_counts'][0]}/{n}={t['true_counts'][0]/n:.1%}만 맞는다.")
  if name in ('pair01','pair02'):
   lines.append(f"후보를 해당 둘로 강제 제한할 때 정답을 원천 제외하는 선박은 {t['forced_exclusion_true_outside_pair']}척이다.")
  lines.append(f"같은 base 정답 {t['baseline_correct']}척 → SELECT 선택 절차 정답 {t['selected_correct']}척.")
 lines.append('')
lines += ['## fold별 선택과 보호', '', '| fold | SELECT 수 | 선택안 | OUTER base → 선택 |', '|---|---:|---|---|']
for f,d in zip(r['fold_results'],s['folds']):
 lines.append(f"| {f['fold']} | {d['select_n']} | {d['selected']} | {f['baseline']['correct']} → {f['selected']['correct']} |")
lines += ['',f"보호 판정: {json.dumps(r['protection'],ensure_ascii=False)}.", '',
'단일seed 기준 TP0≥2389/TP3≥90과 역사5seed 기준 TP0≥2381/TP3≥92를 각각 표시한다. '
'이번 작은 재검사기의 단일seed 진단은 새 후보5seed 확인을 대신하지 않는다.', '',
'| 실제 클래스 | precision | recall | F1 | TP | FP |', '|---|---:|---:|---:|---:|---:|']
for c,name in enumerate(['연안복합','자망','통발','채낚기연승낚시']):
 lines.append(f"| {name} | {m['precision'][c]:.4f} | {m['recall'][c]:.4f} | {m['f1'][c]:.4f} | {m['tp'][c]} | {m['fp'][c]} |")
for ref,p in r['selected_vs'].items():
 lines += ['',f"참조 {ref}: gain/loss/net={p['gain']}/{p['loss']}/{p['net']}; "
           f"class0={p['per_true_class']['0']}; class3={p['per_true_class']['3']}."]
lines += ['', '## 검증, 한계와 다음 단계', '',
f"저장 예측 독립 산술검산: {v['rows']}척, {v['candidate_metrics_checked']}개 예측열, "
f"{v['input_hashes_checked']}개 입력 해시 통과. 메타 선택 규칙과 교차적합 선박 분리를 재계산했다.", '',
f"실행 자원: 기록한 최대 RSS {max(x['rss_gib'] for x in resources):.3f}GiB, "
f"최저 단계별 가용 RAM {min(x['available_gib'] for x in resources):.3f}GiB. 1개 계산 프로세스, thread1, BelowNormal.", '',
'- 원모델 일부는 예전 INNER 전체를 조기종료에 사용했다. 새로운 SELECT 재검사 교차적합이 그 이력을 지우지는 않는다.',
'- OVR 모델은 326특징 FIT 학습 소스/명부를 확인했으나, 과거 저장 확률에 ID 및 실행 당시 snapshot 해시가 없다. 현재 metadata 정렬·label 대조로 보강했다.',
'- 기존 학습모델/특징의 반복 선택 이력이 있다. 새 holdout, 공식 제출, 실제 장치 실험을 수행하지 않았다.',
'- 관측일 구간 평가는 확률 전용 입력에 해당 필드가 없어 수행하지 않았다.',
'- micro-F1 0.7 목표를 유지한다. 이번 실험만으로 목표 지표를 macro로 바꾸거나 최종 모델을 채택하지 않는다.', '',
'후속은 이 표의 OUTER 최고값을 좇는 추가 튜닝보다, SELECT에서 선택되지 않거나 보호를 잃는 원인과 '
'실제 후보 누락을 먼저 검토한다. 도메인 특징이 필요하다면 별도 가설·예산으로 사전 고정한다.', '',
'## 학습 확인 질문', '',
'1. 이름표가 하나라는 사실과 그 이름표가 정답이라는 사실은 어떻게 다른가?',
'2. 무표 집단의 최빈 클래스 비율과 전체 base 정확도 중 어느 것을 비교해야 하는가?',
'3. 0/1 이진 재검사기가 잘 분리해도 실제2/3인 선박을 잘못 라우팅하면 어떤 손실이 생기는가?',
'4. SELECT OOF에서 보호를 만족해도 OUTER에서 보호를 잃을 수 있는 이유는 무엇인가?', '']
(HERE/'ROUND_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print(HERE/'ROUND_REPORT.md')
