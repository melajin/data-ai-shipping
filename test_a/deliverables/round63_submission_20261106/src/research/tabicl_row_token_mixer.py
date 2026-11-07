"""Explicit TabICLv2 architecture change, with an identity initial function."""
import torch
from torch import nn

class RowTokenMixer(nn.Module):
    def __init__(self,base):
        super().__init__();self.base=base;self.num_cls=base.num_cls;self.embed_dim=base.embed_dim;self.bypass=False
        self.norm=nn.LayerNorm(self.embed_dim)
        self.attention=nn.MultiheadAttention(self.embed_dim,4,dropout=0.,batch_first=True)
        self.gate=nn.Linear(self.num_cls*self.embed_dim,self.num_cls)
        nn.init.zeros_(self.attention.out_proj.weight);nn.init.zeros_(self.attention.out_proj.bias)
        nn.init.zeros_(self.gate.weight);nn.init.constant_(self.gate.bias,-2.)

    def mix(self,out):
        shape=out.shape
        # The base inference manager may return half tensors outside autocast.
        # Keep this small added module in FP32 and restore the original dtype.
        with torch.autocast(device_type=out.device.type,enabled=False):
            tokens=out.float().reshape(-1,self.num_cls,self.embed_dim);z=self.norm(tokens)
            delta,_=self.attention(z,z,z,need_weights=False)
            gates=torch.sigmoid(self.gate(out.float().reshape(-1,self.num_cls*self.embed_dim))).unsqueeze(-1)
        return out+(gates*delta).reshape(shape).to(out.dtype)

    def forward(self,*args,**kwargs):
        out=self.base(*args,**kwargs)
        return out if self.bypass else self.mix(out)

    def new_state(self):
        return {k:v.detach().cpu().clone() for k,v in self.state_dict().items() if not k.startswith('base.')}


def load_custom_tabicl_checkpoint(path,device='cpu'):
    """Custom checkpoints require this architecture-aware loader, not vanilla loading."""
    from tabicl._model.tabicl import TabICL
    saved=torch.load(path,map_location='cpu',weights_only=False);net=TabICL(**saved['config'])
    if any(k.startswith('row_interactor.base.') for k in saved['state_dict']):net.row_interactor=RowTokenMixer(net.row_interactor)
    net.load_state_dict(saved['state_dict'],strict=True);return net.to(device).eval()
