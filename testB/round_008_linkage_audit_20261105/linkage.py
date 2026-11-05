"""Filter observations before counting vessels; preserve Round 007 cascade policy."""
from __future__ import annotations

CASCADE = [(0, 2.0), (0, 5.0), (1, 2.0), (1, 5.0), (2, 5.0),
           (0, 10.0), (1, 10.0), (3, 5.0), (2, 10.0)]


def candidates(rows, window_h, radius_km, gear=True):
    """One actual representative row per vessel, from inside this condition only."""
    mask = (rows.dt_h <= window_h) & (rows.dist_km <= radius_km)
    if gear:
        mask &= rows.gear_match
    order = ["rfid_id", "dist_km", "dt_h", "row_ts"]
    order += [c for c in ("source_month", "source_row_index") if c in rows]
    return (rows.loc[mask].sort_values(order, kind="stable")
        .drop_duplicates("rfid_id"))


def choose_event(rows):
    chosen, tier, conflict, witness = None, None, False, None
    for i, (w, r) in enumerate(CASCADE):
        selected = candidates(rows, w, r)
        if len(selected) == 1:
            row = selected.iloc[0]
            if chosen is None:
                chosen, tier, witness = int(row.rfid_id), i, row
            elif int(row.rfid_id) != chosen:
                conflict = True
    if chosen is None:
        return None
    return {"rfid_id": chosen, "tier": tier, "cascade_cond": str(CASCADE[tier]),
            "conflict": conflict, "dt_h": float(witness.dt_h),
            "dist_km": float(witness.dist_km), "row_ts": int(witness.row_ts),
            "source_month": int(witness.source_month),
            "source_row_index": int(witness.source_row_index),
            "n_cand_base_gear": len(candidates(rows, 1, 5.0))}
