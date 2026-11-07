"""Build label-free Test A features from the supplied target CSV directory."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src/vendor')]
from round63.features import build_features

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'data/testA/features.csv')
    parser.add_argument('--ids',type=Path,default=ROOT/'data/template/schema.json')
    args=parser.parse_args()
    targets=json.loads(args.ids.read_text(encoding='utf-8'))['testA_ids']
    schema=json.loads((ROOT/'model/feature_schema.json').read_text(encoding='utf-8'))
    build_features(args.input,targets,schema,args.output)

if __name__=='__main__':main()
