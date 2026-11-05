"""Fold-local T5 from vetted label-free current-period fishing-cell profiles.

Never imports the legacy producer: it loads 2025 while building shared harbors.
Existing T5 aggregate CSV is not sufficient to reconstruct fold-local counts.
This boundary fails closed until an exact, provenance-reviewed geometry cache
exists. The numerical engine is independent of labels outside the training set.
"""
from pathlib import Path
from collections import defaultdict
import hashlib,json
import numpy as np

R=Path(__file__).resolve().parents[1]
FIELDS=('row_idx','month','fine_x','fine_y','coarse_x','coarse_y','record_count')

def roster_hash(ids):
    return hashlib.sha256('\n'.join(map(str,ids)).encode('utf8')).hexdigest()

def make_rebuilder(n_rows, records):
    """records columns: row,month,fine_x,fine_y,coarse_x,coarse_y,count."""
    profiles=[[] for _ in range(n_rows)]
    seen=set()
    for item in records:
        row,month,fx,fy,cx,cy,count=map(int,item)
        if not(0<=row<n_rows and 1<=month<=6 and count>0):raise ValueError('Invalid T5 profile row')
        key=(row,month,fx,fy,cx,cy)
        if key in seen:raise ValueError('Duplicate T5 profile key')
        seen.add(key);profiles[row].append((month,(fx,fy),(cx,cy),count))

    def rebuild(train_indices, train_labels):
        ti=np.asarray(train_indices,dtype=int);ty=np.asarray(train_labels,dtype=int)
        if len(ti)!=len(ty) or len(set(ti.tolist()))!=len(ti):raise ValueError('Bad T5 training partition')
        if np.any((ti<0)|(ti>=n_rows)) or np.any((ty<0)|(ty>3)):raise ValueError('Bad T5 training labels')
        labels=dict(zip(ti.tolist(),ty.tolist()))
        states={m:dict(fine=defaultdict(lambda:np.zeros(4,dtype=np.int64)),coarse=defaultdict(lambda:np.zeros(4,dtype=np.int64)),global_counts=np.zeros(4,dtype=np.int64),members=set()) for m in range(7)}
        memberships={}
        for row,label in labels.items():
            for month in range(7):
                rr=[x for x in profiles[row] if month==0 or x[0]==month]
                if not rr:continue
                fine={x[1] for x in rr};coarse={x[2] for x in rr}
                memberships[(row,month)]=(fine,coarse)
                state=states[month];state['global_counts'][label]+=1;state['members'].add(row)
                for cell in fine:state['fine'][cell][label]+=1
                for cell in coarse:state['coarse'][cell][label]+=1
        def query(row,month,fine,coarse):
            st=states[month];own=row in st['members'];label=labels.get(row)
            glob=st['global_counts'].copy()
            if own:glob[label]-=1
            total=int(glob.sum());prior=glob/total if total else np.full(4,.25)
            owncells=memberships.get((row,month),(set(),set()))
            fine_ok=False
            for tier,cell,selfcells in [('fine',fine,owncells[0]),('coarse',coarse,owncells[1])]:
                counts=st[tier].get(cell)
                if counts is None:continue
                adj=counts.copy()
                if own and cell in selfcells:adj[label]-=1
                if np.any(adj<0):raise AssertionError('T5 negative leave-self-out count')
                n=int(adj.sum())
                if tier=='fine':fine_ok=n>=3
                if n>=3:return (adj+2.0*prior)/(n+2.0),fine_ok
            return prior,fine_ok
        result=np.full((n_rows,10),np.nan,dtype=np.float64)
        for row,rr in enumerate(profiles):
            total=sum(x[3] for x in rr)
            if not total:continue
            main=np.zeros(4);monthly=np.zeros(4);fine_total=0
            for month,fine,coarse,count in rr:
                vec,ok=query(row,0,fine,coarse);vm,_=query(row,month,fine,coarse)
                main+=count*vec;monthly+=count*vm;fine_total+=count*ok
            result[row,:4]=main/total;result[row,4:8]=monthly/total
            result[row,8]=fine_total/total;result[row,9]=np.log1p(total)
        return result
    return rebuild

def prepare_t5(ids):
    data=R/'artifacts/t5_fishing_profiles.npz';manifest=data.with_suffix('.manifest.json')
    if not data.exists() or not manifest.exists():
        raise RuntimeError('T5 prerequisite missing: vetted exact current2026 fishing-cell profile cache. Legacy producer would read2025; cached aggregate T5 cannot substitute.')
    meta=json.loads(manifest.read_text(encoding='utf8-sig'))
    required={'roster_sha256':roster_hash(ids),'year':2026,'fishing_row_count_equivalence_verified':True,'pointwise_mask_equivalence_verified':False,'test2025_query_rows_materialized':0,'test2025_labels_read':False,'test2025_individual_outputs_retained':False,'labels_used':False}
    if any(meta.get(k)!=v for k,v in required.items()):raise ValueError('T5 profile provenance contract failed')
    with data.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=meta.get('sha256'):raise ValueError('T5 profile hash mismatch')
    with np.load(data,allow_pickle=False) as z:
        if set(z.files)!=set(FIELDS):raise ValueError('Unexpected T5 profile columns')
        arrays=[z[k] for k in FIELDS]
        if len({len(x) for x in arrays})!=1:raise ValueError('T5 profile column length mismatch')
        records=zip(*arrays)
        return make_rebuilder(len(ids),records)
