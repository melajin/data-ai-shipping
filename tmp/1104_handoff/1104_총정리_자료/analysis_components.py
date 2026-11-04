"""Post-hoc analysis of saved predictions only; no fitting or policy changes."""
from pathlib import Path
import sys,json,hashlib
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
RUN=ROOT/'TabICLv2_투트랙_6_10차_20261104'
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(RUN/'code'))
from validation import evaluate_predictions,classification_metrics
from confidence_decoder10 import combine


def load(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k] for k in z.files}


def main():
    ref=load(RUN/'inputs/ref.npz');q=load(RUN/'inputs/outer.npz')
    y=q['y'];ids=q['ids'];known=np.isin(ids,ref['ids'])
    components={}
    probs={name:np.load(RUN/f'shared/{path}/outer.npy') for name,path in
           [('TabICL_global','global'),('TabICL_local','local8'),('TabICL_blend','blend8')]}
    result=json.loads((RUN/'10차 시도/result.json').read_text(encoding='utf-8'))
    rr=load(RUN/'shared/retrieval10/learned/outer.npz')
    assert np.array_equal(rr['query_ids'],ids)
    top=ref['y'][rr['candidate_indices'][:,0]]
    onehot=np.eye(4)[top]
    probs['retrieval_top1']=onehot
    cfg=result['selection']
    nobias,weight=combine(probs['TabICL_blend'],onehot,rr['gate_features'],cfg['style'],cfg['alpha'],[1,1,1,1])
    probs['final10_before_class_bias']=nobias
    probs['final10']=np.load(RUN/'10차 시도/outer.npy')
    for name in ('TabICL_global','TabICL_local'):
        counterfactual,_=combine(probs[name],onehot,rr['gate_features'],cfg['style'],cfg['alpha'],cfg['bias'])
        probs['posthoc_same_policy_'+name]=counterfactual
    np.testing.assert_allclose(weight,np.load(RUN/'10차 시도/outer_retrieval_weight.npy'))
    recheck,_=combine(probs['TabICL_blend'],onehot,rr['gate_features'],cfg['style'],cfg['alpha'],cfg['bias'])
    np.testing.assert_allclose(recheck,probs['final10'],atol=1e-12)
    for name,p in probs.items():
        components[name]=evaluate_predictions(ids,y,p.argmax(1),ref_ids=ref['ids'],observed_days=q['observed_days'])
    base=probs['TabICL_blend'].argmax(1);final=probs['final10'].argmax(1)
    changes={}
    for name,m in [('all',np.ones(len(y),bool)),('known',known),('novel',~known)]:
        changes[name]={'n':int(m.sum()),'final_correct':int(((final==y)&m).sum()),
          'both_correct':int(((base==y)&(top==y)&m).sum()),'both_wrong':int(((base!=y)&(top!=y)&m).sum()),
          'model_only_correct':int(((base==y)&(top!=y)&m).sum()),'retrieval_only_correct':int(((base!=y)&(top==y)&m).sum()),
          'fusion_corrected_model_errors':int(((base!=y)&(final==y)&m).sum()),
          'fusion_damaged_model_correct':int(((base==y)&(final!=y)&m).sum()),
          'fusion_corrected_retrieval_errors':int(((top!=y)&(final==y)&m).sum()),
          'fusion_damaged_retrieval_correct':int(((top==y)&(final!=y)&m).sum()),
          'retrieval_weight_quantiles':np.quantile(weight[m],[0,.1,.25,.5,.75,.9,1]).tolist(),
          'retrieval_weight_mean':float(weight[m].mean())}
    pre=nobias.argmax(1)
    calibration={'changed':int((pre!=final).sum()),'corrected':int(((pre!=y)&(final==y)).sum()),
                 'damaged':int(((pre==y)&(final!=y)).sum()),
                 'changed_pairs':np.bincount(4*pre[pre!=final]+final[pre!=final],minlength=16).reshape(4,4).tolist()}
    confidence={}
    p=probs['final10'];confidence_value=p.max(1)
    for name,m in [('all',np.ones(len(y),bool)),('known',known),('novel',~known)]:
        records=[]
        for lo,hi in ((0.,.5),(.5,.7),(.7,.9),(.9,1.000001)):
            mask=m&(confidence_value>=lo)&(confidence_value<hi)
            records.append({'min':lo,'max':min(hi,1.),'n':int(mask.sum()),'accuracy':float((final[mask]==y[mask]).mean()) if mask.any() else None,
                            'mean_score':float(confidence_value[mask].mean()) if mask.any() else None})
        confidence[name]=records
    metrics=components['final10']['groups']
    mixture=[]
    for novel_fraction in (0.,.1,.25,.5,.75,1.):
        score=(1-novel_fraction)*metrics['known_by_ref_id']['micro_f1']+novel_fraction*metrics['novel_by_ref_id']['micro_f1']
        mixture.append({'novel_fraction':novel_fraction,'micro':score})
    out={'scope':'post-hoc diagnostics from saved predictions; no model fitted, no production policy changed; component substitutions were not selected on INNER and are not additional official attempts',
         'component_only':components,'fusion_changes':changes,'class_bias_diagnostic':calibration,
         'confidence_bins':confidence,'composition_sensitivity':mixture,
         'sensitivity_limit':'Arithmetic scenario holding each observed group accuracy constant; not a forecast for new populations.'}
    (OUT/'component_analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    for k,v in components.items():print(k,v['micro_f1'],v['class_f1'],v['groups']['novel_by_ref_id']['micro_f1'])
    print(json.dumps({'changes':changes,'bias':calibration},ensure_ascii=False))


if __name__=='__main__':main()
