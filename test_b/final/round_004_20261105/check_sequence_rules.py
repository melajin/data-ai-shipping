from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_rules import build_rules


def put(store, rid, ts, length=200.0, bbox=200.0, score=1.0, lon=127.0, lat=37.0):
    store[(rid, ts)] = {"rfid_id": rid, "ts": ts, "source_ordinal": ts,
                         "len_m": length, "bbox_m": bbox, "cen_lon": lon,
                         "cen_lat": lat, "score": score}


def base_rows(rids, centers_by_rid=None):
    store = {}
    centers_by_rid = centers_by_rid or {}
    for rid in rids:
        centers = centers_by_rid.get(rid, [*range(2, 10), *range(26, 34), *range(50, 58)])
        for c in centers:
            for t in (c - 1, c, c + 1):
                put(store, rid, t)
    return store


def run(store, gears=None):
    frame = pd.DataFrame(list(store.values()))
    registry = pd.DataFrame(gears if gears is not None else [
        {"rfid_id": rid, "primary_gear": "g", "is_single_code": True}
        for rid in frame.rfid_id.unique()
    ])
    return build_rules(frame, registry)


def row(out, rid, ts):
    return out["ledger"].query("rfid_id == @rid and ts == @ts").iloc[0]


checks = {}
# Exact 24 valid triples over 3 center dates; future/current transition not in baseline.
rids = ["V", "P0", "P1", "P2", "P3", "P4"]
store = base_rows(rids)
# Prior transitions for peers only: both centers fall after t=100's strict cutoff.
for peer in rids[1:]:
    put(store, peer, 98, length=220, score=1)
    put(store, peer, 99, length=80, bbox=80)
    put(store, peer, 100, length=80, bbox=80)
    put(store, peer, 102, length=220, score=1)
    put(store, peer, 103, length=80, bbox=80)
    put(store, peer, 104, length=80, bbox=80)
# Three observed persistent transitions on V; score-only stage0 decoy at t=95.
put(store, "V", 95, score=1000)
for t, score in ((100, 90), (105, 80), (110, 70)):
    put(store, "V", t - 1, length=220, score=1)
    put(store, "V", t, length=80, bbox=80, score=score)
    put(store, "V", t + 1, length=80, bbox=80, score=score - 1)
out = run(store)
checks["exact_24_triples_3_days"] = {
    "n": int(row(out, "V", 100).own_baseline_triples),
    "days": int(row(out, "V", 100).own_baseline_center_dates),
    "eligible_stage3": bool(row(out, "V", 100).stage3_ok),
}
assert checks["exact_24_triples_3_days"] == {"n": 24, "days": 3, "eligible_stage3": True}
# Past-only boundary: peer transitions at centers 99 and 103 do not alter t=100 baseline.
checks["strict_prior_excludes_current_and_future_triples"] = {
    "peer_count_at_100": int(row(out, "V", 100).eligible_peer_count),
    "target_transitions_at_100": int(row(out, "V", 100).own_baseline_transitions),
    "target_transitions_at_105": int(row(out, "V", 105).own_baseline_transitions),
}
assert checks["strict_prior_excludes_current_and_future_triples"]["target_transitions_at_100"] == 0
assert checks["strict_prior_excludes_current_and_future_triples"]["target_transitions_at_105"] == 1
assert checks["strict_prior_excludes_current_and_future_triples"]["peer_count_at_100"] == 5
# Methods have three distinct top-1 timestamps; shared cap comes from G's three candidates.
tops = out["predictions"].query("rfid_id == 'V' and rank == 1").set_index("method")["ts"].to_dict()
checks["distinct_method_winners"] = {k: int(v) for k, v in tops.items()}
assert tops == {"B0": 95, "S": 100, "G": 105}
manifest = out["pool_manifest"].query("rfid_id == 'V'").set_index("method")
checks["shared_cap"] = {k: int(v) for k, v in manifest.cap.to_dict().items()}
assert set(checks["shared_cap"].values()) == {3}
assert len(out["predictions"].query("rfid_id == 'V' and method == 'B0'")) <= 3
# Future-only append must not change prior baseline/ranking fields (t+1 persistence already present).
future = dict(store)
for t in range(150, 156):
    put(future, "V", t, length=(80 if t in (152, 153) else 220), bbox=(80 if t in (152, 153) else 220), score=5000)
