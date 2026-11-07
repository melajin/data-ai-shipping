"""2026 학습 기간 전체 선단의 시간별 기하 요약을 추출한다.

목적은 음성 표본(미사고 선박)의 확보다. 지금까지의 평가 집단은 사고 연결 선박 82척뿐이어서
정밀도를 실측할 수 없었다. 2026 자료는 학습 사용이 허용되므로 여기서 선박 단위 사고 판정을
적합할 수 있다. 테스트 자료(2025)는 건드리지 않는다.

기하 정의는 round_008 extract_geometry.py의 재구성 경로와 동일하다.
  coords  = 모든 part의 모든 점
  len_m   = part 내 연속 점들의 haversine 합
  bbox_m  = (min lon, min lat) ~ (max lon, max lat) haversine
  cen_*   = 전체 점의 산술평균
  ts      = source_clock_hour(part_dt, rfid_time)
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROUND_DIR = Path(__file__).resolve().parent
ROOT = ROUND_DIR.parents[2]
sys.path.insert(0, str(ROOT / "testB/final/round_008_20261106"))
RAW_DIR = Path(r"F:/문제 데이터_수정_1027/vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터")
EXPECTED_MONTH_ROWS = {1: 497942, 2: 479290, 3: 657292, 4: 717294, 5: 761846, 6: 773405}
RESERVE_MIB = 640
EXPECTED_PEAK_MIB = 900

csv.field_size_limit(1 << 24)


def available_mib() -> float:
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(n, ctypes.c_ulonglong) for n in
                      ("total", "available", "total_page", "available_page",
                       "total_virtual", "available_virtual", "extended")]]
    s = Status()
    s.length = ctypes.sizeof(s)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
        raise MemoryError("가용 RAM을 읽을 수 없다")
    return int(s.available) / 2 ** 20


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--months", default="1,2,3,4,5,6")
    args = ap.parse_args()
    out: Path = args.output.resolve()
    if out.exists():
        raise SystemExit(f"새 출력 폴더가 필요하다: {out}")

    free = available_mib()
    if free < EXPECTED_PEAK_MIB + RESERVE_MIB:
        raise SystemExit(f"RAM 부족으로 보류: 가용 {free:.0f}MiB < 예상 {EXPECTED_PEAK_MIB}+여유 {RESERVE_MIB}MiB")

    from extract_geometry import haversine_m, parse_multilinestring, source_clock_hour
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    out.mkdir(parents=True)
    months = [int(m) for m in args.months.split(",")]
    started = time.perf_counter()
    stats = {"months": {}, "unparsed_examples": []}
    vessels: set[str] = set()
    total_rows = 0
    total_skipped = 0

    for month in months:
        path = RAW_DIR / f"vpass_{month}월 데이터.csv"
        if not path.is_file():
            raise SystemExit(f"원자료 없음: {path}")
        t0 = time.perf_counter()
        rid_l, ts_l, ord_l, len_l, bbox_l, lon_l, lat_l, nc_l = ([] for _ in range(8))
        read = skipped = 0
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            if header[:4] != ["part_dt", "rfid_id", "rfid_time", "geom"]:
                raise SystemExit(f"{month}월 헤더가 예상과 다르다: {header[:5]}")
            for row_index, row in enumerate(reader):
                read += 1
                try:
                    part_dt, rfid, rfid_time_s, geom = row[0], row[1], row[2], row[3]
                    parts = parse_multilinestring(geom)
                    coords = [pt for part in parts for pt in part]
                    if not coords or not all(math.isfinite(x) and math.isfinite(y) for x, y in coords):
                        raise ValueError("non_finite")
                    ts = source_clock_hour(part_dt, int(rfid_time_s))
                    length = sum(haversine_m(a[0], a[1], b[0], b[1])
                                 for part in parts for a, b in zip(part, part[1:]))
                    xs = [x for x, _ in coords]
                    ys = [y for _, y in coords]
                    bbox = haversine_m(min(xs), min(ys), max(xs), max(ys))
                except (ValueError, IndexError, TypeError) as exc:
                    skipped += 1
                    if len(stats["unparsed_examples"]) < 20:
                        stats["unparsed_examples"].append(
                            {"month": month, "row_index": row_index, "error": str(exc)[:80]})
                    continue
                rid_l.append(rfid)
                ts_l.append(ts)
                ord_l.append(month * 10_000_000 + row_index)
                len_l.append(length)
                bbox_l.append(bbox)
                lon_l.append(sum(xs) / len(xs))
                lat_l.append(sum(ys) / len(ys))
                nc_l.append(len(coords))
                vessels.add(rfid)

        if read != EXPECTED_MONTH_ROWS[month]:
            raise SystemExit(f"{month}월 행 수 불일치: 읽음 {read} 기대 {EXPECTED_MONTH_ROWS[month]}")
        table = pa.table({"rfid_id": pa.array(rid_l, pa.string()),
                          "ts": pa.array(ts_l, pa.int64()),
                          "source_ordinal": pa.array(ord_l, pa.int64()),
                          "len_m": pa.array(len_l, pa.float64()),
                          "bbox_m": pa.array(bbox_l, pa.float64()),
                          "cen_lon": pa.array(lon_l, pa.float64()),
                          "cen_lat": pa.array(lat_l, pa.float64()),
                          "n_coords": pa.array(nc_l, pa.int64())})
        pq.write_table(table, out / f"hourly_{month:02d}.parquet", compression="zstd")
        elapsed = time.perf_counter() - t0
        stats["months"][str(month)] = {"rows_read": read, "rows_written": len(rid_l),
                                       "skipped": skipped, "seconds": round(elapsed, 1),
                                       "vessels_cumulative": len(vessels)}
        total_rows += len(rid_l)
        total_skipped += skipped
        print(f"{month}월 완료: {len(rid_l):,}행 기록 / {skipped}행 제외 / {elapsed:.0f}초 "
              f"/ 누적 선박 {len(vessels):,}", flush=True)
        del rid_l, ts_l, ord_l, len_l, bbox_l, lon_l, lat_l, nc_l, table

    stats.update({"completed_at": datetime.now(timezone.utc).astimezone().isoformat(),
                  "raw_dir": str(RAW_DIR), "total_rows_written": total_rows,
                  "total_rows_skipped": total_skipped, "vessels": len(vessels),
                  "elapsed_seconds": round(time.perf_counter() - started, 1),
                  "available_mib_at_start": round(free, 1),
                  "purpose": "미사고 선박 음성 표본 확보 (2026 학습 기간)",
                  "test_data_touched": False})
    (out / "extract_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "vessel_roster.txt").write_text("\n".join(sorted(vessels)) + "\n", encoding="utf-8")
    print(json.dumps({k: stats[k] for k in
                      ("total_rows_written", "total_rows_skipped", "vessels", "elapsed_seconds")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
