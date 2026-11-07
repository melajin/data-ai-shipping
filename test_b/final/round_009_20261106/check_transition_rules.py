"""Synthetic-only checks for frozen Round9 transition rules and code binding."""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import datetime as dt
import hashlib
import json
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
                             "cmdline": " ".join(proc.info["cmdline"] or [])[:250]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    available = vm.available / 1048576
    # Reserve one Gemini synthetic job even if it is not a local Python
    # process, plus 512 MiB for each other visible Python job.
    gemini_reserve = 512
    concurrent = 512 * len(jobs)
    result = {"checked_at": dt.datetime.now().astimezone().isoformat(), "available_mib": round(available, 2),
              "luna_fixture_extra_mib": 768, "gemini_synthetic_reserve_mib": gemini_reserve,
              "overlap_job_reserve_mib": concurrent,
              "other_python_jobs": jobs, "reserve_mib": 640,
              "required_available_mib": 768 + gemini_reserve + concurrent + 640,
              "allowed": available >= 768 + gemini_reserve + concurrent + 640,
              "estimate_basis": "small synthetic fixtures only; 768 MiB Luna plus fixed 512 MiB Gemini reserve plus 512 MiB per other active Python job plus 640 MiB reserve"}
    if not result["allowed"]:
        raise MemoryError(f"synthetic checks deferred for low RAM: {result}")
    return result


RAM_PREFLIGHT = ram_preflight()

import pandas as pd

from transition_rules import build_transition_rules