out_future = run(future)
old = row(out, "V", 105)
new = row(out_future, "V", 105)
fields = ["own_baseline_triples", "own_baseline_transitions", "eligible_peer_count", "peer_percentile", "gear_priority", "stage3_ok"]
assert all((pd.isna(old[f]) and pd.isna(new[f])) or old[f] == new[f] for f in fields)
checks["future_append_invariance"] = {"fields": fields, "unchanged": True}
# Exactly 24 triples but only two center dates is ineligible.
two_day = {"X": [*range(2, 14), *range(26, 38)]}
s = base_rows(["X"], two_day)
put(s, "X", 99, length=220); put(s, "X", 100, length=80, bbox=80); put(s, "X", 101, length=80, bbox=80)
xout = run(s, [{"rfid_id": "X", "primary_gear": "solo", "is_single_code": True}])
x = row(xout, "X", 100)
checks["three_day_boundary"] = {"n": int(x.own_baseline_triples), "days": int(x.own_baseline_center_dates), "reason": x.own_baseline_missing_reason}
assert x.own_baseline_triples >= 24 and x.own_baseline_center_dates == 2 and x.own_baseline_missing_reason == "insufficient_center_dates"
# Remove one observation from the 24-triple baseline: count drops below 24.
s2 = base_rows(["X"])
s2["X", 4]["len_m"] = np.nan
put(s2, "X", 99, length=220); put(s2, "X", 100, length=80, bbox=80); put(s2, "X", 101, length=80, bbox=80)
xout2 = run(s2, [{"rfid_id": "X", "primary_gear": "solo", "is_single_code": True}])
x2 = row(xout2, "X", 100)
checks["24_triple_boundary"] = {"n": int(x2.own_baseline_triples), "reason": x2.own_baseline_missing_reason}
assert x2.own_baseline_triples < 24 and x2.own_baseline_missing_reason == "insufficient_triples"
# Four eligible records in group means only four peers; fallback is explicit.
scarce = {k: v for k, v in store.items() if k[0] in ("V", "P0", "P1", "P2", "P3")}
scarce_gears = [{"rfid_id": rid, "primary_gear": "g", "is_single_code": True} for rid in ("V", "P0", "P1", "P2", "P3")]
sout = run(scarce, scarce_gears)
sx = row(sout, "V", 105)
checks["five_peer_scarcity"] = {"eligible_peers": int(sx.eligible_peer_count), "stage3": bool(sx.stage3_ok), "G_fallback": sout["pool_manifest"].query("rfid_id == 'V' and method == 'G'").iloc[0].fallback_reason}
assert sx.eligible_peer_count == 4 and not sx.stage3_ok and checks["five_peer_scarcity"]["G_fallback"] == "no_gear_eligible_candidates"
# A singleton code gets no peer percentile and uses the common-transition pool.
single = run({k: v for k, v in store.items() if k[0] == "V"}, [{"rfid_id": "V", "primary_gear": "g", "is_single_code": True}])
sv = row(single, "V", 100)
checks["singleton_fallback"] = {"stage3": bool(sv.stage3_ok), "reason": sv.gear_missing_reason,
                                "G_pool": single["pool_manifest"].query("rfid_id == 'V' and method == 'G'").iloc[0].pool_stage}
assert not sv.stage3_ok and sv.gear_missing_reason == "singleton_no_peer_rule" and checks["singleton_fallback"]["G_pool"] == "stage2"
# Missing hour is never interpolated: break t=100 onset's exact prior observation.
gap = {k: v for k, v in store.items() if k != ("V", 99)}
gout = run(gap)
g = row(gout, "V", 100)
checks["broken_gap"] = {"stage1": bool(g.stage1_ok), "previous_reason": g.previous_gap_reason}
assert not g.stage1_ok and g.previous_gap_reason == "missing_observation"

# Persistence requires an exact next hour; invalid and missing next observations defer Stage2.
for label, next_row in (("invalid", {"len_m": np.nan, "bbox_m": 80.0}), ("missing", None)):
    q = {("Q", t): {"rfid_id": "Q", "ts": t, "source_ordinal": t, "len_m": 200.0,
                      "bbox_m": 200.0, "cen_lon": 127.0, "cen_lat": 37.0, "score": 1.0}
         for t in (98, 99, 100)}
    q[("Q", 100)].update(len_m=80.0, bbox_m=80.0)
    if next_row is not None:
        q[("Q", 101)] = {"rfid_id": "Q", "ts": 101, "source_ordinal": 101,
                          "len_m": next_row["len_m"], "bbox_m": next_row["bbox_m"],
                          "cen_lon": 127.0, "cen_lat": 37.0, "score": 1.0}
    qo = run(q, [{"rfid_id": "Q", "primary_gear": "unknown", "is_single_code": True}])
    qr = row(qo, "Q", 100)
    checks[f"{label}_next_defers_stage2"] = {"stage1": bool(qr.stage1_ok), "stage2": bool(qr.stage2_ok), "reason": qr.next_gap_reason}
    assert qr.stage1_ok and not qr.stage2_ok
    assert qr.next_gap_reason == ("invalid_geometry" if label == "invalid" else "missing_observation")
# No common transition pool falls back to Stage0 and cap derives from that G pool.
no_history = {("N", 10): {"rfid_id": "N", "ts": 10, "source_ordinal": 10, "len_m": 30.0,
                            "bbox_m": 30.0, "cen_lon": 127.0, "cen_lat": 37.0, "score": 3.0}}
nh = run(no_history, [{"rfid_id": "N", "primary_gear": "mixed", "is_single_code": True}])
nm = nh["pool_manifest"].query("rfid_id == 'N' and method == 'G'").iloc[0]
checks["no_history_fallback"] = {"pool_stage": nm.pool_stage, "pool_n": int(nm.actual_pool_n), "cap": int(nm.cap), "reason": nm.fallback_reason}
assert nm.pool_stage == "stage0" and nm.actual_pool_n == 1 and nm.cap == 1 and nm.fallback_reason == "no_common_transitions"
assert bool(row(nh, "N", 10).gear_known) is False

# Dataframe order/index and no duplicate timestamp predictions.
assert list(out["ledger"].index) == list(pd.DataFrame(list(store.values())).index)
assert not out["predictions"].duplicated(["rfid_id", "method", "ts"]).any()
checks["ledger_order_and_prediction_uniqueness"] = True

result = {"status": "passed", "fixture_scope": "small synthetic rows only; no development data read", "checks": checks}
(HERE / "rule_checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
