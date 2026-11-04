"""Recompute selected synthetic teaching examples from fishing chapters 19-25.

Uses only Python's standard library. No competition data, model training,
simulation performance, or real hardware is evaluated.
"""

import json
import math
from pathlib import Path
import statistics

RESULTS = []


def check(name, condition, actual, expected, tolerance=1e-8):
    passed = math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)
    RESULTS.append({"name": name, "condition": condition, "expected": expected,
                    "computed": actual, "tolerance": tolerance, "passed": passed})


def softmax(values):
    maximum = max(values)
    exponentials = [math.exp(value - maximum) for value in values]
    return [value / sum(exponentials) for value in exponentials]


def path_length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def dtw_squared(a, b):
    grid = [[math.inf] * (len(b) + 1) for _ in range(len(a) + 1)]
    grid[0][0] = 0
    for i, x in enumerate(a, 1):
        for j, y in enumerate(b, 1):
            grid[i][j] = (x - y) ** 2 + min(grid[i-1][j], grid[i][j-1], grid[i-1][j-1])
    return grid[-1][-1]


def normal_density(x, mean=0.0, variance=1.0):
    return math.exp(-(x-mean)**2/(2*variance)) / math.sqrt(2*math.pi*variance)


def main():
    RESULTS.clear()
    # 19: Euclidean geometry, covariance and order-preserving comparison.
    points = [(0, 0), (300, 0), (300, 400)]
    length = path_length(points)
    check("M19 length", "One connected synthetic part, coordinates in m", length, 700)
    check("M19 displacement", "End-to-end distance", math.dist(points[0], points[-1]), 500)
    check("M19 straightness", "D/L", 500/length, 0.7142857142857143)
    check("M19 multipart length", "Separate 300 m second part; no gap edge", length+300, 1000)
    check("M19 multipart straightness", "Sum D / sum L", 800/1000, 0.8)
    check("M19 turn", "Vectors (300,0),(0,400), rad", math.atan2(120000, 0), math.pi/2)
    check("M19 box area", "Width 300 m, height 400 m", 300*400, 120000)
    means = [statistics.mean(p[k] for p in points) for k in range(2)]
    cov = [[sum((p[j]-means[j])*(p[k]-means[k]) for p in points)/3
            for k in range(2)] for j in range(2)]
    for j, k, expected in [(0,0,20000), (0,1,40000/3), (1,1,320000/9)]:
        check(f"M19 covariance {j},{k}", "Population point covariance, m²", cov[j][k], expected)
    check("M19 arc-length interpolation", "350 m is 50/400 along second segment", 400*(350-300)/400, 50)
    check("M19 DTW", "A=(0,2), B=(0,1,2), squared cost then sqrt", math.sqrt(dtw_squared([0,2],[0,1,2])), 1)
    check("M19 spherical distance", "Equator 0.01 deg, assumed R=6371000 m", 6371000*math.radians(0.01), 1111.9492664455875)

    # 20: CE derivative checked independently by finite differences.
    logits = [0, math.log(2), math.log(3)]
    probabilities = softmax(logits)
    check("M20 initial CE", "Class index 1, z=(0,ln2,ln3)", -math.log(probabilities[1]), 1.0986122886681098)
    for k in range(3):
        plus, minus = logits.copy(), logits.copy()
        plus[k] += 1e-6
        minus[k] -= 1e-6
        finite_difference = (-math.log(softmax(plus)[1])+math.log(softmax(minus)[1]))/2e-6
        check(f"M20 CE gradient {k}", "Central finite difference against p-onehot", finite_difference,
              probabilities[k]-(k==1), tolerance=1e-7)
    # W and b update together: x=(1,2), squared norm plus bias contribution = 6.
    updated = softmax([z-0.1*6*(p-(k==1)) for k,(z,p) in enumerate(zip(logits,probabilities))])
    check("M20 updated probability", "Joint W,b step eta=.1 on x=(1,2)", updated[1], 0.488247090454)
    check("M20 updated CE", "Same single synthetic sample", -math.log(updated[1]), 0.716933668374)
    check("M20 weighted CE exercise", "Loss .4,1; weight 1,3", (0.4+3)/4, 0.85)
    check("M20 Gini parent", "Class frequencies 3/4,1/4", 1-(3/4)**2-(1/4)**2, 0.375)
    check("M20 RBF", "gamma=.5, squared distance 2", math.exp(-0.5*2), 0.367879441171)
    check("M20 joint objective", "ln2 plus .2 times half squared residual .5", math.log(2)+0.2*0.125, 0.718147180560)
    check("M20 shared gradient", ".2 times residual -.5 times decoder .5", 0.2*(-0.5)*0.5, -0.05)
    check("M20 opposing objectives", "gC=(1,0),gA=(-2,1)", 1*(-2)+0*1, -2)

    # 21: recurrence and inference, keeping physical time separate.
    check("M21 causal attention", "Only scores 0,ln2; values 10,20", (10+2*20)/3, 16.666666666667)
    check("M21 unmasked attention", "Scores 0,ln2,ln4; values 10,20,100", (10+2*20+4*100)/7, 64.285714285714)
    check("M21 TCN receptive field", "One conv/layer; k=3, dilations 1,2,4", 1+(3-1)*sum([1,2,4]), 15)
    check("M21 LSTM cell", "f=.8,cprev=1,i=.2,candidate=.5", 0.8+0.2*0.5, 0.9)
    check("M21 LSTM hidden", "o=.5,c=.9", 0.5*math.tanh(0.9), 0.358148935100)
    alpha1 = [0.5*0.8, 0.5*0.3]
    transition = [[0.9,0.1],[0.2,0.8]]
    alpha2 = [sum(alpha1[i]*transition[i][j] for i in range(2))*[0.2,0.7][j] for j in range(2)]
    delta2 = [max(alpha1[i]*transition[i][j] for i in range(2))*[0.2,0.7][j] for j in range(2)]
    check("M21-Q2 likelihood", "Forward sums all state paths", sum(alpha2), 0.19)
    check("M21-Q2 posterior V", "alpha2V divided by likelihood", alpha2[1]/sum(alpha2), 0.589473684211)
    check("M21-Q2 Viterbi", "Maximum joint path probability", max(delta2), 0.084)
    check("M21 AR", "c=.2,phi=.8,current=1.5", 0.2+0.8*1.5, 1.4)
    gain = 9/(9+3)
    check("M21-Q3 gain", "H=1,Pminus=9,R=3", gain, 0.75)
    check("M21-Q3 mean", "Prior5,observation8", 5+gain*(8-5), 7.25)
    check("M21-Q3 variance", "Joseph form agrees with scalar shortcut", (1-gain)**2*9+gain**2*3, 2.25)

    # 22: robust, distributional, isolation, reconstruction and label masking.
    base = [8,9,10,11,12]
    median = statistics.median(base)
    mad = statistics.median(abs(x-median) for x in base)
    check("M22 MAD", "14 against baseline8..12; fixed1.4826 convention", (14-median)/(1.4826*mad), 2.69796303790638)
    for name, a, b, target in [("aligned",1,1,10/9),("opposed",1,-1,10)]:
        d2 = (a*a+b*b-1.6*a*b)/0.36
        check(f"M22-Q1 D2 {name}", "Sigma=[[1,.8],[.8,1]]", d2, target)
        check(f"M22-Q1 NLL {name}", "2D Gaussian log determinant included",
              0.5*(d2+math.log(0.36)+2*math.log(2*math.pi)),
              1.882606998198 if name=="aligned" else 6.327051442642, tolerance=1e-6)
    mixture = 0.6*normal_density(4)+0.4*normal_density(4,mean=4)
    check("M22 mixture density", "Fixed weights .6,.4 and unit variances", mixture, 0.159657210095)
    for value, target in [(0,1.223174051735),(3,3.936373364569)]:
        kde = sum(normal_density(value, mean=x) for x in [-1,0,1])/3
        check(f"M22 KDE {value}", "h=1,Gaussian kernel,base(-1,0,1)", -math.log(kde), target, tolerance=1e-6)
    c8 = 2*sum(1/k for k in range(1,8))-2*7/8
    check("M22 isolation c8", "Exact harmonic-number convention", c8, 3.4357142857142855)
    check("M22-Q2 isolation score", "Average corrected path=3", 2**(-3/c8), 0.545941823059)
    calibration = [0.2,0.5,0.5,0.8,1.0]
    for value,target in [(0.8,0.5),(1.2,1/6)]:
        check(f"M22 tail {value}", "One plus count>=score, divide by n+1", (1+sum(s>=value for s in calibration))/6, target)
    check("M22 PCA residual", "Projection(2,0) on span(1,1) gives(1,1)", ((2-1)**2+(0-1)**2)/2, 1)
    check("M22 AE MSE", "Input(2,0),reconstruction(1.5,.5)", ((2-1.5)**2+(0-0.5)**2)/2, 0.25)
    cumulative = 0
    for k,(value,target) in enumerate(zip([0.2,1,1.1,0.1,1.4],[0,0.5,1.1,0.7,1.6]),1):
        cumulative = max(0,cumulative+value-0.5)
        check(f"M22 CUSUM step{k}", "kappa=.5,threshold1.5", cumulative, target)
    bce = (-math.log(0.8)-math.log(0.7))/2
    check("M22-Q3 masked BCE", "Known labels1,0; third unknown excluded", bce, 0.289909247626)
    check("M22-Q3 false negative label BCE", "Incorrectly forcing unknown p=.9 to negative", (-math.log(0.8)-math.log(0.7)-math.log(0.1))/3, 0.960801196082)
    check("M22-Q3 joint loss", "Lclass=.4,lambda=.5", 0.4+0.5*bce, 0.544954623813)

    # 23: normalized weights and causal information availability.
    weights = [1000**-2,2000**-2]
    normalized = [w/sum(weights) for w in weights]
    check("M23 IDW sum", "Distances in m,p=2", sum(normalized), 1)
    check("M23 IDW value", "Observations2m,5m", sum(w*x for w,x in zip(normalized,[2,5])), 2.6)
    a=b=0.25
    check("M23 bilinear", "Corners1,2,3,4;relativea=b=.25", (1-a)*(1-b)*1+a*(1-b)*2+(1-a)*b*3+a*b*4, 1.75)
    check("M23 valid-time mean", "20min2m,10min5m", (20*2+10*5)/30, 3)
    check("M23 coverage", "30 of60 minutes valid", 30/60, 0.5)
    check("M23 future observation unavailable", "11:10 publication after10:30 judgment", float(11*60+10<=10*60+30), 0)

    # 24: synthetic kinetics, state transitions, correlated variation and KL.
    for name,actual,target in [("east",(2*math.cos(math.pi/2)+0.3)*5,1.5),
                               ("north",(2*math.sin(math.pi/2)-0.2)*5,9)]:
        check(f"M24-Q1 position {name}", "Synthetic dt5s,current(.3,-.2)m/s", actual, target)
    check("M24-Q1 direction", "Current headingpi/2,rate-.02rad/s,dt5s", math.pi/2-0.02*5, 1.470796326795)
    check("M24-Q1 ground speed", "Ground vector(.3,1.8)m/s", math.hypot(0.3,1.8), 1.824828759089)
    check("M24-Q2 Markov T", "P=[[.8,.2],[.4,.6]],startT,two steps", 0.8*0.8+0.2*0.4, 0.72)
    check("M24-Q2 dwell", "Self-transition.8,geometricsteps", 1/(1-0.8), 5)
    check("M24-Q2 AR1 sd", "rho=.8,innovationSD=.012rad/s", 0.012/math.sqrt(1-0.8**2), 0.02)
    check("M24 OU coefficient", "kappa=.1/s,dt10s", math.exp(-0.1*10), 0.367879441171)
    check("M24 OU innovation sd", "sigma=.002,kappa=.1,dt10", 0.002*math.sqrt((1-math.exp(-2*0.1*10))/(2*0.1)), 0.004158521043)
    check("M24-Q3 KL", "q=N(1,.25),p=N(0,1)", 0.5*(1+0.25-1-math.log(0.25)), 0.818147180560)

    # 25: metrics on fully labelled synthetic examples, not incident data.
    matrix = [[3,1,0],[1,1,0],[0,1,2]]
    f1 = [2*matrix[c][c]/(sum(matrix[c])+sum(row[c] for row in matrix)) for c in range(3)]
    check("M25 macro F1", "Specified3x3syntheticconfusionmatrix", statistics.mean(f1), 0.65)
    check("M25 accuracy", "6correctof9", sum(matrix[c][c] for c in range(3))/9, 2/3)
    truth, scores = [1,0,1,0], [0.9,0.8,0.4,0.1]
    pairs = [(p,n) for p,y in zip(scores,truth) if y for n,z in zip(scores,truth) if not z]
    auc = sum((p>n)+0.5*(p==n) for p,n in pairs)/len(pairs)
    check("M25-Q1 AUC", "Two positive, two negative labelled examples", auc, 0.75)
    check("M25-Q1 AP", "Positive ranks1,3,no ties", (1+2/3)/2, 5/6)
    check("M25 Brier", "Fully definedbinarytargets", statistics.mean((p-y)**2 for p,y in zip(scores,truth)), 0.255)
    check("M25 NLL", "Probabilities andbinarytargets", -statistics.mean(math.log(p if y else 1-p) for p,y in zip(scores,truth)), 0.684112418883)
    check("M25 temperature", "Logitsln9,0;T=2", softmax([math.log(9)/2,0])[0], 0.75)
    check("M25-Q2 lead minutes", "Incident10:40,judgment11:05", (10*60+40)-(11*60+5), -25)

    report = {"date": "2026-10-07", "scope": "Selected synthetic calculations in fishing chapters19-25; not actual model or vessel validation",
              "real_data_evaluated": False, "model_training_performed": False,
              "hardware_experiment_performed": False, "checks": len(RESULTS),
              "passed": sum(result["passed"] for result in RESULTS), "results": RESULTS}
    path = Path(__file__).resolve().parent / "fishing_numerical_report.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    failed = [item for item in RESULTS if not item["passed"]]
    print(json.dumps({"checks":len(RESULTS), "passed":report["passed"], "failed":failed,
                      "report":str(path)},ensure_ascii=False,indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
