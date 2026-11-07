"""Same per-task seed,class shuffles,feature shuffles and4members as deployment."""
from final_evidence_cache import *
import tabicl._finetune.data as fd
from tabicl._sklearn.preprocessing import TransformToNumerical

def native_specs(calls):return [{**r,'seed':calls[r['index']]['seed']} for r in task_specs(calls)]

def native_fold_views(mixed,labels,context,query,task):
    cy=np.searchsorted(task['pair'],labels[context]) if task['pair'] else labels[context]
    # Match the production float32/F-order ndarray route and fit its numeric
    # imputer on this task's context only,before the exact native ensemble.
    x=np.asfortranarray(mixed[context,:task['features']],dtype=np.float32);q=np.asfortranarray(mixed[query,:task['features']],dtype=np.float32);numeric=TransformToNumerical();x=numeric.fit_transform(x);q=numeric.transform(q)
    gen=fd._build_ensemble_generator(classification=True,n_estimators=4,norm_methods=['none','power'],feat_shuffle_method='latin',class_shuffle_method='shift',outlier_threshold=4.,random_state=task['seed']);gen.fit(x,cy);variants=gen.transform(q,mode='both');views=[]
    for method,(X,targets) in variants.items():
        for i,shuffle in enumerate(gen.class_shuffles_[method]):
            perm=torch.tensor(shuffle,dtype=torch.long);assert np.array_equal(targets[i],perm[torch.from_numpy(cy).long()].numpy());views.append({'X':torch.from_numpy(X[i:i+1]).float(),'context_labels':torch.from_numpy(targets[i]).float(),'permutation':perm,'method':method,'member_in_method':i})
    assert len(views)==4;return views

def create_native_caches(owner,encoded,labels):
    folder=owner.audit_dir/'native_four_cache';folder.mkdir();calls=[json.loads(l) for l in (owner.audit_dir.parent/'fresh_fit_calls.jsonl').read_text(encoding='utf-8').splitlines()];specs=native_specs(calls);public=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict'];state=owner.model_.state_dict();assert all(torch.equal(state[k].cpu(),v) for k,v in public.items()) and all(torch.count_nonzero(v)==0 for v in owner.initial_new_body.values());teacher_sha=weight_digest(owner.teacher_icl.state_dict());del public,state
    assert not (owner.audit_dir/'actual_optimizer_steps.jsonl').exists();raw=owner.original_fit_features;crop=np.asarray(owner.crop_raw,dtype=np.float32);flags=np.random.default_rng(owner.random_state+100000).random(len(labels))<.5;mixed=np.where(flags[:,None],crop,raw);np.savez(folder/'encoded_inputs.npz',native_raw_full=raw,native_raw_crop=crop,crop_flags=flags,FIT_ids=owner.fit_ids);owner.teacher_icl.cuda().train();records=[]
    retained={};prepared=getattr(owner,'prepared_current_round_cache',None)
    if prepared is not None:
        assert prepared.resolve().is_relative_to(owner.audit_dir.parent.resolve()) and not (prepared.parent/'actual_optimizer_steps.jsonl').exists()
        prior=json.loads((prepared/'manifest.json').read_text(encoding='utf-8'));retained={(r['fold'],r['index']):r for r in prior['records']};old=np.load(prepared/'encoded_inputs.npz')
        for name,value in [('native_raw_full',raw),('native_raw_crop',crop),('crop_flags',flags),('FIT_ids',owner.fit_ids)]:assert np.array_equal(old[name],value,equal_nan=True)
    for fi,(fc,query) in enumerate(StratifiedKFold(n_splits=2,shuffle=True,random_state=owner.random_state).split(np.zeros(len(labels)),labels)):
        for task in specs:
            context=fc[np.isin(labels[fc],task['pair'])] if task['pair'] else fc;views=native_fold_views(mixed,labels,context,query,task);rr=[];tt=[];norm={}
            if (fi,task['index']) in retained:
                rec=retained[(fi,task['index'])];old_path=prepared.parent/rec['cache'];old_norm=prepared.parent/rec['normalized_inputs'];assert sha(old_path)==rec['cache_sha256'] and sha(old_norm)==rec['normalized_sha256'] and rec['context_ids']==owner.fit_ids[context].tolist() and rec['query_ids']==owner.fit_ids[query].tolist()
                data=torch.load(old_path,map_location='cpu',weights_only=False);normal=np.load(old_norm);assert torch.equal(data['global_query_targets'],torch.from_numpy(labels[query]).long())
                for i,view in enumerate(views):assert np.array_equal(view['X'].numpy(),normal[f'X_{i}']) and torch.equal(view['context_labels'],data['context_labels'][i]) and torch.equal(view['permutation'],data['permutations'][i])
                shutil.copy2(old_path,owner.audit_dir/rec['cache']);shutil.copy2(old_norm,owner.audit_dir/rec['normalized_inputs']);records.append(rec);dump(folder/'manifest.json',{'records':records,'complete':False});print('VERIFIED_SAME_ROUND_NATIVE4_CACHE_RETAINED',fi,task['index']+1,flush=True);continue
            for i,view in enumerate(views):
                cl=view['context_labels'][None];rep=encode_frozen(owner.model_,view['X'],cl);rr.append(rep[0]);norm[f'X_{i}']=view['X'].numpy()
                with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16,cache_enabled=False):value=owner.teacher_icl(rep.cuda().float().clone(),y_train=cl.cuda())[...,:task['classes']].float().cpu()
                tt.append(value[0])
            path=folder/f'fold_{fi}_task_{task["index"]:02}.pt';normal=path.with_suffix('.npz');torch.save({'representations':torch.stack(rr),'teacher_logits':torch.stack(tt),'context_labels':torch.stack([v['context_labels'] for v in views]),'permutations':torch.stack([v['permutation'] for v in views]),'global_query_targets':torch.from_numpy(labels[query]).long(),'context_indices':context,'query_indices':query},path);np.savez(normal,**norm)
            rec={**task,'fold':fi,'fold_seed':owner.random_state,'context_ids':owner.fit_ids[context].tolist(),'query_ids':owner.fit_ids[query].tolist(),'context_rows':len(context),'query_rows':len(query),'cache':str(path.relative_to(owner.audit_dir)),'cache_sha256':sha(path),'normalized_inputs':str(normal.relative_to(owner.audit_dir)),'normalized_sha256':sha(normal),'members':[{'method':v['method'],'member_in_method':v['member_in_method'],'permutation':v['permutation'].tolist()} for v in views]};records.append(rec);dump(folder/'manifest.json',{'records':records,'complete':False});print('NATIVE4_CACHE',fi,task['index']+1,task['name'],'ctx',len(context),'allclassquery',len(query),flush=True)
    assert weight_digest(owner.teacher_icl.state_dict())==teacher_sha;owner.teacher_icl.cpu();del owner.teacher_icl;gc.collect();torch.cuda.empty_cache();dump(folder/'manifest.json',{'records':records,'complete':True,'encoder_native_ensemble_views':160,'teacher_public_ICL_sha256':teacher_sha,'teacher_fixed_public_before_any_update':True,'encoded_inputs_sha256':sha(folder/'encoded_inputs.npz'),'crop_flag_seed':owner.random_state+100000,'common_global_query_folds_for_all20tasks':True,'per_task_preprocessing_seed_matches_deployment':True});return records
