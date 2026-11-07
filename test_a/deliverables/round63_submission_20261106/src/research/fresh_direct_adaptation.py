"""Round25: direct four-class ICL weight adaptation, original weights only.

Unlike the earlier error-verifier idea, no previous predictions/OOF are training
features. Only true FIT labels and pure337 geometric/state features are used.
"""
from fresh_best_reference import *
from tabicl import FinetunedTabICLClassifier


class DirectFishingAdapter(FinetunedTabICLClassifier):
    def _compute_batch_loss(self,batch,model):
        loss=super()._compute_batch_loss(batch,model)
        self.loss_forward_calls+=1
        self.finite_loss_calls+=int(torch.isfinite(loss.detach()).item())
        return loss

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        result=super()._run_validation(inner,X_train,y_train,X_val,y_val)
        if not self.original_control:
            assert self.loss_forward_calls==0,'Original-weight control must precede every gradient batch'
            control=self._build_inner_estimator(self.model_,4,torch.device('cuda'))
            control.fit(X_train,y_train)
            assert list(control.classes_)==[0,1,2,3]
            for v,raw in self.raw_queries.items():
                encoded=np.asarray(self._X_encoder_.transform(raw),dtype=np.float64)
                self.original_control[v]=np.concatenate([control.predict_proba(encoded[i:i+1000]) for i in range(0,len(encoded),1000)]).copy()
                np.save(self.audit_dir/f'unadapted_head_{v}.npy',self.original_control[v])
            dump(self.audit_dir/'unadapted_control_audit.json',{'captured_before_loss_forward_calls':self.loss_forward_calls,'context_n':len(y_train),'features':X_train.shape[1],
                'inference_estimators':4,'same_current_round_outer_encoder':True,'same_model_original_initial_weights':True,'selection_labels':'No REPORT labels; predictions only'})
            del control;gc.collect();torch.cuda.empty_cache()
            print('ORIGINAL_WEIGHT_CONTROL_CAPTURED',flush=True)
        return result


def choose_head(reference,newhead,y,tu):
    best=None;choices=[];j0=reference['joint'];p=reference['pair'];alpha=reference['alpha'];w=reference['weights']
    for gamma in [0.,.25,.5,.75,1.]:
        j=(1-gamma)*j0+gamma*newhead;pr=apply_policy(j,p,alpha,w);m=metrics(y[tu],pr[tu]);key=(int((pr[tu]==y[tu]).sum()),m['macro_f1'],-gamma)
        choices.append({'gamma':gamma,'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']})
        if best is None or key>best[0]:best=(key,gamma,j,pr)
    return best[1:],choices


