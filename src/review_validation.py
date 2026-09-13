"""Machine-checkable subset of the organiser's reference review record.

Passing these checks never approves anatomy or reference completeness. The
expanded components are not per-daughter segmentation masks. Review decisions,
visual confirmations and sign-off stay unset until explicitly recorded.
"""
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy import ndimage as ndi

MANUAL_BRANCH_CHECKS = [
    'continuous_contrast_lumen_in_consecutive_and_orthogonal_views',
    'direct_origin_vs_downstream_branch_and_common_trunk',
    'parent_boundary_imperfections_and_corrections',
    'origin_diameter_and_uncertainty_near_2mm',
    'first_bifurcation_and_distal_stopping_point',
    'lumen_width_no_vein_bone_calcification_or_tissue_spill',
    'per_instance_mask_holes_fragments_overlap_and_seed_support',
    'guide_direction_and_full_segment_mask_coverage',
    'radius_measurement_and_uncertainty',
]
MANUAL_CASE_CHECKS = [
    'itk_snap_alignment_and_label_descriptions_in_three_planes',
    'case_notes_excluded_candidates_and_validation_flags_reviewed',
    'entire_parent_circumference_swept_in_consecutive_slices',
    'nearby_ostia_common_trunks_and_oblique_small_vessels_reviewed',
    'crop_caps_and_terminal_iliac_division_adjudicated',
    'excluded_candidates_adjudicated_and_new_candidates_recorded',
    'image_quality_and_unresolved_scoring_policy_recorded',
    'edited_masks_versioned_with_integer_ids_and_consistent_metadata',
    'saved_masks_reopened_geometry_connectivity_contact_overlap_rechecked',
    'release_scoring_interpretation_owner_and_version_confirmed',
]


def file_fingerprint(path):
    path=Path(path);h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return {'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':h.hexdigest()}


def _sample(image, array, points, order=0):
    indices=np.array([image.TransformPhysicalPointToContinuousIndex([float(v) for v in p])[::-1] for p in points])
    valid=np.all((indices>=0)&(indices<=np.array(array.shape)-1),axis=1)
    values=ndi.map_coordinates(array.astype(np.float32,copy=False),indices.T,order=order,mode='constant',cval=0)
    return values,valid


def branch_checks(branch, detail, context, min_diameter_mm):
    checks={};metrics={}
    def check(name,condition):checks[name]='pass' if bool(condition) else 'fail'
    vectors=[np.asarray(branch.get(k,[]),dtype=float) for k in ['ostium_xyz_mm','seed_xyz_mm','direction_xyz']]
    valid=all(v.shape==(3,) and np.isfinite(v).all() for v in vectors)
    check('finite_physical_landmarks',valid)
    radius=branch.get('radius_mm')
    checks['seed_radius_present_positive_finite']=('unresolved' if radius is None else
        'pass' if np.isfinite(radius) and radius>0 else 'fail')
    if not valid:return checks,metrics
    origin,seed,direction=vectors
    check('parent_identifier',branch.get('parent_instance_id')=='aorta')
    delta=seed-origin
    check('unit_outward_direction',np.isclose(np.linalg.norm(direction),1,atol=1e-5) and np.dot(delta,direction)>0)
    diameter=detail.get('origin_diameter_mm')
    checks['origin_diameter_eligibility']=('unresolved' if diameter is None else
        'pass' if np.isfinite(diameter) and diameter>=min_diameter_mm else 'fail')
    metrics['origin_diameter_mm']=diameter
    metrics['origin_diameter_method']='Area-equivalent diameter on daughter-side perpendicular binary-lumen section'
    metrics['seed_radius_method']='Area-equivalent radius on perpendicular binary-lumen section at 5 mm arc length'
    path=np.asarray(detail.get('path_xyz_mm',[]),dtype=float)
    usable=path.ndim==2 and path.shape[1:]==(3,) and len(path)>=2 and np.isfinite(path).all()
    check('valid_saved_path',usable)
    if not usable:return checks,metrics
    segments=np.linalg.norm(np.diff(path,axis=0),axis=1);arc=np.r_[0,np.cumsum(segments)]
    check('path_starts_at_ostium',np.linalg.norm(path[0]-origin)<=1e-4)
    check('path_length_5_to_10mm',5-1e-5<=arc[-1]<=10+1e-5)
    metrics['path_length_mm']=float(arc[-1]);metrics['distal_point_xyz_mm']=path[-1].tolist()
    metrics['stop_reason']=detail.get('stop_reason')
    if arc[-1]>=5-1e-5 and np.all(segments>0):
        expected=np.array([np.interp(5,arc,path[:,k]) for k in range(3)])
        metrics['seed_arc_interpolation_error_mm']=float(np.linalg.norm(expected-seed))
        check('seed_at_5mm_along_path',metrics['seed_arc_interpolation_error_mm']<=1e-4)
    else:checks['seed_at_5mm_along_path']='fail'
    # A prematurely terminated numerical track is not an established bifurcation.
    check('distal_stop_10mm_or_bifurcation_flag',arc[-1]>=10-1e-5 or detail.get('stop_reason')=='possible_bifurcation')
    if context is None:
        checks['image_support']='unresolved';return checks,metrics
    image,parent,labels=context
    occupancy,in_bounds=_sample(image,parent.astype(np.float32),[origin],order=1)
    metrics['origin_parent_interpolated_occupancy']=float(occupancy[0])
    check('origin_on_half_occupancy_parent_boundary',in_bounds[0] and abs(occupancy[0]-.5)<=.02)
    seed_labels,valid_seed=_sample(image,labels,[seed]);seed_parent,_=_sample(image,parent,[seed])
    check('seed_in_expanded_daughter',valid_seed[0] and seed_labels[0]>0 and seed_parent[0]==0)
    # Skip the voxelized interface band and sample the rest at <=0.25 mm.
    start=min(max(image.GetSpacing()),float(arc[-1]))
    ts=np.linspace(start,arc[-1],max(2,int(np.ceil((arc[-1]-start)/.25))+1))
    samples=np.column_stack([np.interp(ts,arc,path[:,k]) for k in range(3)])
    support,valid_path=_sample(image,labels,samples);parent_support,_=_sample(image,parent,samples)
    check('sampled_path_in_expanded_daughter',valid_path.all() and (support>0).all() and not parent_support.any())
    check('sampled_path_in_same_expansion_component_as_seed',seed_labels[0]>0 and np.all(support==seed_labels[0]))
    metrics['path_support_sampling_step_max_mm']=.25
    metrics['interface_band_omitted_mm']=start
    return checks,metrics


