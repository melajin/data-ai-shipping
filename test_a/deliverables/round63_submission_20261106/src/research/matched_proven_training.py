"""Develop41's internal FFN substitution and49's broad public-anchored learning."""
from full_context_body_training import FullContextBodyAdapter
from fresh_representation_adaptation import RepresentationAdapter
from fresh_wide_training import WideBodyAdapter
from fresh_fixed_inference import attach_fixed_inference
from tabicl_gated_ffn_body import attach_gated_ffn,load_gated_body
from matched_proven_cache import create_matched_caches,task_specs
from encoded_public_cache import replay_bundle,frozen_encoder_sha
from fresh_deployed_reference import aggregate_deployed
from fresh_architecture_adapter import weight_digest
from fresh_rounds import *
import tabicl._finetune.base as ft_base
import tabicl._finetune.data as fd
from torch.nn import functional as F
import copy

GAMMAS=[0.,.1,.25,.5,.75,1.]

def choose_matched(ref,joint,pair,y,tu):
    choices=[];outputs={};yt=y if len(y)==int(tu.sum()) else y[tu]
    for g in GAMMAS:
        j=(1-g)*ref['joint']+g*joint;p=(1-g)*ref['pair']+g*pair
        score=(1-ref['alpha'])*np.log(np.clip(j,1e-6,1))+ref['alpha']*np.log(np.clip(p,1e-6,1)).sum(2)/3+np.log(ref['weights']);pr=score.argmax(1);m=metrics(yt,pr[tu])
        choices.append({'gamma':g,'TUNE_correct':int((pr[tu]==yt).sum()),'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']});outputs[g]=(pr,score,j,p)
    best=max(choices[1:],key=lambda z:(z['TUNE_correct'],z['TUNE_macro'],-z['gamma']))
    return best,outputs[best['gamma']],choices,outputs[0.]

def replay_deployment(model,rd,out_dir,verify_public=False):
    out_dir.mkdir(exist_ok=True);calls=[json.loads(l) for l in (rd/'fresh_fit_calls.jsonl').read_text().splitlines()];outputs={};records=[]
    encoder_digest=frozen_encoder_sha(model)
    for task in task_specs(calls):
        path=rd/'encoded_public_deployment'/f'task_{task["index"]:02}.pt';bundle=torch.load(path,map_location='cpu',weights_only=False);q=replay_bundle(model,bundle,verify_public_outputs=verify_public,frozen_encoder_digest=encoder_digest);outputs[task['name']]=q;np.save(out_dir/(task['name']+'.npy'),q);records.append({**task,'encoded_deployment_sha256':sha(path),'native_ICL_calls':len(bundle['calls']),'public_output_bitwise_verified':verify_public});del bundle
    assert frozen_encoder_sha(model)==encoder_digest
    policy=json.loads((rd/'fresh_reference_policy_full.json').read_text());j,p=aggregate_deployed(outputs,policy);np.save(out_dir/'joint.npy',j);np.save(out_dir/'pair.npy',p);dump(out_dir/'cached_deployment_audit.json',{'tasks':records,'frozen_public_col_row_yencoder':True,'body_weight_sha256':weight_digest(model.state_dict()),'no_new_preprocessor_fit_during_ICL_replay':True});return j,p

