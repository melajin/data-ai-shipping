"""Predeclared coupled joint/pair deployment;positive body-pair weight mandatory."""
from fresh_rounds import *

def choose_joint_pair(reference,head,pair,y,tu):
    choices=[];outputs={}
    for pg,hg in [(0.,0.)]+list(itertools.product([.25,.5,.75,1.],[0.,.25,.5])):
        j=(1-hg)*reference['joint']+hg*head;p=(1-pg)*reference['pair']+pg*pair
        score=(1-reference['alpha'])*np.log(np.clip(j,1e-6,1))+reference['alpha']*np.log(np.clip(p,1e-6,1)).sum(2)/3+np.log(reference['weights'])
        pred=score.argmax(1);m=metrics(y[tu],pred[tu])
        choices.append({'gamma':pg,'head_gamma':hg,'TUNE_correct':int((pred[tu]==y[tu]).sum()),'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']});outputs[(pg,hg)]=(pred,score,j,p)
    best=max(choices[1:],key=lambda a:(a['TUNE_correct'],a['TUNE_macro'],-a['gamma'],-a['head_gamma']))
    return best,outputs[(best['gamma'],best['head_gamma'])],choices,choices[0]['TUNE_correct']>best['TUNE_correct']

def official_tasks():
    return [None]+list(itertools.combinations(range(4),2))

def task_rows(labels,pair):
    if pair is None:return np.arange(len(labels)),np.asarray(labels,dtype=np.int64)
    a,b=pair;positions=np.flatnonzero(np.isin(labels,[a,b]));return positions,(labels[positions]==b).astype(np.int64)
