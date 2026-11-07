"""Common FIT query fold for every task,including all out-of-pair queries."""
from matched_proven_cache import *

def create_evidence_caches(owner,encoded,labels):
    folder=owner.audit_dir/'evidence_view_cache';folder.mkdir();assert encoded.shape==(4423,402)
    calls=[json.loads(l) for l in (owner.audit_dir.parent/'fresh_fit_calls.jsonl').read_text(encoding='utf-8').splitlines()];specs=task_specs(calls);teacher_sha=weight_digest(owner.teacher_icl.state_dict());public=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict'];assert weight_digest(owner.model_.state_dict())==weight_digest(public);del public
    assert not (owner.audit_dir/'actual_optimizer_steps.jsonl').exists();crop=np.asarray(owner._X_encoder_.transform(owner.crop_raw),dtype=encoded.dtype);flags=np.random.default_rng(owner.random_state+100000).random(len(labels))<.5;mixed=np.where(flags[:,None],crop,encoded);np.savez(folder/'encoded_inputs.npz',encoded_full=encoded,encoded_crop=crop,crop_flags=flags,FIT_ids=owner.fit_ids)
    owner.teacher_icl.cuda().train();records=[];views=0
    for fi,(full_context,query) in enumerate(StratifiedKFold(n_splits=2,shuffle=True,random_state=owner.random_state).split(np.zeros(len(labels)),labels)):
        for task in specs:
            context=full_context[np.isin(labels[full_context],task['pair'])] if task['pair'] else full_context
            local_labels=np.searchsorted(task['pair'],labels[context]) if task['pair'] else labels[context];positions=np.concatenate([context,query]);dummy=np.concatenate([local_labels,np.zeros(len(query),dtype=labels.dtype)])
            xs,cy,unused=normalized_fold(mixed[positions,:task['features']],dummy,np.arange(len(context)),np.arange(len(context),len(positions)),owner.random_state);K=task['classes'];reps=[];teachers=[]
            for method,X in enumerate(xs):
                rr=[];tt=[]
                for shift in range(K):
                    perm=torch.roll(torch.arange(K),shifts=shift);cl=perm[cy.long()].float()[None];rep=encode_frozen(owner.model_,X,cl);rr.append(rep[0])
                    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):value=owner.teacher_icl(rep.cuda().float().clone(),y_train=cl.cuda())[...,:K].float().cpu()
                    tt.append(value[0]);views+=1
                reps.append(torch.stack(rr));teachers.append(torch.stack(tt))
            path=folder/f'fold_{fi}_task_{task["index"]:02}.pt';normal=path.with_suffix('.npz');torch.save({'representations':torch.stack(reps),'teacher_logits':torch.stack(teachers),'context_labels':cy,'global_query_targets':torch.from_numpy(labels[query]).long(),'context_indices':context,'query_indices':query},path);np.savez(normal,none=xs[0].numpy(),power=xs[1].numpy(),context_labels=cy.numpy(),global_query_targets=labels[query])
            rec={**task,'fold':fi,'fold_seed':owner.random_state,'context_ids':owner.fit_ids[context].tolist(),'query_ids':owner.fit_ids[query].tolist(),'context_rows':len(context),'query_rows':len(query),'cache':str(path.relative_to(owner.audit_dir)),'cache_sha256':sha(path),'normalized_inputs':str(normal.relative_to(owner.audit_dir)),'normalized_sha256':sha(normal),'queries_include_all_four_classes_even_for_binary_context':True};records.append(rec);dump(folder/'manifest.json',{'records':records,'complete':False});print('FINAL_EVIDENCE_CACHE',fi,task['index']+1,task['name'],'ctx',len(context),'allclassquery',len(query),flush=True)
    assert views==176 and weight_digest(owner.teacher_icl.state_dict())==teacher_sha;owner.teacher_icl.cpu();del owner.teacher_icl;gc.collect();torch.cuda.empty_cache();dump(folder/'manifest.json',{'records':records,'complete':True,'encoder_label_normal_views':views,'teacher_public_ICL_sha256':teacher_sha,'teacher_fixed_public_before_any_update':True,'encoded_inputs_sha256':sha(folder/'encoded_inputs.npz'),'crop_flag_seed':owner.random_state+100000,'common_global_query_folds_for_all20tasks':True});return records
