"""Exhaustive same gradient checks,with one device synchronization per body module."""
import torch

def gradient_statistics(named_parameters):
    grouped={}
    for name,param in named_parameters:
        values=grouped.setdefault(name.split('.')[0],[])
        if param.grad is not None:values.append(param.grad)
    result={}
    with torch.no_grad():
        for module,gradients in grouped.items():
            if not gradients:
                result[module]={'tensors_with_finite_nonzero_grad':0,'finite':True};continue
            # Inspect every element of every tensor,as in the previous audit.
            # Transfer only the small boolean table once,instead of two scalar
            # GPU/CPU synchronizations for every individual parameter tensor.
            flags=torch.stack([torch.stack([torch.isfinite(g).all(),torch.count_nonzero(g)>0]) for g in gradients]).cpu().tolist()
            result[module]={'tensors_with_finite_nonzero_grad':sum(int(v[1]) for v in flags),'finite':all(v[0] for v in flags)}
    return result
