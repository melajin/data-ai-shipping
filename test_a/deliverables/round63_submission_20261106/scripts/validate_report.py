"""Run the deployable14-task pipeline on label-hidden historical query features."""
import json
import os
import sys
from pathlib import Path
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src/vendor')]
import numpy as np
import torch
from sklearn.metrics import f1_score
from round63.model import Round63Predictor

def main():
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    data=np.load(ROOT/'data/reproduction/report_input.npz')
    predictor=Round63Predictor(ROOT)
    # Labels are held outside the inference call.
    prediction,probability=predictor.predict(data['X'],ROOT/'validation/report_inference')
    report=data['split']=='REPORT';tune=data['split']=='TUNE'
    result={'passed':bool(np.array_equal(prediction,data['prediction'])),
        'all_query_boats':len(prediction),'changed_predictions':int((prediction!=data['prediction']).sum()),
        'REPORT_micro_f1':float(f1_score(data['y'][report],prediction[report],average='micro')),
        'TUNE_micro_f1':float(f1_score(data['y'][tune],prediction[tune],average='micro')),
        'normalized_probability_sums':bool(np.allclose(probability.sum(axis=1),1.)),
        'deployed_tasks':14,'training_performed':False}
    scores=np.load(ROOT/'validation/report_inference/final_scores.npy')
    result['maximum_log_score_difference']=float(np.abs(scores-data['scores']).max())
    (ROOT/'validation/report_regression.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    if not result['passed']:raise AssertionError('Predictions differ from the fixed original Round63 result')

if __name__=='__main__':main()
