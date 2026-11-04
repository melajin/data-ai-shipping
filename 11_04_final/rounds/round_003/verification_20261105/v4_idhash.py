"""Independent verification step 4: try to recover the frozen INNER/FIT ID digests
(the round_003 report's limitation #1)."""
import hashlib, itertools, json
from pathlib import Path

PKG = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
ROUND = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_003")
VER = ROUND / "verification_20261105"

rule = json.loads((PKG / "evaluation" / "final_fixed_decision_rule.json").read_text(encoding="utf-8"))
targets = {}
for ch in rule["inner_choices"]:
    targets[("inner", ch["fold"])] = ch["inner_ids_sha256"]
    targets[("fit", ch["fold"])] = ch["fit_ids_sha256"]

splits = json.loads((PKG / "splits" / "splits_original.json").read_text(encoding="utf-8"))
out = {"split_manifest": {}, "fold_keys": sorted({k for f in splits["folds"] for k in f}),
       "recovered": {}, "unrecovered": []}

# split manifest hash
h = hashlib.sha256((PKG / "splits" / "splits_original.json").read_bytes()).hexdigest()
out["split_manifest"] = {"rule_split_manifest_sha256": rule["split_manifest_sha256"],
                         "sha256_of_splits_original_json": h, "match": h == rule["split_manifest_sha256"]}

def variants(ids):
    """ids: list of original values (strings as stored)."""
    s_str = [str(x) for x in ids]
    s_int = [str(int(x)) for x in ids]
    orders = {"orig": s_str, "sorted_str": sorted(s_str), "sorted_int": [str(x) for x in sorted(map(int, s_str))]}
    orders_i = {"orig_int": s_int, "sorted_int_as_int": [str(x) for x in sorted(map(int, s_int))]}
    orders.update(orders_i)
    for oname, seq in orders.items():
        yield oname + "|newline", ("\n".join(seq)).encode()
        yield oname + "|newline+trail", ("\n".join(seq) + "\n").encode()
        yield oname + "|comma", (",".join(seq)).encode()
        yield oname + "|comma+trail", (",".join(seq) + "\n").encode()
        yield oname + "|crlf", ("\r\n".join(seq)).encode()
        yield oname + "|crlf+trail", ("\r\n".join(seq) + "\r\n").encode()
        yield oname + "|space", (" ".join(seq)).encode()
        yield oname + "|json_list", json.dumps(seq).encode()
        yield oname + "|json_list_compact", json.dumps(seq, separators=(",", ":")).encode()
        yield oname + "|json_list_indent2", json.dumps(seq, indent=2).encode()
        yield oname + "|repr", repr(seq).encode()
        yield oname + "|concat", ("".join(seq)).encode()
        ints = [int(x) for x in seq]
        yield oname + "|json_int_list", json.dumps(ints).encode()
        yield oname + "|json_int_compact", json.dumps(ints, separators=(",", ":")).encode()


for fold in (0, 1, 2):
    f = next(x for x in splits["folds"] if x["fold"] == fold)
    for role_key in f:
        if role_key == "fold":
            continue
        ids = f[role_key]
        if not isinstance(ids, list):
            continue
        for name, blob in variants(ids):
            d = hashlib.sha256(blob).hexdigest()
            for (role, fo), target in targets.items():
                if fo == fold and d == target:
                    out["recovered"]["%s/fold%d" % (role, fold)] = {
                        "source": "splits_original.json folds[%d][%s]" % (fold, role_key),
                        "serialization": name, "sha256": d, "n": len(ids)}

# also try the INNER prediction CSV id column order (what round_003 tried)
import pandas as pd
for fold in (0, 1, 2):
    inn = pd.read_csv(PKG / ("evaluation/seed_42/fold_%d/inner_predictions.csv" % fold), encoding="utf-8-sig")
    for name, blob in variants(inn.rfid_id.tolist()):
        d = hashlib.sha256(blob).hexdigest()
        if d == targets[("inner", fold)]:
            out["recovered"].setdefault("inner/fold%d" % fold, {
                "source": "inner_predictions.csv row order", "serialization": name, "sha256": d, "n": len(inn)})

for (role, fold), t in targets.items():
    k = "%s/fold%d" % (role, fold)
    if k not in out["recovered"]:
        out["unrecovered"].append({k: t})

VER.joinpath("v4_idhash.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
