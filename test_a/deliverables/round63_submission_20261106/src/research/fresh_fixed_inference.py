"""Numerical policy:fixed column,row and ICL batch sizes for memory-independent replay."""
from fresh_rounds import *
from contextlib import contextmanager
from tabicl import TabICLClassifier
from tabicl._model.inference import InferenceManager

FIXED_BATCHES={'col_embedder':64,'row_interactor':64,'icl_predictor':1}

class FixedInferenceManager(InferenceManager):
    def configure(self,**kwargs):
        kwargs['min_batch_size']=self.fixed_batch_size
        return super().configure(**kwargs)
    def estimate_safe_batch_size(self,*args,**kwargs):
        memory,_=super().estimate_safe_batch_size(*args,**kwargs)
        return memory,self.fixed_batch_size

def attach_fixed_inference(model):
    for name,size in FIXED_BATCHES.items():
        manager=getattr(model,name).inference_mgr;manager.__class__=FixedInferenceManager;manager.fixed_batch_size=size
    return model

@contextmanager
def fixed_public_inference():
    original=TabICLClassifier._load_model
    def load(estimator):
        original(estimator);attach_fixed_inference(estimator.model_)
    TabICLClassifier._load_model=load
    try:yield
    finally:TabICLClassifier._load_model=original
