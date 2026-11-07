from __future__ import annotations

"""Build fold-local sparse FIT-only Bhattacharyya features for SELECT or OUTER."""
import argparse
import csv
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RESOLUTIONS = (0.01, 0.05)
CLASSES = (0, 1, 2, 3)
FEATURES = tuple(f"spatial_bhat_r{int(round(res * 100)):03d}_c{c}" for res in RESOLUTIONS for c in CLASSES)
EXPECTED_SPATIAL_PARQUET_SHA256 = "b732e2d87f795885426abbc805381e29bcad466e8be7abf37fc4c361bd853131"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_profiles(path: Path) -> dict[float, dict[str, dict[str, float]]]:
    profiles: dict[float, dict[str, dict[str, float]]] = {r: {} for r in RESOLUTIONS}
    sums: dict[tuple[float, str], float] = defaultdict(float)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != ("id", "res", "cell", "weight"):
            raise ValueError(f"Unexpected filtered profile schema: {reader.fieldnames}")
        for row in reader:
            vessel = row["id"]
            res = float(row["res"])
            cell = row["cell"]
            weight = float(row["weight"])
            if not vessel or res not in RESOLUTIONS or not cell or not math.isfinite(weight) or weight < 0:
                raise ValueError(f"Invalid filtered profile row: {row}")
            by_vessel = profiles[res].setdefault(vessel, {})
            if cell in by_vessel:
                raise ValueError(f"Duplicate cell for id/res: {vessel}/{res}/{cell}")
            by_vessel[cell] = weight
            sums[(res, vessel)] += weight
    for (res, vessel), total in sums.items():
        if not math.isfinite(total) or abs(total - 1.0) > 1e-12:
            raise ValueError(f"Filtered profile weights are not normalized: {vessel}/{res}={total}")
    return profiles


