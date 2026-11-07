"""Only replace the last4of12ICL feedforward operations;public early8 stay fixed."""
from tabicl_gated_ffn_body import GatedFFNBlock
import torch
from torch import nn

def attach_tail_gates(model):
    assert len(model.icl_predictor.tf_icl.blocks)==12
    for block in model.icl_predictor.tf_icl.blocks[8:]:
        block.__class__=GatedFFNBlock;block.ffn_gate=nn.Linear(block.linear1.in_features,block.linear1.out_features,device=block.linear1.weight.device);nn.init.zeros_(block.ffn_gate.weight);nn.init.zeros_(block.ffn_gate.bias)
    return model

def load_tail_body(path,device):
    from tabicl._model.tabicl import TabICL
    z=torch.load(path,map_location='cpu',weights_only=False);net=attach_tail_gates(TabICL(**z['config']));net.load_state_dict(z['state_dict'],strict=True);net.to(device).eval();return net,z['config']
