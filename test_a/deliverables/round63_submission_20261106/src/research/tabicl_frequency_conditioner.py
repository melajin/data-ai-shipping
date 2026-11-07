"""Selected part:context-frequency-conditioned label injection inside the public column encoder."""
import torch
from torch import nn
from torch.nn import functional as F
from tabicl._model.layers import OneHotAndLinear

class FrequencyConditionedLabels(OneHotAndLinear):
    def forward(self,src):
        hot=F.one_hot(src.long(),self.num_classes).to(src.dtype)
        embedding=F.linear(hot.float(),self.weight,self.bias)
        # src contains context labels only. Mean over their actual sample axis.
        frequency=hot.float().mean(dim=-2,keepdim=True)
        return embedding*(2*torch.sigmoid(self.frequency_gate(frequency)))

def attach_frequency_conditioner(model):
    assert model.col_embedder.target_aware
    layer=model.col_embedder.y_encoder;assert isinstance(layer,OneHotAndLinear) and layer.num_classes==10 and layer.out_features==128
    layer.__class__=FrequencyConditionedLabels
    layer.frequency_gate=nn.Linear(10,128,device=layer.weight.device,dtype=layer.weight.dtype)
    nn.init.zeros_(layer.frequency_gate.weight);nn.init.zeros_(layer.frequency_gate.bias)
    return model

def new_frequency_state(model):
    return {k:v.detach().cpu().clone() for k,v in model.state_dict().items() if '.frequency_gate.' in k}

def load_frequency_body(path,device='cpu'):
    from tabicl._model.tabicl import TabICL
    saved=torch.load(path,map_location='cpu',weights_only=False);model=attach_frequency_conditioner(TabICL(**saved['config']))
    model.load_state_dict(saved['state_dict'],strict=True);model.to(device);model.eval();return model,saved['config']
