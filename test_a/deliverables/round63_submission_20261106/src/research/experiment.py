from pathlib import Path
import sys,json,time,hashlib,gc,itertools,shutil
B=Path(__file__).resolve().parent;sys.path.insert(0,str(B/'vendor'))
import numpy as np,pandas as pd,torch
from tabicl import TabICLClassifier
from sklearn.metrics import f1_score,confusion_matrix,precision_recall_fscore_support,accuracy_score

CLASSES=['연안복합','자망','통발','채낚기연승낚시'];VIEWS=['full','d1','d3','d7'];SEED=20261105
TRANSITION_DELTA=.01  # Latest user rule from round28; earlier snapshots retain their historical .03 rule.
CHECKPOINT=B.parent/'1105_신규아이디어'/'pretrained'/'tabicl-classifier-v2-20260212.ckpt'
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load():
    s=pd.read_csv(B/'fixed_split.csv',index_col='id');xx={v:pd.read_csv(B/f'features_{v}.csv',index_col='id').reindex(s.index) for v in VIEWS}
    assert s.index.is_unique and all(x.index.equals(s.index) for x in xx.values())
    assert set(s.split)=={'FIT','TUNE','REPORT'}
    return s,xx
def model(seed=SEED,estimators=2):
    return TabICLClassifier(n_estimators=estimators,batch_size=1,model_path=CHECKPOINT,allow_auto_download=False,device='cuda',use_amp=True,use_fa3=False,kv_cache='repr',n_jobs=4,random_state=seed)
def predict(ctx_x,ctx_y,query_x,seed=SEED,estimators=2):
    ctx_x=np.asarray(ctx_x,dtype=np.float32);query_x=np.asarray(query_x,dtype=np.float32)
    ctx_x=np.where(np.isfinite(ctx_x),ctx_x,np.nan);query_x=np.where(np.isfinite(query_x),query_x,np.nan)
    t=time.time();m=model(seed,estimators);m.fit(ctx_x,ctx_y)
    pred=[]
    for i in range(0,len(query_x),1000):pred.append(m.predict_proba(query_x[i:i+1000]))
    pred=np.concatenate(pred);classes=m.classes_.copy()
    print(f'TABICL context={len(ctx_y)} query={len(query_x)} features={ctx_x.shape[1]} classes={classes.tolist()} sec={time.time()-t:.2f}',flush=True)
    del m;gc.collect();torch.cuda.empty_cache()
    assert np.isfinite(pred).all()
    return pred,classes
def thresholds(p,y):
    ts=[]
    for c in range(4):
        candidates=np.arange(.05,.851,.025)
        scores=[f1_score(y==c,p[:,c]>=t,zero_division=0) for t in candidates]
        # deterministic tie rule: choose the threshold nearest 0.5, then smaller.
        best=max(range(len(scores)),key=lambda i:(scores[i],-abs(candidates[i]-.5),-candidates[i]))
        ts.append(float(candidates[best]))
    return np.array(ts)
def tags(p,t):return p>=t
def maskcode(tag):return (tag*np.array([1,2,4,8])).sum(axis=1).astype(int)
def original(tag):
    result=[]
    for row in tag:
        z=set(np.flatnonzero(row))
        if not z:r=0
        elif len(z)==1:r=next(iter(z))
        else:
            z.discard(3)
            if 1 in z and 2 in z:r=0
            elif 1 in z:r=1
            elif 2 in z:r=2
            else:r=0
        result.append(r)
    return np.array(result)
def metrics(y,p):
    pr,re,f,sup=precision_recall_fscore_support(y,p,labels=range(4),zero_division=0)
    micro=f1_score(y,p,average='micro');assert abs(micro-accuracy_score(y,p))<1e-12
    cm=confusion_matrix(y,p,labels=range(4))
    return {'n':len(y),'micro_f1':micro,'macro_f1':float(np.mean(f)),'f1':dict(zip(CLASSES,map(float,f))),'precision':dict(zip(CLASSES,map(float,pr))),'recall':dict(zip(CLASSES,map(float,re))),'support':dict(zip(CLASSES,map(int,sup))),'confusion_true_rows_pred_cols':cm.tolist(),'gillnet_to_complex_rate':float(cm[1,0]/max(sup[1],1)),'trap_to_complex_rate':float(cm[2,0]/max(sup[2],1))}
