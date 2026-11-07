"""Default-deny entry point for any future Round003 production run."""
from __future__ import annotations
import argparse

def build_train_references(*, allow_production: bool = False):
    if not allow_production:
        raise RuntimeError("default-deny: separate supervisor approval and RAM gate required")
    raise RuntimeError("production path intentionally unimplemented in this task")


def run_harbor_density_gap_sequentially(*, allow_production: bool = False):
    if not allow_production:
        raise RuntimeError("default-deny: separate supervisor approval and RAM gate required")
    raise RuntimeError("production path intentionally unimplemented in this task")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=("harbor","density","gap"))
    ap.add_argument("--partition", choices=("train",), default="train")
    ap.add_argument("--batch-rows", type=int, default=8192)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--source-manifest", required=True)
    ap.add_argument("--harbor-manifest")
    ap.add_argument("--expected-train-rows", type=int, default=3887069)
    ap.add_argument("--allow-production", action="store_true")
    ap.parse_args()
    raise SystemExit("default-deny: Round003 production builder not implemented; no data read or output written")


if __name__=="__main__":
    main()
