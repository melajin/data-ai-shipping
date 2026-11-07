"""Seven supervised tasks share a broadly trained original ICL body."""
from fresh_anchored_training import AnchoredBodyAdapter
from fresh_joint_pair_components import choose_joint_pair,official_tasks,task_rows
from fresh_pair_body_components import infer_body_pairs
from fresh_architecture_adapter import weight_digest
from fresh_rounds import *
import tabicl._finetune.base as ft_base
import tabicl._finetune.data as fd

class JointPairBodyAdapter(AnchoredBodyAdapter):
    body_trainable_prefixes=('icl_predictor.',)
    def _fit_impl(self,X,y,*,X_val,y_val,output_dir):
        original_count=ft_base.count_chunks
        def count(n,max_chunk_size,**kw):return sum(original_count(len(task_rows(np.asarray(y),pair)[0]),max_chunk_size,**kw) for pair in official_tasks())
        ft_base.count_chunks=count
        try:return super()._fit_impl(X,y,X_val=X_val,y_val=y_val,output_dir=output_dir)
        finally:ft_base.count_chunks=original_count

    def iter_task_batches(self,encoded,labels,kw,iterator):
        crop=np.asarray(self._X_encoder_.transform(self.crop_raw),dtype=encoded.dtype)
        flags=np.random.default_rng(kw['epoch_seed']+100000).random(len(encoded))<.5;mixed=np.where(flags[:,None],crop,encoded)
        assert kw['n_estimators']==1 and kw['class_shuffle_method']=='none' and kw.get('world_size',1)==1
        for ti,pair in enumerate(official_tasks()):
            positions,local_labels=task_rows(labels,pair);seed=kw['epoch_seed']+ti*997
            chunks=fd._chunk_indices(len(positions),max_chunk_size=kw['max_chunk_size'],rng=np.random.default_rng(seed),min_chunk_size=kw.get('min_chunk_size',50))
            for k,batch in enumerate(iterator(mixed[positions],local_labels,**dict(kw,epoch_seed=seed))):
                ix=chunks[k];qsize=max(1,int(len(ix)*kw['query_ratio']),int(local_labels[ix].max())+1)
                ci,qi=fd._split_ctx_query(local_labels[ix],query_size=qsize,seed=seed+k*7919,stratify=True)
                ctx=self.fit_ids[positions[ix[ci]]];qry=self.fit_ids[positions[ix[qi]]]
                assert not set(ctx)&set(qry) and np.array_equal(batch.y_train[0],local_labels[ix[ci]]) and np.array_equal(batch.y_query[0],local_labels[ix[qi]])
                rec={'epoch_seed':kw['epoch_seed'],'task_index':ti,'official_pair':pair,'task_seed':seed,'chunk':k,'context_ids':ctx.tolist(),'query_ids':qry.tolist(),
                    'context_task_labels':local_labels[ix[ci]].tolist(),'query_task_labels':local_labels[ix[qi]].tolist(),'crop_ids':self.fit_ids[positions[ix[flags[positions[ix]]]]].tolist(),
                    'one_version_per_boat':True,'max_chunk_size':kw['max_chunk_size'],'query_ratio':kw['query_ratio'],'split_method':'singleton-safe reserved context',
                    'actual_batch_X_sha256':hashlib.sha256(batch.X.numpy().tobytes()).hexdigest()}
                with (self.audit_dir/'actual_training_batches.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec)+'\n')
                self.current_training_record=rec
                yield batch

    def _run_validation(self,inner,X_train,y_train,X_val,y_val):
        vi=getattr(self,'validation_index',0);self.validation_index=vi+1
        query=np.asarray(self._X_encoder_.transform(self.raw_queries['full']),dtype=np.float64);assert np.array_equal(query[self.tune_mask],X_val,equal_nan=True)
        pair=infer_body_pairs(self,X_train,y_train,query,self.audit_dir,f'validation_{vi:02}')
        inner.fit(X_train,y_train);head=np.concatenate([inner.predict_proba(query[j:j+1000]) for j in range(0,len(query),1000)])
        np.save(self.audit_dir/f'validation_full_head_{vi:02}.npy',head);np.save(self.audit_dir/f'validation_head_{vi:02}.npy',head[self.tune_mask])
        best,_,cand,zero_current=choose_joint_pair(self.tune_reference,head[self.tune_mask],pair[self.tune_mask],y_val,np.ones(len(y_val),dtype=bool))
        steps=max([int(z['step']) for z in self.audit_optimizer.state.values() if 'step' in z],default=0)
        if steps:self.best_positive_correct_so_far=max(getattr(self,'best_positive_correct_so_far',-1),best['TUNE_correct'])
        zero=bool(steps and cand[0]['TUNE_correct']>self.best_positive_correct_so_far)
        event={'epoch':vi,'optimizer_steps':steps,'loss_forward_calls':self.loss_forward_calls,'weights_sha256':weight_digest(self.model_.state_dict()),'positive_choice':best,'candidates':cand,
            'zero_strictly_better':zero,'zero_better_than_current_epoch':zero_current,'eligible_trained_checkpoint':steps>0,'best_positive_correct_so_far':getattr(self,'best_positive_correct_so_far',None),
            'termination_comparator':'Best eligible positive checkpoint so far;not an inferior transient later epoch.'}
        if vi==0:
            for v,raw in self.raw_queries.items():
                q=np.asarray(self._X_encoder_.transform(raw),dtype=np.float64);op=head if v=='full' else np.concatenate([inner.predict_proba(q[j:j+1000]) for j in range(0,len(q),1000)])
                np.save(self.audit_dir/f'unadapted_head_{v}.npy',op)
        elif zero:self.time_limit=0;self.zero_stop=True
        with (self.audit_dir/'validation_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        print('JOINT_PAIR_BODY_VALIDATION',json.dumps(event),flush=True)
        return ft_base.ValidationMetrics(primary=(best['TUNE_correct']+best['TUNE_macro']*1e-4)/len(y_val) if steps else -1.)