def evaluate(rd,s,xx,prob,t,final=None,extra=None):
    allmetrics={};groups=[];flows=[]
    report=s.split.eq('REPORT').to_numpy();tune=s.split.eq('TUNE').to_numpy();mask=report|tune
    sub=s.loc[mask];truth=sub.y.to_numpy()
    for v in VIEWS:
        tag=tags(prob[v],t);base=original(tag);pred=base if final is None else final[v]
        d=sub.copy();d['view']=v;d['tag_code']=maskcode(tag);d['tag_count']=tag.sum(axis=1);d['before']=base;d['prediction']=pred
        for c in range(4):d[f'judge_p{c}']=prob[v][:,c]
        if extra is not None:
            for k,z in extra.get(v,{}).items():d[k]=z
        d.to_csv(rd/f'predictions_{v}.csv',encoding='utf-8-sig')
        allmetrics[v]={}
        for sp in ['TUNE','REPORT']:
            z=d.split.eq(sp).to_numpy();allmetrics[v][sp]=metrics(truth[z],pred[z]);allmetrics[v][sp]['before_reinspection']=metrics(truth[z],base[z])
            truth_in_tags=tag[np.arange(len(tag)),truth];final_in_tags=tag[np.arange(len(tag)),pred]
            allmetrics[v][sp]['true_class_candidate_inclusion_rate']=float(truth_in_tags[z].mean())
            allmetrics[v][sp]['true_class_missing_from_candidates_n']=int((z&~truth_in_tags).sum())
            allmetrics[v][sp]['recovered_true_class_outside_candidates_n']=int((z&~truth_in_tags&(pred==truth)).sum())
            allmetrics[v][sp]['final_prediction_outside_candidates_n']=int((z&~final_in_tags).sum())
            for code,g in d.loc[z].groupby('tag_code'):
                rec={'view':v,'split':sp,'tag_code':int(code),'tags':'+'.join(CLASSES[i] for i in range(4) if code&(1<<i)) or '없음','n':len(g),'before_correct':int((g.y==g.before).sum()),'after_correct':int((g.y==g.prediction).sum())}
                rec.update({f'true_{CLASSES[c]}':int((g.y==c).sum()) for c in range(4)});groups.append(rec)
            for (before,after),g in d.loc[z].groupby(['before','prediction']):flows.append({'view':v,'split':sp,'before':int(before),'after':int(after),'n':len(g),'rescued':int(((g.y!=g.before)&(g.y==g.prediction)).sum()),'damaged':int(((g.y==g.before)&(g.y!=g.prediction)).sum())})
    # Natural observation strata use the full input, independent of labels and every round.
    d=pd.read_csv(rd/'predictions_full.csv',index_col='id');d=d.loc[d.split=='REPORT'];f=xx['full'].loc[d.index]
    strata={}
    for col,bins,names in [('n_days',[-1,3,7,30,np.inf],['1-3','4-7','8-30','31+']),('n_rows',[-1,24,72,168,np.inf],['1-24','25-72','73-168','169+']),('length_sum_km',[-1,1,10,100,np.inf],['0-1km','1-10km','10-100km','100km+'])]:
        stratum=pd.cut(f[col],bins=bins,labels=names,right=True)
        strata[col]={}
        for name in names:
            z=stratum.eq(name).to_numpy();strata[col][name]=metrics(d.y.to_numpy()[z],d.prediction.to_numpy()[z]) if z.any() else {'n':0}
    pd.DataFrame(groups).to_csv(rd/'tag_combinations.csv',index=False,encoding='utf-8-sig');pd.DataFrame(flows).to_csv(rd/'reinspection_flows.csv',index=False)
    dump(rd/'metrics.json',allmetrics);dump(rd/'natural_short_strata.json',strata)
    print('ROUND_RESULT',json.dumps(allmetrics['full']['REPORT'],ensure_ascii=False),flush=True)
    return allmetrics
