"""Small independent set/count and original-file preservation checks."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "round_007_20261105"


def main():
    before = json.loads((HERE / "round007_sha256_before.json").read_text(encoding="utf-8"))
    after = {}
    for name in before:
        with (OLD / name).open("rb") as f:
            after[name] = hashlib.file_digest(f, "sha256").hexdigest()
    assert before == after, "Round007 source artifact changed"
    obs = pd.read_csv(HERE / "links_observations.csv")
    old = pd.read_csv(OLD / "links_candidates.csv")
    grid = json.loads((HERE / "links_summary.json").read_text(encoding="utf-8"))["grid"]
    checked = 0
    for w in (0, 1, 2, 3, 6):
        for r in (2, 5, 10, 20):
            for gear in (False, True):
                mask = obs.dt_h.le(w) & obs.dist_km.le(r)
                if gear:
                    mask &= obs.gear_match
                pairs = set(zip(obs.loc[mask, "acc_id"], obs.loc[mask, "rfid_id"]))
                counts = {}
                for event, vessel in pairs:
                    counts[event] = counts.get(event, 0) + 1
                key = f"w{w}_r{r}" + ("_gear" if gear else "")
                assert len(counts) == grid[key]["events_with_candidate"]
                assert sum(n == 1 for n in counts.values()) == grid[key]["events_single_candidate"]
                checked += 1
    # Replay the old erroneous projection from the newly preserved observations.
    replay = (obs.sort_values("row_ts", kind="stable")
              .sort_values(["acc_id", "rfid_id", "dist_km", "dt_h"], kind="stable")
              .drop_duplicates(["acc_id", "rfid_id"]))
    comparison = old.merge(replay, on=["acc_id", "rfid_id"], how="outer", suffixes=("_old", "_replay"), indicator=True)
    assert comparison["_merge"].eq("both").all()
    assert np.allclose(comparison.dist_km_old, comparison.dist_km_replay, atol=1e-9, rtol=0)
    assert comparison.dt_h_old.eq(comparison.dt_h_replay).all()
    assert comparison.gear_match_old.eq(comparison.gear_match_replay).all()
    dev = pd.read_csv(HERE / "devset_positives.csv")
    from linkage import CASCADE
    assert not dev.acc_id.duplicated().any()
    for a in dev.itertuples():
        w, r = CASCADE[a.tier]
        assert a.dt_h <= w and a.dist_km <= r
        witness = obs.loc[obs.acc_id.eq(a.acc_id) & obs.rfid_id.eq(a.rfid_id)
                          & obs.source_month.eq(a.source_month)
                          & obs.source_row_index.eq(a.source_row_index)]
        assert len(witness) == 1 and witness.gear_match.all()
    old_summary = json.loads((OLD / "devset_summary.json").read_text(encoding="utf-8"))
    summary = json.loads((HERE / "devset_summary.json").read_text(encoding="utf-8"))
    assert summary["negative_pool"] == old_summary["negative_pool"]
    neg_before = pd.read_csv(OLD / "devset_negative_sample.csv")
    neg_after = pd.read_csv(HERE / "devset_negative_sample.csv")
    pd.testing.assert_frame_equal(neg_before, neg_after)
    evaluated = json.loads((HERE / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert evaluated["threshold"]["n_pos"] == dev.rfid_id.nunique()
    assert evaluated["threshold"]["n_neg"] == len(neg_after)
    report = {"round007_files_unchanged": len(before), "independent_grid_conditions_checked": checked,
              "legacy_projection_reproduced_event_vessel_pairs": len(comparison),
              "chosen_tier_witnesses_checked": len(dev), "negative_pool_and_sample_unchanged": True,
              "corrected_evaluation_positive_vessels": evaluated["threshold"]["n_pos"],
              "passed": True}
    (HERE / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
