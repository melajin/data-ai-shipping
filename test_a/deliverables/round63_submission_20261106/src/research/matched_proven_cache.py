"""Round-local two-fold training views matching all20 actually deployed tasks."""
from proven_normalization_cache import normalized_fold
from full_context_body_cache import encode_frozen
from fresh_architecture_adapter import weight_digest
from fresh_rounds import *
from sklearn.model_selection import StratifiedKFold

def task_specs(calls):
    result=[]
    for i,c in enumerate(calls):
        pair=[int(c['task'][-3]),int(c['task'][-1])] if 'pair_' in c['task'] else None
        name=c['arm']+'_'+c['task'] if c['arm'] in ['compact','state'] else c['task']
        result.append({'index':i,'name':name,'features':c['n_features'],'pair':pair,'classes':2 if pair else 4})
    assert len(result)==20
    return result

def create_matched_caches(owner,encoded,labels):
    folder=owner.audit_dir/'matched_view_cache';folder.mkdir();assert encoded.shape==(4423,402)
    calls=[json.loads(l) for l in (owner.audit_dir.parent/'fresh_fit_calls.jsonl').read_text().splitlines()]
    public=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict']
    teacher_sha=weight_digest({k.removeprefix('icl_predictor.'):v for k,v in public.items() if k.startswith('icl_predictor.')})
    assert weight_digest(owner.teacher_icl.state_dict())==teacher_sha
    assert all(torch.equal(v.detach().cpu(),public[k]) for k,v in owner.model_.state_dict().items() if k in public)
    assert not (owner.audit_dir/'actual_optimizer_steps.jsonl').exists();del public
    crop=np.asarray(owner._X_encoder_.transform(owner.crop_raw),dtype=encoded.dtype);flags=np.random.default_rng(owner.random_state+100000).random(len(labels))<.5;mixed=np.where(flags[:,None],crop,encoded)
    np.savez(folder/'encoded_inputs.npz',encoded_full=encoded,encoded_crop=crop,crop_flags=flags,FIT_ids=owner.fit_ids)
    owner.teacher_icl.cuda().train();records=[];views=0
    for task in task_specs(calls):
        positions=np.flatnonzero(np.isin(labels,task['pair'])) if task['pair'] else np.arange(len(labels));target=np.searchsorted(task['pair'],labels[positions]) if task['pair'] else labels
        K=task['classes'];seed=owner.random_state+task['index']*997
        for fi,(ci,qi) in enumerate(StratifiedKFold(n_splits=2,shuffle=True,random_state=seed).split(np.zeros(len(target)),target)):
            context=positions[ci];query=positions[qi];assert not set(context)&set(query)
            xs,cy,qy=normalized_fold(mixed[positions,:task['features']],target,ci,qi,owner.random_state);reps=[];teachers=[]
            for method,X in enumerate(xs):
                rr=[];tt=[]
                for shift in range(K):
                    perm=torch.roll(torch.arange(K),shifts=shift);cl=perm[cy.long()].float()[None];rep=encode_frozen(owner.model_,X,cl);rr.append(rep[0])
                    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):teacher=owner.teacher_icl(rep.cuda().float().clone(),y_train=cl.cuda())[...,:K].float()
                    assert torch.isfinite(teacher).all();tt.append(teacher[0].cpu());views+=1
                reps.append(torch.stack(rr));teachers.append(torch.stack(tt))
            path=folder/f'task_{task["index"]:02}_fold_{fi}.pt';normal=path.with_suffix('.npz')
            torch.save({'representations':torch.stack(reps),'teacher_logits':torch.stack(teachers),'context_labels':cy,'query_targets':qy,'context_indices':context,'query_indices':query},path)
            np.savez(normal,none=xs[0].numpy(),power=xs[1].numpy(),context_labels=cy.numpy(),query_targets=qy.numpy())
            rec={**task,'fold':fi,'fold_seed':seed,'preprocessing_seed':owner.random_state,'context_ids':owner.fit_ids[context].tolist(),'query_ids':owner.fit_ids[query].tolist(),'context_rows':len(context),'query_rows':len(query),'cache':str(path.relative_to(owner.audit_dir)),'cache_sha256':sha(path),'normalized_inputs':str(normal.relative_to(owner.audit_dir)),'normalized_sha256':sha(normal)};records.append(rec)
        dump(folder/'manifest.json',{'records':records,'complete':False});print('MATCHED20_CACHE',task['index']+1,task['name'],'folds2/norms2/views',K,flush=True)
    assert views==176 and weight_digest(owner.teacher_icl.state_dict())==teacher_sha
    owner.teacher_icl.cpu();del owner.teacher_icl;gc.collect();torch.cuda.empty_cache()
    dump(folder/'manifest.json',{'records':records,'complete':True,'encoder_label_normal_views':views,'teacher_public_ICL_sha256':teacher_sha,'teacher_fixed_public_before_any_update':True,'encoded_inputs_sha256':sha(folder/'encoded_inputs.npz'),'crop_flag_seed':owner.random_state+100000});return records
