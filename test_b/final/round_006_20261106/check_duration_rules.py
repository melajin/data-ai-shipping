"""Tiny deterministic contract checks; never loads project data."""
import json
import math
from pathlib import Path
import pandas as pd
from duration_rules import build_duration_rules

BASE = pd.Timestamp("2026-10-31 00:00:00")
rows=[]
def put(rfid, ts, small, score=0.0, length=None, bbox=None):
    ts=pd.Timestamp(ts)
    rows.append({"rfid_id":rfid,"ts":ts,"source_ordinal":len(rows),"len_m":(50.0 if small else 150.0) if length is None else length,"bbox_m":(50.0 if small else 150.0) if bbox is None else bbox,"cen_lon":0.0,"cen_lat":0.0,"score":score})
starts=[BASE-pd.Timedelta(hours=x) for x in (720,712,704,696,600,592,584,480,472,464,456,448)]
# Target vessel: twelve completed length-5 references, first exactly at the inclusive window edge.
for j,start in enumerate(starts):
    put("A",start-pd.Timedelta(hours=1),False)
    for h in range(5): put("A",start+pd.Timedelta(hours=h),True)
    put("A",start+pd.Timedelta(hours=5),False)
# Current candidates: B0 favors an isolated high legacy row; S favors L=6; G's peer CDF breaks
# an exact self-CDF tie in favor of L=7. The two small runs are separated by a data gap.
put("A",BASE-pd.Timedelta(hours=6),False)
for h in range(-5,1): put("A",BASE+pd.Timedelta(hours=h),True,10 if h==0 else 1)
for h in range(7,14): put("A",BASE+pd.Timedelta(hours=h),True,1 if h==13 else 0)
put("A",BASE+pd.Timedelta(hours=20),True,999)
# Five fully eligible peers each have twelve length-6 references; the sixth has nine prior refs
# plus a run whose close_ts is exactly BASE and must be excluded at that time.
for k in range(1,7):
    rfid=f"P{k}"
    peer_starts=starts if k<6 else starts[:9]
    for start in peer_starts:
        put(rfid,start-pd.Timedelta(hours=1),False)
        for h in range(6): put(rfid,start+pd.Timedelta(hours=h),True)
        put(rfid,start+pd.Timedelta(hours=6),False)
    if k==6:
        for h in (-2,-1): put(rfid,BASE+pd.Timedelta(hours=h),True)
        put(rfid,BASE,False)
