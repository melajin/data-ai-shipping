"""Broad last6ICL adaptation with larger context and a public-weight teacher constraint."""
from fresh_row_latent_training import RowLatentAdapter
from fresh_representation_adaptation import RepresentationAdapter
from fresh_architecture_adapter import weight_digest
from fresh_rounds import *
import copy
from torch.nn import functional as F

class AnchoredBodyAdapter(RowLatentAdapter):
    body_trainable_prefixes=tuple(f'icl_predictor.tf_icl.blocks.{i}.' for i in range(6,12))+('icl_predictor.ln.','icl_predictor.decoder.')
    expected_changed_original_modules=('icl_predictor',)
    new_body_learning_rate=None
    def _load_pretrained(self,device):
        RepresentationAdapter._load_pretrained(self,device)
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            self.teacher_icl=copy.deepcopy(self.model_.icl_predictor)
            for p in self.teacher_icl.parameters():p.requires_grad_(False)
            self.teacher_initial_sha=weight_digest(self.teacher_icl.state_dict())
            dump(self.audit_dir/'teacher_initialization.json',{'public_checkpoint_sha256':sha(CHECKPOINT),'public_ICL_state_sha256':self.teacher_initial_sha,'all_teacher_parameters_frozen':True,'teacher_not_in_optimizer':True,'temperature':2.,'KL_coefficient':1.})

    def _apply_freezing(self,model):
        for name,p in model.named_parameters():p.requires_grad_(name.startswith(self.body_trainable_prefixes))
        return True

    def _make_amp(self,device):
        assert device.type=='cuda' and torch.cuda.is_bf16_supported()
        dump(self.audit_dir/'training_precision.json',{'autocast':'bfloat16','gradient_scaler_enabled':False,'loss_components':'float32'})
        return True,torch.GradScaler('cuda',enabled=False),lambda:torch.autocast('cuda',dtype=torch.bfloat16)

    def _compute_batch_loss(self,batch,model):
        assert model is self.model_ and all(not p.requires_grad for p in model.col_embedder.parameters()) and all(not p.requires_grad for p in model.row_interactor.parameters())
        self.teacher_icl.to(batch.X.device).train()
        with torch.no_grad():
            # Identical public train-forward feature computation,once per actual batch.
            rep=model.row_interactor(model.col_embedder(batch.X,y_train=batch.y_train.float(),d=None,embed_with_test=False),d=None)
            # ICL adds label embeddings in-place,so each branch needs its own copy.
            teacher=self.teacher_icl(rep.clone(),y_train=batch.y_train.float())
        logits=model.icl_predictor(rep.clone(),y_train=batch.y_train.float());classes=int(batch.y_train.max())+1
        a=logits[...,:classes].float().reshape(-1,classes);b=teacher[...,:classes].float().reshape(-1,classes);target=batch.y_query.long().reshape(-1)
        ce=F.cross_entropy(a,target);kl=F.kl_div(F.log_softmax(a/2.,dim=-1),F.softmax(b/2.,dim=-1),reduction='batchmean')*4.;loss=ce+kl
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss))
        assert weight_digest(self.teacher_icl.state_dict())==self.teacher_initial_sha
        index=self.loss_forward_calls
        np.savez(self.audit_dir/f'anchored_batch_{index:03}.npz',representations=rep.float().cpu().numpy(),teacher_logits=b.detach().cpu().numpy(),student_logits=a.detach().cpu().numpy(),targets=target.cpu().numpy(),context_labels=batch.y_train.cpu().numpy())
        rec={'index':index,'cross_entropy':float(ce.detach()),'temperature_scaled_KL':float(kl.detach()),'total_loss':float(loss.detach()),'teacher_public_weights_unchanged':True,
            'batch_X_sha256':hashlib.sha256(batch.X.detach().cpu().numpy().tobytes()).hexdigest(),'saved_batch_sha256':sha(self.audit_dir/f'anchored_batch_{index:03}.npz')}
        with (self.audit_dir/'anchored_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
        return loss
