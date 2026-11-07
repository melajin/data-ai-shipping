"""Replace only the decoder's hidden transform;keep exact public function at initialization."""
import torch
from torch import nn

class GatedDecoder(nn.Sequential):
    def forward(self,x):
        return self[2](self[1](self[0](x))*(2*torch.sigmoid(self.gate(x))))

def attach_gated_decoder(model):
    decoder=model.icl_predictor.decoder
    assert len(decoder)==3 and decoder[0].in_features==512 and decoder[0].out_features==1024
    decoder.__class__=GatedDecoder
    decoder.gate=nn.Linear(512,1024,device=decoder[0].weight.device,dtype=decoder[0].weight.dtype)
    nn.init.zeros_(decoder.gate.weight);nn.init.zeros_(decoder.gate.bias)
    return model

def new_decoder_state(model):
    return {k:v.detach().cpu().clone() for k,v in model.state_dict().items() if '.decoder.gate.' in k}

def load_gated_decoder_body(path,device='cpu'):
    from tabicl._model.tabicl import TabICL
    saved=torch.load(path,map_location='cpu',weights_only=False);model=attach_gated_decoder(TabICL(**saved['config']))
    model.load_state_dict(saved['state_dict'],strict=True);model.to(device);model.eval();return model,saved['config']
