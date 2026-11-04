#!/usr/bin/env python3
"""Visualize the completed frozen synthetic comparison; never fit or select."""
from pathlib import Path
import json
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
font_path = Path("C:/Windows/Fonts/malgun.ttf")
if font_path.is_file():
    font_manager.fontManager.addfont(str(font_path))
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font_path)).get_name()
plt.rcParams["axes.unicode_minus"] = False


def main():
    input_path = ROOT / "outputs/critique_comparison_20261027/final/results.json"
    result = json.loads(input_path.read_text(encoding="utf-8"))
    stages = result["stage_results"]
    if len(stages) != 9 or any(len(stage["records"]) != 20 or not stage.get("summary") for stage in stages):
        raise SystemExit("Nine complete, frozen 20-run comparisons are required before plotting.")
    labels = ["기준 MLP 400", "MLP 1200 / L2 0", "MLP 1200 / L2 .001",
              "MLP 1200 / L2 .01", "선형 / L2 .01", "ExtraTrees",
              "MLP + 합성 속력", "MLP + 보폭 대조", "MLP + 합성 Δt 대조"]
    y = np.arange(len(stages))
    avg = lambda rows, role, metric, key="metrics": statistics.mean(r[key][role][metric] for r in rows)
    normal = [avg(s["records"], "normal", "macro_f1") for s in stages]
    shift = [avg(s["records"], "shift", "macro_f1") for s in stages]
    raw_nll = [avg(s["records"], "shift", "nll", "before_calibration") for s in stages]
    cal_nll = [avg(s["records"], "shift", "nll") for s in stages]
    fig, (left, right) = plt.subplots(1, 2, figsize=(16, 8), constrained_layout=True)
    left.barh(y - 0.18, normal, .36, label="보통 조건", color="#376da8")
    left.barh(y + 0.18, shift, .36, label="조건 변화", color="#e28a38")
    left.set_yticks(y, labels)
    left.invert_yaxis()
    left.set_xlim(0, 1)
    left.set_xlabel("Macro F1 (높을수록 좋음)")
    left.set_title("클래스별 성능의 균형")
    left.legend(loc="lower right")
    left.grid(axis="x", alpha=.25)
    right.barh(y - .18, raw_nll, .36, label="보정 전", color="#79a79d")
    right.barh(y + .18, cal_nll, .36, label="보정 후", color="#a55051")
    right.set_yticks(y, labels)
    right.invert_yaxis()
    right.set_xlabel("조건 변화 NLL (낮을수록 좋음)")
    right.set_title("확률 손실과 온도 보정")
    right.legend(loc="lower right")
    right.grid(axis="x", alpha=.25)
    fig.suptitle("합성자료 고정 비교: 생성 seed 10개, 초기화 2개 평균\n"
                 "보조·탐색 결과 | 실제 선박 성능 아님", fontsize=15)
    output = ROOT / "outputs/critique_comparison_summary_20261027.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
