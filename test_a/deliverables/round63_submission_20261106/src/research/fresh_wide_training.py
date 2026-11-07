"""Broad original-body optimization, coherent crops and positive-only selection."""
from fresh_representation_adaptation import RepresentationAdapter
from fresh_architecture_adapter import weight_digest
from fresh_row_round import choose_records
from fresh_rounds import *
import tabicl._finetune.base as ft_base
import tabicl._finetune.data as ft_data
from fresh_gradient_audit import gradient_statistics
import os
import tempfile

GAMMAS=[0.,.25,.5,.75,1.]

def save_selected_inference_checkpoint(path,saved,selected):
    """Publish selected weights without the optimizer from a later epoch."""
    checkpoint=dict(saved)
    checkpoint.pop('optimizer_state',None)
    checkpoint.pop('scheduler_state',None)
    checkpoint.update(epoch=int(selected['epoch']),curr_step=int(selected['optimizer_steps']),
        selected_epoch=int(selected['epoch']),selected_optimizer_steps=int(selected['optimizer_steps']),
        checkpoint_type='inference_only',resume_training_supported=False)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='wb',dir=path.parent,
                prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            torch.save(checkpoint,stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return checkpoint


def choose_positive(reference,prob,y,tu):
    from fresh_hierarchy_round import hierarchy_scores
    choices=[];out={}
    for g in GAMMAS:
        score=hierarchy_scores(reference['joint'],reference['pair'],prob,reference['alpha'],reference['weights'],g)
        pred=score.argmax(1);m=metrics(y[tu],pred[tu])
        choices.append({'gamma':g,'TUNE_correct':int((pred[tu]==y[tu]).sum()),'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']})
        out[g]=(pred,score)
    best=max(choices[1:],key=lambda z:(z['TUNE_correct'],z['TUNE_macro'],-z['gamma']))
    zero_better=choices[0]['TUNE_correct']>best['TUNE_correct']
    return best,out[best['gamma']],choices,zero_better

