"""Trace selected substantive Gemini prose claims to retained artifacts."""
import json,re,statistics
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parent;G=P/'original_root_snapshot';C=ROOT/'codex_independent'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
b=read(G/'t2_state_distribution.json');codex=read(C/'t2_state_distribution.json')
qs=[r['q10_len_m'] for r in codex['profiles']]
profile={'aggregation':'vessel','n_vessels':len(qs),'q10_len_m_min':min(qs),'q10_len_m_median':statistics.median(qs),
 'q10_len_m_max':max(qs),'q10_below_5m_vessels':sum(x<5 for x in qs),'q10_equal_zero_vessels':sum(x==0 for x in qs),
 'sustained_drift_rows':sum(r['sustained_drift_rows'] for r in codex['profiles'])}
table_differences=[];s=None
for line in (G/'t2_report.md').read_text(encoding='utf-8').splitlines():
    if not line.startswith('|'):continue
    cols=[x.strip() for x in line.split('|')[1:-1]]
    if len(cols)!=7:continue
    if '전체 (ALL)' in cols[0]:s='ALL'
    elif 'Tier0-1' in cols[0]:s='Tier0_1'
    elif '기관손상' in cols[0]:s='기관손상_linked_34'
    state=cols[1].replace('*','')
    if not s or state not in ['저속굴곡','이동','정박정지','해상정지','연안정지']:continue
    match=re.fullmatch(r'([0-9.]+) / ([0-9.]+)',cols[5])
    if match:
        record=b['state_distribution_and_drift_audit'][s]['states_mcnemar'][state]
        printed=list(map(float,match.groups()));values=[record['discordant_b10_acc_only'],record['discordant_b01_ctrl_only']]
        if any(abs(a-v)>.0500001 for a,v in zip(printed,values)):
            table_differences.append({'stratum':s,'state':state,'printed_expected_discordances':printed,'json_expected_discordances':values,'tolerance_rounding_1decimal':.05})
claims=[
 {'claim':'Codex 문자 그대로의 최종 경로 기각', 'verdict':'해석 정정 필요','reason':'K=7 단일 Bonferroni와 구별해야 하며 보정 p를 다시 0.05/7과 비교해 K=49 수준 기준을 적용했다. 수치 자체는 Gemini와 재현된다.'},
 {'claim':'lin_raw가 사고의 물리적 선회·예인 기제를 확증', 'verdict':'근거 초과','reason':'동일 dev의 요약지표 차이이며 좌표별 원시 시각·예인 정답·조류·기계 상태가 없다. bbox/path 상대비 차이는 재현되나 원인을 식별하지 못한다.'},
 {'claim':'창폭 확대 효과 약화가 사고시각 지연 없음 증명', 'verdict':'근거 초과','reason':'창폭에 따라 유효 사건과 대조창 집합도 변한다. 희석·표본선택·신고지연을 구분하지 못한다.'},
 {'claim':'p가 비유의인 다른 6지표는 무신호·최종 효과 부재', 'verdict':'기각','reason':'등가성 검정을 하지 않았다. MDE와 CI 범위에서 검출 실패만 말할 수 있다.'},
 {'claim':'대부분 선박 q10이 GPS 지터 <5m 수준', 'verdict':'반증','reason':'82척의 q10 중앙값과 <5m 선박 수를 profile_diagnostics로 직접 확인했다. 공간 진동의 원인도 미확인이다.'},
 {'claim':'state 누락 및 외해 초저속의 물리적 불가능 규명', 'verdict':'근거 초과','reason':'고정 임계값은 원천에서 확인했지만 현장 표류 정답이나 해당 사고의 외력 실측이 없다. 규칙 부적합 가능성과 실제 누락 검증을 구분해야 한다.'},
 {'claim':'Gemini 일반 정확 McNemar p', 'verdict':'통계 명칭 부적합','reason':'기대 불일치 소수를 round해 binomtest에 넣었다. 실제 짝 관측의 정수 불일치 표가 아니며 반올림은 정확 검정이 아니다.'},
 {'claim':'Codex McNemar p 합성은 원 계약 검정과 동일', 'verdict':'동일하지 않음','reason':'전수 짝 조합 정확 p의 적분·2배 결합은 별도 진단이며 단일 정수짝 McNemar로 표시하면 안 된다.'},
 {'claim':'영 과다 지표는 백분위-Wilcoxon 금지 준수', 'verdict':'Gemini 산출물에서 위반','reason':'T1 grid 36셀 및 T2 세 층에 백분위·Wilcoxon p를 저장했다. 최종 추론에서 제외한다.'},
 {'claim':'Gemini T1 실제 코드·종료코드 완전 보존', 'verdict':'검증 불가','reason':'루트 T1 소스·메모리·종료기록이 초기 Codex 경합으로 덮어쓰였다. 보고된 0과 독립 포착 0을 구분한다.'}
]
out={'profile_diagnostics':profile,'Gemini_T2_table_vs_JSON_mismatches':table_differences,'claim_audit':claims,
 'scope':'selected material claims; does not claim literal automated provenance for every word in original reports'}
(P/'report_claims_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'profile_diagnostics':profile,'table_vs_JSON_mismatches':len(table_differences)},ensure_ascii=False))
