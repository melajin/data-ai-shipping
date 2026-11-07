"""Export the unchanged Test B candidates and merge them with Test A."""
import csv,json,argparse
from pathlib import Path
from merge_submission import merge
from export_submission import export_pending
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]

def run(candidates,output):
    bridge=ROOT/'outputs/testB_submission.csv'
    with Path(candidates).open(encoding='utf-8-sig',newline='') as source,bridge.open('w',encoding='utf-8-sig',newline='') as target:
        writer=csv.writer(target)
        writer.writerow(['rfid_id','사고시각','이상항적 점수','시각1','시각1 이상항적 점수','시각2','시각2 이상항적 점수','시각3','시각3 이상항적 점수'])
        for row in csv.DictReader(source):
            values=[row['rfid_id'],row['lead_label'],row['score']]
            for offset in [3,2,1]:values.extend([row[f'reference{offset}_label'],row[f'reference{offset}_score']])
            writer.writerow(values)
    with TemporaryDirectory() as temporary:
        base=Path(temporary)/'taskA.xlsx'
        export_pending(ROOT/'outputs/testA_predictions.csv',base)
        return merge(base,bridge,output)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,default=ROOT/'testb_system_20261106/results/reproduction_001/candidates.csv')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/제출결과_최종.xlsx')
    args=parser.parse_args();print(json.dumps(run(args.candidates,args.output),ensure_ascii=False))
