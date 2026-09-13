"""Local CT verification and opening-based proposal grouping, without labels.

Features are measured along the supported first 5 mm. Neural evidence is a
ranking input; low neural scores alone cannot discard an otherwise strong tube.
Numerical rules are development adaptations, not paper parameters.
"""
import numpy as np
from scipy import ndimage as ndi


def path_samples(pred,image,lengths):
    points=np.array([image.TransformPhysicalPointToContinuousIndex(v) for v in pred['path_xyz_mm']])[:,::-1]
    spacing=np.array(image.GetSpacing())[::-1];points*=spacing
    arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    at=lambda s:np.array([np.interp(s,arc,points[:,k]) for k in range(3)])
    samples=[at(s) for s in lengths]
    tangents=[at(min(arc[-1],s+.75))-at(max(0,s-.75)) for s in lengths]
    return np.array(samples),np.array(tangents),points


def plane_evidence(centre,tangent,data,pixel=.5,half_width=7.,neck_opening_mm=0.):
    tangent=tangent/max(np.linalg.norm(tangent),1e-12)
    basis=np.eye(3)[np.argmin(abs(tangent))];u=np.cross(tangent,basis);u/=np.linalg.norm(u);v=np.cross(tangent,u)
    axis=np.arange(-half_width,half_width+pixel/2,pixel)
    a,b=np.meshgrid(axis,axis,indexing='ij')
    spacing=np.array(data['roi'].GetSpacing())[::-1]
    q=(centre[:,None,None]+u[:,None,None]*a+v[:,None,None]*b)/spacing[:,None,None]
    lo=np.maximum(0,np.floor(q.min(axis=(1,2))).astype(int)-1)
    hi=np.minimum(data['parent'].shape,np.ceil(q.max(axis=(1,2))).astype(int)+2)
    box=tuple(slice(int(a),int(b)) for a,b in zip(lo,hi));local_q=q-lo[:,None,None]
    sample=lambda array,order:ndi.map_coordinates(array[box].astype(np.float32,copy=False),local_q,order=order,mode='constant',cval=0)
    lumen=sample(data['added'],0)>.5;parent=sample(data['parent'],0)>.5
    valid=sample(data['valid_support'],0)>.5;ct=sample(data['ct'],1)
    original_lumen=lumen.copy()
    if neck_opening_mm>0:
        radius=int(np.ceil(neck_opening_mm/pixel));yy,xx=np.mgrid[-radius:radius+1,-radius:radius+1]
        disk=(xx*pixel)**2+(yy*pixel)**2<=neck_opening_mm**2+1e-9
        lumen=ndi.binary_opening(lumen,structure=disk)
    labels,_=ndi.label(lumen);middle=len(axis)//2;identity=labels[middle,middle]
    if identity==0:return {'supported':False}
    part=labels==identity;coords=np.argwhere(part);area=part.sum()*pixel**2;radius=np.sqrt(area/np.pi)
    edge=bool(part[0].any() or part[-1].any() or part[:,0].any() or part[:,-1].any())
    distance=ndi.distance_transform_edt(~part,sampling=pixel)
    ring=(distance>=1)&(distance<=3)&~parent&valid&~original_lumen
    core=part&valid
    contrast=float(np.median(ct[core])-np.median(ct[ring])) if core.any() and ring.sum()>=8 else None
    covariance=np.cov(coords.T*pixel) if len(coords)>2 else np.eye(2)
    eig=np.linalg.eigvalsh(covariance)
    aspect=float(np.sqrt(max(eig[-1],1e-6)/max(eig[0],pixel**2/12)))
    offcentre=float(np.linalg.norm((coords.mean(axis=0)-middle)*pixel)/max(radius,pixel))
    return {'supported':True,'area_mm2':float(area),'radius_mm':float(radius),'edge':edge,
            'aspect':aspect,'offcentre_ratio':offcentre,'contrast_hu':contrast,
            'lumen_median_hu':float(np.median(ct[core])) if core.any() else None}