def assert_ready_fit_records(paths: tuple[Path, Path]) -> dict:
    rows = []
    for path, expected in zip(paths, ("baseline_12_fit_reloaded_select_only", "candidate_20_fit_reloaded_select_only")):
        if not path.is_file():
            raise FileNotFoundError(f"OUTER feature build requires fit artifact: {path}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != expected or record.get("fits", {}).get("meta_fits") != 3:
            raise PermissionError(f"OUTER feature build requires three frozen/reloaded models: {path}")
        if not record.get("fit_records") or len(record["fit_records"]) != 3 or not all(x.get("reload_check_pass") for x in record["fit_records"]):
            raise PermissionError(f"OUTER feature build found an incomplete model reload record: {path}")
        rows.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    return {"baseline_fit_sha256": rows[0]["sha256"], "candidate_fit_sha256": rows[1]["sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--profile-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--role", choices=("INNER_SELECT", "OUTER"), required=True)
    parser.add_argument("--select-roster", type=Path)
    parser.add_argument("--baseline-fit", type=Path)
    parser.add_argument("--candidate-fit", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("Spatial feature output must remain inside the Round021 workspace") from exc
    started = time.perf_counter()
    profile_path = args.profiles.resolve()
    profile_manifest = json.loads(args.profile_manifest.resolve().read_text(encoding="utf-8"))
    if profile_manifest.get("source_sha256", "").lower() != EXPECTED_SPATIAL_PARQUET_SHA256:
        raise ValueError("Filtered profile manifest is not bound to the frozen spatial parquet source")
    if sha256_file(profile_path) != profile_manifest.get("output_sha256"):
        raise ValueError("Filtered profile CSV differs from its extraction manifest")
    fit_proof = None
    if args.role == "OUTER":
        if args.baseline_fit is None or args.candidate_fit is None:
            raise PermissionError("OUTER feature build requires explicit baseline and candidate reloaded-fit artifacts")
        fit_proof = assert_ready_fit_records((args.baseline_fit.resolve(), args.candidate_fit.resolve()))
    select_ids_by_fold: dict[int, list[str]] = {f: [] for f in range(3)}
    select_labels_by_fold: dict[int, dict[str, int]] = {f: {} for f in range(3)}
    if args.role == "INNER_SELECT":
        if args.select_roster is None:
            raise ValueError("INNER_SELECT feature construction requires the frozen round002 inner split roster")
        with args.select_roster.resolve().open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != ("fold", "role", "rfid_id", "y_true"):
                raise ValueError(f"Unexpected SELECT roster schema: {reader.fieldnames}")
            for row in reader:
                if row["role"] == "INNER_SELECT":
                    fold = int(row["fold"])
                    if fold not in select_ids_by_fold:
                        raise ValueError(f"Invalid SELECT roster fold: {fold}")
                    vessel = row["rfid_id"]
                    if vessel in select_labels_by_fold[fold]:
                        raise ValueError(f"Duplicate SELECT roster ID: {fold}/{vessel}")
                    select_ids_by_fold[fold].append(vessel)
                    select_labels_by_fold[fold][vessel] = int(row["y_true"])

    profiles = load_profiles(profile_path)
    out_rows = []
    audits = {}
    for fold in range(3):
        feature_file = args.feature_root.resolve() / f"fold_{fold}_features.npz"
        with np.load(feature_file, allow_pickle=False) as z:
            ids = z["rfid_ids"].astype(str)
            y = z["y"].astype(np.int64)
            roles = z["roles"].astype(str)
        if len(ids) != 5897 or len(set(ids.tolist())) != 5897 or not (len(ids) == len(y) == len(roles)):
            raise ValueError(f"Fold {fold} metadata dimensions are invalid")
        if set(np.unique(roles).tolist()) != {"FIT", "INNER", "OUTER"}:
            raise ValueError(f"Fold {fold} has unexpected role values")
        fit_mask = roles == "FIT"
        query_mask = roles == args.role if args.role == "OUTER" else np.zeros(len(roles), dtype=bool)
        fit_ids = ids[fit_mask].tolist()
        query_ids = ids[query_mask].tolist() if args.role == "OUTER" else list(select_ids_by_fold[fold])
        fit_y = y[fit_mask]
        if len(set(fit_ids) & set(query_ids)):
            raise ValueError(f"FIT/query overlap at fold={fold}")
        if args.role == "INNER_SELECT":
            expected_inner = set(ids[roles == "INNER"].tolist())
            index = {v: i for i, v in enumerate(ids.tolist())}
            if len(query_ids) != 394 or not set(query_ids).issubset(expected_inner):
                raise ValueError(f"Expected 394 roster IDs contained in INNER at fold={fold}")
            if set(select_labels_by_fold[fold]) != set(query_ids):
                raise ValueError(f"SELECT roster label inventory mismatch fold={fold}")
            if any(int(y[index[v]]) != select_labels_by_fold[fold][v] for v in query_ids):
                raise ValueError(f"SELECT roster labels mismatch source cache fold={fold}")
        if args.role == "OUTER" and len(query_ids) != (1966 if fold < 2 else 1965):
            raise ValueError(f"Unexpected OUTER query count at fold={fold}")
        prototypes: dict[tuple[float, int], dict[str, float]] = {}
        profile_support: dict[str, int] = {}
        for res in RESOLUTIONS:
            for cls in CLASSES:
                sums: dict[str, float] = defaultdict(float)
                members = [v for v, label in zip(fit_ids, fit_y.tolist()) if label == cls and v in profiles[res]]
                if members:
                    for vessel in members:
                        for cell, weight in profiles[res][vessel].items():
                            sums[cell] += weight / len(members)
                    total = math.fsum(sums.values())
                    if total <= 0 or not math.isfinite(total):
                        raise ValueError(f"Invalid class prototype fold={fold}/{res}/{cls}")
                    prototypes[(res, cls)] = {cell: value / total for cell, value in sums.items()}
                else:
                    prototypes[(res, cls)] = {}
                profile_support[f"r{res:.2f}_c{cls}"] = len(members)
        missing = 0
        for vessel in query_ids:
            values = []
            for res in RESOLUTIONS:
                p = profiles[res].get(vessel)
                for cls in CLASSES:
                    q = prototypes[(res, cls)]
                    if p is None or not q:
                        values.append(float("nan"))
                    else:
                        values.append(math.fsum(math.sqrt(max(0.0, weight * q.get(cell, 0.0))) for cell, weight in p.items()))
            if not all(math.isnan(v) or (math.isfinite(v) and -1e-12 <= v <= 1.0 + 1e-12) for v in values):
                raise ValueError(f"Bhattacharyya coefficient out of range: fold={fold} id={vessel}")
            if any(math.isnan(v) for v in values):
                missing += 1
            out_rows.append({"id": vessel, "year": 2026, "fold": fold, "role": args.role,
                             **{name: value for name, value in zip(FEATURES, values)}})
        audits[str(fold)] = {"fit_rows": len(fit_ids), "query_rows": len(query_ids),
                             "query_profile_missing_rows": missing, "fit_profiles_by_resolution_class": profile_support,
                             "fit_query_disjoint": True, "query_labels_used_for_features": False,
                             "prototype_construction": "equal-vessel mean of normalized FIT profiles, class-specific and resolution-specific"}

    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ("id", "year", "fold", "role", *FEATURES)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in out_rows:
            writer.writerow({k: ("" if isinstance(row[k], float) and math.isnan(row[k]) else row[k]) for k in columns})
    meta = {"status": f"{args.role.lower()}_spatial_features_written", "role": args.role,
            "columns": list(FEATURES), "rows": len(out_rows), "folds": audits,
            "profile_csv_sha256": sha256_file(profile_path), "output_sha256": sha256_file(output),
            "output_bytes": output.stat().st_size, "fit_artifact_proof": fit_proof,
            "query_labels_used_for_features": False, "elapsed_seconds": time.perf_counter() - started,
            "imputation": "NaN is intentionally preserved for downstream constant-zero imputer; no missingness indicators"}
    output.with_suffix(output.suffix + ".manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
