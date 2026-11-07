"""Recreate the task2-pending workbook from an actual Test A prediction CSV."""
import argparse
import csv
import json
from pathlib import Path
from merge_submission import normalize_id,numeric_score

ROOT=Path(__file__).resolve().parents[1]


def export_pending(test_a,output):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill
    schema=json.loads((ROOT/'data/template/schema.json').read_text(encoding='utf-8'))
    with Path(test_a).open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
    if not rows or rows[0]!=schema['testA_headers']:raise ValueError('Test A CSV headers differ')
    predictions={}
    for row in rows[1:]:
        if len(row)!=3:raise ValueError('Expected3 Test A columns')
        boat=normalize_id(row[0]);probability=numeric_score(row[2])
        if boat in predictions:raise ValueError('Duplicate Test A ID')
        if row[1] not in ['연안복합','자망','통발','채낚기연승낚시'] or not 0<=probability<=1:raise ValueError('Invalid Test A class/probability')
        predictions[boat]=[boat,row[1],probability]
    if set(predictions)!=set(schema['testA_ids']):raise ValueError('Test A target IDs differ')
    workbook=Workbook();a=workbook.active;a.title='테스트A';b=workbook.create_sheet('테스트B')
    a.append(schema['testA_headers']);b.append(schema['testB_headers'])
    for boat in schema['testA_ids']:a.append(predictions[boat])
    for boat in schema['testB_ids']:b.append([boat]+[None]*8)
    for sheet in [a,b]:
        for cell in sheet[1]:cell.font=Font(name='Arial',size=11,bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='52525B')
        sheet.column_dimensions['A'].width=15
        for column in ['B','C','D','E','F','G','H','I']:sheet.column_dimensions[column].width=24
        for row in sheet.iter_rows(min_row=2):row[0].number_format='@'
    for row in a.iter_rows(min_row=2):row[2].number_format='0.000000000000'
    for row in b.iter_rows(min_row=2,min_col=2,max_col=9):
        for cell in row:cell.fill=PatternFill('solid',fgColor='FFF4CF')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);workbook.save(output);workbook.close()
    return {'testA_boats':len(predictions),'testB_pending':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-a',type=Path,default=ROOT/'outputs/testA_predictions.csv')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/round63_submission_20261106/제출결과_과제2대기.xlsx')
    args=parser.parse_args();print(json.dumps(export_pending(args.test_a,args.output),ensure_ascii=False))
