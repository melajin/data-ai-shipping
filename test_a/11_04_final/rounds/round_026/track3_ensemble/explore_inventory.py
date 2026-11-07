import csv
import gc
import json
import os
import sys
from pathlib import Path
import numpy as np

# Restrict threads to 1
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

from resource_guard import check_ram

def main():
    check_ram("explore_inventory_start", expected_peak_mb=80.0)
    
    # 1. Round 002 probability files
    r2_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
    r2_files = sorted(r2_dir.glob("*.npz"))
    print(f"--- Round 002 probability files ({len(r2_files)}) ---")
    for f in r2_files:
        with np.load(f, allow_pickle=False) as z:
            print(f"  {f.name}: keys={list(z.keys())}, ids={len(z['ids'])}, probs={z['probabilities'].shape}")
    
    # 2. TabICLv2 files
    tab_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")
    for seed in [42, 2026]:
        oof = tab_dir / f"seed_{seed}" / "original_oof_predictions.csv"
        if oof.exists():
            with open(oof, "r", encoding="utf-8-sig") as stream:
                reader = csv.reader(stream)
                header = next(reader)
                count = sum(1 for _ in reader)
            print(f"  TabICL seed_{seed} OOF: header={header}, rows={count}")
        for fold in [0, 1, 2]:
            inner = tab_dir / f"seed_{seed}" / f"fold_{fold}" / "inner_predictions.csv"
            if inner.exists():
                with open(inner, "r", encoding="utf-8-sig") as stream:
                    reader = csv.reader(stream)
                    header = next(reader)
                    count = sum(1 for _ in reader)
                print(f"  TabICL seed_{seed} fold_{fold} inner: header={header}, rows={count}")

    # 3. rank1_experiments_20261104
    rank1_dir = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts")
    print("\n--- rank1_experiments_20261104 outer / inner files ---")
    for p in sorted(rank1_dir.glob("exp*/**/*predictions.csv")):
        with open(p, "r", encoding="utf-8-sig") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            count = sum(1 for _ in reader)
        rel = p.relative_to(rank1_dir)
        print(f"  {rel}: header={header[:6]}... rows={count}")
        
    gc.collect()
    check_ram("explore_inventory_end", expected_peak_mb=80.0)

if __name__ == "__main__":
    main()
