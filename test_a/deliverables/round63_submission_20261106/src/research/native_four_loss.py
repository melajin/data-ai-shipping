"""The exact four-view classifier averaging rule inside the20-task objective."""
import torch
from torch.nn import functional as F

def native_evidence_scores(logits,permutations,specs,average_views=True):
    outputs={}
    for value,perms,task in zip(logits,permutations,specs):
        aligned=torch.stack([value[i].index_select(-1,perm) for i,perm in enumerate(perms)]);z=aligned.mean(0) if average_views else aligned;outputs[task['name']]=(z/.9).softmax(-1)
    template=outputs['compact_head'];pairs={arm:torch.ones((*template.shape[:-1],4,4),dtype=template.dtype,device=template.device) for arm in ['compact','state','relation']}
    for task in specs:
        if task['pair']:
            a,b=task['pair'];pa=outputs[task['name']][...,0];arm=task['name'].split('_')[0];pairs[arm][...,a,b]=pa;pairs[arm][...,b,a]=1-pa
    joint=.5*outputs['compact_head']+.5*outputs['state_head'];pair=.25*pairs['compact']+.25*pairs['state']+.5*pairs['relation'];return .5*joint.clamp_min(1e-6).log()+(.5/3)*pair.clamp_min(1e-6).log().sum(-1)

def native_evidence_objective(logits,teacher,permutations,specs,target):
    score=native_evidence_scores(logits,permutations,specs);public=native_evidence_scores(teacher,permutations,specs);views=native_evidence_scores(logits,permutations,specs,average_views=False);ce=F.cross_entropy(score,target);kl=F.kl_div(F.log_softmax(score/2.,dim=-1),F.softmax(public/2.,dim=-1),reduction='batchmean')*4.;p=views.softmax(-1);lm=p.mean(0).clamp_min(1e-12).log();js=F.kl_div(lm.expand_as(p),p,reduction='none').sum(-1).mean();return ce+kl+js,{'cross_entropy':ce,'public_teacher_T2_KL':kl,'four_view_JS':js}
