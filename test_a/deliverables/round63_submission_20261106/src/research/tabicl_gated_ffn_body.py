"""Prepared body substitution: replace the FFN operation in all12 ICL blocks.

No fitting on import. The original public FFN weights initialize the value path.
The added gate has full input/hidden dimensions;original ICL weights are trainable.
"""
import torch
from torch import nn
from torch.nn import functional as F

def attach_gated_ffn(model):
    from tabicl._model.layers import MultiheadAttentionBlock
    class_name=GatedFFNBlock
    blocks=model.icl_predictor.tf_icl.blocks
    assert len(blocks)==12
    for block in blocks:
        assert isinstance(block,MultiheadAttentionBlock)
        block.__class__=class_name
        block.ffn_gate=nn.Linear(block.linear1.in_features,block.linear1.out_features,device=block.linear1.weight.device)
        nn.init.zeros_(block.ffn_gate.weight);nn.init.zeros_(block.ffn_gate.bias)
    return model

def _block_class():
    from tabicl._model.layers import MultiheadAttentionBlock
    class _GatedFFNBlock(MultiheadAttentionBlock):
        def _ff_block(self,x):
            value=self.activation(self.linear1(x))
            gate=2*torch.sigmoid(self.ffn_gate(x))
            return self.dropout2(self.linear2(self.dropout(value*gate)))
    return _GatedFFNBlock

GatedFFNBlock=_block_class()

def load_gated_body(path,device='cpu'):
    from tabicl._model.tabicl import TabICL
    saved=torch.load(path,map_location='cpu',weights_only=False)
    net=attach_gated_ffn(TabICL(**saved['config']))
    net.load_state_dict(saved['state_dict'],strict=True);net.to(device);net.eval();return net,saved['config']

def self_check():
    from tabicl._model.layers import MultiheadAttentionBlock
    torch.manual_seed(411);base=MultiheadAttentionBlock(16,4,32,zero_init=False)
    import copy
    changed=copy.deepcopy(base);changed.__class__=GatedFFNBlock;changed.ffn_gate=nn.Linear(16,32)
    nn.init.zeros_(changed.ffn_gate.weight);nn.init.zeros_(changed.ffn_gate.bias)
    x=torch.randn(2,12,16);p=base(x,train_size=8);q=changed(x,train_size=8)
    assert torch.equal(p,q)
    opt=torch.optim.AdamW(changed.parameters(),lr=.001);q.square().mean().backward()
    assert torch.isfinite(changed.ffn_gate.weight.grad).all() and changed.ffn_gate.weight.grad.abs().sum()>0
    assert changed.linear1.weight.grad.abs().sum()>0 and changed.attn.in_proj_weight.grad.abs().sum()>0
    opt.step();assert not torch.equal(changed(x,train_size=8),p)
    # With context-only keys,the first query's prediction cannot depend on another query.
    altered=x.clone();altered[:,9]+=100
    assert torch.equal(changed(x,train_size=8)[:,8],changed(altered,train_size=8)[:,8])
    print('GATED_FFN_SYNTHETIC_PREFLIGHT_PASSED:identity initialization,original+gate gradients,query isolation')

if __name__=='__main__':self_check()
