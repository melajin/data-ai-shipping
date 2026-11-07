"""Render detailed conclusions directly from retained comparison evidence."""
import json,math,hashlib,statistics,csv
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent;R=P.parent;C=R/'codex_independent';G=P/'original_root_snapshot'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,lines):p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
def f(x):return 'NA' if x is None else f'{x:.6g}'
def interval(x):return 'NA' if not isinstance(x,list) else '['+', '.join(f(v) for v in x)+']'
def table(headers,rows):return ['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(str(v) for v in row)+'|' for row in rows]
def main():
    co=read(P/'comparison_results.json');ca=read(C/'t1_gate_results.json');cb=read(C/'t2_state_distribution.json')
    audit=read(P/'report_claims_audit.json');ver=read(P/'t3_verification.json');binary=read(P/'t3_matched_set_binary.json')
    gates={(g['metric'],g['stratum']):g for g in co['canonical_gate']}
    lin=gates['lin_raw','Tier0_1'];alllin=gates['lin_raw','ALL']
    linre=next(x for x in ver['event_summary_recomputations'] if x['metric']=='lin_raw' and x['stratum']=='Tier0_1')
    rawdone=ver['raw_status'].get('actual_raw_metrics_rebuilt',False)
    data={'decision':'lin_raw is the sole follow-up candidate under single Bonferroni; operational/model promotion not established',
      'alpha_raw':.05/7,'alpha_adjusted':.05,'literal_adjusted_alpha':.05/7,
      'single_Bonferroni_candidates':[g for g in co['canonical_gate'] if g['normal_single_Bonferroni_pass']],
      'double_Bonferroni_candidates':[g for g in co['canonical_gate'] if g['literal_double_Bonferroni_pass']],
      'lin_raw_K14_adjusted_p':min(1.,14*lin['raw_p']),'lin_raw_K49_adjusted_p':min(1.,49*lin['raw_p']),
      'raw_recompute_completed':rawdone,'statistics_match':ver['statistics_match'],
      'metadata':ca['input'],'profile_diagnostics':audit['profile_diagnostics'],
      'independent_reviewer_session':False,'implementation_independence_only':True,
      'legacy_results_unchanged':True,'new_model_training':False,'test_2025_used':False,'official_submission':False}
    (P/'final_decision.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    base=['작성: '+datetime.now().astimezone().isoformat(),
      '자료: 2026 dev 실제 항적의 사건 단위 탐색 분석. 같은 Codex 작성자의 별도 구현 검산이며 새 데이터·별도 검토자에 의한 독립 평가가 아니다. 기존 수치 JSON과 Codex 독립 결과는 유지했다. Gemini 원 보고서는 비교 폴더의 사본·해시로 보존하고 루트 보고서는 최신 통합본으로 갱신했다.']
    # Main comparison report: each section develops a conclusion rather than just listing numbers.
    lines=['# Round010 Gemini–Codex 비교 및 결과 보고','']+base+['',
      '## 1. 최종 판단: 수치는 재현됐고, 가장 큰 결론 차이는 Codex의 이중 보정 해석이었다',
      f"후속 검증 후보는 `lin_raw` 하나다. Tier0-1의 유효 {lin['n']}사건에서 Δ백분위 {f(lin['delta'])}, 원 p={f(lin['raw_p'])}, 7개 지표 Bonferroni 보정 p={f(lin['adjusted_p'])}, 사건 부트스트랩 95% CI={interval(lin['ci95'])}이며 설계 부호는 10종 모두 음수다. 이는 통상적인 단일 Bonferroni와 원래 효과·구간·안정성 조건을 충족한다.",
      'Gemini는 원 p를 α=0.05/7과 비교했고, 초기 Codex는 이미 7배 한 p를 다시 α=0.05/7과 비교했다. 후자는 사실상 49개 검정 수준의 더 엄격한 기준이다. 서로 다른 데이터를 관찰한 결과가 아니므로 두 실행의 성공·실패 우열로 해석할 수 없다.',
      '통합 판정은 K=7의 수학적 의미에 맞춰 **원 p<0.05/7 또는 보정 p<0.05**를 사용한다. Codex의 과도한 보정에서 나온 경로 전체 기각을 단일 Bonferroni의 결과로 인용하는 것은 정정한다. 동시에 계약에 적힌 “보정 p<0.00714”를 문자 그대로 적용하면 미통과라는 이력도 지우지 않는다. 이 문구의 모순은 다음 계약에서 결과를 보기 전에 제거해야 한다.',
      '이번 채택은 **다음 단계에서 검증할 특징 후보의 선택**이다. 전체 사건의 확증, 사고 탐지 성능, 실제 표류·예인 기제, 실선 운용 또는 공식 제출 준비 완료를 뜻하지 않는다.',
      '출처: `comparison_20261105/final_decision.json`, `comparison_results.json/canonical_gate`, `codex_independent/MULTIPLICITY_INTERPRETATION.md`와 독립 원 결과의 gates.',
      '', '## 2. 비교 범위와 집계 수준을 맞춘 결과',
      f"원 parquet은 {ca['input']['source_rows']:,}행이며 양성 선박에 해당하는 {ca['input']['selected_rows']:,}행·{ca['input']['positive_vessels']}척을 사용했다. 양성 사건은 {ca['input']['positive_events']}건, Tier0-1 원 집합은 {ca['input']['tier01_events']}건이다. `len_m<1m` 제외는 {ca['input']['lin_raw_excluded_len_lt_1_rows']:,}행이며, 이 제외는 비율의 정의를 안정화하기 위한 것이지 각 행이 GPS 잡음이라고 확인한 것이 아니다.",
      f"Gemini T1의 10종×7층×7지표 그리드는 {co['gemini_T1_grid_cells']}셀이다. Codex는 사고유형별 Tier0-1까지 포함하고 모든 창폭과 교차해 {co['codex_T1_cells']}셀을 저장했다. 교집합 그리드와 창폭 요약 {co['compared_records_including_duplicate_primary_width']}레코드를 비교했으며, 기본 창폭의 요약이 두 위치에 있는 중복을 포함한 수다. 셀 수가 많다는 사실을 성능 우수성으로 해석하지 않는다.",
      '주 결과의 사고창은 ±3h, 대조 중심은 같은 선박의 모든 사고에서 76h 이상 떨어지고, 시각대 원형거리 ≤1h·관측행수 일치·조건 충족 전수 대조창·최소 15개 조건을 사용했다. 무통제 설계는 요구된 부호 진단에만 포함하고 아래 효과 비교 표에 수치를 인용하지 않았다.',
      '출처: `comparison_results.json/input_counts`, `gemini_T1_grid_cells`, `compared_records_including_duplicate_primary_width`. 상세 집계 키: `comparison_t1.csv`.',
      '', '## 3. T1 주요 수치: 무엇이 같고 무엇이 달랐는가']
    lines+=table(['지표','층(사건)','Gemini n','Codex n','Gemini Δ','Codex Δ','Gemini 원 p','Codex 원 p'],
      [[x['metric'],x['stratum'],x['gemini_n'],x['codex_n'],f(x['gemini_delta']),f(x['codex_delta']),f(x['gemini_raw_p']),f(x['codex_raw_p'])] for x in co['primary_numeric_comparison']])
    lines+=['','표 출처: `comparison_results.json/primary_numeric_comparison` (사건 단위, ±3h·hod±1h·행수매칭). 영 과다 `still_frac`는 백분위·Wilcoxon 표기를 금지해 NA다.',
      '### 3.1 lin_raw·활동량·시간 간 이동: 사건별 값까지 일치',
      '기본 설계의 `lin_raw`, `speed_mean`, `step_mean`은 공통 유효 사건의 중간순위 백분위가 일치했다. 원 지표의 극히 작은 소수 오차는 합산 순서 차이 수준이다. 따라서 이 세 지표의 통계 차이를 모델이나 실험자의 성능 차이라고 볼 근거가 없다.',
      f"별도 표준 라이브러리 구현으로 세 지표×두 층, 총 {len(ver['event_summary_recomputations'])}개 통계를 다시 계산했고 Δ·Wilcoxon·부호검정·MDE를 대조했다. `statistics_match={ver['statistics_match']}`이며 최대 오차와 검정 방식은 `t3_event_recompute.json/results`에 있다.",
      '### 3.2 창 수준 직선도: 관측 한 개를 0으로 포함할지 결측으로 볼지의 차이',
      '사건 104에서 Gemini는 창 수준 직선도를 0으로 두고 백분위 0.5로 포함했지만 Codex는 시간 간 방향을 정의할 수 없어 결측 처리했다. 이로 인해 Tier0-1 분모가 달라지고 평균 Δ도 약간 달라졌다. 값이 다른 사건을 새 신호라고 해석하면 안 되며, 이후 계약에는 최소 관측 개수와 0/결측 규칙을 명시해야 한다.',
      '### 3.3 방위 집중도·회전 변화: 유효 벡터 수와 부동소수 동률에 민감',
      '공통으로 계산된 사고창 방위 지표 값은 매우 가깝지만, 방위 집중도에서 한 개 변위 벡터를 허용하는지와 대조창의 유효성 정의가 달랐다. 한 벡터의 집중도는 수학적으로 1이지만 일관된 운항 방향의 반복 증거는 아니다. 1 부근의 미세한 실수 오차를 정확 동률 비교가 순위 차이로 확대할 수도 있다.',
      '회전 변화의 사고창 값도 공통 사건에서는 일치하지만 일부 대조 분포 백분위가 다르다. 원래 Gemini T1 생성 소스가 경합으로 보존되지 않아 차이의 모든 원인을 확정할 수 없다. 이 지표들은 통과하지 않았으며, 숫자 일부를 어느 쪽이 우수하다는 근거로 쓰지 않는다. 유효 벡터 수·정지 변위·수치 동률 정책을 고정한 뒤에야 재검토할 수 있다.',
      '출처: `comparison_results.json/primary_event_comparison`, `comparison_t1_event_values.json`. 여기의 사건 번호는 추적용 식별자다.',
      '', '## 4. lin_raw 결론의 강도와 한계',
      f"전체 유효 {alllin['n']}사건에서는 Δ={f(alllin['delta'])}, 원 p={f(alllin['raw_p'])}, 보정 p={f(alllin['adjusted_p'])}로 미통과다. Tier0-1의 결과를 전체 선박·전체 사고의 확증으로 올릴 수 없다. 좁은 연결 조건의 내부 일관성과 사고 선박의 실제 신원 확정도 구분한다.",
      f"Tier0-1의 부호검정 p={f(linre['sign_recomputed'])}는 단일 Bonferroni의 원 p 기준을 넘는다. 사전 주요 검정인 Wilcoxon은 통과했지만 두 검정이 모두 같은 강도로 확인한 것은 아니다. 사건 {linre['n_events']}건은 {linre['n_vessels']}척에서 나왔고, 선박 군집 부트스트랩의 사후 95% CI는 {interval(linre['cluster_bootstrap_ci95_posthoc'])}로 음의 방향을 유지했다. 이 보조 검산으로 선박 반복의 영향을 점검했으며 새 독립 자료의 확증으로 바꾸지는 않는다.",
      f"사후 참고로 두 주요 층까지 K=14로 묶어 보정하면 p={f(data['lin_raw_K14_adjusted_p'])}다. 이는 여전히 0.05보다 작지만 모든 사고유형·설계·후보 탐색을 보정한 결과는 아니다. 이 수치를 원래 기준의 사전 등록 증거로 쓰지 않는다.",
      '창폭을 넓힐 때 효과가 약해지는 현상은 재현되지만, 유효 사건과 대조창 구성도 바뀐다. 이를 “사고시각이 정확하다”, “신고 지연이 없다”는 증거로 단정한 Gemini 서술을 철회한다. 기관손상·부유물감김의 작은 부분집합에서 큰 Δ가 나와도 보정 p가 통과하지 않으면 추가 확증으로 쓰지 않는다.',
      '물리적으로 말할 수 있는 범위는 같은 선박·같은 시각대의 대조창에 비해 `bbox_m/len_m`이 낮은 경향이 있다는 것까지다. 제자리 맴돎·예인 결속·엔진 고장을 실제로 확인한 것은 아니다. `T1_결론상세보고_20261105.md`에 창폭·사고유형·MDE를 따로 해설했다.',
      '', '## 5. T2 상태 분포: 발생률은 재현됐으나 기존 p의 명칭은 정정한다']
    lines+=table(['상태','층(사건)','n','Gemini 사고율','Codex 사고율','Gemini 대조율','Codex 대조율','Gemini p','Codex 결합 p'],
      [[x['state'],x['stratum'],x['n'],f(x['gemini_acc_rate']),f(x['codex_acc_rate']),f(x['gemini_ctrl_rate']),f(x['codex_ctrl_rate']),f(x['gemini_p_rounded_fractional_discordances']),f(x['codex_p_pairing_mixture_merger'])] for x in co['state_comparison']])
    lines+=['','표 출처: `comparison_results.json/state_comparison` (사건별 창 출현율, 대조율은 사건가중). 두 p 열은 같은 검정이 아니며 정확성·검정력의 우열 비교에 쓰지 않는다.',
      '다섯 상태×세 층의 사고율·대조율은 Gemini의 저장 반올림 정밀도에서 일치했다. 상태의 조건부 출현률이라는 기술 결과는 재현된다. 다만 Gemini는 기대 불일치가 소수인 값을 반올림해 이항검정에 넣었다. 이는 실제 짝 관측의 정수 불일치표를 사용하는 정확 McNemar가 아니므로 그 p를 확증 판단에서 폐기한다.',
      '초기 Codex는 모든 대조 짝 조합의 정확 p를 적분해 보수적으로 합쳤다. 이는 계약에 명시되지 않은 p 결합 방식이며 일반 McNemar와 동일하지 않다. 원 결과에는 진단값으로 남기되 방법 차이를 숨기지 않는다.',
      '통합 감사는 모든 대조창을 쓰는 사건별 1:M 조건부 이진 검정을 보조 계산했다. 사건 i의 사고 지표 a, 대조 양성 수 k, 대조 수 M을 놓고 조건부 사고 양성 확률을 (a+k)/(M+1)로 두어 사건 합계의 Poisson-binomial 분포에서 양측 확률을 계산한다. M=1에서는 정확 McNemar로 환원되는 작은 fixture가 통과했다. 기대 소수를 정수로 반올림하지 않는다.',
      '이 방법도 사후 보완이며 동일 선박 사건·겹친 대조창의 의존성이 완전히 제거된 것은 아니다. T2의 원 계약 검정이 소급해 완벽하게 구현됐다고 선언하지 않는다. 상태 5종과 직접표류를 포함한 K=6의 보조 결과에서 채택할 지표는 없었다. 상세 p·MDE·효과 구간은 T2 상세 보고와 `t3_matched_set_binary.json`에 있다.',
      '', '## 6. 직접표류: “0건 대 3건”은 같은 정의의 재현 실패가 아니다']
    lines+=table(['층(사건)','n','Gemini 양성 사건','Codex 양성 사건','Gemini 대조율','Codex 대조율','직접 비교 가능'],
      [[x['stratum'],x['n'],x['gemini_positive_events'],x['codex_positive_events'],f(x['gemini_ctrl_rate']),f(x['codex_ctrl_rate']),'아니오'] for x in co['direct_drift_comparison']])
    lines+=['','표 출처: `comparison_results.json/direct_drift_comparison` (사건별 창 내 출현).',
      'Gemini는 저속 지점의 빈도 상위 고정 격자 세 개를 정박권역으로 제외하고, 창 안의 연속 시간대 두 개를 검사했다. Codex는 자체 항적의 100m 이웃 체류 빈도가 높은 지점을 제외하고 시각 차이가 실제로 2시간 이상인 연속 관측 세 개 이상을 표류로 정의했다. 전체 기간에서 먼저 지속 구간을 만들고 창에 겹친 행을 세는 방식과 창 안에서 지속 조건을 검사하는 방식도 다르다.',
      '따라서 0건과 비영 건수의 차이를 어느 실행자가 표류를 더 잘 찾았다는 근거로 쓰지 않는다. 원 계약이 정박권역의 공간 규모·시간대 coverage와 시각 차이·창 경계 처리를 충분히 고정하지 않은 결과다. 이 정의 차이를 분해하지 않은 상태에서 단일 원인에 귀속하지 않는다.',
      f"Gemini의 ‘대부분 선박의 q10이 5m 미만 지터’ 서술도 데이터로 지지되지 않았다. {audit['profile_diagnostics']['n_vessels']}척의 q10 중앙값은 {f(audit['profile_diagnostics']['q10_len_m_median'])}m이고, 5m 미만은 {audit['profile_diagnostics']['q10_below_5m_vessels']}척, 정확히 0은 {audit['profile_diagnostics']['q10_equal_zero_vessels']}척이다. 엄격한 `len_m<q10`에서 q10=0인 선박은 비음수 길이에 대해 저속 행이 발생하지 않는 정의상 제약을 가진다.",
      '고정 state의 50m·100m 정지 조건은 원천 코드에서 확인됐다. 그러나 해당 사고가 실제로 표류했고 특정 상태로 오분류됐다는 현장 정답은 없다. 조류 속도 범위·외해에서의 불가능·100% 오분류 같은 단정은 이 데이터에서 검증되지 않아 최종 결과에서 제외한다.',
      '영 과다 규칙에 따라 직접표류의 Δ백분위는 계산 근거로 사용하지 않는다. Gemini T2의 저장된 백분위 p도 폐기한다. 결론은 “고정한 표류 대용 지표의 차이를 이 표본·검정력에서 확증하지 못했다”이며 “실제 표류가 없다”가 아니다.',
      '', '## 7. 보존·실행 증거와 남은 검증 범위',
      'Codex T1·T2는 실제 종료코드 0과 이전 메모리 보류 75, 충돌 중단 -1을 execution.json에 남겼다. Gemini의 종료 0은 원 보고서의 자기보고이며, 원 T1 소스·메모리·종료기록이 초기 경합으로 바뀌었으므로 현재 루트의 Codex 종료기록을 Gemini의 증거로 바꾸어 인용하지 않는다.',
      f"Gemini T2 보고서의 불일치 쌍 일부는 JSON 값과도 맞지 않았다. 선택한 표 검사에서 {len(audit['Gemini_T2_table_vs_JSON_mismatches'])}개 행을 확인했으며, 최종 표는 JSON을 직접 읽어 생성했다. 영 과다인데 백분위·Wilcoxon 값이 저장된 T1 그리드 {len(co['gemini_forbidden_zero_inflated_percentile_cells'])}셀도 추론에서 제외했다.",
      (f"원 parquet에서 선택 {ver['raw_status']['n_selected_rows']:,}행·{ver['raw_status']['n_vessels']}척을 다시 읽고 세 지표의 사건별 수치 {ver['raw_status']['n_event_metric_records']}개를 별도 구현으로 재계산했다. 백분위 불일치는 {ver['raw_status']['n_mismatches']}건이고 최대 오차는 {f(ver['raw_status']['max_percentile_error'])}다. 원자료별 상세 결과는 `t3_raw_recompute.json`에 있다." if rawdone else '원 parquet의 전체 재로딩 재검산은 현재 RAM 관문에서 보류됐다. 저장된 사건별 자료의 여섯 통계 재계산은 완료했지만, 이를 원자료 전체 재계산 완료로 표현하지 않는다. 재개 명령과 메모리 확인은 `REPRODUCE.md`에 남긴다.'),
      '별도 세션의 독립 검토자는 이번 통합 작성에 참여하지 않았다. 이번에 완료한 것은 두 실행의 비교·별도 구현 검산·주장 정정과 결과 문서화이며, 공식 탐지 성능·새 데이터 일반화·현장 물리 검증은 완료 범위 밖이다.',
      '', '## 상세 보고서',
      '- [T1 결론 상세](T1_결론상세보고_20261105.md)',
      '- [T2 결론 상세](T2_결론상세보고_20261105.md)',
      '- [검산·규율 감사](t3_audit_report.md)',
      '- [최종 라운드 결과](ROUND_REPORT.md)',
      '- [재현 명령·증거 경로](REPRODUCE.md)']
    write(R/'ROUND010_비교및결과보고_20261105.md',lines)
    # T1 detailed conclusions.
    t1=['# T1 결론 상세 보고 — 직선도 성분 분해','']+base+['',
      '## 결론 1. lin_raw는 Tier0-1의 후속 검증 후보로 유지한다',
      '관측 결과는 같은 시각대·관측행수의 선박 내 대조분포에서 사고창 비율이 상대적으로 낮다는 것이다. 분모가 1m 미만인 행을 제외하고 시간별 bbox/path 비율을 관측 시간에 대해 평균했다. 원래 클램프와 다른 정의이므로 비율이 안정화됐다는 설명과 사고 기제를 규명했다는 설명을 구분한다.']
    t1+=table(['층(사건)','유효 n','Δ백분위','원 p','보정 p(K=7)','95% CI','MDE 근사','부호/10'],
      [[s,gates['lin_raw',s]['n'],f(gates['lin_raw',s]['delta']),f(gates['lin_raw',s]['raw_p']),f(gates['lin_raw',s]['adjusted_p']),interval(gates['lin_raw',s]['ci95']),f(gates['lin_raw',s]['mde']),gates['lin_raw',s]['sign_count']] for s in ['ALL','Tier0_1']])
    t1+=['','출처: `comparison_results.json/canonical_gate` (사건 단위). 주요 검정은 Wilcoxon이며 부호검정은 보조다.',
      f"Tier0-1의 Δ·p·MDE는 별도 구현에서 재현됐고, {linre['n_vessels']}척의 군집 재표집 구간 {interval(linre['cluster_bootstrap_ci95_posthoc'])}도 0을 포함하지 않았다. 반면 보조 부호검정 p={f(linre['sign_recomputed'])}는 K=7 기준을 충족하지 않았다. 신호 방향은 반복됐지만 검정 방식에 상관없이 모두 통과한 것은 아니다.",
      '최종 조치는 후보 하나를 남기는 것이다. 전체 집합은 보정 검정 미통과이며, 원 선박 연결 오류와 반복 dev 탐색의 불확실성이 남는다. 사고 탐지 모델의 성능 개선이나 예인 행동의 확인을 선언하지 않는다.',
      '', '## 결론 2. 단일 Bonferroni와 계약의 이중 해석을 구분한다',
      f"표준 K=7의 α는 원 p 기준 {f(.05/7)}이며 보정 p 기준은 0.05다. 이 경우 lin_raw/Tier0-1은 통과한다. Codex 초기의 보정 p<{f(.05/7)} 해석은 K=49 수준으로 한 번 더 엄격해져 보정 p={f(data['lin_raw_K49_adjusted_p'])}에 해당한다. 그 결과를 보통의 K=7에서도 경로가 기각됐다는 뜻으로 사용하지 않는다.",
      '이번 정정은 새 유의수준을 성능에 맞춰 선택한 척하는 것이 아니라, 두 실행이 왜 같은 수치로 다른 결론을 냈는지 수학적 기준을 공개하는 것이다. 문자 그대로의 계약 판정은 원 결과에 남아 있으며, 후속 실행 전에는 검정 p의 종류와 α를 하나의 수식으로 확정해야 한다.',
      '', '## 결론 3. 나머지 여섯 성분은 이번 관문에서 승격하지 않는다']
    for metric,title,meaning,limit in [
      ('straight_win','창 수준 직선도','창의 첫·끝 중심점 순변위를 관측 len_m 합으로 나눈 값','한 관측일 때의 0/결측 정의가 달라 분모가 바뀌었다. 이는 실제 시간 간 운항 경로 길이를 모두 관측한 직선성이 아니다.'),
      ('speed_mean','시간당 경로장 평균','관측된 시간의 len_m 평균으로 활동량을 요약한 값','실제 순간속도·가속도를 계산한 것이 아니며, 양의 평균 차이가 기관고장 부재를 뜻하지 않는다.'),
      ('step_mean','시간 간 중심점 평균변위율','연속 관측 중심점의 거리를 실제 시간 간격으로 나눈 평균','결측 사이의 실제 경로는 알 수 없다. 직선 연결 거리를 실제 항로·순간속도로 해석하지 않는다.'),
      ('bearing_consistency','방위 원형 집중도','유효 변위 방위의 평균 합성 벡터 길이','한 벡터는 집중도 1이어도 반복 일관성의 증거가 아니며 1 부근 실수 동률과 유효 벡터 정의에 민감하다.'),
      ('turn_rate','방위 변화 절대값 평균','연속 변위 벡터 간 최소 원형각 차이의 평균(rad)','각도 차이의 평균이며 시간으로 나눈 각속도 단위가 아니다. 실제 시간 내 선회를 모두 측정한 것은 아니다.')]:
        t1+=['',f'### {title} ({metric})',meaning+'다.']
        t1+=table(['층(사건)','유효 n','Δ백분위','원 p','95% CI','MDE 근사','부호/10'],
          [[s,gates[metric,s]['n'],f(gates[metric,s]['delta']),f(gates[metric,s]['raw_p']),interval(gates[metric,s]['ci95']),f(gates[metric,s]['mde']),gates[metric,s]['sign_count']] for s in ['ALL','Tier0_1']])
        t1+=['',limit,'두 층 모두 고정 네 조건을 함께 만족하지 않아 승격하지 않는다. 표의 MDE는 보정 α에서 80% 검정력을 계획한 정규근사이며, 그보다 작은 효과의 안정적 검출을 기대하기 어렵다. 정확 비모수 검정력 또는 효과 부재의 증명은 아니다.',
          '출처: `comparison_results.json/canonical_gate`; 두 실행의 차이: `primary_event_comparison`. 방위·회전의 정밀 수치 차이는 미해결 수치·유효성 정책의 영향을 포함해 확증에 쓰지 않는다.']
    t1+=['','### 정지 비율 (still_frac)',
      '사고창의 0 비율이 높아 백분위-Wilcoxon을 사용하지 않는다. 사고/대조의 관측 값이 0을 초과했는지로 비교해야 한다. Gemini 그리드에 저장된 백분위 p는 이 규칙에 따라 제외하며, 소수 기대 불일치 반올림 p도 정확 McNemar로 인정하지 않는다.']
    t1+=table(['층(사건)','n','사고 양성률','대조 양성률','1:M 조건부 p','K=7 보정 p','양성률 차이 95% CI','MDE 근사'],
      [[v['stratum'],v['n_events'],f(v['acc_rate']),f(v['control_rate_event_weighted']),f(v['conditional_exact_p']),f(v['p_bonferroni']),interval(v['ci95_positive_rate']),f(v['mde80_positive_rate_approx'])] for v in binary['T1_still_frac_supplement']])
    t1+=['','사후 1:M 보조 검정에서도 채택 근거를 얻지 못했다. 이 표는 사건가중 양성률 차이 단위이며 백분위 차이 단위가 아니다. MDE는 기존 기대 불일치 기반 근사로 이 조건부 검정의 정확 검정력을 보장하지 않는다. 출처: `t3_matched_set_binary.json/T1_still_frac_supplement`.',
      '', '## 결론 4. 창폭 민감도는 시간 정확도의 증명이 아니다']
    widths=[x for x in ca['results'] if x['metric']=='lin_raw' and x['design']=='hod_1/nrows_matched' and x['stratum'] in ['ALL','Tier0_1']]
    t1+=table(['반폭(h)','층(사건)','유효 n','Δ백분위','원 p','95% CI','MDE 근사'],[[v['half_width_h'],v['stratum'],v['n_events'],f(v['delta_percentile']),f(v['p_raw']),interval(v['ci95']),f(v['mde80_percentile_approx'])] for v in widths])
    t1+=['','출처: `codex_independent/t1_gate_results.json/results`. ±3h에서 상대적으로 큰 효과가 관찰되지만 더 넓은 창은 다른 사건·대조집합을 사용한다. 신고 지연·효과 희석·선택 차이를 구별할 수 없다. 모든 폭에서 중심 가드 76h를 고정했기 때문에 넓은 창은 경계가 사고 여파에 더 가까워질 수 있다는 한계도 남는다.',
      '', '## 결론 5. 사고유형별 큰 수치는 작은 부분집합의 탐색 결과다']
    types=[x for x in ca['results'] if x['metric']=='lin_raw' and x['half_width_h']==3 and x['design']=='hod_1/nrows_matched' and x['stratum'] not in ['ALL','Tier0_1']]
    t1+=table(['층(사건)','유효 n','Δ백분위','보정 p(K=7)','95% CI','MDE 근사'],[[v['stratum'],v['n_events'],f(v['delta_percentile']),f(v['p_bonferroni']),interval(v['ci95']),f(v['mde80_percentile_approx'])] for v in types])
    t1+=['','출처: 동일 JSON/results (사건 단위). 기관손상과 부유물감김의 Tier0-1 부분집합에서 큰 음의 Δ가 있지만 유효 표본이 작고 보정 p는 통과하지 않았다. 화재의 큰 값도 같은 한계를 가진다. 작은 표본의 백분위 bootstrap 구간이 0을 제외해도 단독으로 검정 통과를 대신할 수 없다. 더 유리한 층만 골라 전체 효과를 설명하지 않는다.',
      '', '## 최종 조치',
      '`lin_raw`만 후속 검증 후보로 유지하고 나머지 성분은 이번 단계에서 승격하지 않는다. 절대 위치·격자 ID를 모델 특징으로 추가하지 않으며 모델 학습·임계값 설정·2025 테스트 평가를 시작하지 않는다. 원자료 재검산 상태와 실제 종료코드는 최종 감사 보고에 구분했다.']
    write(R/'T1_결론상세보고_20261105.md',t1)
    write(R/'t1_report.md',['> 최신 통합·정정본. Gemini 원 보고서는 comparison_20261105/original_root_snapshot/t1_report.md에 보존했다.','']+t1)
    # T2 detailed conclusions.
    t2=['# T2 결론 상세 보고 — 상태 분류와 직접표류','']+base+['',
      '## 결론 1. 상태의 생성 규칙은 찾았지만 표류 정답은 아니다',
      '원천 코드는 `D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py`의 score_vessel이다. stop은 len_m≤50m 및 bbox_m≤100m를 동시에 요구한다. stop 중 공용 항구 또는 과거 자체 야간 정박지에서 1km 이내이면 정박정지, 두 거리 모두 2km 이상이면 해상정지, 그 사이는 연안정지다. 비정지 중 len_m>3km이고 bbox_m/len_m≥0.6이면 이동, 나머지는 저속굴곡이다.',
      '이 규칙은 위치·길이 대용치에 따른 상태 분할이다. 엔진의 실제 작동 여부나 사고 표류 여부를 정답으로 학습한 분류기가 아니다. 현재 source 파일과 생성 체인은 확인했지만 과거 parquet 생성 당시 파일 버전과 바이트 단위로 일치한다는 증명은 없다. 원천 경로·상수·해시는 `codex_independent/t2_state_source.json`에 있다.',
      '', '## 결론 2. 다섯 상태의 사고·대조 출현률은 재현된다',
      '한 창에 상태가 한 번이라도 나타났는지를 세는 출현률이다. 여러 상태가 한 창에 함께 있으므로 이 표의 상태별 비율을 합쳐 100%가 되어야 한다고 해석하지 않는다. 행 단위 구성비와도 다르다. 대조율은 각 사건의 전수 대조창 평균을 사건별 동일 가중으로 합친 값이다.']
    t2+=table(['상태','층(사건)','유효 n','사고 출현률','대조 출현률','차이','1:M 조건부 원 p','K=6 보정 p','MDE 근사'],
      [[v['metric'],v['stratum'],v['n_events'],f(v['acc_rate']),f(v['control_rate_event_weighted']),f(v['acc_rate']-v['control_rate_event_weighted']),f(v['conditional_exact_p']),f(v['p_bonferroni']),f(v['mde80_positive_rate_approx'])] for v in binary['results'] if v['metric']!='direct_drift'])
    t2+=['','출처: `t3_matched_set_binary.json/results` (사건 단위). 기존 두 실행의 발생률 교차 확인은 `comparison_results.json/state_comparison`이다.',
      '정박정지 전체 집합의 원 p는 명목 0.05 아래지만 K=6 보정 후에는 통과하지 않는다. 이 값만 골라 새로운 사고 특징으로 채택하지 않는다. 해상정지는 더 낮아 보이는 방향이지만 보정 검정에서 확증되지 않았다. 어느 상태도 이번 기준으로 채택하지 않는다.',
      '각 표의 MDE는 양성률 차이의 근사 계획값이다. 기대 불일치 분산을 사용한 정규근사로서 작은 표본·상태 의존·같은 선박 반복을 완전히 반영하지 않는다. 작은 층에서 관측 분산이 0이라고 MDE=0으로 보고하지 않으며, 검출이 불가능한 경우 JSON mde_status를 명시했다.',
      '']
    state_interpretation={
      '저속굴곡':'이 상태는 정지 조건과 높은 직선 이동 조건에 들지 않는 여러 행동을 함께 포함한다. 사고창의 높은 출현률만으로 사고 특이성을 말할 수 없고, 대조창에서도 비슷하게 흔한지 함께 봐야 한다. 실제 조업·표류·선회 원인 중 무엇인지는 상태 이름만으로 식별되지 않는다.',
      '이동':'이 상태의 사고창 출현이 조금 낮아 보이더라도 실제 엔진 고장이나 정지의 정답으로 바꿀 수 없다. 길이와 직선도 문턱을 넘은 관측의 출현 여부이며, 이번 조건부 검정은 차이를 확증하지 못했다.',
      '정박정지':'전체 집합에서 양의 차이와 명목 유의성이 보이는 항목이다. 그러나 다중검정 보정 후에는 채택 기준을 넘지 못한다. 항구 귀항·수리·정상 정박·연결 오차 중 원인을 구별할 추가 근거도 없으므로 사고의 결과 행동이라고 확정하지 않는다.',
      '해상정지':'처음 표류 가설이 기대한 증가 방향과 달리 전체 사고창에서 낮은 쪽이다. 이것이 실제 표류가 없다는 뜻은 아니다. 위치·정지 임계값으로 만든 상태가 실제 표류와 얼마나 일치하는지는 현장 정답이 없어 평가할 수 없다.',
      '연안정지':'출현 사건 자체가 적은 희소 항목이다. 전체 창 출현률의 작은 차이와 비유의 p를 효과 부재로 해석하지 않는다. 이 표본수와 MDE로는 작은 양성률 차이에 대한 안정적 결론이 어렵다.'}
    for state,explanation in state_interpretation.items():
        v=next(x for x in binary['results'] if x['metric']==state and x['stratum']=='ALL')
        t2+=['',f'### {state}의 개별 해석',
          f"전체 유효 {v['n_events']}사건에서 사고 출현률은 {f(v['acc_rate'])}, 사건가중 대조율은 {f(v['control_rate_event_weighted'])}다. 양성률 차이의 사건 bootstrap 95% CI는 {interval(v['ci95_positive_rate'])}, 보정 p는 {f(v['p_bonferroni'])}, MDE 근사는 {f(v['mde80_positive_rate_approx'])}다. 출처: `t3_matched_set_binary.json/results`의 해당 metric·ALL.",explanation]
    t2+=['', '## 결론 3. Gemini의 정확 McNemar p는 철회하고 두 Codex 방식도 구분한다',
      'Gemini는 a_i(1-q_i)와 (1-a_i)q_i를 더해 소수 형태의 기대 불일치 수를 만든 뒤 반올림했다. 일반 정확 McNemar는 실제 정수 짝의 불일치 수를 조건화한다. 기대 수의 반올림은 그 자료 구조를 재현하지 않으므로 “정확”이라는 명칭이 맞지 않는다.',
      '초기 Codex의 p 적분·보수 결합은 모든 가능한 짝을 활용하는 별도 진단이다. 이번 통합의 1:M 조건부 보조 검정은 모든 대조창을 한 matched set에 포함한다. 사건별 사고·대조 양성 총수를 조건화한 확률 (a_i+k_i)/(M_i+1)을 사용하고, 그 확률의 사건 합계 분포를 계산한다. 대조 하나인 경우 일반 McNemar로 환원되는지 fixture로 확인했다.',
      '다만 1:M 보조 검정은 원 계약의 미정의 부분을 사후에 보완한 방법이며, 서로 겹친 창·같은 선박의 여러 사건을 완전히 독립이라고 보장할 수 없다. 따라서 원 계약의 일반 McNemar가 소급 검증됐다고 선언하지 않는다. 효과·발생률은 재현 사실로, p는 조건부 가정이 있는 보조 결과로 구분한다.',
      '', '## 결론 4. 직접표류의 서로 다른 정의를 성능 비교로 바꾸지 않는다']
    t2+=table(['요소','Gemini','Codex'],[
      ['저속','자체 len_m q10 미만','동일'],
      ['정박권역','저속 지점 0.005도 격자 빈도 상위 3개','자체 전체 지점 100m 이웃 체류빈도 상위 10%·이웃수>1'],
      ['지속 기준','창 안에서 연속된 2개 시간대','관측 시각 차이≥2h·연속 3개 관측 이상'],
      ['창 경계','창 안에서 연속 조건 충족','전체 기간의 지속 구간과 창이 겹치는 행'],
      ['저장 지표','발생 여부 및 저속 후보 시간 수','지속 표류 행의 관측시간 비율']])
    t2+=['','출처: Gemini `original_root_snapshot/t2_state_audit.py`, Codex `codex_independent/t2_state_audit.py`. 고정 격자를 내부 체류빈도 계산에 쓴 사실만으로 모델에 격자 ID 특징을 넣었다고 단정하지는 않는다. 그러나 두 정박권역 정의가 같다고 할 수는 없다. 시간대 coverage와 관측 시각의 경과시간 중 무엇을 지속시간으로 볼지도 계약에 고정해야 한다.']
    t2+=table(['층(사건)','n','Gemini 양성 사건','Codex 양성 사건','Codex 양성률 차이','차이 95% CI','1:M 보정 p','MDE 근사'],
      [[v['stratum'],v['n_events'],next(d['gemini_positive_events'] for d in co['direct_drift_comparison'] if d['stratum']==v['stratum']),v['acc_positive_count'],f(v['acc_rate']-v['control_rate_event_weighted']),interval(v['ci95_positive_rate']),f(v['p_bonferroni']),f(v['mde80_positive_rate_approx'])] for v in binary['results'] if v['metric']=='direct_drift'])
    t2+=['','출처: `comparison_results.json/direct_drift_comparison`, `t3_matched_set_binary.json/results`. 사고창의 영 과다 때문에 Δ백분위를 쓰지 않는다.',
      '한 정의에서 0건이고 다른 정의에서 비영이라고 해서 더 좋은 표류 탐지기가 증명된 것이 아니다. 실제 표류 정답 없이 민감도·특이도·오분류율을 계산할 수 없다. 두 정의의 차이를 표준화한 별도 대조 실험도 아직 하지 않았으므로 어느 요소가 건수 차이를 만들었는지 정량 귀속하지 않는다.',
      '', '## 결론 5. q10을 거의 모두 지터라고 한 물리 해석은 데이터와 맞지 않는다']
    pr=audit['profile_diagnostics']
    t2+=table(['선박 단위 지표','값'],[['대상 선박',pr['n_vessels']],['q10 최솟값(m)',f(pr['q10_len_m_min'])],['q10 중앙값(m)',f(pr['q10_len_m_median'])],['q10 최댓값(m)',f(pr['q10_len_m_max'])],['q10<5m 선박',pr['q10_below_5m_vessels']],['q10=0 선박',pr['q10_equal_zero_vessels']]])
    t2+=['','출처: `report_claims_audit.json/profile_diagnostics` (선박 단위).',
      'q10=0인 선박은 엄격한 `<q10` 조건에서 저속 행이 나오지 않는다. 이는 실제로 고장이 없다는 증거가 아니라 지표 정의의 바닥 효과다. 다른 선박에서는 q10이 훨씬 높을 수 있으므로 “대부분 5m 미만”, “모두 계류 지터”라고 묶을 수 없다.',
      '조류·풍압의 특정 속도 범위나 외해의 물리적 불가능은 이 항적 요약표에서 실측하지 않았다. 저속굴곡으로 분류된 비율은 규칙에 따른 출현률이며, 실제 표류가 모두 그 상태로 오분류됐다는 비율이 아니다.',
      '', '## 최종 조치',
      '상태와 직접표류는 이번 단계의 확증 특징으로 승격하지 않는다. 반대로 실제 표류 부재나 고정 state의 사고 정답 누락률을 확정하지도 않는다. 다음 단계가 필요하다면 먼저 정박권역·지속시간·경계 처리와 1:M 검정의 사건 의존성 정책을 고정하고 현장 정답과 시간해상도를 확인해야 한다.']
    write(R/'T2_결론상세보고_20261105.md',t2)
    write(R/'t2_report.md',['> 최신 통합·정정본. Gemini 원 보고서는 comparison_20261105/original_root_snapshot/t2_report.md에 보존했다.','']+t2)
    # Audit outcome: explicit completed and unverified components.
    au=['# Round010 검산·규율 감사','']+base+['',
      '## 확인한 항목',
      '- 기본 설계의 사건별 lin_raw·speed_mean·step_mean 백분위 교차 일치.',
      '- 같은 세 지표의 전체/Tier0-1 Δ·Wilcoxon·부호검정·MDE를 생산 함수나 SciPy 없이 별도 재계산.',
      '- 선박 군집 부트스트랩으로 반복 사건의 영향을 사후 점검.',
      '- 상태 5종×3층 발생률의 저장 반올림 정밀도 일치.',
      '- 1:M 조건부 이진 검정의 M=1 McNemar 환원 fixture.',
      '- 소스·종료기록 경합, 영 과다 p 저장, 기대 불일치 반올림, 과잉 물리 해석과 작은 층 MDE 처리.',
      '', '## 재계산 수치']
    au+=table(['지표','층(사건)','n','Δ 오차','Wilcoxon p 오차','군집 CI(사후)'],[[x['metric'],x['stratum'],x['n_events'],f(x['delta_abs_error']),f(x['wilcoxon_abs_error']),interval(x['cluster_bootstrap_ci95_posthoc'])] for x in ver['event_summary_recomputations']])
    au+=['','출처: `comparison_20261105/t3_event_recompute.json/results`.',
      '', '## 판정별 처리']
    au+=table(['원 주장','감사 판정','이유'],[[x['claim'],x['verdict'],x['reason']] for x in audit['claim_audit']])
    au+=['','출처: `comparison_20261105/report_claims_audit.json/claim_audit`.',
      '', '## 원자료 재검산과 독립성',
      ('원 parquet 재계산 완료. `t3_raw_recompute.json`의 원자료별 사건수·백분위 오차·불일치 목록을 확인했다.' if rawdone else '원 parquet 재계산은 RAM 부족으로 보류했다. 일부 선박까지 읽거나 계산한 시도는 전체 완료로 세지 않았고, t3_memory.json과 raw_status에 남겼다. 저장 사건자료의 통계 검산과 원자료 전체 파이프라인 재검산을 구분한다.'),
      '별도 세션의 독립 검토자가 수행한 T3라는 수용 조건은 충족했다고 표현하지 않는다. 여기서의 독립은 같은 작성자의 별도 코드 구현이라는 뜻이다. 원 결과를 본 사후 감사이므로 새로운 blind test도 아니다.',
      '', '## 최종 감사 결론',
      '통상 K=7 기준에서 lin_raw/Tier0-1은 후속 후보로 유지 가능하다. 전체 집합·다른 6지표·상태·직접표류를 확증 특징으로 승격할 근거는 없다. 과도한 이중 보정에 의한 경로 전체 기각과 실제 표류·예인 기제를 확정한 원 서술을 모두 정정한다.']
    write(R/'t3_audit_report.md',au)
    # Compact final status links to detailed reports, without deleting historic prose.
    final=['# Round010 최종 결과','']+base+['',
      '## 완료한 작업',
      'Gemini와 Codex의 결과·유효 사건·지표 정의를 맞춰 교차 비교하고, 별도 구현 통계 검산과 주장 감사를 수행했다. 원 보고서는 `comparison_20261105/original_root_snapshot/`에 보존했다.',
      '', '## 최종 판정',
      f"**lin_raw를 Tier0-1의 단일 후속 검증 후보로 채택한다.** 유효 {lin['n']}사건·{linre['n_vessels']}척에서 Δ={f(lin['delta'])}, 원 p={f(lin['raw_p'])}, K=7 보정 p={f(lin['adjusted_p'])}, 사건 CI={interval(lin['ci95'])}, 설계 부호 10/10이다. 통상 단일 Bonferroni 기준의 판정이며, 문자 그대로 이중 보정한 초기 Codex의 경로 전체 기각과 구분한다.",
      f"전체 {alllin['n']}유효 사건의 보정 p={f(alllin['adjusted_p'])}는 미통과다. 나머지 여섯 기구학 지표와 상태·직접표류도 이번 단계에서 승격하지 않는다. 비유의는 효과 부재의 증명이 아니며 지표별 MDE·표본수·정의 차이를 상세 보고했다.",
      '사고시각 정확성, 실제 표류·예인 기제, 엔진 상태, 사고 탐지 성능은 확증되지 않았다. 새로운 학습·임계값 선정·2025 테스트 사용·공식 제출을 수행하지 않았다.',
      '', '## 비교에서 바로잡은 부분',
      '- 동일한 lin_raw 수치가 재현됐는데 다중검정 해석 때문에 결론이 달랐던 문제.',
      '- 정확 McNemar라는 이름으로 기대 불일치 소수를 반올림한 문제와 두 Codex 확장의 구분.',
      '- 영 과다 지표의 백분위 결과를 저장·인용한 문제.',
      '- 직접표류의 서로 다른 정박권역·지속시간·경계 처리를 같은 정의로 취급한 문제.',
      '- q10·사고시각·물리 원인·무신호에 관한 과잉 해석.',
      '- 초기 출력 경합으로 Gemini T1 소스·종료기록의 계보가 손상된 문제.',
      '', '## 검산의 범위와 남은 조건',
      ('원자료에서 세 지표의 사건별 백분위 재계산을 완료했다.' if rawdone else '저장된 사건자료의 여섯 통계 재계산은 완료했고 원 parquet의 전체 재검산은 RAM 관문으로 보류했다.'),
      '별도 세션 검토자의 승인은 미확인이다. 기존 계약의 모호한 보정 p 문구와 다중 대조창 이진 검정은 다음 실행 전에 명확히 고정해야 한다. 후보 채택과 원 계약의 모든 형식적 수용 조건 충족을 구분한다.',
      '', '## 읽을 보고서',
      '- [비교 및 결과 보고](ROUND010_비교및결과보고_20261105.md): 일치·차이·정정 판단의 근거.',
      '- [T1 상세 결론](T1_결론상세보고_20261105.md): 일곱 성분, 창폭, 사고유형, 검정력.',
      '- [T2 상세 결론](T2_결론상세보고_20261105.md): 상태 생성, 이진 검정, 직접표류 정의.',
      '- [검산 감사](t3_audit_report.md): 재계산·출처·미확인 범위.',
      '- [다음 단계](NEXT_ROUND.md), [재현](REPRODUCE.md).',
      '', '수치 원본: `comparison_20261105/final_decision.json`, `comparison_results.json`, `t3_verification.json`, `t3_matched_set_binary.json`. 실제 실행 이력: `phase_execution.json` 및 `codex_independent/*_execution.json`.']
    write(R/'ROUND_REPORT.md',final);write(R/'ROUND010_실행보고_20261105.md',final)
    write(R/'NEXT_ROUND.md',['# Round011 인계 — 이번 요청에서는 실행하지 않음','',
      '먼저 읽기: ROUND_REPORT.md → T1·T2 상세 보고 → t3_audit_report.md → comparison_20261105/final_decision.json.',
      '', '## 유지할 후보와 검증 질문',
      '- lin_raw 하나를 사전 후보로 동결한다. 전체 집합과 Tier0-1의 성능을 분리한다.',
      '- K=7 원 p 기준 0.05/7와 보정 p 기준 0.05를 같은 식으로 쓰고, 이중 보정 문구를 제거한다.',
      '- 같은 dev 반복 탐색을 새 독립 검증이라고 부르지 않고, 새 평가 자료의 허용 범위·선박/사건 의존성을 먼저 확정한다.',
      '- 정지·방위의 유효 관측/벡터 수와 수치 동률 규칙을 고정한다.',
      '- 상태·직접표류를 다시 보려면 정박권역·지속시간·창 경계·1:M 이진 검정과 의존성 처리를 먼저 고정한다.',
      '', '## 남은 실행·검토',
      ('- 원 parquet 세 지표 재계산은 완료됐다. 상세 오차는 t3_raw_recompute.json을 따른다.' if rawdone else '- 원 parquet 재계산은 RAM 관문 통과 후 t3_recompute.py로 재개한다. polling하지 말고 작업 경계에서 새 확인을 남긴다.'),
      '- 별도 검토자 세션의 수치·출처 확인은 미확인이다. 이번 동일 작성자의 별도 구현 검산과 혼동하지 않는다.',
      '- Gemini T1 원 생성 소스가 복원되지 않으면 원소스 미확인 상태를 유지한다. 현재 루트 T1은 Codex 경합 사본이다.',
      '- 새로운 모델 학습·2025 테스트 사용·실선 실험·공식 제출은 이번 완료 작업에 포함하지 않는다.'])
    write(R/'REPRODUCE.md',['# Round010 비교 재현','',
      '현재 루트의 t1_decompose.py는 초기 경합의 Codex 사본이며 Gemini 원 생성 소스로 쓰지 않는다. 루트 원 보고서는 comparison_20261105/original_root_snapshot에 있다. 원 수치·코드를 덮어쓰는 구형 실행 대신 아래 새 비교 스크립트를 쓴다.',
      '', '작업공간 루트에서:',
      '```powershell',
      'python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" compare_results.py',
      'python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" audit_report_claims.py',
      'python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" t3_recompute.py --evidence-only',
      'python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" write_final_reports.py',
      'python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" closeout_round.py',
      'python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" validate_final_artifacts.py',
      '```','',
      '원 parquet 재계산은 RAM을 실행 직전에 확인하는 아래 명령이다. 메모리 미달이면 raw_status=deferred_memory로 돌아오며 전체 원자료 완료로 세지 않는다. 선택 로딩·변환은 순차 실행이고 사용자 프로세스를 종료하지 않는다.',
      '```powershell','python -B "testB/round_010_20261105/comparison_20261105/run_phase.py" t3_recompute.py','```','',
      '가정: Python 표준 라이브러리, 원자료 재검산에는 현재 환경의 PyArrow. 검산은 생산 함수와 SciPy의 검정 함수를 import하지 않는다. 과거 Codex 2000회 사건 bootstrap은 원 NumPy 결과를 보존하고, 별도 군집 bootstrap은 Python Random seed20261105의 사후 민감도다.',
      '메모리 예산의 변경 근거·실제 관측 RSS·가용 RAM은 t3_memory.json에 모두 남겼다. 초기에 보수적 512MiB 추가 여유를 중복 요구한 시도와 총 RSS 기반·관측 보정 예산을 구분한다. 가용 RAM reserve 1GiB는 대용량 검산에서 유지한다.',
      '별도 세션 T3 승인은 이 재현 명령이 대신하지 않는다.'])
    write(R/'README.md',['# Round010 완료 결과 진입점','',
      '사용자 요청에 따라 Gemini–Codex 비교와 결론별 상세 해설, 원자료 재계산·통계 검산을 완료했다. 최신 결과는 다음 문서가 기준이다.','',
      '- [최종 결과](ROUND_REPORT.md)',
      '- [비교 및 결과 보고](ROUND010_비교및결과보고_20261105.md)',
      '- [T1 상세 결론](T1_결론상세보고_20261105.md)',
      '- [T2 상세 결론](T2_결론상세보고_20261105.md)',
      '- [검산·규율 감사](t3_audit_report.md)',
      '- [수용 조건과 완료 범위](ROUND010_수용조건점검_20261105.md)',
      '- [재현 방법](REPRODUCE.md)','',
      '루트 t1_report.md·t2_report.md·실행보고는 정정한 통합본이다. Gemini의 원 보고서와 당시 루트 파일 사본은 comparison_20261105/original_root_snapshot에 있고, 독립 Codex 실험은 codex_independent에 있다. 두 실행의 최초 물리 해석·다중검정 판단을 최신 판정으로 혼동하지 않는다.','',
      '루트 t1_gate_results.json·t2_state_distribution.json은 Gemini의 원 수치다. 최신 비교·판정·검산 JSON은 comparison_20261105에 있다. 루트 T1 소스·메모리·종료기록은 초기 출력 경합의 Codex 사본이므로 Gemini 원 생성 소스나 실제 종료코드 증거가 아니다. 구형 run_task.ps1 대신 REPRODUCE.md의 비교 스크립트를 사용한다.','',
      '최종 후보는 단일 Bonferroni 기준 lin_raw/Tier0-1이다. 문자 그대로의 이중 보정 분기, 별도 세션 검토자 미참여, 공식 성능 미평가도 상세 보고에 공개했다.'])
    print('Detailed comparison, T1, T2, audit and final reports written')
if __name__=='__main__':main()