def opening_context(data):
    contacts=data['added']&ndi.binary_dilation(data['parent'],structure=ndi.generate_binary_structure(3,1))
    # Surface patches can cross differently oriented voxel faces at corners.
    # Keep both connectivities, and require proximal/distal agreement as well.
    labels,_=ndi.label(contacts,structure=ndi.generate_binary_structure(3,1))
    labels26,_=ndi.label(contacts,structure=np.ones((3,3,3)))
    coords=np.argwhere(contacts);spacing=np.array(data['roi'].GetSpacing())[::-1]
    from scipy.spatial import cKDTree
    return labels,labels26,coords,cKDTree(coords*spacing) if len(coords) else None


def verify_candidate(pred,data,context):
    centres,tangents,path=path_samples(pred,data['roi'],np.arange(1.,5.01,1.))
    planes=[plane_evidence(c,t,data) for c,t in zip(centres,tangents)]
    good=[p for p in planes if p['supported']]
    values=lambda key:[p[key] for p in good if p.get(key) is not None]
    spacing=np.array(data['roi'].GetSpacing())[::-1]
    radius=values('radius_mm');contrast=values('contrast_hu')
    seed_distance=float(ndi.map_coordinates(data['distance'],(centres[-1]/spacing)[:,None],order=1)[0])
    labels,labels26,coords,tree=context
    distance,index=tree.query(path[0]) if tree is not None else (np.inf,0)
    opening=int(labels[tuple(coords[index])]) if distance<=max(spacing)*1.5 else None
    result={'sections':planes,'supported_sections':len(good),'opening_patch_6':opening,
            'sampling_mm':float(max(spacing)),
            'opening_patch_26':int(labels26[tuple(coords[index])]) if opening is not None else None,
            'seed_parent_distance_mm':seed_distance,
            'median_contrast_hu':float(np.median(contrast)) if contrast else None,
            'median_aspect':float(np.median(values('aspect'))) if good else None,
            'median_offcentre_ratio':float(np.median(values('offcentre_ratio'))) if good else None,
            'radius_ratio':float(max(radius)/max(min(radius),.25)) if radius else None,
            'clipped_sections':sum(p.get('edge',False) for p in good),
            'straightness':float(np.linalg.norm(centres[-1]-path[0])/5)}
    return result


def quality(pred):
    f=pred['local_evidence']
    # Keep components interpretable; this is a ranking heuristic, not confidence.
    contrast=np.clip((f['median_contrast_hu'] or 0)/100,0,1)
    centring=1-np.clip(f['median_offcentre_ratio'] or 0,0,1)
    tubular=1/ max(f['median_aspect'] or 10,1)
    outward=np.clip(f['seed_parent_distance_mm']/4,0,1)
    neural=pred.get('neural_distal_score',.5)
    return float(.3*contrast+.2*centring+.15*tubular+.15*outward+.2*neural)


def same_opening(a,b):
    fa,fb=a['local_evidence'],b['local_evidence']
    if fa['opening_patch_26'] is None or fb['opening_patch_26'] is None:return False
    origin_distance=np.linalg.norm(np.array(a['ostium_xyz_mm'])-b['ostium_xyz_mm'])
    seed_distance=np.linalg.norm(np.array(a['seed_xyz_mm'])-b['seed_xyz_mm'])
    # Both proximal and distal agreement are needed. Seed convergence alone is
    # not enough to merge two different wall openings.
    origin_width=(a['origin_diameter_mm']+b['origin_diameter_mm'])/2
    # A voxelized opening may split into several surface contact islands. Require
    # overlapping estimated opening footprints AND agreeing distal locations,
    # instead of equating a connected-component ID with an anatomical ostium.
    tolerance=.5*min(fa['sampling_mm'],fb['sampling_mm'])
    def point_path_distance(point,path):
        path=np.asarray(path,float);v=path[1:]-path[:-1]
        t=np.clip(np.sum((np.asarray(point)-path[:-1])*v,axis=1)/np.maximum(np.sum(v*v,axis=1),1e-12),0,1)
        return float(np.min(np.linalg.norm(path[:-1]+t[:,None]*v-point,axis=1)))
    shared_path=max(point_path_distance(a['seed_xyz_mm'],b['path_xyz_mm']),
                    point_path_distance(b['seed_xyz_mm'],a['path_xyz_mm']))<=min(a['radius_mm'],b['radius_mm'])
    return bool(origin_distance<=origin_width+tolerance and shared_path)


