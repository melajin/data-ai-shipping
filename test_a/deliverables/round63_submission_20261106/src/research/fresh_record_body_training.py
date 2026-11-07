"""Broad original input stages and last-four-ICL adaptation on learned record features."""
from fresh_frequency_training import FrequencyBodyAdapter
from fresh_representation_adaptation import RepresentationAdapter
from fresh_fixed_inference import attach_fixed_inference
from fresh_rounds import *
from torch.nn import functional as F


class RecordLatentBodyAdapter(FrequencyBodyAdapter):
    body_trainable_prefixes=('col_embedder.','row_interactor.')+tuple(f'icl_predictor.tf_icl.blocks.{i}.' for i in range(8,12))+('icl_predictor.ln.','icl_predictor.decoder.')
    expected_changed_original_modules=('col_embedder','row_interactor','icl_predictor')
    new_body_learning_rate=None
    validation_label='RECORD_LATENT_BROAD_BODY_VALIDATION'

    def _apply_freezing(self,model):
        for name,p in model.named_parameters():p.requires_grad_(name.startswith(self.body_trainable_prefixes) and name not in self.fixed_body_parameter_names)
        return True

    def initial_control_metadata(self):
        return {'initial_body_is_original_public_without_added_module':True,'all_new_gate_weights_zero':None,'new_gate_multiplier_exactly_one':None}

    def _load_pretrained(self,device):
        RepresentationAdapter._load_pretrained(self,device);self.initial_new_body={};attach_fixed_inference(self.model_)

    def _compute_batch_loss(self,batch,model):
        assert model is self.model_ and batch.X.shape[0]==1 and not dict(model.named_parameters())['row_interactor.tf_row.rope.freqs'].requires_grad
        classes=int(batch.y_train.max())+1;seed=int(self.random_state)+self.loss_forward_calls*1009+761;shift=int(np.random.default_rng(seed).integers(1,classes));perm=torch.roll(torch.arange(classes,device=batch.X.device),shifts=shift)
        context=torch.cat([batch.y_train,perm[batch.y_train.long()].float()],dim=0);q=batch.y_query[0].long();target=torch.stack([q,perm[q]])
        logits=model(batch.X.repeat(2,1,1),context.float())[...,:classes].float();ce=.5*(F.cross_entropy(logits[0],target[0])+F.cross_entropy(logits[1],target[1]))
        p0=logits[0].softmax(-1);p1=logits[1].index_select(-1,perm).softmax(-1);lm=((p0+p1)*.5).clamp_min(1e-12).log();js=.5*(F.kl_div(lm,p0,reduction='batchmean')+F.kl_div(lm,p1,reduction='batchmean'));loss=ce+.25*js
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));index=self.loss_forward_calls;path=self.audit_dir/f'paired_batch_{index:03}.npz'
        np.savez(path,student_logits=logits.detach().cpu().numpy(),targets=target.cpu().numpy(),context_labels=context.cpu().numpy(),original_context_labels=batch.y_train.cpu().numpy(),original_query_targets=q.cpu().numpy(),permutation=perm.cpu().numpy())
        rec={'index':index,'paired_label_views':2,'no_teacher':True,'permutation_seed':seed,'cyclic_shift':shift,'cross_entropy':float(ce.detach()),'permutation_JS':float(js.detach()),'total_loss':float(loss.detach()),'batch_X_sha256':hashlib.sha256(batch.X.detach().cpu().numpy().tobytes()).hexdigest(),'saved_batch_sha256':sha(path)}
        with (self.audit_dir/'paired_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
        return loss
