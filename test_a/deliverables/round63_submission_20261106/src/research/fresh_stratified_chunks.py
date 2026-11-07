"""FIT-label-stratified episode chunks;every task boat occurs exactly once."""
from fresh_rounds import *
from sklearn.model_selection import StratifiedKFold

def stratified_chunks(labels,max_chunk_size,rng,min_chunk_size=50):
    labels=np.asarray(labels);n=len(labels)
    if n<=max_chunk_size:return [rng.permutation(n)]
    count=int(np.ceil(n/max_chunk_size));classes,support=np.unique(labels,return_counts=True)
    assert len(classes)>=2 and support.min()>=count,'Not enough actual class members for all task chunks'
    splitter=StratifiedKFold(n_splits=count,shuffle=True,random_state=int(rng.integers(0,2**31-1)))
    chunks=[ix for _,ix in splitter.split(np.zeros((n,1)),labels)]
    assert sorted(np.concatenate(chunks).tolist())==list(range(n)) and all(len(ix)<=max_chunk_size and len(np.unique(labels[ix]))==len(classes) for ix in chunks)
    return chunks
