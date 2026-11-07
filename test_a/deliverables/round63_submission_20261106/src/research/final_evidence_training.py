"""Develop19/28+49 by training the final combined four-class evidence directly."""
from matched_proven_training import *
from final_evidence_cache import create_evidence_caches
from final_evidence_loss import final_evidence_objective

class FinalEvidenceBodyAdapter(MatchedProvenBodyAdapter):
    new_body_learning_rate=None
    def _make_amp(self,device):
        assert device.type=='cuda' and torch.cuda.is_bf16_supported();dump(self.audit_dir/'training_precision.json',{'autocast':'bfloat16','autocast_weight_cache':False,'gradient_scaler_enabled':False,'reason':'Distinctper-forwardweightcastssoFP32parametergradientsaccumulatepercomponent;avoidBF16shared-castgradientaggregationdifferencefromdensegraph.'})
        return True,torch.GradScaler('cuda',enabled=False),lambda:torch.autocast('cuda',dtype=torch.bfloat16,cache_enabled=False)
    def _load_pretrained(self,device):
        RepresentationAdapter._load_pretrained(self,device);self.initial_new_body={}
        if Path(self.model_path).resolve()==CHECKPOINT.resolve():
            self.teacher_icl=copy.deepcopy(self.model_.icl_predictor).cpu()
            for p in self.teacher_icl.parameters():p.requires_grad_(False)
        self.fixed_body_parameter_names=tuple(k for k,v in self.model_.named_parameters() if k.startswith('icl_predictor.y_encoder.'))+('row_interactor.tf_row.rope.freqs',);attach_fixed_inference(self.model_)

    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        original=ft_base.count_chunks;ft_base.count_chunks=lambda *a,**kw:2
        try:return WideBodyAdapter._fit_impl(self,X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:ft_base.count_chunks=original

    def iter_task_batches(self,encoded,labels,kw,iterator):
        if not hasattr(self,'evidence_records'):self.evidence_records=create_evidence_caches(self,encoded,labels)
        epoch=kw['epoch_seed']-self.random_state
        for fold in range(2):
            self.current_global_records=[r for r in self.evidence_records if r['fold']==fold];self.current_epoch=epoch;self.current_fold=fold
            # Only a carrier;the actual20input tensors are audited in the loss.
            yield fd.MetaBatch(X=torch.zeros(1,2,1),y_train=torch.zeros(1,1),y_query=torch.zeros(1,1,dtype=torch.long),train_size=1,y_scaler_mean=None,y_scaler_std=None)

    def _compute_batch_loss(self,batch,model):
        assert model is self.model_ and len(self.current_global_records)==20;plans=[];leaves=[];teachers=[];perms=[];specs=self.current_global_records;methods=[self.current_epoch%2,1-self.current_epoch%2];records=[]
        # Use grad-enabled forward in both passes so forward kernels are identical;
        # discard each first-pass body graph immediately,keeping only small logits.
        for task in specs:
            data=torch.load(self.audit_dir/task['cache'],map_location='cpu',weights_only=False);K=task['classes'];seed=self.random_state+self.loss_forward_calls*1009+task['index']*37+761;shift=int(np.random.default_rng(seed).integers(1,K));perm=torch.roll(torch.arange(K),shifts=shift);X=torch.stack([data['representations'][methods[0],0],data['representations'][methods[1],shift]]).float();cy=data['context_labels'];context=torch.stack([cy,perm[cy.long()].float()]);teacher=torch.stack([data['teacher_logits'][methods[0],0],data['teacher_logits'][methods[1],shift]]).cuda();target=data['global_query_targets'].cuda()
            out=model.icl_predictor(X.cuda().clone(),y_train=context.cuda())[...,:K].float();leaf=out.detach().clone().requires_grad_(True);del out;leaves.append(leaf);teachers.append(teacher);perms.append(perm.cuda());plans.append((X,context,K))
            records.append({'task_index':task['index'],'fold':task['fold'],'cache_sha256':task['cache_sha256'],'normalization_view_indices':methods,'permutation_seed':seed,'cyclic_shift':shift,'actual_batch_X_sha256':hashlib.sha256(X.numpy().tobytes()).hexdigest()})
        loss,parts=final_evidence_objective(leaves,teachers,perms,specs,target);cotangents=torch.autograd.grad(loss,leaves);index=self.loss_forward_calls+1
        saved={'student_logits':[z.detach().cpu() for z in leaves],'teacher_logits':[z.detach().cpu() for z in teachers],'permutations':[z.cpu() for z in perms],'targets':target.cpu(),'cotangents':[z.detach().cpu() for z in cotangents]};path=self.audit_dir/f'global_loss_{index:03}.pt';torch.save(saved,path)
        for i,(X,context,K) in enumerate(plans):
            actual=model.icl_predictor(X.cuda().clone(),y_train=context.cuda())[...,:K].float();assert torch.equal(actual.detach(),leaves[i].detach()),'Two-passforwardmustbeidentical';actual.backward(cotangents[i]);del actual
        self.loss_forward_calls+=1;self.finite_loss_calls+=int(torch.isfinite(loss));event={'index':index,'epoch':self.current_epoch,'fold':self.current_fold,'components':records,'actual_body_forwards':40,'actual_body_backwards':20,'optimizer_steps':1,'two_pass_forward_bitwise_equal_all20':True,'loss_tensors_sha256':sha(path),**{k:float(v.detach()) for k,v in parts.items()},'total_loss':float(loss.detach())}
        with (self.audit_dir/'global_loss_audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        with (self.audit_dir/'actual_training_batches.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'global_step':index,'epoch':self.current_epoch,'fold':self.current_fold,'components':records,'loss_tensors_sha256':sha(path)})+'\n')
        # Native loop's disabled-scaler backward on this scalar is a no-op for
        # body weights;the exact accumulated body gradient already exists above.
        return loss.detach().requires_grad_(True)
