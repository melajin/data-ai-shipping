"""Check schema,IDs,predictions and Test B input status without model fitting."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
from merge_submission import normalize_id,validate_test_b


def validate(path,allow_pending=False):
    from openpyxl import load_workbook
    schema=json.loads((ROOT/'data/template/schema.json').read_text(encoding='utf-8'))
    workbook=load_workbook(path,read_only=True,data_only=True)
    if workbook.sheetnames!=['테스트A','테스트B']:raise ValueError('Expected official 테스트A,테스트B sheet order')
    a=[list(row) for row in workbook.worksheets[0].iter_rows(values_only=True)]
    b=[list(row) for row in workbook.worksheets[1].iter_rows(values_only=True)]
    workbook.close()
    if a[0]!=schema['testA_headers']:raise ValueError('Test A headers differ from the official template')
    if [normalize_id(row[0]) for row in a[1:]]!=schema['testA_ids']:raise ValueError('Test A IDs/order differ')
    classes=['연안복합','자망','통발','채낚기연승낚시']
    for row in a[1:]:
        if row[1] not in classes or not 0<=float(row[2])<=1:raise ValueError('Invalid Test A class/probability')
    if [normalize_id(row[0]) for row in b[1:]]!=schema['testB_ids']:raise ValueError('Test B IDs/order differ')
    pending=all(all(value in (None,'') for value in row[1:]) for row in b[1:])
    if pending and not allow_pending:raise ValueError('Test B is pending;merge the Test B result before final submission')
    if not pending:validate_test_b(b,schema['testB_ids'])
    return {'workbook_valid':True,'testA_boats':len(a)-1,'testB_boats':len(b)-1,
        'testB_pending':pending,'final_submission_ready':not pending}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--allow-pending',action='store_true')
    args=parser.parse_args();print(json.dumps(validate(args.file,args.allow_pending),ensure_ascii=False))
