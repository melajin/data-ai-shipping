from __future__ import annotations
import ast, hashlib, json, math, platform, sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import psutil
import numpy as np
import pandas as pd

AUDIT=Path(__file__).resolve().parent
RUN008=Path(r'D:\repos\fishing-track-classification\code\tools\run_008_testB_20261101.py')
REMEASURE=Path(r'D:\repos\fishing-track-classification\code\tools\run_remeasure_20261031.py')
EXPECTED_RUN008='cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8'
EXPECTED_REMEASURE='5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def env():
    v=psutil.virtual_memory()
    return {'local_time':datetime.now().astimezone().isoformat(),'available_mib':round(v.available/2**20,1),'total_mib':round(v.total/2**20,1),'python':sys.version,'platform':platform.platform()}
def nodes_for(source, wanted):
    tree=ast.parse(source)
    nodes=[]
    for n in tree.body:
        if isinstance(n,ast.Assign):
            names={t.id for t in n.targets if isinstance(t,ast.Name)}
            if names & wanted: nodes.append(n)
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in wanted:
            nodes.append(n)
    return nodes

def main():
    ram=env()
    if ram['available_mib']<1024: raise RuntimeError('synthetic fixture RAM gate below 1024MiB')
    if sha(RUN008)!=EXPECTED_RUN008 or sha(REMEASURE)!=EXPECTED_REMEASURE: raise RuntimeError('fixed original-source hash mismatch')
    src=RUN008.read_text(encoding='utf-8-sig'); rm_src=REMEASURE.read_text(encoding='utf-8-sig')
    names={'GRID_HARBOR','GRID_FINE','GRID_COARSE','T5_MIN_VESSELS','MIN_HIST_FOR_CHANGE','STOP_LEN_M','STOP_BBOX_M','HARBOR_NEAR_M','MOORING_NEAR_M','SEA_STOP_FAR_M','MOVE_LEN_M','MOVE_STRAIGHT','NIGHT_HOURS','score_vessel','lookup_density','robust_z','squash'}
    rm_names={'EARTH_R','haversine_m'}
    rm_nodes=nodes_for(rm_src,rm_names)
    rm_ns={'math':math,'np':np}
    exec(compile(ast.Module(body=rm_nodes,type_ignores=[]),str(REMEASURE),'exec'),rm_ns)
    # Deliberately use a plain instance attribute: no method binding is introduced.
    remeasure=SimpleNamespace(**rm_ns)
    assert not __import__('inspect').ismethod(remeasure.haversine_m)
    ns={'np':np,'pd':pd,'math':math,'remeasure':remeasure}
    exec(compile(ast.Module(body=nodes_for(src,names),type_ignores=[]),str(RUN008),'exec'),ns)
    calls=[]; hav_orig=remeasure.haversine_m
    def traced(*args):
        calls.append(args); return hav_orig(*args)
    remeasure.haversine_m=traced
    n=26; rows=[]
    for i in range(n):
        # Row 0 is an observed night stop, which seeds own mooring state; the remaining
        # points occupy distinct fine cells and exercise accumulated-visited haversines.
        lon=127.0+0.012*i; lat=36.0+0.003*((i%3)-1)
        stop=(i==0)
        rows.append({'rfid_id':'SYNTHETIC_ONLY','part_dt':'20250101','rfid_time':22 if stop else (23 if i==1 else (i%24)),
          'wkt_valid':True,'cen_lon':lon,'cen_lat':lat,'len_m':20.0 if stop else (4000.0 if i%2 else 3600.0),
          'bbox_m':20.0 if stop else (2600.0 if i%2 else 3200.0),'ts':float(i),'source_ordinal':i})
    frame=pd.DataFrame(rows)
    # Independent scalar reference: fixture normalizers are linear and fixed, no learned reference.
    ng=lambda x: float(x)/100.0
    nj=lambda x: float(x)/10000.0
    out=ns['score_vessel'](frame,lambda lon,lat:np.full(len(lon),10000.0),None,{}, {},ng,nj)
    if len(calls)<26: raise AssertionError(f'haversine path not exercised enough: {len(calls)}')
    if not np.all(np.isnan(out['s_change'].to_numpy()[:24])): raise AssertionError('s_change became defined before 24 historical rows')
    if not np.isfinite(out['s_change'].to_numpy()[24:]).all(): raise AssertionError('s_change missing after 24 history rows')
    if out['state'].iloc[0]!='해상정지' or out['state'].iloc[1]!='이동': raise AssertionError(f'unexpected synthetic state transitions: {out.state.iloc[:3].tolist()}')
    # Independent scalar for row 24: history rows 0..23, robust-IQR lengths and straightness,
    # prior state surprise, min distance to visited 0.01-degree cell centers, and gap/jump.
    def scalar_robust_z(x,hist):
        med=float(np.median(hist)); iqr=float(np.percentile(hist,75)-np.percentile(hist,25))
        scale=iqr/1.349 if iqr>0 else (float(np.std(hist)) if float(np.std(hist))>0 else 1.0)
        return abs(float(x)-med)/scale if scale>0 else 0.0
    def scalar_squash(z): return 1.0-math.exp(-abs(z)/2.0)
    hlen=[float(x) for x in frame['len_m'].to_list()[:24]]
    hstraight=[float(b/a) if a>0 else math.nan for a,b in zip(frame['len_m'].to_list()[:24],frame['bbox_m'].to_list()[:24])]
    state24=out['state'].iloc[24]
    prior_states=out['state'].to_list()[:24]
    z1=scalar_robust_z(float(frame['len_m'].iloc[24]),hlen)
    z2=scalar_robust_z(float(frame['bbox_m'].iloc[24]/frame['len_m'].iloc[24]),hstraight)
    surprise=1.0-sum(x==state24 for x in prior_states)/24.0
    expected_change=(scalar_squash(z1)+scalar_squash(z2)+surprise)/3.0
    visited=set()
    for i in range(24): visited.add((math.floor(float(frame['cen_lon'].iloc[i])/.01),math.floor(float(frame['cen_lat'].iloc[i])/.01)))
    lon24=float(frame['cen_lon'].iloc[24]); lat24=float(frame['cen_lat'].iloc[24])
    dist_km=min(hav_orig(lon24,lat24,(cx+.5)*.01,(cy+.5)*.01) for cx,cy in visited)/1000.0
    expected_zone=.5*min(dist_km/20.0,1.0)+.5
    jump=hav_orig(float(frame['cen_lon'].iloc[23]),float(frame['cen_lat'].iloc[23]),lon24,lat24)
    expected_gap=.5*1.0/100.0+.5*jump/10000.0
    expected_score=float(np.clip(np.mean([expected_zone,expected_change,expected_gap]),1e-6,1.0))
    for key,expected in [('s_zone',expected_zone),('s_change',expected_change),('s_gap',expected_gap),('score',expected_score)]:
        actual=float(out[key].iloc[24])
        if not math.isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-11): raise AssertionError(f'{key} scalar mismatch actual={actual}, expected={expected}')
    floor_frame=pd.DataFrame([{'rfid_id':'SYNTHETIC_FLOOR','part_dt':'20250101','rfid_time':10,'wkt_valid':True,'cen_lon':127.001,'cen_lat':36.001,'len_m':1000.0,'bbox_m':500.0,'ts':0.0,'source_ordinal':0}])
    floor_cell=(math.floor(127.001/.01),math.floor(36.001/.01))
    floor_out=ns['score_vessel'](floor_frame,lambda lon,lat:np.full(len(lon),10000.0),None,{floor_cell:3},{},ng,nj)
    floor_score=float(floor_out.score.iloc[0])
    if floor_score!=1e-6: raise AssertionError(f'floor fixture did not preserve 1e-6: {floor_score}')
    return {'status':'pass','ram':ram,'source_sha256':{'run008':sha(RUN008),'remeasure':sha(REMEASURE)},'fixture_rows':n,'haversine_calls':len(calls),'simple_namespace_haversine_is_bound_method':False,'state_first_rows':out.state.iloc[:3].tolist(),'s_change_first_defined_row':24,'s_change_row24':float(out.s_change.iloc[24]),'independent_scalar_row24':{'s_zone':expected_zone,'s_change':expected_change,'s_gap':expected_gap,'score':expected_score},'production_ast_row24':{k:float(out[k].iloc[24]) for k in ['s_zone','s_change','s_gap','score']},'floor_fixture_score':floor_score,'floor_fixture_preserved':floor_score==1e-6,'actual_data_or_reference_loaded':False}

if __name__=='__main__':
    started=datetime.now().astimezone().isoformat()
    try:
        r=main(); r['started_local']=started
        (AUDIT/'independent_scorer_fixture.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps({'status':r['status'],'fixture_rows':r['fixture_rows'],'haversine_calls':r['haversine_calls'],'scalar_check':'passed'},ensure_ascii=False))
    except Exception as e:
        d={'status':'fail','error_type':type(e).__name__,'error':str(e),'started_local':started}
        (AUDIT/'independent_scorer_fixture.json').write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(d,ensure_ascii=False),file=sys.stderr); sys.exit(1)
