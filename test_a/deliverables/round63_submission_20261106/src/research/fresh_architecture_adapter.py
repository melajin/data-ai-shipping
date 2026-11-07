"""Architecture and coherent augmentation factorial, never old learned weights."""
from fresh_representation_adaptation import RepresentationAdapter
from fresh_rounds import *
from tabicl_row_token_mixer import RowTokenMixer
import tabicl._finetune.base as ft_base
import tabicl._finetune.data as ft_data


def weight_digest(state):
    digest=hashlib.sha256()
    for name,value in state.items():
        z=value.detach().cpu().contiguous()
        digest.update(name.encode());digest.update(str((z.dtype,tuple(z.shape))).encode());digest.update(z.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


class ArchitectureAdapter(RepresentationAdapter):
    def _load_pretrained(self,device):
        super()._load_pretrained(device)
        if self.use_architecture:
            self.model_.row_interactor=RowTokenMixer(self.model_.row_interactor).to(device)
            torch.save(self.model_.row_interactor.new_state(),self.audit_dir/'initial_new_module.pt')
        dump(self.audit_dir/'architecture.json',{'modified':self.use_architecture,'part':'row_interactor output','base_CLS_tokens':4,'base_embed_dim':128,
            'new_module':'FP32 LayerNorm +4-head attention over4 existing CLS summaries + input-dependent4 gates + residual connection',
            'initial_function':'Attention output projection is zero; sigmoid gates start at sigmoid(-2), so original output is exactly preserved and output projection receives gradients.',
            'frozen':'Original column and row networks','trainable':'ICL predictor and new module, when present',
            'custom_checkpoint_loader':'tabicl_row_token_mixer.load_custom_tabicl_checkpoint; vanilla TabICL checkpoint loading is insufficient for modified arms'})

    def _apply_freezing(self,model):
        super()._apply_freezing(model)
        base=model.row_interactor.base if self.use_architecture else model.row_interactor
        for p in base.parameters():p.requires_grad=False
        return True

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        result=super()._run_validation(inner,X_train,y_train,X_val,y_val)
        optimizer=self._audit_optimizer
        steps=max([int(z['step']) for z in optimizer.state.values() if 'step' in z],default=0)
        event={'validation_index':getattr(self,'_validation_index',0),'primary':float(result.primary),'loss_forward_calls':self.loss_forward_calls,
               'optimizer_steps':steps,'weights_sha256':weight_digest(self.model_.state_dict())}
        self._validation_index=event['validation_index']+1
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        return result

    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        original_iterator=ft_base.iter_epoch_meta_batches;original_optimizer=ft_base.AdamW
        def optimizer(params,lr,**kwargs):
            params=list(params)
            new_ids={id(p) for name,p in self.model_.named_parameters() if name.startswith('row_interactor.') and not name.startswith('row_interactor.base.')} if self.use_architecture else set()
            new=[p for p in params if id(p) in new_ids];old=[p for p in params if id(p) not in new_ids]
            groups=[{'params':old,'lr':lr}]
            if new:groups.append({'params':new,'lr':3e-4})
            dump(self.audit_dir/'optimizer_groups.json',{'original_ICL_lr':lr,'new_module_lr':3e-4 if new else None,'original_trainable_parameters':sum(p.numel() for p in old),'new_trainable_parameters':sum(p.numel() for p in new)})
            opt=original_optimizer(groups,lr=lr,**kwargs);self._audit_optimizer=opt;return opt
        def iterator(encoded,labels,**kw):
            assert kw.get('world_size',1)==1 and kw.get('rank',0)==0
            assert len(encoded)==len(self.fit_ids)==len(np.unique(self.fit_ids))
            crop=np.asarray(self._X_encoder_.transform(self.crop_raw),dtype=encoded.dtype)
            assert crop.shape==encoded.shape
            rng=np.random.default_rng(kw['epoch_seed']+100000);selected=rng.random(len(encoded))<.5 if self.use_augmentation else np.zeros(len(encoded),dtype=bool)
            mixed=encoded.copy();mixed[selected]=crop[selected]
            chunks=ft_data._chunk_indices(len(labels),max_chunk_size=kw['max_chunk_size'],rng=np.random.default_rng(kw['epoch_seed']),min_chunk_size=kw.get('min_chunk_size',50))
            for k,batch in enumerate(original_iterator(mixed,labels,**kw)):
                ix=chunks[k];qsize=max(1,int(len(ix)*kw['query_ratio']),int(labels[ix].max())+1)
                ci,qi=ft_data._split_ctx_query(labels[ix],query_size=qsize,seed=kw['epoch_seed']+k*7919,stratify=True)
                context=self.fit_ids[ix[ci]];query=self.fit_ids[ix[qi]]
                assert not set(context)&set(query) and len(context)+len(query)==len(ix)
                # Class shuffle is predeclared none, making this a direct audit
                # of the actually yielded context/query labels, not only a plan.
                assert np.array_equal(batch.y_train[0].numpy(),labels[ix[ci]]) and np.array_equal(batch.y_query[0].numpy(),labels[ix[qi]])
                rec={'epoch_seed':kw['epoch_seed'],'chunk':k,'context_ids':context.tolist(),'query_ids':query.tolist(),
                    'crop_ids':self.fit_ids[ix[selected[ix]]].tolist(),'one_version_per_boat':True,'context_query_boat_overlap':0}
                with (self.audit_dir/'actual_training_batches.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
                yield batch
        ft_base.iter_epoch_meta_batches=iterator;ft_base.AdamW=optimizer
        try:return super()._fit_impl(X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:
            ft_base.iter_epoch_meta_batches=original_iterator;ft_base.AdamW=original_optimizer
            if hasattr(self,'_audit_optimizer'):del self._audit_optimizer


def train_architecture_arm(rd,name,use_architecture,use_augmentation,train,crop,queries,s,sub,tu):
    ad=rd/name;ad.mkdir();seed=SEED+3000;torch.manual_seed(seed);np.random.seed(seed);torch.cuda.manual_seed_all(seed)
    m=ArchitectureAdapter(epochs=8,learning_rate=1e-5,max_data_size=512,finetune_ctx_query_ratio=.25,
        n_estimators_finetune=2,n_estimators_validation=2,n_estimators_inference=4,
        freeze_col=True,freeze_row=False,freeze_icl=False,class_shuffle_method='none',early_stopping=True,patience=3,time_limit=480,save_interval=0,
        model_path=CHECKPOINT,allow_auto_download=False,device='cuda',random_state=seed,verbose=True,eval_metric='accuracy',
        extra_classifier_kwargs={'batch_size':1,'kv_cache':'repr','use_amp':True,'use_fa3':False,'n_jobs':4})
    fit=s.split.eq('FIT').to_numpy();m.use_architecture=use_architecture;m.use_augmentation=use_augmentation;m.crop_raw=crop;m.fit_ids=s.index[fit].to_numpy()
    m.loss_forward_calls=0;m.finite_loss_calls=0;m.original_control={};m.raw_queries=queries;m.audit_dir=ad
    begun=now();t=time.time();m.fit(train,s.loc[fit,'y'].to_numpy(),X_val=queries['full'][tu],y_val=sub.loc[tu,'y'].to_numpy(),output_dir=ad/'checkpoint')
    original=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict'];changed=[];new_changed=[]
    initial=torch.load(ad/'initial_new_module.pt',map_location='cpu',weights_only=True) if use_architecture else {}
    for key,value in m.model_.state_dict().items():
        if use_architecture and key.startswith('row_interactor.') and not key.startswith('row_interactor.base.'):
            short=key.removeprefix('row_interactor.')
            if not torch.equal(value.detach().cpu(),initial[short]):new_changed.append(key)
        else:
            original_key=key.replace('row_interactor.base.','row_interactor.',1)
            if not torch.equal(value.detach().cpu(),original[original_key]):changed.append(original_key)
    assert all(k.startswith('icl_predictor.') for k in changed)
    assert m.loss_forward_calls>0 and m.loss_forward_calls==m.finite_loss_calls
    saved=torch.load(ad/'checkpoint'/'best.ckpt',map_location='cpu',weights_only=False)
    steps=max([int(z['step']) for z in saved['optimizer_state']['state'].values() if 'step' in z],default=0)
    events=[json.loads(x) for x in (ad/'validation_events.jsonl').read_text(encoding='utf-8').splitlines()]
    selected=max(events,key=lambda z:z['primary']);assert selected['primary']==float(m._best_metric_)
    assert weight_digest(saved['state_dict'])==selected['weights_sha256']
    audit={'arm':name,'use_architecture':use_architecture,'use_augmentation':use_augmentation,'started':begun,'finished':now(),'training_seconds':time.time()-t,
        'loss_forward_calls':m.loss_forward_calls,'finite_loss_calls':m.finite_loss_calls,'selected_optimizer_steps':selected['optimizer_steps'],'selected_epoch':selected['validation_index'],
        'optimizer_steps_recorded_at_final_save':steps,'epoch_field_recorded_at_final_save':int(saved['epoch']),'selected_validation_weights_sha256':selected['weights_sha256'],
        'changed_original_tensor_names':changed,'changed_new_tensor_names':new_changed,'selected_new_module_changed':bool(new_changed),'best_TUNE_accuracy':float(m._best_metric_),
        'original_checkpoint_sha256':sha(CHECKPOINT),'selected_checkpoint_sha256':sha(ad/'checkpoint'/'best.ckpt'),'FIT_ids_sha256':hashlib.sha256(m.fit_ids.tobytes()).hexdigest(),
        'TUNE_ids_sha256':hashlib.sha256(sub.index[tu].to_numpy().tobytes()).hexdigest(),'seed':seed,'epochs_max':8,'max_data_size':512,
        'preprocessing_source_sha256':sha(Path(ft_data.__file__)),'frozen_original_row_and_column_unchanged':True}
    dump(ad/'weight_change_audit.json',audit);del saved,original;gc.collect()
    pred={}
    for v in VIEWS:
        pred[v]=np.concatenate([m.predict_proba(queries[v][i:i+1000]) for i in range(0,len(sub),1000)])
        assert list(m.classes_)==[0,1,2,3];np.save(ad/f'adapted_head_{v}.npy',pred[v])
    if use_architecture:
        # Diagnostic only. Refit inference context after bypassing the residual
        # so no cache from the active residual is silently reused.
        m.model_.row_interactor.bypass=True;inner=m._build_inner_estimator(m.model_,4,torch.device('cuda'))
        encoded_train=np.asarray(m._X_encoder_.transform(train),dtype=np.float64);inner.fit(encoded_train,s.loc[fit,'y'].to_numpy())
        for v in VIEWS:
            q=np.asarray(m._X_encoder_.transform(queries[v]),dtype=np.float64)
            p=np.concatenate([inner.predict_proba(q[i:i+1000]) for i in range(0,len(sub),1000)]);np.save(ad/f'residual_bypassed_head_{v}.npy',p)
        m.model_.row_interactor.bypass=False;del inner
        dump(ad/'bypass_diagnostic.json',{'new_inference_context_fit_after_bypass':True,'same_selected_weights':True,'REPORT_used_for_selection':False,'diagnostic_only':True})
    original_probs={v:p.copy() for v,p in m.original_control.items()};del m;gc.collect();torch.cuda.empty_cache()
    print('ARCHITECTURE_ARM_COMPLETE',name,json.dumps({k:audit[k] for k in ['loss_forward_calls','selected_optimizer_steps','selected_new_module_changed','best_TUNE_accuracy']}),flush=True)
    return pred,original_probs,audit