def setup_round(n,config):
    rd=B/f'round_{n:02d}';rd.mkdir(exist_ok=False)
    for p in [B/'experiment.py',B/'build_inputs.py',B/'fixed_split.csv',B/'input_spec.json']:
        shutil.copy2(p,rd/p.name)
    config.update({'seed':SEED,'checkpoint':str(CHECKPOINT),'checkpoint_sha256':sha(CHECKPOINT),'source_manifest_sha256':sha(B/'source_manifest.json'),'features_sha256':{v:sha(B/f'features_{v}.csv') for v in VIEWS},'weights_changed':False,'report_status':'repeated development evaluation; not independent final or official Test F1','ensemble':config.get('ensemble',2),'inference':'cuda float16, batch_size 1, repr cache; 1000 queries/batch'})
    dump(rd/'config.json',config);return rd
def finish_round(n,m,note):
    curr=m['full']['REPORT']['micro_f1'];prev=None
    if n>1:prev=json.loads((B/f'round_{n-1:02d}'/'metrics.json').read_text(encoding='utf-8'))['full']['REPORT']['micro_f1']
    delta=None if prev is None else curr-prev
    dump(B/f'round_{n:02d}'/'feedback.json',{'round':n,'micro_f1':curr,'previous_new_round_micro':prev,'absolute_improvement':delta,'transition_required_improvement':TRANSITION_DELTA,'improvement_requirement_met':None if delta is None else bool(delta>=TRANSITION_DELTA),'next_must_change_core_structure':False if delta is None else bool(delta<TRANSITION_DELTA),'note':note,'only_feedback_used':'this independent session metrics and the user feedback explicitly in the request'})
def round1():
    s,xx=load();fit=s.split.eq('FIT').to_numpy();q=s.split.ne('FIT').to_numpy();sub=s.loc[q];tune=sub.split.eq('TUNE').to_numpy()
    rd=setup_round(1,{'design':'four independent one-versus-rest TabICLv2 tasks; original label-combination rules','training_task':'each class vs other three, natural class prior, all FIT vessels','threshold_selection':'TUNE full-view per-judge binary F1; grid .05 to .85 step .025','next_transition_rule':'first round has no previous comparison'})
    query=np.concatenate([xx[v].loc[q].to_numpy() for v in VIEWS]);p=np.empty((len(query),4))
    for c in range(4):
        pp,cc=predict(xx['full'].loc[fit],(s.y.to_numpy()[fit]==c).astype(int),query,SEED+c)
        p[:,c]=pp[:,list(cc).index(1)]
        np.save(rd/f'judge_{c}_raw.npy',p[:,c])
    prob=dict(zip(VIEWS,np.split(p,4)));ts=thresholds(prob['full'][tune],sub.y.to_numpy()[tune]);dump(rd/'thresholds.json',ts.tolist())
    for v,z in prob.items():np.save(rd/f'prob_{v}.npy',z)
    m=evaluate(rd,s,xx,prob,ts)
    finish_round(1,m,'First independent measurement. Inspect singleton correctness, no-tag truth distribution and complex/gillnet/trap confusion before choosing the next structure.')
def pair_decision(tag,pair,mode='priority'):
    base=original(tag);out=base.copy();wins=(pair>.5).sum(axis=2)
    for i,row in enumerate(tag):
        z=set(np.flatnonzero(row))
        if not z:continue
        if mode=='priority' and 0 in z and 1 in z:
            out[i]=0 if pair[i,0,1]>.5 else 1
        elif mode=='priority' and 0 in z and 2 in z:
            out[i]=0 if pair[i,0,2]>.5 else 2
        elif mode=='priority' and 1 in z and 2 in z:
            out[i]=1 if pair[i,1,2]>.5 else 2
        else:
            champion=np.flatnonzero(wins[i]==3)
            if len(champion)==1:out[i]=champion[0]
    return out
