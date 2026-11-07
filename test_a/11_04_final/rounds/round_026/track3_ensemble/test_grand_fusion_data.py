import json
import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from resource_guard import check_ram
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

def main():
    check_ram("test_grand_fusion_data_start", expected_peak_mb=100.0)

    inner_records, outer_records = load_canonical_data()
    print(f"Canonical INNER count: {len(inner_records)}, OUTER count: {len(outer_records)}")
    
    # 1. Verify Track 1 mapping
    t1_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
    with np.load(t1_npz_path, allow_pickle=False) as z:
        t1_vids = z["vessel_ids"].astype(str)
        t1_outer_probs = z["outer_probs"]
        t1_y = z["y_true"]
        
        t1_inner_f0 = z["inner_probs_fold0"]
        t1_inner_f1 = z["inner_probs_fold1"]
        t1_inner_f2 = z["inner_probs_fold2"]

    # Check outer mapping
    t1_outer_by_id = {vid: (t1_outer_probs[i], t1_y[i]) for i, vid in enumerate(t1_vids)}
    assert len(t1_outer_by_id) == 5897
    
    outer_probs_t1 = np.zeros((len(outer_records), 4), dtype=np.float32)
    for i, r in enumerate(outer_records):
        vid, y_true = r[2], r[3]
        assert vid in t1_outer_by_id, f"Vessel {vid} missing in Track 1 outer"
        prob, y_t1 = t1_outer_by_id[vid]
        assert y_t1 == y_true, f"Label mismatch for {vid}: {y_t1} vs {y_true}"
        outer_probs_t1[i] = prob
        
    print(f"Track 1 OUTER mapped perfectly: shape={outer_probs_t1.shape}")

    # Check inner mapping for Track 1
    # Check inner order in fold_{f}_features.npz
    exp01_dir = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
    t1_inner_probs = [t1_inner_f0, t1_inner_f1, t1_inner_f2]
    
    inner_probs_t1_by_fold_id = {}
    for f in FOLDS:
        with np.load(exp01_dir / f"fold_{f}_features.npz") as zf:
            f_ids = zf["rfid_ids"].astype(str)
            f_roles = zf["roles"].astype(str)
            f_inner_ids = f_ids[f_roles == "INNER"]
            assert len(f_inner_ids) == 787
            p_f = t1_inner_probs[f]
            for j, vid in enumerate(f_inner_ids):
                inner_probs_t1_by_fold_id[(f, vid)] = p_f[j]

    # Map onto canonical inner_records
    inner_probs_t1 = np.zeros((len(inner_records), 4), dtype=np.float32)
    for i, r in enumerate(inner_records):
        f, role, vid, y_true = r
        assert (f, vid) in inner_probs_t1_by_fold_id, f"Inner ({f}, {vid}) missing in Track 1"
        inner_probs_t1[i] = inner_probs_t1_by_fold_id[(f, vid)]

    print(f"Track 1 INNER mapped perfectly: shape={inner_probs_t1.shape}")

    # 2. Verify Track 2 mapping
    t2_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\probabilities_track2.npz")
    with np.load(t2_npz_path, allow_pickle=False) as z:
        t2_vids = z["vessel_ids"].astype(str)
        t2_y = z["y_true"]
        t2_cand_probs_sqrt = z["cand_outer_probs_sqrt"]
        t2_cand_probs_std = z["cand_outer_probs_std"]

    t2_outer_by_id_sqrt = {vid: (t2_cand_probs_sqrt[i], t2_y[i]) for i, vid in enumerate(t2_vids)}
    t2_outer_by_id_std = {vid: (t2_cand_probs_std[i], t2_y[i]) for i, vid in enumerate(t2_vids)}
    
    outer_probs_t2_sqrt = np.zeros((len(outer_records), 4), dtype=np.float32)
    outer_probs_t2_std = np.zeros((len(outer_records), 4), dtype=np.float32)
    for i, r in enumerate(outer_records):
        vid, y_true = r[2], r[3]
        assert vid in t2_outer_by_id_sqrt
        p_sqrt, y_t2 = t2_outer_by_id_sqrt[vid]
        assert y_t2 == y_true
        outer_probs_t2_sqrt[i] = p_sqrt
        outer_probs_t2_std[i] = t2_outer_by_id_std[vid][0]

    print(f"Track 2 OUTER mapped perfectly: shape={outer_probs_t2_sqrt.shape}")

    # Track 2 inner records
    t2_json_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\track2_results.json")
    t2_json = json.loads(t2_json_path.read_text(encoding="utf-8"))
    t2_inner_list = t2_json.get("outer_results", {}).get("inner_records", [])
    print(f"Track 2 inner records count in results JSON: {len(t2_inner_list)}")
    if t2_inner_list:
        print("Track 2 inner record keys:", list(t2_inner_list[0].keys()))

    # Check standalone performance of Track 1 and Track 2 on OUTER
    outer_y = np.array([r[3] for r in outer_records], dtype=np.int64)
    inner_y = np.array([r[3] for r in inner_records], dtype=np.int64)

    m_t1_out = compute_metrics(outer_y, outer_probs_t1.argmax(axis=1))
    m_t1_in = compute_metrics(inner_y, inner_probs_t1.argmax(axis=1))
    print(f"\nTrack 1 Alone: OUTER={m_t1_out['correct']}/5897 ({m_t1_out['micro_f1']:.6f}), TP={m_t1_out['tp']} | INNER={m_t1_in['correct']}/2361 ({m_t1_in['micro_f1']:.6f}), TP={m_t1_in['tp']}")

    m_t2_sqrt_out = compute_metrics(outer_y, outer_probs_t2_sqrt.argmax(axis=1))
    print(f"Track 2 (sqrt) Alone: OUTER={m_t2_sqrt_out['correct']}/5897 ({m_t2_sqrt_out['micro_f1']:.6f}), TP={m_t2_sqrt_out['tp']}")

    check_ram("test_grand_fusion_data_end", expected_peak_mb=100.0)

if __name__ == "__main__":
    main()
