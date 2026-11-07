"""Round29 candidate: train feature interactions as well as ICL prediction.

Both adaptation arms start from the public checkpoint. The ICL-only arm is
retrained here with identical optimizer settings, never loaded from round25.
"""
from fresh_direct_adaptation import DirectFishingAdapter
from fresh_best_reference import *
from fresh_row_round import choose_records


class RepresentationAdapter(DirectFishingAdapter):
    def _load_pretrained(self,device):
        super()._load_pretrained(device)
        # Same checkpoint tensors; recompute activations during backward to fit
        # the unfrozen row network in the available GPU memory. Both arms use it.
        for module in self.model_.modules():
            if hasattr(module,'recompute'):module.recompute=True
        self.model_config_=dict(self.model_config_);self.model_config_['recompute']=True


def train_arm(rd,arm,train,queries,s,sub,tu):
    ad=rd/arm;ad.mkdir();seed=SEED+2900;torch.manual_seed(seed);np.random.seed(seed);torch.cuda.manual_seed_all(seed)
    freeze_row=arm=='icl_only_control'
    m=RepresentationAdapter(epochs=12,learning_rate=3e-6,max_data_size=512,finetune_ctx_query_ratio=.25,
        n_estimators_finetune=2,n_estimators_validation=2,n_estimators_inference=4,
        freeze_col=True,freeze_row=freeze_row,freeze_icl=False,class_shuffle_method='none',early_stopping=True,patience=4,time_limit=480,save_interval=0,
        model_path=CHECKPOINT,allow_auto_download=False,device='cuda',random_state=seed,verbose=True,eval_metric='accuracy',
        extra_classifier_kwargs={'batch_size':1,'kv_cache':'repr','use_amp':True,'use_fa3':False,'n_jobs':4})
    m.loss_forward_calls=0;m.finite_loss_calls=0;m.original_control={};m.raw_queries=queries;m.audit_dir=ad
    fit=s.split.eq('FIT').to_numpy();begun=now();t=time.time()
    m.fit(train,s.loc[fit,'y'].to_numpy(),X_val=queries['full'][tu],y_val=sub.loc[tu,'y'].to_numpy(),output_dir=ad/'checkpoint')
    orig=torch.load(CHECKPOINT,map_location='cpu',weights_only=False)['state_dict'];changed=[];modules={}
    for key,tensor in m.model_.state_dict().items():
        flag=not torch.equal(orig[key],tensor.detach().cpu());module=key.split('.')[0]
        if flag:changed.append(key)
        modules.setdefault(module,{'changed':0,'total':0});modules[module]['changed']+=int(flag);modules[module]['total']+=1
    allowed=['icl_predictor'] if freeze_row else ['row_interactor','icl_predictor']
    assert all(k.split('.')[0] in allowed for k in changed)
    assert m.loss_forward_calls>0 and m.loss_forward_calls==m.finite_loss_calls
    saved=torch.load(ad/'checkpoint'/'best.ckpt',map_location='cpu',weights_only=False)
    selected_steps=max([int(z['step']) for z in saved['optimizer_state']['state'].values() if 'step' in z],default=0)
    selected_epoch=int(saved['epoch']);del saved
    audit={'arm':arm,'started':begun,'finished':now(),'training_seconds':time.time()-t,'loss_forward_calls':m.loss_forward_calls,'finite_loss_calls':m.finite_loss_calls,
        'optimizer_steps_recorded_at_final_save':selected_steps,'epoch_field_recorded_at_final_save':selected_epoch,
        'selected_weights_epoch':None,'selected_weights_optimizer_steps':None,
        'checkpoint_metadata_limitation':'Library restores best weights, then saves final optimizer state and configured maximum epoch. These checkpoint fields do not identify the selected weights epoch or step.',
        'selected_weights_changed':bool(changed),'changed_tensor_names':changed,'modules':modules,'best_TUNE_accuracy':float(m._best_metric_),
        'starting_checkpoint_sha256':sha(CHECKPOINT),'saved_checkpoint_sha256':sha(ad/'checkpoint'/'best.ckpt'),
        'training_ids_sha256':hashlib.sha256(s.index[fit].to_numpy().tobytes()).hexdigest(),'validation_ids_sha256':hashlib.sha256(sub.index[tu].to_numpy().tobytes()).hexdigest(),
        'seed':seed,'max_data_size':512,'learning_rate':3e-6,'epochs_max':12,'activation_recomputation':True,'frozen_modules':['col_embedder']+(['row_interactor'] if freeze_row else [])}
    dump(ad/'weight_change_audit.json',audit);del orig
    preds={};original={v:p.copy() for v,p in m.original_control.items()}
    for v in VIEWS:
        preds[v]=np.concatenate([m.predict_proba(queries[v][i:i+1000]) for i in range(0,len(sub),1000)])
        assert list(m.classes_)==[0,1,2,3];np.save(ad/f'adapted_head_{v}.npy',preds[v])
    del m;gc.collect();torch.cuda.empty_cache();print('REPRESENTATION_ARM_COMPLETE',arm,json.dumps({k:audit[k] for k in ['loss_forward_calls','selected_weights_changed','modules','best_TUNE_accuracy']}),flush=True)
    return preds,original,audit


