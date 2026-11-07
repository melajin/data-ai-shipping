"""Synthetic-only R11 distance-CDF contract checks and source binding receipt."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODULE_PATH = HERE / "position_rules.py"
CHECK_PATH = Path(__file__).resolve()
R8_PATH = HERE.parent / "round_008_20261106" / "shape_rules.py"


def ram_preflight() -> dict:
    current_pid = os.getpid()
    jobs = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] != current_pid and "python" in (proc.info["name"] or "").lower():
                jobs.append({"pid": proc.info["pid"], "name": proc.info["name"],
                             "cmdline": " ".join(proc.info["cmdline"] or [])[:220]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    available = psutil.virtual_memory().available / 1048576
    fixed_gemini = 512
    other_jobs = 512 * len(jobs)
    required = 768 + fixed_gemini + other_jobs + 640
    out = {"checked_at": dt.datetime.now().astimezone().isoformat(), "available_mib": round(available, 2),
           "luna_synthetic_extra_mib": 768, "gemini_reserve_mib": fixed_gemini,
           "other_python_jobs": jobs, "other_job_reserve_mib": other_jobs, "reserve_mib": 640,
           "required_available_mib": required, "allowed": available >= required,
           "basis": "synthetic fixture only; 768 Luna + 512 Gemini + 640 reserve + 512 per other visible Python job"}
    if not out["allowed"]:
        raise MemoryError(f"RAM preflight failed before pandas/R8 helper import: {out}")
    return out


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def make_fixture(pd):
    rows = []
    ordinal = 0

    def add(rid, t, distance, *, score=0.2, length=80.0, bbox=70.0, raw=True, lon=120.0, lat=35.0):
        nonlocal ordinal
        current_ordinal = ordinal
        ordinal += 1
        rows.append({
            "rfid_id": rid, "ts": int(t), "source_ordinal": current_ordinal,
            "len_m": length, "bbox_m": bbox, "score": score,
            "cen_lon": lon, "cen_lat": lat,
            # Frozen R10 fields; deliberately unrelated ref counts/peer flags
            # prove the new distance histories are recomputed independently.
            "coordinate_valid": True, "own_ref_n": 777, "own_ref_dates": 9,
            "own_distance_eligible": bool(raw),
            "nearest_distance_m": float(distance) if distance is not None else float("nan"),
            "nearest_source_ordinal": max(0, current_ordinal - 1), "nearest_ts": int(t) - 1,
            "nearest_cen_lon": lon, "nearest_cen_lat": lat,
            "peer_eligible_n": 0, "peer_eligible": False,
            "own_status": "keep" if raw else "defer", "own_reason": "r10_fixed",
            "peer_status": "defer", "peer_reason": "r10_fixed",
        })
        return len(rows) - 1

    def add_history(rid, n, *, starts=(0, 240, 480), invalid_first=False, value_fn=None,
                    only_two_dates=False):
        if only_two_dates:
            times = list(range(12)) + list(range(24, 36))
        elif len(starts) == 3 and n % 3 == 0:
            per = n // 3
            times = [base + j for base in starts for j in range(per)]
        else:
            sizes = [n // len(starts) + int(i < n % len(starts)) for i in range(len(starts))]
            times = [base + j for base, size in zip(starts, sizes) for j in range(size)]
        for j, t in enumerate(times):
            distance = float(value_fn(j) if value_fn else j)
            bad = invalid_first and j == 0
            add(rid, t, distance, score=float("nan") if bad else 0.2,
                length=-1.0 if bad else 80.0, bbox=70.0)
        return times

    # V has 24 strict-past distance values. The first is score/geometry-invalid
    # but is raw-distance-available and must remain in the distribution.
    add_history("V", 24, invalid_first=True)
    v_baseline_only = add("V", 719, None, score=0.99, raw=False)
    v_low = add("V", 720, 18.2, score=0.95)
    v_high = add("V", 720, 18.4, score=0.90)
    v_future_nan_score = add("V", 721, 0.0, score=float("nan"))
    v_lowcdf = add("V", 722, 0.0, score=0.10)

    # Five same-gear distance-history peers. P1 has 18.3 to create a peer-CDF
    # difference inside V's exact self-CDF tie; P5 has a longer history to test
    # equal-vessel rather than pooled-row weighting.
    peers = ["P1", "P2", "P3", "P4", "P5"]
    for rid in peers[:4]:
        vals = list(float(x) for x in range(36))
        if rid == "P1":
            vals[18] = 18.3
        times = [base + j for base in (0, 240, 480) for j in range(12)]
        for t, d in zip(times, vals):
            add(rid, t, d, score=float("nan") if t == 0 else 0.2,
                length=-1.0 if t == 0 else 80.0)
    times_p5 = [base + j for base in (0, 240, 480) for j in range(16)]
    for j, t in enumerate(times_p5):
        add("P5", t, float(j), score=0.2)

    # R10 coordinate-history eligibility is true, but only 23 distance values
    # are in the new distribution history; its large R10 counts must not leak in.
    add_history("COORDONLY", 23)
    coordonly = add("COORDONLY", 720, 12.0, score=0.4)

    add_history("TWODATE", 24, only_two_dates=True)
    twodate = add("TWODATE", 720, 12.0, score=0.4)

    add_history("RAWNAN", 24, invalid_first=True)
    rawnan = add("RAWNAN", 720, 12.0, score=float("nan"))

    for rid in ("SINGLE", "UNKNOWN"):
        add_history(rid, 24)
    solo = add("SINGLE", 720, 18.0, score=0.3)
    unknown = add("UNKNOWN", 720, 18.0, score=0.3)

    # Boundary: at t=719, -1 is exactly t-720 and included; at t=720 it is
    # t-721 and excluded. There are 23 other values in [0,720).
    add("BOUND", -1, 100.0)
    add_history("BOUND", 23)
    bound719 = add("BOUND", 719, None, raw=False)
    bound720 = add("BOUND", 720, None, raw=False)

    # Singleton and zero candidate pools exercise the shared budget rule.
    cap1 = add("CAP1", 100, None, score=0.4, raw=False)
    zero = add("ZERO", 100, None, score=float("nan"), raw=False)
    fb = [add("FB", 10, None, score=0.1, raw=False),
          add("FB", 20, None, score=0.9, raw=False),
          add("FB", 30, None, score=0.5, raw=False)]
    missing_flag = add("FLAGFALSE", 720, 2.0, score=0.2, raw=False)
    missing_distance = add("DISTNAN", 720, float("nan"), score=0.2, raw=True)

    # Future row is appended only in the future-invariance assertion.
    future_row = {"rfid_id": "V", "ts": 2000, "source_ordinal": ordinal + 10,
                  "len_m": 80.0, "bbox_m": 70.0, "score": 0.2,
                  "cen_lon": 120.0, "cen_lat": 35.0, "coordinate_valid": True,
                  "own_ref_n": 777, "own_ref_dates": 9, "own_distance_eligible": True,
                  "nearest_distance_m": 400.0, "nearest_source_ordinal": ordinal,
                  "nearest_ts": 1999, "nearest_cen_lon": 120.0, "nearest_cen_lat": 35.0,
                  "peer_eligible_n": 0, "peer_eligible": False,
                  "own_status": "keep", "own_reason": "r10_fixed",
                  "peer_status": "defer", "peer_reason": "r10_fixed",
                  "primary_gear": "G", "is_single_code": True}

    frame = pd.DataFrame(rows)
    registry_rows = [{"rfid_id": "V", "primary_gear": "G", "is_single_code": True}]
    registry_rows.extend({"rfid_id": r, "primary_gear": "G", "is_single_code": True} for r in peers)
    registry_rows.extend([
        {"rfid_id": "COORDONLY", "primary_gear": "CoordOnly", "is_single_code": True},
        {"rfid_id": "TWODATE", "primary_gear": "TwoDate", "is_single_code": True},
        {"rfid_id": "RAWNAN", "primary_gear": "RawNan", "is_single_code": True},
        {"rfid_id": "SINGLE", "primary_gear": "Solo", "is_single_code": True},
        {"rfid_id": "UNKNOWN", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "BOUND", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "CAP1", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "ZERO", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "FB", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "FLAGFALSE", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "DISTNAN", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "REGZERO", "primary_gear": "Unused", "is_single_code": True},
    ])
    registry = pd.DataFrame(registry_rows)
    gearmap = registry.set_index("rfid_id")["primary_gear"].to_dict()
    singlemap = registry.set_index("rfid_id")["is_single_code"].to_dict()
    frame["primary_gear"] = frame.rfid_id.map(gearmap)
    frame["is_single_code"] = frame.rfid_id.map(singlemap).fillna(False).astype(bool)
    ix = {"v_baseline_only": v_baseline_only, "v_low": v_low, "v_high": v_high,
          "v_future_nan_score": v_future_nan_score, "v_lowcdf": v_lowcdf,
          "coordonly": coordonly, "twodate": twodate, "rawnan": rawnan,
          "solo": solo, "unknown": unknown, "bound719": bound719, "bound720": bound720,
          "cap1": cap1, "zero": zero, "fb": fb, "flagfalse": missing_flag,
          "distnan": missing_distance, "future_row": future_row}
    return frame, registry, ix


def main() -> dict:
    ram = ram_preflight()
    pd = importlib.import_module("pandas")
    np = importlib.import_module("numpy")
    module = importlib.import_module("position_rules")
    paths = {"position_rules.py": MODULE_PATH, "check_position_rules.py": CHECK_PATH,
             "shape_rules.py": R8_PATH}
    hashes_before = {name: sha(path) for name, path in paths.items()}
    frame, registry, ix = make_fixture(pd)
    artifacts = module.build_position_rules(frame, registry)
    ledger, preds = artifacts["ledger"], artifacts["predictions"]
    manifest, diagnostics = artifacts["pool_manifest"], artifacts["diagnostics"]
    checks = []

    assert len(ledger) == len(frame) and ledger["source_ordinal"].tolist() == frame["source_ordinal"].tolist()
    r10_cols = ["coordinate_valid", "own_ref_n", "own_ref_dates", "own_distance_eligible",
                "nearest_distance_m", "nearest_source_ordinal", "nearest_ts", "nearest_cen_lon",
                "nearest_cen_lat", "peer_eligible_n", "peer_eligible", "own_status", "own_reason",
                "peer_status", "peer_reason"]
    for col in r10_cols:
        pd.testing.assert_series_equal(ledger[col], frame[col], check_names=False)
    assert len(diagnostics["per_vessel_distance_history"]) == len(registry)
    checks.append("all canonical/R10 rows and coordinate metadata are preserved; per-vessel count inventory includes registry-only zeroes")

    exact_new = ["raw_distance_available", "self_distance_ref_n", "self_distance_ref_dates", "self_distance_cdf",
                 "self_distance_history_eligible", "peer_distance_eligible_n", "peer_distance_cdf_mean",
                 "peer_distance_history_eligible", "s0_ok", "s1_ok", "s2_ok", "s3_ok", "s4_ok",
                 "s0_status", "s0_reason", "s1_status", "s1_reason", "s2_status", "s2_reason",
                 "s3_status", "s3_reason", "s4_status", "s4_reason"]
    assert set(exact_new).issubset(ledger.columns)
    assert list(preds.columns) == ["rfid_id", "method", "rank", "ts", "ordinal", "method_score", "secondary_score",
                                   "legacy_score", "score_kind", "actual_pool_n", "cap", "fallback_reason"]
    assert list(manifest.columns) == ["rfid_id", "method", "pool_stage", "actual_pool_n", "cap", "fallback_reason"]
    assert [s["stage_id"] for s in artifacts["stage_spec"]] == ["s0", "s1", "s2", "s3", "s4"]
    assert set(diagnostics["per_vessel_distance_history"][0]) == {
        "rfid_id", "primary_gear", "observed_n", "raw_distance_available_n",
        "self_distribution_eligible_n", "peer_distribution_eligible_n"}
    checks.append("API keys, exact ledger additions, generic stages, prediction/manifest fields, and independent count field names match the contract")

    vlow, vhigh = ledger.iloc[ix["v_low"]], ledger.iloc[ix["v_high"]]
    assert int(vlow.self_distance_ref_n) == 24 and int(vlow.self_distance_ref_dates) == 3
    assert bool(vlow.raw_distance_available) and bool(vlow.self_distance_history_eligible)
    assert abs(float(vlow.self_distance_cdf) - 19.0 / 24.0) < 1e-15
    assert float(vlow.self_distance_cdf) == float(vhigh.self_distance_cdf)
    assert bool(ledger.iloc[0].raw_distance_available) and not bool(ledger.iloc[0].s0_ok)
    checks.append("24 past DIST values/3 dates pass; raw history includes a NaN-score/invalid-geometry point and exact ties count one-half")

    coord = ledger.iloc[ix["coordonly"]]
    assert bool(coord.own_distance_eligible) and int(coord.own_ref_n) == 777
    assert bool(coord.raw_distance_available) and int(coord.self_distance_ref_n) == 23
    assert int(coord.self_distance_ref_dates) == 3 and bool(coord.s1_ok)
    assert not bool(coord.self_distance_history_eligible) and not bool(coord.s2_ok)
    two = ledger.iloc[ix["twodate"]]
    assert int(two.self_distance_ref_n) == 24 and int(two.self_distance_ref_dates) == 2
    assert not bool(two.self_distance_history_eligible)
    checks.append("R10 coordinate-history counts are not reused: 23 distance values defer, and 24 values on two dates defer")

    bound719, bound720 = ledger.iloc[ix["bound719"]], ledger.iloc[ix["bound720"]]
    assert int(bound719.self_distance_ref_n) == 24 and int(bound719.self_distance_ref_dates) == 4
    assert int(bound720.self_distance_ref_n) == 23 and int(bound720.self_distance_ref_dates) == 3
    assert int(vlow.self_distance_ref_n) == 24  # same-hour candidates and future row are excluded
    checks.append("strict [t-720,t) includes the left boundary, excludes t-721/current/future, and uses source-clock dates")

    rawnan = ledger.iloc[ix["rawnan"]]
    assert bool(rawnan.raw_distance_available) and bool(rawnan.self_distance_history_eligible)
    assert not bool(rawnan.s0_ok) and not bool(rawnan.s2_ok)
    assert abs(float(rawnan.self_distance_cdf) - 12.5 / 24.0) < 1e-15
    assert not bool(ledger.iloc[ix["flagfalse"]].raw_distance_available)
    assert not bool(ledger.iloc[ix["distnan"]].raw_distance_available)
    checks.append("raw distance/history masks are score-independent, while raw distance availability requires R10 flag and finite nonnegative distance")

    assert int(vlow.peer_distance_eligible_n) == 5 and bool(vlow.peer_distance_history_eligible)
    assert not ((ledger.rfid_id.isin(["P1", "P2", "P3", "P4", "P5"])) & ledger.ts.eq(720)).any()
    p1 = 18.0 / 36.0
    p2 = 19.0 / 36.0
    p5 = 19.0 / 48.0
    expected_peer_low = (p1 + 3 * p2 + p5) / 5.0
    expected_peer_high = (4 * p2 + p5) / 5.0
    assert abs(float(vlow.peer_distance_cdf_mean) - expected_peer_low) < 1e-15
    assert abs(float(vhigh.peer_distance_cdf_mean) - expected_peer_high) < 1e-15
    pooled_wrong = (18 + 3 * 19 + 19) / (36 * 4 + 48)
    assert abs(expected_peer_low - pooled_wrong) > 1e-4
    checks.append("five other same-gear DIST histories qualify at the same t without peer current rows; peer CDF is equal-vessel, not pooled")

    solo, unknown = ledger.iloc[ix["solo"]], ledger.iloc[ix["unknown"]]
    assert bool(solo.self_distance_history_eligible) and int(solo.peer_distance_eligible_n) == 0
    assert not bool(solo.s3_ok) and not bool(solo.s4_ok)
    assert bool(unknown.self_distance_history_eligible) and int(unknown.peer_distance_eligible_n) == 0
    assert not bool(unknown.s3_ok) and not bool(unknown.s4_ok)
    checks.append("known singleton and unknown gear defer before distance-peer stage; distance-peer counts exclude self")

    assert ((ledger.s1_ok <= ledger.s0_ok) & (ledger.s2_ok <= ledger.s1_ok) &
            (ledger.s3_ok <= ledger.s2_ok) & (ledger.s4_ok <= ledger.s3_ok)).all()
    checks.append("s0-s4 masks are monotone and all new distance-history availability is separate from R10 flags")

    def winner(method):
        return preds[(preds.rfid_id == "V") & (preds.method == method) & preds["rank"].eq(1)].iloc[0]
    b0, s, g = winner("B0"), winner("S"), winner("G")
    assert int(b0.ts) == 719
    assert int(s.ordinal) == int(frame.iloc[ix["v_low"]].source_ordinal)
    assert int(g.ordinal) == int(frame.iloc[ix["v_high"]].source_ordinal)
    assert float(s.method_score) == float(g.method_score) == 19.0 / 24.0
    assert float(vhigh.peer_distance_cdf_mean) > float(vlow.peer_distance_cdf_mean)
    assert float(g.secondary_score) == float(vhigh.peer_distance_cdf_mean)
    rank_fixture = pd.DataFrame({"self_distance_cdf": [0.9, 0.8], "peer_distance_cdf_mean": [0.1, 0.99],
                                 "score": [0.1, 0.99], "ts": [10, 20], "source_ordinal": [1, 2]})
    assert module._g_rank([0, 1], rank_fixture)[0] == 0
    checks.append("B0/S/G have distinct winners; S uses legacy DESC only after self-CDF, G uses peer CDF only inside an exact self-CDF tie, and self priority beats peer")

    v_manifest = manifest[manifest.rfid_id.eq("V")]
    assert v_manifest.cap.tolist() == [3, 3, 3]
    fb_manifest = manifest[manifest.rfid_id.eq("FB")].set_index("method")
    assert fb_manifest.loc["S", "pool_stage"] == fb_manifest.loc["G", "pool_stage"] == "s0"
    for method in ("B0", "S", "G"):
        scores = preds[(preds.rfid_id == "FB") & (preds.method == method)].sort_values("rank").legacy_score.tolist()
        assert scores == [0.9, 0.5, 0.1]
    for rid, cap in (("CAP1", 1), ("ZERO", 0)):
        assert manifest[manifest.rfid_id.eq(rid)].cap.tolist() == [cap] * 3
    checks.append("shared cap is 3/1/0 for G pool sizes 3/1/0; explicit S/G fallback and legacy DESC order pass")

    base = ledger.copy()
    future = pd.concat([frame, pd.DataFrame([ix["future_row"]])], ignore_index=True)
    extended = module.build_position_rules(future, registry)["ledger"].iloc[:len(frame)]
    compare_cols = ["raw_distance_available", "self_distance_ref_n", "self_distance_ref_dates", "self_distance_cdf",
                    "self_distance_history_eligible", "peer_distance_eligible_n", "peer_distance_cdf_mean",
                    "peer_distance_history_eligible", "s0_ok", "s1_ok", "s2_ok", "s3_ok", "s4_ok"]
    pd.testing.assert_frame_equal(base[compare_cols], extended[compare_cols], check_dtype=False)
    checks.append("appending a future raw distance leaves all prior self/peer CDFs, counts, masks, and stages unchanged")

    dup = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    try:
        module.build_position_rules(dup, registry)
        raise AssertionError("duplicate full key accepted")
    except ValueError:
        pass
    fractional = frame.copy(); fractional["ts"] = fractional.ts.astype(np.float64) + 0.25
    try:
        module.build_position_rules(fractional, registry)
        raise AssertionError("fractional source hour accepted")
    except ValueError:
        pass
    checks.append("duplicate RFID/hour/ordinal and fractional source-clock keys are rejected")

    hashes_after = {name: sha(path) for name, path in paths.items()}
    assert hashes_before == hashes_after
    payload = {
        "status": "passed", "requested_model": "GPT-6 Luna", "requested_effort": "xhigh",
        "check_count": len(checks), "checks": checks, "synthetic_rows": int(len(frame)),
        "synthetic_rfids": int(frame.rfid_id.nunique()), "V_t720_self_cdf": float(vlow.self_distance_cdf),
        "V_t720_peer_cdf_mean_low": float(vlow.peer_distance_cdf_mean),
        "V_t720_peer_cdf_mean_high": float(vhigh.peer_distance_cdf_mean),
        "distinct_winners": {"B0": [int(b0.ts), int(b0.ordinal)], "S": [int(s.ts), int(s.ordinal)],
                             "G": [int(g.ts), int(g.ordinal)]},
        "source_hashes_before": hashes_before, "source_hashes_after": hashes_after,
        "code_hashes_before": {k: hashes_before[k] for k in ("position_rules.py", "check_position_rules.py")},
        "code_hashes_after": {k: hashes_after[k] for k in ("position_rules.py", "check_position_rules.py")},
        "r8_history_sweep_sha256": module.R8_HISTORY_SWEEP_SHA256,
        "ram_preflight": ram,
        "scope": "synthetic-only in-memory rows; no R10 actual ledger, R4 numeric source, events, labels, scores, or model training read",
    }
    (HERE / "rule_checks.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                              encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