def build_review(prediction,diagnostics,context,min_diameter_mm=2.):
    details={d['instance_id']:d for d in diagnostics.get('branches',[])}
    branches=[]
    for branch in prediction['daughters']:
        checks,metrics=branch_checks(branch,details.get(branch['instance_id'],{}),context,min_diameter_mm)
        branches.append({'instance_id':branch['instance_id'],'decision':'unresolved',
            'reviewer':None,'review_date':None,'edits_or_unresolved_issue':None,
            'automatic_checks':checks,'measurements':metrics,
            'visual_review':{k:'pending' for k in MANUAL_BRANCH_CHECKS}})
    ids=[b['instance_id'] for b in branches]
    failures=sum(v=='fail' for b in branches for v in b['automatic_checks'].values())
    if len(set(ids))!=len(ids):failures+=1
    geometry=None
    if context is not None:
        im,_,_=context
        geometry={'scope':'processing ROI; original inputs preserved and fingerprinted',
                  'size_xyz':list(im.GetSize()),'spacing_xyz_mm':list(im.GetSpacing()),
                  'origin_lps_mm':list(im.GetOrigin()),'direction':list(im.GetDirection())}
    return {'case_id':prediction.get('case_id'),'generated_utc':datetime.now(timezone.utc).isoformat(),
        'record_version':'organizer-review-1','case_disposition':'further edits required' if failures else 'unresolved',
        'automatic_failure_count':failures,'unique_instance_ids':len(set(ids))==len(ids),
        'coordinate_system':'SimpleITK LPS millimetres','geometry':geometry,
        'minimum_origin_diameter_mm':min_diameter_mm,
        'boundary_convention':'0.5 interpolated occupancy of supplied parent mask',
        'early_bifurcation_policy':'Flag unresolved before 5 mm; no invented downstream seed; organiser convention still required',
        'completeness':'not established by automatic detection',
        'per_daughter_segmentation_checks':'unavailable: expansion components are not daughter instance masks',
        'case_review':{k:'pending' for k in MANUAL_CASE_CHECKS},
        'branches':branches,'candidate_decisions':diagnostics.get('candidate_records',[]),
        'overlooked_origins_added':[],'unresolved_regions':[],
        'approved_branch_ids':[],'scoring_exclusions':None,
        'reviewer_sign_off':None,'review_date':None,'release_owner':None,'release_version':None}


def protect_reviewed_output(output):
    """Require a new output name when the existing review has human edits."""
    import json
    review_path=Path(output).with_suffix('.review.json')
    if not review_path.exists():return
    review=json.loads(review_path.read_text())
    edited=bool(review.get('reviewer_sign_off') or review.get('review_date') or
                review.get('approved_branch_ids') or review.get('scoring_exclusions') is not None or
                review.get('overlooked_origins_added') or review.get('unresolved_regions') or
                review.get('release_owner') or review.get('release_version'))
    edited|=any(v!='pending' for v in review.get('case_review',{}).values())
    for b in review.get('branches',[]):
        edited|=bool(b.get('decision','unresolved')!='unresolved' or b.get('reviewer') or
                     b.get('review_date') or b.get('edits_or_unresolved_issue'))
        edited|=any(v!='pending' for v in b.get('visual_review',{}).values())
    if edited:raise ValueError('Existing output has review decisions; choose a new --output version to preserve provenance')
