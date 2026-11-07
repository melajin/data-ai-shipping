"""Small synthetic API checks for the frozen shape-only B0/S/G rule builder."""
from __future__ import annotations

import json
import datetime as dt
import os
from pathlib import Path

import psutil


def ram_preflight() -> dict:
    vm = psutil.virtual_memory()
    current = os.getpid()
    jobs = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] != current and "python" in (proc.info["name"] or "").lower():
                jobs.append({"pid": proc.info["pid"], "name": proc.info["name"],
                             "cmdline": " ".join(proc.info["cmdline"] or [])[:200]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    available = vm.available / 1048576
    result = {"checked_at": dt.datetime.now().astimezone().isoformat(), "available_mib": round(available, 2),
              "expected_extra_mib": 768, "reserve_mib": 640, "active_python_jobs": jobs,
              "allowed": available >= 1408,
              "estimate_basis": "synthetic 183-row pandas fixture; conservative project 768 MiB implementation ceiling plus 640 MiB reserve"}
    if not result["allowed"]:
        raise MemoryError(f"synthetic rule fixture deferred for low RAM: {result}")
    return result


RAM_PREFLIGHT = ram_preflight()

import pandas as pd

from shape_rules import build_shape_rules


def row(rid: str, ts: int, ordinal: int, shape: float, score: float = 0.5,
        length: float = 200.0, bbox: float = 150.0, status: str = "informative",
        unique: int = 3, informative_parts: int = 1) -> dict:
    return {"rfid_id": rid, "ts": ts, "source_ordinal": ordinal, "len_m": length,
            "bbox_m": bbox, "score": score, "n_parts": 1 if status == "informative" else 0,
            "n_informative_parts": informative_parts, "chosen_part_index": 0,
            "chosen_n_points": unique, "chosen_n_unique": unique,
            "chosen_path_m": 100.0 if status == "informative" else None,
            "chosen_endpoint_m": 100.0 if status == "informative" else None,
            "shape_dl": shape if status == "informative" else None,
            "geometry_status": status, "geometry_reason": "fixture"}


def main() -> dict:
    checks = []
    rows = []
    # Candidate V has two same-rarity shape rows plus a later base-only row.
    # Descending baseline chooses the highest legacy score; S resolves its self tie
    # by descending legacy, while G's peer rarity wins only on the B/C self tie.
    ordinal = 0
    for i in range(8):
        rows.append(row("V", i, ordinal, 0.5, score=0.1)); ordinal += 1
    for i in range(24, 32):
        rows.append(row("V", i, ordinal, 0.5, score=0.1)); ordinal += 1
    for i in range(48, 56):
        rows.append(row("V", i, ordinal, 0.5, score=0.1)); ordinal += 1
    rows.append(row("V", 720, ordinal, 0.5, score=0.5)); ordinal += 1
    rows.append(row("V", 721, ordinal, 0.5, score=0.4)); ordinal += 1
    rows.append(row("V", 722, ordinal, 0.5, score=0.9, status="uninformative", informative_parts=0)); ordinal += 1  # later s0-only baseline top

    # Six same-code peers have qualifying prior histories. Three receive a 720-hour
    # query-hour observation; the other three have no current row, yet remain peers
    # at the same t because eligibility uses history only.
    for p in range(1, 7):
        rid = f"P{p}"
        peer_times = list(range(8)) + list(range(24, 32)) + list(range(48, 56))
        for j, t in enumerate(peer_times):
            rows.append(row(rid, t, ordinal, 0.1 if j < 12 else 0.9)); ordinal += 1
        rows.append(row(rid, 100, ordinal, 0.5)); ordinal += 1
        if p <= 3:
            rows.append(row(rid, 720, ordinal, 0.9)); ordinal += 1

    # A small, invalid and uninformed set exercises branch statuses and hierarchy.
    rows.append(row("BAD", 720, ordinal, 0.5, score=float("nan"))); ordinal += 1
    rows.append(row("SMALL", 720, ordinal, 0.5, length=20.0, bbox=30.0)); ordinal += 1
    rows.append(row("NO_SHAPE", 720, ordinal, 0.5, status="uninformative", informative_parts=0)); ordinal += 1
    frame = pd.DataFrame(rows)
    registry_rows = [{"rfid_id": "V", "primary_gear": "G", "is_single_code": True}]
    registry_rows += [{"rfid_id": f"P{p}", "primary_gear": "G", "is_single_code": True} for p in range(1, 7)]
    registry_rows += [{"rfid_id": "BAD", "primary_gear": "G", "is_single_code": True},
                      {"rfid_id": "SMALL", "primary_gear": "G", "is_single_code": True},
                      {"rfid_id": "NO_SHAPE", "primary_gear": "G", "is_single_code": True}]
    registry = pd.DataFrame(registry_rows)
    out = build_shape_rules(frame, registry)
    ledger = out["ledger"]

    v = ledger[ledger.rfid_id == "V"].set_index("ts")
    assert int(v.loc[720, "self_ref_n"]) == 24 and int(v.loc[720, "self_ref_dates"]) == 3
    assert bool(v.loc[720, "s3_ok"]), "t-720 rows must be included"
    checks.append("strict history window includes exact t-720 row and meets 24-row/3-date boundary")
    assert int(v.loc[721, "self_ref_n"]) == 24 and int(v.loc[721, "self_ref_dates"]) == 4
    checks.append("current-hour row is excluded at t and enters history at t+1 while the exact 720-hour boundary rolls out")

    assert int(v.loc[720, "peer_eligible_n"]) == 6
    assert int(v.loc[721, "peer_eligible_n"]) == 6
    expected_peer_mean = (3 * (1 - 2 * 0.46) + 3 * (1 - 2 * (11.5 / 24))) / 6
    assert abs(float(v.loc[720, "peer_rarity_mean"])) < 1e-10
    assert abs(float(v.loc[721, "peer_rarity_mean"]) - expected_peer_mean) < 1e-10
    checks.append("six same-code histories qualify at common t, including peers without a current row; peer rarity is equally vessel-weighted")

    preds = out["predictions"]
    def winner(method: str) -> int:
        p = preds[(preds.rfid_id == "V") & (preds.method == method) & (preds["rank"] == 1)]
        return int(p.iloc[0].ordinal)
    winner_ord = {m: winner(m) for m in ("B0", "S", "G")}
    v_b_ord = int(ledger[(ledger.rfid_id == "V") & (ledger.ts == 720)].iloc[0].source_ordinal)
    v_c_ord = int(ledger[(ledger.rfid_id == "V") & (ledger.ts == 721)].iloc[0].source_ordinal)
    v_base_ord = int(ledger[(ledger.rfid_id == "V") & (ledger.ts == 722)].iloc[0].source_ordinal)
    assert winner_ord == {"B0": v_base_ord, "S": v_b_ord, "G": v_c_ord}, winner_ord
    assert float(ledger.loc[ledger.source_ordinal == v_base_ord, "score"].iloc[0]) == 0.9
    checks.append("synthetic fixture yields distinct B0/S/G winners: later highest legacy baseline, S legacy tie, and G peer-only self tie-break")

    vm = out["pool_manifest"].query("rfid_id == 'V'").set_index("method")
    assert vm.loc["B0", "cap"] == vm.loc["S", "cap"] == vm.loc["G", "cap"] == 2
    assert vm.loc["S", "pool_stage"] == "s3" and vm.loc["G", "pool_stage"] == "s4"
    checks.append("all methods share cap=min(4,G actual pool n), with exact B0/S/G masks")

    # Fallback semantics are exercised on a one-row vessel with no history.
    fallback_frame = pd.DataFrame([
        row("F", 10, 1, 0.5, score=0.1, status="uninformative", informative_parts=0),
        row("F", 20, 2, 0.5, score=0.5, status="uninformative", informative_parts=0),
        row("F", 30, 3, 0.5, score=0.9, status="uninformative", informative_parts=0),
    ])
    fallback_reg = pd.DataFrame([{"rfid_id": "F", "primary_gear": "solo", "is_single_code": True}])
    fallback = build_shape_rules(fallback_frame, fallback_reg)
    fm = fallback["pool_manifest"].set_index("method")
    assert fm.loc["S", "pool_stage"] == fm.loc["G", "pool_stage"] == "s0"
    assert fm.loc["S", "fallback_reason"] == "s3_empty_use_s0"
    assert fm.loc["G", "fallback_reason"] == "s4_empty_use_s0"
    assert fm["cap"].nunique() == 1 and fm["cap"].iloc[0] == 3
    fallback_preds = fallback["predictions"]
    for method in ("B0", "S", "G"):
        scores = fallback_preds[(fallback_preds.rfid_id == "F") & (fallback_preds.method == method)].sort_values("rank").legacy_score.tolist()
        assert scores == [0.9, 0.5, 0.1], (method, scores)
    checks.append("empty S/G uses documented fallback; B0/S/G legacy-only paths rank descending as [.9,.5,.1]")

    status = ledger.set_index("rfid_id")
    assert status.loc["BAD", "s0_status"] == "defer" and not status.loc["BAD", "s1_ok"]
    assert status.loc["SMALL", "s0_status"] == "keep" and status.loc["SMALL", "s1_status"] == "reject"
    assert status.loc["SMALL", "s2_status"] == "not_applicable"
    assert status.loc["NO_SHAPE", "s2_status"] == "defer"
    checks.append("invalid base defers, observed-small rejects, and missing geometry defers without violating mask hierarchy")

    # Appending a future row cannot affect earlier row scores or stage decisions.
    base = build_shape_rules(frame, registry)["ledger"].set_index(["rfid_id", "ts"])
    future = pd.concat([frame, pd.DataFrame([row("V", 2000, ordinal + 5, 0.99, score=0.9)])], ignore_index=True)
    extended = build_shape_rules(future, registry)["ledger"].set_index(["rfid_id", "ts"])
    cols = ["self_ref_n", "self_ref_dates", "self_cdf", "self_rarity", "peer_eligible_n", "peer_rarity_mean", "s0_ok", "s1_ok", "s2_ok", "s3_ok", "s4_ok"]
    for key in base.index:
        for col in cols:
            a, b = base.loc[key, col], extended.loc[key, col]
            if pd.isna(a):
                assert pd.isna(b), (key, col, a, b)
            else:
                assert a == b, (key, col, a, b)
    checks.append("appending a future row leaves every existing score and stage unchanged")

    # Unique-hour and integer source-clock guards.
    try:
        build_shape_rules(pd.concat([fallback_frame, fallback_frame]), fallback_reg)
        raise AssertionError("duplicate RFID/hour unexpectedly accepted")
    except ValueError:
        pass
    fractional = fallback_frame.copy(); fractional["ts"] = fractional["ts"].astype(float) + 0.5
    try:
        build_shape_rules(fractional, fallback_reg)
        raise AssertionError("fractional ts unexpectedly accepted")
    except ValueError:
        pass
    checks.append("duplicate RFID/hour and fractional source-clock hours are rejected")

    # Save a compact ranking and rule receipt.
    result = {"status": "passed", "requested_model": "GPT-6 Luna", "requested_effort": "xhigh",
              "checks": checks, "check_count": len(checks), "synthetic_rows": len(frame),
              "distinct_top1_ordinals": winner_ord, "peer_mean_at_t721": float(v.loc[721, "peer_rarity_mean"]),
              "diagnostics_peer_ties": out["diagnostics"]["peer_tie_activation_within_same_G_s4_pools"],
              "ram_preflight": RAM_PREFLIGHT,
              "scope": "synthetic in-memory fixture only; no production data, labels, extraction, scoring evaluation or model training"}
    Path(__file__).resolve().parent.joinpath("shape_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False, default=str))
