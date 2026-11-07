"""Optional fresh-public neural training replay;does not replace submitted weights."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src/vendor')]
from round63.training import reproduce

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(reproduce(ROOT,args.output),ensure_ascii=False),flush=True)
