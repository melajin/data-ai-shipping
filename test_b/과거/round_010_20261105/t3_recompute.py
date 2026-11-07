"""Canonical audit entry point. Producer implementations are not imported."""
import sys,runpy
from pathlib import Path
sys.dont_write_bytecode=True
runpy.run_path(str(Path(__file__).resolve().parent/'comparison_20261105'/'t3_recompute.py'),run_name='__main__')
