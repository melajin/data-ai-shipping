"""Resource checking utility for Track 2 S2 segment experiments."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import psutil

TRACK_DIR = Path(__file__).resolve().parent
CHECKS_FILE = TRACK_DIR / "resource_checks.json"


def record_resource_check(stage: str, expected_peak_mb: float = 450.0) -> dict:
    """Check and record RAM snapshot to resource_checks.json."""
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    mem = psutil.virtual_memory()
    available_mb = mem.available / (1024 * 1024)
    
    other_pythons = []
    current_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "memory_info", "create_time"]):
        try:
            info = proc.info
            p_name = (info.get("name") or "").lower()
            if info["pid"] != current_pid and "python" in p_name:
                other_pythons.append({
                    "pid": int(info["pid"]),
                    "name": info.get("name"),
                    "rss_mb": round(info["memory_info"].rss / (1024 * 1024), 2),
                    "create_time": info.get("create_time"),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    snap = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stage": stage,
        "available_mb": round(available_mb, 2),
        "expected_peak_mb": round(expected_peak_mb, 2),
        "minimum_free_mb": 1024.0,
        "allowed": bool(available_mb >= 1024.0),
        "other_python_processes": other_pythons,
        "action_on_shortfall": "stop stage before operation; do not terminate other processes",
    }
    
    checks = []
    if CHECKS_FILE.exists():
        try:
            data = json.loads(CHECKS_FILE.read_text(encoding="utf-8"))
            checks = data.get("checks", [])
        except Exception:
            checks = []
            
    checks.append(snap)
    CHECKS_FILE.write_text(json.dumps({"checks": checks}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    
    if not snap["allowed"]:
        raise RuntimeError(f"RAM check failed for stage '{stage}': available {available_mb:.1f} MB < 1024 MB minimum")
        
    return snap


if __name__ == "__main__":
    snap = record_resource_check("initial_test")
    print(f"Recorded snapshot: Available {snap['available_mb']} MB, allowed={snap['allowed']}")
