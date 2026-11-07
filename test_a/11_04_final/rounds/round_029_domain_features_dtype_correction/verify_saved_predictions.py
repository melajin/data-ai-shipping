"""Independent arithmetic check of frozen Round029 FIT CV predictions; no fitting."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R25 = HERE.parent / "round_025" / "artifacts" / "gate" / "predictions_baseline.npz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    cm = np.bincount(y * 4 + p, minlength=16).reshape(4, 4)
    tp = np.diag(cm)
    support, predicted = cm.sum(axis=1), cm.sum(axis=0)
    f1 = np.divide(2 * tp, support + predicted,
                   out=np.zeros(4, dtype=float), where=(support + predicted) > 0)
    return {"correct": int(tp.sum()), "micro": float(tp.sum() / len(y)),
            "macro": float(f1.mean()), "tp": tp.tolist(), "f1": f1.tolist(),
            "support": support.tolist(), "predicted": predicted.tolist(),
            "cm": cm.tolist()}


def main() -> None:
    output = HERE / "saved_prediction_verification.json"
    if output.exists():
        raise FileExistsError(output)
    source = HERE / "fit_predictions_frozen.npz"
    reported = json.loads((HERE / "fit_results.json").read_text(encoding="utf-8"))
    with np.load(source, allow_pickle=False) as data:
        y = data["y"].astype(np.int64)
        baseline = data["baseline"].astype(np.int64)
        candidate = data["candidate"].astype(np.int64)
        ids = data["ids"].astype(str)
    with np.load(R25, allow_pickle=False) as data:
        replay = (np.array_equal(data["row_index"], np.arange(len(y)))
                  and np.array_equal(data["y_true"], y)
                  and np.array_equal(data["y_pred"], baseline))
    if len(y) != 3144 or len(set(ids)) != len(ids) or not replay:
        raise ValueError("FIT roster or original baseline replay mismatch")
    base, cand = metrics(y, baseline), metrics(y, candidate)
    for name, actual in (("baseline", base), ("candidate", cand)):
        for key in ("correct", "micro", "macro", "tp", "f1", "cm"):
            if not np.allclose(actual[key], reported[name][key], rtol=0, atol=1e-12):
                raise ValueError(f"reported {name}.{key} differs from frozen predictions")
    base_ok = baseline == y
    cand_ok = candidate == y
    gained = int((~base_ok & cand_ok).sum())
    lost = int((base_ok & ~cand_ok).sum())
    both_correct = int((base_ok & cand_ok).sum())
    both_wrong = int((~base_ok & ~cand_ok).sum())
    assert gained - lost == cand["correct"] - base["correct"]
    result = {
        "scope": "FIT3144 internal 4-fold stored predictions only; no new fit or OUTER read",
        "source_sha256": sha256(source), "original_baseline_exact": bool(replay),
        "baseline": base, "candidate": cand,
        "paired": {"gained": gained, "lost": lost, "both_correct": both_correct,
                   "both_wrong": both_wrong, "net": gained - lost},
        "reported_metrics_match": True,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["paired"], ensure_ascii=False))


if __name__ == "__main__":
    main()
