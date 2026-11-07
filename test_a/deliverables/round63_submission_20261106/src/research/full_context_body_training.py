"""Broad ICL tuning with entire FIT-fold contexts and cached frozen encoders."""
from fresh_record_body_training import RecordLatentBodyAdapter
from fresh_wide_training import WideBodyAdapter
from full_context_body_cache import create_caches
from full_context_components import choose_full_context
from fresh_architecture_adapter import weight_digest
from fresh_rounds import *
from torch.nn import functional as F
import tabicl._finetune.base as ft_base
import tabicl._finetune.data as fd

class FullContextBodyAdapter(RecordLatentBodyAdapter):
    body_trainable_prefixes=('icl_predictor.',)
    expected_changed_original_modules=('icl_predictor',)
    new_body_learning_rate=None
    validation_label='FULL_COHORT_CONTEXT_VALIDATION'

    def _load_pretrained(self,device):
        super()._load_pretrained(device)
        for module in self.model_.modules():
            if hasattr(module,'recompute'):module.recompute=True
        self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True

    def _set_training_mode(self,training):
        if training:self.model_.clear_cache();gc.collect();torch.cuda.empty_cache()
        return super()._set_training_mode(training)

    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        original=ft_base.count_chunks;ft_base.count_chunks=lambda *a,**kw:28
        try:return WideBodyAdapter._fit_impl(self,X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:ft_base.count_chunks=original

    def iter_task_batches(self,encoded,labels,kw,iterator):
        if not hasattr(self,'full_context_records'):
            self.full_context_records=create_caches(self,encoded,labels)
        for record in self.full_context_records:
            cache=torch.load(self.audit_dir/record['cache'],map_location='cpu',weights_only=False);classes=record['classes']
            seed=int(self.random_state)+self.loss_forward_calls*1009+761;shift=int(np.random.default_rng(seed).integers(1,classes));perm=torch.roll(torch.arange(classes),shifts=shift)
            labels=cache['context_labels'];target=cache['query_targets'];X=cache['representations'][[0,shift]].float()
            batch=fd.MetaBatch(X=X,y_train=torch.stack([labels,perm[labels.long()].float()]),y_query=torch.stack([target,perm[target]]),train_size=len(labels),y_scaler_mean=None,y_scaler_std=None)
            rec={**record,'epoch_seed':kw['epoch_seed'],'permutation_seed':seed,'cyclic_shift':shift,'actual_batch_X_sha256':hashlib.sha256(X.numpy().tobytes()).hexdigest(),'representation_cache_reused_only_within_current_round':True}
            with (self.audit_dir/'actual_training_batches.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
            self.current_training_record=rec;yield batch

    def _compute_batch_loss(self,batch,model):
        assert model is self.model_ and batch.X.shape[0]==2
        assert all(not p.requires_grad for module in [model.col_embedder,model.row_interactor] for p in module.parameters())
        classes=int(batch.y_train.max())+1;shift=self.current_training_record['cyclic_shift'];perm=torch.roll(torch.arange(classes,device=batch.X.device),shifts=shift)
        logits=model.icl_predictor(batch.X.clone(),y_train=batch.y_train.float())[...,:classes].float()
        ce=.5*(F.cross_entropy(logits[0],batch.y_query[0])+F.cross_entropy(logits[1],batch.y_query[1]));p0=logits[0].softmax(-1);p1=logits[1].index_select(-1,perm).softmax(-1);lm=((p0+p1)*.5).clamp_min(1e-12).log();js=.5*(F.kl_div(lm,p0,reduction='batchmean')+F.kl_div(lm,p1,reduction='batchmean'));loss=ce+.25*js
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));path=self.audit_dir/f'full_context_loss_{self.loss_forward_calls:03}.npz'
        np.savez(path,logits=logits.detach().cpu().numpy(),targets=batch.y_query.cpu().numpy(),context_labels=batch.y_train.cpu().numpy(),permutation=perm.cpu().numpy())
        rec={'index':self.loss_forward_calls,'cross_entropy':float(ce.detach()),'permutation_JS':float(js.detach()),'total_loss':float(loss.detach()),'loss_tensors_sha256':sha(path),'context_rows':batch.train_size,'query_rows':batch.y_query.shape[1],'no_teacher':True,'peak_allocated_GPU_bytes':torch.cuda.max_memory_allocated()}
        with (self.audit_dir/'full_context_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
        return loss

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        from fresh_deployed_reference import prepare_deployment,infer_one,infer_deployed
        from fresh_geometry_reference import read_components
        vi=getattr(self,'validation_index',0);self.validation_index=vi+1;rd=self.audit_dir.parent;dd=self.audit_dir/f'deployment_validation_{vi:02}';dd.mkdir()
        query=np.asarray(self._X_encoder_.transform(self.raw_queries['full']),dtype=np.float64);assert np.array_equal(query[self.tune_mask],X_val,equal_nan=True)
        if vi==0:
            specs=prepare_deployment(rd);assert len(specs)==13;probe,classes=infer_one(self,specs[0]);assert classes==[0,1,2,3] and np.array_equal(probe,np.load(rd/'compact_full_head.npy'));np.save(dd/'initial_compact_probe.npy',probe);hashes={}
            for spec in specs:
                path=rd/(f'{spec["arm"]}_full_{spec["task"]}.npy' if spec['arm']=='compact' else spec['task']+'_full.npy');shutil.copy2(path,dd/(spec['name']+'.npy'));hashes[spec['name']]=sha(path)
            dump(dd/'same_round_initial_control_reuse.json',{'only_current_round_reference_components_reused':True,'actual_fresh_reference_fits':13,'actual_initial_compact_probe_fits':1,'compact_probe_probability_replay_exact':True,'source_component_sha256':hashes,'original_fit_log_sha256':sha(rd/'fresh_fit_calls.jsonl')})
        else:infer_deployed(self,rd,dd)
        reference={'joint':np.load(rd/'fresh_reference_joint_full.npy'),'pair':np.load(rd/'fresh_reference_pair_full.npy')};best,out,candidates,zero=choose_full_context(reference,read_components(dd),y_val,self.tune_mask);np.save(dd/'joint.npy',out[4]);np.save(dd/'pair.npy',out[5])
        steps=max([int(z['step']) for z in self.audit_optimizer.state.values() if 'step' in z],default=0)
        if steps:self.best_positive_correct_so_far=max(getattr(self,'best_positive_correct_so_far',-1),best['TUNE_correct'])
        stop=bool(steps and zero['TUNE_correct']>self.best_positive_correct_so_far)
        event={'epoch':vi,'optimizer_steps':steps,'loss_forward_calls':self.loss_forward_calls,'weights_sha256':weight_digest(self.model_.state_dict()),'positive_choice':best,'zero_body_choice':zero,'candidates':candidates,'zero_strictly_better':stop,'eligible_trained_checkpoint':steps>0,'best_positive_correct_so_far':getattr(self,'best_positive_correct_so_far',None)}
        if vi==0:
            inner.fit(X_train,y_train)
            for v,raw in self.raw_queries.items():
                q=np.asarray(self._X_encoder_.transform(raw),dtype=np.float64);p=np.concatenate([inner.predict_proba(q[j:j+1000]) for j in range(0,len(q),1000)]);np.save(self.audit_dir/f'unadapted_head_{v}.npy',p)
        elif stop:self.time_limit=0;self.zero_stop=True
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        print(self.validation_label,json.dumps({k:v for k,v in event.items() if k!='candidates'}),flush=True)
        return ft_base.ValidationMetrics(primary=(best['TUNE_correct']+best['TUNE_macro']*1e-4)/len(y_val) if steps else -1.)
