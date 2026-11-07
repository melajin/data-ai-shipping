"""Predict target boats using the selected Round63 checkpoint and fixed policy."""
import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src/vendor')]
from round63.pipeline import predict_to_csv

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features',type=Path,default=ROOT/'data/testA/features.csv')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/testA_predictions.csv')
    parser.add_argument('--device',default='cuda')
    args=parser.parse_args()
    result=predict_to_csv(ROOT,args.features,args.output,args.device)
    print(json.dumps({'testA_boats':len(result),'classes':{str(k):int(v) for k,v in result.iloc[:,1].value_counts().items()},
        'probability_min':float(result.iloc[:,2].min()),'probability_max':float(result.iloc[:,2].max())},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
