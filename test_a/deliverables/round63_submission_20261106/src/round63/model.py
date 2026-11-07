"""Fixed Round63 body and14-task deployment;no optimizer or research state."""
import gc
import itertools
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from tabicl import TabICLClassifier
from tabicl._model.tabicl import TabICL
from tabicl._model.layers import MultiheadAttentionBlock
from tabicl._model.inference import InferenceManager


class GatedFFNBlock(MultiheadAttentionBlock):
    """Round63's unchanged full-width gate inside the last4 FFN blocks."""
    def _ff_block(self,x):
        value=self.activation(self.linear1(x))
        gate=2*torch.sigmoid(self.ffn_gate(x))
        return self.dropout2(self.linear2(self.dropout(value*gate)))


class FixedInferenceManager(InferenceManager):
    def configure(self,**kwargs):
        kwargs['min_batch_size']=self.fixed_batch_size
        return super().configure(**kwargs)

    def estimate_safe_batch_size(self,*args,**kwargs):
        memory,_=super().estimate_safe_batch_size(*args,**kwargs)
        return memory,self.fixed_batch_size


def configure_inference(model):
    for name,size in [('col_embedder',64),('row_interactor',64),('icl_predictor',1)]:
        manager=getattr(model,name).inference_mgr
        manager.__class__=FixedInferenceManager;manager.fixed_batch_size=size
    return model


def load_body(path,device='cuda',gated=True):
    saved=torch.load(path,map_location='cpu',weights_only=False)
    model=TabICL(**saved['config'])
    if gated:
        blocks=model.icl_predictor.tf_icl.blocks
        if len(blocks)!=12:raise ValueError('Expected12 ICL blocks in the selected checkpoint')
        for block in blocks[8:]:
            block.__class__=GatedFFNBlock
            block.ffn_gate=nn.Linear(block.linear1.in_features,block.linear1.out_features)
    model.load_state_dict(saved['state_dict'],strict=True)
    model.to(device).eval();configure_inference(model)
    for parameter in model.parameters():parameter.requires_grad_(False)
    return model,saved['config']


class BodyClassifier(TabICLClassifier):
    """Bind native task preprocessing to an explicitly loaded fixed body.

    The saved artifact is a state-dictionary checkpoint plus context and schema.
    This class is never serialized as a Python estimator.
    """
    def _load_model(self):
        self.model_=self.bound_body
        self.model_config_=self.bound_config
        self.model_path_=self.bound_checkpoint


def make_task_estimator(body,config,checkpoint,seed,device):
    estimator=BodyClassifier(n_estimators=4,batch_size=1,model_path=checkpoint,
        allow_auto_download=False,device=device,use_amp=True,use_fa3=False,
        kv_cache='repr',n_jobs=4,random_state=int(seed))
    estimator.bound_body=body;estimator.bound_config=config
    estimator.bound_checkpoint=Path(checkpoint)
    return estimator


def combine_outputs(outputs,policy):
    n=len(outputs['compact_head']);pair={arm:np.ones((n,4,4)) for arm in ['compact','state']}
    for arm in pair:
        for a,b in itertools.combinations(range(4),2):
            probability=outputs[f'{arm}_pair_{a}_{b}']
            pair[arm][:,a,b]=probability[:,0];pair[arm][:,b,a]=1-probability[:,0]
    beta=policy['state_beta']
    joint=(1-beta)*outputs['compact_head']+beta*outputs['state_head']
    paired=(1-beta)*pair['compact']+beta*pair['state']
    score=(1-policy['alpha'])*np.log(np.clip(joint,1e-6,1))
    score+=policy['alpha']*np.log(np.clip(paired,1e-6,1)).sum(axis=2)/3
    score+=np.log(np.asarray(policy['weights']))
    exponential=np.exp(score-score.max(axis=1,keepdims=True))
    probability=exponential/exponential.sum(axis=1,keepdims=True)
    return score,probability


class Round63Predictor:
    def __init__(self,root,device='cuda'):
        self.root=Path(root);self.device=device
        self.schema=json.loads((self.root/'model/feature_schema.json').read_text(encoding='utf-8'))
        self.policy=json.loads((self.root/'model/policy.json').read_text(encoding='utf-8'))
        if self.policy['relation_beta']!=0 or self.policy['body_gamma']!=1:
            raise ValueError('This deployment supports the selected Round63 policy:eta0,gamma1')
        context=np.load(self.root/'data/reference/context.npz')
        self.context=np.asfortranarray(context['X'],dtype=np.float32)
        self.labels=context['y'];self.context_ids=context['ids']
        self.checkpoint=self.root/'model/round63.ckpt'
        self.body,self.config=load_body(self.checkpoint,device)

    def predict(self,features,output_dir=None):
        if hasattr(features,'columns'):
            if list(features.columns)!=self.schema['columns']:raise ValueError('Feature names/order differ from the model schema')
            features=features.to_numpy(dtype=np.float32)
        query=np.asfortranarray(features,dtype=np.float32)
        if query.ndim!=2 or query.shape[1]!=337:raise ValueError('Expected337 feature columns')
        query=np.where(np.isfinite(query),query,np.nan)
        outputs={};audit=[]
        for arm,size in [('compact',150),('state',337)]:
            specs=[('head',None)]+[(f'pair_{a}_{b}',(a,b)) for a,b in itertools.combinations(range(4),2)]
            for task,pair in specs:
                started=time.perf_counter()
                mask=np.ones(len(self.labels),dtype=bool) if pair is None else np.isin(self.labels,pair)
                seed=20262015 if pair is None else 20262205+10*pair[0]+pair[1]
                estimator=make_task_estimator(self.body,self.config,self.checkpoint,seed,self.device)
                x=np.asfortranarray(self.context[mask,:size]);q=np.asfortranarray(query[:,:size])
                estimator.fit(np.where(np.isfinite(x),x,np.nan),self.labels[mask])
                probability=np.concatenate([estimator.predict_proba(q[start:start+1000]) for start in range(0,len(q),1000)])
                expected=list(range(4)) if pair is None else list(pair)
                if estimator.classes_.tolist()!=expected:raise ValueError('Native class order mismatch')
                name=f'{arm}_{task}';outputs[name]=probability
                record={'task':name,'seed':seed,'context_boats':int(mask.sum()),'query_boats':len(q),
                    'features':size,'seconds':time.perf_counter()-started}
                audit.append(record);print(json.dumps(record),flush=True)
                del estimator;gc.collect()
                if torch.cuda.is_available():torch.cuda.empty_cache()
        scores,probabilities=combine_outputs(outputs,self.policy)
        if output_dir is not None:
            output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
            np.save(output_dir/'final_scores.npy',scores);np.save(output_dir/'class_probabilities.npy',probabilities)
            (output_dir/'task_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        return scores.argmax(axis=1),probabilities
