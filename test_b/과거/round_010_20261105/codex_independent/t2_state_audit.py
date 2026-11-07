"""독립 Codex T2. T1 다음 순차 실행. 기존 state는 직접표류에 사용하지 않는다."""
import sys
sys.dont_write_bytecode=True
import hashlib,traceback,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import t1_decompose as t
STATES=['저속굴곡','이동','정박정지','해상정지','연안정지']
SCORER=Path(r'D:\repos\fishing-track-classification\code\tools\run_008_testB_20261101.py')
DECISIONS=[
 '창별 state는 해당 상태가 한 번 이상 출현함을 이진값으로 검정한다. 배타적 구성비는 별도 기술통계로 저장한다.',
 '모든 대조창을 사건 내 균등 사용한다. 단일 짝 McNemar가 아니라 모든 짝 조합의 정확 McNemar p를 적분하고 min(1,2*평균p)를 보수 결합한다. 이 확장은 T3 검토가 필요하다.',
 '표류는 자체 len_m q10 미만 AND 자체 정박권역 밖 AND 결측 없는 시간당 관측에서 최소 2시간 지속(3개 관측 이상)이다.',
 '정박권역은 자체 전체 dev 항적 중심점 반경 100m의 체류 횟수가 자체 상위10%이고 1 초과인 지점으로 사전 정의한다. 좌표는 거리 계산에만 쓰고 절대좌표·격자 ID를 특징으로 쓰지 않는다. 이 공간 가정은 항구 정답이 아니며 튜닝하지 않는다.',
 '자체 선박의 전체 평가기간 사후 항적 참조 허용을 적용한다. 다른 선박 및 2025 자료는 사용하지 않는다.',
 '직접표류는 창 내 지속표류 관측 비율이다. 0 비율>50%이면 Δ백분위 요구보다 백분위 금지를 우선해 NA와 McNemar·양성률 차이·MDE를 보고한다.',
 '실제 발생유형 정확일치 사건 수를 사용하고 지시서의 기관손상 58건을 강제하지 않는다.',
 '현장 표류 정답이 없으므로 state 누락과 실제 표류 부재를 양자택일하지 않는다. 시간해상도·정의 차이·검정력 한계를 구분한다.',
 'T2 검정족은 상태 5종과 직접표류를 합친 K=6이다. 민감도·층화 다중성은 추가 탐색 한계다.'
]

def source_audit():
    paths=[t.R8/'rescore_evaluate.py',t.BASE/'round_007_20261105'/'s4_score_dev.py',SCORER]
    source={'status':'원천 코드 확인; 캐시 생성 당시 코드 버전 동일성은 미확인',
      'chain':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
      'source_lines':{'constants':'178-186','score_vessel':'436-474','own_mooring_update':'507-510'},
      'rules':{'stop':'len_m<=50 AND bbox_m<=100','anchored':'stop AND (harbor_dist<=1000m OR own_mooring_dist<=1000m)',
        'sea_stop':'stop AND harbor_dist>=2000m AND own_mooring_dist>=2000m','coast_stop':'remaining stop',
        'moving':'not stop AND len_m>3000 AND bbox_m/len_m>=0.6','slow_turn':'remaining not-stop',
        'own_mooring':'past night stop occupancy top3 0.005-degree cells; night=20..23,0..3; update after classifying current row'}}
    t.save('t2_state_source.json',source);return source

