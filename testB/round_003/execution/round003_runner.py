"""Default-deny entry point for any future Round003 production run."""
from __future__ import annotations

def build_train_references(*, allow_production: bool = False):
    if not allow_production:
        raise RuntimeError("default-deny: separate supervisor approval and RAM gate required")
    raise RuntimeError("production path intentionally unimplemented in this task")


def run_harbor_density_gap_sequentially(*, allow_production: bool = False):
    if not allow_production:
        raise RuntimeError("default-deny: separate supervisor approval and RAM gate required")
    raise RuntimeError("production path intentionally unimplemented in this task")
