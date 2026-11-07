from __future__ import annotations

import datetime as dt
import gc
import json
import os
import platform
import sys
from pathlib import Path
import numpy as np

TRACK1_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn")
RESOURCE_CHECKS_FILE = TRACK1_DIR / "resource_checks.json"


def record_resource_check(stage: str, expected_peak_mb: float = 350.0) -> dict:
    """Record memory check into resource_checks.json.
    
    Verifies that available RAM is at least expected_peak_mb (with safety margin >= 1.0 GiB).
    Never terminates other processes.
    """
    import psutil

    memory = psutil.virtual_memory()
    available_bytes = int(memory.available)
    expected_peak_bytes = int(expected_peak_mb * 1024 * 1024)
    minimum_free_bytes = int(1.0 * 1024 * 1024 * 1024)  # 1.0 GiB safety gate

    others = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "create_time"]):
        try:
            info = proc.info
            if info["pid"] != os.getpid() and "python" in (info.get("name") or "").lower():
                others.append({
                    "pid": int(info["pid"]),
                    "name": info.get("name"),
                    "rss_bytes": int(info["memory_info"].rss),
                    "create_time": info.get("create_time"),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    snap = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stage": stage,
        "available_bytes": available_bytes,
        "available_gib": round(available_bytes / (1024**3), 3),
        "expected_peak_bytes": expected_peak_bytes,
        "expected_peak_mb": expected_peak_mb,
        "minimum_free_bytes": minimum_free_bytes,
        "other_python_processes": others,
        "allowed": bool(available_bytes >= minimum_free_bytes),
        "action_on_shortfall": "stop stage before operation; do not terminate other processes",
    }

    TRACK1_DIR.mkdir(parents=True, exist_ok=True)
    existing_checks = []
    if RESOURCE_CHECKS_FILE.exists():
        try:
            data = json.loads(RESOURCE_CHECKS_FILE.read_text(encoding="utf-8"))
            existing_checks = data.get("checks", [])
        except Exception:
            existing_checks = []

    existing_checks.append(snap)
    save_json(RESOURCE_CHECKS_FILE, {"checks": existing_checks})

    if not snap["allowed"]:
        raise RuntimeError(
            f"RAM gate violated at stage '{stage}': available {snap['available_gib']} GiB < 1.0 GiB minimum free!"
        )
    return snap


def calc_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calculate micro-F1, macro-F1, per-class metrics and confusion matrix."""
    cm = np.zeros((4, 4), dtype=np.int64)
    for actual, predicted in zip(y_true.tolist(), y_pred.tolist()):
        cm[int(actual), int(predicted)] += 1
    support = cm.sum(axis=1)
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = support - tp
    precision = np.divide(tp, tp + fp, out=np.zeros(4, dtype=np.float64), where=(tp + fp) != 0)
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support != 0)
    f1 = np.divide(
        2 * precision * recall, precision + recall,
        out=np.zeros(4, dtype=np.float64), where=(precision + recall) != 0
    )
    return {
        "n": int(len(y_true)),
        "correct": int(tp.sum()),
        "micro_f1": float(tp.sum() / len(y_true)),
        "macro_f1": float(f1.mean()),
        "support": support.tolist(),
        "tp": tp.tolist(),
        "fp": fp.tolist(),
        "fn": fn.tolist(),
        "precision": precision.tolist(),
        "recall": recall.tolist(),
        "class_f1": f1.tolist(),
        "confusion": cm.tolist(),
    }


def save_json(path: Path | str, value: dict | list) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
