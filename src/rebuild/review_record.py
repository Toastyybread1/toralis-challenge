"""Versioned machine-readable review records corresponding to the supplied form.

This helper deliberately refuses to overwrite review work. It records evidence,
not a forged accept/edit/exclude decision or anatomical sign-off.
"""
from pathlib import Path
import json
from src.review_validation import MANUAL_BRANCH_CHECKS, MANUAL_CASE_CHECKS, file_fingerprint


def write_review_record(result,ct_path,parent_path,document_path,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a new review version; existing review records are never overwritten')
    branches=[]
    for pred in result['seed_candidates']:
        branches.append({'branch_id':pred['instance_id'],'decision':'unresolved',
            'reviewer':None,'review_date':None,'origin_diameter_mm':pred['origin_diameter_mm'],
            'diameter_method':pred['origin_diameter_method'],'diameter_eligibility':pred['diameter_eligibility'],
            'visible_path_length_mm':pred['path_length_mm'],'distal_point_xyz_mm':pred['path_xyz_mm'][-1],
            'distal_stopping_reason':pred['stop_reason'],'radius_mm':pred['radius_mm'],
            'automatic_checks':pred['automatic_checks'],'flags':pred['review_flags'],
            'direct_origin_review':pred.get('direct_origin_review'),
            'visual_review':{name:'pending' for name in MANUAL_BRANCH_CHECKS},
            'edits_or_unresolved_issue':None})
    record={'record_version':1,'case_disposition':'unresolved',
            'inputs':[file_fingerprint(p) for p in (ct_path,parent_path,document_path)],
            'case_review':{name:'pending' for name in MANUAL_CASE_CHECKS},'branches':branches,
            'overlooked_origins_added':[],'excluded_candidates':[],
            'unresolved_regions':[],'scoring_policy_for_unresolved':None,
            'approved_branch_ids':[],'explicit_scoring_exclusions':None,
            'reviewer_signoff':None,'review_date':None,'release_owner':None,'release_version':None,
            'automatic_rejections':result['rejected_candidates'],
            'deferred_groups':result.get('deferred_groups',[]),
            'early_bifurcation_policy':'unresolved before 5 mm; do not select downstream daughter',
            'boundary_convention':'exposed voxel-cell face of supplied parent; case-24 original loader transformation recorded',
            'geometry_resampling':result['loading'],'code_sha256':result['code_sha256']}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(record,indent=2,allow_nan=False))
    return record


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--document',type=Path,required=True)
    args=parser.parse_args()
    rows=json.loads((args.results/'summary.json').read_text())
    for row in rows:
        case=row['case'];folder=args.results/f'subject{case:03d}'
        source=Path('data/TORALIS CHALLENGE')/folder.name
        write_review_record(json.loads((folder/'predictions.json').read_text()),source/f'orig{case}.nii',
                            source/f'mask{case}.nii',args.document,folder/'review_record.json')
    print(f'{len(rows)} versioned review records written')