ROOT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def make_fixture() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    rows: list[dict] = []
    ordinal = 0

    def add(rid: str, t: int, length: float, bbox: float, score: float = 0.1) -> int:
        nonlocal ordinal
        ix = ordinal
        rows.append({"rfid_id": rid, "ts": int(t), "source_ordinal": ordinal,
                     "len_m": float(length), "bbox_m": float(bbox), "cen_lon": 127.0,
                     "cen_lat": 37.0, "score": score})
        ordinal += 1
        return ix

    def chunks(rid: str, n: int, pattern_n: int, *, endpoint_nan: bool = False,
               date_count: int = 3) -> list[int]:
        """Create n contiguous valid triples across the requested end dates."""
        day_bases = (0, 120, 240, 360)[:date_count]
        sizes = [n // date_count + int(i < n % date_count) for i in range(date_count)]
        made = []
        pattern_days = set(range(date_count - pattern_n, date_count))
        for day_i, (day_base, size) in enumerate(zip(day_bases, sizes)):
            row_n = size + 2
            has_pattern = day_i in pattern_days
            for j in range(row_n):
                is_small = has_pattern and j < 2
                is_transition_end = has_pattern and j == 2
                score = float("nan") if endpoint_nan and has_pattern and j == 2 else 0.1
                idx = add(rid, day_base + j, 50 if is_small else 200,
                          50 if is_small else 150, score)
                if is_transition_end:
                    made.append(idx)
        return made

    def current_pattern(rid: str, t: int, score: float = 0.5, *, prev2_score: float = 0.1) -> tuple[int, int, int]:
        i2 = add(rid, t - 2, 50, 50, prev2_score)
        i1 = add(rid, t - 1, 50, 50, 0.1)
        it = add(rid, t, 200, 150, score)
        return i2, i1, it

    # Three distinct winners. W's historical pattern endpoint has NaN legacy
    # score yet remains a valid raw/reference triple; row t=718 also has NaN
    # score but valid geometry and must support the t=720 transition.
    endpoint_indices = chunks("W", 36, 1, endpoint_nan=True, date_count=4)
    w720 = current_pattern("W", 720, 0.5, prev2_score=float("nan"))[2]
    w730 = current_pattern("W", 730, 0.9)[2]
    w740 = current_pattern("W", 740, 0.8)[2]
    w750 = add("W", 750, 300, 200, 0.99)  # s0-only later baseline winner

    # Five history-qualified same-gear peers, none with current-hour rows.
    # Rates: 3/48, 3/48, 1/36 (exact own-rate tie at t=720), 3/40, 3/40.
    for rid, ref_n, pat_n in (("P1", 48, 3), ("P2", 48, 3), ("P3", 36, 1),
                              ("P4", 40, 3), ("P5", 40, 3)):
        chunks(rid, ref_n, pat_n, date_count=4)

    # Strict window boundary: start at t-720 is included; an otherwise valid
    # triple ending before that is excluded; the current-ending triple is also excluded.
    add("BOUND", -10, 50, 50); add("BOUND", -9, 50, 50); add("BOUND", -8, 200, 150)
    chunks("BOUND", 24, 1)
    bound_current = current_pattern("BOUND", 720, 0.5)[2]

    # Exact 24/23 references with three end dates and a valid zero rate.
    chunks("AT24", 24, 0)
    at24 = current_pattern("AT24", 720, 0.5)[2]
    chunks("AT23", 23, 0)
    at23 = current_pattern("AT23", 720, 0.5)[2]
    chunks("RATE0", 24, 0)
    rate0_current = current_pattern("RATE0", 720, 0.5)[2]
    chunks("UNKNOWN", 24, 0)
    unknown_current = current_pattern("UNKNOWN", 720, 0.5)[2]
    chunks("SOLO", 24, 0)
    solo_current = current_pattern("SOLO", 720, 0.5)[2]

    # Exact previous-key behavior and observed non-pattern rejection.
    add("GAP", 10, 50, 50); add("GAP", 12, 50, 50); gap_current = add("GAP", 13, 200, 150)
    add("OBS", 10, 50, 50); add("OBS", 11, 200, 150); obs_current = add("OBS", 12, 200, 150)
    fb = [add("FB", 10, 200, 150, 0.1), add("FB", 20, 200, 150, 0.9), add("FB", 30, 200, 150, 0.5)]
    cap1 = add("CAP1", 100, 200, 150, 0.4)
    zero = add("ZERO", 100, 200, 150, float("nan"))

    frame = pd.DataFrame(rows)
    registry_rows = []
    for rid in ("W", "P1", "P2", "P3", "P4", "P5"):
        registry_rows.append({"rfid_id": rid, "primary_gear": "G", "is_single_code": True})
    for rid, gear, single in (("BOUND", None, False), ("AT24", "A", True), ("AT23", "A", True),
                              ("RATE0", "R0", True), ("UNKNOWN", None, False), ("SOLO", "Solo", True),
                              ("GAP", None, False), ("OBS", None, False), ("FB", None, False),
                              ("CAP1", None, False), ("ZERO", None, False), ("REGZERO", "Unused", True)):
        registry_rows.append({"rfid_id": rid, "primary_gear": gear, "is_single_code": single})
    registry = pd.DataFrame(registry_rows)
    indices = {"w720": w720, "w730": w730, "w740": w740, "w750": w750,
               "bound_current": bound_current, "at24": at24, "at23": at23,
               "rate0_current": rate0_current, "unknown_current": unknown_current,
               "solo_current": solo_current, "gap_current": gap_current,
               "obs_current": obs_current, "cap1": cap1, "zero": zero,
               "w_history_pattern_endpoint": endpoint_indices[0]}
    return frame, registry, indices


def main() -> dict:
    paths = {"transition_rules.py": ROOT / "transition_rules.py",
             "check_transition_rules.py": ROOT / "check_transition_rules.py"}
    source_hashes_before = {name: sha(path) for name, path in paths.items()}
    frame, registry, ix = make_fixture()
    result = build_transition_rules(frame, registry)
    ledger = result["ledger"]
    pred = result["predictions"]
    manifest = result["pool_manifest"]
    checks: list[str] = []

    # Preserve input order, one row per observed key; raw masks are score-independent.
    assert ledger["source_ordinal"].tolist() == frame["source_ordinal"].tolist()
    assert ledger["triplet_valid"].sum() >= ledger["pattern"].sum()
    ep = ledger.iloc[ix["w_history_pattern_endpoint"]]
    assert bool(ep.triplet_valid) and bool(ep.pattern) and not bool(ep.s0_ok)
    assert bool(ledger.iloc[ix["w720"]].pattern) and bool(ledger.iloc[ix["w720"]].s2_ok)
    checks.append("all-row raw valid-triple/pattern masks are score-independent, preserve input order, and retain NaN-score geometry")

    # Exact previous timestamps and an observed but non-pattern transition.
    gap = ledger.iloc[ix["gap_current"]]
    obs = ledger.iloc[ix["obs_current"]]
    assert not bool(gap.prev2_observed) and bool(gap.prev1_observed) and not bool(gap.triplet_valid)
    assert gap.s1_status == "defer" and gap.s2_status == "not_applicable"
    assert bool(obs.triplet_valid) and not bool(obs.pattern) and obs.s1_status == "keep" and obs.s2_status == "reject"
    checks.append("missing exact t-2 key defers despite observed t-1, while an observed valid non-pattern triple rejects at s2")

    # Previous geometry, not prior legacy score, governs the transition key.
    w = ledger[ledger.rfid_id == "W"].set_index("ts")
    assert not bool(w.loc[718, "s0_ok"]) and bool(w.loc[720, "prev2_geometry_valid"])
    assert bool(w.loc[720, "s1_ok"]) and bool(w.loc[720, "s2_ok"])
    checks.append("previous geometry with NaN score is still usable by s1 and the current pattern")

    # Window start and end boundaries plus the full valid-triple denominator.
    bound = ledger.iloc[ix["bound_current"]]
    assert int(bound.own_ref_n) == 24 and int(bound.own_pattern_n) == 1
    assert int(bound.own_ref_dates) == 3
    checks.append("triple starting exactly t-720 is included; older triple and current-end triple are excluded")

    # Reference/pattern resolution boundaries; a zero pattern rate remains valid.
    at24 = ledger.iloc[ix["at24"]]
    at23 = ledger.iloc[ix["at23"]]
    zero_rate = ledger.iloc[ix["rate0_current"]]
    assert int(at24.own_ref_n) == 24 and int(at24.own_ref_dates) == 3 and bool(at24.s3_ok)
    assert int(at23.own_ref_n) == 23 and int(at23.own_ref_dates) == 3 and not bool(at23.s3_ok)
    assert int(zero_rate.own_ref_n) == 24 and int(zero_rate.own_pattern_n) == 0
    assert float(zero_rate.own_transition_rate) == 0.0 and bool(zero_rate.s3_ok)
    checks.append("24 references/3 end dates pass, 23 defer, and zero pattern count over a valid denominator yields rate 0")

    # Five same-time peers, no peer current row, equal-vessel weighting and exact fractional tie.
    target = ledger.iloc[ix["w720"]]
    assert int(target.own_ref_n) == 36 and int(target.own_pattern_n) == 1
    assert (int(target.own_rate_num), int(target.own_rate_den)) == (1, 36)
    assert int(target.peer_eligible_n) == 5
    assert int(target.peer_rate_less_n) == 0 and int(target.peer_rate_equal_n) == 1
    assert (int(target.peer_rate_rarity_num), int(target.peer_rate_rarity_den)) == (9, 10)
    assert abs(float(target.peer_rate_rarity) - 0.9) < 1e-12 and bool(target.s4_ok)
    assert not ((ledger.rfid_id.isin(["P1", "P2", "P3", "P4", "P5"])) & ledger.ts.eq(720)).any()
    checks.append("five prior-only same-gear peers qualify at the shared query time; exact 1/36 tie and equal-vessel rarity are rationally counted")

    # Distinct top1 winners: B0 descending legacy, S descending legacy tie, G peer rarity first.
    def winner(method: str) -> int:
        row = pred[(pred.rfid_id == "W") & (pred.method == method) & pred["rank"].eq(1)].iloc[0]
        return int(row.ordinal)
    winners = {m: winner(m) for m in ("B0", "S", "G")}
    assert winners == {"B0": int(frame.iloc[ix["w750"]].source_ordinal),
                       "S": int(frame.iloc[ix["w730"]].source_ordinal),
                       "G": int(frame.iloc[ix["w720"]].source_ordinal)}, winners
    rarity_order = (float(target.peer_rate_rarity), float(w.loc[730, "peer_rate_rarity"]),
                    float(w.loc[740, "peer_rate_rarity"]))
    assert rarity_order[0] > rarity_order[1] > rarity_order[2], rarity_order
    checks.append("distinct B0/S/G winners confirm descending legacy and peer-rarity-first G ranking")

    # Fallback ordering and shared cap at 0, 1 and 3.
    fb_pred = pred[pred.rfid_id.eq("FB")]
    for method in ("B0", "S", "G"):
        scores = fb_pred[fb_pred.method.eq(method)].sort_values("rank").legacy_score.tolist()
        assert scores == [0.9, 0.5, 0.1], (method, scores)
    for rid, expected_cap in (("W", 3), ("CAP1", 1), ("ZERO", 0)):
        caps = manifest[manifest.rfid_id.eq(rid)].cap.tolist()
        assert caps == [expected_cap] * 3, (rid, caps, ledger[(ledger.rfid_id == rid) & ledger.ts.isin([720, 730, 740])][
            ["ts", "s2_ok", "s3_ok", "s4_ok", "own_ref_n", "own_ref_dates", "peer_eligible_n", "peer_rate_rarity"]].to_dict("records"))
    fbm = manifest[manifest.rfid_id.eq("FB")].set_index("method")
    assert fbm.loc["S", "pool_stage"] == fbm.loc["G", "pool_stage"] == "s0"
    assert fbm.loc["S", "fallback_reason"] == "s2_empty_use_s0"
    assert fbm.loc["G", "fallback_reason"] == "s4_empty_use_s0"
    checks.append("B0/S/G fallback order is [.9,.5,.1] and one shared cap handles G pool sizes 3, 1 and 0")

    unknown = ledger.iloc[ix["unknown_current"]]
    solo = ledger.iloc[ix["solo_current"]]
    assert bool(unknown.s3_ok) and not bool(unknown.s4_ok) and unknown.s4_reason == "unknown_or_non_single_gear"
    assert bool(solo.s3_ok) and not bool(solo.s4_ok) and int(solo.peer_eligible_n) == 0
    checks.append("unknown gear and a known singleton defer at s4")

    # Future append invariance applies to all earlier raw masks, history statistics and stage states.
    base = ledger.set_index(["rfid_id", "ts"])
    future_row = pd.DataFrame([{"rfid_id": "W", "ts": 2000, "source_ordinal": int(frame.source_ordinal.max()) + 100,
                                "len_m": 400.0, "bbox_m": 300.0, "cen_lon": 127.0, "cen_lat": 37.0, "score": 0.7}])
    extended = build_transition_rules(pd.concat([frame, future_row], ignore_index=True), registry)["ledger"].set_index(["rfid_id", "ts"])
    invariant_cols = ["triplet_valid", "pattern", "own_ref_n", "own_ref_dates", "own_pattern_n", "own_transition_rate",
                      "peer_eligible_n", "peer_rate_less_n", "peer_rate_equal_n", "peer_rate_rarity_num", "peer_rate_rarity_den",
                      "s0_ok", "s1_ok", "s2_ok", "s3_ok", "s4_ok"]
    for key in base.index:
        for col in invariant_cols:
            a, b = base.loc[key, col], extended.loc[key, col]
            if pd.isna(a):
                assert pd.isna(b), (key, col, a, b)
            else:
                assert a == b, (key, col, a, b)
    checks.append("appending a future observation leaves all existing raw triplets, reference metrics, peer ranks and stages unchanged")

    # Monotone hierarchy, exact integer clock and unique RFID/hour validation.
    assert ((ledger.s1_ok <= ledger.s0_ok) & (ledger.s2_ok <= ledger.s1_ok) &
            (ledger.s3_ok <= ledger.s2_ok) & (ledger.s4_ok <= ledger.s3_ok)).all()
    try:
        build_transition_rules(pd.concat([frame, frame.iloc[[0]]], ignore_index=True), registry)
        raise AssertionError("duplicate RFID/hour accepted")
    except ValueError:
        pass
    fractional = frame.copy(); fractional["ts"] = fractional["ts"].astype(float) + 0.5
    try:
        build_transition_rules(fractional, registry)
        raise AssertionError("fractional source hour accepted")
    except ValueError:
        pass
    checks.append("all stage masks are monotone; duplicate RFID/hour and fractional source-clock keys are rejected")

    source_hashes_after = {name: sha(path) for name, path in paths.items()}
    assert source_hashes_before == source_hashes_after
    raw_inventory = result["diagnostics"]["inventory_counts"]
    result_json = {"status": "passed", "requested_model": "GPT-6 Luna", "requested_effort": "xhigh",
        "check_count": len(checks), "checks": checks, "synthetic_rows": len(frame),
        "raw_inventory_totals": {"valid_triple_n": raw_inventory["valid_triple_n"], "pattern_n": raw_inventory["pattern_n"]},
        "distinct_winner_ordinals": winners, "t720_own_rate": [int(target.own_rate_num), int(target.own_rate_den)],
        "t720_peer_rarity_exact": [int(target.peer_rate_rarity_num), int(target.peer_rate_rarity_den)],
        "source_hashes_before": source_hashes_before, "source_hashes_after": source_hashes_after,
        "ram_preflight": RAM_PREFLIGHT,
        "scope": "synthetic-only in-memory fixtures; no R4/R3 inputs, raw CSV/cache, labels, event scoring or model training read"}
    (ROOT / "transition_checks.json").write_text(json.dumps(result_json, indent=2, ensure_ascii=False), encoding="utf-8")
    return result_json


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False, default=str))
