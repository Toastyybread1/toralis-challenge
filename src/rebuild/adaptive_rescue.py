"""One bounded second pass over strong rejected flood paths; never uses labels.

No expected daughter count, global threshold changes, inferred anatomy or new
voxels. Multiple starts are algorithmic corroboration, not independent clinical
evidence. Distal split/merge interpretation remains explicitly unresolved.
"""


def strong_local_path(p):
    f=p.get('local_evidence',{});score=p.get('neural_distal_score')
    return (p.get('source')=='local_flood' and bool(p.get('automatic_checks'))
            and all(p['automatic_checks'].values()) and score is not None and score>=.7
            and f.get('supported_sections',0)==5 and f.get('clipped_sections',1)==0
            and f.get('median_contrast_hu') is not None and f['median_contrast_hu']>=200
            and f.get('median_aspect') is not None and f['median_aspect']<=2
            and f.get('radius_ratio') is not None and f['radius_ratio']<=2.5
            and f.get('seed_parent_distance_mm',0)>=4)


def rescue_groups(groups,rejected):
    from src.rebuild.opening_verification import same_opening
    pool=[p for p in rejected if p.get('verification_decision')=='flood_path_requires_review'
          and strong_local_path(p)]
    rescued=[]
    # Among independently agreeing paths prefer stable cross-section width;
    # the general ranking's median centring can favour an offset wall start.
    for p in sorted(pool,key=lambda p:(p['local_evidence']['radius_ratio'],-p['verification_score'])):
        peers=[q for q in pool if q is not p and q.get('flood_patch')==p.get('flood_patch')
               and q.get('flood_trial')!=p.get('flood_trial') and same_opening(p,q)]
        p['adaptive_review']={'trigger':'supported_flood_rejected_by_confidence_gate',
                              'corroborating_candidates':[q['instance_id'] for q in peers],
                              'passes_used':1,'decision':'unresolved'}
        if not peers:continue
        p['adaptive_review']['decision']='provisional_rescue'
        p['verification_decision']='adaptive_supported_flood'
        p['review_flags'].append('adaptive_rescue_requires_direct_origin_and_split_review')
        group=next((g for g in groups if same_opening(g['representative'],p)),None)
        if group is None:
            groups.append({'representative':p,'alternative_candidate_ids':[],
                           'group_status':'adaptive_provisional_opening'})
        else:group['alternative_candidate_ids'].append(p['instance_id'])
        rescued.append(p)
    identities={id(p) for p in rescued}
    return groups,[p for p in rejected if id(p) not in identities],rescued
