"""Inspect one anomalously merged measurement plane; preserve 3D masks and paths.

This subtractive 2D measurement repair is not a new 3D segmentation or anatomical
sign-off. Four neighbouring bounded sections must support a small proximal tube.
"""
import copy
import numpy as np
from src.rebuild.local_flood import flood_proposals
from src.rebuild.opening_verification import opening_context,verify_candidate,path_samples,plane_evidence,same_opening,quality


def flagged(p):
    f=p.get('local_evidence',{});parts=f.get('sections',[])
    bounded=[s for s in parts if s.get('supported') and not s.get('edge')]
    return (p.get('source')=='local_flood' and bool(p.get('automatic_checks')) and all(p['automatic_checks'].values())
            and f.get('supported_sections')==5 and f.get('clipped_sections')==1
            and f.get('seed_parent_distance_mm',0)>=2 and len(bounded)==4
            and np.median([s['radius_mm'] for s in bounded])<=1.6)


def repaired_evidence(p,data):
    if not flagged(p):return None
    old=p['local_evidence'];parts=copy.deepcopy(old['sections'])
    index=next(i for i,s in enumerate(parts) if s['edge'])
    centres,tangents,_=path_samples(p,data['roi'],np.arange(1.,6.))
    repaired=plane_evidence(centres[index],tangents[index],data,neck_opening_mm=.5)
    if not repaired['supported'] or repaired['edge']:return None
    parts[index]=repaired
    radius=[s['radius_mm'] for s in parts];contrast=[s['contrast_hu'] for s in parts]
    hu=[s['lumen_median_hu'] for s in parts]
    if any(x is None for x in contrast+hu):return None
    if (max(radius)/min(radius)>2 or max(radius)>1.6 or min(contrast)<75 or np.median(contrast)<100 or
            max(hu)-min(hu)>100):return None
    f=copy.deepcopy(old);f.update(sections=parts,clipped_sections=0,
        radius_ratio=float(max(radius)/min(radius)),median_contrast_hu=float(np.median(contrast)),
        median_aspect=float(np.median([s['aspect'] for s in parts])),
        median_offcentre_ratio=float(np.median([s['offcentre_ratio'] for s in parts])))
    if f['median_aspect']>2:return None
    return f,index


def review_sections(groups,rejected,data,held_out_case=None):
    from src.rebuild.review_pipeline import audit_prediction,score_cpu,same_origin
    triggers=[p for p in rejected if flagged(p)]
    if not triggers:return groups,[]
    patches={p['flood_patch'] for p in triggers}
    dense,_=flood_proposals(data,max_starts=16,max_targets=8,patch_ids=patches)
    context=opening_context(data);pool=[]
    for original in triggers+dense:
        p=copy.deepcopy(original)
        if any(same_origin(p,q) for q in pool):continue
        if not audit_prediction(p,data):continue
        p['local_evidence']=verify_candidate(p,data,context)
        repair=repaired_evidence(p,data)
        if repair is None:continue
        p['instance_id']=f'section_review_{len(pool)+1:04d}'
        p['original_local_evidence']=copy.deepcopy(p['local_evidence'])
        p['local_evidence'],index=repair
        p['section_review']={'trigger':'one_clipped_section_among_four_small_bounded_sections',
            'section_distance_mm':index+1,'opening_radius_mm':.5,'passes_used':1,
            'scope':'subtractive 2D measurement repair; original 3D masks unchanged',
            'anatomical_confirmation':'unresolved'}
        pool.append(p)
    score_cpu(pool,data,held_out_case)
    for p in pool:
        p['verification_score']=quality(p)
        p['verification_decision']='section_review_rejected';p['selection_reason']='section_review_rejected'
    for p in sorted(pool,key=lambda p:-(p.get('neural_distal_score') or 0)):
        n=p.get('neural_distal_score')
        if n is None or n<.3:continue
        peers=[q for q in pool if q is not p and (q.get('neural_distal_score') or 0)>=.3
               and q['flood_patch']==p['flood_patch'] and q['flood_trial']!=p['flood_trial'] and same_opening(p,q)]
        p['section_review']['corroborating_candidates']=[q['instance_id'] for q in peers]
        if not peers:continue
        p['verification_decision']='section_review_supported';p['selection_reason']='section_review_supported'
        p['review_flags'].append('local_plane_repair_and_direct_origin_require_review')
        group=next((g for g in groups if same_opening(g['representative'],p)),None)
        if group is None:groups.append({'representative':p,'alternative_candidate_ids':[],
                                       'group_status':'section_review_provisional_opening'})
        else:group['alternative_candidate_ids'].append(p['instance_id'])
    return groups,pool