def drift_rows(g):
    ts=g.ts.to_numpy(int);lm=g.len_m.to_numpy(float)
    lat=np.radians(g.cen_lat.to_numpy(float));lon=np.radians(g.cen_lon.to_numpy(float))
    xyz=6371000*np.column_stack([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
    xyz-=xyz[0];finite=np.isfinite(xyz).all(axis=1);counts=np.zeros(len(g),int)
    if finite.any():counts[finite]=cKDTree(xyz[finite]).query_ball_point(xyz[finite],r=100,return_length=True,workers=1)
    cutoff=float(np.quantile(counts[finite],.9)) if finite.any() else None
    anchor=(counts>=cutoff)&(counts>1) if cutoff is not None else np.zeros(len(g),bool)
    q10=float(np.nanquantile(lm,.1));cand=(lm<q10)&~anchor&finite
    drift=np.zeros(len(g),bool);a=0
    while a<len(g):
        if not cand[a]:a+=1;continue
        b=a+1
        while b<len(g) and cand[b] and ts[b]-ts[b-1]==1:b+=1
        if ts[b-1]-ts[a]>=2:drift[a:b]=True
        a=b
    return drift,{'rfid_id':int(g.rfid_id_int.iloc[0]),'n_rows':len(g),'q10_len_m':q10,
      'occupancy_radius_m':100,'occupancy_quantile':.9,'occupancy_cutoff':cutoff,
      'anchor_rows':int(anchor.sum()),'low_speed_rows':int((lm<q10).sum()),
      'candidate_rows':int(cand.sum()),'sustained_drift_rows':int(drift.sum())}

def window_states(g,half,lo,hi,drift):
    W,_=t.make_windows(g,half,lo,hi);W={k:W[k] for k in ['center','n_rows']}
    ts=g.ts.to_numpy(int)-lo;left=np.searchsorted(ts,W['center']-half);right=np.searchsorted(ts,W['center']+half,side='right')
    for name,vals in {**{s:(g.state.to_numpy(str)==s).astype(float) for s in STATES},'direct_drift':drift.astype(float)}.items():
        cs=np.r_[0,np.cumsum(vals)];sums=cs[right]-cs[left]
        fraction=np.divide(sums,W['n_rows'],out=np.full(len(left),np.nan),where=W['n_rows']>0)
        W[name]=fraction if name=='direct_drift' else np.where(W['n_rows']>0,(sums>0).astype(float),np.nan)
        if name in STATES:W['fraction_'+name]=fraction
    return W

def make_report(data):
    lines=['# T2 독립 상태 감사','',data['state_source']['status'],
      '생성 경로: '+' → '.join(x['path'] for x in data['state_source']['chain']),
      '원천 상수·규칙·해시: t2_state_source.json/rules, chain. 코드 추적과 캐시 생성 버전 일치 증명은 구분한다.',
      '', '사고창 ±3h, 시각대 ±1h, n_rows 매칭. 사건 단위 McNemar 전수 짝 조합 적분의 보수 결합 p. K=6, α=0.05/6.',
      '|지표|층(사건)|n|사고 양성률|대조 양성률(사건가중)|양성률 차이|보정 p|MDE 근사|대조<15 제외|','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    fmt=lambda v:'NA' if v is None else f'{v:.6g}'
    primary=[r for r in data['results'] if r['half_width_h']==3 and r['design']==t.design_name(1,True) and r['stratum'] in ['ALL','Tier0_1','기관손상']]
    for r in primary:lines.append('|'+ '|'.join([r['metric'],r['stratum'],str(r['n_events']),fmt(r.get('acc_positive_rate')),fmt(r.get('ctrl_positive_rate_event_weighted')),fmt(r.get('delta_positive_rate')),fmt(r['p_bonferroni']),fmt(r.get('mde80_positive_rate_approx')),str(r['excluded_fewer_than_15_controls'])])+'|')
    lines+=['','출처: t2_state_distribution.json/results (사건 단위). 비유의 결과에서 표의 MDE 미만 양성률 차이는 이 근사 설계로 안정적으로 검출할 수 없다. 정확 McNemar 검정력과 선박 의존성을 보장하는 MDE가 아니다.',
      '', '|직접표류 층(사건)|유효 n|0 비율|Δ백분위|검정법|','|---|---:|---:|---:|---|']
    for r in primary:
        if r['metric']=='direct_drift':lines.append(f"|{r['stratum']}|{r['n_events']}|{fmt(r.get('zero_fraction'))}|{fmt(r['delta_percentile'])}|{r['method']}|")
    lines+=['','NA는 영 과다로 금지된 백분위다. 실제 기관손상 사건 수는 JSON/input/cause_counts에 있다. 행 단위 상태 구성과 사건가중 창 구성비는 JSON/state_row_distribution 및 state_window_fraction_results에 있다.',
      '', '## 이번에 내린 판단과 근거']+['- '+x for x in DECISIONS]
    lines+=['','## 해석','초기에는 기존 상태가 사고 표류를 놓칠 수 있다고 예상했다. 두 정의는 서로의 현장 정답이 아니므로 상태 분류기의 누락 또는 실제 표류 부재를 확정할 수 없다.',
      '실제 종료코드: t2_execution.json. T3 독립 검산은 별도 담당이다.']
    (t.HERE/'t2_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    source=source_audit();pos,sc,meta=t.load_inputs('t2');lo,hi=int(sc.ts.min()),int(sc.ts.max())
    se=[];de=[];fe=[];profiles=[]
    for rid,g in sc.groupby('rfid_id_int',sort=True):
        checkpoint=t.HERE/f't2_checkpoint_{int(rid)}.json'
        if checkpoint.exists():
            t.memory_gate('t2',f'before_vessel_{int(rid)}_checkpoint_load')
            saved=json.loads(checkpoint.read_text(encoding='utf-8'))
            assert saved['version']=='codex_direct_v1'
            se.extend(saved['state_events']);de.extend(saved['drift_events']);fe.extend(saved['fraction_events']);profiles.append(saved['profile'])
            continue
        t.memory_gate('t2',f'before_vessel_{int(rid)}_occupancy_transform')
        drift,profile=drift_rows(g)
        vse=[];vde=[];vfe=[]
        for half in [3,6,12]:
            t.memory_gate('t2',f'before_vessel_{int(rid)}_half_{half}_transform')
            W=window_states(g,half,lo,hi,drift)
            vse.extend(t.collect_events(pos,g,W,half,lo,hi,STATES,binary_metrics=STATES))
            vde.extend(t.collect_events(pos,g,W,half,lo,hi,['direct_drift']))
            vfe.extend(t.collect_events(pos,g,W,half,lo,hi,['fraction_'+s for s in STATES]))
        t.save(checkpoint.name,{'version':'codex_direct_v1','state_events':vse,'drift_events':vde,'fraction_events':vfe,'profile':profile})
        se.extend(vse);de.extend(vde);fe.extend(vfe);profiles.append(profile)
        if len(profiles)%10==0:print(f'T2 vessels={len(profiles)}',flush=True)
    t.memory_gate('t2','before_statistical_summary')
    results=t.all_results(se,STATES,True,.05/6,6)+t.all_results(de,['direct_drift'],False,.05/6,6)
    fractions=[]
    for (half,design,metric),sub in pd.DataFrame(fe).groupby(['half_width_h','design','metric'],sort=False):
        for name,mask in t.strata_masks(sub):
            valid=sub.loc[mask];valid=valid.loc[valid.exclusion.isna()]
            fractions.append({'half_width_h':int(half),'design':design,'metric':metric,'stratum':name,
              'aggregation':'event_weighted_observed_row_fraction','n_events':len(valid),
              'acc_fraction':float(valid.acc_value.mean()) if len(valid) else None,
              'ctrl_fraction_event_weighted':float(valid.ctrl_mean.mean()) if len(valid) else None})
    data={'contract':'R010-GATE','input':meta,'state_source':source,'decisions':DECISIONS,
      'state_row_distribution':{'aggregation':'row','n_rows':len(sc),'counts':sc.state.value_counts().to_dict(),'fractions':sc.state.value_counts(normalize=True).to_dict()},
      'profiles':profiles,'results':results,'state_window_fraction_results':fractions,
      'actual_result_cells':len(results),'expected_result_cells':6*10*12*3,
      'declaration':'state 누락과 실제 표류 부재의 양자택일 불가; 현장 표류 정답과 시간해상도 확인 필요'}
    t.save('t2_state_distribution.json',data);t.save('t2_event_evidence.json',{'state_events':se,'direct_drift_events':de})
    make_report(data);print(data['declaration'],flush=True)

if __name__=='__main__':
    try:main()
    except t.MemoryDeferred as e:print(str(e),flush=True);sys.exit(75)
    except Exception:traceback.print_exc();sys.exit(1)
