"""Column+ICL broad optimization with context-frequency label injection and a full public teacher."""
from fresh_permutation_training import PermutationDeployedAdapter
from fresh_representation_adaptation import RepresentationAdapter
from fresh_fixed_inference import attach_fixed_inference
from fresh_architecture_adapter import weight_digest
from tabicl_frequency_conditioner import attach_frequency_conditioner,new_frequency_state,load_frequency_body
from fresh_rounds import *
from torch.nn import functional as F
import copy
import tabicl._finetune.data as fd
from fresh_joint_pair_components import official_tasks,task_rows
from fresh_stratified_chunks import stratified_chunks

class FrequencyBodyAdapter(PermutationDeployedAdapter):
    body_trainable_prefixes=('col_embedder.','icl_predictor.')
    expected_changed_original_modules=('col_embedder','icl_predictor')
    new_body_learning_rate=3e-4
    validation_label='FREQUENCY_COLUMN_BODY_VALIDATION'
    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        # These seven fixed-cohort task sizes are distinct;the generic iterator
        # uses the same scoped function for its audit and actual data construction.
        task_labels={len(task_rows(np.asarray(y),pair)[0]):task_rows(np.asarray(y),pair)[1] for pair in official_tasks()}
        assert len(task_labels)==7
        original=fd._chunk_indices
        def chunks(n_samples,max_chunk_size,rng,min_chunk_size=50):
            assert n_samples in task_labels
            return stratified_chunks(task_labels[n_samples],max_chunk_size,rng,min_chunk_size)
        fd._chunk_indices=chunks
        try:return super()._fit_impl(X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:fd._chunk_indices=original
    def initial_control_metadata(self):
        return {'initial_body_public_equivalence_by_zero_column_frequency_gate':True,'all_new_gate_weights_zero':all(torch.count_nonzero(v)==0 for v in self.initial_new_body.values()),'new_gate_multiplier_exactly_one':True}

    def _load_pretrained(self,device):
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            RepresentationAdapter._load_pretrained(self,device)
            self.teacher_model=copy.deepcopy(self.model_)
            for p in self.teacher_model.parameters():p.requires_grad_(False)
            self.teacher_initial_sha=weight_digest(self.teacher_model.state_dict())
            dump(self.audit_dir/'teacher_initialization.json',{'public_checkpoint_sha256':sha(CHECKPOINT),'public_full_body_state_sha256':self.teacher_initial_sha,'all_teacher_parameters_frozen':True,'teacher_not_in_optimizer':True,'temperature':2.,'KL_coefficient':1.,'teacher_uses_original_public_column_row_and_ICL':True})
            self.model_=attach_frequency_conditioner(self.model_);self.initial_new_body=new_frequency_state(self.model_);torch.save(self.initial_new_body,self.audit_dir/'initial_new_body.pt')
        else:self.model_,self.model_config_=load_frequency_body(self.model_path,device);self.model_path_=Path(self.model_path)
        for module in self.model_.modules():
            if hasattr(module,'recompute'):module.recompute=True
        self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True;attach_fixed_inference(self.model_)

    def _compute_batch_loss(self,batch,model):
        assert model is self.model_ and batch.X.shape[0]==1 and all(not p.requires_grad for p in model.row_interactor.parameters())
        assert any(p.requires_grad for p in model.col_embedder.parameters())
        classes=int(batch.y_train.max())+1;assert classes>=2
        seed=int(self.random_state)+self.loss_forward_calls*1009+761;shift=int(np.random.default_rng(seed).integers(1,classes));perm=torch.roll(torch.arange(classes,device=batch.X.device),shifts=shift)
        context=torch.cat([batch.y_train,perm[batch.y_train.long()].float()],dim=0);y0=batch.y_query[0].long();targets=torch.stack([y0,perm[y0]]);x=batch.X.repeat(2,1,1)
        self.teacher_model.to(batch.X.device).train()
        with torch.no_grad():teacher=self.teacher_model(x,context.float())[...,:classes].float()
        # Row parameters stay fixed,but gradients must pass through it to columns.
        logits=model(x,context.float())[...,:classes].float()
        ce=.5*(F.cross_entropy(logits[0],targets[0])+F.cross_entropy(logits[1],targets[1]));a=logits.reshape(-1,classes);b=teacher.reshape(-1,classes)
        kl=F.kl_div(F.log_softmax(a/2.,dim=-1),F.softmax(b/2.,dim=-1),reduction='batchmean')*4.
        p0=logits[0].softmax(-1);p1=logits[1].index_select(-1,perm).softmax(-1);lm=((p0+p1)*.5).clamp_min(1e-12).log();js=.5*(F.kl_div(lm,p0,reduction='batchmean')+F.kl_div(lm,p1,reduction='batchmean'));loss=ce+kl+js
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));index=self.loss_forward_calls;assert weight_digest(self.teacher_model.state_dict())==self.teacher_initial_sha
        np.savez(self.audit_dir/f'anchored_batch_{index:03}.npz',teacher_logits=b.detach().cpu().numpy(),student_logits=a.detach().cpu().numpy(),targets=targets.reshape(-1).cpu().numpy(),context_labels=context.cpu().numpy(),original_context_labels=batch.y_train.cpu().numpy(),original_query_targets=y0.cpu().numpy(),permutation=perm.cpu().numpy())
        rec={'index':index,'paired_label_views':2,'target_aware_encoders_evaluated_for_each_label_view':True,'teacher_public_weights_unchanged':True,'teacher_is_full_original_public_model':True,'student_column_and_ICL_gradient_path':True,
            'permutation_seed':seed,'cyclic_shift':shift,'cross_entropy':float(ce.detach()),'temperature_scaled_KL':float(kl.detach()),'permutation_JS':float(js.detach()),'total_loss':float(loss.detach()),
            'batch_X_sha256':hashlib.sha256(batch.X.detach().cpu().numpy().tobytes()).hexdigest(),'saved_batch_sha256':sha(self.audit_dir/f'anchored_batch_{index:03}.npz')}
        with (self.audit_dir/'anchored_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
        return loss
