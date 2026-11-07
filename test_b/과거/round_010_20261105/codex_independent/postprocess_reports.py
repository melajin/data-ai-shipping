"""Repair zero-variance MDE planning values, preserving all test statistics."""
import ctypes,json,sys,math,ast,types
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent
class Mem(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('available',ctypes.c_ulonglong),('tp',ctypes.c_ulonglong),('ap',ctypes.c_ulonglong),('tv',ctypes.c_ulonglong),('av',ctypes.c_ulonglong),('ext',ctypes.c_ulonglong)]
m=Mem();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
rec={'checked_at':datetime.now().astimezone().isoformat(),'available_mib':m.available/2**20,
 'stage':'small JSON report editing; no experiment data loading','estimated_maximum_increment_mib':64,'reserve_mib':0,
 'estimate_basis':'standard library only; summary JSONs; exact small binomial sums; no scientific imports, parquet or bootstrap',
 'concurrent_work':'no own experiment running',
 'gate_scope':'low-memory report editing allowed while large-memory jobs remain deferred; does not relax T1/T2 512MiB+1GiB experiment gates',
 'allowed':m.available/2**20>=64}
(P/'postprocess_memory.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
if not rec['allowed']:print('postprocess deferred');sys.exit(75)
def zero_mde(n,alpha):
    critical=next((k for k in range(1,n+1) if 2*min(1,2**(1-k))<alpha),None)
    if critical is None:return None
    low,high=0.,1.
    for _ in range(45):
        q=(low+high)/2
        power=sum(math.comb(n,j)*q**j*(1-q)**(n-j) for j in range(critical,n+1))
        if power<.8:low=q
        else:high=q
    return high
def save(name,data):(P/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def render_report(prefix,data):
    filename='t1_decompose.py' if prefix=='t1' else 't2_state_audit.py'
    name='report' if prefix=='t1' else 'make_report'
    tree=ast.parse((P/filename).read_text(encoding='utf-8'))
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name)
    design=lambda h,match:f'hod_{"none" if h is None else h}/nrows_{"matched" if match else "unmatched"}'
    env={'json':json,'HERE':P,'DECISIONS':data['decisions'],'design_name':design,
      'CAUSES':['기관손상','부유물감김','침수','화재','운항저해'],
      't':types.SimpleNamespace(HERE=P,design_name=design)}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),filename,'exec'),env)
    env[name](data)
changes=[]
for prefix,file in [('t1','t1_gate_results.json'),('t2','t2_state_distribution.json')]:
    data=json.loads((P/file).read_text(encoding='utf-8'))
    for r in data['results']:
        if r.get('mde80_positive_rate_approx')==0:
            value=zero_mde(r['n_events'],r['alpha'])
            r['mde80_positive_rate_approx']=value
            r['mde_status']='best_case_exact_binomial_80pct_power_all_discordances_same_direction' if value is not None else 'unattainable_even_at_rate_difference_1_for_this_n_and_alpha'
            r['mde_approximation']='observed discordance=0; exact best-case binomial 80% power planning with all future discordances same direction; includes conservative p-merger; not general exact McNemar power'
            changes.append({'task':prefix,'metric':r['metric'],'half_width_h':r['half_width_h'],'design':r['design'],'stratum':r['stratum'],'n':r['n_events'],'previous_mde':0,'new_mde':value,'status':r['mde_status']})
    save(file,data)
    render_report(prefix,data)
note='\nMDE 보완: 관측 불일치가 0인 작은 층에서 MDE=0이라는 초기 정규근사 결론을 폐기했다. 가능한 모든 미래 불일치가 한 방향이라는 최선 조건에서도 목표 검정력에 필요한 이진 차이를 계산했으며, 해당 사건 수에서 차이가 1이어도 유의해질 수 없으면 MDE는 NA이고 mde_status에 검출 불가를 명시했다. 변경 내역은 mde_corrections.json에 있고 p값·효과·CI·승격 판정은 바꾸지 않았다.\n'
for name in ['t1_report.md','t2_report.md']:
    with (P/name).open('a',encoding='utf-8') as f:f.write(note)
save('mde_corrections.json',{'changes':changes,'n_corrected_cells':len(changes),'test_statistics_unchanged':True})
print('MDE corrected cells='+str(len(changes)))
