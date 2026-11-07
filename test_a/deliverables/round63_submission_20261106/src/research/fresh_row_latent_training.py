"""Selected row aggregation replacement plus broad row/ICL optimization."""
from fresh_wide_training import WideBodyAdapter,choose_positive
from fresh_architecture_adapter import weight_digest
from tabicl_row_latents_body import attach_row_latents,new_row_state,load_row_latent_body
from fresh_rounds import *
import tabicl._finetune.base as ft_base

class RowLatentAdapter(WideBodyAdapter):
    body_trainable_prefixes=('row_interactor.','icl_predictor.')
    expected_changed_original_modules=('row_interactor','icl_predictor')
    fixed_body_parameter_names=('row_interactor.tf_row.rope.freqs',)
    safe_episode_split=True
    new_body_learning_rate=3e-4
    def _load_pretrained(self,device):
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            super()._load_pretrained(device);torch.manual_seed(self.random_state+1);torch.cuda.manual_seed_all(self.random_state+1)
            self.model_=attach_row_latents(self.model_);self.initial_new_body=new_row_state(self.model_)
            torch.save(self.initial_new_body,self.audit_dir/'initial_new_body.pt')
        else:
            self.model_,self.model_config_=load_row_latent_body(self.model_path,device);self.model_path_=Path(self.model_path)
        for module in self.model_.modules():
            if hasattr(module,'recompute'):module.recompute=True
        self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        inner.fit(X_train,y_train);encoded=np.asarray(self._X_encoder_.transform(self.raw_queries['full']),dtype=np.float64)
        assert np.array_equal(encoded[self.tune_mask],X_val,equal_nan=True)
        all_p=np.concatenate([inner.predict_proba(encoded[j:j+1000]) for j in range(0,len(encoded),1000)]);p=all_p[self.tune_mask]
        vi=getattr(self,'validation_index',0);self.validation_index=vi+1;np.save(self.audit_dir/f'validation_head_{vi:02}.npy',p)
        best,_,cand,zero_current=choose_positive(self.tune_reference,p,y_val,np.ones(len(y_val),dtype=bool))
        steps=max([int(z['step']) for z in self.audit_optimizer.state.values() if 'step' in z],default=0)
        if steps:self.best_positive_correct_so_far=max(getattr(self,'best_positive_correct_so_far',-1),best['TUNE_correct'])
        zero=bool(steps and cand[0]['TUNE_correct']>self.best_positive_correct_so_far)
        event={'epoch':vi,'optimizer_steps':steps,'loss_forward_calls':self.loss_forward_calls,'weights_sha256':weight_digest(self.model_.state_dict()),
            'positive_choice':best,'candidates':cand,'zero_strictly_better':zero,'zero_better_than_current_epoch':zero_current,'eligible_trained_checkpoint':steps>0,
            'best_positive_correct_so_far':getattr(self,'best_positive_correct_so_far',None),'termination_comparator':'Best eligible positive checkpoint so far;not an inferior transient later epoch.'}
        if vi==0:
            for v,raw in self.raw_queries.items():
                q=np.asarray(self._X_encoder_.transform(raw),dtype=np.float64)
                op=all_p if v=='full' else np.concatenate([inner.predict_proba(q[j:j+1000]) for j in range(0,len(q),1000)])
                np.save(self.audit_dir/f'unadapted_head_{v}.npy',op)
        elif zero:self.time_limit=0;self.zero_stop=True
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        print('ROW_LATENT_VALIDATION',json.dumps(event),flush=True)
        return ft_base.ValidationMetrics(primary=(best['TUNE_correct']+best['TUNE_macro']*1e-4)/len(y_val) if steps else -1.)
