"""Validate the Test B result and merge it without changing Test A.

Portable input utility. Requires openpyxl only when reading/writing XLSX.
"""
import argparse
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def normalize_id(value):
    if isinstance(value,(int,float)):
        if not math.isfinite(value) or value!=int(value):raise ValueError(f'Invalid rfid_id:{value}')
        value=str(int(value))
    value=str(value).strip()
    if not re.fullmatch(r'\d{8}',value):raise ValueError(f'Expected8-digit rfid_id:{value}')
    return value


def normalize_time(value):
    if isinstance(value,datetime):return value.strftime('%Y%m%d %H')
    text=str(value).strip()
    match=re.fullmatch(r'(\d{8})\s+(\d{1,2})',text)
    if not match:raise ValueError(f'Expected YYYYMMDD HH:{value}')
    return datetime.strptime(f'{match[1]} {int(match[2]):02d}','%Y%m%d %H').strftime('%Y%m%d %H')


def numeric_score(value):
    result=float(value)
    if not math.isfinite(result):raise ValueError('Test B score must be finite')
    return result


def read_rows(path):
    path=Path(path)
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.reader(stream))
    if path.suffix.lower()!='.xlsx':raise ValueError('Test B input must be CSV or XLSX')
    from openpyxl import load_workbook
    workbook=load_workbook(path,read_only=True,data_only=True)
    candidates=[sheet for sheet in workbook if sheet.title.replace(' ','').lower() in ['테스트b','testb','sheet2']]
    sheet=candidates[0] if candidates else workbook.worksheets[0]
    rows=[list(row) for row in sheet.iter_rows(values_only=True)]
    workbook.close();return rows


def validate_test_b(rows,expected_ids):
    if not rows:raise ValueError('Test B result is empty')
    headers=[str(value).strip() if value is not None else '' for value in rows[0]]
    while headers and not headers[-1]:headers.pop()
    if len(headers)<3 or (len(headers)-3)%2:raise ValueError('Test B columns must be id,time,score and time/score pairs')
    if headers[0]!='rfid_id':raise ValueError('First Test B column must be rfid_id')
    result={}
    for raw in rows[1:]:
        if not any(value not in (None,'') for value in raw):continue
        if any(value not in (None,'') for value in raw[len(headers):]):
            raise ValueError('Test B data extends beyond its declared headers')
        row=(list(raw)+[None]*len(headers))[:len(headers)]
        boat=normalize_id(row[0])
        if boat in result:raise ValueError(f'Duplicate Test B boat:{boat}')
        if row[1] in (None,'') or row[2] in (None,''):raise ValueError(f'Missing Test B incident time/score:{boat}')
        cleaned=[boat,normalize_time(row[1]),numeric_score(row[2])]
        for index in range(3,len(headers),2):
            time_value,score=row[index:index+2]
            if time_value in (None,'') and score in (None,''):cleaned.extend([None,None])
            elif time_value in (None,'') or score in (None,''):raise ValueError(f'Incomplete observation time/score pair:{boat}')
            else:cleaned.extend([normalize_time(time_value),numeric_score(score)])
        result[boat]=cleaned
    expected=[normalize_id(value) for value in expected_ids]
    if set(result)!=set(expected):
        raise ValueError(f'Test B ID mismatch;missing={sorted(set(expected)-set(result))},extra={sorted(set(result)-set(expected))}')
    # Header labels match the official order;additional observed time pairs stay.
    standard=['rfid_id','사고시각','이상항적 점수']
    for index in range((len(headers)-3)//2):standard.extend([f'시각{index+1}',f'시각{index+1} 이상항적 점수'])
    return [standard]+[result[boat] for boat in expected]


def merge(base,test_b,output):
    from openpyxl import load_workbook
    schema=json.loads((ROOT/'data/template/schema.json').read_text(encoding='utf-8'))
    b=validate_test_b(read_rows(test_b),schema['testB_ids'])
    workbook=load_workbook(base)
    original_a=list(workbook.worksheets[0].values)
    if [normalize_id(row[0]) for row in original_a[1:]]!=schema['testA_ids']:
        raise ValueError('Base Test A ID order differs from the official template')
    for row in original_a[1:]:
        if row[1] not in ['연안복합','자망','통발','채낚기연승낚시'] or not 0<=float(row[2])<=1:
            raise ValueError('Base Test A class/probability is invalid')
    sheet=workbook.worksheets[1];sheet.delete_rows(1,sheet.max_row)
    for row in b:sheet.append(row)
    from openpyxl.styles import Font,PatternFill
    for cell in sheet[1]:cell.font=Font(name='Arial',bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='52525B')
    for row in sheet.iter_rows(min_row=2):
        row[0].number_format='@'
        for cell in row:cell.fill=PatternFill(fill_type=None)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.resolve()==Path(base).resolve():raise ValueError('Write to a new final file;the task2-pending workbook is preserved')
    workbook.save(output);workbook.close()
    check=load_workbook(output,read_only=True,data_only=True)
    if list(check.worksheets[0].values)!=original_a:raise AssertionError('Test A changed during merge')
    if check.worksheets[1].max_row!=len(schema['testB_ids'])+1:raise AssertionError('Test B row count mismatch')
    check.close()
    result={'complete':True,'testA_unchanged':True,'testA_boats':100,'testB_boats':100,
        'testB_columns':len(b[0]),'testB_source_sha256':hashlib.sha256(Path(test_b).read_bytes()).hexdigest(),
        'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix('.validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=ROOT/'outputs/round63_submission_20261106/제출결과_과제2대기.xlsx')
    parser.add_argument('--test-b',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/제출결과_최종.xlsx')
    args=parser.parse_args()
    print(json.dumps(merge(args.base,args.test_b,args.output),ensure_ascii=False))
