"""Independently recompute selected textbook numbers with the standard library.

Only these synthetic calculations are checked; this is not a model benchmark,
learner assessment, simulation of a physical device, or hardware verification.
"""
from pathlib import Path
import ast
import contextlib
import io
import json
import math
import re

RESULTS = []


def check(label, actual, expected, tolerance=1e-9):
    if isinstance(actual, (list, tuple)):
        passed = len(actual) == len(expected) and all(
            math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)
            for a, b in zip(actual, expected)
        )
    else:
        passed = math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)
    RESULTS.append({"case": label, "actual": actual, "expected": expected, "passed": passed})


def confusion(labels, probabilities, threshold):
    predictions = [p >= threshold for p in probabilities]
    tp = sum(y == 1 and p for y, p in zip(labels, predictions))
    fp = sum(y == 0 and p for y, p in zip(labels, predictions))
    fn = sum(y == 1 and not p for y, p in zip(labels, predictions))
    tn = sum(y == 0 and not p for y, p in zip(labels, predictions))
    return [tp, fp, fn, tn]


def main():
    check("M01 worked example t=0.5 TP FP FN TN", confusion([1, 1, 0, 0], [.8, .6, .4, .1], .5), [2, 0, 0, 2])
    check("M01 worked example t=0.7 TP FP FN TN", confusion([1, 1, 0, 0], [.8, .6, .4, .1], .7), [1, 0, 1, 2])
    log_loss = -sum(y * math.log(p) + (1-y) * math.log(1-p)
                    for y, p in zip([1, 1, 0, 0], [.8, .6, .4, .1])) / 4
    check("M01 mean log loss rounded to 3 decimals", round(log_loss, 3), .338)
    check("M01-Q3 t=0.5 TP FP FN TN", confusion([1, 0, 1, 0], [.7, .4, .45, .2], .5), [1, 0, 1, 2])
    check("M01-Q3 t=0.4 TP FP FN TN", confusion([1, 0, 1, 0], [.7, .4, .45, .2], .4), [2, 1, 0, 1])

    a, x, b = [[1, 2], [0, 1], [3, -1]], [2, 1], [1, 0, -2]
    ax = [sum(c*v for c, v in zip(row, x)) for row in a]
    check("M02 Ax", ax, [4, 1, 5])
    check("M02-Q1 Ax+b", [v+t for v, t in zip(ax, b)], [5, 1, 3])
    u, v = [1, 2], [2, 1]
    scale = sum(c*d for c, d in zip(u, v)) / sum(c*c for c in u)
    projection = [scale*c for c in u]
    check("M02 projection", projection, [.8, 1.6])
    check("M02 residual orthogonality", sum((d-p)*c for c, d, p in zip(u, v, projection)), 0)
    loss = lambda w: .5 * (2*w-3)**2
    step = 1e-6
    numerical_gradient = (loss(.5+step)-loss(.5-step))/(2*step)
    check("M02 finite difference gradient", numerical_gradient, -4, 1e-7)
    new_w = .5 - .1 * (-4)
    check("M02 updated w", new_w, .9)
    check("M02 updated loss", loss(new_w), .72)
    check("M02 separate quadratic updated w", 0-.25*(0-2), .5)
    exercise_u, exercise_v = [1, 1], [3, 1]
    exercise_scale = sum(a*b for a,b in zip(exercise_u,exercise_v))/sum(a*a for a in exercise_u)
    exercise_projection = [exercise_scale*a for a in exercise_u]
    check("M02-Q2 projection and residual", exercise_projection+[b-p for b,p in zip(exercise_v,exercise_projection)], [2, 2, 1, -1])
    check("M02-Q3 large learning rate w and loss", [.5-.6*(-4), loss(.5-.6*(-4))], [2.9, 3.92])

    check("M03 Bayesian posterior", .9*.02/(.9*.02+.05*.98), 18/67)
    check("M03 estimated proportion standard error rounded", round(math.sqrt(.3*.7/10), 3), .145)
    check("M03 one-sided all-heads p-value", .5**10, 1/1024)
    p, q = [.75, .25], [.5, .5]
    entropy = lambda distribution: -sum(x*math.log2(x) for x in distribution)
    kl = lambda left, right: sum(x*math.log2(x/y) for x, y in zip(left, right))
    check("M03 entropy in bits", entropy(p), .8112781244591328)
    check("M03-Q3 forward KL in bits", kl(p, q), .18872187554086717)
    check("M03-Q3 reverse KL in bits", kl(q, p), .20751874963942185)
    check("M03-Q1 Bayesian posterior", .8*.01/(.8*.01+.1*.99), 80/1070)
    check("M03-Q2 one-sided tail if pre-specified", sum(math.comb(20, k)*.5**20 for k in range(14, 21)), .057659149169921875)

    check("M04 activation bytes", 32*512*768*4, 50331648)
    check("M04 activation MiB", 32*512*768*4/2**20, 48)
    check("M04-Q1 multiplication count", 64*128*10, 81920)
    check("M04-Q1 array byte counts", [64*128*4, 128*10*4, 64*10*4], [32768, 5120, 2560])
    check("M04-Q2 attention element ratio", 1024**2/512**2, 4)
    objective = lambda a, b, c: (a*b+c-10)**2
    derivatives = [(objective(2+step,3,1)-objective(2-step,3,1))/(2*step),
                   (objective(2,3+step,1)-objective(2,3-step,1))/(2*step),
                   (objective(2,3,1+step)-objective(2,3,1-step))/(2*step)]
    check("M04 worked example finite difference gradients", derivatives, [-18, -12, -6], 1e-7)
    exercise_derivatives = [(objective(1+step,4,2)-objective(1-step,4,2))/(2*step),
                            (objective(1,4+step,2)-objective(1,4-step,2))/(2*step),
                            (objective(1,4,2+step)-objective(1,4,2-step))/(2*step)]
    check("M04-Q3 changed condition gradients", exercise_derivatives, [-32, -8, -8], 1e-7)
    # This exact educational block was read and inspected before execution.
    chapter04 = Path(__file__).resolve().parent.parent / "chapters" / "04_computing.md"
    code04 = re.findall(r"```python\s*\n(.*?)\n```", chapter04.read_text(encoding="utf-8-sig"), re.S)
    if len(code04) != 1:
        raise ValueError("Re-inspect M04 code examples: expected exactly one reviewed block")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        exec(compile(code04[0], str(chapter04), "exec"), {})
    check("M04 actual textbook Python execution", ast.literal_eval(captured.getvalue().strip()), [4, 1, 5])

    graph = {"S": {"A": 2, "B": 1}, "A": {"G": 2}, "B": {"G": 6}, "G": {}}
    heuristic = {"S": 1, "A": 2, "B": 0, "G": 0}
    check("M05 path costs through A and B", [graph["S"]["A"]+graph["A"]["G"], graph["S"]["B"]+graph["B"]["G"]], [4, 7])
    check("M05 all edges meet consistency condition", sum(heuristic[u] <= w+heuristic[v] for u, edges in graph.items() for v, w in edges.items()), 4)
    check("M05 changed B to G edge shortest path", min(2+2, 1+1), 2)
    check("M05-Q1 changed graph shortest path", min(4+2, 1+3), 4)

    observations = [(1, 2), (2, 3)]
    regression_loss = lambda w: sum((w*x-y)**2 for x, y in observations)/(2*len(observations))
    regression_gradient = sum((x-y)*x for x, y in observations)/len(observations)
    check("M06 initial loss and gradient", [regression_loss(1), regression_gradient], [.5, -1.5])
    updated_w = 1-.1*regression_gradient
    check("M06 updated weight and loss", [updated_w, regression_loss(updated_w)], [1.15, .303125])
    optimal_w = sum(x*y for x,y in observations)/sum(x*x for x,y in observations)
    check("M06 analytic optimum and loss", [optimal_w, regression_loss(optimal_w)], [1.6, .05])
    check("M06 ridge optimum lambda one", sum(x*y for x,y in observations)/(sum(x*x for x,y in observations)+len(observations)), 8/7)
    changed_observations = [(1,2), (3,5)]
    numerator = sum(x*y for x,y in changed_observations)
    denominator = sum(x*x for x,y in changed_observations)
    check("M06-Q1 unregularized and regularized optima", [numerator/denominator, numerator/(denominator+2)], [1.7, 17/12])

    prob_s = .2*.8+.8*.1
    prob_sw = .2*.8*.7+.8*.1*.2
    check("M07 single observation probability and posterior", [prob_s, .2*.8/prob_s], [.24, 2/3])
    check("M07 joint observations and posterior", [prob_sw, .2*.8*.7/prob_sw], [.128, .875])
    check("M07 independent product differs from joint", prob_s*(.2*.7+.8*.2), .072)
    check("M07 Beta posterior mean MAP MLE", [5/8, (5-1)/(5+3-2), 3/4], [.625, 2/3, .75])
    transition = [[.7,.3], [.2,.8]]
    emission = [.9,.2]
    alpha1 = [p*e for p,e in zip([.6,.4], emission)]
    alpha2 = [sum(alpha1[i]*transition[i][j] for i in range(2))*emission[j] for j in range(2)]
    check("M07 HMM first forward weights", alpha1, [.54, .08])
    check("M07 HMM second forward weights", alpha2, [.3546, .0452])
    check("M07 HMM observation likelihood", sum(alpha2), .3998)
    check("M07 HMM posterior rounded", round(alpha2[0]/sum(alpha2), 6), .886943)
    check("M07-Q1 changed prior posterior", .5*.8/(.5*.8+.5*.1), 8/9)
    check("M07-Q2 posterior mean MAP MLE", [5/10, 4/8, 2/5], [.5,.5,.4])

    network_loss = lambda weights, target: .5*(weights[2]*max(0, weights[0]*2+weights[1])+weights[3]-target)**2
    initial = [1,-1,.5,0]
    gradients = []
    for i in range(4):
        plus, minus = initial.copy(), initial.copy()
        plus[i] += step
        minus[i] -= step
        gradients.append((network_loss(plus,2)-network_loss(minus,2))/(2*step))
    check("M08 finite difference gradients", gradients, [-1.5,-.75,-1.5,-1.5], 1e-7)
    updated = [p-.1*g for p,g in zip(initial, gradients)]
    check("M08 simultaneous update", updated, [1.15,-.925,.65,.15], 1e-7)
    check("M08 updated loss", network_loss(updated,2), .45720703125, 1e-7)
    attention_a = math.exp(1/math.sqrt(2))/(math.exp(1/math.sqrt(2))+1)
    check("M08 attention weights rounded", [round(attention_a,6), round(1-attention_a,6)], [.669762,.330238])
    check("M08 attention weighted output rounded", [round(2*attention_a,6),round(4*(1-attention_a),6)], [1.339523,1.320954])
    changed_gradients = []
    for i in range(4):
        plus, minus = initial.copy(), initial.copy()
        plus[i] += step
        minus[i] -= step
        changed_gradients.append((network_loss(plus,1)-network_loss(minus,1))/(2*step))
    check("M08-Q1 changed target loss and gradients", [network_loss(initial,1)]+changed_gradients, [.125,-.5,-.25,-.5,-.5], 1e-7)
    check("M08-Q1 changed target update", [p-.1*g for p,g in zip(initial,changed_gradients)], [1.05,-.975,.55,.05], 1e-7)

    check("M09 contrastive losses with alternative temperatures", [round(math.log1p(math.exp(-1)),6),round(math.log1p(math.exp(-2)),6)], [.313262,.126928])
    check("M09 FedAvg sample-weighted versus uniform", [(3*2+1*5)/4,(2+5)/2], [2.75,3.5])
    check("M09-Q2 changed client sample count", (3*2+2*5)/5, 3.2)

    joint = lambda first,aa,ba: [first*aa,first*(1-aa),(1-first)*ba,(1-first)*(1-ba)]
    check("M10 autoregressive joint probabilities", joint(.6,.2,.5), [.12,.48,.20,.20])
    vae_kl = .5*(1**2+.25-1-math.log(.25))
    check("M10 Gaussian KL and ELBO rounded", [round(vae_kl,6),round(-2-vae_kl,6)], [.818147,-2.818147])
    check("M10 flow density at transformed origin rounded", round(1/(2*math.sqrt(2*math.pi)),6), .199471)
    energies = [0, math.log(3)]
    weights = [math.exp(-energy) for energy in energies]
    check("M10 normalized energy distribution", [w/sum(weights) for w in weights], [.75,.25])
    xt = math.sqrt(.64)*2+math.sqrt(1-.64)*(-1)
    check("M10 noised input and reconstructed estimate", [xt,(xt-math.sqrt(1-.64)*(-.5))/math.sqrt(.64)], [1,1.625])
    check("M10-Q1 joint probabilities", joint(.55,.51,.99), [.2805,.2695,.4455,.0045])
    check("M10-Q2 corrected flow density", 1/(3*math.sqrt(2*math.pi)), .1329807601338109)

    check("M11 Bellman go value and Q update", [.9*3,1+.5*(.9*3-1)], [2.7,1.85])
    check("M11 changed discount go value", .2*3, .6)
    check("M11 closed-loop coefficients", [.8-1*.3,.8-1*2], [.5,-1.2])
    check("M11 control trajectories", [2*(.8-.3)**t for t in range(4)], [2,1,.5,.25])
    optimal_u = -2/2
    check("M11 one-step MPC input next state cost", [optimal_u,2+optimal_u,(2+optimal_u)**2+optimal_u**2], [-1,1,2])
    check("M11-Q1 action values in two conditions", [1,.5*3,1,.5*1], [1,1.5,1,.5])
    check("M11-Q2 target and updated Q", [1+.5*4,0+.2*(1+.5*4-0)], [3,.6])
    check("M11-Q3 coefficient and open stability interval endpoints", [.8-1.9,(.8-1)/1,(.8+1)/1], [-1.1,-.2,1.8])

    softmax = lambda values,temperature: [math.exp(v/temperature)/sum(math.exp(u/temperature) for u in values) for v in values]
    check("M12 token probabilities", softmax([0,math.log(3)],1), [.25,.75])
    check("M12 temperature two probabilities rounded", [round(p,6) for p in softmax([0,math.log(3)],2)], [.366025,.633975])
    check("M12 token negative log likelihood rounded", round(-math.log(.75),6), .287682)
    b_column, a_row = [2,1], [1,-1]
    delta = [[b*a for a in a_row] for b in b_column]
    check("M12 LoRA low-rank product", [v for row in delta for v in row], [2,-2,1,-1])
    example_x = [1,2]
    check("M12 LoRA updated output", [value+sum(w*x for w,x in zip(row,example_x)) for value,row in zip(example_x,delta)], [-1,1])
    dpo_margin = math.log(.6/.5)-math.log(.4/.5)
    check("M12 DPO preference loss rounded", round(math.log1p(math.exp(-dpo_margin)),6), .510826)
    check("M12-Q1 original and changed temperature probabilities", softmax([0,math.log(4)],1)+softmax([0,math.log(4)],2), [.2,.8,1/3,2/3])
    check("M12-Q1 negative log likelihood rounded", round(-math.log(.8),6), .223144)
    check("M12-Q2 trainable and original parameter counts", [4*(100+80),100*80], [720,8000])

    check("M13 two aliasing frequencies on sampled grid", [math.cos(2*math.pi*2*n/8)-math.cos(2*math.pi*6*n/8) for n in range(8)], [0]*8)
    intersection_over_union = lambda a,b: (max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))) / ((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1])))
    check("M13 overlapping-box IoU", intersection_over_union([0,0,2,2],[1,0,3,2]), 1/3)
    check("M13 audio window and DFT bin spacing", [16000*.020,16000/320], [320,50])
    check("M13 two-candidate contrastive scores rounded", [round(p,6) for p in softmax([1,0],1)], [.731059,.268941])
    check("M13-Q1 changed audio window samples", 16000*.025, 400)
    check("M13-Q2 contained-box IoU", intersection_over_union([0,0,2,2],[0,0,1,2]), .5)

    kalman = lambda mean,variance,observation,noise: [variance/(variance+noise),mean+variance/(variance+noise)*(observation-mean),(1-variance/(variance+noise))*variance]
    check("M14 scalar Kalman update", kalman(10,4,12,1), [.8,11.6,.8])
    check("M14 next-state mean and variance", [.9*11.6,.9**2*.8+.5], [10.44,1.148])
    check("M14 increased observation noise", kalman(10,4,12,4), [.5,11,2])
    check("M14 autoregressive mean forecasts", [.5*8,.5**2*8], [4,2])
    check("M14 recommendation scores", [sum(a*b for a,b in zip([1,2],item)) for item in [[2,0],[0,2]]], [2,4])
    node_values, neighbors = [1,2,5], [[0,1],[0,1,2],[1,2]]
    check("M14 self-including mean aggregation", [sum(node_values[j] for j in group)/len(group) for group in neighbors], [1.5,8/3,3.5])
    check("M14-Q1 changed Kalman update", kalman(10,9,14,3), [.75,13,2.25])
    check("M14-Q2 changed recommendation scores", [sum(a*b for a,b in zip([2,1],item)) for item in [[1,0],[0,3]]], [2,3])

    check("M15 crude observational difference", (45+60)/200-(120+15)/200, -.15)
    check("M15 standardized intervention means", [.5*.9+.5*.4, .5*.8+.5*.3], [.65, .55])
    check("M15 changed population means", [.2*.9+.8*.4, .2*.8+.8*.3], [.5, .4])
    check("M15 utility with alternative costs", [20*.1-3, 20*.1-1], [-1, 1])
    check("M15-Q1 standardized means", [.25*.8+.75*.5, .25*.6+.75*.4], [.575, .45])
    check("M15-Q1 changed population effect", (.75*.8+.25*.5)-(.75*.6+.25*.4), .175)
    exogenous = 11-4*1-2*2
    check("M15-Q2 exogenous factor and counterfactual", [exogenous, 4*0+2*2+exogenous], [3, 7])
    ips = sum((1/.5 if action == 1 else 0)*reward for action, reward in [(1,1),(0,0),(1,0),(0,1)])/4
    check("M15-Q3 IPS value and net utility", [ips, ips-.2], [.5, .3])

    check("M16 fuzzy output at T=28 rounded", round((.7*30+.4*70)/1.1, 2), 44.55)
    check("M16-Q2 fuzzy outputs", [(.5*30+.5*70)/1, (.25*30+.5*70)/.75], [50, 170/3])
    check("M16 PINN residual loss rounded", round((.5**2+(.5*math.exp(-.5))**2)/2, 6), .170985)
    check("M16 PINN solution error rounded", round(math.exp(-.5)-math.exp(-1), 6), .238651)
    check("M16-Q3 changed physics residual loss rounded", round((1+math.exp(-2))/2, 6), .567668)
    check("M16-Q3 changed physics solution error rounded", round(math.exp(-1)-math.exp(-2), 6), .232544)
    check("M16 neuro-symbolic sum probabilities", [.2*.7,.2*.3+.8*.7,.8*.3], [.14,.62,.24])

    check("M17 weighted data-parallel gradient", (2*1+6*3)/8, 2.5)
    check("M17 serial latency in milliseconds", sum([10,40,150,20]), 220)
    check("M17 chain-rule success probabilities", [.8*.9*.95, .95*.9*.95, .8*1*.95], [.684,.81225,.76])
    quantize = lambda w, upper: min(3,max(0,round(w/(upper/3))))
    quantized = []
    for w in [.52,1.2]:
        code = quantize(w,.9)
        reconstruction = code*.9/3
        quantized += [code,reconstruction,abs(w-reconstruction)]
    check("M17 quantization codes reconstruction and errors", quantized, [2,.6,.08,3,.9,.3])
    check("M17 weight-only storage bytes", [10**6*32/8,10**6*8/8], [4000000,1000000])
    cost = lambda inputs, outputs: (inputs*.2+outputs)/10**6
    check("M17 synthetic request cost and increased context", [cost(1000,200),1000*cost(1000,200),cost(3000,200)], [.0004,.4,.0008])
    exercise_quantized = []
    for w in [.73,1.5]:
        code = quantize(w,1.2)
        reconstruction = code*1.2/3
        exercise_quantized += [code,reconstruction,abs(w-reconstruction)]
    check("M17-Q1 quantization codes reconstruction and errors", exercise_quantized, [2,.8,.07,3,1.2,.3])
    check("M17-Q2 original and changed success and costs", [.75*.8*.9,cost(2000,300),.9*.8*.9,cost(4000,300)], [.54,.0007,.648,.0011])

    metrics = lambda tp,fn,fp,tn: [(tp+tn)/(tp+fn+fp+tn),tp/(tp+fp),tp/(tp+fn),2*tp/(2*tp+fp+fn)]
    check("M18 original accuracy precision recall F1", metrics(15,5,10,70), [.85,.6,.75,2/3])
    check("M18 raised-threshold metrics", metrics(12,8,4,76), [.88,.75,.6,2/3])
    check("M18 cost-sensitive versus equal costs", [(4*5+10)/100,(4*8+4)/100,(5+10)/100,(8+4)/100], [.30,.36,.15,.12])
    check("M18 accuracy standard error rounded", round(math.sqrt(.85*.15/100),4), .0357)
    brier = lambda ps,ys: sum((p-y)**2 for p,y in zip(ps,ys))/len(ps)
    check("M18 Brier score", brier([.8,.8,.2,.2],[1,0,0,0]), .19)
    binary_ece = lambda ps,ys: sum(len(indices)/len(ps)*abs(sum(ys[i] for i in indices)/len(indices)-sum(ps[i] for i in indices)/len(indices)) for indices in [[i for i,p in enumerate(ps) if p<.5],[i for i,p in enumerate(ps) if p>=.5]] if indices)
    check("M18 two-bin positive-probability ECE", binary_ece([.8,.8,.2,.2],[1,0,0,0]), .25)
    check("M18 Laplace scale and basic composition", [1/.5,.5+.5], [2,1])
    group_rates = lambda tp,fn,fp,tn: [tp/(tp+fn),fp/(fp+tn),(tp+fp)/(tp+fn+fp+tn)]
    check("M18 group A TPR FPR acceptance rate", group_rates(8,2,8,32), [.8,.2,.32])
    check("M18 group B TPR FPR acceptance rate", group_rates(16,4,6,24), [.8,.2,.44])
    check("M18-Q1 original metrics", metrics(6,4,5,35), [.82,6/11,.6,4/7])
    check("M18-Q1 accuracy and cost comparison", [(6+35)/50,(4*4+5)/50,(4+38)/50,(4*6+2)/50], [.82,.42,.84,.52])
    check("M18-Q2 Brier and ECE", [brier([.9,.9,.1,.1],[1,0,0,1]),binary_ece([.9,.9,.1,.1],[1,0,0,1])], [.41,.4])
    check("M18-Q3 group A rates", group_rates(16,4,3,27), [.8,.1,.38])
    check("M18-Q3 group B rates", group_rates(8,2,4,36), [.8,.1,.24])

    choice_confidence = lambda ps: (max(ps)-1/len(ps))/(1-1/len(ps))
    check("Jev case synthetic Choice confidence for two distributions", [choice_confidence([.6,.3,.1]),choice_confidence([.6,.2,.2])], [.4,.4])

    output = Path(__file__).with_name("numerical_report.json")
    report = {"scope": "Independent recomputation of listed synthetic textbook examples",
              "checks": len(RESULTS), "passed": sum(r["passed"] for r in RESULTS),
              "results": RESULTS}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": report["checks"], "passed": report["passed"],
                      "failures": [r for r in RESULTS if not r["passed"]],
                      "report": str(output)}, ensure_ascii=False, indent=2))
    return 0 if all(r["passed"] for r in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