def round2():
    s,xx=load();fit=s.split.eq('FIT').to_numpy();q=s.split.ne('FIT').to_numpy();sub=s.loc[q]
    rd=setup_round(2,{'design':'six pairwise contrast reinspection tasks and candidate-combination routing','training_task':'Each verifier sees only the two true classes it must distinguish; every query is evaluated by all six. No base training predictions are used as verifier training data. C+G has pairwise priority even if P/D also appear; C+P and G+P get direct contrast. Singleton decisions are challenged by a unanimous pairwise champion. No-label remains C.','core_change_from_previous':'New pair-specific context labels and six independent reinspection tasks replace unconditional singleton and mixed-label assertions. The original four judges still evaluate every query.','previous_result_used':'round_01 only: Micro .4542, C->G errors 342/730, trap F1 .2174'})
    prob={v:np.load(B/'round_01'/f'prob_{v}.npy') for v in VIEWS};ts=np.array(json.loads((B/'round_01'/'thresholds.json').read_text()))
    query=np.concatenate([xx[v].loc[q].to_numpy() for v in VIEWS]);pair=np.zeros((len(query),4,4));y=s.y.to_numpy()
    for a,b in itertools.combinations(range(4),2):
        ctx=fit&np.isin(y,[a,b]);pp,cc=predict(xx['full'].loc[ctx],y[ctx],query,SEED+10*a+b)
        pair[:,a,b]=pp[:,list(cc).index(a)];pair[:,b,a]=1-pair[:,a,b]
    pv=dict(zip(VIEWS,np.split(pair,4)));final={v:pair_decision(tags(prob[v],ts),pv[v]) for v in VIEWS}
    for v in VIEWS:np.save(rd/f'pair_{v}.npy',pv[v]);np.save(rd/f'prob_{v}.npy',prob[v])
    dump(rd/'thresholds.json',ts.tolist())
    m=evaluate(rd,s,xx,prob,ts,final)
    finish_round(2,m,'Separate pair tasks test the user hypotheses instead of asserting them. Next design must change its core if absolute Micro-F1 improvement is below 0.10; inspect rescued versus damaged singleton/mixed decisions and short-view performance.')
def meta_input(x,p,t):
    tg=tags(p,t);before=original(tg)
    return np.column_stack([np.asarray(x),p,tg.astype(float),np.eye(4)[before],tg.sum(axis=1)])
def choose_meta_weights(p,y):
    best=(-1,None)
    for g,tr,d in itertools.product([.8,1.,1.2,1.4],[1.,1.5,2.,2.5],[.8,1.,1.2]):
        w=np.array([1,g,tr,d]);pr=(p*w).argmax(axis=1)
        score=.6*f1_score(y,pr,average='micro')+.4*f1_score(y,pr,labels=range(4),average='macro',zero_division=0)
        if score>best[0]+1e-12:best=(score,w)
    return best[1],best[0]
def get_oof(rd,s,xx,train_views=None,query_views=('full',)):
    fit=s.split.eq('FIT').to_numpy();fids=s.index[fit];y=s.y.to_numpy();folds=s.fold.to_numpy()
    xxtrain=xx['full'].copy()
    if train_views is not None:
        for v in VIEWS:
            z=fit&(train_views==v);xxtrain.loc[z]=xx[v].loc[z]
    oof={v:np.zeros((fit.sum(),4)) for v in query_views};positions=np.flatnonzero(fit)
    provenance=[]
    for fold in [0,1]:
        ctx=fit&(folds!=fold);held=fit&(folds==fold)
        assert not(set(s.index[ctx])&set(s.index[held]))
        np.save(rd/f'oof_context_ids_fold{fold}.npy',s.index[ctx].to_numpy());np.save(rd/f'oof_query_ids_fold{fold}.npy',s.index[held].to_numpy())
        query=np.concatenate([xx[v].loc[held].to_numpy() for v in query_views]);dest=np.isin(positions,np.flatnonzero(held))
        for c in range(4):
            p,cc=predict(xxtrain.loc[ctx],(y[ctx]==c).astype(int),query,SEED+100*fold+c)
            for v,z in zip(query_views,np.split(p[:,list(cc).index(1)],len(query_views))):oof[v][dest,c]=z
        provenance.append({'fold':fold,'context_n':int(ctx.sum()),'query_n':int(held.sum()),'id_overlap':0,'train_view':'full' if train_views is None else 'one independently sampled observation budget per FIT vessel'})
    dump(rd/'oof_provenance.json',provenance)
    for v,z in oof.items():np.save(rd/f'oof_judges_{v}.npy',z)
    return oof,xxtrain
