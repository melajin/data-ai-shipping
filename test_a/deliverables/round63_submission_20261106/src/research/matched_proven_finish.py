from matched_proven_training import *
from fresh_primary_reference import short_original_reference

def finish_matched(rd,s,base,ref,pred,audit,config_updates=None,*,update_session=True):
    sub=s.loc[s.split!='FIT'];tu=sub.split.eq('TUNE').to_numpy();y=sub.y.to_numpy()
    cfg=json.loads((rd/'config.json').read_text(encoding='utf-8'));cfg.update(gradient_updates=True,weights_changed=True,broad_TabICLv2_body_finetuning=True,matched_proven_body=True,development_parent_rounds=[19,28,41,49],positive_body_weight_required=True,updated_modules=['icl_predictor'],gradient_description='0.61초과19/28차의실제20작업기준,41차의내부FFN교체구조,49차의CE/공개KL/JS를발전시켰다. 41차의거절된가중치는쓰지않고공개원본과새0게이트부터시작했다. ICL12블록의원본을넓게학습하고내부FFN게이트6303744개를학습했다. 열·행·레이블주입은공개원본고정이다. 실제150/337/402의동일20작업을FIT2폴드·none/power·순환레이블뷰로학습하고배포했다. 공개동결표현을캐시해매검증에서ICL만재계산했다.');dump(rd/'config.json',cfg)
    if config_updates:
        cfg.update(config_updates);dump(rd/'config.json',cfg)
    dd=rd/'wide_body'/f'deployment_validation_{audit["selected_epoch"]:02}';j=np.load(dd/'joint.npy');p=np.load(dd/'pair.npy');prob={};pairs={};final={};decisions={};controls={}
    for v in VIEWS:
        original=np.load(rd/'wide_body'/f'unadapted_head_{v}.npy');r=ref if v=='full' else short_original_reference(rd,v,original,y,tu);jj,pp=(j,p) if v=='full' else (pred[v],np.ones((len(y),4,4)))
        best,out,choices,zero=choose_matched(r,jj,pp,y,tu);pr,score,prob[v],pairs[v]=out;final[v]=pr;np.save(rd/f'final_scores_{v}.npy',score)
        decisions[v]={'reference':r['policy'],'positive_gamma':best['gamma'],'choice':best,'candidates':choices,'zero_strictly_better':choices[0]['TUNE_correct']>best['TUNE_correct'],'epoch0_excluded':True};controls[v]={'fresh_best_design_prediction':zero[0],'raw_broad_body_prediction':pred[v].argmax(1),'raw_matched_original_prediction':original.argmax(1)}
    rejected=bool(decisions['full']['zero_strictly_better'] or audit['zero_weight_stop_triggered']);dump(rd/'body_acceptance_before_REPORT.json',{'rejected_because_zero_weight_higher_TUNE':rejected,'candidate_body_weight':decisions['full']['positive_gamma'],'trained_body_changed':True});return complete(rd,s,base,prob,pairs,final,decisions,controls,eligible_for_best=not rejected,update_session=update_session)
