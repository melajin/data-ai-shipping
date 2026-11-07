"""Synthetic contract checks for extract_geometry.py; never opens production inputs."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import tempfile
from pathlib import Path

import extract_geometry as eg


def main() -> dict:
    checks = []
    preflight = eg._ram_preflight()
    assert preflight["allowed"], f"synthetic Arrow fixture deferred for low RAM: {preflight}"
    import pyarrow as pa
    import pyarrow.parquet as pq
    # >=3 vertices with only two distinct coordinates is not informative.
    repeated = eg.part_features([(127.0, 37.0), (127.001, 37.0), (127.0, 37.0), (127.001, 37.0)], 0)
    assert repeated["n_points"] == 4 and repeated["n_unique_coords"] == 2 and not repeated["eligible"]
    checks.append("repeated-coordinate part with >=3 points but <3 unique coordinates is ineligible")

    two = eg.part_features([(127.0, 37.0), (127.001, 37.0)], 0)
    assert two["n_points"] == 2 and not two["eligible"]
    checks.append("two-point part is retained as an ineligible geometry")

    closed = eg.part_features([(127.0, 37.0), (127.001, 37.0), (127.001, 37.001), (127.0, 37.0)], 0)
    assert closed["eligible"] and closed["endpoint_distance_m"] == 0 and closed["shape_dl"] == 0
    checks.append("closed nonzero path has D=0, D/L=0, and remains eligible")

    a = [(127.0, 37.0), (127.001, 37.0), (127.002, 37.0)]
    b = [(127.0, 37.01), (127.001, 37.01), (127.002, 37.01)]
    multi = eg.summarize_parts([a, b])
    each = [eg.part_features(p, i) for i, p in enumerate((a, b))]
    assert multi["n_parts"] == 2 and multi["n_informative_parts"] == 2
    assert multi["chosen"]["path_length_m"] == max(f["path_length_m"] for f in each)
    checks.append("separate nearly straight parts are measured independently and never bridged")

    tied = eg.summarize_parts([a, a])
    assert tied["chosen"]["part_index"] == 0
    longer = eg.summarize_parts([a, a + [(127.003, 37.0)]])
    assert longer["chosen"]["part_index"] == 1
    checks.append("longest eligible part wins; exact path tie chooses smaller original part index")

    # Contract month boundary uses cumulative cache rows and a 0-based post-header row index.
    offsets = [0, 497942, 977232, 1634524, 2351818, 3113664]
    assert eg.ordinal_month_index(497941, offsets) == (1, 497941)
    assert eg.ordinal_month_index(497942, offsets) == (2, 0)
    checks.append("source ordinal at the month-1/month-2 boundary maps to month 2 row_index 0")

    # Exact upstream source clock: naïve YYYYMMDD hours since 1970, without timezone conversion.
    assert eg.source_clock_hour("19700101", 0) == 0
    assert eg.source_clock_hour("19700102", 3) == 27
    try:
        eg.source_clock_hour("19700230", 0)
        raise AssertionError("invalid date unexpectedly accepted")
    except ValueError:
        pass
    try:
        eg.source_clock_hour("19700101", 24)
        raise AssertionError("hour 24 unexpectedly accepted")
    except ValueError:
        pass
    checks.append("ts key uses validated naive source-clock epoch-hours; no UTC/KST localization")

    good = {"rfid_id": "R1", "ts": eg.source_clock_hour("20260101", 4)}
    eg.check_key("R1", "20260101", 4, good)
    try:
        eg.check_key("R2", "20260101", 4, good)
        raise AssertionError("raw RFID mismatch unexpectedly accepted")
    except ValueError:
        pass
    try:
        eg.check_key("R1", "20260101", 5, good)
        raise AssertionError("raw timestamp mismatch unexpectedly accepted")
    except ValueError:
        pass
    checks.append("raw RFID or source-hour mismatch raises and blocks row validation")

    # Original CSV parser contract: row[3] only; quoted commas remain inside geom.
    sample = 'part_dt,rfid_id,rfid_time,geom,fishing_code,extra\n20260101,R1,4,"MULTILINESTRING ((127 37, 127.001 37), (128 38, 128.001 38))",G,"ignore,this"\n'
    reader = csv.reader(io.StringIO(sample, newline=""))
    header = next(reader)
    row = next(reader)
    assert header[:5] == eg.RAW_HEADER_PREFIX
    parsed = eg.parse_multilinestring(row[3])
    assert len(parsed) == 2 and len(parsed[0]) == 2 and len(parsed[1]) == 2
    checks.append("CSV reader preserves quoted row[3] geometry; unrelated extra columns are ignored")

    # Stable nullable Arrow schema and exact-once writer: a null first shape must
    # not force null physical type or be emitted twice before the second row.
    def arrow_row(order: int, informative: bool) -> dict:
        return {"rfid_id": "A" if order == 0 else "B", "ts": 10 + order, "source_ordinal": order,
                "len_m": 150.0, "bbox_m": 120.0, "cen_lon": 127.0, "cen_lat": 37.0, "score": 0.5,
                "canonical_order": order, "source_month": 1, "row_index": order, "primary_gear": "G",
                "n_parts": 1 if informative else 0, "n_informative_parts": 1 if informative else 0,
                "chosen_part_index": 0 if informative else None, "chosen_n_points": 3 if informative else None,
                "chosen_n_unique": 3 if informative else None, "chosen_path_m": 100.0 if informative else None,
                "chosen_endpoint_m": 80.0 if informative else None, "shape_dl": 0.8 if informative else None,
                "geometry_status": "informative" if informative else "uninformative",
                "geometry_reason": "fixture", "raw_record_sha256": None, "cache_n_coords": 3,
                "cache_len_m": 150.0, "cache_bbox_m": 120.0, "cache_cen_lon": 127.0, "cache_cen_lat": 37.0}
    with tempfile.TemporaryDirectory(prefix="r8_geometry_schema_") as td:
        root = Path(td)
        one = root / "one.parquet"
        n_one = eg.write_geometry_rows([arrow_row(0, False)], one, pa, pq, batch_size=1)
        one_read = pq.read_table(one, columns=["canonical_order"])["canonical_order"].to_pylist()
        assert n_one == 1 and one_read == [0]
        two = root / "null_first_valid_second.parquet"
        n_two = eg.write_geometry_rows([arrow_row(0, False), arrow_row(1, True)], two, pa, pq, batch_size=1)
        two_table = pq.read_table(two, columns=["canonical_order", "shape_dl"])
        assert n_two == 2 and two_table.num_rows == 2
        assert two_table["canonical_order"].to_pylist() == [0, 1]
        assert two_table["shape_dl"].to_pylist() == [None, 0.8]
    checks.append("explicit nullable Arrow schema writes null-first/valid-second exactly once and one-row output once")

    result = {"status": "passed", "requested_model": "GPT-6 Luna", "requested_effort": "xhigh",
              "checks": checks, "check_count": len(checks),
              "ram_preflight": preflight,
              "scope": "synthetic in-memory records and temporary miniature parquet only; no production CSV/parquet, labels, extraction or scoring read"}
    out = Path(__file__).resolve().parent / "extract_checks.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