def evidence_decision(pred):
    """Select using independent section evidence; never the neural score alone."""
    f=pred['local_evidence']
    bounded=f['supported_sections']>=4 and f['clipped_sections']==0
    shape=f['median_aspect'] is not None and f['median_aspect']<=3 and f['radius_ratio']<=3
    intensity=f['median_contrast_hu'] is not None and f['median_contrast_hu']>=25
    rescue=(bounded and shape and intensity and f['median_contrast_hu']>=100
            and f['seed_parent_distance_mm']>=4 and pred['radius_mm']>=1
            and f['radius_ratio']<=2)
    neural=pred.get('neural_distal_score')
    supported=(neural is not None and neural>=.5) or rescue or neural is None
    if bounded and shape and intensity and supported:
        return 'local_evidence_rescue' if neural is not None and neural<.5 else 'supported_local_tube'
    return 'local_evidence_unresolved'


def select_verified(proposals,data,face_consensus=True):
    context=opening_context(data);eligible=[];rejected=[]
    for pred in proposals:
        if not all(pred['automatic_checks'].values()):
            pred['verification_decision']='invalid_geometry';rejected.append(pred);continue
        f=verify_candidate(pred,data,context);pred['local_evidence']=f;pred['verification_score']=quality(pred)
        # Strong local evidence can rescue a weak neural prediction. A neural
        # score cannot override an unsupported or unbounded proximal section.
        pred['verification_decision']=evidence_decision(pred)
        if pred['verification_decision']!='local_evidence_unresolved':
            eligible.append(pred)
        else:
            rejected.append(pred)
    # New contact-face starts require independent evidence and repeatability.
    # Preserve the established ray/graph candidates, whose selection is unchanged.
    # Different directions must agree on the proximal and distal tube; a lone
    # successful trace near a bright wall is insufficient for this rescue.
    retained=[]
    for pred in eligible:
        if pred.get('source')=='local_flood':
            neural=pred.get('neural_distal_score')
            pred['flood_rescue_requirements']={'neural_minimum':.9,'seed_parent_distance_minimum_mm':4.}
            if neural is None or neural<.9 or pred['local_evidence']['seed_parent_distance_mm']<4.:
                pred['verification_decision']='flood_path_requires_review';rejected.append(pred);continue
        if face_consensus and pred.get('origin_initialization')=='contact_face':
            neural=pred.get('neural_distal_score')
            corroborating=[q for q in eligible if q is not pred and same_opening(pred,q)
                           and (q.get('direction_trial')!=pred.get('direction_trial') or q.get('trial')!=pred.get('trial'))]
            pred['face_consensus_candidate_ids']=[q['instance_id'] for q in corroborating]
            pred['face_rescue_neural_threshold']=.8
            if neural is None or neural<.8 or not corroborating:
                pred['verification_decision']='face_rescue_insufficient_consensus';rejected.append(pred);continue
        retained.append(pred)
    eligible=retained
    groups=[]
    for pred in sorted(eligible,key=lambda p:(p.get('source')=='local_flood',face_consensus and p.get('origin_initialization')=='contact_face',-p['verification_score'])):
        group=next((g for g in groups if same_opening(g['representative'],pred)),None)
        if group is None:groups.append({'representative':pred,'alternative_candidate_ids':[],
                                       'group_status':'provisional_opening'})
        else:
            group['alternative_candidate_ids'].append(pred['instance_id'])
            group['group_status']='overlapping_opening_footprints_requires_review'
    return groups,rejected
