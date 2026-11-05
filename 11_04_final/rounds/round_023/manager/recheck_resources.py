"""One-shot resource recheck after independent work; never poll or launch."""
import datetime, json, os
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1]
guard=json.loads((R/'manager/next_resource_contract.json').read_text(encoding='utf-8'))
memory=psutil.virtual_memory()
ancestors={p.pid for p in psutil.Process().parents()} | {os.getpid()}
other=[]
for p in psutil.process_iter(['pid','name','cmdline','memory_info']):
    try:
        d=p.info
        if d['pid'] not in ancestors and 'python' in (d['name'] or '').lower():
            other.append(dict(pid=d['pid'],cmdline=d['cmdline'],rss=d['memory_info'].rss))
    except (psutil.NoSuchProcess,psutil.AccessDenied): pass
record=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),available_gib=memory.available/2**30,
            required_entry_gib=guard['minimum_entry_available_gib'],expected_peak_gib=guard.get('owned_job_expected_peak_gib',0.5),other_python_jobs=other,
            allowed=memory.available>=guard['minimum_entry_available_gib']*2**30 and not other,
            independent_work_since_deferral=['blocked execution/source audit','portable saved-metric analysis preparation',
                'S2 source/readiness documentation only','user-directed low-memory sequential setup and resource contract update'],
            estimate_basis=guard['basis'],user_processes_terminated=0,training_retries=0)
(R/'manager/resource_recheck_after_independent_work.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
