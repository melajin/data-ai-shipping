"""Replay the recorded Round63 training on its supplied fixed feature tensors.

Run through scripts/train.py in a separate process. The deployment path never
imports this module or the preserved research dependency closure.
"""
import json
import os
import sys
from pathlib import Path


def reproduce(root,output_dir):
    root=Path(root).resolve();rd=Path(output_dir).resolve()
    if rd.exists():raise FileExistsError(f'Training output already exists:{rd}')
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
    sys.path.insert(0,str(root/'src/research'))
    import numpy as np
    import pandas as pd
    import torch
    import experiment
    # These globals belong exclusively to the isolated reproduction worker.
    experiment.B=root/'data/reproduction';experiment.CHECKPOINT=root/'model/public_init.ckpt'
    from middle_transition_training import MiddleTransitionBodyAdapter
    from fresh_wide_training import train_wide
    from encoded_public_cache import capture_reference_encodings,attach_capture
    from fresh_fixed_inference import fixed_public_inference
    from fresh_primary_reference import policy,choose_blend
    from matched_proven_training import choose_matched
    from sklearn.metrics import f1_score
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if filename and Path(filename).resolve().parent==root/'src/research':
            if hasattr(module,'B'):module.B=root/'data/reproduction'
            if hasattr(module,'CHECKPOINT'):module.CHECKPOINT=root/'model/public_init.ckpt'
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    rd.mkdir(parents=True)
    write=lambda path,value:path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    write(rd/'config.json',{'round':63,'mode':'fixed-feature training replay','original_public_initialization':True,
        'input_features':'Supplied original FIT-fitted476-column tensors and coherent crop',
        'prototype_refit_in_this_command':False,'selection':'TUNE only;positive trained body;REPORT after freeze'})
    s=pd.read_csv(root/'data/reproduction/fixed_split.csv',index_col='id')
    raw=np.load(root/'data/reproduction/training_inputs.npz')
    fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();fy=s.loc[fit,'y'].to_numpy();y=sub.y.to_numpy()
    specs=json.loads((root/'data/reproduction/task_specs.json').read_text(encoding='utf-8'))
    outputs={}
    with capture_reference_encodings(rd) as paths:
        for spec in specs:
            pair=None if spec['task']=='head' else tuple(map(int,spec['task'].split('_')[-2:]))
            mask=np.ones(len(fy),dtype=bool) if pair is None else np.isin(fy,pair)
            x=np.asfortranarray(raw['raw_train'][mask,:spec['n_features']],dtype=np.float32)
            q=np.asfortranarray(raw['raw_query_full'][:,:spec['n_features']],dtype=np.float32)
            estimator=experiment.model(spec['seed'],4)
            with fixed_public_inference():estimator.fit(x,fy[mask])
            probability=np.concatenate([estimator.predict_proba(q[i:i+1000]) for i in range(0,len(q),1000)])
            name=spec['arm']+'_'+spec['task'] if spec['arm'] in ['compact','state'] else spec['task']
            outputs[name]=probability
            with (rd/'fresh_fit_calls.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({**spec,'fresh_fit':True,'view':'full'})+'\n')
            del estimator
    if len(paths)!=20:raise AssertionError('Expected20 reference tasks')
    import itertools
    pairs={arm:np.ones((len(y),4,4)) for arm in ['compact','state','relation']}
    for arm in pairs:
        for a,b in itertools.combinations(range(4),2):
            name=f'{arm}_pair_{a}_{b}' if arm!='relation' else f'relation_pair_{a}_{b}'
            pairs[arm][:,a,b]=outputs[name][:,0];pairs[arm][:,b,a]=1-outputs[name][:,0]
    alpha,weights,_=policy(outputs['compact_head'][tu],pairs['compact'][tu],y[tu])
    (beta,j16,p16,_),bc=choose_blend(outputs['compact_head'],pairs['compact'],outputs['state_head'],pairs['state'],alpha,weights,y,tu)
    (eta,joint,paired,baseline_prediction),ec=choose_blend(j16,p16,j16,pairs['relation'],alpha,weights,y,tu)
    config={'alpha':alpha,'weights':weights.tolist(),'state_beta':beta,'state_candidates':bc,'relation_beta':eta,'relation_candidates':ec}
    write(rd/'fresh_reference_policy_full.json',config)
    np.save(rd/'fresh_reference_joint_full.npy',joint);np.save(rd/'fresh_reference_pair_full.npy',paired)
    reference={'joint':joint,'pair':paired,'prediction':baseline_prediction,'alpha':alpha,'weights':weights,'policy':config}
    for view in ['d1','d3','d7']:
        estimator=experiment.model(20262015,4)
        attach_capture(estimator,rd/'encoded_public_deployment'/f'short_{view}.pt')
        with fixed_public_inference():estimator.fit(np.asfortranarray(raw['raw_train'][:,:150]),fy)
        q=np.asfortranarray(raw[f'raw_query_{view}'][:,:150])
        for i in range(0,len(q),1000):estimator.predict_proba(q[i:i+1000])
        del estimator
    predictions,audit=train_wide(rd,raw['raw_train'],raw['raw_crop'],
        {view:raw[f'raw_query_{view}'] for view in ['full','d1','d3','d7']},s,reference,
        adapter_type=MiddleTransitionBodyAdapter,round_number=63,
        train_kwargs={'epochs':6,'patience':1,'time_limit':900,'learning_rate':1e-5,'max_data_size':4423,'use_lr_scheduler':False})
    selected=rd/'wide_body'/f'deployment_validation_{audit["selected_epoch"]:02}'
    best,output,candidates,_=choose_matched(reference,np.load(selected/'joint.npy'),np.load(selected/'pair.npy'),y,tu)
    prediction=output[0]
    result={'selected_epoch':audit['selected_epoch'],'selected_updates':audit['selected_optimizer_steps'],
        'actual_updates':audit['actual_optimizer_steps'],'gamma':best['gamma'],
        'REPORT_micro_f1':float(f1_score(y[~tu],prediction[~tu],average='micro')),
        'training_feature_basis':'Original supplied FIT-only fitted features;this command retrains the neural body and references',
        'used_as_submission_model':False,'session_state_updated':False}
    write(rd/'training_result.json',result)
    return result
