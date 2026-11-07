import csv
import gc
import json
import os
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from resource_guard import check_ram

R2_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
TAB_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")
RANK1_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts")

FOLDS = (0, 1, 2)
CLASSES = ["연안복합(0)", "자망(1)", "통발(2)", "채낚기(3)"]

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    cm = np.bincount(y_true * 4 + y_pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.int64)
    support = cm.sum(axis=1).astype(np.int64)
    predicted = cm.sum(axis=0).astype(np.int64)
    
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros(4, dtype=np.float64), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(4, dtype=np.float64), where=(precision + recall) > 0)
    
    correct = int(np.count_nonzero(y_true == y_pred))
    n = len(y_true)
    
    return {
        "n": n,
        "correct": correct,
        "micro_f1": correct / n if n > 0 else 0.0,
        "macro_f1": float(f1.mean()),
        "tp": tp.tolist(),
        "support": support.tolist(),
        "predicted": predicted.tolist(),
        "precision": precision.tolist(),
        "recall": recall.tolist(),
        "f1": f1.tolist(),
        "confusion_matrix": cm.tolist()
    }

def load_canonical_data():
    """Load canonical roster, labels, and day counts for INNER (2361) and OUTER (5897)."""
    inner_records = [] # (fold, role, rfid_id, y_true)
    outer_records = [] # (fold, role, rfid_id, y_true)
    
    for fold in FOLDS:
        es = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        out = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_outer.npz")
        
        for vid, y in zip(es["ids"], es["y_true"]):
            inner_records.append((fold, "INNER_ES", str(vid), int(y)))
        for vid, y in zip(sel["ids"], sel["y_true"]):
            inner_records.append((fold, "INNER_SELECT", str(vid), int(y)))
        for vid, y in zip(out["ids"], out["y_true"]):
            outer_records.append((fold, "OUTER", str(vid), int(y)))
            
    return inner_records, outer_records

