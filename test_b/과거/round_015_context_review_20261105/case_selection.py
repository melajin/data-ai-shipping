#!/usr/bin/env python3
"""Create the Round015 T0 case register from the two approved metadata CSVs."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


BASE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DEV_PATH = BASE / "testB/round_008_linkage_audit_20261105/devset_positives.csv"
VOY_PATH = BASE / "testB/round_012_20261105/g2v2_voyages.csv"
REGISTER = OUT / "case_register.csv"
RECEIPT = OUT / "case_selection_receipt.json"

DEV_COLS = [
    "acc_id", "rfid_id", "tier", "conflict", "row_ts", "source_month",
    "source_row_index", "acc_ts", "\uBC1C\uC0DD\uC77C\uC2DC",
    "\uBC1C\uC0DD\uC720\uD615", "\uC5B4\uC5C5\uBA74\uD5C8", "\uD1A4\uC218",
    "\uC0AC\uACE0\uC120\uBC15\uC218", "dt_h", "dist_km",
]
VOY_COLS = ["rfid_id", "voy", "n_voyages", "t_start", "t_end"]
SLOT_RULES = {
    "A": "conflict=False, tier<=1, valid consistent n_voyages>=3; up to 3 distinct RFID",
    "B": "first unused RFID with conflict=True; n_voyages not required",
    "C": "first unused RFID with conflict=False and tier>=2; n_voyages not required",
    "D": "first unused RFID with valid consistent n_voyages<3",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integer(value: Any) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def source_file_record(path: Path, whitelist: list[str], rows: int) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.relative_to(BASE)).replace("\\", "/"),
        "bytes": stat.st_size,
        "mtime_local": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256(path),
        "rows_parsed": rows,
        "whitelisted_columns_parsed": whitelist,
    }


def main() -> None:
    # Selection-column parsing is constrained at the CSV parser, not after loading.
    dev = pd.read_csv(DEV_PATH, usecols=DEV_COLS, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    voyages = pd.read_csv(VOY_PATH, usecols=VOY_COLS, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    dev = dev.reset_index(drop=True)
    voyages = voyages.reset_index(drop=True)
    dev["_input_order"] = range(len(dev))

    # Build one validated count value per RFID; never join voyage rows to incidents.
    by_rfid: dict[str, dict[str, Any]] = {}
    n_count_diag: dict[str, Any] = {}
    voyage_groups: dict[str, pd.DataFrame] = {}
    for raw_rfid, group in voyages.groupby("rfid_id", sort=False, dropna=False):
        rfid = str(raw_rfid)
        voyage_groups[rfid] = group.copy()
        raw_counts = [str(v).strip() for v in group["n_voyages"].tolist()]
        parsed = [integer(v) for v in raw_counts]
        nonblank = {v for v in parsed if v is not None}
        missing_count_rows = sum(not v for v in raw_counts)
        invalid_count_rows = sum(bool(v) and integer(v) is None for v in raw_counts)
        consistent = len(nonblank) == 1 and missing_count_rows == 0 and invalid_count_rows == 0
        count_value = next(iter(nonblank)) if consistent else None
        if count_value is not None and count_value < 0:
            consistent = False
            count_value = None
        by_rfid[rfid] = {"n_voyages": count_value, "n_voyages_valid": consistent}
        n_count_diag[rfid] = {
            "rows": len(group),
            "distinct_raw_values": sorted(set(raw_counts)),
            "missing_rows": missing_count_rows,
            "invalid_rows": invalid_count_rows,
            "consistent_valid_count": count_value,
            "status": "valid" if consistent else "invalid_inconsistent_or_missing",
        }

    # Identify incident IDs whose rows disagree on any permitted field. Exact duplicates
    # are retained as diagnostics but equivalent rows do not create a second case.
    selection_identity_cols = [c for c in DEV_COLS]
    acc_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dev.to_dict(orient="records"):
        acc_rows[str(row["acc_id"])].append(row)
    duplicate_acc_ids = {k: v for k, v in acc_rows.items() if len(v) > 1}
    conflicting_acc_ids = {
        acc_id for acc_id, rows in duplicate_acc_ids.items()
        if len({tuple(str(row[c]) for c in selection_identity_cols) for row in rows}) > 1
    }
    duplicate_source_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dev.to_dict(orient="records"):
        month, index = str(row["source_month"]).strip(), str(row["source_row_index"]).strip()
        if month and index:
            duplicate_source_groups[f"{month}:{index}"].append(row)
    duplicate_source_refs = {
        k: v for k, v in duplicate_source_groups.items() if len(v) > 1
    }
    conflicting_source_refs = {
        ref for ref, rows in duplicate_source_refs.items()
        if len({(str(r["rfid_id"]), str(r["row_ts"])) for r in rows}) > 1
    }

    # Slot filters are applied before sorting/scanning. Do not globally reduce by RFID.
    chosen: list[dict[str, Any]] = []
    used_rfids: set[str] = set()
    slot_results: dict[str, dict[str, Any]] = {}

    def row_selection_status(row: dict[str, Any]) -> tuple[int | None, bool | None, str | None, str | None]:
        tier = integer(row["tier"])
        conflict_text = str(row["conflict"]).strip().lower()
        conflict = True if conflict_text == "true" else False if conflict_text == "false" else None
        acc_id = str(row["acc_id"]).strip()
        rfid = str(row["rfid_id"]).strip()
        return tier, conflict, acc_id or None, rfid or None

    def select_slot(slot: str, limit: int, eligible) -> None:
        candidates: list[tuple[int, dict[str, Any]]] = []
        for row in dev.to_dict(orient="records"):
            tier, conflict, acc_id, rfid = row_selection_status(row)
            acc_num = integer(acc_id or "")
            if not acc_id or not rfid or acc_num is None or tier is None or conflict is None:
                continue
            metadata = by_rfid.get(rfid, {"n_voyages": None, "n_voyages_valid": False})
            if acc_id in conflicting_acc_ids or f"{str(row['source_month']).strip()}:{str(row['source_row_index']).strip()}" in conflicting_source_refs:
                continue
            if eligible(tier, conflict, metadata):
                candidates.append((acc_num, row))
        candidates.sort(key=lambda pair: (pair[0], pair[1]["_input_order"]))
        selected_for_slot: list[dict[str, Any]] = []
        seen_in_slot: set[str] = set()
        for _acc_num, row in candidates:
            rfid = str(row["rfid_id"]).strip()
            if rfid in used_rfids or rfid in seen_in_slot:
                continue
            selected_for_slot.append(row)
            seen_in_slot.add(rfid)
            used_rfids.add(rfid)
            if len(selected_for_slot) >= limit:
                break
        for row in selected_for_slot:
            chosen.append({"slot": slot, "row": row})
        slot_results[slot] = {
            "rule": SLOT_RULES[slot],
            "selected_acc_ids": [str(r["acc_id"]) for r in selected_for_slot],
            "selected_rfids": [str(r["rfid_id"]) for r in selected_for_slot],
            "selected_count": len(selected_for_slot),
            "empty_reason": None if selected_for_slot else "no eligible unused RFID under fixed slot filter and ascending acc_id scan",
        }

    select_slot("A", 3, lambda tier, conflict, m: not conflict and tier <= 1 and m["n_voyages_valid"] and m["n_voyages"] is not None and m["n_voyages"] >= 3)
    select_slot("B", 1, lambda tier, conflict, m: conflict)
    select_slot("C", 1, lambda tier, conflict, m: not conflict and tier >= 2)
    select_slot("D", 1, lambda tier, conflict, m: m["n_voyages_valid"] and m["n_voyages"] is not None and m["n_voyages"] < 3)

    def event_key(row: dict[str, Any]) -> int | None:
        return integer(row["row_ts"])

    def compare_windows(rfid: str, h: int | None) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        group = voyage_groups.get(rfid)
        if h is None:
            return [], "unavailable_invalid_anchor_key", {"candidate_rows": 0, "invalid_rows": 0, "duplicate_voy_ids": [], "conflicting_voy_ids": []}
        if group is None or group.empty:
            return [], "unavailable_no_voyage_rows", {"candidate_rows": 0, "invalid_rows": 0, "duplicate_voy_ids": [], "conflicting_voy_ids": []}
        parsed_rows: list[dict[str, Any]] = []
        invalid_rows = 0
        raw_rows = group.to_dict(orient="records")
        per_voy: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for r in raw_rows:
            voy = integer(r["voy"])
            start = integer(r["t_start"])
            end = integer(r["t_end"])
            count = integer(r["n_voyages"])
            if voy is None or start is None or end is None or end < start or count is None:
                invalid_rows += 1
                continue
            per_voy[str(voy)].append((count, start, end))
            parsed_rows.append({"voy": voy, "t_start": start, "t_end": end, "n_voyages": count})
        conflicting_voy_ids = sorted(v for v, vals in per_voy.items() if len(set(vals)) > 1)
        duplicate_voy_ids = sorted(v for v, vals in per_voy.items() if len(vals) > 1)
        if conflicting_voy_ids:
            return [], "unavailable_conflicting_voyage_rows", {
                "candidate_rows": len(raw_rows), "invalid_rows": invalid_rows,
                "duplicate_voy_ids": duplicate_voy_ids, "conflicting_voy_ids": conflicting_voy_ids,
            }
        # Equivalent duplicate rows represent one identical analysis segment; report them,
        # then use one metadata row so a duplicate cannot manufacture extra windows.
        unique_by_voy: dict[int, dict[str, int]] = {}
        for item in parsed_rows:
            unique_by_voy.setdefault(item["voy"], item)
        qualifying = [r for r in unique_by_voy.values() if r["t_end"] <= h - 37]
        qualifying.sort(key=lambda r: (-r["t_end"], r["t_start"], r["voy"]))
        selected_windows: list[dict[str, Any]] = []
        for r in qualifying:
            window = {"voy": r["voy"], "start": r["t_end"] - 24, "end": r["t_end"]}
            if any(window["start"] <= prev["end"] and window["end"] >= prev["start"] for prev in selected_windows):
                continue
            selected_windows.append(window)
            if len(selected_windows) == 2:
                break
        if invalid_rows:
            status = "available_with_invalid_voyage_rows_skipped"
        elif not selected_windows:
            status = "unavailable_no_nonoverlapping_eligible_window"
        else:
            status = "available" if len(selected_windows) == 2 else "available_one_window_only"
        return selected_windows, status, {
            "candidate_rows": len(raw_rows), "invalid_rows": invalid_rows,
            "duplicate_voy_ids": duplicate_voy_ids, "conflicting_voy_ids": conflicting_voy_ids,
            "eligible_rows": len(qualifying),
        }

    register_rows: list[dict[str, Any]] = []
    comparison_diagnostics: dict[str, Any] = {}
    all_dev_rows = dev.to_dict(orient="records")
    for entry in chosen:
        slot, row = entry["slot"], entry["row"]
        acc_id, rfid = str(row["acc_id"]), str(row["rfid_id"])
        h = event_key(row)
        tier = integer(row["tier"])
        conflict = str(row["conflict"]).strip().lower()
        count_meta = by_rfid.get(rfid, {"n_voyages": None, "n_voyages_valid": False})
        event_rows = [r for r in all_dev_rows if str(r["rfid_id"]) == rfid and str(r["acc_id"]) != acc_id]
        other_ids = sorted({str(r["acc_id"]) for r in event_rows if str(r["acc_id"]).strip()}, key=lambda x: (integer(x) is None, integer(x) or 0, x))
        windows, comp_status, comp_diag = compare_windows(rfid, h)
        in_window_ids: list[list[str]] = []
        for window in windows:
            ids = sorted({str(r["acc_id"]) for r in event_rows if (event_key(r) is not None and window["start"] <= event_key(r) <= window["end"])}, key=lambda x: (integer(x) is None, integer(x) or 0, x))
            in_window_ids.append(ids)
        comparison_diagnostics[acc_id] = comp_diag
        regs: dict[str, Any] = {
            "slot": slot,
            "selection_rule": SLOT_RULES[slot],
            "acc_id": acc_id,
            "rfid_id": rfid,
            "tier": "" if tier is None else tier,
            "conflict": conflict,
            "n_voyages": count_meta["n_voyages"] if count_meta["n_voyages_valid"] else "",
            "n_voyages_status": "valid" if count_meta["n_voyages_valid"] else "invalid_inconsistent_or_missing",
            "anchor_row_ts_H": "" if h is None else h,
            "anchor_status": "valid_integer_key" if h is not None else "invalid_or_missing_key",
            "anchor_source_month": row["source_month"],
            "anchor_source_row_index": row["source_row_index"],
            "target_window_start_H_minus_12": "" if h is None else h - 12,
            "target_window_end_H_plus_12": "" if h is None else h + 12,
            "target_window_status": "available_25_hour_keys" if h is not None else "unavailable_invalid_anchor_key",
            "comparison_status": comp_status,
            "comparison_1_voy": windows[0]["voy"] if len(windows) > 0 else "",
            "comparison_1_start": windows[0]["start"] if len(windows) > 0 else "",
            "comparison_1_end": windows[0]["end"] if len(windows) > 0 else "",
            "comparison_1_other_event_ids": ";".join(in_window_ids[0]) if len(in_window_ids) > 0 else "",
            "comparison_2_voy": windows[1]["voy"] if len(windows) > 1 else "",
            "comparison_2_start": windows[1]["start"] if len(windows) > 1 else "",
            "comparison_2_end": windows[1]["end"] if len(windows) > 1 else "",
            "comparison_2_other_event_ids": ";".join(in_window_ids[1]) if len(in_window_ids) > 1 else "",
            "other_event_ids_for_rfid": ";".join(other_ids),
            "overlay_acc_ts": row["acc_ts"],
            "overlay_\uBC1C\uC0DD\uC77C\uC2DC": row["\uBC1C\uC0DD\uC77C\uC2DC"],
            "overlay_\uBC1C\uC0DD\uC720\uD615": row["\uBC1C\uC0DD\uC720\uD615"],
            "overlay_\uC5B4\uC5C5\uBA74\uD5C8": row["\uC5B4\uC5C5\uBA74\uD5C8"],
            "overlay_\uD1A4\uC218": row["\uD1A4\uC218"],
            "overlay_\uC0AC\uACE0\uC120\uBC15\uC218": row["\uC0AC\uACE0\uC120\uBC15\uC218"],
            "overlay_dt_h": row["dt_h"],
            "overlay_dist_km": row["dist_km"],
        }
        register_rows.append(regs)

    fieldnames = list(register_rows[0].keys()) if register_rows else [
        "slot", "selection_rule", "acc_id", "rfid_id", "tier", "conflict", "n_voyages", "n_voyages_status",
        "anchor_row_ts_H", "anchor_status", "anchor_source_month", "anchor_source_row_index",
        "target_window_start_H_minus_12", "target_window_end_H_plus_12", "target_window_status", "comparison_status",
        "comparison_1_voy", "comparison_1_start", "comparison_1_end", "comparison_1_other_event_ids",
        "comparison_2_voy", "comparison_2_start", "comparison_2_end", "comparison_2_other_event_ids",
        "other_event_ids_for_rfid", "overlay_acc_ts", "overlay_\uBC1C\uC0DD\uC77C\uC2DC", "overlay_\uBC1C\uC0DD\uC720\uD615",
        "overlay_\uC5B4\uC5C5\uBA74\uD5C8", "overlay_\uD1A4\uC218", "overlay_\uC0AC\uACE0\uC120\uBC15\uC218", "overlay_dt_h", "overlay_dist_km",
    ]
    with REGISTER.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(register_rows)

    missing_selection_fields = {
        c: int((dev[c].astype(str).str.strip() == "").sum())
        for c in ["acc_id", "rfid_id", "tier", "conflict"]
    }
    missing_anchor_fields = {
        c: int((dev[c].astype(str).str.strip() == "").sum())
        for c in ["row_ts", "source_month", "source_row_index"]
    }
    receipt = {
        "round": "Round015 T0 fixed case selection",
        "created_at_local": datetime.now().astimezone().isoformat(),
        "execution": {
            "requested_model": "GPT-6 Luna",
            "requested_effort": "xhigh",
            "actual_model_effort_evidence": "This worker was dispatched by the coordinator with requested model GPT-6 Luna and effort xhigh; no independent runtime model attestation is available in this environment.",
            "scope": "T0 metadata-only selection; no raw extraction",
            "selection_implementation": str(Path(__file__).relative_to(BASE)).replace("\\", "/"),
            "selection_implementation_sha256": sha256(Path(__file__).resolve()),
        },
        "inputs": {
            "devset": source_file_record(DEV_PATH, DEV_COLS, len(dev)),
            "voyages": source_file_record(VOY_PATH, VOY_COLS, len(voyages)),
        },
        "slot_rules": SLOT_RULES,
        "slots": slot_results,
        "diagnostics": {
            "devset_rows": len(dev),
            "voyage_rows": len(voyages),
            "unique_devset_acc_ids": int(dev["acc_id"].nunique(dropna=False)),
            "unique_devset_rfids": int(dev["rfid_id"].nunique(dropna=False)),
            "missing_selection_fields": missing_selection_fields,
            "missing_anchor_fields": missing_anchor_fields,
            "duplicate_acc_id_row_counts": {k: len(v) for k, v in duplicate_acc_ids.items()},
            "conflicting_acc_ids_excluded_from_slot_scans": sorted(conflicting_acc_ids, key=lambda x: (integer(x) is None, integer(x) or 0, x)),
            "duplicate_source_row_refs": {k: len(v) for k, v in duplicate_source_refs.items()},
            "conflicting_source_row_refs_excluded_from_slot_scans": sorted(conflicting_source_refs),
            "rfids_with_missing_or_inconsistent_n_voyages": sorted(r for r, v in by_rfid.items() if not v["n_voyages_valid"]),
            "n_voyages_by_rfid_diagnostics": n_count_diag,
            "comparison_window_diagnostics_by_acc_id": comparison_diagnostics,
            "selected_anchor_keys_missing_or_invalid": [r["acc_id"] for r in register_rows if not r["anchor_row_ts_H"]],
        },
        "outputs": {
            "case_register": {
                "path": str(REGISTER.relative_to(BASE)).replace("\\", "/"),
                "bytes": REGISTER.stat().st_size,
                "sha256": sha256(REGISTER),
                "rows_excluding_header": len(register_rows),
            }
        },
        "limitations": [
            "RFID denotes a candidate data-group key, not confirmed vessel identity or accident attribution.",
            "Voyage rows are six-hour-gap-derived analysis segments, not proof of actual departures or arrivals.",
            "The target is the stored-key interval [H-12,H+12]; incident timestamps are overlay-only and did not affect selection or windows.",
            "Comparison windows are unlabeled; absence of an incident record does not establish normal behavior.",
            "The deterministic cases are a convenience sample and support no population representativeness or performance estimate.",
            "Source-row lineage was recorded from Round008 metadata but not traced against raw monthly files; raw extraction remains NO-GO pending separate T1 ticket, independent review, and fresh G0-G3 gates.",
            "No existing SHA baseline evidence was opened or compared in this T0-only run; hashes below identify the exact input bytes processed.",
            "No score, state, coordinate, geometry, raw monthly CSV, parquet, XLSX, 2025 Test B, external data, model training, or candidate output was read.",
        ],
    }
    RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