def round3():
    s,xx=load();fit=s.split.eq('FIT').to_numpy();q=s.split.ne('FIT').to_numpy();sub=s.loc[q];tune=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy()
    rd=setup_round(3,{'design':'cross-fitted label-error correction TabICLv2 with candidate evidence and measured geometry','training_task':'A distinct 4-class reinspection task learns actual class from unseen-by-base FIT cross-predictions, tag bits, original routed proposal and geometry. It can overturn singleton/no-label/mixed assertions. The final decision is learned error correction, not the highest of the four original judge scores.','core_change_from_previous':'Pair routing is replaced by an error-correction learning task trained on 2-fold out-of-context FIT predictions. User C+G priority becomes an input hypothesis rather than a forced elimination.','bias_control':'Both folds exclude all observations and all truncated versions of the queried vessel; exact context/query IDs and zero overlap saved. The OOF contexts are half-FIT, so a calibration distribution difference remains.','policy_selection':'TUNE only, fixed 48 candidate class-cost weights, objective 0.6 Micro + 0.4 macro F1. REPORT never chooses weights.','previous_result_used':'round_02 only plus round_01: higher Micro but gillnet/trap -> C error worsened'})
    prob={v:np.load(B/'round_01'/f'prob_{v}.npy') for v in VIEWS};ts=np.array(json.loads((B/'round_01'/'thresholds.json').read_text()))
    oof,_=get_oof(rd,s,xx)
    train=meta_input(xx['full'].loc[fit],oof['full'],ts)
    query=np.concatenate([meta_input(xx[v].loc[q],prob[v],ts) for v in VIEWS])
    pp,cc=predict(train,y[fit],query,SEED+300)
    assert list(cc)==[0,1,2,3]
    mp=dict(zip(VIEWS,np.split(pp,4)));w,obj=choose_meta_weights(mp['full'][tune],sub.y.to_numpy()[tune])
    final={v:(mp[v]*w).argmax(axis=1) for v in VIEWS}
    for v in VIEWS:np.save(rd/f'prob_{v}.npy',prob[v]);np.save(rd/f'meta_prob_{v}.npy',mp[v])
    dump(rd/'thresholds.json',ts.tolist());dump(rd/'decision_weights.json',{'weights':w.tolist(),'TUNE_objective':obj})
    m=evaluate(rd,s,xx,prob,ts,final)
    finish_round(3,m,'This is learned out-of-context correction rather than a repeated identical judgment. Inspect whether full-history FIT context is mismatched to first-day queries. If improvement <0.10, change the observation-budget training task rather than only the class weights.')
