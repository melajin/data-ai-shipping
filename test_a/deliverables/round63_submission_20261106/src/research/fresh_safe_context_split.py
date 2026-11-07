"""Keep singleton official classes in context;never drop or duplicate a boat."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
import numpy as np
import tabicl._finetune.data as data
_ORIGINAL_SPLIT=data._split_ctx_query

def safe_context_query_split(y_chunk,*,query_size,seed,stratify):
    y=np.asarray(y_chunk);n=len(y);query_size=max(1,min(query_size,n-1));classes,counts=np.unique(y,return_counts=True)
    if not stratify or (counts.min()>=2 and query_size>=len(classes) and n-query_size>=len(classes)):
        return _ORIGINAL_SPLIT(y,query_size=query_size,seed=seed,stratify=stratify)
    rng=np.random.default_rng(seed)
    reserved=np.asarray([rng.choice(np.flatnonzero(y==c)) for c in classes],dtype=np.int64)
    available=np.setdiff1d(np.arange(n),reserved);qsize=min(query_size,len(available))
    if qsize<1:raise ValueError('No disjoint query possible while retaining every observed class in context')
    query=rng.choice(available,size=qsize,replace=False);context=np.setdiff1d(np.arange(n),query)
    rng.shuffle(context);rng.shuffle(query)
    assert len(context)+len(query)==n and not set(context)&set(query) and set(y[query])<=set(y[context]) and set(y[context])==set(classes)
    return context,query

def build_safe_meta_batch(*args,**kwargs):
    original=data._split_ctx_query;data._split_ctx_query=safe_context_query_split
    try:return data._build_meta_batch(*args,**kwargs)
    finally:data._split_ctx_query=original
