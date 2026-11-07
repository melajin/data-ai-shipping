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

def main():
    check_ram("explore_tracks_1_2_start", expected_peak_mb=100.0)

    # 1. Track 1
    t1_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
    with np.load(t1_npz_path, allow_pickle=False) as z:
        print("=== Track 1 probabilities_track1.npz ===")
        for k in z.files:
            arr = z[k]
            print(f"  {k}: shape={arr.shape}, dtype={arr.dtype}")
            if "id" in k or "y" in k:
                print(f"    first 5: {arr[:5]}")
            elif "prob" in k:
                print(f"    first row: {arr[0]}")

    t1_json_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\track1_results.json")
    if t1_json_path.exists():
        t1_res = json.loads(t1_json_path.read_text(encoding="utf-8"))
        print("\nTrack 1 Results JSON summary:")
        print(json.dumps({k: v for k, v in t1_res.items() if not isinstance(v, dict) or len(str(v)) < 150}, indent=2, ensure_ascii=False))

    # 2. Track 2
    t2_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\probabilities_track2.npz")
    with np.load(t2_npz_path, allow_pickle=False) as z:
        print("\n=== Track 2 probabilities_track2.npz ===")
        for k in z.files:
            arr = z[k]
            print(f"  {k}: shape={arr.shape}, dtype={arr.dtype}")
            if "id" in k or "y" in k:
                print(f"    first 5: {arr[:5]}")
            elif "prob" in k:
                print(f"    first row: {arr[0]}")

    t2_json_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\track2_results.json")
    if t2_json_path.exists():
        t2_res = json.loads(t2_json_path.read_text(encoding="utf-8"))
        print("\nTrack 2 Results JSON summary:")
        print(json.dumps({k: v for k, v in t2_res.items() if not isinstance(v, dict) or len(str(v)) < 150}, indent=2, ensure_ascii=False))

    check_ram("explore_tracks_1_2_end", expected_peak_mb=100.0)

if __name__ == "__main__":
    main()
