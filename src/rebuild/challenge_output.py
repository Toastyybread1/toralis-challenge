"""Challenge-format automatic predictions, separate from anatomical sign-off."""
import argparse
import json
from pathlib import Path
import numpy as np


def export_case(result,case_id):
    daughters=[];audit=[]
    for group in result['review_groups']:
        p=group['representative'];reason=None
        origin=np.asarray(p.get('ostium_xyz_mm'),float)
        seed=np.asarray(p.get('seed_xyz_mm'),float)
        direction=np.asarray(p.get('direction_xyz'),float)
        path=np.asarray(p.get('path_xyz_mm'),float)
        if any(v.shape!=(3,) or not np.isfinite(v).all() for v in (origin,seed,direction)):
            reason='invalid_physical_geometry'
        elif path.ndim!=2 or path.shape[1]!=3 or len(path)<2 or not np.isfinite(path).all():
            reason='missing_supported_path'
        elif not np.isfinite(p.get('origin_diameter_mm',np.nan)) or p['origin_diameter_mm']<2:
            reason='origin_diameter_below_2mm_or_unknown'
        elif not np.isfinite(p.get('radius_mm',np.nan)) or p['radius_mm']<=0:
            reason='invalid_seed_radius'
        else:
            arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
            if arc[-1]<5-1e-5:reason='path_shorter_than_5mm'
            elif np.linalg.norm(path[0]-origin)>1e-4:reason='path_does_not_start_at_origin'
            else:
                at5=np.array([np.interp(5,arc,path[:,axis]) for axis in range(3)])
                if np.linalg.norm(at5-seed)>.1:reason='seed_not_at_5mm_arc_length'
                elif np.linalg.norm(direction)<1e-8 or np.dot(direction,seed-origin)<=0:
                    reason='invalid_outward_direction'
        entry={'source_candidate':p['instance_id'],'exclusion_reason':reason}
        if reason is None:
            branch=f'branch_{len(daughters)+1:03d}'
            daughters.append(dict(instance_id=branch,parent_instance_id='aorta',
                ostium_xyz_mm=origin.tolist(),seed_xyz_mm=seed.tolist(),
                radius_mm=float(p['radius_mm']),direction_xyz=(direction/np.linalg.norm(direction)).tolist()))
            entry['instance_id']=branch
        audit.append(entry)
    for group in result.get('deferred_groups',[]):
        audit.append({'source_candidate':group['representative']['instance_id'],'exclusion_reason':'deferred_tree_return_connection'})
    return dict(case_id=case_id,parent={'instance_id':'aorta'},daughters=daughters),dict(
        prediction_status='automatic_unvalidated',coordinate_system='SimpleITK LPS mm',
        selection='one representative per retained group, estimated origin diameter >=2mm, supported path and seed at 5mm',
        anatomical_confirmation='pending',candidates=audit)


def write_case(result,case_id,output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    prediction,audit=export_case(result,case_id)
    output.write_text(json.dumps(prediction,indent=2,allow_nan=False))
    evidence=output.parent/'diagnostics';evidence.mkdir(exist_ok=True)
    (evidence/(output.stem+'.json')).write_text(json.dumps(audit,indent=2,allow_nan=False))
    return prediction,audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--aorta-mask',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case-id')
    parser.add_argument('--neural',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--held-out-case',type=int,choices=range(19,24))
    args=parser.parse_args()
    if args.output.resolve() in (args.image.resolve(), args.aorta_mask.resolve()):
        parser.error('Output must not overwrite an input image or mask')
    if args.case_id is not None and not args.case_id.strip():
        parser.error('case-id must not be empty')
    import SimpleITK as sitk
    from src.rebuild.review_pipeline import infer,save_result
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    result,data=infer(args.image,args.aorta_mask,use_neural=args.neural,held_out_case=args.held_out_case)
    # Model/runtime errors must not silently look like successful empty predictions.
    status=result['neural']['status']
    valid_empty=status=='no_proposals' and not result['review_groups']
    if args.neural and status not in ('scored','unsupported_model_spacing') and not valid_empty:
        raise RuntimeError(f"Neural inference unavailable: {result['neural']}")
    case_id=args.case_id or args.image.parent.name
    prediction,_=write_case(result,case_id,args.output)
    save_result(result,data,args.output.parent/(args.output.stem+'_review'))
    print(json.dumps({'output':str(args.output),'daughters':len(prediction['daughters']),
        'status':'automatic predictions; not anatomically approved'}))


if __name__=='__main__':main()