def round4():
    s,xx=load();fit=s.split.eq('FIT').to_numpy();q=s.split.ne('FIT').to_numpy();sub=s.loc[q];tune=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy()
    rd=setup_round(4,{'design':'observation-budget-matched cross-fitted judges and error reinspection','training_task':'Each FIT vessel supplies exactly one independently sampled observation budget: full .25, first day .35, first 3 days .20, first 7 days .20. Both four judges and the correction task learn from this mixture. No vessel duplication in context. Each OOF query and all its versions are excluded from its base context.','core_change_from_previous':'Changes the supervised observation task from only whole-window training to censored-observation training and cross-predicts all observation budgets; this is the mandatory structural change after round_03 improvement below 0.10.','policy_selection':'TUNE only 0.6 Micro + 0.4 macro F1 across the four fixed observation budgets with equal weight. Full REPORT remains the transition metric.','previous_result_used':'round_03 .5790 Micro; trap correction partially improved but whole-window context still mismatched to short inputs'})
    rng=np.random.default_rng(SEED+400);train_views=np.full(len(s),'full',dtype='U4');train_views[fit]=rng.choice(VIEWS,size=fit.sum(),p=[.25,.35,.2,.2])
    pd.DataFrame({'id':s.index[fit],'view':train_views[fit]}).to_csv(rd/'training_observation_budgets.csv',index=False)
    oof,xt=get_oof(rd,s,xx,train_views,VIEWS)
    query=np.concatenate([xx[v].loc[q].to_numpy() for v in VIEWS]);pp=np.zeros((len(query),4))
    for c in range(4):
        p,cc=predict(xt.loc[fit],(y[fit]==c).astype(int),query,SEED+400+c);pp[:,c]=p[:,list(cc).index(1)]
    prob=dict(zip(VIEWS,np.split(pp,4)))
    ts=thresholds(np.concatenate([prob[v][tune] for v in VIEWS]),np.tile(sub.y.to_numpy()[tune],4))
    op=np.zeros((fit.sum(),4));fitviews=train_views[fit]
    for v in VIEWS:
        z=fitviews==v;op[z]=oof[v][z]
    train=meta_input(xt.loc[fit],op,ts)
    query=np.concatenate([meta_input(xx[v].loc[q],prob[v],ts) for v in VIEWS]);mp,cc=predict(train,y[fit],query,SEED+450)
    assert list(cc)==[0,1,2,3]
    metap=dict(zip(VIEWS,np.split(mp,4)));w,obj=choose_meta_weights(np.concatenate([metap[v][tune] for v in VIEWS]),np.tile(sub.y.to_numpy()[tune],4))
    final={v:(metap[v]*w).argmax(axis=1) for v in VIEWS}
    for v in VIEWS:np.save(rd/f'prob_{v}.npy',prob[v]);np.save(rd/f'meta_prob_{v}.npy',metap[v])
    dump(rd/'thresholds.json',ts.tolist());dump(rd/'decision_weights.json',{'weights':w.tolist(),'TUNE_equal_budget_objective':obj})
    m=evaluate(rd,s,xx,prob,ts,final)
    finish_round(4,m,'Observation-budget matching is an actual task change with no new split or removed evaluation vessels. Next, if Micro improvement is below 0.10, replace the judgment code itself with subset-partition evidence rather than adjusting these weights.')
def decode_code(bits,book,w,base,order):
    distances=((bits[:,None,:]!=book[None,:,:])*w).sum(axis=2)
    allowed=np.isclose(distances,distances.min(axis=1,keepdims=True))
    order=np.array(order);result=order[np.argmax(allowed[:,order],axis=1)]
    keep=allowed[np.arange(len(base)),base];result[keep]=base[keep]
    return result
