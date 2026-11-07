import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

t1_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
if t1_path.exists():
    with np.load(t1_path) as z:
        print("Track1 keys:", z.files)
        for k in z.files:
            print(" ", k, z[k].shape, z[k].dtype)

t2_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\probabilities_track2.npz")
if t2_path.exists():
    with np.load(t2_path) as z:
        print("Track2 keys:", z.files)
        for k in z.files:
            print(" ", k, z[k].shape, z[k].dtype)
