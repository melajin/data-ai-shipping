import json
import os
import psutil
from datetime import datetime, timezone
from pathlib import Path

RESOURCE_FILE = Path(__file__).resolve().parent / "resource_checks.json"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def check_ram(stage: str, expected_peak_mb: float = 100.0) -> dict:
    mem = psutil.virtual_memory()
    available_bytes = int(mem.available)
    available_mb = available_bytes / (1024 * 1024)
    available_gib = available_bytes / (1024 * 1024 * 1024)
    rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    
    record = {
        "timestamp_utc": utc_now(),
        "stage": stage,
        "available_ram_bytes": available_bytes,
        "available_ram_mb": round(available_mb, 2),
        "available_ram_gib": round(available_gib, 3),
        "process_rss_mb": round(rss_mb, 2),
        "expected_peak_mb": expected_peak_mb,
        "passed_guard": available_mb > expected_peak_mb + 200,
    }
    
    records = []
    if RESOURCE_FILE.exists():
        try:
            records = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
        except Exception:
            records = []
    records.append(record)
    RESOURCE_FILE.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    
    if not record["passed_guard"]:
        raise MemoryError(f"Insufficient RAM for stage '{stage}': Available {available_mb:.1f} MB, Expected peak {expected_peak_mb:.1f} MB")
    
    return record
