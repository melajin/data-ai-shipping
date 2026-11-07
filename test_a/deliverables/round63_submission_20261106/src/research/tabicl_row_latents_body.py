"""Selected body part: replace row feature aggregation with eight latent summaries.

Original four CLS summaries cannot attend to the four added latent keys. This
preserves the original mathematical path initially,while a new learned readout
can use the added summaries. Original row and ICL weights are broadly trained.
"""
import torch
from torch import nn
from torch.nn import functional as F
from functools import partial
from torch.utils.checkpoint import checkpoint
from tabicl._model.interaction import RowInteraction
from tabicl._model.inference import InferenceManager

class FixedRowBatchManager(InferenceManager):
    def configure(self,**kwargs):
        kwargs['min_batch_size']=64
        return super().configure(**kwargs)
    def estimate_safe_batch_size(self,*args,**kwargs):
        memory,_=super().estimate_safe_batch_size(*args,**kwargs)
        return memory,64

class ExpandedRowInteraction(RowInteraction):
    def _aggregate_embeddings(self,embeddings,key_mask=None):
        old_size=embeddings.shape[-2];extra=self.extra_cls_tokens.to(embeddings.dtype).expand(*embeddings.shape[:-2],4,self.embed_dim)
        emb=torch.cat([embeddings,extra],dim=-2);size=old_size+4
        attn_mask=torch.zeros(size,size,dtype=torch.bool,device=emb.device);attn_mask[:old_size,old_size:]=True
        if key_mask is not None:key_mask=F.pad(key_mask,(0,4),value=False)
        for block in self.tf_row.blocks:
            fn=partial(block,key_padding_mask=key_mask,attn_mask=attn_mask,rope=self.tf_row.rope)
            emb=checkpoint(fn,emb,use_reentrant=False) if self.recompute and torch.is_grad_enabled() else fn(emb)
        summaries=torch.cat([emb[...,:4,:],emb[...,old_size:,:]],dim=-2)
        return self.cls_readout(self.out_ln(summaries).flatten(-2))

def attach_row_latents(model):
    row=model.row_interactor;assert row.num_cls==4 and row.embed_dim==128 and len(row.tf_row.blocks)==3
    row.__class__=ExpandedRowInteraction
    row.inference_mgr=FixedRowBatchManager(enc_name='tf_row',out_dim=512,out_no_seq=True)
    row.extra_cls_tokens=nn.Parameter(torch.empty(4,128,device=row.cls_tokens.device))
    nn.init.trunc_normal_(row.extra_cls_tokens,std=.02)
    row.cls_readout=nn.Linear(1024,512,device=row.cls_tokens.device)
    with torch.no_grad():
        row.cls_readout.weight.zero_();row.cls_readout.bias.zero_();row.cls_readout.weight[:,:512].copy_(torch.eye(512,device=row.cls_tokens.device))
    return model

def new_row_state(model):
    return {k:v.detach().cpu().clone() for k,v in model.state_dict().items() if '.extra_cls_tokens' in k or '.cls_readout.' in k}

def load_row_latent_body(path,device='cpu'):
    from tabicl._model.tabicl import TabICL
    saved=torch.load(path,map_location='cpu',weights_only=False);model=attach_row_latents(TabICL(**saved['config']))
    model.load_state_dict(saved['state_dict'],strict=True);model.to(device);model.eval();return model,saved['config']

def self_check():
    from tabicl._model.tabicl import TabICL
    import copy
    torch.set_num_threads(2);torch.manual_seed(430)
    model=TabICL(embed_dim=128,row_num_cls=4,col_num_blocks=1,row_num_blocks=3,icl_num_blocks=1,zero_init=False)
    original=copy.deepcopy(model.row_interactor);changed=attach_row_latents(model).row_interactor
    x=torch.randn(1,5,17,128);x[:,:,:4]=original.cls_tokens
    a=original._aggregate_embeddings(x.clone());b=changed._aggregate_embeddings(x.clone())
    assert a.shape==b.shape==(1,5,512) and torch.allclose(a,b,atol=3e-6,rtol=2e-5)
    opt=torch.optim.AdamW(changed.parameters(),lr=.001)
    for step in range(2):
        opt.zero_grad();out=changed._aggregate_embeddings(x.detach().clone());out.square().mean().backward()
        assert changed.cls_readout.weight.grad.abs().sum()>0
        if step:assert changed.extra_cls_tokens.grad.abs().sum()>0
        assert changed.tf_row.blocks[0].attn.in_proj_weight.grad.abs().sum()>0
        opt.step()
    assert not torch.allclose(changed._aggregate_embeddings(x.detach().clone()),a)
    # Rows remain independent inside this row module.
    altered=x.detach().clone();altered[:,1]+=100
    assert torch.allclose(changed._aggregate_embeddings(x.detach().clone())[:,0],changed._aggregate_embeddings(altered)[:,0],atol=1e-6,rtol=1e-5)
    print('ROW_LATENTS_SYNTHETIC_PREFLIGHT_PASSED:initial public path,original+new gradients,row isolation',flush=True)

if __name__=='__main__':self_check()