class WideBodyAdapter(RepresentationAdapter):
    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        inner.fit(X_train,y_train)
        encoded_full=np.asarray(self._X_encoder_.transform(self.raw_queries['full']),dtype=np.float64)
        assert np.array_equal(encoded_full[self.tune_mask],X_val,equal_nan=True)
        all_p=np.concatenate([inner.predict_proba(encoded_full[j:j+1000]) for j in range(0,len(encoded_full),1000)])
        p=all_p[self.tune_mask]  # Same query order/batches as final inference;REPORT labels never read.
        assert list(inner.classes_)==[0,1,2,3]
        vi=getattr(self,'validation_index',0);self.validation_index=vi+1
        np.save(self.audit_dir/f'validation_head_{vi:02}.npy',p)
        best,_,cand,zero=choose_positive(self.tune_reference,p,y_val,np.ones(len(y_val),dtype=bool))
        steps=max([int(v['step']) for v in self.audit_optimizer.state.values() if 'step' in v],default=0)
        event={'epoch':vi,'optimizer_steps':steps,'loss_forward_calls':self.loss_forward_calls,
            'weights_sha256':weight_digest(self.model_.state_dict()),'positive_choice':best,'candidates':cand,
            'zero_strictly_better':zero,'raw_TUNE_correct':int((p.argmax(1)==y_val).sum()),'eligible_trained_checkpoint':steps>0}
        if vi==0:
            assert steps==self.loss_forward_calls==0
            # Same raw control as the training/validation path; no REPORT labels.
            for v,raw in self.raw_queries.items():
                enc=np.asarray(self._X_encoder_.transform(raw),dtype=np.float64)
                op=all_p if v=='full' else np.concatenate([inner.predict_proba(enc[j:j+1000]) for j in range(0,len(enc),1000)])
                np.save(self.audit_dir/f'unadapted_head_{v}.npy',op)
        elif zero:
            self.time_limit=0  # library exits immediately after this validation
            self.zero_stop=True
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        print('WIDE_BODY_VALIDATION',json.dumps(event),flush=True)
        # Epoch0 may serve as a control but cannot become the trained candidate.
        value=(best['TUNE_correct']+best['TUNE_macro']*1e-4)/len(y_val) if steps else -1.
        return ft_base.ValidationMetrics(primary=value)

    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        orig_iterator=ft_base.iter_epoch_meta_batches;orig_optimizer=ft_base.AdamW;original_split=ft_data._split_ctx_query
        owner=self
        class AuditedAdamW(orig_optimizer):
            def step(self,*args,**kwargs):
                gradients=gradient_statistics(owner.model_.named_parameters())
                assert all(z['finite'] for z in gradients.values())
                result=super().step(*args,**kwargs)
                with (owner.audit_dir/'actual_optimizer_steps.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps({'step':len(self.state) and max(int(z['step']) for z in self.state.values()),'modules':gradients})+'\n')
                return result
        def optimizer(params,lr,**kwargs):
            params=list(params);named=list(self.model_.named_parameters())
            prefixes=getattr(self,'body_trainable_prefixes',('icl_predictor.',))
            fixed_names=set(getattr(self,'fixed_body_parameter_names',()))
            assert all(v.requires_grad==(k.startswith(prefixes) and k not in fixed_names) for k,v in named)
            total=sum(v.numel() for k,v in named if v.requires_grad);assert sum(v.numel() for v in params)==total
            dump(self.audit_dir/'optimizer_audit.json',{'lr':lr,'all12_original_ICL_blocks_trainable':all(v.requires_grad for k,v in named if k.startswith('icl_predictor.')),'trainable_parameters':total,
                'modules':{m:sum(v.numel() for k,v in named if k.startswith(m+'.')) for m in ['col_embedder','row_interactor','icl_predictor']},
                'trainable_names':[k for k,v in named if v.requires_grad],'fixed_nontrainable_parameters':sorted(fixed_names)})
            new_lr=getattr(self,'new_body_learning_rate',None)
            if new_lr is not None:
                new_names=set(self.initial_new_body);new=[v for k,v in named if k in new_names];old=[v for k,v in named if v.requires_grad and k not in new_names]
                opt=AuditedAdamW([{'params':old,'lr':lr},{'params':new,'lr':new_lr}],lr=lr,**kwargs)
            else:opt=AuditedAdamW(params,lr=lr,**kwargs)
            self.audit_optimizer=opt;return opt
        def iterator(encoded,labels,**kw):
            if hasattr(self,'iter_task_batches'):
                yield from self.iter_task_batches(encoded,labels,kw,orig_iterator)
                return
            assert kw.get('world_size',1)==1 and len(encoded)==len(self.fit_ids)
            crop=np.asarray(self._X_encoder_.transform(self.crop_raw),dtype=encoded.dtype)
            selected=np.random.default_rng(kw['epoch_seed']+100000).random(len(encoded))<.5
            mixed=np.where(selected[:,None],crop,encoded)
            chunks=ft_data._chunk_indices(len(labels),max_chunk_size=kw['max_chunk_size'],rng=np.random.default_rng(kw['epoch_seed']),min_chunk_size=kw.get('min_chunk_size',50))
            for k,batch in enumerate(orig_iterator(mixed,labels,**kw)):
                ix=chunks[k];qsize=max(1,int(len(ix)*kw['query_ratio']),int(labels[ix].max())+1)
                ci,qi=ft_data._split_ctx_query(labels[ix],query_size=qsize,seed=kw['epoch_seed']+k*7919,stratify=True)
                assert np.array_equal(batch.y_train[0].numpy(),labels[ix[ci]]) and np.array_equal(batch.y_query[0].numpy(),labels[ix[qi]])
                ctx=self.fit_ids[ix[ci]];qry=self.fit_ids[ix[qi]];assert not set(ctx)&set(qry)
                rec={'epoch_seed':kw['epoch_seed'],'chunk':k,'context_ids':ctx.tolist(),'query_ids':qry.tolist(),
                    'crop_ids':self.fit_ids[ix[selected[ix]]].tolist(),'one_version_per_boat':True,
                    'max_chunk_size':kw['max_chunk_size'],'query_ratio':kw['query_ratio'],
                    'split_method':'singleton-safe reserved context' if getattr(self,'safe_episode_split',False) else 'original stratified',
                    'actual_batch_X_sha256':hashlib.sha256(batch.X.numpy().tobytes()).hexdigest()}
                with (self.audit_dir/'actual_training_batches.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
                yield batch
        if getattr(self,'safe_episode_split',False):
            from fresh_safe_context_split import safe_context_query_split
            ft_data._split_ctx_query=safe_context_query_split
        ft_base.iter_epoch_meta_batches=iterator;ft_base.AdamW=optimizer
        try:return super()._fit_impl(X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:
            ft_base.iter_epoch_meta_batches=orig_iterator;ft_base.AdamW=orig_optimizer;ft_data._split_ctx_query=original_split

def train_wide(rd,train,crop,queries,s,reference,adapter_type=None,round_number=40,train_kwargs=None):
    ad=rd/'wide_body';ad.mkdir();fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy()
    seed=SEED+round_number*100;torch.manual_seed(seed);np.random.seed(seed);torch.cuda.manual_seed_all(seed);torch.set_num_threads(4)
    training_args=dict(epochs=8,learning_rate=1e-5,max_data_size=256,finetune_ctx_query_ratio=.25,
        n_estimators_finetune=1,n_estimators_validation=4,n_estimators_inference=4,
        freeze_col=True,freeze_row=True,freeze_icl=False,class_shuffle_method='none',early_stopping=True,patience=3,min_delta=0,
        time_limit=900,save_interval=0,model_path=CHECKPOINT,allow_auto_download=False,device='cuda',random_state=seed,verbose=False,eval_metric='accuracy',
        extra_classifier_kwargs={'batch_size':1,'kv_cache':'repr','use_amp':True,'use_fa3':False,'n_jobs':4})
    training_args.update(train_kwargs or{});m=(adapter_type or WideBodyAdapter)(**training_args)
    m.fit_ids=s.index[fit].to_numpy();m.crop_raw=crop;m.audit_dir=ad;m.raw_queries=queries;m.tune_mask=tu;m.loss_forward_calls=0;m.finite_loss_calls=0;m.zero_stop=False
    m.tune_reference={k:(v[tu] if k in ['joint','pair','prediction'] else v) for k,v in reference.items()}
    begun=now()
    try:m.fit(train,s.loc[fit,'y'].to_numpy(),X_val=queries['full'][tu],y_val=sub.y.to_numpy()[tu],output_dir=ad/'checkpoint')
    except Exception as error:
        failure={'error_type':type(error).__name__,'error':str(error),'loss_forward_calls':m.loss_forward_calls,'finite_loss_calls':m.finite_loss_calls,'audit_only_never_resume_failed_weights':True}
        try:
            if hasattr(m,'model_'):
                torch.save({'state_dict':m.model_.state_dict(),'optimizer':m.audit_optimizer.state_dict() if hasattr(m,'audit_optimizer') else None},ad/'failed_training_state_audit_only.pt')
        except Exception as save_error:failure['failure_checkpoint_save_error']=str(save_error)
        dump(ad/'failed_training_audit.json',failure);raise
    original=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict']
    saved=torch.load(ad/'checkpoint'/'best.ckpt',map_location='cpu',weights_only=False)
    events=[json.loads(line) for line in (ad/'validation_events.jsonl').read_text(encoding='utf-8').splitlines()]
    eligible=[e for e in events if e['eligible_trained_checkpoint']]
    selected=max(eligible,key=lambda e:(e['positive_choice']['TUNE_correct'],e['positive_choice']['TUNE_macro']))
    assert weight_digest(saved['state_dict'])==selected['weights_sha256']
    if getattr(m,'inference_only_checkpoint',False):
        saved=save_selected_inference_checkpoint(ad/'checkpoint'/'best.ckpt',saved,selected)
    changed={};new_changed=[]
    new_initial=getattr(m,'initial_new_body',{})
    for k,v in saved['state_dict'].items():
        z=changed.setdefault(k.split('.')[0],{'changed_tensors':[],'changed_parameters':0,'total_parameters':0})
        z['total_parameters']+=v.numel()
        if k in original:
            if not torch.equal(v,original[k]):z['changed_tensors'].append(k);z['changed_parameters']+=v.numel()
        else:
            assert k in new_initial
            if not torch.equal(v,new_initial[k]):new_changed.append(k)
    allowed=getattr(m,'expected_changed_original_modules',('icl_predictor',))
    assert all(bool(z['changed_parameters'])==(k in allowed) for k,z in changed.items())
    steps=[json.loads(line) for line in (ad/'actual_optimizer_steps.jsonl').read_text(encoding='utf-8').splitlines()]
    assert m.loss_forward_calls==m.finite_loss_calls>0 and len(steps)>0
    audit={'started':begun,'finished':now(),'original_checkpoint_sha256':sha(CHECKPOINT),'selected_checkpoint_sha256':sha(ad/'checkpoint'/'best.ckpt'),
        'modules':changed,'all12_original_ICL_blocks_trainable':all(v.requires_grad for k,v in m.model_.named_parameters() if k.startswith('icl_predictor.')),'trainable_parameter_fraction':sum(v.numel() for k,v in original.items() if dict(m.model_.named_parameters())[k].requires_grad)/sum(v.numel() for v in original.values()),'selected_epoch':selected['epoch'],'selected_optimizer_steps':selected['optimizer_steps'],
        'actual_optimizer_steps':len(steps),'actual_loss_forwards':m.loss_forward_calls,'finite_loss_forwards':m.finite_loss_calls,
        'selected_weights_sha256':selected['weights_sha256'],'epoch0_excluded':True,'zero_weight_stop_triggered':m.zero_stop,
        'checkpoint_type':saved.get('checkpoint_type','legacy_training_metadata'),'resume_training_supported':saved.get('resume_training_supported',True),
        'round_number':round_number,'new_body_changed_tensors':new_changed,'new_body_parameters':sum(v.numel() for v in new_initial.values()),
        'FIT_ids_sha256':hashlib.sha256(m.fit_ids.tobytes()).hexdigest(),'TUNE_ids_sha256':hashlib.sha256(sub.index[tu].to_numpy().tobytes()).hexdigest()}
    dump(ad/'weight_audit.json',audit);del saved,original;gc.collect();pred={}
    import joblib
    joblib.dump(m._X_encoder_,ad/'fresh_outer_encoder.joblib')
    np.savez(ad/'inference_inputs.npz',FIT_ids=s.index[fit].to_numpy(),query_ids=sub.index.to_numpy(),
        encoded_train=np.asarray(m._X_encoder_.transform(train),dtype=np.float64),
        **{f'encoded_{v}':np.asarray(m._X_encoder_.transform(x),dtype=np.float64) for v,x in queries.items()})
    for v in VIEWS:
        pred[v]=np.concatenate([m.predict_view_proba(v,start=j,stop=min(j+1000,len(queries[v])))
            if hasattr(m,'predict_view_proba') else m.predict_proba(queries[v][j:j+1000])
            for j in range(0,len(sub),1000)])
        np.save(ad/f'adapted_head_{v}.npy',pred[v])
    del m;gc.collect();torch.cuda.empty_cache()
    print('WIDE_BODY_TRAINED',json.dumps(audit),flush=True)
    return pred,audit
