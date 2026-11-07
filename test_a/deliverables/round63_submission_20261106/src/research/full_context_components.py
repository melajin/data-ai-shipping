"""Finite TUNE calibration for a trained body with no auxiliary classifier."""
from fresh_calibrated_components import fast_policy,body_components,materialize,choice_key
from fresh_rounds import *

def choose_full_context(reference,components,y_tune,tu):
    choices=[];rj=reference['joint'][tu].astype(np.float64);rp=reference['pair'][tu];cj,cp,rr=[a[tu] for a in components]
    for gamma in [0.,.25,.5,.75,1.]:
        for beta in ([0.] if gamma==0 else [0.,.25,.5,.75,1.]):
            bj,bp=body_components(cj,cp,rr,beta);j=(1-gamma)*rj+gamma*bj;p=(1-gamma)*rp+gamma*bp;alpha,w,key=fast_policy(j,p,y_tune)
            choices.append({'gamma':gamma,'body_relation_beta':beta,'cat_joint_fraction':0.,'alpha':alpha,'weights':w.tolist(),'TUNE_correct':key[0],'TUNE_micro':key[0]/len(y_tune),'TUNE_macro':key[1]})
    best=max([c for c in choices if c['gamma']>0],key=choice_key);zero=choices[0]
    assert len(choices)==21
    return best,materialize(reference,components,np.zeros_like(reference['joint']),best),choices,zero