def load_all_models(inner_records, outer_records):
    """Load all probability matrices for INNER and OUTER."""
    inner_keys = [(r[0], r[2]) for r in inner_records] # (fold, rfid_id)
    outer_keys = [r[2] for r in outer_records]         # rfid_id
    
    inner_y = np.array([r[3] for r in inner_records], dtype=np.int64)
    outer_y = np.array([r[3] for r in outer_records], dtype=np.int64)
    
    inner_probs = {}
    outer_probs = {}
    
    # 1. LightGBM seed 42
    p_in = np.zeros((len(inner_records), 4), dtype=np.float64)
    p_out = np.zeros((len(outer_records), 4), dtype=np.float64)
    idx_in, idx_out = 0, 0
    for fold in FOLDS:
        es = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        out = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_outer.npz")
        
        p_in[idx_in : idx_in + len(es["ids"])] = es["probabilities"]
        idx_in += len(es["ids"])
        p_in[idx_in : idx_in + len(sel["ids"])] = sel["probabilities"]
        idx_in += len(sel["ids"])
        
        p_out[idx_out : idx_out + len(out["ids"])] = out["probabilities"]
        idx_out += len(out["ids"])
    inner_probs["LightGBM_seed42"] = p_in
    outer_probs["LightGBM_seed42"] = p_out
    
    # 2. CatBoost seed 42
    p_in = np.zeros((len(inner_records), 4), dtype=np.float64)
    p_out = np.zeros((len(outer_records), 4), dtype=np.float64)
    idx_in, idx_out = 0, 0
    for fold in FOLDS:
        es = np.load(R2_DIR / f"fold_{fold}_candidate_catboost_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold}_candidate_catboost_inner_select.npz")
        out = np.load(R2_DIR / f"fold_{fold}_candidate_catboost_outer.npz")
        
        p_in[idx_in : idx_in + len(es["ids"])] = es["probabilities"]
        idx_in += len(es["ids"])
        p_in[idx_in : idx_in + len(sel["ids"])] = sel["probabilities"]
        idx_in += len(sel["ids"])
        
        p_out[idx_out : idx_out + len(out["ids"])] = out["probabilities"]
        idx_out += len(out["ids"])
    inner_probs["CatBoost"] = p_in
    outer_probs["CatBoost"] = p_out

    # 3. TabICLv2 seed 42
    for seed in [42, 2026]:
        # Inner
        tab_in_map = {}
        for fold in FOLDS:
            p = TAB_DIR / f"seed_{seed}" / f"fold_{fold}" / "inner_predictions.csv"
            with open(p, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    tab_in_map[(fold, r["rfid_id"])] = [float(r[f"p{c}"]) for c in range(4)]
        p_in = np.array([tab_in_map[k] for k in inner_keys], dtype=np.float64)
        
        # Outer
        tab_out_map = {}
        p = TAB_DIR / f"seed_{seed}" / "original_oof_predictions.csv"
        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                tab_out_map[r["rfid_id"]] = [float(r[f"p{c}"]) for c in range(4)]
        p_out = np.array([tab_out_map[k] for k in outer_keys], dtype=np.float64)
        
        inner_probs[f"TabICL_seed{seed}"] = p_in
        outer_probs[f"TabICL_seed{seed}"] = p_out

    # 4. rank1_experiments models
    rank1_candidates = [
        ("LightGBM_5seed_sqrt_macro", RANK1_DIR / "exp01" / "sqrt_macro"),
        ("LightGBM_5seed_sqrt_micro", RANK1_DIR / "exp01" / "sqrt_micro"),
        ("LightGBM_5seed_none_macro", RANK1_DIR / "exp01" / "none_macro"),
        ("LightGBM_5seed_none_micro", RANK1_DIR / "exp01" / "none_micro"),
        ("LightGBM_fold_inner_selected", RANK1_DIR / "exp01" / "fold_inner_selected"),
        ("Exp03_daily_summary", RANK1_DIR / "exp03" / "daily_summary"),
        ("Exp03_monthly_repeat", RANK1_DIR / "exp03" / "monthly_repeat"),
        ("Exp04_segment_weak_supervision", RANK1_DIR / "exp04" / "segment_weak_supervision"),
        ("Exp05_fold_local_binary_redist", RANK1_DIR / "exp05" / "fold_local_binary_redistribution"),
        ("Exp07_simple_mean_all_valid", RANK1_DIR / "exp07" / "predictions" / "simple_mean_all_valid_candidates"),
        ("Exp07_simple_mean_s6_four_cond", RANK1_DIR / "exp07" / "predictions" / "simple_mean_s6_four_conditions"),
        ("Exp08_reservoir_sequence", RANK1_DIR / "exp08" / "reservoir_sequence"),
    ]
    
    for name, dir_path in rank1_candidates:
        in_p_file = dir_path / "inner_predictions.csv"
        out_p_file = dir_path / "outer_predictions.csv"
        if not (in_p_file.exists() and out_p_file.exists()):
            continue
            
        with open(in_p_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            in_map = {(int(r["fold"]), r["rfid_id"]): [float(r[f"p{c}"]) for c in range(4)] for r in reader}
            
        with open(out_p_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            out_map = {r["rfid_id"]: [float(r[f"p{c}"]) for c in range(4)] for r in reader}
            
        inner_probs[name] = np.array([in_map[k] for k in inner_keys], dtype=np.float64)
        outer_probs[name] = np.array([out_map[k] for k in outer_keys], dtype=np.float64)

    return inner_y, outer_y, inner_probs, outer_probs

def main():
    check_ram("exp3a_inventory_start", expected_peak_mb=120.0)
    
    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    
    print(f"Loaded {len(inner_probs)} models across INNER (N={len(inner_y)}) and OUTER (N={len(outer_y)}).")
    
    # 1. Individual model performance
    results_inner = {}
    results_outer = {}
    
    print("\n" + "="*90)
    print("INDIVIDUAL MODEL PERFORMANCE COMPARISON (OUTER N=5,897 vs INNER N=2,361)")
    print("="*90)
    header = f"{'Model Name':<32} | {'OUTER Correct':<14} | {'OUTER micro-F1':<14} | {'OUTER macro-F1':<14} | {'TP(0,1,2,3)':<20} | {'INNER Correct':<14} | {'INNER micro-F1':<14}"
    print(header)
    print("-" * len(header))
    
    for name in inner_probs:
        p_in = inner_probs[name]
        p_out = outer_probs[name]
        
        pred_in = p_in.argmax(axis=1)
        pred_out = p_out.argmax(axis=1)
        
        m_in = compute_metrics(inner_y, pred_in)
        m_out = compute_metrics(outer_y, pred_out)
        
        results_inner[name] = m_in
        results_outer[name] = m_out
        
        tp_str = f"{m_out['tp'][0]},{m_out['tp'][1]},{m_out['tp'][2]},{m_out['tp'][3]}"
        print(f"{name:<32} | {m_out['correct']:<5}/5897     | {m_out['micro_f1']:.6f}       | {m_out['macro_f1']:.6f}       | {tp_str:<20} | {m_in['correct']:<5}/2361     | {m_in['micro_f1']:.6f}")

    # 2. Key Oracle Analysis (OUTER and INNER)
    # Focus on the core trio: LightGBM_5seed_sqrt_macro (or seed42), CatBoost, TabICL_seed42
    core_models = ["LightGBM_seed42", "LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42", "TabICL_seed2026"]
    
    print("\n" + "="*90)
    print("ORACLE UPPER BOUND ANALYSIS (Any model correct)")
    print("="*90)
    
    for split_name, y, probs_dict in [("INNER (2,361)", inner_y, inner_probs), ("OUTER (5,897)", outer_y, outer_probs)]:
        print(f"\n--- {split_name} ---")
        preds = {name: p.argmax(axis=1) for name, p in probs_dict.items()}
        
        # Core combinations
        combos = [
            ("LightGBM_seed42 + TabICL_seed42", ["LightGBM_seed42", "TabICL_seed42"]),
            ("LightGBM_5seed + TabICL_seed42", ["LightGBM_5seed_sqrt_macro", "TabICL_seed42"]),
            ("LightGBM_seed42 + CatBoost + TabICL_seed42", ["LightGBM_seed42", "CatBoost", "TabICL_seed42"]),
            ("LightGBM_5seed + CatBoost + TabICL_seed42", ["LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42"]),
            ("LightGBM_5seed + CatBoost + TabICL_seed42 + TabICL_seed2026", ["LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42", "TabICL_seed2026"]),
            ("All 16 models oracle", list(probs_dict.keys())),
        ]
        
        for label, model_list in combos:
            any_correct = np.zeros(len(y), dtype=bool)
            for m in model_list:
                any_correct |= (preds[m] == y)
            oracle_correct = int(np.count_nonzero(any_correct))
            oracle_micro = oracle_correct / len(y)
            print(f"  {label:<55}: {oracle_correct}/{len(y)} ({oracle_micro:.6f})")

    # 3. Class-by-Class Strengths and Weaknesses
    print("\n" + "="*90)
    print("CLASS-BY-CLASS RECALL & PRECISION BREAKDOWN (OUTER 5,897)")
    print("="*90)
    class_header = f"{'Model':<30} | {'Class 0 (연안복합)':<20} | {'Class 1 (자망)':<20} | {'Class 2 (통발)':<20} | {'Class 3 (채낚기)':<20}"
    print(class_header)
    print("-" * len(class_header))
    for name in ["LightGBM_seed42", "LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42", "TabICL_seed2026"]:
        m = results_outer[name]
        c0 = f"R:{m['recall'][0]:.3f} P:{m['precision'][0]:.3f} ({m['tp'][0]})"
        c1 = f"R:{m['recall'][1]:.3f} P:{m['precision'][1]:.3f} ({m['tp'][1]})"
        c2 = f"R:{m['recall'][2]:.3f} P:{m['precision'][2]:.3f} ({m['tp'][2]})"
        c3 = f"R:{m['recall'][3]:.3f} P:{m['precision'][3]:.3f} ({m['tp'][3]})"
        print(f"{name:<30} | {c0:<20} | {c1:<20} | {c2:<20} | {c3:<20}")

    # Save 3A results to json
    report_3a = {
        "inner_metrics": results_inner,
        "outer_metrics": results_outer,
    }
    with open(Path(__file__).resolve().parent / "experiment_3a_inventory.json", "w", encoding="utf-8") as f:
        json.dump(report_3a, f, indent=2, ensure_ascii=False)
        
    gc.collect()
    check_ram("exp3a_inventory_end", expected_peak_mb=120.0)
    print("\nExperiment 3A successfully finished and saved to experiment_3a_inventory.json!")

if __name__ == "__main__":
    main()
