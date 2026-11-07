"""Selected decoder replacement,broad last6ICL tuning,and matched whole-algorithm deployment."""
from fresh_joint_pair_training import JointPairBodyAdapter
from fresh_anchored_training import AnchoredBodyAdapter
from fresh_deployed_reference import prepare_deployment,infer_one,infer_deployed,choose_deployed
from tabicl_gated_decoder_body import attach_gated_decoder,new_decoder_state,load_gated_decoder_body
from fresh_architecture_adapter import weight_digest
from fresh_fixed_inference import attach_fixed_inference
from fresh_rounds import *
import tabicl._finetune.base as ft_base

class GatedDeployedAdapter(JointPairBodyAdapter):
    body_trainable_prefixes=tuple(f'icl_predictor.tf_icl.blocks.{i}.' for i in range(6,12))+('icl_predictor.ln.','icl_predictor.decoder.')
    new_body_learning_rate=3e-4
    validation_label='GATED_DEPLOYED_BODY_VALIDATION'
    def initial_control_metadata(self):
        return {'all_new_gate_weights_zero':all(torch.count_nonzero(v)==0 for v in self.initial_new_body.values()),'new_gate_multiplier_exactly_one':True}
    def _load_pretrained(self,device):
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            # Capture public teacher before inserting the new decoder operation.
            AnchoredBodyAdapter._load_pretrained(self,device)
            self.model_=attach_gated_decoder(self.model_);self.initial_new_body=new_decoder_state(self.model_)
            torch.save(self.initial_new_body,self.audit_dir/'initial_new_body.pt')
        else:
            self.model_,self.model_config_=load_gated_decoder_body(self.model_path,device);self.model_path_=Path(self.model_path)
        for module in self.model_.modules():
            if hasattr(module,'recompute'):module.recompute=True
        self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True
        attach_fixed_inference(self.model_)

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        vi=getattr(self,'validation_index',0);self.validation_index=vi+1;rd=self.audit_dir.parent;dd=self.audit_dir/f'deployment_validation_{vi:02}';dd.mkdir()
        query=np.asarray(self._X_encoder_.transform(self.raw_queries['full']),dtype=np.float64);assert np.array_equal(query[self.tune_mask],X_val,equal_nan=True)
        if vi==0:
            specs=prepare_deployment(rd);probe,classes=infer_one(self,specs[0]);assert classes==[0,1,2,3] and np.array_equal(probe,np.load(rd/'compact_full_head.npy'))
            np.save(dd/'initial_compact_probe.npy',probe)
            joint=np.load(rd/'fresh_reference_joint_full.npy');pair=np.load(rd/'fresh_reference_pair_full.npy')
            np.save(dd/'joint.npy',joint);np.save(dd/'pair.npy',pair)
            control={'only_current_round_original_reference_outputs_reused':True,'current_round_fresh_reference_fits':len(specs),'actual_current_body_initial_compact_probe_fits':1,'compact_probe_probability_replay_exact':True,'no_claim_of_extra_initial_body_fits':True,'original_fit_log_sha256':sha(rd/'fresh_fit_calls.jsonl')}
            if len(specs)==20:control.update(only_current_round_fresh20_original_reference_outputs_reused=True,no_claim_of20extra_initial_body_fits=True)
            control.update(self.initial_control_metadata());dump(dd/'same_round_initial_control_reuse.json',control)
        else:joint,pair=infer_deployed(self,rd,dd)
        best,_,cand,zero_current=choose_deployed(self.tune_reference,joint[self.tune_mask],pair[self.tune_mask],y_val,np.ones(len(y_val),dtype=bool))
        steps=max([int(z['step']) for z in self.audit_optimizer.state.values() if 'step' in z],default=0)
        if steps:self.best_positive_correct_so_far=max(getattr(self,'best_positive_correct_so_far',-1),best['TUNE_correct'])
        zero=bool(steps and cand[0]['TUNE_correct']>self.best_positive_correct_so_far)
        event={'epoch':vi,'optimizer_steps':steps,'loss_forward_calls':self.loss_forward_calls,'weights_sha256':weight_digest(self.model_.state_dict()),'positive_choice':best,'candidates':cand,'zero_strictly_better':zero,'zero_better_than_current_epoch':zero_current,'eligible_trained_checkpoint':steps>0,'best_positive_correct_so_far':getattr(self,'best_positive_correct_so_far',None),'termination_comparator':'Best eligible positive checkpoint so far;not an inferior transient later epoch.'}
        if vi==0:
            inner.fit(X_train,y_train)
            for v,raw in self.raw_queries.items():
                q=np.asarray(self._X_encoder_.transform(raw),dtype=np.float64);op=np.concatenate([inner.predict_proba(q[j:j+1000]) for j in range(0,len(q),1000)])
                np.save(self.audit_dir/f'unadapted_head_{v}.npy',op)
        elif zero:self.time_limit=0;self.zero_stop=True
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        print(self.validation_label,json.dumps(event),flush=True)
        return ft_base.ValidationMetrics(primary=(best['TUNE_correct']+best['TUNE_macro']*1e-4)/len(y_val) if steps else -1.)
