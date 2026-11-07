# -*- coding: utf-8 -*-
"""Full archive extraction and byte-level comparison of 문제 데이터_수정_1103_v2.zip to F:\\문제 데이터_수정_1103_v2.
"""
import os
import sys
import time
import zipfile
import hashlib
import json
import datetime
import psutil

ZIP_PATH = r"C:\Users\dlehs\Downloads\문제 데이터_수정_1103_v2.zip"
TARGET_DIR = r"F:\문제 데이터_수정_1103_v2"
OLD_DIR = r"F:\문제 데이터_수정_1027"
AUDIT_LOG_PATH = r"testB\intake\1103_v2\extraction_audit.json"

KST = datetime.timezone(datetime.timedelta(hours=9))


def get_now_kst():
    return datetime.datetime.now(KST).isoformat()


def file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    start_time = time.time()
    vm_start = psutil.virtual_memory()
    print(f"[{get_now_kst()}] Starting full extraction to {TARGET_DIR}")
    print(f"RAM available: {vm_start.available / (1024**2):.1f} MiB")
    
    os.makedirs(TARGET_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    
    records = []
    
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        infolist = z.infolist()
        total_files = len(infolist)
        print(f"Total entries in archive: {total_files}")
        
        for idx, info in enumerate(infolist, 1):
            target_path = os.path.join(TARGET_DIR, info.filename)
            old_path = os.path.join(OLD_DIR, info.filename)
            
            if info.is_dir():
                os.makedirs(target_path, exist_ok=True)
                records.append({
                    "name": info.filename,
                    "is_dir": True,
                    "size": 0,
                    "status": "directory_created"
                })
                continue
                
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            t0 = time.time()
            print(f"[{idx}/{total_files}] Extracting {info.filename} ({info.file_size:,} bytes)...", end="", flush=True)
            
            # Extract
            z.extract(info, TARGET_DIR)
            ext_time = time.time() - t0
            
            # Compute SHA256 of extracted file
            sha_new = file_sha256(target_path)
            
            # Compare with old file if exists
            old_exists = os.path.exists(old_path)
            sha_old = None
            byte_identical = None
            old_size = None
            
            if old_exists:
                old_size = os.path.getsize(old_path)
                if old_size == info.file_size:
                    # Compare full content
                    sha_old = file_sha256(old_path)
                    byte_identical = (sha_new == sha_old)
                else:
                    sha_old = file_sha256(old_path)
                    byte_identical = False
            
            status_str = f" Done ({ext_time:.1f}s) | Identical to 1027: {byte_identical}"
            print(status_str)
            
            records.append({
                "name": info.filename,
                "is_dir": False,
                "file_size": info.file_size,
                "extract_seconds": round(ext_time, 2),
                "target_path": target_path,
                "sha256_new": sha_new,
                "old_path": old_path,
                "old_exists": old_exists,
                "old_size": old_size,
                "sha256_old": sha_old,
                "byte_identical_to_1027": byte_identical,
            })
            
    total_time = time.time() - start_time
    vm_end = psutil.virtual_memory()
    
    identical_count = sum(r.get("byte_identical_to_1027") is True for r in records if not r["is_dir"])
    different_count = sum(r.get("byte_identical_to_1027") is False for r in records if not r["is_dir"])
    new_files_count = sum(r.get("old_exists") is False for r in records if not r["is_dir"])
    
    summary = {
        "timestamp_kst": get_now_kst(),
        "archive_path": ZIP_PATH,
        "target_directory": TARGET_DIR,
        "old_directory": OLD_DIR,
        "total_seconds": round(total_time, 2),
        "total_entries": total_files,
        "regular_files": sum(not r["is_dir"] for r in records),
        "byte_identical_files_count": identical_count,
        "different_files_count": different_count,
        "new_files_count": new_files_count,
        "ram_before_mib": round(vm_start.available / (1024**2), 2),
        "ram_after_mib": round(vm_end.available / (1024**2), 2),
        "files": records,
    }
    
    with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    print("\n=== Extraction & Audit Summary ===")
    print(f"Total time: {total_time:.1f} seconds")
    print(f"Total regular files: {summary['regular_files']}")
    print(f"Byte-identical to 1027: {identical_count}")
    print(f"DIFFERENT from 1027: {different_count}")
    print(f"Audit log saved to: {AUDIT_LOG_PATH}")
    
    if different_count > 0:
        print("\nFiles with differences:")
        for r in records:
            if r.get("byte_identical_to_1027") is False:
                print(f"  * {r['name']}: New SHA={r['sha256_new'][:16]}..., Old SHA={r['sha256_old'][:16]}...")


if __name__ == "__main__":
    main()
