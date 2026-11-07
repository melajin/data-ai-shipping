"""Broad originalICL learning with paired cyclic-label equivariance matching shift deployment."""
from fresh_gated_deployment_training import GatedDeployedAdapter
from fresh_anchored_training import AnchoredBodyAdapter
from fresh_fixed_inference import attach_fixed_inference
from fresh_architecture_adapter import weight_digest
from fresh_rounds import *
from torch.nn import functional as F

class PermutationDeployedAdapter(GatedDeployedAdapter):
    body_trainable_prefixes=('icl_predictor.',)
    new_body_learning_rate=None
    validation_label='PERMUTATION_DEPLOYED_BODY_VALIDATION'
    def _load_pretrained(self,device):
        AnchoredBodyAdapter._load_pretrained(self,device)
        self.initial_new_body={};attach_fixed_inference(self.model_)

    def initial_control_metadata(self):
        return {'initial_body_is_original_public_without_added_module':True,'all_new_gate_weights_zero':None,'new_gate_multiplier_exactly_one':None}

    def _compute_batch_loss(self,batch,model):
        assert model is self.model_ and batch.X.shape[0]==1
        assert all(not p.requires_grad for p in model.col_embedder.parameters()) and all(not p.requires_grad for p in model.row_interactor.parameters())
        classes=int(batch.y_train.max())+1;assert classes>=2
        seed=int(self.random_state)+self.loss_forward_calls*1009+761;shift=int(np.random.default_rng(seed).integers(1,classes))
        permutation=torch.roll(torch.arange(classes,device=batch.X.device),shifts=shift)
        context=torch.cat([batch.y_train,permutation[batch.y_train.long()].float()],dim=0)
        y0=batch.y_query[0].long();targets=torch.stack([y0,permutation[y0]])
        self.teacher_icl.to(batch.X.device).train()
        with torch.no_grad():
            # Publicv2column embeddings are target-aware:recompute both frozen
            # encoding stages for each cyclic label view,not just the ICL labels.
            assert model.col_embedder.target_aware
            paired_X=batch.X.repeat(2,1,1)
            rep=model.row_interactor(model.col_embedder(paired_X,y_train=context.float(),d=None,embed_with_test=False),d=None)
            teacher=self.teacher_icl(rep.clone(),y_train=context.float())
        logits=model.icl_predictor(rep.clone(),y_train=context.float())[...,:classes].float();teacher=teacher[...,:classes].float()
        ce=.5*(F.cross_entropy(logits[0],targets[0])+F.cross_entropy(logits[1],targets[1]))
        a=logits.reshape(-1,classes);b=teacher.reshape(-1,classes)
        kl=F.kl_div(F.log_softmax(a/2.,dim=-1),F.softmax(b/2.,dim=-1),reduction='batchmean')*4.
        p0=logits[0].softmax(-1);p1=logits[1].index_select(-1,permutation).softmax(-1);log_m=((p0+p1)*.5).clamp_min(1e-12).log()
        js=.5*(F.kl_div(log_m,p0,reduction='batchmean')+F.kl_div(log_m,p1,reduction='batchmean'));loss=ce+kl+js
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));index=self.loss_forward_calls
        assert weight_digest(self.teacher_icl.state_dict())==self.teacher_initial_sha
        np.savez(self.audit_dir/f'anchored_batch_{index:03}.npz',representations=rep.float().cpu().numpy(),teacher_logits=b.detach().cpu().numpy(),student_logits=a.detach().cpu().numpy(),targets=targets.reshape(-1).cpu().numpy(),context_labels=context.cpu().numpy(),original_context_labels=batch.y_train.cpu().numpy(),original_query_targets=y0.cpu().numpy(),permutation=permutation.cpu().numpy())
        rec={'index':index,'paired_label_views':2,'target_aware_frozen_encoders_recomputed_for_each_label_view':True,'permutation_seed':seed,'cyclic_shift':shift,'cross_entropy':float(ce.detach()),'temperature_scaled_KL':float(kl.detach()),'permutation_JS':float(js.detach()),'total_loss':float(loss.detach()),'teacher_public_weights_unchanged':True,
            'batch_X_sha256':hashlib.sha256(batch.X.detach().cpu().numpy().tobytes()).hexdigest(),'saved_batch_sha256':sha(self.audit_dir/f'anchored_batch_{index:03}.npz')}
        with (self.audit_dir/'anchored_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
        return loss
