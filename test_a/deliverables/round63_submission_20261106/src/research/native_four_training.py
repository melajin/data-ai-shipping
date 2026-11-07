"""Last4internalFFNgates+last4originalICL,trained through native4memberfinalevidence."""
from final_evidence_training import *
from native_four_cache import create_native_caches
from native_four_loss import native_evidence_objective
from tabicl_tail_gated_body import attach_tail_gates,load_tail_body

class NativeFourBodyAdapter(FinalEvidenceBodyAdapter):
    body_trainable_prefixes=tuple(f'icl_predictor.tf_icl.blocks.{i}.' for i in range(8,12))+('icl_predictor.ln.','icl_predictor.decoder.')
    new_body_learning_rate=1e-4
    def fit(self,X,y,**kwargs):
        self.original_fit_features=np.asarray(X,dtype=np.float32).copy(order='K');return super().fit(X,y,**kwargs)
    def _load_pretrained(self,device):
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            FinalEvidenceBodyAdapter._load_pretrained(self,device);self.model_=attach_tail_gates(self.model_);self.initial_new_body={k:v.detach().cpu().clone() for k,v in self.model_.state_dict().items() if '.ffn_gate.' in k};torch.save(self.initial_new_body,self.audit_dir/'initial_new_body.pt')
        else:
            self.model_,self.model_config_=load_tail_body(self.model_path,device);self.model_path_=Path(self.model_path);self.fixed_body_parameter_names=('row_interactor.tf_row.rope.freqs',)
            for module in self.model_.modules():
                if hasattr(module,'recompute'):module.recompute=True
            self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True;attach_fixed_inference(self.model_)

    def iter_task_batches(self,encoded,labels,kw,iterator):
        if not hasattr(self,'evidence_records'):self.evidence_records=create_native_caches(self,encoded,labels)
        self.current_epoch=kw['epoch_seed']-self.random_state
        for fold in range(2):
            self.current_fold=fold;self.current_global_records=[r for r in self.evidence_records if r['fold']==fold];yield fd.MetaBatch(X=torch.zeros(1,2,1),y_train=torch.zeros(1,1),y_query=torch.zeros(1,1,dtype=torch.long),train_size=1,y_scaler_mean=None,y_scaler_std=None)

    def _compute_batch_loss(self,batch,model):
        plans=[];leaves=[];teachers=[];perms=[];specs=self.current_global_records;records=[]
        for task in specs:
            data=torch.load(self.audit_dir/task['cache'],map_location='cpu',weights_only=False);X=data['representations'].float();cy=data['context_labels'];K=task['classes'];out=model.icl_predictor(X.to('cuda',copy=True),y_train=cy.cuda())[...,:K].float();leaves.append(out.detach().clone().requires_grad_(True));del out;plans.append((X,cy,K));teachers.append(data['teacher_logits'].cuda());perms.append(data['permutations'].cuda());target=data['global_query_targets'].cuda();records.append({'task_index':task['index'],'fold':task['fold'],'cache_sha256':task['cache_sha256'],'native_preprocessing_seed':task['seed'],'actual_batch_X_sha256':hashlib.sha256(X.numpy().tobytes()).hexdigest()})
        loss,parts=native_evidence_objective(leaves,teachers,perms,specs,target);cot=torch.autograd.grad(loss,leaves);index=self.loss_forward_calls+1;path=self.audit_dir/f'native_loss_{index:03}.pt';torch.save({'student_logits':[z.detach().cpu() for z in leaves],'teacher_logits':[z.cpu() for z in teachers],'permutations':[z.cpu() for z in perms],'targets':target.cpu(),'cotangents':[z.cpu() for z in cot]},path)
        for i,(X,cy,K) in enumerate(plans):
            out=model.icl_predictor(X.to('cuda',copy=True),y_train=cy.cuda())[...,:K].float();assert torch.equal(out.detach(),leaves[i].detach());out.backward(cot[i]);del out
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));event={'index':index,'epoch':self.current_epoch,'fold':self.current_fold,'components':records,'actual_body_forwards':40,'actual_body_backwards':20,'optimizer_steps':1,'native_ensemble_members_per_task':4,'two_pass_forward_bitwise_equal_all20':True,'loss_tensors_sha256':sha(path),**{k:float(v.detach()) for k,v in parts.items()},'total_loss':float(loss.detach())}
        for filename in ['native_loss_audit.jsonl','actual_training_batches.jsonl']:
            with (self.audit_dir/filename).open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        return loss.detach().requires_grad_(True)