def round5():
    s,xx=load();fit=s.split.eq('FIT').to_numpy();q=s.split.ne('FIT').to_numpy();sub=s.loc[q];tune=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy()
    rd=setup_round(5,{'design':'seven binary partition tasks with disagreement-correcting label codes','training_task':'Retain four class judges for every vessel and add three separate TabICLv2 subset tasks C+G vs P+D, C+P vs G+D, C+D vs G+P. Decode seven hard labels by weighted Hamming disagreement to the four class codewords. Retain original combination if tied; otherwise a global TUNE-selected tie order. No maximum of original judge scores.','core_change_from_previous':'Replaces multiclass correction with a discrete error-correcting code and new class-subset learning tasks. This is a core transition after +.0027 < new .03 requirement.','policy_selection':'Subset thresholds maximize TUNE binary macro-F1 across all four budgets. Code weights and global tie order optimize .6 Micro + .4 macro on the same TUNE budgets only.','transition_required_improvement':TRANSITION_DELTA})
    budgets=pd.read_csv(B/'round_04'/'training_observation_budgets.csv',index_col='id').view
    xt=xx['full'].copy()
    for v in VIEWS:
        ids=budgets.index[budgets==v];xt.loc[ids]=xx[v].loc[ids]
    groups=[[0],[1],[2],[3],[0,1],[0,2],[0,3]];book=np.array([[c in a for a in groups] for c in range(4)])
    prob={v:np.load(B/'round_04'/f'prob_{v}.npy') for v in VIEWS};ts=np.array(json.loads((B/'round_04'/'thresholds.json').read_text()))
    query=np.concatenate([xx[v].loc[q].to_numpy() for v in VIEWS]);additional=[];thresholds_extra=[];tmask=np.tile(tune,4);ty=np.tile(sub.y.to_numpy()[tune],4)
    for a in groups[4:]:
        p,cc=predict(xt.loc[fit],np.isin(y[fit],a).astype(int),query,SEED+500+sum(a));p=p[:,list(cc).index(1)];additional.append(p)
        grid=np.arange(.05,.951,.025);scores=[f1_score(np.isin(ty,a),p[tmask]>=t,average='macro',zero_division=0) for t in grid];thresholds_extra.append(float(grid[np.argmax(scores)]))
    ap=np.column_stack(additional);allp=np.column_stack([np.concatenate([prob[v] for v in VIEWS]),ap]);allthreshold=np.r_[ts,thresholds_extra];bits=allp>=allthreshold
    base=np.concatenate([original(tags(prob[v],ts)) for v in VIEWS]);best=(-1,None)
    for group_w,d_w in itertools.product([.5,1.,1.5,2.,3.],[1.,2.,3.]):
        weights=np.array([1.,1.,1.,d_w,group_w,group_w,group_w])
        for order in itertools.permutations(range(4)):
            pr=decode_code(bits[tmask],book,weights,base[tmask],order)
            score=.6*f1_score(ty,pr,average='micro')+.4*f1_score(ty,pr,labels=range(4),average='macro',zero_division=0)
            if score>best[0]+1e-12:best=(score,(weights,order))
    w,order=best[1];pred=decode_code(bits,book,w,base,order);final=dict(zip(VIEWS,np.split(pred,4)))
    for v,z,b in zip(VIEWS,np.split(allp,4),np.split(bits,4)):
        np.save(rd/f'code_prob_{v}.npy',z);np.save(rd/f'code_bits_{v}.npy',b);np.save(rd/f'prob_{v}.npy',prob[v])
    dump(rd/'thresholds.json',ts.tolist());dump(rd/'codebook.json',{'positive_class_groups':groups,'codewords':book.astype(int).tolist(),'thresholds':allthreshold.tolist(),'weights':w.tolist(),'tie_order':list(order),'TUNE_objective':best[0]})
    m=evaluate(rd,s,xx,prob,ts,final)
    finish_round(5,m,'Completed the five initially requested independent rounds, not an automatic stop. Evaluate remaining Micro > .65, short-observation and trap/gillnet goals. A further structure change is required if improvement is below .03; daily and tail geometry evidence is a candidate within TabICLv2.')
def tournament3(pair,fallback,cg,cp):
    wins=np.zeros((len(fallback),3),dtype=int)
    for a,b,cut in [(0,1,cg),(0,2,cp),(1,2,.5)]:
        a_wins=pair[:,a,b]>=cut;wins[:,a]+=a_wins;wins[:,b]+=~a_wins
    champion=wins==2;has=champion.any(axis=1);out=fallback.copy();out[has]=champion[has].argmax(axis=1)
    return out
