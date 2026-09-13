"""Fixed hybrid experiment: geometry proposals plus held-out neural evidence.

Uses the mean of two same-held-out neural runs, not a trained/calibrated
confidence model. Labels are read only after proposals have been filtered.
"""
import json
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.evaluate_predictions import compare


def path_score(path,probability,image):
    path=np.asarray(path,float);arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
    if arc[-1]<5-1e-5:raise ValueError('Need supported 5 mm path')
    samples=np.array([[np.interp(s,arc,path[:,k]) for k in range(3)] for s in np.linspace(2,5,16)])
    indices=np.array([image.TransformPhysicalPointToContinuousIndex(p.tolist()) for p in samples])[:,::-1]
    return float(np.median(ndi.map_coordinates(probability,indices.T,order=1,mode='constant',cval=0)))


def overlapping_seed(a,b):
    """Convergent seed sites, not proof of identical anatomical origins.

    Require each seed centre to lie inside the other's radius estimate.
    Alternative origins remain visible for common-trunk/junction review.
    """
    distance=np.linalg.norm(np.array(a['seed_xyz_mm'])-b['seed_xyz_mm'])
    return distance<min(a['radius_mm'],b['radius_mm'])


def main():
    root=Path('rebuild/hybrid_results');root.mkdir(parents=True,exist_ok=True);rows=[]
    for case in range(19,24):
        a=sitk.ReadImage(str(Path('models/learned_results')/f'held_out_{case}'/'probability.nii.gz'))
        b=sitk.ReadImage(str(Path('models/learned_2000_results')/f'held_out_{case}'/'probability.nii.gz'))
        for attr in ('GetSize','GetOrigin','GetSpacing','GetDirection'):
            if not np.allclose(getattr(a,attr)(),getattr(b,attr)()):raise ValueError('Probability grids differ')
        for folder in ('learned_results','learned_2000_results'):
            manifest=json.loads((Path('models')/folder/'training_manifest.json').read_text())
            fold=next(f for f in manifest['folds'] if f['held_out']==case)
            if case in fold['train']:raise ValueError('Training leakage')
        probability=(sitk.GetArrayFromImage(a)+sitk.GetArrayFromImage(b))/2
        local=json.loads((Path('rebuild/local_daughter_results')/f'case_{case}.json').read_text())
        graph=json.loads((Path('rebuild/daughter_graph_results')/f'subject{case:03d}'/'daughters.json').read_text())
        proposals=[]
        for source,result in [('local',local),('graph',graph)]:
            for pred in result['seed_candidates']:
                if source=='local':r=next(r for r in result['candidate_records'] if r['status']=='seed_candidate' and r['contact_patch']==pred['contact_patch'] and r['trial']==pred['trial'])
                else:r=next(r for r in result['candidate_records'] if r['candidate_id']==pred['candidate_id'])
                proposals.append({**pred,'source':source,'path_xyz_mm':r['path_xyz_mm'],
                                  'neural_distal_score':path_score(r['path_xyz_mm'],probability,a)})
        selected=[]
        for pred in sorted(proposals,key=lambda p:-p['neural_distal_score']):
            if pred['neural_distal_score']<.5:pred['decision']='neural_evidence_below_threshold';continue
            overlapping=next((old for old in selected if overlapping_seed(old,pred)),None)
            if overlapping is not None:
                pred['decision']='convergent_seed_review'
                overlapping.setdefault('alternative_origins_xyz_mm',[]).append(pred['ostium_xyz_mm'])
                overlapping['origin_group_requires_review']=True
                continue
            pred['decision']='provisional_seed_candidate';selected.append(pred)
        for i,pred in enumerate(selected,1):pred['instance_id']=f'branch_{i:03d}'
        result={'seed_candidates':selected,'all_proposals':proposals,'warning':'Experimental hybrid seed proposals; no complete bifurcation assertion.'}
        # No reference used in proposal generation, scoring or duplicate removal.
        ref=json.loads((Path('references/border_results')/f'case_{case}'/'inputs'/'annotations.json').read_text())
        row={'case':case,'proposals':len(proposals),'selected':len(selected),
             'evaluation_3mm':compare({'daughters':selected},ref,3.)}
        (root/f'case_{case}.json').write_text(json.dumps(result,indent=2));rows.append(row)
        print(json.dumps(row),flush=True)
    (root/'summary.json').write_text(json.dumps(rows,indent=2))

if __name__=='__main__':main()
