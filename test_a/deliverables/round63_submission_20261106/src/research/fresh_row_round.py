"""Round26: change learning unit to observed hourly records, pool by vessel."""
from fresh_row_contexts import *
from fresh_best_reference import fit_reference
from fresh_hierarchy_round import hierarchy_scores


def choose_records(reference,newprob,y,tu):
    best=None;choices=[]
    for gamma in [0.,.25,.5,.75,1.]:
        scores=hierarchy_scores(reference['joint'],reference['pair'],newprob,reference['alpha'],reference['weights'],gamma)
        pr=scores.argmax(1);m=metrics(y[tu],pr[tu]);key=(int((pr[tu]==y[tu]).sum()),m['macro_f1'],-gamma)
        choices.append({'gamma':gamma,'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']})
        if best is None or key>best[0]:best=(key,gamma,pr,scores)
    return best[1:],choices


def main():
    rd=start(26,'Hourly-record classification with diverse actual-record contexts, vessel probability pooling, matched repeat-context control')
    for name in ['fresh_row_round.py','fresh_row_contexts.py','fresh_best_reference.py','fresh_relation_basis.py','fresh_hierarchy_round.py']:
        shutil.copy2(B/name,rd/name)
    dump(rd/'predeclared_protocol.json',{'primary_change':'Change from vessel-summary training to hourly-record training; every row context contains exactly one actual record per FIT vessel, labeled with its official vessel gear.',
        'row_features':'16 original-geometry features plus sin/cos of supplied hour. All from the same selected record; no full-view statistics inserted into a cropped observation.',
        'record_eligibility':'Measured original line length>0.05km, fallback to all actual records if none qualify. Same rule for FIT and query, no vessels dropped, not a fishing-action annotation.',
        'primary_arm':'Two freshly fitted row models use distinct actual records A/B for each FIT boat where possible, equal natural vessel class counts.',
        'control_arm':'Two freshly fitted row models both use actual record A, with exactly the same two model seeds/4 estimators as primary. All four fits actually executed; no old predictions.',
        'query':'Up to8 actual records per held-out boat; mean probability across records and both models. Evaluation remains one prediction per vessel, never row-weighted F1.',
        'reference':'All80 prior-design task fits and FIT-only prototype/scaler fits recalculated in this round. No fine-tuned weights from25 used.',
        'selection':'Five final log-evidence blend values on TUNE Micro/macro/less-change, independently for primary and matched control. This permits row evidence even when reference head weight is0. Primary fixed to diverse arm before REPORT.',
        'total_model_fits':96,'gradient_updates':False})
    restrict_old_rounds(26);s,base=load();sub=s.loc[s.split!='FIT'];tu=sub.split.eq('TUNE').to_numpy();qy=sub.y.to_numpy()
    build_inputs(rd,s);ref=fit_reference(rd,s,base)
    prob={};pairs={};final={};decisions={};controls={}
    for v in VIEWS:
        diverse=row_arm(rd,s,v,'diverse');repeat=row_arm(rd,s,v,'repeat_control')
        (gamma,final[v],scores),cand=choose_records(ref[v],diverse,qy,tu)
        (cg,cp,cs),cc=choose_records(ref[v],repeat,qy,tu)
        prob[v]=ref[v]['joint'];pairs[v]=ref[v]['pair'];np.save(rd/f'final_scores_{v}.npy',scores)
        decisions[v]={'reference':ref[v]['policy'],'row_gamma':gamma,'row_candidates':cand,'control_gamma':cg,'control_candidates':cc}
        controls[v]={'fresh_best_design_prediction':ref[v]['prediction'],'matched_repeat_selected_prediction':cp,'raw_diverse_row_prediction':diverse.argmax(1),'raw_repeat_row_prediction':repeat.argmax(1)}
        print('FRESH_ROW_SELECTION',v,json.dumps(decisions[v]),flush=True)
    complete(rd,s,base,prob,pairs,final,decisions,controls)


if __name__=='__main__':main()