def round6():
    s,xx=load();fit=s.split.eq('FIT').to_numpy();q=s.split.ne('FIT').to_numpy();sub=s.loc[q];tune=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy()
    ex={v:pd.read_csv(B/f'episode_features_{v}.csv',index_col='id').reindex(s.index) for v in VIEWS}
    for v in VIEWS:
        assert ex[v].index.equals(xx[v].index)
        assert np.array_equal(ex[v].n_rows,xx[v].n_rows) and np.array_equal(ex[v].n_days,xx[v].n_days),'Fixed observation denominator must not change'
    rd=setup_round(6,{'design':'daily-distribution geometry and focused three-class contrast tournament','training_task':'New measured row/day quantiles, movement-line length bins and hourly activity fractions replace previous mean/std representations. A D-vs-rest task and C/G/P pairwise contrast tasks inspect every query, while a separate 3-class TabICLv2 breaks tournament cycles. This uses only each target observation budget.','core_change_from_previous':'Replaces the seven-bit code with a rare-geometry/day-distribution representation and hierarchical focused contrast learning. Mandatory transition because round_05 improvement < .03.','ensemble':8,'policy_selection':'TUNE only: D threshold maximizes binary F1 across four budgets; 25 fixed CG/CP contrast threshold combinations maximize .8 Micro + .2 macro. REPORT is unchanged.','episode_features_sha256':{v:sha(B/f'episode_features_{v}.csv') for v in VIEWS},'base_name_tags':'round_04 four-judge cached predictions from this independent session, used for before/after combination diagnostics; no old-project outputs'})
    shutil.copy2(B/'build_episode_inputs.py',rd/'build_episode_inputs.py');shutil.copy2(B/'episode_input_spec.json',rd/'episode_input_spec.json')
    budgets=pd.read_csv(B/'round_04'/'training_observation_budgets.csv',index_col='id').view;xt=ex['full'].copy()
    for v in VIEWS:
        ids=budgets.index[budgets==v];xt.loc[ids]=ex[v].loc[ids]
    query=np.concatenate([ex[v].loc[q].to_numpy() for v in VIEWS]);tmask=np.tile(tune,4);ty=np.tile(sub.y.to_numpy()[tune],4)
    dp,cc=predict(xt.loc[fit],(y[fit]==3).astype(int),query,SEED+600,8);dp=dp[:,list(cc).index(1)]
    grid=np.arange(.05,.951,.025);dscores=[f1_score(ty==3,dp[tmask]>=t,zero_division=0) for t in grid];dt=float(grid[np.argmax(dscores)])
    ctx=fit&(y!=3);tri,cc=predict(xt.loc[ctx],y[ctx],query,SEED+610,8);assert list(cc)==[0,1,2];fallback=tri.argmax(axis=1)
    pair=np.zeros((len(query),3,3))
    for a,b in itertools.combinations(range(3),2):
        ctx=fit&np.isin(y,[a,b]);pp,cc=predict(xt.loc[ctx],y[ctx],query,SEED+620+a*10+b,8)
        pair[:,a,b]=pp[:,list(cc).index(a)];pair[:,b,a]=1-pair[:,a,b]
    best=(-1,None)
    for cg,cp in itertools.product([.35,.45,.55,.65,.75],repeat=2):
        pr=tournament3(pair[tmask],fallback[tmask],cg,cp);pr[dp[tmask]>=dt]=3
        score=.8*f1_score(ty,pr,average='micro')+.2*f1_score(ty,pr,labels=range(4),average='macro',zero_division=0)
        if score>best[0]+1e-12:best=(score,(cg,cp))
    cg,cp=best[1];pred=tournament3(pair,fallback,cg,cp);pred[dp>=dt]=3;final=dict(zip(VIEWS,np.split(pred,4)))
    prob={v:np.load(B/'round_04'/f'prob_{v}.npy') for v in VIEWS};ts=np.array(json.loads((B/'round_04'/'thresholds.json').read_text()))
    for v,z,dd,tt in zip(VIEWS,np.split(pair,4),np.split(dp,4),np.split(tri,4)):
        np.save(rd/f'focused_pair_{v}.npy',z);np.save(rd/f'd_judge_{v}.npy',dd);np.save(rd/f'threeclass_{v}.npy',tt);np.save(rd/f'prob_{v}.npy',prob[v])
    dump(rd/'thresholds.json',ts.tolist());dump(rd/'focused_policy.json',{'D_threshold':dt,'CG_C_threshold':cg,'CP_C_threshold':cp,'GP_G_threshold':.5,'TUNE_objective':best[0],'tie_rule':'three-class separate learned task breaks cycles, D gate overrides only when its independently tuned label is present'})
    m=evaluate(rd,s,xx,prob,ts,final)
    finish_round(6,m,'New daily/rare shape representation and focused context tasks have been measured without changing vessels or observation budgets. Compare short-view and gillnet/trap errors as well as overall Micro. Use .03 improvement requirement for any next core direction decision.')
if __name__=='__main__':
    globals()['round'+sys.argv[1]]()
