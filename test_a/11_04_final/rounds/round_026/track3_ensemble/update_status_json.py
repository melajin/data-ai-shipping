import json
from pathlib import Path

status_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\STATUS.json")
data = json.loads(status_path.read_text(encoding="utf-8-sig"))

data["updated_at_utc"] = "2026-11-05T05:25:00.000000+00:00"
data["current_round"] = "round_026"
data["round_status"] = "completed_verified_grand_fusion_success"
data["paths"]["round"] = "rounds/round_026"
data["full_status_report"] = "reports/20261105_round026_FULL_STATUS_REPORT.md"

data["scores"]["adopted_best"] = {
    "name": "T3_Grand_Fusion_BothTab_T1_w10",
    "micro_f1": 0.6023401729693064,
    "macro_f1": 0.521551724137931,
    "correct": 3552,
    "n": 5897,
    "tp": [2541, 814, 105, 92],
    "protection_passed": True,
    "delta_vs_baseline": 55,
    "bootstrap_ci95": [0.002709, 0.016619],
    "source": "rounds/round_026/track3_ensemble/track3_results.json; rounds/round_026/ROUND_REPORT.md"
}

data["scores"]["round_026"] = {
    "evaluation_population": "Repeatedly exposed development OUTER, 5897 vessels",
    "grand_fusion": {
        "n": 5897,
        "correct": 3552,
        "micro_f1": 0.6023401729693064,
        "macro_f1": 0.521551724137931,
        "tp": [2541, 814, 105, 92],
        "delta_vs_baseline_3497": 55,
        "delta_vs_seed42_3476": 76,
        "bootstrap_ci95_vs_3497": [0.002709, 0.016619],
        "protection_passed": True
    },
    "track3_pure_trio": {
        "n": 5897,
        "correct": 3538,
        "micro_f1": 0.5999660844497202,
        "macro_f1": 0.5174850849683616,
        "tp": [2538, 801, 106, 93],
        "delta_vs_baseline_3497": 41,
        "protection_passed": True
    },
    "track1_hellinger_knn": {
        "n": 5897,
        "correct": 3466,
        "micro_f1": 0.587756486348991,
        "macro_f1": 0.5220173678735235,
        "tp": [2346, 927, 117, 76]
    },
    "track2_s2_segments_sqrt": {
        "n": 5897,
        "correct": 3371,
        "micro_f1": 0.5716465999660845,
        "macro_f1": 0.5141384073384214,
        "tp": [2216, 934, 144, 77]
    }
}

status_path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
print("STATUS.json successfully updated for round_026!")
