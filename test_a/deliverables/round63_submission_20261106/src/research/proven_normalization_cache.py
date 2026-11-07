"""Develop49:paired normalization/label views,public teacher logits cached before updates."""
from fresh_rounds import *
from full_context_body_cache import encode_frozen
from fresh_architecture_adapter import weight_digest
from sklearn.model_selection import StratifiedKFold
import tabicl._finetune.data as fd

METHODS=['none','power']

def normalized_fold(mixed,labels,context,query,seed):
    gen=fd._build_ensemble_generator(classification=True,n_estimators=2,norm_methods=METHODS,feat_shuffle_method='latin',class_shuffle_method='none',outlier_threshold=4.,random_state=seed)
    gen.fit(mixed[context],labels[context]);variants=gen.transform(mixed[query],mode='both');assert set(variants)==set(METHODS)
    xs=[]
    for method in METHODS:
        X,cy=variants[method];assert X.shape[0]==1 and np.array_equal(cy[0],labels[context]);xs.append(torch.from_numpy(X).float())
    return xs,torch.from_numpy(labels[context]).float(),torch.from_numpy(labels[query]).long()

def create_proven_caches(owner,encoded,labels):
    folder=owner.audit_dir/'proven_view_cache';folder.mkdir();assert encoded.shape==(4423,402) and set(labels)=={0,1,2,3}
    public_digest=weight_digest(owner.model_.state_dict());public=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict'];assert weight_digest(public)==public_digest;del public
    assert not (owner.audit_dir/'actual_optimizer_steps.jsonl').exists();crop=np.asarray(owner._X_encoder_.transform(owner.crop_raw),dtype=encoded.dtype);flags=np.random.default_rng(owner.random_state+100000).random(len(encoded))<.5;mixed=np.where(flags[:,None],crop,encoded)
    np.savez(folder/'encoded_inputs.npz',encoded_full=encoded,encoded_crop=crop,crop_flags=flags,FIT_ids=owner.fit_ids);records=[]
    for fi,(context,query) in enumerate(StratifiedKFold(n_splits=4,shuffle=True,random_state=owner.random_state).split(np.zeros(len(labels)),labels)):
        xs,cy,qy=normalized_fold(mixed,labels,context,query,owner.random_state);reps=[];teachers=[]
        for method,X in enumerate(xs):
            rr=[];tt=[]
            for shift in range(4):
                perm=torch.roll(torch.arange(4),shifts=shift);context_labels=perm[cy.long()].float()[None];rep=encode_frozen(owner.model_,X,context_labels);rr.append(rep[0])
                with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):teacher=owner.model_.icl_predictor(rep.to('cuda').float().clone(),y_train=context_labels.cuda())[...,:4].float()
                assert torch.isfinite(teacher).all();tt.append(teacher[0].cpu())
            reps.append(torch.stack(rr));teachers.append(torch.stack(tt))
        path=folder/f'fold_{fi}.pt';torch.save({'representations':torch.stack(reps),'teacher_logits':torch.stack(teachers),'context_labels':cy,'query_targets':qy,'context_indices':context,'query_indices':query},path)
        normal=folder/f'fold_{fi}_normalized.npz';np.savez(normal,none=xs[0].numpy(),power=xs[1].numpy(),context_labels=cy.numpy(),query_targets=qy.numpy())
        records.append({'fold':fi,'fold_seed':owner.random_state,'context_ids':owner.fit_ids[context].tolist(),'query_ids':owner.fit_ids[query].tolist(),'context_rows':len(context),'query_rows':len(query),'cache':str(path.relative_to(owner.audit_dir)),'cache_sha256':sha(path),'normalized_inputs':str(normal.relative_to(owner.audit_dir)),'normalized_sha256':sha(normal),'normalization_methods':METHODS,'cyclic_label_views_per_method':4,'teacher_public_state_sha256':public_digest,'teacher_computed_before_any_optimizer_step':True,'query_labels_not_encoded':True})
        print('PROVEN49_ALIGNED_CACHE',fi,len(context),len(query),'norms2/labelviews4',flush=True)
    assert weight_digest(owner.model_.state_dict())==public_digest
    dump(folder/'manifest.json',{'records':records,'complete':True,'encoder_label_normal_views':32,'teacher_public_state_sha256':public_digest,'teacher_logits_fixed_before_any_gradient_update':True,'no_teacher_forward_during_training_updates':True,'encoded_inputs_sha256':sha(folder/'encoded_inputs.npz'),'crop_flag_seed':owner.random_state+100000});return records
