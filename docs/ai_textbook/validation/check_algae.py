"""Verify selected educational calculations and algebraic invariants.

No data download, actual model training, sensor test or mastery assessment.
Uses only the Python standard library. Report values are synthetic.
"""

from pathlib import Path
from datetime import date
import json
import math
import re
from urllib.parse import urlsplit, unquote
from check_book import prose_only, anchors

BOOK = Path(__file__).resolve().parent.parent
checks = []


def close(name, observed, expected, condition, tol=1e-6):
    passed = math.isclose(observed, expected, rel_tol=tol, abs_tol=tol)
    checks.append(dict(name=name, condition=condition, expected=expected,
                       observed=observed, passed=passed))


def true(name, passed, condition):
    checks.append(dict(name=name, condition=condition, expected=True,
                       observed=bool(passed), passed=bool(passed)))


def derivative(f, x, eps=1e-5):
    return (f(x + eps) - f(x - eps)) / (2 * eps)


def main():
    # Unit conversions, log roundtrip and gradient descent.
    close("M19 total cells", 3 * 1e6 * 50, 1.5e8, "3 m3 at 50 cells/mL")
    close("M19 outflow concentration", 1e8 / (2 * 1e6), 50,
          "Well-mixed removal of 1 m3; no growth or inflow")
    close("M19 daily volume", 2 * 86400, 172800, "Q=2 m3/s")
    for c in [0, 9, 99, 999, 12345]:
        close(f"M19 log inverse {c}", 10 ** math.log10(1 + c) - 1, c,
              "C_ref=1 cells/mL")
    close("M19 log derivative", derivative(lambda c: math.log10(1 + c), 99),
          1 / (100 * math.log(10)), "Finite difference at C=99")
    close("M19 gradient w", derivative(lambda w: ((1-1)**2 + (w+1-2)**2)/2, 0),
          -1, "x=(0,1), y=(1,2), b=1")
    close("M19 descent eta0.1", ((1.1-1)**2+(1.2-2)**2)/2, .325,
          "w=.1 b=1.1")
    close("M19 descent eta0.2", ((1.2-1)**2+(1.4-2)**2)/2, .2,
          "w=.2 b=1.2")
    close("M19 Jensen toy inverse", 10**1.5-1, 30.6227766017,
          "Equally probable C=9 and 99; mean log=1.5")
    # Growth, finite-difference solution check and exact mass-balance cancellation.
    close("M20 exponential", 1000*math.exp(.2*7), 4055.199966845,
          "Constant r=.2/day, C0=1000")
    logistic = lambda t: 10000/(1+9*math.exp(-.2*t))
    close("M20 logistic C0=1000", logistic(7), 3106.19521667,
          "K=10000, r=.2/day")
    c = logistic(7)
    close("M20 logistic derivative", derivative(logistic, 7), .2*c*(1-c/10000),
          "Analytic solution compared to ODE at t=7")
    close("M20 logistic C0=8000", 10000/(1+.25*math.exp(-1.4)), 9419.3077349,
          "K=10000, r=.2/day")
    close("M20 Monod derivative", derivative(lambda s: s/(2+s), 3), 2/25,
          "K_S=2, S=3")
    close("M20 nutrient limited growth", .4*.8*.5*min(.5,.9)-.03, .05,
          "mu_max=.4; T=.8; I=.5; N=.5; P=.9; loss=.03")
    close("M20 nutrient improved forecast", 1000*math.exp(.114*7), 2221.09389588,
          "Both nutrient factors=.9; loss=.03")
    for qout in [0, 2, 5]:
        v, c, r, qin, cin = 100, 1000, .1, 4, 500
        via_total = (r*v*c+qin*cin-qout*c-c*(qin-qout))/v
        close(f"M20 mass balance qout={qout}", via_total, r*c+qin/v*(cin-c),
              "Consistent volume units, Cout=C; variable volume cancellation")
    close("M20 clean inflow", 1000*math.exp(-1.4), 246.596963942,
          "No growth; D=.2/day; Cin=0")
    close("M20 rich inflow", 2000-1000*math.exp(-1.4), 1753.403036058,
          "No growth; D=.2/day; Cin=2000")
    close("M20 identified r assumption", math.log(2)/7+.15, .249021025794,
          "Observed doubling; independent D=.15/day; Cin=0")
    # Irregular dates and feature examples.
    base = date(2026, 7, 1)
    goal = date(2026, 7, 8)
    candidates = [date(2026, 7, d) for d in [5, 10, 11, 12]]
    valid = [d for d in candidates if abs((d-goal).days) <= 3]
    selected = min(valid, key=lambda d: (abs((d-goal).days), d))
    true("M21 nearest label", selected == date(2026, 7, 10),
         "Goal July8; candidates July5,10,11,12; tolerance3days")
    close("M21 label actual horizon", (selected-base).days, 9,
          "Audit horizon, not predictor input")
    close("M21 shifted log trend", math.log10(4)/7, .0860085701897,
          "999 to3999 in7days; reference1")
    close("M21 linear rate", (999-99)/7, 128.571428571,
          "99 to999 in7days")
    close("M21 extended14day trend", 10**3.5-1, 3161.277660168,
          "Past14day shifted log change1; extend7days")
    close("M21 time average", (20*1+30*3)/4, 27.5,
          "20C for1hour,30C for3hours")
    close("M21 residence days", 43200000/(50*86400), 10,
          "m3 and m3/s conversion")
    dec = (math.sin(2*math.pi*11/12), math.cos(2*math.pi*11/12))
    close("M21 adjacent season distance", math.hypot(dec[0], dec[1]-1),
          .517638090205, "December andJanuary onunitcircle")
    # Statistical models and derivative-defined optimum.
    close("M22 ridge slope", 2/(2+2), .5, "Z=(-1,1), centered y=(-1,1),lambda2")
    close("M22 ridge new inverse", 10**2.25-1, 176.827941004,
          "new standardized temperature .5; intercept2; slope.5")
    ys = [0,0,1,2,2,3]
    avg = sum(ys)/len(ys)
    rss0 = sum((y-avg)**2 for y in ys)
    rss1 = sum((y-1/3)**2 for y in ys[:3])+sum((y-7/3)**2 for y in ys[3:])
    close("M22 CART parentRSS", rss0, 22/3, "Six syntheticlogtargets")
    close("M22 CART splitRSS", rss1, 4/3, "Split after third sample")
    close("M22 CART improvement", rss0-rss1, 6, "Same sample trainingRSS")
    close("M22 leaf derivative", derivative(lambda a: sum((y-a)**2 for y in [1,1,4]),2),
          0, "Leaf mean2 minimizes squaredloss")
    close("M22 boostedRSS", sum((a-b)**2 for a,b in zip([1,2,3,4],[2,2,3,3])),2,
          "eta.5 afterone residualtree")
    close("M22 regularizedGain", .5*(4/3+4/3)-.1, 1.233333333333,
          "G_L=2,G_R=-2,H_L=H_R=2,lambda1,gamma.1")
    close("M22 unregularizedGain", .5*(4/2+4/2)-.1, 1.9,
          "lambda0,gamma.1")
    # Latent model operations, not real data results.
    gain = .04/(.04+.01)
    close("M23 Kalmanmean", 2+gain*.3, 2.24, "P=.04,R=.01,obs2.3")
    close("M23 Kalmanvariance", (1-gain)*.04, .008, "Scalarposterior")
    close("M23 transitionvariance", .9**2*.008+.02, .02648,
          "A=.9,processvariance.02")
    close("M23 highnoise posterior", 2+.04/.13*.3, 2.092307692308,
          "P=.04,R=.09")
    close("M23 LSTMstate", .5*math.tanh(.8+.5*.2), .3581489351,
          "Fixedscalar gates; c_prev1")
    close("M23 attention", 2*math.e/(1+math.e), 1.46211715726,
          "q1,keys0and1,values0and2")
    close("M23 receptivefield", 1+2*(1+2+4), 15,
          "3layers,oneconv each,kernel3,dilation1,2,4")
    close("M23 mechanism", 100*math.exp(.05*7), 141.906754859,
          "r.1,D.05,clean inflow constant volume")
    close("M23 hybrid inverse", 10**2.3-1, 198.526231497,
          "Physicallog2 plusresidual.3")
    # Metrics, rank and interval arithmetic.
    actual, pred = [0,9,99],[0,9,9]
    err = [b-a for a,b in zip(actual,pred)]
    close("M24 rawMAE",sum(abs(e) for e in err)/3,30,"Toy concentration errors")
    close("M24 rawRMSE",math.sqrt(sum(e*e for e in err)/3),51.9615242271,
          "Toy concentration errors")
    close("M24 logRMSE",math.sqrt(1/3),.57735026919,"Logerrors0,0,-1")
    mean = sum(actual)/3
    sst = sum((a-mean)**2 for a in actual)
    close("M24 SST",sst,5994,"Mean actual36")
    close("M24 R2 NSE",1-8100/sst,-.351351351351,"Same unweighteddefinition")
    matrix = [[4,1,0,0],[1,2,1,0],[0,1,2,1],[0,0,1,1]]
    f1s = []
    for k in range(4):
        tp = matrix[k][k]
        fp = sum(row[k] for row in matrix)-tp
        fn = sum(matrix[k])-tp
        f1s.append(2*tp/(2*tp+fp+fn))
    close("M24 macroF1",sum(f1s)/4,.575,"Rowsactual,columnspredicted")
    close("M24 accuracy",sum(matrix[k][k] for k in range(4))/sum(map(sum,matrix)),.6,
          "Same confusionmatrix15rows")
    close("M24 conformalrank",math.ceil((9+1)*(1-.2)),8,
          "Synthetic sortederrors; mathematicalrank only")
    close("M24 strictrank",math.ceil((9+1)*(1-.1)),9,
          "No time-series coverage guarantee")

    # All added chapters have paired display math and no tool citation placeholders.
    chapters = sorted((BOOK/'chapters').glob('*_algae_*.md'))
    for chapter in chapters:
        text = chapter.read_text(encoding='utf-8-sig')
        boundaries = len(re.findall(r'^\s*\$\$\s*$', text, re.M))
        true(f"{chapter.stem} math delimiters",boundaries%2==0,
             "Paired standalone displaymath delimiters; not TeX rendering")
        true(f"{chapter.stem} no leaked tokens",
             'chatgpt-content-reference' not in text and '\ufffd' not in text,
             "No placeholder citations or replacementcharacters")

    # Inspect only this extension's documents; unrelated extensions can be in progress.
    paths = chapters + [BOOK/name for name in
                        ['algae_learning_path.md','94_algae_sources.md','95_algae_solutions.md']]
    texts = {path.resolve():path.read_text(encoding='utf-8-sig') for path in paths}
    structural_errors = []
    solutions = texts[(BOOK/'95_algae_solutions.md').resolve()]
    for path,text in texts.items():
        prose, open_fence = prose_only(text)
        if open_fence:
            structural_errors.append(f'Unclosed code fence: {path.name}')
        link_text = re.sub(r'\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\$)(?:\\.|[^$\\])*?(?<!\\)\$', '', prose)
        link_text = re.sub(r'`[^`\n]*`','',link_text)
        for match in re.finditer(r'(?<!!)\[[^\]\n]+\]\((<[^>]+>|[^)\s]+)(?:\s+"[^\"]*")?\)',link_text):
            target = match.group(1).strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            local = (path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            if not local.exists():
                structural_errors.append(f'Broken link: {path.name} -> {target}')
            elif parsed.fragment and local.suffix=='.md':
                other_text = texts.get(local) or local.read_text(encoding='utf-8-sig')
                if unquote(parsed.fragment).lower() not in anchors(other_text):
                    structural_errors.append(f'Broken anchor: {path.name} -> {target}')
        if path.parent.name=='chapters':
            for q in range(1,4):
                qid = f'M{int(path.name[:2]):02d}-Q{q}'
                if qid not in text or qid not in solutions:
                    structural_errors.append(f'Missing exercise or solution: {qid}')
    if len(chapters)!=7:
        structural_errors.append(f'Expected7algaechapters, found{len(chapters)}')
    report = dict(scope="Selected synthetic calculations, finite differences and algae-extension document structure; no actual model training or device measurement",
                  checks=checks, count=len(checks), passed=sum(c['passed'] for c in checks),
                  failed=[c for c in checks if not c['passed']],
                  structure=dict(documents=len(paths),chapters=len(chapters),exercise_pairs=21,
                                 errors=structural_errors))
    output = BOOK/'validation'/'algae_report.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(count=report['count'],passed=report['passed'],failed=report['failed'],
                          structure=report['structure'],report=str(output)),ensure_ascii=False,indent=2))
    return 1 if report['failed'] or structural_errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