def main():
    rd=start(25,'Direct natural-frequency four-class ICL weight adaptation, with original-weight matched control and entirely refitted reference')
    for name in ['fresh_direct_adaptation.py','fresh_best_reference.py','fresh_relation_basis.py','fresh_hierarchy_round.py']:
        shutil.copy2(B/name,rd/name)
    dump(rd/'predeclared_protocol.json',{'reference':'All80 frozen-weight task fits, shape/region transforms and TUNE decisions rebuilt within this round.',
        'primary_change':'Actual gradient optimization of ICL predictor on true FIT labels, direct337 geometric/state inputs; no OOF or previous prediction training features. Natural unweighted cross-entropy.',
        'frozen_modules':['col_embedder','row_interactor'],'updated_module':'icl_predictor',
        'epochs_max':12,'learning_rate':1e-5,'max_data_size':1024,'query_fraction':.25,'patience':4,'time_limit_seconds':480,
        'selection':'Full-view TUNE accuracy selects weights. Separate five-way head blend per view on TUNE Micro, macro tie-break, smaller gamma. REPORT never selects weights or blend.',
        'control':'Before first gradient batch, capture original weights with the same current-round outer encoder, FIT context, class_shuffle none and4-estimator inference.',
        'short_views':'One full-view adapted model transfers to pure337 features with identical semantics in d1/d3/d7. Learned region/shape codes are not transferred across views. Fresh matched references remain available.',
        'gradient_initialization':'Verified original public checkpoint only; epoch0/fallback is not counted as an adaptation gain.'})
    restrict_old_rounds(25);s,base=load();fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();qy=sub.y.to_numpy()
    ref=fit_reference(rd,s,base);train=ref['full']['state'].loc[fit].to_numpy(dtype=np.float32)
    assert all(list(ref[v]['state'].columns)==list(ref['full']['state'].columns) for v in VIEWS)
    queries={v:ref[v]['state'].loc[sub.index].to_numpy(dtype=np.float32) for v in VIEWS}
    train=np.where(np.isfinite(train),train,np.nan);queries={v:np.where(np.isfinite(x),x,np.nan) for v,x in queries.items()}
    torch.set_num_threads(4)
    m=DirectFishingAdapter(epochs=12,learning_rate=1e-5,max_data_size=1024,finetune_ctx_query_ratio=.25,
        n_estimators_finetune=2,n_estimators_validation=2,n_estimators_inference=4,
        freeze_col=True,freeze_row=True,freeze_icl=False,class_shuffle_method='none',early_stopping=True,patience=4,time_limit=480,save_interval=0,
        model_path=CHECKPOINT,allow_auto_download=False,device='cuda',random_state=SEED+2500,verbose=True,eval_metric='accuracy',
        extra_classifier_kwargs={'batch_size':1,'kv_cache':'repr','use_amp':True,'use_fa3':False,'n_jobs':4})
    m.loss_forward_calls=0;m.finite_loss_calls=0;m.original_control={};m.raw_queries=queries;m.audit_dir=rd
    begun=now();t=time.time();m.fit(train,s.loc[fit,'y'].to_numpy(),X_val=queries['full'][tu],y_val=qy[tu],output_dir=rd/'adapted_checkpoint')
    orig=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict'];changed=[];modules={}
    for key,tensor in m.model_.state_dict().items():
        flag=not torch.equal(orig[key],tensor.detach().cpu());module=key.split('.')[0]
        if flag:changed.append(key)
        modules.setdefault(module,{'changed':0,'total':0});modules[module]['changed']+=int(flag);modules[module]['total']+=1
    assert all(k.startswith('icl_predictor.') for k in changed)
    assert m.loss_forward_calls>0 and m.finite_loss_calls>0,'Do not claim adaptation without gradient-loss batches'
    audit={'started':begun,'finished':now(),'training_seconds':time.time()-t,'loss_forward_calls':m.loss_forward_calls,'finite_loss_calls':m.finite_loss_calls,
        'selected_weights_changed':bool(changed),'changed_tensor_names':changed,'modules':modules,'best_TUNE_accuracy':float(m._best_metric_),
        'starting_checkpoint_sha256':sha(CHECKPOINT),'saved_checkpoint_sha256':sha(rd/'adapted_checkpoint'/'best.ckpt'),
        'training_ids_sha256':hashlib.sha256(s.index[fit].to_numpy().tobytes()).hexdigest(),'validation_ids_sha256':hashlib.sha256(sub.index[tu].to_numpy().tobytes()).hexdigest()}
    dump(rd/'weight_change_audit.json',audit);del orig
    cfg=json.loads((rd/'config.json').read_text(encoding='utf-8'));cfg.update(gradient_updates=True,weights_changed=bool(changed),updated_modules=['icl_predictor'] if changed else []);dump(rd/'config.json',cfg)
    prob={};pairs={};final={};decisions={};controls={}
    for v in VIEWS:
        ap=np.concatenate([m.predict_proba(queries[v][i:i+1000]) for i in range(0,len(sub),1000)]);assert list(m.classes_)==[0,1,2,3]
        np.save(rd/f'adapted_head_{v}.npy',ap)
        (gamma,prob[v],final[v]),choices=choose_head(ref[v],ap,qy,tu)
        (cg,cj,cp),cc=choose_head(ref[v],m.original_control[v],qy,tu)
        pairs[v]=ref[v]['pair'];decisions[v]={'reference':ref[v]['policy'],'adapted_gamma':gamma,'adapted_candidates':choices,'control_gamma':cg,'control_candidates':cc}
        controls[v]={'fresh_best_design_prediction':ref[v]['prediction'],'matched_unadapted_selected_prediction':cp,'raw_adapted_head_prediction':ap.argmax(1),'raw_unadapted_head_prediction':m.original_control[v].argmax(1)}
        print('FRESH_ADAPTATION_SELECTION',v,json.dumps(decisions[v]),flush=True)
    del m;gc.collect();torch.cuda.empty_cache()
    complete(rd,s,base,prob,pairs,final,decisions,controls)


if __name__=='__main__':main()
