"""Round010 independent Codex T1; outputs confined to this directory.

Statistics and unresolved contract interpretations are serialized, never hidden.
No bytecode is written to imported read-only Round009 source directories.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import csv, gc, hashlib, importlib.util, json, math, os, traceback
from functools import lru_cache
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq
from scipy import stats as st

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
R8 = BASE / 'round_008_linkage_audit_20261105'
R9 = BASE / 'round 9'
SOURCE = R9 / 'verify_round9_review.py'
spec = importlib.util.spec_from_file_location('r009_readonly', SOURCE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
build_vessel, ctrl_mask, pct_rank = review.build_vessel, review.ctrl_mask, review.pct_rank
METRICS = ['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
CAUSES = ['기관손상','부유물감김','침수','화재','운항저해']
COLS = ['rfid_id_int','ts','len_m','bbox_m','cen_lon','cen_lat','state','score']
ALPHA = 0.05 / 7
NBOOT = 2000
DESIGNS = [(h, match) for h in [0,1,2,3,None] for match in [True,False]]
DECISIONS = [
 '시각대 무통제 두 설계는 요구된 부호 안정성 진단 JSON/CSV에만 수록하며 본문 결과·승격 근거에서 제외한다.',
 'ctrl_mask는 내부에서 guard_h+4를 사용하므로 guard_h=72로 호출해 모든 사고와의 중심 간격 >=76h를 구현한다. 창폭 민감도에서도 계약의 고정 76h를 유지한다.',
 'build_vessel는 7시간 전용이므로 기본 창의 관측행수와 중심을 이 함수에서 그대로 재사용한다. 13/25시간 민감도는 같은 hourly 인덱스로 확장한다.',
 '필수 선택 컬럼에 없는 s_gap은 build_vessel 호환용 NaN 열로만 추가하며 분석에는 사용하지 않는다.',
 '사고유형은 실제 입력 발생유형의 정확 일치로 층화한다. 지시서의 유형별 사건 수를 강제하지 않는다.',
 '전체와 Tier0-1을 사전 주요 층으로 삼고 각각 고정 4조건을 평가한다. 유형·창폭 민감도만으로 승격하지 않는다. 이 두 주요 층의 탐색 다중성은 K=7 밖의 한계다.',
 '지시서의 보정 p<0.00714를 문자 그대로 적용한다: p_bonferroni=min(1,7*p_raw)<0.05/7. 통상 p_raw<0.05/7 판단도 별도로 저장하되 승격은 더 엄격한 명시 문구를 따른다.',
 '다중 대조창과 사건단위 McNemar의 짝 정의가 계약에 없다. 각 사건의 모든 대조창을 균등하게 짝짓는 모든 조합의 정확 McNemar p를 동적계획법으로 적분하고, 의존 p 평균의 유효 보수 결합값 min(1,2*E[p])을 주 p로 쓴다. 일반 단일 짝 McNemar와 다른 확장이며 T3 승인 전 확증으로 쓰지 않는다.',
 '영 과다는 유효 사고창 중 정확 0 비율 >0.5인 경우다. 해당 층·설계에서는 백분위를 산출/검정하지 않고 0초과 McNemar 확장만 한다. 백분위 효과 조건이 정의되지 않아 승격 불가다.',
 'MDE는 양측 Bonferroni 및 80% power 정규근사 계획값이다. Wilcoxon/중첩창/동일 선박 반복 사건의 정확 검정력 보장은 아니다. 사건 부트스트랩은 계약대로 수행하고 반복 선박 의존성은 한계로 남긴다.',
 '연속 관측 중심점은 결측 시간 간격으로 나누어 step_mean을 구한다. 연결선은 실제 운항 경로가 아니며 m/h 단위 중심점 평균변위율 대용치다. len_m 시간당 평균도 실제 순간속도가 아니다.',
 '방위는 구면 초기방위각, turn_rate는 방위의 최소 원형차 절대값 평균(rad)이다. 0변위는 방위 미정으로 제외하고 그 양쪽의 방위를 임의로 연결하지 않는다.',
 'lin_raw는 len_m>=1인 유효 행의 비율 평균이다. straight_win은 관측 첫/끝 중심점 순변위/관측 len_m 합이며 분모가 0이면 결측, 시간 간 실제 경로의 직선성으로 단정하지 않는다.',
]

def save(name, value):
    def conv(x):
        if isinstance(x, np.generic): return x.item()
        if isinstance(x, np.ndarray): return x.tolist()
        raise TypeError(type(x).__name__)
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=conv),encoding='utf-8')

class MemoryDeferred(RuntimeError): pass

def memory_gate(prefix, stage):
    path = HERE / f'{prefix}_memory.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    processes=[]
    for p in psutil.process_iter(['pid','name','memory_info']):
        try:
            if any(x in (p.info['name'] or '').lower() for x in ['python','antigravity','node','orca']):
                processes.append({'pid':p.pid,'name':p.info['name'],'rss_mib':round(p.info['memory_info'].rss/2**20,2)})
        except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    available=psutil.virtual_memory().available/2**20
    rec={'stage':stage,'checked_at':datetime.now().astimezone().isoformat(),
         'available_mib':available,'estimated_maximum_increment_mib':512,'reserve_mib':1024,
         'estimate_basis':'8 selected columns, 65536-row streaming parquet batches filtered to positive vessels; one vessel/window width at a time; event summaries only; bootstrap <=2000x100 floats',
         'concurrent_processes':processes,'allowed':available>=1536,
         'current_rss_mib':psutil.Process().memory_info().rss/2**20}
    old.append(rec); save(path.name,old)
    if not rec['allowed']: raise MemoryDeferred(f'{stage}: available={available:.1f}MiB <1536MiB; deferred')

def load_inputs(prefix):
    memory_gate(prefix,'before_metadata_loading')
    pos=pd.read_csv(R8/'devset_positives.csv')
    audit=pd.read_csv(R9/'task1_linkage_audit_167.csv')
    linked=audit.set_index('acc_id').loc[pos.acc_id]
    assert np.array_equal(pos.rfid_id.to_numpy(),linked.rfid_id.to_numpy())
    assert np.array_equal(pos.tier.to_numpy(),linked.tier.to_numpy())
    pos['audit_status']=linked.status.to_numpy()
    ids=set(pos.rfid_id.astype(int))
    pf=pq.ParquetFile(R8/'dev_hourly_scores.parquet')
    frames=[]
    # Gates are at execution boundaries, never a time/polling loop.
    for i,batch in enumerate(pf.iter_batches(batch_size=65536,columns=COLS,use_threads=False)):
        memory_gate(prefix,f'before_batch_{i}_conversion')
        df=batch.to_pandas()
        sub=df.loc[df.rfid_id_int.isin(ids)].copy()
        if len(sub): frames.append(sub)
        del df,batch
    memory_gate(prefix,'before_filtered_concat_sort')
    sc=pd.concat(frames,ignore_index=True).sort_values(['rfid_id_int','ts'],kind='stable')
    del frames; gc.collect()
    assert not sc.duplicated(['rfid_id_int','ts']).any(), 'duplicate vessel/hour requires explicit policy'
    assert np.isfinite(sc.ts).all()
    assert (sc.ts == np.floor(sc.ts)).all()
    assert pd.to_datetime(sc.ts,unit='h').dt.year.eq(2026).all()
    meta={'source_rows':pf.metadata.num_rows,'source_columns':pf.schema_arrow.names,
          'loaded_columns':COLS,'positive_events':len(pos),'positive_vessels':len(ids),
          'selected_rows':len(sc),'selected_vessels':int(sc.rfid_id_int.nunique()),
          'cause_field':'발생유형','cause_counts':pos['발생유형'].value_counts().to_dict(),
          'tier01_events':int((pos.tier<=1).sum()),'audit_status_counts':pos.audit_status.value_counts().to_dict(),
          'lin_raw_excluded_len_lt_1_rows':int((sc.len_m<1).sum()),
          'lin_raw_excluded_nonfinite_rows':int((~np.isfinite(sc.len_m) | ~np.isfinite(sc.bbox_m)).sum()),
          'missing_vessels':sorted(ids-set(sc.rfid_id_int.astype(int))),
          'timestamp_min':int(sc.ts.min()),'timestamp_max':int(sc.ts.max()),
          'review_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    return pos,sc,meta

def bearing(lat1,lon1,lat2,lon2):
    p1,p2=np.radians(lat1),np.radians(lat2); dl=np.radians(lon2-lon1)
    return np.arctan2(np.sin(dl)*np.cos(p2),np.cos(p1)*np.sin(p2)-np.sin(p1)*np.cos(p2)*np.cos(dl))

def make_windows(g,half,lo,hi):
    """Compute seven components; original builder anchors the primary design."""
    span=hi-lo+1
    g=g.copy(); g['s_gap']=np.nan
    original=build_vessel(g,span,lo)
    centers=np.arange(half,span-half)
    W={'center':centers,'n_rows':np.zeros(len(centers),int)}
    for m in METRICS: W[m]=np.full(len(centers),np.nan)
    ts=g.ts.to_numpy(dtype=int)-lo; lm=g.len_m.to_numpy(float); bb=g.bbox_m.to_numpy(float)
    lat=g.cen_lat.to_numpy(float); lon=g.cen_lon.to_numpy(float)
    q10=float(np.nanquantile(lm,.1))
    steps=review.haversine_m(lat[:-1],lon[:-1],lat[1:],lon[1:])
    dt=np.diff(ts)
    bearings=bearing(lat[:-1],lon[:-1],lat[1:],lon[1:])
    bearings[(steps<=1e-9) | ~np.isfinite(steps)]=np.nan
    turns=np.abs(np.angle(np.exp(1j*np.diff(bearings))))
    left=np.searchsorted(ts,centers-half,'left'); right=np.searchsorted(ts,centers+half,'right')
    W['n_rows']=right-left
    for j,(a,b) in enumerate(zip(left,right)):
        if b<=a: continue
        lens=lm[a:b]; valid=np.isfinite(lens)
        if valid.any():
            W['speed_mean'][j]=float(np.mean(lens[valid]))
            W['still_frac'][j]=float(np.mean(lens[valid]<q10))
        v=(lens>=1)&np.isfinite(lens)&np.isfinite(bb[a:b])
        if v.any(): W['lin_raw'][j]=float(np.mean(bb[a:b][v]/lens[v]))
        den=np.sum(lens) if valid.all() else np.nan
        if b-a>=2:
            if den>0: W['straight_win'][j]=float(review.haversine_m(lat[a],lon[a],lat[b-1],lon[b-1])/den)
            ss=steps[a:b-1]/dt[a:b-1]
            if np.isfinite(ss).any(): W['step_mean'][j]=float(np.nanmean(ss))
            ang=bearings[a:b-1]; ang=ang[np.isfinite(ang)]
            if len(ang): W['bearing_consistency'][j]=float(abs(np.mean(np.exp(1j*ang))))
        if b-a>=3 and np.isfinite(turns[a:b-2]).any(): W['turn_rate'][j]=float(np.nanmean(turns[a:b-2]))
    if half==3:
        assert np.array_equal(W['center'],original['center'])
        assert np.array_equal(W['n_rows'],original['n_rows'])
        W['center'],W['n_rows']=original['center'],original['n_rows']
    return W,{'rfid_id':int(g.rfid_id_int.iloc[0]),'q10_len_m':q10,'n_rows':len(g),
               'rows_below_q10':int((lm<q10).sum()),'rows_len_lt_1':int((lm<1).sum())}

def design_name(h,match): return f'hod_{"none" if h is None else h}/nrows_{"matched" if match else "unmatched"}'

def collect_events(pos,g,W,half,lo,hi,metrics):
    rows=[]; rid=int(g.rfid_id_int.iloc[0]); events=pos.loc[pos.rfid_id==rid]
    all_acc=events.acc_ts.to_numpy(int)-lo
    for e in events.to_dict('records'):
        ai=int(e['acc_ts'])-lo; found=np.flatnonzero(W['center']==ai)
        ci=int(found[0]) if len(found) else None
        for h,match in DESIGNS:
            base={'acc_id':int(e['acc_id']),'rfid_id':rid,'tier':int(e['tier']),
                  'cause':str(e['발생유형']),'half_width_h':half,'design':design_name(h,match),
                  'hod_tolerance_h':h,'nrows_match':match,'inferential_result':h is not None,
                  'n_acc_rows':int(W['n_rows'][ci]) if ci is not None else 0}
            if ci is None: idx=np.array([],int)
            else:
                ok=ctrl_mask(W,hi-lo+1,all_acc,72,W['n_rows'][ci],exact=match)
                if h is not None:
                    d=np.abs((W['center']+lo)%24-int(e['acc_ts'])%24)
                    ok &= np.minimum(d,24-d)<=h
                idx=np.flatnonzero(ok)
                # Prove actual, not just configured, guard for every returned control.
                assert all(np.all(np.abs(W['center'][idx]-a)>=76) for a in all_acc)
            for m in metrics:
                pool=W[m][idx]; pool=pool[np.isfinite(pool)]
                val=float(W[m][ci]) if ci is not None else np.nan
                reason=('accident_center_outside_complete_window' if ci is None else
                        'accident_metric_undefined' if not np.isfinite(val) else
                        'fewer_than_15_finite_controls' if len(pool)<15 else None)
                rows.append(dict(base,metric=m,acc_value=val if np.isfinite(val) else None,
                                 n_ctrl_candidates=len(idx),n_ctrl_finite=len(pool),exclusion=reason,
                                 ctrl_positive_rate=float(np.mean(pool>0)) if len(pool) else None,
                                 ctrl_mean=float(np.mean(pool)) if len(pool) else None,
                                 percentile=None if reason else pct_rank(val,pool)))
    return rows

def strata_masks(df):
    yield 'ALL',np.ones(len(df),bool)
    yield 'Tier0_1',(df.tier<=1).to_numpy()
    for cause in CAUSES:
        yield cause,(df.cause==cause).to_numpy()
        yield cause+'/Tier0_1',((df.cause==cause)&(df.tier<=1)).to_numpy()

@lru_cache(maxsize=12000)
def exact_mcnemar_p(b,c):
    return float(st.binomtest(b,b+c,.5).pvalue) if b+c else 1.

def mcnemar_all_controls(a,q):
    """Integrate EXACT binomial McNemar over every control pairing; no extraction.
    Event weights sum to one irrespective of its number of eligible controls.
    2*mean(p) is a conservative arithmetic-mean p merger, NOT pooled-pair inference.
    """
    a=np.asarray(a,bool); q=np.asarray(q,float)
    db=np.array([1.]); dc=np.array([1.])
    for aa,qq in zip(a,q):
        if aa: db=np.convolve(db,[qq,1-qq])
        else: dc=np.convolve(dc,[1-qq,qq])
    expected=0.
    for b,pb in enumerate(db):
        for c,pc in enumerate(dc):
            p=exact_mcnemar_p(b,c)
            expected+=pb*pc*p
    n=len(a); diff=a.astype(float)-q
    rng=np.random.default_rng(20261105)
    boots=rng.choice(diff,size=(NBOOT,n),replace=True).mean(1)
    discord=float(np.mean(np.where(a,1-q,q)))
    return {'method':'all_control_pairings_exact_McNemar_conservative_p_merger',
            'mcnemar_pairing_expected_exact_p':float(expected),'p_raw':float(min(1,2*expected)),
            'expected_discordant_acc_only':float(np.sum(np.where(a,1-q,0))),
            'expected_discordant_ctrl_only':float(np.sum(np.where(~a,q,0))),
            'acc_positive_rate':float(np.mean(a)),'ctrl_positive_rate_event_weighted':float(np.mean(q)),
            'delta_positive_rate':float(np.mean(diff)),
            'ci95_positive_rate':np.quantile(boots,[.025,.975]).tolist(),
            'mde80_positive_rate_approx':float((st.norm.ppf(1-ALPHA/2)+st.norm.ppf(.8))*math.sqrt(discord/n)),
            'mde_approximation':'normal approximation using expected discordance; exact McNemar power not guaranteed'}

def summarize(df,alpha=ALPHA,k=7,force_binary=False):
    total=len(df); valid=df.loc[df.exclusion.isna()].copy(); n=len(valid)
    res={'aggregation':'event','n_events_total':total,'n_events':n,
         'excluded_events':total-n,
         'excluded_fewer_than_15_controls':int((df.exclusion=='fewer_than_15_finite_controls').sum()),
         'exclusion_counts':df.exclusion.dropna().value_counts().to_dict(),
         'median_n_controls':float(valid.n_ctrl_finite.median()) if n else None,
         'bonferroni_K':k,'alpha':alpha,'bootstrap_replicates':NBOOT,
         'delta_percentile':None,'wilcoxon_p':None,'sign_p':None,'ci95':None,
         'mde80_percentile_approx':None,'p_raw':None,'p_bonferroni':None}
    if not n: res['method']='not_estimable'; return res
    zfrac=float((valid.acc_value==0).mean()); res['zero_fraction']=zfrac
    if force_binary or zfrac>.5:
        res.update(mcnemar_all_controls(valid.acc_value.to_numpy(float)>0,valid.ctrl_positive_rate.to_numpy(float)))
        res['percentile_prohibited']=True
    else:
        d=valid.percentile.to_numpy(float)-.5
        wp=float(st.wilcoxon(d).pvalue) if np.any(d!=0) else 1.
        nz=d[d!=0]
        sp=float(st.binomtest(int((nz>0).sum()),len(nz),.5).pvalue) if len(nz) else 1.
        boots=np.random.default_rng(20261105).choice(d,size=(NBOOT,n),replace=True).mean(1)
        sd=float(np.std(d,ddof=1)) if n>1 else None
        res.update(method='midrank_percentile_Wilcoxon',delta_percentile=float(np.mean(d)),
                   mean_percentile=float(np.mean(d)+.5),wilcoxon_p=wp,sign_p=sp,p_raw=wp,
                   ci95=np.quantile(boots,[.025,.975]).tolist(),
                   mde80_percentile_approx=float((st.norm.ppf(1-alpha/2)+st.norm.ppf(.8))*sd/math.sqrt(n)) if sd is not None else None,
                   mde_approximation='two-sided normal mean-shift approximation, alpha=0.05/K, power=0.8; not exact Wilcoxon power')
    res['p_bonferroni']=float(min(1,k*res['p_raw']))
    res['significant_usual_single_bonferroni']=res['p_raw']<alpha
    res['significant_literal_corrected_p_vs_alpha']=res['p_bonferroni']<alpha
    return res

def all_results(events,metrics,force_binary=False,alpha=ALPHA,k=7):
    df=pd.DataFrame(events); results=[]
    for (half,design,m),sub in df.groupby(['half_width_h','design','metric'],sort=False):
        for name,mask in strata_masks(sub):
            s=summarize(sub.loc[mask],alpha,k,force_binary)
            s.update(half_width_h=int(half),design=design,metric=m,stratum=name,
                     inferential_result=not design.startswith('hod_none'))
            results.append(s)
    # Do not serialize forbidden percentiles for zero-inflated subgroup tests.
    # Row CSV is primary ALL-scope diagnostic; subgroup suppression lives above.
    prohibited={(r['half_width_h'],r['design'],r['metric']) for r in results
                if r['stratum']=='ALL' and r.get('percentile_prohibited')}
    for e in events:
        if force_binary or (e['half_width_h'],e['design'],e['metric']) in prohibited:
            e['percentile']=None
    return results

def gates(results):
    out=[]
    for m in METRICS:
        for s in ['ALL','Tier0_1']:
            r=next(x for x in results if x['half_width_h']==3 and x['design']==design_name(1,True) and x['metric']==m and x['stratum']==s)
            d=r['delta_percentile']; direction=np.sign(d) if d is not None else 0
            variants=[x for x in results if x['half_width_h']==3 and x['metric']==m and x['stratum']==s]
            nsign=sum(x['delta_percentile'] is not None and np.sign(x['delta_percentile'])==direction and direction!=0 for x in variants)
            ci=r['ci95']; checks={'abs_delta_at_least_005':d is not None and abs(d)>=.05,
                'corrected_p_below_alpha':r['p_bonferroni'] is not None and r['p_bonferroni']<ALPHA,
                'ci95_excludes_zero':ci is not None and (ci[0]>0 or ci[1]<0),
                'sign_consistent_at_least_8_of_10':nsign>=8}
            out.append({'metric':m,'stratum':s,'aggregation':'event','alpha':ALPHA,'sign_consistent_designs':nsign,
                        'checks':checks,'passed':all(checks.values()),'primary':r})
    return out

def report(data):
    meta=data['input']; lines=['# T1 독립 실험 보고','',
      '실제 2026 dev 데이터의 사건 단위 평가이며 모델 학습·장치 실험은 수행하지 않았다.',
      f"입력 집계: 사건 {meta['positive_events']}건, 선박 {meta['positive_vessels']}척, 선택 항적 {meta['selected_rows']}행; lin_raw의 len_m<1 제외 {meta['lin_raw_excluded_len_lt_1_rows']}행. 출처: t1_gate_results.json/input.",
      '발생유형별 실제 사건 수: '+json.dumps(meta['cause_counts'],ensure_ascii=False)+' (동일 JSON/input/cause_counts).',
      '', '고정 관문: |Δ백분위|≥0.05, 보정 p<α=0.00714(정확값 0.05/7), 사건 부트스트랩 2000회 95% CI의 0 제외, 10종 설계 중 8종 이상 동일 부호. 문자 그대로 보정 p를 α와 비교하며 통상 단일 보정보다 엄격하다.',
      '', '|지표|층(사건)|n|Δ백분위|보정 p|95% CI|부호 일치/10|MDE 근사|대조<15 제외|통과|',
      '|---|---|---:|---:|---:|---|---:|---:|---:|---|']
    fmt=lambda v:'NA' if v is None else f'{v:.6g}'
    for gate in data['gates']:
        r=gate['primary']; ci=r['ci95']
        lines.append(f"|{gate['metric']}|{gate['stratum']}|{r['n_events']}|{fmt(r['delta_percentile'])}|{fmt(r['p_bonferroni'])}|{str(ci)}|{gate['sign_consistent_designs']}|{fmt(r['mde80_percentile_approx'] or r.get('mde80_positive_rate_approx'))}|{r['excluded_fewer_than_15_controls']}|{'통과' if gate['passed'] else '미통과'}|")
    lines += ['', '표 출처: t1_gate_results.json/gates[].primary (사건 단위). 영 과다 지표의 Δ백분위/CI는 NA이며 MDE는 양성률 차이 단위다.',
      '각 비유의 층·지표는 표의 MDE보다 작은 평균효과를 이 근사 설계로 안정적으로 검출할 수 없다. MDE는 정확 Wilcoxon 검정력의 보장이 아니며 동일 선박 반복 사건·중첩 대조창 의존성을 포함하지 않는다.',
      '', '## 창폭·사고유형 민감도',
      '전수 결과는 t1_gate_results.json/results에 있다. 다음 표는 시각대 ±1h·행수 매칭에서 사건 유형별 값이며 무통제 결과는 본문에 인용하지 않는다.',
      '|창 반폭(h)|지표|층(사건)|n|Δ백분위|보정 p|MDE 근사|대조<15 제외|','|---:|---|---|---:|---:|---:|---:|---:|']
    for r in data['results']:
        if r['design']==design_name(1,True) and r['stratum'] in ['ALL','Tier0_1']+CAUSES:
            lines.append(f"|{r['half_width_h']}|{r['metric']}|{r['stratum']}|{r['n_events']}|{fmt(r['delta_percentile'])}|{fmt(r['p_bonferroni'])}|{fmt(r['mde80_percentile_approx'] or r.get('mde80_positive_rate_approx'))}|{r['excluded_fewer_than_15_controls']}|")
    lines += ['', '## 이번에 내린 판단과 근거']+['- '+x for x in DECISIONS]
    lines += ['', '## 가설과 실제 해석',
      '초기 가설은 기존 직선도 신호가 더 분명한 시간 간 이동·방위 성분으로 분해될 수 있다는 것이었다. 결과 판정은 고정 관문 표를 따르며, 비유의를 효과 부재의 증거로 바꾸지 않는다.',
      data['declaration'],
      '하나의 유리한 사고유형·창폭 결과를 전체 사건의 결론으로 올리지 않는다. T3 독립 검산은 이 실행자의 범위 밖이며 별도 승인 전 승격은 잠정이다.',
      '실제 프로세스 종료코드는 t1_execution.json에 외부 실행 래퍼가 기록한다.']
    (HERE/'t1_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    pos,sc,meta=load_inputs('t1')
    lo,hi=int(sc.ts.min()),int(sc.ts.max())
    events=[]; profiles=[]
    for rid,g in sc.groupby('rfid_id_int',sort=True):
        memory_gate('t1',f'before_vessel_{int(rid)}_window_transform')
        for half in [3,6,12]:
            W,p=make_windows(g,half,lo,hi)
            events.extend(collect_events(pos,g,W,half,lo,hi,METRICS))
            if half==3: profiles.append(p)
        del W
        if len(profiles)%10==0: print(f'T1 vessels={len(profiles)} events_rows={len(events)}',flush=True)
    memory_gate('t1','before_event_statistical_summary')
    results=all_results(events,METRICS); gate=gates(results)
    passed=[{'metric':x['metric'],'stratum':x['stratum']} for x in gate if x['passed']]
    data={'contract':'R010-GATE','implementation':'independent Codex; T1 then T2; no helper workers',
          'input':meta,'decisions':DECISIONS,'vessel_profiles':profiles,'results':results,'gates':gate,
          'passed_primary_metrics':passed,'expected_result_cells':7*10*12*3,'actual_result_cells':len(results),
          'declaration':('통과 지표 승격 후보: '+json.dumps(passed,ensure_ascii=False)+'; T3 독립 검산 전 잠정.') if passed else '직선도·기구학 경로 최종 기각',
          'limits':['동일 dev 재사용에 의한 탐색 선택','주요 층 2개와 민감도·유형 다중성은 K=7 외부','이진 다중대조 McNemar 확장은 계약의 미정의 짝 구조를 명시적으로 보완','사건 bootstrap의 동일 선박 의존성 미보정']}
    save('t1_gate_results.json',data)
    with (HERE/'t1_event_percentiles.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(events[0]));w.writeheader();w.writerows(events)
    report(data)
    print(data['declaration'],flush=True)

if __name__=='__main__':
    try: main()
    except MemoryDeferred as e:
        print(str(e),flush=True); sys.exit(75)
    except Exception:
        traceback.print_exc(); sys.exit(1)
