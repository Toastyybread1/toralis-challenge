"""Bounded reinspection of an already detected, weak-neural opening.

No added group or label access. Dense alternatives must agree with the existing
proximal vessel and pass unchanged boundary, support, CT and arclength checks.
"""
import numpy as np
from src.rebuild.local_flood import flood_proposals
from src.rebuild.opening_verification import opening_context,verify_candidate,quality,same_opening


def eligible_replacement(old,p):
    f=p.get('local_evidence',{});neural=p.get('neural_distal_score')
    return (bool(p.get('automatic_checks')) and all(p['automatic_checks'].values()) and neural is not None
            and neural>=max(.5,old['neural_distal_score']+.02)
            and f.get('supported_sections')==5 and f.get('clipped_sections')==0
            and f.get('radius_ratio',99)<=2.5 and f.get('median_contrast_hu',0)>=200
            and same_opening(old,p)
            and np.linalg.norm(np.array(old['ostium_xyz_mm'])-p['ostium_xyz_mm'])<=old['origin_diameter_mm'])


def review_origins(groups,data,held_out_case=None):
    from src.rebuild.review_pipeline import audit_prediction,score_cpu,same_origin
    flagged=[g for g in groups if g['representative'].get('neural_distal_score') is not None
             and g['representative']['neural_distal_score']<.5
             and g['representative']['local_evidence']['median_contrast_hu']>=200]
    if not flagged:return groups,[],[]
    patches={g['representative']['local_evidence']['opening_patch_26'] for g in flagged}
    proposed,records=flood_proposals(data,max_starts=16,max_targets=8,patch_ids=patches)
    context=opening_context(data);tested=[]
    for p in proposed:
        if any(same_origin(p,q) for q in tested):continue
        p['instance_id']=f'origin_review_{len(tested)+1:04d}'
        p['source']='origin_review';p['selection_reason']='origin_review_rejected'
        p['verification_decision']='origin_review_rejected'
        valid=audit_prediction(p,data);tested.append(p)
        if not valid:continue
        p['local_evidence']=verify_candidate(p,data,context)
    score_cpu([p for p in tested if all(p['automatic_checks'].values())],data,held_out_case)
    for p in tested:
        if 'local_evidence' in p:p['verification_score']=quality(p)
    chosen_ids=set()
    for group in flagged:
        old=group['representative']
        choices=[p for p in tested if p['instance_id'] not in chosen_ids and eligible_replacement(old,p)]
        if not choices:continue
        best=max(choices,key=lambda p:p['neural_distal_score'])
        best['verification_decision']='origin_review_supported';best['selection_reason']='origin_review_supported'
        best['origin_review']={'trigger':'weak_neural_existing_opening_with_strong_CT',
            'previous_representative':old['instance_id'],'origin_shift_mm':float(np.linalg.norm(
                np.array(old['ostium_xyz_mm'])-best['ostium_xyz_mm'])),
            'anatomical_confirmation':'unresolved','passes_used':1}
        best['review_flags'].append('origin_revision_requires_anatomical_review')
        group['alternative_candidate_ids'].append(old['instance_id'])
        group['representative']=best;group['group_status']='origin_refined_provisional_opening'
        chosen_ids.add(best['instance_id'])
    return groups,tested,records
