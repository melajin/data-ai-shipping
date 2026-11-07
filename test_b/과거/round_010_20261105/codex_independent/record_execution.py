"""Preserve real process exit receipts, flattening PowerShell array wrappers."""
import sys,json
from pathlib import Path
P=Path(__file__).resolve().parent
def flatten(x):
    if isinstance(x,list):return [y for e in x for y in flatten(e)]
    if isinstance(x,dict):
        if 'exit_code' in x:return [x]
        if 'value' in x:return flatten(x['value'])
    raise ValueError('unrecognized receipt structure')
def normalize(name):
    path=P/(name+'_execution.json')
    if not path.exists():return []
    original=path.read_text(encoding='utf-8-sig');data=json.loads(original);flat=flatten(data)
    if data!=flat:
        (P/(name+'_execution_raw_nested.json')).write_text(original,encoding='utf-8')
        path.write_text(json.dumps(flat,ensure_ascii=False,indent=2),encoding='utf-8')
    return flat
if __name__=='__main__':
    if len(sys.argv)==1:
        for name in ['t1','t2']:normalize(name)
    else:
        _,name,script,start,end,code,log=sys.argv
        data=normalize(name);data.append({'script':script,'started_at':start,'ended_at':end,'exit_code':int(code),'log_path':log})
        (P/(name+'_execution.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
