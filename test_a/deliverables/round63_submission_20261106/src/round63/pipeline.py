"""Shared Test A inference entry for command-line and notebook execution."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from .model import Round63Predictor


def predict_to_csv(root,features_path,output_path,device='cuda'):
    root=Path(root);output_path=Path(output_path)
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    frame=pd.read_csv(features_path,index_col='id')
    template=json.loads((root/'data/template/schema.json').read_text(encoding='utf-8'))
    order=np.asarray(template['testA_ids'],dtype=np.int64)
    if not frame.index.is_unique or set(frame.index)!=set(order):
        raise ValueError('Feature IDs differ from the official Test A target IDs')
    frame=frame.reindex(order)
    predictor=Round63Predictor(root,device)
    prediction,probability=predictor.predict(frame,output_path.parent/'testA_inference')
    headers=template['testA_headers'];classes=np.asarray(predictor.schema['classes'])
    result=pd.DataFrame({headers[0]:[f'{i:08d}' for i in order],headers[1]:classes[prediction],
        headers[2]:probability[np.arange(len(prediction)),prediction]})
    output_path.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(output_path,index=False,encoding='utf-8-sig',float_format='%.12g')
    return result
