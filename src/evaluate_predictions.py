"""One-to-one ostium matching against reference JSON in the daughter schema.

Matching tolerance is supplied by the caller, not claimed as organiser policy.
Reference JSON must contain daughters with ostium_xyz_mm; optional seed, radius
and direction fields enable corresponding errors. This does not run inference.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist


def compare(prediction,reference,tolerance_mm):
    if not np.isfinite(tolerance_mm) or tolerance_mm<=0:raise ValueError('Positive tolerance required')
    pred=prediction['daughters'];ref=reference['daughters'];pairs=[]
    if pred and ref:
        distances=cdist([p['ostium_xyz_mm'] for p in pred],[r['ostium_xyz_mm'] for r in ref])
        # Invalid matches cost more than all valid distances together. This
        # maximizes valid match count before minimizing their total distance.
        penalty=(min(len(pred),len(ref))+1)*tolerance_mm
        rows,cols=linear_sum_assignment(np.where(distances<=tolerance_mm,distances,penalty))
        for i,j in zip(rows,cols):
            if distances[i,j]>tolerance_mm:continue
            item={'prediction_index':int(i),'reference_index':int(j),'ostium_error_mm':float(distances[i,j])}
            if ref[j].get('seed_xyz_mm') is not None and pred[i].get('seed_xyz_mm') is not None:item['seed_error_mm']=float(np.linalg.norm(np.array(pred[i]['seed_xyz_mm'])-ref[j]['seed_xyz_mm']))
            if ref[j].get('radius_mm') is not None and pred[i].get('radius_mm') is not None:item['radius_absolute_error_mm']=abs(pred[i]['radius_mm']-ref[j]['radius_mm'])
            if ref[j].get('direction_xyz') is not None and pred[i].get('direction_xyz') is not None:
                a=np.array(pred[i]['direction_xyz']);b=np.array(ref[j]['direction_xyz'])
                item['direction_error_degrees']=float(np.degrees(np.arccos(np.clip(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)),-1,1))))
            pairs.append(item)
    tp=len(pairs);fp=len(pred)-tp;fn=len(ref)-tp
    return {'tp':tp,'fp':fp,'fn':fn,'matches':pairs}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predictions',required=True);p.add_argument('--references',required=True)
    p.add_argument('--tolerance-mm',required=True,type=float);p.add_argument('--output',required=True)
    args=p.parse_args();results={}
    files=sorted(Path(args.references).glob('*.json'))
    if not files:raise ValueError('No reference JSON files found')
    for f in files:
        reference=json.loads(f.read_text());pred_file=Path(args.predictions)/f.name
        if not pred_file.exists():raise ValueError(f'Missing prediction: {pred_file}')
        results[f.stem]=compare(json.loads(pred_file.read_text()),reference,args.tolerance_mm)
    tp=sum(r['tp'] for r in results.values());fp=sum(r['fp'] for r in results.values());fn=sum(r['fn'] for r in results.values())
    metrics={'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,
             'recall':tp/(tp+fn) if tp+fn else None,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
    Path(args.output).write_text(json.dumps({'tolerance_mm':args.tolerance_mm,'metrics':metrics,'cases':results},indent=2,allow_nan=False))
    print(json.dumps(metrics))


if __name__=='__main__':main()