# Additional boundary/censor cases: left-censored, invalid geometry breaks/censors, and a
# non-small immediately before an isolated small observation gives an observed reject at d2.
put("EDGE",BASE,True)
put("EDGE",BASE+pd.Timedelta(hours=1),True,length=float("nan"))
put("EDGE",BASE+pd.Timedelta(hours=3),True)
put("EDGE",BASE+pd.Timedelta(hours=2),False)
put("ONE",BASE-pd.Timedelta(hours=1),False)
put("ONE",BASE,True)
frame=pd.DataFrame(rows)
# A missing old score must not remove a geometry-valid completed reference run.
old_score_idx=frame.index[(frame.rfid_id=="A") & (frame.ts==starts[0])][0]
frame.at[old_score_idx,"score"]=float("nan")
gear=pd.DataFrame([{"rfid_id":x,"primary_gear":"trawl","is_single_code":True} for x in ["A"]+[f"P{k}" for k in range(1,7)]+["EDGE","ONE"]])
art=build_duration_rules(frame,gear)
ledger=art["ledger"].set_index(["rfid_id","ts"],drop=False)
byid=art["predictions"].groupby(["rfid_id","method"],sort=False).first()
pools=art["pool_manifest"].set_index(["rfid_id","method"])
reg=art["run_registry"]
# Both observed boundaries required; edge start is included; ten runs over three dates suffice.
a0=ledger.loc[("A",BASE)]
assert a0.self_ref_n==12 and a0.self_ref_start_dates>=3 and a0.d3_ok
assert a0.current_L==6 and not a0.current_L_is_lower_bound
old_bad_ts=starts[0]
old_bad=ledger.loc[("A",old_bad_ts)]
assert not old_bad.d0_ok and all(not bool(old_bad[f"d{i}_ok"]) and old_bad[f"d{i}_status"]=="not_applicable" for i in range(1,5))
assert bool(reg[(reg.rfid_id=="A") & (reg.start_ts==starts[0])].iloc[0].left_confirmed) and bool(reg[(reg.rfid_id=="A") & (reg.start_ts==starts[0])].iloc[0].right_confirmed)
assert a0.peer_eligible_n==5, a0.peer_eligible_n
# Strict close boundary: P6's close-at-BASE run is not in its references at BASE; only nine remain.
# Peer eligibility therefore excludes P6.
assert len(reg[(reg.rfid_id=="P6") & (reg.close_ts==BASE)])==1
assert ledger.loc[("A",BASE+pd.Timedelta(hours=13)),"self_ref_n"]==10
assert not bool(reg[(reg.rfid_id=="A") & (reg.start_ts==BASE-pd.Timedelta(hours=5))].iloc[0].right_confirmed)
# Distinct method winners, no hidden reranking, and a shared cap derived from actual G pool size.
assert byid.loc[("A","B0"),"ts"]==BASE+pd.Timedelta(hours=20)
assert byid.loc[("A","S"),"ts"]==BASE
assert byid.loc[("A","G"),"ts"]==BASE+pd.Timedelta(hours=13)
assert pools.loc[("A","B0"),"cap"]==pools.loc[("A","S"),"cap"]==pools.loc[("A","G"),"cap"]
assert pools.loc[("A","G"),"cap"]==min(4,pools.loc[("A","G"),"actual_pool_n"])
# Missing previous hour defers, observed non-small previous hour rejects.
assert ledger.loc[("EDGE",BASE),"current_L_is_lower_bound"]
assert ledger.loc[("EDGE",BASE),"d2_status"]=="defer"
assert ledger.loc[("EDGE",BASE),"d3_status"]=="not_applicable" and ledger.loc[("EDGE",BASE),"d4_status"]=="not_applicable"
assert [set(x) for x in art["stage_spec"]]==[set(["stage_id","label","input_stage","mask_column","status_column","reason_column"])]*5
assert ledger.loc[("ONE",BASE),"d2_status"]=="reject"
# Invalid geometry makes an unconfirmed boundary and cannot complete a run.
edge_runs=reg[reg.rfid_id=="EDGE"]
assert len(edge_runs)>=2 and not edge_runs.iloc[0].right_confirmed
# Unknown gear and singleton gear fall back explicitly.
unknown=gear.copy(); unknown.loc[unknown.rfid_id=="A","is_single_code"]=False
u=build_duration_rules(frame,unknown)
assert u["ledger"].loc[u["ledger"].rfid_id=="A","d4_status"].eq("defer").any()
assert u["pool_manifest"].query("rfid_id == 'A' and method == 'G'").iloc[0].fallback_reason=="no_peer_history_candidates"
singleton=gear.copy(); singleton.loc[~singleton.rfid_id.eq("A"),"primary_gear"]="other"
s=build_duration_rules(frame,singleton)
assert s["ledger"].loc[s["ledger"].rfid_id=="A","peer_missing_reason"].dropna().eq("singleton_gear").any()
assert s["pool_manifest"].query("rfid_id == 'A' and method == 'G'").iloc[0].pool_stage=="d3"
assert s["pool_manifest"].query("rfid_id == 'A' and method == 'G'").iloc[0].fallback_reason=="no_peer_history_candidates"
# Appending a future valid non-small observation may confirm the run, but cannot alter prior
# scored candidate fields (future close still fails close_ts < earlier t).
future=frame.copy()
for h in (14,15):
    future.loc[len(future)]={"rfid_id":"A","ts":BASE+pd.Timedelta(hours=h),"source_ordinal":len(future),"len_m":150.0,"bbox_m":150.0,"cen_lon":0.0,"cen_lat":0.0,"score":0.0}
