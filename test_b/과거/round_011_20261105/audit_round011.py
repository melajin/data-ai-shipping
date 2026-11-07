"""Independent bounded-memory Round011 output audit (no implementation imports).

Real-output execution is intentionally separate from --self-test. See AUDIT.md.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parent
CONTEXTS = ("T", "L", "TL")
SCORES = ("score_raw_lin",) + tuple(f"{c}_score_{s}" for c in CONTEXTS for s in ("lin", "activity", "joint"))


def number(value: str) -> float:
    return float(value) if value not in ("", "None", "null") else math.nan


def flag(value: str) -> bool:
    return value.lower() in ("true", "1")


def close(a: float, b: float) -> bool:
    return (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, abs_tol=2e-12, rel_tol=2e-12)


def distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    # Preserve the frozen implementation's radians-before-subtraction ordering.
    # Converting deltas first is mathematically equivalent but changes nearest
    # selection at subnanometer coordinate-roundoff ties (see diagnostics JSON).
    lon1,lat1,lon2,lat2 = (math.radians(v) for v in (lon1,lat1,lon2,lat2))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def hour_distance(a: int, b: int) -> int:
    d = abs(a % 24 - b % 24)
    return min(d, 24-d)


def midrank(value: float, reference: Iterable[float]) -> float:
    values = list(reference)
    return sum((x < value) + .5*(x == value) for x in values)/len(values)


def ranks(times: list[int], scores: list[float], accident: int) -> dict[str, float]:
    """Exact tie marginalization, independently expressed with integer combs."""
    if not scores:
        return {"top1": math.nan, "top10": math.nan, "chance": math.nan}
    pairs = sorted(zip(scores, times), reverse=True)
    max_score = pairs[0][0]
    ties = [t for s, t in pairs if s == max_score]
    top1 = sum(abs(t-accident) <= 6 for t in ties)/len(ties)
    k = min(10, len(pairs))
    boundary = pairs[k-1][0]
    above = [t for s, t in pairs if s > boundary]
    equal = [t for s, t in pairs if s == boundary]
    n_choose = k-len(above)
    if any(abs(t-accident) <= 6 for t in above):
        top10 = 1.0
    else:
        misses = sum(abs(t-accident) > 6 for t in equal)
        top10 = 1.0 - (math.comb(misses, n_choose)/math.comb(len(equal), n_choose) if misses >= n_choose else 0.0)
    return {"top1": top1, "top10": top10, "chance": sum(abs(t-accident) <= 6 for t in times)/len(times)}


@dataclass(slots=True)
class Window:
    ts: int
    n_rows: int
    n_valid: int
    n_lin: int
    n_pairs: int
    lin: float
    activity: float
    movement: float
    lon: float
    lat: float
    center_valid: bool
    quality: bool
    common: bool
    scores: tuple[float, ...]
    refs: tuple[tuple[int, ...], ...]
    eligible: tuple[tuple[int, int], ...]
    reasons: tuple[str, ...]

    @classmethod
    def parse(cls, r: dict[str, str]) -> "Window":
        return cls(int(r["ts"]), int(r["n_rows"]), int(r["n_valid_rows"]), int(r["n_lin_valid"]), int(r["n_pairs"]),
                   number(r["lin_raw"]), number(r["A"]), number(r["M"]), number(r["end_lon"]), number(r["end_lat"]),
                   flag(r["end_center_valid"]), flag(r["quality_valid"]), flag(r["common_candidate"]),
                   tuple(number(r[s]) for s in SCORES),
                   tuple(tuple(json.loads(r[f"{c}_ref_ts_json"])) for c in CONTEXTS),
                   tuple((int(r[f"{c}_eligible_endpoints"]), int(r[f"{c}_eligible_days"])) for c in CONTEXTS),
                   tuple(r[f"{c}_unknown_reason"] for c in CONTEXTS))


def select_independent(current: Window, windows: list[Window], times: list[int], context: str) -> tuple[tuple[int, ...], tuple[int, int]]:
    daily: dict[int, tuple[tuple[float, ...], int]] = {}
    count = 0
    for ref in windows[bisect.bisect_left(times, current.ts-720):bisect.bisect_right(times, current.ts-24)]:
        if not ref.quality or abs(ref.n_rows-current.n_rows) > 1:
            continue
        hour = hour_distance(current.ts, ref.ts)
        if context != "L" and hour > 1:
            continue
        spatial = math.inf
        if context != "T":
            if not current.center_valid or not ref.center_valid:
                continue
            spatial = distance(current.lon, current.lat, ref.lon, ref.lat)
            if spatial > 10000:
                continue
        count += 1
        delta = abs(ref.n_rows-current.n_rows)
        key = (hour, delta, ref.ts) if context == "T" else ((spatial, delta, ref.ts) if context == "L" else (hour, spatial, delta, ref.ts))
        day = ref.ts//24
        if day not in daily or key < daily[day][0]:
            daily[day] = (key, ref.ts)
    chosen = tuple(daily[day][1] for day in sorted(daily, reverse=True)[:10])
    return chosen, (count, len(daily))


class Checks:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.failures: list[dict] = []

    def check(self, test: str, condition: bool, detail: object = None) -> None:
        self.counts[test] = self.counts.get(test, 0)+1
        if not condition and len(self.failures) < 100:
            self.failures.append({"check": test, "detail": detail})


def memory_receipt() -> dict:
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(k, ctypes.c_ulonglong) for k in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    status = Status()
    status.length = ctypes.sizeof(Status)
    if sys.platform != "win32" or not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError("Windows available-RAM receipt unavailable")
    processes = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 12 Id,ProcessName,WorkingSet64 | ConvertTo-Json -Compress"], capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "available_bytes": status.available,
            "expected_peak_bytes": 256*1024**2, "required_available_bytes": 768*1024**2,
            "other_processes": json.loads(processes.stdout) if processes.returncode == 0 else "snapshot unavailable",
            "concurrency": "Parent must authorize sequential audit after experiment exits."}


def audit_vessel(vessel: str, windows: list[Window], checks: Checks) -> dict:
    times = [w.ts for w in windows]
    lookup = {w.ts: w for w in windows}
    checks.check("timestamp_unique_sorted", times == sorted(set(times)), vessel)
    sampled = set(range(min(5, len(windows))))
    if windows:
        sampled.update(round((len(windows)-1)*i/7) for i in range(8))
        common_indices = [i for i,w in enumerate(windows) if w.common]
        if common_indices:
            sampled.update(common_indices[round((len(common_indices)-1)*i/7)] for i in range(8))
    for index, current in enumerate(windows):
        detail = [vessel, current.ts]
        expected_quality = current.n_valid >= 4 and current.n_lin >= 3 and current.n_pairs >= 2 and all(math.isfinite(v) for v in (current.lin, current.activity, current.movement))
        checks.check("quality_counts", current.quality == expected_quality, detail)
        checks.check("raw_lin_score", close(current.scores[0], -current.lin) if current.quality else not math.isfinite(current.scores[0]), detail)
        expected_common = current.quality and all(len(refs) == 10 for refs in current.refs) and all(math.isfinite(v) for v in current.scores)
        checks.check("common_universe", current.common == expected_common, detail)
        for ci, context in enumerate(CONTEXTS):
            refs = current.refs[ci]
            checks.check("ref_distinct_latest_days_order", len({t//24 for t in refs}) == len(refs) and [t//24 for t in refs] == sorted([t//24 for t in refs], reverse=True) and len(refs) <= 10, detail+[context])
            valid = True
            ref_windows = []
            for t in refs:
                ref = lookup.get(t)
                valid &= current.ts-720 <= t <= current.ts-24 and ref is not None
                if ref is None:
                    continue
                ref_windows.append(ref)
                valid &= ref.quality and abs(ref.n_rows-current.n_rows) <= 1
                if context != "L":
                    valid &= hour_distance(current.ts, t) <= 1
                if context != "T":
                    valid &= current.center_valid and ref.center_valid and distance(current.lon, current.lat, ref.lon, ref.lat) <= 10000+1e-7
            checks.check("ref_past_range_same_vessel_quality_matching", valid, detail+[context])
            scores = current.scores[1+ci*3:4+ci*3]
            if current.quality and len(ref_windows) == 10:
                p_lin = midrank(current.lin, (r.lin for r in ref_windows))
                p_a = midrank(current.activity, (r.activity for r in ref_windows))
                p_m = midrank(current.movement, (r.movement for r in ref_windows))
                checks.check("context_scores_midrank", all(close(a,b) for a,b in zip(scores, (1-p_lin, 1-p_a, (1-p_a)*p_m))), detail+[context])
            else:
                checks.check("insufficient_refs_unknown", all(not math.isfinite(s) for s in scores), detail+[context])
            if index in sampled and current.quality:
                selected, counts = select_independent(current, windows, times, context)
                checks.check("reference_selection_sample", refs == selected and current.eligible[ci] == counts, detail+[context, list(refs), list(selected)])
    common = [w for w in windows if w.common]
    return {"timestamps": len(windows), "common": len(common), "min_ts": min(times) if times else None, "max_ts": max(times) if times else None}


def rule_column(rule: str) -> str:
    if rule == "raw_lin":
        return "score_raw_lin"
    context, metric = rule.split("_", 1)
    return f"{context}_score_{metric}"


def audit_events(vessel: str, windows: list[Window], event_rows: list[dict[str,str]], checks: Checks) -> list[dict]:
    common = [w for w in windows if w.common]
    times = [w.ts for w in common]
    output = []
    for row in event_rows:
        accident = int(row["acc_ts"])
        rule = row["rule"]
        evaluable = len(common) >= 100
        detail = [row["acc_id"], rule]
        checks.check("event_candidate_evaluable", int(row["candidate_count"]) == len(common) and flag(row["evaluable"]) == evaluable, detail)
        observed_near = sum(abs(w.ts-accident) <= 6 for w in windows)
        quality_near = sum(abs(w.ts-accident) <= 6 and w.quality for w in windows)
        common_near = sum(abs(t-accident) <= 6 for t in times)
        checks.check("event_near_coverage", (int(row["observed_near_count"]), int(row["quality_near_count"]), int(row["common_near_count"])) == (observed_near,quality_near,common_near) and close(number(row["near_coverage_13h"]), common_near/13), detail)
        checks.check("event_candidate_range", row["candidate_min_ts"] == (str(min(times)) if times else "") and row["candidate_max_ts"] == (str(max(times)) if times else ""), detail)
        computed = {"acc_id": int(row["acc_id"]), "rfid_id": int(vessel), "tier": int(row["tier"]), "rule": rule,
                    "evaluable": evaluable, "common_near_count": common_near}
        if evaluable:
            column = SCORES.index(rule_column(rule))
            values = ranks(times, [w.scores[column] for w in common], accident)
            checks.check("event_top1_top10_chance", all(close(values[key], number(row[field])) for key,field in (("top1","top1_expected"),("top10","top10_probability"),("chance","chance"))), detail)
            checks.check("event_conservative_valid", close(values["top1"],number(row["conservative_top1_expected"])) and close(values["top10"],number(row["conservative_top10_probability"])), detail)
            computed.update(values)
        else:
            checks.check("event_unknown_preserved", all(row[key] == "" for key in ("top1_expected","top10_probability","chance")) and number(row["conservative_top1_expected"]) == 0 and number(row["conservative_top10_probability"]) == 0, detail)
            computed.update(top1=0.0, top10=0.0, chance=math.nan)
        output.append(computed)
    return output


def audit_summary(summary: dict, computed: list[dict], checks: Checks) -> None:
    for profile,total in (("tier01",60),("all100",100)):
        rows = [r for r in computed if profile == "all100" or r["tier"] <= 1]
        checks.check("fixed_profile_denominator", summary["profiles"][profile]["n_total"] == total, profile)
        for rule,reported in summary["profiles"][profile]["rules"].items():
            chosen = [r for r in rows if r["rule"] == rule]
            valid = [r for r in chosen if r["evaluable"]]
            expected = {"n_total":total,"n_evaluable":len(valid),"n_unknown":total-len(valid),
                        "n_evaluable_vessels":len({r["rfid_id"] for r in valid}),
                        "top1_expected_sum":sum(r["top1"] for r in chosen),
                        "top1_conditional":sum(r["top1"] for r in valid)/len(valid) if valid else None,
                        "top10_conditional":sum(r["top10"] for r in valid)/len(valid) if valid else None,
                        "chance_conditional":sum(r["chance"] for r in valid)/len(valid) if valid else None,
                        "top1_unconditional":sum(r["top1"] for r in chosen)/total,
                        "top10_unconditional":sum(r["top10"] for r in chosen)/total,
                        "n_evaluable_without_near_candidates":sum(r["common_near_count"] == 0 for r in valid)}
            checks.check("summary_rule_metrics", len(chosen)==total and all((reported[k] is None if v is None else close(reported[k],v)) for k,v in expected.items()), [profile,rule,expected])
    # Independently expand repeated vessel draws into event indices rather than
    # reusing the implementation's cluster sums/counts aggregation.
    import numpy as np
    lookup = {(r["acc_id"],r["rule"]):r for r in computed}
    events = sorted((r for r in computed if r["rule"] == "TL_lin" and r["tier"] <= 1 and r["evaluable"]), key=lambda r:r["acc_id"])
    contrasts = summary["primary_contrasts"]
    checks.check("fixed_contrast_family",[(c["contrast"],c["rule_a"],c["rule_b"]) for c in contrasts]==[("H1_TL_minus_T","TL_lin","T_lin"),("H1_TL_minus_L","TL_lin","L_lin"),("H2_TL_minus_T","TL_joint","T_joint"),("H2_TL_minus_L","TL_joint","L_joint")])
    matrix = np.array([[lookup[(e["acc_id"],c["rule_a"])]["top1"]-lookup[(e["acc_id"],c["rule_b"])]["top1"] for c in contrasts] for e in events], dtype=float).reshape(-1,4)
    groups = [[i for i,e in enumerate(events) if e["rfid_id"] == vessel] for vessel in sorted({e["rfid_id"] for e in events})]
    if groups:
        rng = np.random.default_rng(11052026)
        bootstrap = np.empty((4000,4))
        for iteration in range(4000):
            selected = [i for draw in rng.integers(0,len(groups),len(groups)) for i in groups[int(draw)]]
            bootstrap[iteration] = matrix[selected].mean(axis=0)
        lower,upper = np.quantile(bootstrap,[.00625,.99375],axis=0,method="linear")
        mean = matrix.mean(axis=0)
        for i,reported in enumerate(contrasts):
            checks.check("bootstrap_repeated_vessel_exact", reported["n_events"]==len(events) and reported["n_clusters"]==len(groups) and all(close(reported[k],v) for k,v in (("mean_difference",mean[i]),("ci_low",lower[i]),("ci_high",upper[i]))) and reported["exploratory_improvement_supported"] == bool(len(events)>=30 and lower[i]>0), reported["contrast"])
    else:
        checks.check("bootstrap_empty", all(c["n_events"]==0 and c["ci_low"] is None and not c["exploratory_improvement_supported"] for c in contrasts))


def raw_sample_audit(parquet_path: Path, samples: dict[int,dict[int,Window]], checks: Checks) -> dict:
    import pyarrow.parquet as pq
    needed = {vessel:{hour for t in windows for hour in range(t-6,t+1)} for vessel,windows in samples.items()}
    retained: dict[int,dict[int,tuple]] = {v:{} for v in samples}
    scanned = 0
    for batch in pq.ParquetFile(parquet_path).iter_batches(batch_size=8192, columns=["rfid_id_int","ts","len_m","bbox_m","cen_lon","cen_lat"],use_threads=False):
        columns = batch.to_pydict()
        for vessel,t,length,bbox,lon,lat in zip(*(columns[k] for k in ("rfid_id_int","ts","len_m","bbox_m","cen_lon","cen_lat"))):
            scanned += 1
            if vessel in needed and t in needed[vessel]:
                retained[vessel][t] = tuple(float(x) if x is not None else math.nan for x in (length,bbox,lon,lat))
    def center(row: tuple) -> bool:
        return math.isfinite(row[2]) and math.isfinite(row[3]) and abs(row[2])<=180 and abs(row[3])<=90
    for vessel,windows in samples.items():
        for t,w in windows.items():
            rows = sorted((hour,row) for hour,row in retained[vessel].items() if t-6<=hour<=t)
            geometry = [r for _,r in rows if math.isfinite(r[0]) and r[0]>=0 and math.isfinite(r[1]) and r[1]>=0]
            lin = [r[1]/r[0] for r in geometry if r[0]>=1]
            activity = [math.log1p(r[0]) for _,r in rows if math.isfinite(r[0]) and r[0]>=0]
            pairs = [distance(a[2],a[3],b[2],b[3]) for (ta,a),(tb,b) in zip(rows,rows[1:]) if tb-ta==1 and center(a) and center(b)]
            mean = lambda x: math.fsum(x)/len(x) if x else math.nan
            movement_equal = (math.isnan(w.movement) and not pairs) or math.isclose(w.movement,mean(pairs),rel_tol=2e-12,abs_tol=2e-6)
            checks.check("raw_sample_window_formula", (w.n_rows,w.n_valid,w.n_lin,w.n_pairs)==(len(rows),len(geometry),len(lin),len(pairs)) and all(close(a,b) for a,b in ((w.lin,mean(lin)),(w.activity,mean(activity)))) and movement_equal, [vessel,t])
    return {"raw_rows_streamed":scanned,"sampled_windows":sum(map(len,samples.values())),"raw_rows_retained":sum(map(len,retained.values()))}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024**2),b""):
            digest.update(chunk)
    return digest.hexdigest()


def self_test() -> None:
    assert midrank(2, [1,2,2,3]) == .5
    assert hour_distance(0,23) == 1 and hour_distance(12,0) == 12
    result = ranks(list(range(20)), [1.0]*20, -6)
    assert result == {"top1": .05, "top10": .5, "chance": .05}, result
    assert ranks(list(range(30)), list(range(30)), 0)["top10"] == 0
    assert ranks(list(range(5)), [1]*5, 0)["top10"] == 1
    assert ranks(list(range(20)), [1]*20, 100)["top1"] == 0
    def window(ts: int, n: int = 7) -> Window:
        return Window(ts, n, 7, 7, 6, .5, 1, 0, 128, 35, True, True, False,
                      tuple([.5]*10), ((),(),()), ((0,0),(0,0),(0,0)), ("","",""))
    current = window(1000)
    historical = sorted([window(1000-24*d) for d in range(1,31)]+[window(1000-23), window(1000-721), window(1000+1)], key=lambda w:w.ts)
    chosen, counts = select_independent(current, historical, [w.ts for w in historical], "TL")
    assert chosen == tuple(1000-24*d for d in range(1,11)) and counts == (30,30), (chosen,counts)
    zero_joint = (1-midrank(0,[0]*10))*midrank(0,[0]*10)
    assert zero_joint == .25  # A positive joint rank is not proof of physical movement.
    print(json.dumps({"self_test": "passed", "scope": "synthetic exact ties, no-hit, <=10 candidates, midrank, circular hour, past bounds, latest10days, joint-zero caveat"}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--sequential-ready", action="store_true", help="Parent confirmed experiment exited; no concurrent dataset operations")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.sequential_ready:
        parser.error("Actual audit requires --sequential-ready after parent's output-ready signal")
    memory = memory_receipt()
    if memory["available_bytes"] < memory["required_available_bytes"]:
        print(json.dumps({"status": "deferred_memory", "memory": memory}))
        return 75
    execution = json.loads((ROOT/"execution.json").read_text(encoding="utf-8"))
    if execution["status"] != "complete" or (ROOT/"experiment.lock").exists():
        raise RuntimeError("Parent experiment is not complete and unlocked")
    checks = Checks()
    for name,receipt in execution["outputs"].items():
        checks.check("output_hash", sha256(ROOT/name)==receipt["sha256"],name)
    checks.check("protocol_hash",sha256(ROOT/"PROTOCOL.md")==execution["protocol_sha256"])
    checks.check("execution_code_hash",sha256(ROOT/"run_experiment.py")==execution["code_sha256"]["run_experiment.py"])
    summary = json.loads((ROOT/"summary.json").read_text(encoding="utf-8"))
    by_vessel: dict[str,list[dict[str,str]]] = {}
    with (ROOT/"event_metrics.csv").open(encoding="utf-8-sig",newline="") as f:
        event_rows = list(csv.DictReader(f))
    for row in event_rows:
        by_vessel.setdefault(row["rfid_id"],[]).append(row)
    with Path(execution["inputs"]["events"]).open(encoding="utf-8-sig",newline="") as f:
        original_events = {int(r["acc_id"]):{k:int(r[k]) for k in ("rfid_id","tier","acc_ts")} for r in csv.DictReader(f)}
    checks.check("fixed_input_event_output_identity",len(original_events)==100 and all(int(r[k])==original_events[int(r["acc_id"])][k] for r in event_rows for k in ("rfid_id","tier","acc_ts")))
    checks.check("event_metric_rows",len(event_rows)==1000 and len({(r["acc_id"],r["rule"]) for r in event_rows})==1000)
    checks.check("event_vessel_count",len(by_vessel)==82)
    computed,coverage,samples = [],{},{}
    def finish(vessel: str, windows: list[Window]) -> None:
        coverage[vessel] = audit_vessel(vessel,windows,checks)
        computed.extend(audit_events(vessel,windows,by_vessel.get(vessel,[]),checks))
        if windows:
            # Fixed quantile indices plus first/last common: no outcome-based sampling.
            indices = {round((len(windows)-1)*i/3) for i in range(4)}
            common = [i for i,w in enumerate(windows) if w.common]
            if common:
                indices.update((common[0],common[len(common)//2],common[-1]))
                lookup = {w.ts:w for w in windows}
                for i in (common[0],common[-1]):
                    for refs in windows[i].refs:
                        if refs:
                            samples.setdefault(int(vessel),{})[refs[0]]=lookup[refs[0]]
            samples.setdefault(int(vessel),{}).update({windows[i].ts:windows[i] for i in indices})
    current_vessel = None
    windows: list[Window] = []
    with (ROOT/"timestamp_scores.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            vessel = row["rfid_id"]
            if vessel != current_vessel:
                if current_vessel is not None:
                    finish(current_vessel,windows)
                checks.check("vessel_contiguous",vessel not in coverage,vessel)
                current_vessel,windows = vessel,[]
            window = Window.parse(row)
            windows.append(window)
            for i,c in enumerate(CONTEXTS):
                checks.check("reference_receipt_fields",int(row[f"{c}_ref_count"])==len(window.refs[i]) and row[f"{c}_reference_max_ts"]==(str(max(window.refs[i])) if window.refs[i] else ""),[vessel,window.ts,c])
            dt = datetime.fromtimestamp(window.ts*3600,tz=timezone.utc)
            checks.check("timestamp_rendering",row["year_month"]==dt.strftime("%Y-%m") and int(row["stored_hour"])==window.ts%24 and row["ts_utc"]==dt.isoformat().replace("+00:00","Z"),[vessel,window.ts])
    if current_vessel is not None:
        finish(current_vessel,windows)
    for vessel in by_vessel.keys()-coverage.keys():
        finish(vessel,[])
    del windows
    checks.check("timestamp_row_total",sum(v["timestamps"] for v in coverage.values())==summary["timestamp_score_rows"])
    audit_summary(summary,computed,checks)
    memory_raw = memory_receipt()
    raw = {"status":"deferred_memory"}
    if memory_raw["available_bytes"] >= memory_raw["required_available_bytes"]:
        checks.check("raw_input_hash",sha256(Path(execution["inputs"]["parquet"]))==execution["input_sha256"]["parquet"])
        checks.check("event_input_hash",sha256(Path(execution["inputs"]["events"]))==execution["input_sha256"]["events"])
        raw = raw_sample_audit(Path(execution["inputs"]["parquet"]),samples,checks)
    receipt = {"status":"passed" if not checks.failures and "sampled_windows" in raw else "failed" if checks.failures else "partial_memory_deferred",
               "created_at_utc":datetime.now(timezone.utc).isoformat(),"reviewer_requested_model":"gpt-6.1-sol","reviewer_requested_effort":"high",
               "provider_model_proof":"unavailable; role/config receipt only", "memory":[memory,memory_raw],
               "script_sha256":sha256(Path(__file__)),"protocol_sha256":sha256(ROOT/"PROTOCOL.md"),
               "checks":checks.counts,"failures":checks.failures,"vessel_coverage":coverage,"raw_sample_audit":raw,
               "scope":"All output refs/ranges/scores/common flags/events/summary/4000 bootstrap; fixed reference-choice and raw-window samples; no implementation imports, training,2025 data,or hardware execution"}
    (ROOT/"audit.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":receipt["status"],"checks":checks.counts,"failures":checks.failures,"raw":raw},ensure_ascii=False))
    return 0 if receipt["status"]=="passed" else 75 if receipt["status"]=="partial_memory_deferred" else 1


if __name__ == "__main__":
    raise SystemExit(main())
