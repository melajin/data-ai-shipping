"""TUNE-only finite calibration grid;every positive/zero body uses the same auxiliary."""
from fresh_rounds import *

WEIGHTS=np.asarray([[1.,g,t,d] for g,t,d in itertools.product([.8,1.,1.2,1.4],[1.,1.5,2.,2.5],[.8,1.,1.2])]);LOG_WEIGHTS=np.log(WEIGHTS);NORMS=np.abs(LOG_WEIGHTS).sum(1)


def fast_policy(joint,pair,y):
    contrast=np.log(np.clip(pair,1e-6,1)).sum(2)/3;lj=np.log(np.clip(joint,1e-6,1));best=None
    for alpha in [.25,.5,.75,1.]:
        base=(1-alpha)*lj+alpha*contrast;pred=(base[:,None,:]+LOG_WEIGHTS[None,:,:]).argmax(2);correct=(pred==y[:,None]).sum(0)
        threshold=max(int(correct.max()),-1 if best is None else best[0][0])
        for i in np.flatnonzero(correct>=threshold):
            macro=f1_score(y,pred[:,i],labels=range(4),average='macro',zero_division=0);key=(int(correct[i]),macro,-float(NORMS[i]),-abs(alpha-.5))
            if best is None or key>best[0]:best=(key,alpha,WEIGHTS[i])
    return best[1],best[2],best[0]


def body_components(compact,compact_pair,relation_pair,beta):
    return compact.astype(np.float64),(1-beta)*compact_pair+beta*relation_pair


def materialize(reference,components,cat,choice):
    bj,bp=body_components(*components,choice['body_relation_beta']);g=choice['gamma'];rho=choice['cat_joint_fraction']
    j=(1-g)*reference['joint'].astype(np.float64)+g*bj;p=(1-g)*reference['pair']+g*bp;j=(1-rho)*j+rho*cat
    score=(1-choice['alpha'])*np.log(np.clip(j,1e-6,1))+choice['alpha']*np.log(np.clip(p,1e-6,1)).sum(2)/3+np.log(choice['weights'])
    return score.argmax(1),score,j,p,bj,bp


def choice_key(c):
    return c['TUNE_correct'],c['TUNE_macro'],-c['gamma'],-c['cat_joint_fraction'],-c['body_relation_beta']


def choose_calibrated(reference,components,cat,y_tune,tu):
    choices=[];rj=reference['joint'][tu].astype(np.float64);rp=reference['pair'][tu];cj,cp,rr=[a[tu] for a in components];ct=cat[tu]
    for g in [0.,.25,.5,.75,1.]:
        for beta in ([0.] if g==0 else [0.,.25,.5,.75,1.]):
            bj,bp=body_components(cj,cp,rr,beta);j=(1-g)*rj+g*bj;p=(1-g)*rp+g*bp
            for rho in [0.,.25,.5]:
                mixed=(1-rho)*j+rho*ct;alpha,w,key=fast_policy(mixed,p,y_tune)
                choices.append({'gamma':g,'body_relation_beta':beta,'cat_joint_fraction':rho,'alpha':alpha,'weights':w.tolist(),'TUNE_correct':key[0],'TUNE_micro':key[0]/len(y_tune),'TUNE_macro':key[1]})
    best=max([c for c in choices if c['gamma']>0],key=choice_key);zero=max([c for c in choices if c['gamma']==0],key=choice_key)
    return best,materialize(reference,components,cat,best),choices,zero