future_art=build_duration_rules(future,gear)
cols=["current_L","current_L_is_lower_bound","self_ref_n","self_cdf","peer_eligible_n","peer_cdf_mean","d0_status","d1_status","d2_status","d3_status","d4_status"]
before=art["ledger"].query("rfid_id == 'A'").set_index("ts").loc[BASE+pd.Timedelta(hours=13),cols]
after=future_art["ledger"].query("rfid_id == 'A'").set_index("ts").loc[BASE+pd.Timedelta(hours=13),cols]
pd.testing.assert_series_equal(before,after,check_names=False)
# Invalid current scores in an otherwise consecutive-small geometry run are deferred
# and cannot violate nested candidate masks; their valid observations still form a completed run.
guard_rows=[]
def guard_put(ts, length, score, ordinal):
    guard_rows.append({"rfid_id":"GUARD","ts":ts,"source_ordinal":ordinal,"len_m":length,"bbox_m":length,"cen_lon":float("nan"),"cen_lat":float("nan"),"score":score})
guard_put(BASE-pd.Timedelta(hours=1),150.0,1.0,0)
for h,score in enumerate((1.0,float("nan"),float("inf"),2.0)):
    guard_put(BASE+pd.Timedelta(hours=h),50.0,score,h+1)
guard_put(BASE+pd.Timedelta(hours=4),150.0,3.0,5)
guard=build_duration_rules(pd.DataFrame(guard_rows),pd.DataFrame([{"rfid_id":"GUARD","primary_gear":"unknown","is_single_code":False}]))
gl=guard["ledger"].sort_values("ts")
bad=gl[~pd.to_numeric(gl.score,errors="coerce").map(lambda x: pd.notna(x) and math.isfinite(x))]
assert len(bad)==2 and bad.score.isna().sum()==1 and math.isinf(float(bad.score.dropna().iloc[0]))
assert bad[[f"d{i}_ok" for i in range(1,5)]].eq(False).all().all()
assert bad[[f"d{i}_status" for i in range(1,5)]].eq("not_applicable").all().all()
assert len(guard["run_registry"])==1 and int(guard["run_registry"].iloc[0].observed_length)==4
assert bool(guard["run_registry"].iloc[0].left_confirmed) and bool(guard["run_registry"].iloc[0].right_confirmed)

# G fallback reason is determined by its actual fallback pool stage.
def fallback_frame(rfid, points):
    return pd.DataFrame([{"rfid_id":rfid,"ts":ts,"source_ordinal":i,"len_m":length,"bbox_m":length,"cen_lon":0.0,"cen_lat":0.0,"score":score} for i,(ts,length,score) in enumerate(points)])
def g_fallback(artifacts, rfid):
    return artifacts["pool_manifest"].query("rfid_id == @rfid and method == 'G'").iloc[0]
short=build_duration_rules(fallback_frame("SHORT",[(BASE-pd.Timedelta(hours=1),150.0,1.0),(BASE,50.0,1.0),(BASE+pd.Timedelta(hours=1),50.0,2.0)]),pd.DataFrame([{"rfid_id":"SHORT","primary_gear":None,"is_single_code":False}]))
assert g_fallback(short,"SHORT").pool_stage=="d2" and g_fallback(short,"SHORT").fallback_reason=="no_self_history_candidates"
only=build_duration_rules(fallback_frame("ONLY",[(BASE-pd.Timedelta(hours=1),150.0,1.0),(BASE,50.0,2.0)]),pd.DataFrame([{"rfid_id":"ONLY","primary_gear":None,"is_single_code":False}]))
assert g_fallback(only,"ONLY").pool_stage=="d0" and g_fallback(only,"ONLY").fallback_reason=="no_continuation_candidates"
none=build_duration_rules(fallback_frame("NONE",[(BASE,50.0,float("nan"))]),pd.DataFrame([{"rfid_id":"NONE","primary_gear":None,"is_single_code":False}]))
assert g_fallback(none,"NONE").pool_stage=="d0" and g_fallback(none,"NONE").actual_pool_n==0 and g_fallback(none,"NONE").fallback_reason=="no_observations"
assert g_fallback(s,"A").pool_stage=="d3" and g_fallback(s,"A").fallback_reason=="no_peer_history_candidates"