def main():
    rd=start(29,'Actual row-interaction and ICL weight adaptation versus matched freshly trained ICL-only control')
    for name in ['fresh_representation_adaptation.py','fresh_direct_adaptation.py','fresh_row_round.py','fresh_best_reference.py','fresh_relation_basis.py','fresh_hierarchy_round.py']:
        shutil.copy2(B/name,rd/name)
    dump(rd/'predeclared_protocol.json',{'primary_change':'Unfreeze row_interactor and icl_predictor to adapt how337 geometric/state features are combined, while col_embedder remains frozen.',
        'control':'A separately trained ICL-only arm starts from the same public checkpoint with identical data, optimizer, seeds, maximum epochs and context/query budgets. Both arms capture original-weight predictions before their first gradient batch.',
        'data':'True FIT vessel labels and deterministic337 features only. No old OOF/predictions or previous adapted weights. One full-view row per boat for adaptation; same column semantics for short-view inference.',
        'training':{'epochs_max':12,'learning_rate':3e-6,'max_data_size':512,'query_fraction':.25,'patience':4,'time_limit_seconds_per_arm':480,'estimators_train':2,'estimators_validation':2,'estimators_inference':4,'activation_recomputation_both_arms':True},
        'selection':'TUNE accuracy selects each arm checkpoint. Primary fixed to row+ICL arm. Five final log-evidence blend values on TUNE, same for ICL-only and original-weight controls. REPORT never selects weights or arm.',
        'reference':'80 fresh public-checkpoint fits and all FIT relation transforms repeated in this round.',
        'gradient_updates':True,'matched_budget_note':'Maximum budgets and sampled-episode seeds match; early stopping may yield different actual step counts, which are reported.'})
    restrict_old_rounds(29);s,base=load();fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();qy=sub.y.to_numpy()
    ref=fit_reference(rd,s,base);train=ref['full']['state'].loc[fit].to_numpy(dtype=np.float32)
    assert all(list(ref[v]['state'].columns)==list(ref['full']['state'].columns) for v in VIEWS)
    queries={v:ref[v]['state'].loc[sub.index].to_numpy(dtype=np.float32) for v in VIEWS}
    train=np.where(np.isfinite(train),train,np.nan);queries={v:np.where(np.isfinite(x),x,np.nan) for v,x in queries.items()};torch.set_num_threads(4)
    primary,original,pa=train_arm(rd,'row_and_icl',train,queries,s,sub,tu)
    control,original_control,ca=train_arm(rd,'icl_only_control',train,queries,s,sub,tu)
    cfg=json.loads((rd/'config.json').read_text(encoding='utf-8'));cfg.update(gradient_updates=True,weights_changed=pa['selected_weights_changed'],updated_modules=[k for k,v in pa['modules'].items() if v['changed']]);dump(rd/'config.json',cfg)
    prob={};pairs={};final={};decisions={};controls={}
    for v in VIEWS:
        (gamma,pr,score),cand=choose_records(ref[v],primary[v],qy,tu)
        (cg,cp,cs),cc=choose_records(ref[v],control[v],qy,tu)
        (og,op,os),oc=choose_records(ref[v],original[v],qy,tu)
        (iog,iop,ios),ioc=choose_records(ref[v],original_control[v],qy,tu)
        prob[v]=ref[v]['joint'];pairs[v]=ref[v]['pair'];final[v]=pr;np.save(rd/f'final_scores_{v}.npy',score)
        decisions[v]={'reference':ref[v]['policy'],'adapted_gamma':gamma,'adapted_candidates':cand,'icl_control_gamma':cg,'icl_control_candidates':cc,'original_gamma':og,'original_candidates':oc,'icl_original_gamma':iog,'icl_original_candidates':ioc}
        controls[v]={'fresh_best_design_prediction':ref[v]['prediction'],'matched_icl_only_prediction':cp,'matched_original_prediction':op,'matched_icl_original_prediction':iop,
            'raw_adapted_prediction':primary[v].argmax(1),'raw_icl_only_prediction':control[v].argmax(1)}
        print('REPRESENTATION_SELECTION',v,json.dumps(decisions[v]),flush=True)
    complete(rd,s,base,prob,pairs,final,decisions,controls)


if __name__=='__main__':main()
