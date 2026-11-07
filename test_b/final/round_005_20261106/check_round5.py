"""Small synthetic checks for Round5 ranking, caps, fallback, and shared events."""
from __future__ import annotations
import importlib.util
import json
import math
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("round5", HERE / "analyze_round5.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

ledger = pd.DataFrame([
    # RFID A: S1 legacy-score winner at ts=10, while saved S winner is ts=11.
    {"rfid_id":"A","ts":10,"source_ordinal":2,"score":.95,"stage0_ok":True,"stage1_ok":True,"stage2_ok":False},
    {"rfid_id":"A","ts":11,"source_ordinal":1,"score":.9,"stage0_ok":True,"stage1_ok":True,"stage2_ok":True},
    {"rfid_id":"A","ts":12,"source_ordinal":3,"score":.7,"stage0_ok":True,"stage1_ok":True,"stage2_ok":True},
    {"rfid_id":"A","ts":13,"source_ordinal":4,"score":.6,"stage0_ok":True,"stage1_ok":True,"stage2_ok":True},
    # RFID B has no stage1: fallback is stage0; cap remains the saved G cap of 1.
    {"rfid_id":"B","ts":20,"source_ordinal":5,"score":.5,"stage0_ok":True,"stage1_ok":False,"stage2_ok":False},
    {"rfid_id":"B","ts":21,"source_ordinal":6,"score":.6,"stage0_ok":True,"stage1_ok":False,"stage2_ok":False},
])
manifest = pd.DataFrame([
    {"rfid_id":"A","method":"G","cap":3,"fallback_reason":None},
    {"rfid_id":"B","method":"G","cap":1,"fallback_reason":"no_common_transitions"},
])
s1, sm = m.build_s1(ledger, manifest)
assert list(s1[s1.rfid_id=="A"].ts) == [10,11,12] # score ordering; 3-cap retained
assert int(sm.set_index("rfid_id").loc["A","cap"]) == 3
assert list(s1[s1.rfid_id=="B"].ts) == [21] # stage0 fallback and original cap 1
assert sm.set_index("rfid_id").loc["B","pool_stage"] == "stage0"

events = pd.DataFrame([
    {"acc_id":"e1","rfid_id":"A","tier":0,"conflict":False,"acc_ts":11,"primary_gear":"g","is_single_code":True,"gear_stratum":"g"},
    {"acc_id":"e2","rfid_id":"A","tier":1,"conflict":False,"acc_ts":12,"primary_gear":"g","is_single_code":True,"gear_stratum":"g"},
])
ref = pd.DataFrame([
    {"rfid_id":"A","method":"B0","rank":1,"ts":20},
    {"rfid_id":"A","method":"B0","rank":2,"ts":21},
    {"rfid_id":"A","method":"S","rank":1,"ts":11},
])
merged = pd.concat([ref, s1[s1.rfid_id=="A"][["rfid_id","method","rank","ts"]]], ignore_index=True)
manifest_eval = pd.DataFrame([
    {"rfid_id":"A","method":"B0","pool_stage":"stage0","actual_pool_n":10,"cap":4,"fallback_reason":None},
    {"rfid_id":"A","method":"S1","pool_stage":"stage1","actual_pool_n":4,"cap":3,"fallback_reason":None},
])
ev, _ = m.eval_events(events, merged, manifest_eval)
assert len(ev) == 2*4*2 and set(ev.rfid_id) == {"A"} and set(ev.acc_id) == {"e1","e2"}
assert set(ev.method) == {"B0","S","S1","G"} and set(ev.k) == {1,4}
assert int(s1[s1.rfid_id=="A"].iloc[0].ts) != int(ref[ref.method=="S"].iloc[0].ts)
assert m.event_error([11, 12], 11) == (0, True)
assert m.event_error([30], 11) == (19, False)

helper_spec = importlib.util.spec_from_file_location("round2", m.ROUND2_HELPERS)
helper = importlib.util.module_from_spec(helper_spec); helper_spec.loader.exec_module(helper)
assert math.isclose(helper._random_hit_probability(3,1,2), 2/3)
fixture = [
    {"acc_id":"t1-a","tier":0,"top1_expected":.2,"top4_hit_probability":.3},
    {"acc_id":"t1-b","tier":1,"top1_expected":.4,"top4_hit_probability":.5},
    {"acc_id":"other-a","tier":2,"top1_expected":.8,"top4_hit_probability":.7},
    {"acc_id":"other-b","tier":3,"top1_expected":.9,"top4_hit_probability":.9},
]
all_random = m.aggregate_random_records(fixture)
tier01_random = m.aggregate_random_records([r for r in fixture if r["tier"] in (0, 1)])
assert math.isclose(all_random["mean_top1_expected"], .575)
assert math.isclose(tier01_random["mean_top1_expected"], .3)
observed_tier01 = .35
assert observed_tier01 > tier01_random["mean_top1_expected"]
assert not observed_tier01 > all_random["mean_top1_expected"]
result = {"version":"round5-cohort-random-fixture-v1","status":"passed","checks":["S1 ranked winner differs from stage2 candidate ordering","original per-RFID G caps 1 and 3 retained","empty stage1 falls back to stage0","all methods/budgets share the same event RFID list","top1 is rank1 and top4 hit uses same ranked list","Round2 random expectation helper gives exact 2/3 for n=3,h=1,k=2","cohort fixture hand means are all=.575 and Tier01=.3; observed .35 passes Tier01 and fails all-scope mismatch"]}
(HERE/"cohort_checks.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result))