class MatchedProvenBodyAdapter(FullContextBodyAdapter):
    body_trainable_prefixes=('icl_predictor.',)
    expected_changed_original_modules=('icl_predictor',)
    new_body_learning_rate=3e-4

    def fit(self,X,y,**kwargs):
        # This diagnostic head uses compact150 and the production reference seed.
        # The final 20-task classifier is evaluated separately by replay_deployment.
        self.compact_fit_features=np.asfortranarray(np.asarray(X,dtype=np.float32)[:,:150])
        self.raw_feature_count=np.asarray(X).shape[1]
        self.compact_fit_labels=np.asarray(y).copy()
        self.__dict__.pop('compact_estimator_',None)
        self.__dict__.pop('final_cached_heads',None)
        return super().fit(X,y,**kwargs)

    def _set_training_mode(self,training):
        if training:
            self.__dict__.pop('compact_estimator_',None)
            self.__dict__.pop('final_cached_heads',None)
        return super()._set_training_mode(training)

    def _load_pretrained(self,device):
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            RepresentationAdapter._load_pretrained(self,device);self.teacher_icl=copy.deepcopy(self.model_.icl_predictor).cpu()
            for p in self.teacher_icl.parameters():p.requires_grad_(False)
            self.model_=attach_gated_ffn(self.model_);self.initial_new_body={k:v.detach().cpu().clone() for k,v in self.model_.state_dict().items() if '.ffn_gate.' in k};torch.save(self.initial_new_body,self.audit_dir/'initial_new_body.pt')
        else:self.model_,self.model_config_=load_gated_body(self.model_path,device);self.model_path_=Path(self.model_path)
        self.fixed_body_parameter_names=tuple(k for k,v in self.model_.named_parameters() if k.startswith('icl_predictor.y_encoder.'))+('row_interactor.tf_row.rope.freqs',)
        for module in self.model_.modules():
            if hasattr(module,'recompute'):module.recompute=True
        self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True;attach_fixed_inference(self.model_)

    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        original=ft_base.count_chunks;ft_base.count_chunks=lambda *a,**kw:40
        try:return WideBodyAdapter._fit_impl(self,X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:ft_base.count_chunks=original

    def iter_task_batches(self,encoded,labels,kw,iterator):
        if not hasattr(self,'matched_records'):self.matched_records=create_matched_caches(self,encoded,labels)
        epoch=kw['epoch_seed']-self.random_state;order=np.random.default_rng(kw['epoch_seed']+111).permutation(len(self.matched_records))
        for index in order:
            rec=self.matched_records[index];data=torch.load(self.audit_dir/rec['cache'],map_location='cpu',weights_only=False);K=rec['classes'];seed=self.random_state+self.loss_forward_calls*1009+761;shift=int(np.random.default_rng(seed).integers(1,K));perm=torch.roll(torch.arange(K),shifts=shift);methods=[epoch%2,1-epoch%2]
            X=torch.stack([data['representations'][methods[0],0],data['representations'][methods[1],shift]]).float();teacher=torch.stack([data['teacher_logits'][methods[0],0],data['teacher_logits'][methods[1],shift]]);cy=data['context_labels'];qy=data['query_targets'];batch=fd.MetaBatch(X=X,y_train=torch.stack([cy,perm[cy.long()].float()]),y_query=torch.stack([qy,perm[qy]]),train_size=len(cy),y_scaler_mean=None,y_scaler_std=None)
            actual={**rec,'epoch':epoch,'epoch_seed':kw['epoch_seed'],'cache_index':int(index),'normalization_view_indices':methods,'permutation_seed':seed,'cyclic_shift':shift,'actual_batch_X_sha256':hashlib.sha256(X.numpy().tobytes()).hexdigest(),'selected_teacher_logits_sha256':hashlib.sha256(teacher.numpy().tobytes()).hexdigest()}
            with (self.audit_dir/'actual_training_batches.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(actual)+'\n')
            self.current_training_record=actual;self.current_teacher_logits=teacher;yield batch

    def _compute_batch_loss(self,batch,model):
        K=self.current_training_record['classes'];perm=torch.roll(torch.arange(K,device=batch.X.device),shifts=self.current_training_record['cyclic_shift']);logits=model.icl_predictor(batch.X.clone(),y_train=batch.y_train.float())[...,:K].float();teacher=self.current_teacher_logits.to(batch.X.device)
        ce=.5*(F.cross_entropy(logits[0],batch.y_query[0])+F.cross_entropy(logits[1],batch.y_query[1]));kl=F.kl_div(F.log_softmax(logits.reshape(-1,K)/2.,dim=-1),F.softmax(teacher.reshape(-1,K)/2.,dim=-1),reduction='batchmean')*4.;p0=logits[0].softmax(-1);p1=logits[1].index_select(-1,perm).softmax(-1);lm=((p0+p1)*.5).clamp_min(1e-12).log();js=.5*(F.kl_div(lm,p0,reduction='batchmean')+F.kl_div(lm,p1,reduction='batchmean'));loss=ce+kl+js
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));path=self.audit_dir/f'matched_loss_{self.loss_forward_calls:03}.npz';np.savez(path,logits=logits.detach().cpu().numpy(),teacher_logits=teacher.cpu().numpy(),targets=batch.y_query.cpu().numpy(),context_labels=batch.y_train.cpu().numpy(),permutation=perm.cpu().numpy())
        rec={'index':self.loss_forward_calls,'cross_entropy':float(ce.detach()),'public_teacher_T2_KL':float(kl.detach()),'normalization_and_label_JS':float(js.detach()),'total_loss':float(loss.detach()),'loss_tensors_sha256':sha(path)}
        with (self.audit_dir/'matched_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
        return loss

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        vi=getattr(self,'validation_index',0);self.validation_index=vi+1;rd=self.audit_dir.parent;dd=self.audit_dir/f'deployment_validation_{vi:02}';j,p=replay_deployment(self.model_,rd,dd,verify_public=vi==0)
        cfg=json.loads((rd/'fresh_reference_policy_full.json').read_text());ref={'joint':np.load(rd/'fresh_reference_joint_full.npy'),'pair':np.load(rd/'fresh_reference_pair_full.npy'),'alpha':cfg['alpha'],'weights':np.array(cfg['weights'])};best,out,candidates,zero=choose_matched(ref,j,p,y_val,self.tune_mask)
        steps=max([int(z['step']) for z in self.audit_optimizer.state.values() if 'step' in z],default=0)
        if steps:self.best_positive_correct_so_far=max(getattr(self,'best_positive_correct_so_far',-1),best['TUNE_correct'])
        stop=bool(steps and candidates[0]['TUNE_correct']>self.best_positive_correct_so_far)
        event={'epoch':vi,'optimizer_steps':steps,'loss_forward_calls':self.loss_forward_calls,'weights_sha256':weight_digest(self.model_.state_dict()),'positive_choice':best,'candidates':candidates,'zero_strictly_better':stop,'eligible_trained_checkpoint':steps>0,'best_positive_correct_so_far':getattr(self,'best_positive_correct_so_far',None),'deployment_tasks':20,'fixed_reference_policy':cfg}
        if vi==0:
            assert np.array_equal(j,ref['joint']) and np.array_equal(p,ref['pair'])
            for v in VIEWS:
                path=rd/'encoded_public_deployment'/('task_00.pt' if v=='full' else f'short_{v}.pt');bundle=torch.load(path,map_location='cpu',weights_only=False);q=np.concatenate([g['public_probability'] for g in bundle['groups']]);np.save(self.audit_dir/f'unadapted_head_{v}.npy',q)
        elif stop:self.time_limit=0;self.zero_stop=True
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        print('MATCHED_PROVEN_BODY_VALIDATION',json.dumps({k:v for k,v in event.items() if k not in ['candidates','fixed_reference_policy']}),flush=True)
        return ft_base.ValidationMetrics(primary=(best['TUNE_correct']+best['TUNE_macro']*1e-4)/len(y_val) if steps else -1.)

    def predict_view_proba(self,view,*,start=0,stop=None):
        """Read an explicit saved diagnostic view; no implicit call counter.

        Use predict_proba for arbitrary input. These cached queries are the
        declared round's compact150 diagnostics, not a generic input cache.
        """
        if view not in VIEWS:raise ValueError(f'Unknown diagnostic view: {view}')
        n=len(self.raw_queries[view]);stop=n if stop is None else stop
        if not 0<=start<=stop<=n:raise ValueError('Diagnostic query range is out of bounds')
        if not hasattr(self,'final_cached_heads'):self.final_cached_heads={}
        if view not in self.final_cached_heads:
            path=self.audit_dir.parent/'encoded_public_deployment'/('task_00.pt' if view=='full' else f'short_{view}.pt')
            bundle=torch.load(path,map_location='cpu',weights_only=False)
            self.final_cached_heads[view]=replay_bundle(self.model_,bundle)
        return self.final_cached_heads[view][start:stop].copy()

    def predict_proba(self,X):
        """Run the trained compact150 diagnostic head on the supplied rows.

        Accept compact150 or this adapter's full raw feature schema. Repeated
        calls, arbitrary row order and arbitrary chunk sizes are supported.
        This is the head diagnostic; final 20-task probabilities use the fixed
        deployment policy and replay_deployment.
        """
        raw=np.asarray(X,dtype=np.float32)
        if raw.ndim!=2 or raw.shape[1] not in (150,self.raw_feature_count):
            raise ValueError(f'Expected 150 or {self.raw_feature_count} feature columns')
        if not hasattr(self,'compact_estimator_'):
            import experiment
            inner=experiment.model(SEED+910,4)
            inner.model_=self.model_;inner.model_config_=self.model_config_;inner.model_path_=self.model_path_
            inner._load_model=lambda:None
            context=np.asfortranarray(np.where(np.isfinite(self.compact_fit_features),self.compact_fit_features,np.nan))
            inner.fit(context,self.compact_fit_labels)
            self.compact_estimator_=inner
        query=np.asfortranarray(np.where(np.isfinite(raw[:,:150]),raw[:,:150],np.nan))
        return self.compact_estimator_.predict_proba(query)

    @property
    def classes_(self):
        from sklearn.utils.validation import check_is_fitted
        check_is_fitted(self,'compact_fit_labels')
        return np.unique(self.compact_fit_labels)

    def predict(self,X):
        """Use the same diagnostic head and class order as predict_proba."""
        return self.classes_[self.predict_proba(X).argmax(axis=1)]