# API boundary: integer values are epoch-hours; equivalent aligned datetimes match exactly.
unit_hour0=int(BASE.value//3_600_000_000_000)
unit_frame=pd.DataFrame([
    {"rfid_id":"UNIT","ts":unit_hour0,"source_ordinal":0,"len_m":50.0,"bbox_m":50.0,"cen_lon":float("nan"),"cen_lat":float("nan"),"score":1.0},
    {"rfid_id":"UNIT","ts":unit_hour0+1,"source_ordinal":1,"len_m":50.0,"bbox_m":50.0,"cen_lon":float("nan"),"cen_lat":float("nan"),"score":2.0},
])
unit_gear=pd.DataFrame([{"rfid_id":"UNIT","primary_gear":"unknown","is_single_code":False}])
integer_art=build_duration_rules(unit_frame,unit_gear)
datetime_frame=unit_frame.copy()
datetime_frame["ts"]=pd.to_datetime(datetime_frame["ts"],unit="h")
datetime_art=build_duration_rules(datetime_frame,unit_gear)
pd.testing.assert_frame_equal(integer_art["ledger"],datetime_art["ledger"])
pd.testing.assert_frame_equal(integer_art["predictions"],datetime_art["predictions"])
pd.testing.assert_frame_equal(integer_art["pool_manifest"],datetime_art["pool_manifest"])
pd.testing.assert_frame_equal(integer_art["run_registry"],datetime_art["run_registry"])
unit_ledger=integer_art["ledger"].sort_values("source_ordinal")
assert unit_ledger["source_ts_hour"].tolist()==[unit_hour0,unit_hour0+1]
assert unit_ledger["d0_ok"].all() and bool(unit_ledger.iloc[1]["d2_ok"])
# Timestamp values carrying nanoseconds are not guessed or interpreted as a different unit.
wrong_unit=unit_frame.copy(); wrong_unit["ts"]=pd.Series([int(BASE.value)]*2,dtype="int64")
try:
    build_duration_rules(wrong_unit,unit_gear)
except ValueError:
    pass
else:
    raise AssertionError("nanosecond-valued integer ts must be rejected as epoch-hours")
unaligned=datetime_frame.copy(); unaligned.loc[0,"ts"]=unaligned.loc[0,"ts"]+pd.Timedelta(minutes=1)
try:
    build_duration_rules(unaligned,unit_gear)
except ValueError:
    pass
else:
    raise AssertionError("non-hour-aligned datetime ts must be rejected")

result={"status":"passed","checks":["both observed boundaries and invalid/gap censoring","strict close boundary and inclusive start-window edge","10 runs/3 dates and 5 other-vessel boundary","current observed lower bound","future append invariance of earlier scores","unknown and singleton gear fallback","distinct B0/S/G winners and shared caps","defer/reject/not_applicable stage statuses","integer-hour/datetime equivalence and source_ts_hour lineage","nanosecond-unit and unaligned timestamps rejected","NaN coordinates do not invalidate duration geometry","NaN/inf score masks defer and preserve geometry-valid reference runs","G fallback reasons follow d3/d2/d0/empty actual pools","d0-failed rows stay outside every downstream candidate mask"],"input_rows":len(frame),"interface_fixture_rows":len(unit_frame),"fixture_only":True,"real_data_loaded":False}
(Path(__file__).parent/"rule_checks.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result))


