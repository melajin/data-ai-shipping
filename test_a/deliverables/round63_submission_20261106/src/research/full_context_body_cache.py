"""Current-round frozen encoders,with fixed feature-group/row chunk boundaries."""
from fresh_rounds import *
from torch.nn import functional as F
from sklearn.model_selection import StratifiedKFold
from fresh_joint_pair_components import official_tasks,task_rows
import tabicl._finetune.data as fd

COL_GROUP_BATCH=16
ROW_BATCH=64

@torch.no_grad()
def encode_frozen(model,X,context_labels):
    assert X.ndim==3 and X.shape[0]==1 and context_labels.shape[0]==1
    assert all(not p.requires_grad for module in [model.col_embedder,model.row_interactor] for p in module.parameters())
    col=model.col_embedder;row=model.row_interactor;device=next(model.parameters()).device
    assert col.feature_group and col.target_aware
    X=X.to(device);labels=context_labels.to(device).float();features=col.feature_grouping(X)
    if col.reserve_cls_tokens>0:features=F.pad(features,(0,0,col.reserve_cls_tokens,0),value=-100.)
    features=features.transpose(1,2);parts=[]
    with torch.autocast('cuda',dtype=torch.bfloat16):
        for start in range(0,features.shape[1],COL_GROUP_BATCH):
            f=features[:,start:start+COL_GROUP_BATCH];y=labels[:,None,:].expand(-1,f.shape[1],-1)
            parts.append(col._compute_embeddings(f,labels.shape[1],y,False).transpose(1,2).cpu())
        columns=torch.cat(parts,dim=2);result=[]
        for start in range(0,X.shape[1],ROW_BATCH):
            result.append(row._train_forward(columns[:,start:start+ROW_BATCH].to(device),None).cpu())
    return torch.cat(result,dim=1).contiguous()

def make_context_batch(mixed,labels,context,query,seed):
    gen=fd._build_ensemble_generator(classification=True,n_estimators=1,norm_methods=None,feat_shuffle_method='latin',class_shuffle_method='none',outlier_threshold=4.,random_state=seed)
    gen.fit(mixed[context],labels[context]);variants=gen.transform(mixed[query],mode='both');assert len(variants)==1
    X,y=next(iter(variants.values()));assert X.shape[0]==1 and np.array_equal(y[0],labels[context])
    return torch.from_numpy(X).float(),torch.from_numpy(y).float(),torch.from_numpy(labels[query]).long()

def create_caches(owner,encoded,labels):
    folder=owner.audit_dir/'full_context_cache';folder.mkdir();crop=np.asarray(owner._X_encoder_.transform(owner.crop_raw),dtype=encoded.dtype)
    flag_seed=owner.random_state+100000;flags=np.random.default_rng(flag_seed).random(len(encoded))<.5;mixed=np.where(flags[:,None],crop,encoded)
    np.savez(folder/'encoded_inputs.npz',encoded_full=encoded,encoded_crop=crop,crop_flags=flags,FIT_ids=owner.fit_ids)
    records=[]
    for ti,pair in enumerate(official_tasks()):
        positions,y=task_rows(labels,pair);fold_seed=owner.random_state+ti*997
        folds=StratifiedKFold(n_splits=4,shuffle=True,random_state=fold_seed)
        for fi,(context,query) in enumerate(folds.split(np.zeros(len(y)),y)):
            assert not set(context)&set(query) and set(y[context])==set(y[query])==set(range(int(y.max())+1))
            X,cy,qy=make_context_batch(mixed[positions],y,context,query,owner.random_state);reps=[];classes=int(y.max())+1
            for shift in range(classes):
                perm=torch.roll(torch.arange(classes),shifts=shift);reps.append(encode_frozen(owner.model_,X,perm[cy.long()].float())[0])
            path=folder/f'task_{ti}_fold_{fi}.pt';torch.save({'representations':torch.stack(reps),'context_labels':cy[0],'query_targets':qy,'context_indices':context,'query_indices':query,'positions':positions},path)
            norm=folder/f'task_{ti}_fold_{fi}_normalized.npz';np.savez(norm,X=X.numpy(),context_labels=cy.numpy(),query_targets=qy.numpy())
            rec={'task_index':ti,'official_pair':pair,'fold':fi,'fold_seed':fold_seed,'preprocessing_seed':owner.random_state,'context_ids':owner.fit_ids[positions[context]].tolist(),'query_ids':owner.fit_ids[positions[query]].tolist(),'context_rows':len(context),'query_rows':len(query),'classes':classes,'label_views':classes,'features_after_context_preprocessing':X.shape[-1],'cache':str(path.relative_to(owner.audit_dir)),'cache_sha256':sha(path),'normalized_inputs':str(norm.relative_to(owner.audit_dir)),'normalized_sha256':sha(norm),'query_labels_not_input_to_any_encoder':True}
            records.append(rec);dump(folder/'manifest.json',{'records':records,'complete':False});print('FULL_CONTEXT_CACHE',ti,fi,len(context),len(query),'views',classes,flush=True)
    manifest={'records':records,'complete':True,'original_public_only_encoder_weights':True,'fixed_column_group_batch':COL_GROUP_BATCH,'fixed_row_batch':ROW_BATCH,'crop_flag_seed':flag_seed,'each_FIT_boat_query_once_per_official_task':True,'all_cyclic_views_encode_context_labels_separately':True,'encoded_inputs_sha256':sha(folder/'encoded_inputs.npz')}
    dump(folder/'manifest.json',manifest);return records
