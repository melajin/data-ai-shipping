"""Capture current-round frozen encoder outputs;replay only the mutable ICL body."""
from fresh_rounds import *
from contextlib import contextmanager
import experiment,weakref,copy

def tensor_sha(value):
    value=value.detach().cpu().contiguous();return hashlib.sha256(value.reshape(-1).view(torch.uint8).numpy().tobytes()).hexdigest()

def frozen_encoder_sha(model):
    from fresh_architecture_adapter import weight_digest
    return weight_digest({k:v for k,v in model.state_dict().items() if k.startswith(('col_embedder.','row_interactor.','icl_predictor.y_encoder.'))})

def attach_capture(estimator,path):
    state={'contexts':{},'calls':[],'groups':[]};ref=weakref.ref(estimator);native_fit=type(estimator).fit;native_predict=type(estimator).predict_proba
    def fit(X,y):
        m=ref();x=np.asarray(X);state['fit_input']={'shape':list(x.shape),'dtype':str(x.dtype),'C':bool(x.flags.c_contiguous),'F':bool(x.flags.f_contiguous),'value_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'labels_sha256':hashlib.sha256(np.asarray(y).tobytes()).hexdigest()};return native_fit(m,X,y)
    def predict(X):
        m=ref()
        if 'metadata' not in state:
            icl=m.model_.icl_predictor;iref=weakref.ref(icl);original=type(icl).forward_with_repr_cache
            def forward(R,**kwargs):
                obj=iref();cpu=R.detach().cpu().contiguous();size=kwargs['train_size'];context=cpu[:,:size].contiguous();key=tensor_sha(context)
                if key not in state['contexts']:state['contexts'][key]=context.clone()
                rec={'context':key,'query':cpu[:,size:].contiguous().clone(),'kwargs':copy.deepcopy(kwargs),'input_sha256':tensor_sha(cpu),'original_device':str(R.device)}
                result=original(obj,R,**kwargs);rec['public_output']=result.detach().float().cpu().clone();state['calls'].append(rec);return result
            icl.forward_with_repr_cache=forward
            shuffles=[list(a) for values in m.ensemble_generator_.class_shuffles_.values() for a in values]
            state['metadata']={'classes':m.classes_.tolist(),'class_shuffles':shuffles,'average_logits':bool(m.average_logits),'softmax_temperature':float(m.softmax_temperature),'seed':m.random_state,'frozen_encoder_sha256':frozen_encoder_sha(m.model_),'public_checkpoint_sha256':sha(CHECKPOINT)}
        start=len(state['calls']);result=native_predict(m,X);stop=len(state['calls']);assert stop-start==len(state['metadata']['class_shuffles']) and all(c['query'].shape[0]==1 for c in state['calls'][start:stop])
        x=np.asarray(X);state['groups'].append({'start':start,'stop':stop,'raw_query_value_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'raw_query_shape':list(x.shape),'raw_query_C':bool(x.flags.c_contiguous),'raw_query_F':bool(x.flags.f_contiguous),'public_probability':result.copy()});torch.save(state,path);return result
    estimator.fit=fit;estimator.predict_proba=predict;return estimator

@contextmanager
def capture_reference_encodings(rd):
    folder=rd/'encoded_public_deployment';folder.mkdir();original=experiment.model;paths=[]
    def factory(*args,**kwargs):
        m=original(*args,**kwargs);path=folder/f'task_{len(paths):02}.pt';paths.append(path);return attach_capture(m,path)
    experiment.model=factory
    try:yield paths
    finally:experiment.model=original

def replay_bundle(model,bundle,verify_public_outputs=False,*,frozen_encoder_digest=None):
    """Replay a bundle,optionally reusing a digest of this model's frozen encoder.

    A deployment sweep may compute the digest once while those weights remain
    unchanged. Omitting it retains the per-call encoder verification.
    """
    digest=frozen_encoder_sha(model) if frozen_encoder_digest is None else frozen_encoder_digest
    assert digest==bundle['metadata']['frozen_encoder_sha256'];model.eval();results=[];meta=bundle['metadata']
    for group in bundle['groups']:
        outputs=[]
        for rec in bundle['calls'][group['start']:group['stop']]:
            device=next(model.parameters()).device if rec['original_device'].startswith('cuda') else torch.device('cpu');R=torch.cat([bundle['contexts'][rec['context']],rec['query']],dim=1);assert tensor_sha(R)==rec['input_sha256'];R=R.to(device,copy=True)
            with torch.no_grad():out=model.icl_predictor.forward_with_repr_cache(R,**rec['kwargs'])
            cpu=out.detach().float().cpu()
            if verify_public_outputs:assert torch.equal(cpu,rec['public_output'])
            outputs.append(cpu.numpy()[0])
        avg=np.zeros_like(outputs[0]);assert len(outputs)==len(meta['class_shuffles'])
        for out,shuffle in zip(outputs,meta['class_shuffles']):avg+=out[...,shuffle]
        avg/=len(outputs)
        if meta['average_logits']:avg=TabICLClassifier.softmax(avg,axis=-1,temperature=meta['softmax_temperature'])
        probability=avg/avg.sum(axis=1,keepdims=True)
        if verify_public_outputs:assert np.array_equal(probability,group['public_probability'])
        results.append(probability)
    return np.concatenate(results)
