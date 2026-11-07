"""산출물·종료코드만 읽어 종합 보고 작성. 원자료·타 실행 결과 미사용."""
import json,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent
def read(n):return json.loads((P/n).read_text(encoding='utf-8-sig'))
def main():
    a,b=read('t1_gate_results.json'),read('t2_state_distribution.json')
    receipts={k:read(k+'_execution.json') for k in ['t1','t2']}
    memory={}
    for k in ['t1','t2']:
        checks=read(k+'_memory.json')
        memory[k]={'n_checkpoints':len(checks),'minimum_available_mib':min(x['available_mib'] for x in checks),
          'maximum_observed_rss_mib':max(x['current_rss_mib'] for x in checks),
          'all_allowed':all(x['allowed'] for x in checks)}
    collision=read('t1_collision_execution.json')
    fmt=lambda x:'NA' if x is None else f'{x:.6g}'
    primary=[g for g in a['gates'] if g['stratum']=='Tier0_1']
    drift=[r for r in b['results'] if r['metric']=='direct_drift' and r['half_width_h']==3 and r['design']=='hod_1/nrows_matched' and r['stratum'] in ['ALL','Tier0_1','기관손상']]
    contract_interpretations={
      'literal_adjusted_p_threshold':a['passed_primary_metrics'],
      'usual_single_bonferroni_candidates':[{'metric':g['metric'],'stratum':g['stratum']} for g in a['gates'] if g['checks']['abs_delta_at_least_005'] and g['checks']['ci95_excludes_zero'] and g['checks']['sign_consistent_at_least_8_of_10'] and g['primary'].get('significant_usual_single_bonferroni')],
      'mcnemar':'일반 단일 짝 exact McNemar가 아닌 전수 짝조합 exact p 적분과 보수 결합; T3 해석 승인 필요'}
    evidence={'input':a['input'],'execution':receipts,'collision_execution':collision,'memory':memory,
      'mde_corrections':read('mde_corrections.json'),'synthetic_validation':read('synthetic_verification.json'),
      't1_result_cells':len(a['results']),'t2_result_cells':len(b['results']),
      'contract_interpretations':contract_interpretations,'declaration':a['declaration'],
      'scope':'2026 dev 실제자료 평가. 모델·장치 실험 없음. T3/LEDGER/STATUS 변경은 담당 범위 밖.',
      'output_collision':'동일 지정 폴더에서 Gemini와 경합 확인. 첫 자체 실행 PID2184를 중단(exit -1); 이후 codex_independent만 사용. 루트 t1/t2 스크립트와 memory에 사전 작성 충돌이 있었으므로 감독자에게 원본 복원 요청 전달.',
      'independence_limit':'경합 탐지 중 Gemini T1 보고서 첫부분 및 T2 소스 헤더를 보았다. 그 수치를 독립 계산에 사용하지 않았고 복사된 T2 소스는 삭제 후 독자 구현했다. 완전한 맹검 비교라고 주장하지 않는다.'}
    (P/'execution_summary.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Round010 Codex 독립 실행보고','',a['declaration'],
      '본 보고의 수치는 codex_independent 안의 산출물만 사용했다. 경합 탐지 중 다른 실행 결과 일부를 보았으므로 완전한 맹검 실험이라고 주장하지 않는다.',
      '', '## T1 고정 관문 결과',
      '|지표|층(사건)|유효 n|Δ백분위|보정 p|95% CI|부호일치/10|MDE 근사|대조<15 제외|통과|',
      '|---|---|---:|---:|---:|---|---:|---:|---:|---|']
    for g in a['gates']:
        r=g['primary'];lines.append(f"|{g['metric']}|{g['stratum']}|{r['n_events']}|{fmt(r['delta_percentile'])}|{fmt(r['p_bonferroni'])}|{str(r['ci95'])}|{g['sign_consistent_designs']}|{fmt(r['mde80_percentile_approx'] or r.get('mde80_positive_rate_approx'))}|{r['excluded_fewer_than_15_controls']}|{'통과' if g['passed'] else '미통과'}|")
    lines+=['','출처: t1_gate_results.json/gates[].primary (집계: 사건). NA는 영 과다 규칙에 의한 백분위 금지이며 그 MDE 단위는 양성률 차이다.',
      '관문은 |Δ백분위|≥0.05, 보정 p<0.00714(정확값 0.05/7), 2000회 사건 부트스트랩 CI의 0 제외, 10종 중 8종 이상 부호일치다. 무통제 설계는 안정성 진단에만 포함한다.',
      '계약 문구의 보정 p<α를 문자 그대로 적용했다. 통상적인 단일 Bonferroni 방식(raw p<α)은 별도 해석이며 다음 후보가 생긴다: '+json.dumps(contract_interpretations['usual_single_bonferroni_candidates'],ensure_ascii=False)+'. 두 해석 차이는 감독·T3가 결정해야 하며 조용히 기준을 변경하지 않는다.',
      '비유의 결과에서 표의 MDE보다 작은 효과는 이 근사 설계로 안정적으로 검출할 수 없다. 정확 검정력·선박 반복 사건 의존성까지 보장하지 않는다.',
      '관측 불일치가 0인 작은 층의 초기 MDE=0 계산은 폐기하고 최선 조건의 이진 정확 검정력 계획값으로 보완했다. 사건 수가 너무 작아 차이가 1이어도 유의해질 수 없으면 MDE는 NA이며 JSON/mde_status에 불가를 명시한다. 수정 내역은 mde_corrections.json에 있다.',
      f"전수 집계 셀: T1 {len(a['results'])}개, T2 {len(b['results'])}개 (지표×설계×층×창폭). 출처: execution_summary.json/t1_result_cells,t2_result_cells. 창폭·사고유형별 전수 결과는 각 JSON/results에 있다.",
      '', '## T2 직접표류',
      '|층(사건)|유효 n|0 비율|Δ백분위|양성률 차이|보정 p|MDE 근사|대조<15 제외|',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in drift:lines.append(f"|{r['stratum']}|{r['n_events']}|{fmt(r.get('zero_fraction'))}|{fmt(r['delta_percentile'])}|{fmt(r.get('delta_positive_rate'))}|{fmt(r['p_bonferroni'])}|{fmt(r.get('mde80_positive_rate_approx'))}|{r['excluded_fewer_than_15_controls']}|")
    lines+=['','출처: t2_state_distribution.json/results. 영 과다이면 백분위 대신 사건 단위의 양성률 대비만 해석한다. 모든 상태별 McNemar 확장 결과와 MDE는 t2_report.md 및 동일 JSON에 있다.',
      b['state_source']['status']+' (출처: t2_state_source.json). 상태 누락과 실제 표류 부재를 구분할 현장 정답은 없다.',
      '', '## 실제 종료코드와 메모리',
      '보조 보고서 생성기의 초기 KeyError와 메모리 보류도 숨기지 않고 helper_execution_history.json에 shell 관측값과 내부 종료 포착 여부를 구분해 남겼다. 영 불일치 MDE의 초기 결론은 mde_corrections.json에 수정 전후를 보존했다.',
      '최초 공유폴더 충돌 중단: '+str(collision[-1]['exit_code'])+' (t1_collision_execution.json, 실행 단위).']
    for k in ['t1','t2']:
        for rec in receipts[k]:lines.append(f"- {k}: 실제 종료코드 {rec['exit_code']}; 로그 {Path(rec['log_path']).name}; 실행 종료 {rec['ended_at']} ({k}_execution.json).")
        m=memory[k];lines.append(f"- {k} 메모리: 최소 가용 {m['minimum_available_mib']:.3f}MiB, 관측 RSS 최대 {m['maximum_observed_rss_mib']:.3f}MiB, 확인 {m['n_checkpoints']}회 (작업 경계 단위, execution_summary.json/memory/{k}).")
    lines+=['','## 이번에 내린 판단과 근거',
      '- 지정 부모 폴더 안에 독립 하위폴더를 사용해 Gemini와 출력 경합을 피했다. 첫 자체 실행만 중단했으며 타 프로세스를 종료하지 않았다.',
      '- 실제 발생유형별 사건 수를 사용했다: '+json.dumps(a['input']['cause_counts'],ensure_ascii=False)+' (사건 집계, t1_gate_results.json/input/cause_counts).',
      '- McNemar와 다중 대조창의 미정의 짝 구성은 전수 짝 적분으로 보완했다. 이는 원 계약의 일반 McNemar와 차이가 있어 별도 검토 대상이다.',
      '- 초기 직선도 분해 가설과 실제 판정의 차이는 고정 관문 표에 보존했다. 층화 중 유리한 수치를 전체에 일반화하지 않았다.',
      '- 모든 주요 구현·메모리 판단은 t1_report.md와 t2_report.md에 기록했다.',
      '', '## 남은 범위',
      'T3 독립 재계산, 다중검정 문구·McNemar 확장 수용 여부, 공유폴더 기존 스크립트 복원, 감독자의 LEDGER/STATUS 갱신이 남았다. 이 실행자는 기존 폴더와 원자료·공식 제출물을 추가 수정하지 않는다.']
    (P/'ROUND010_실행보고_20261105.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in P.iterdir() if p.is_file() and p.name!='manifest.json'}
    (P/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
