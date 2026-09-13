"""CPU-only proximal daughter proposal and review pipeline.

Tahoces-inspired growth and Riffaud graph traversal are reused, not claimed as
full reproductions. The review document requires expert adjudication; automatic
checks never create an approved reference or silently resolve an early split.
Inference accepts CT and parent only. Reference data enter the batch evaluator
after inference. Existing submission and case-24 loading behaviour are preserved.
"""
import argparse
import copy
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi

from src.daughter_geometry import measure_branch, export_measurement, section, path_lumen_supported
from src.submission import contact_start_points
from src.rebuild.staged_growth import segment_files
from src.rebuild.daughter_graph import detect_daughters


def local_proposals(data, max_trials=8, face_origins=False):
    """Sweep every contact patch; try distinct local directions in each patch.

    A finite sampling of a large merged opening is reported, never described as
    proof of completeness. Only geometrically supported paths become proposals.
    """
    p=data['parent']; lumen=data['added']; image=data['roi']
    spacing=np.array(image.GetSpacing())[::-1]
    contacts=lumen & ndi.binary_dilation(p,structure=ndi.generate_binary_structure(3,1))
    labels,_=ndi.label(lumen,structure=ndi.generate_binary_structure(3,1))
    patches,n=ndi.label(contacts,structure=np.ones((3,3,3)))
    distance=data['distance']
    clearance=ndi.distance_transform_edt(np.pad(p|lumen,1),sampling=spacing)[1:-1,1:-1,1:-1]
    gradients=np.gradient(ndi.gaussian_filter(distance.astype(np.float32),1),*spacing)
    extents=np.array([np.flatnonzero(np.any(p,axis=tuple(b for b in range(3) if b!=a)))[[0,-1]] for a in range(3)])
    long_axis=int(np.argmax((extents[:,1]-extents[:,0])*spacing))
    proposals=[]; audit=[]
    for patch,box in enumerate(ndi.find_objects(patches),1):
        coords=np.argwhere(patches[box]==patch)+np.array([s.start for s in box])
        starts=contact_start_points(coords,clearance,spacing,max_points=max_trials,separation_mm=2.)
        record={'patch':patch,'contact_voxels':len(coords),'starts_tested':len(starts),'attempts':[]}
        audit.append(record)
        for trial,q in enumerate(starts):
            normal=np.array([g[tuple(q)] for g in gradients]); norm=np.linalg.norm(normal)
            if norm<1e-8:continue
            normal/=norm
            if (q[long_axis]<=extents[long_axis,0] or q[long_axis]>=extents[long_axis,1]) and abs(normal[long_axis])>.7:
                record['attempts'].append({'trial':trial,'status':'crop_cap_candidate_excluded'});continue
            pad=np.ceil(5/spacing).astype(int);lo=np.maximum(0,q-pad);hi=np.minimum(p.shape,q+pad+1)
            local_box=tuple(slice(a,b) for a,b in zip(lo,hi))
            local=np.argwhere(labels[local_box]==labels[tuple(q)])+lo
            delta=(local-q)*spacing
            keep=(np.linalg.norm(delta,axis=1)<=5)&(delta@normal>.5)
            if not keep.any():continue
            outgoing=delta[keep]
            mean=np.average(outgoing,axis=0,weights=np.maximum(distance[tuple(local[keep].T)],.1))
            # Two additional directions avoid committing to the centroid of a
            # merged or asymmetric region. No reference coordinates are used.
            _,_,v=np.linalg.svd(outgoing,full_matrices=False)
            principal=v[0] if np.dot(v[0],normal)>=0 else -v[0]
            directions=[(mean,None),(normal,None),(principal,None)]
            # Enumerate the actual parent faces touching this exterior cell.
            # This prevents a backward ray selecting an unrelated wall across
            # a concavity. Keep the ray proposals as auditable alternatives.
            for axis in range(3):
                for sign in (-1,1):
                    neighbour=q.copy();neighbour[axis]+=sign
                    if not face_origins or np.any(neighbour<0) or np.any(neighbour>=p.shape) or not p[tuple(neighbour)]:continue
                    face=q.astype(float);face[axis]+=.5*sign
                    for outgoing_direction in (mean,normal,principal):
                        if outgoing_direction[axis]*sign<0:
                            directions.append((outgoing_direction,face*spacing))
            used=[]
            for direction_id,(direction,face_origin) in enumerate(directions):
                direction=direction/max(np.linalg.norm(direction),1e-12)
                if any(np.dot(direction,d)>.98 and ((o is None and face_origin is None) or
                       (o is not None and face_origin is not None and np.allclose(o,face_origin))) for d,o in used):continue
                used.append((direction,face_origin))
                measurement,reason=measure_branch(p.astype(np.uint8),lumen,q,direction,spacing,
                                                  min_diameter_mm=0.,target_length_mm=5.,strict_geometry=True,origin_local_mm=face_origin)
                if measurement is None:
                    record['attempts'].append({'trial':trial,'direction':direction_id,'status':reason});continue
                extended,extension_reason=measure_branch(p.astype(np.uint8),lumen,q,direction,spacing,
                                                          min_diameter_mm=0.,target_length_mm=10.,strict_geometry=True,origin_local_mm=face_origin)
                if extended is not None:
                    measurement=extended
                else:
                    # A failure after the seed is not evidence that a supported
                    # proximal seed disappeared. Preserve it, with no completed
                    # distal-segment assertion.
                    measurement['tracking_status']='seed_only_distal_unresolved'
                    measurement['stop_reason']='extension_'+str(extension_reason)
                pred,path=export_measurement(measurement,image)
                record['attempts'].append({'trial':trial,'direction':direction_id,'status':'supported_seed'})
                pred.update(source='local',path_xyz_mm=path,origin_diameter_mm=measurement['origin_diameter_mm'],
                            origin_initialization='contact_face' if face_origin is not None else 'backward_ray',
                            origin_measurement_offset_mm=.5,tracking_status=measurement['tracking_status'],
                            stop_reason=measurement['stop_reason'],path_length_mm=measurement['path_length_mm'],
                            contact_patch=patch,trial=trial,direction_trial=direction_id,
                            parent_instance_id='aorta',anatomical_confirmation='pending')
                proposals.append(pred)
    return proposals,{'contact_patches':n,'patches':audit,'whole_surface_search':'all growth contacts enumerated; absent-growth openings can still be missed'}


def same_origin(a,b):
    """Conservative numerical duplicate, not convergent-seed-only suppression.

    Distinct nearby ostia must survive for review even if their paths converge.
    """
    return (np.linalg.norm(np.array(a['ostium_xyz_mm'])-b['ostium_xyz_mm'])<1.0
            and np.linalg.norm(np.array(a['seed_xyz_mm'])-b['seed_xyz_mm'])<1.5
            and np.dot(a['direction_xyz'],b['direction_xyz'])>.8)


def score_cpu(proposals,data,held_out_case=None):
    """Optional existing small-network evidence; CPU only, never final truth.

    Restrict to its native trained spacing. New cases use all five model pairs;
    development cases use only their held-out pair. Models cannot read labels.
    """
    if not proposals:return {'status':'no_proposals'}
    if not np.allclose(data['roi'].GetSpacing(),[1.5]*3,atol=1e-5):
        return {'status':'unsupported_model_spacing','required_spacing_mm':1.5}
    import torch
    from src.rebuild.learned_segmentation import SmallUNet
    from src.rebuild.hybrid_candidates import path_score
    torch.set_num_threads(4)
    folds=[held_out_case] if held_out_case is not None else list(range(19,24))
    paths=[Path('models')/folder/f'held_out_{fold}'/'model.pt'
           for folder in ('learned_results','learned_2000_results') for fold in folds]
    if any(not path.exists() for path in paths):return {'status':'weights_missing'}
    models=[]; provenance=[]
    for path in paths:
        saved=torch.load(path,map_location='cpu',weights_only=True)
        if held_out_case is not None and held_out_case in saved['training_cases']:
            raise ValueError('Held-out case present in training')
        model=SmallUNet().eval();model.load_state_dict(saved['state_dict']);models.append(model)
        provenance.append({'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                           'training_cases':saved['training_cases']})
    image=data['roi']; spacing=np.array(image.GetSpacing())[::-1]
    # Candidate-local crops bound memory independently of full CT size. Even
    # crop starts preserve the pooling grid; all paths receive a 16-voxel halo.
    with torch.inference_mode():
        for pred in proposals:
            indices=np.array([image.TransformPhysicalPointToContinuousIndex(v) for v in pred['path_xyz_mm']])[:,::-1]
            lo=np.maximum(0,np.floor(indices.min(axis=0)).astype(int)-16);lo-=lo%2
            hi=np.minimum(data['parent'].shape,np.ceil(indices.max(axis=0)).astype(int)+18)
            box=tuple(slice(int(a),int(b)) for a,b in zip(lo,hi))
            x=np.stack([np.clip(data['ct'][box],-200,800)/500.,data['parent'][box].astype(float),
                        np.clip(data['distance'][box],0,25)/25]).astype(np.float32)
            tensor=torch.from_numpy(x)[None]
            probability=np.mean([m(tensor).sigmoid()[0,0].numpy() for m in models],axis=0)
            crop=sitk.RegionOfInterest(image,[int(v) for v in (hi-lo)[::-1]],[int(v) for v in lo[::-1]])
            pred['neural_distal_score']=path_score(pred['path_xyz_mm'],probability,crop)
    return {'status':'scored','device':'cpu','models':provenance,
            'warning':'Draft-trained development evidence, not a calibrated probability or reference approval'}


def audit_prediction(pred,data):
    image=data['roi'];spacing=np.array(image.GetSpacing())[::-1]
    points=np.array([image.TransformPhysicalPointToContinuousIndex(v) for v in pred['path_xyz_mm']])[:,::-1]*spacing
    arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    seed=np.array(image.TransformPhysicalPointToContinuousIndex(pred['seed_xyz_mm']))[::-1]*spacing
    expected=np.array([np.interp(5.,arc,points[:,a]) for a in range(3)])
    # Riffaud's origin-relative principal axis within 3r of the primary path.
    # This estimates direction from several physical points, not voxel axes.
    limit=min(arc[-1],3*pred['radius_mm'])
    samples=np.array([[np.interp(s,arc,points[:,a]) for a in range(3)] for s in np.linspace(0,limit,16)])
    _,_,axes=np.linalg.svd(samples-points[0],full_matrices=False)
    axis=axes[0]
    if np.dot(axis,expected-points[0])<0:axis=-axis
    world_direction=np.array(image.GetDirection()).reshape(3,3)@axis[::-1]
    pred['direction_xyz']=(world_direction/np.linalg.norm(world_direction)).tolist()
    pred['direction_method']='origin-relative principal axis over first min(3*seed_radius, path_length) mm; Riffaud-inspired'
    tangent=points[min(len(points)-1,3)]-points[0]
    tangent/=max(np.linalg.norm(tangent),1e-12)
    parts=[s for s in section(data['added'],points[0]+.5*tangent,tangent,spacing) if s['contains_centre'] and not s['edge']]
    diameter=float(2*np.sqrt(parts[0]['area']/np.pi)) if parts else None
    pred['origin_diameter_mm']=diameter
    pred['origin_diameter_method']='equivalent-circle area in perpendicular binary-lumen plane, 0.5 mm distal to boundary'
    pred['origin_measurement_offset_mm']=.5
    # Only nearby faces are needed to verify an origin, keeping this O(1) per
    # candidate instead of comparing with every face on the aorta.
    from src.rebuild.border import border_faces,reference_border_distances
    origin_index=points[0]/spacing
    lo=np.maximum(0,np.floor(origin_index).astype(int)-2)
    hi=np.minimum(data['parent'].shape,lo+6)
    box=tuple(slice(int(a),int(b)) for a,b in zip(lo,hi))
    faces,_,_=border_faces(data['parent'][box])
    faces['face_centres_index_zyx']+=lo
    border_error=reference_border_distances([pred['ostium_xyz_mm']],image,faces)[0]
    pred['origin_boundary_error_mm']=border_error
    # An offset measurement is a proxy, not an exact subvoxel ostial diameter.
    flags=['origin_diameter_proxy_requires_CT_review','terminal_iliac_policy_requires_review',
           'contrast_lumen_identity_requires_CT_review','reference_signoff_pending']
    uncertain=diameter is None or abs(diameter-2.)<=max(spacing)
    if uncertain:flags.append('origin_diameter_unresolved_at_sampling_scale')
    pred['diameter_eligibility']=('unresolved' if uncertain else 'proxy_above_cutoff' if diameter>=2 else 'proxy_below_cutoff')
    if pred['tracking_status']!='length_complete':flags.append('distal_stop_requires_review')
    checks={'path_supported_by_connected_growth':path_lumen_supported(points,spacing,data['added'],data['parent']),
            'origin_on_supplied_boundary':bool(border_error is not None and border_error<1e-3),
            'seed_at_5mm_arc':bool(arc[-1]>=5-1e-5 and np.linalg.norm(seed-expected)<1e-4),
            # The document explicitly requires uncertainty near 2 mm. A
            # one-voxel band is a conservative review rule, not an error bar.
            'origin_measurement_available':diameter is not None,
            'not_clearly_below_diameter_cutoff':bool(diameter is not None and diameter+max(spacing)>=2.),
            'proximal_extent_recorded':bool(arc[-1]<=10+1e-5)}
    pred.update(automatic_checks=checks,review_flags=flags,review_decision='unresolved',
                reviewer=None,review_date=None,path_length_mm=float(arc[-1]))
    return all(checks.values())


def infer(image_path,parent_path,use_neural=False,held_out_case=None,verify_openings=True,face_origins=False,local_flood=True,adaptive_rescue=True,aortic_tree_review=True):
    start=time.perf_counter();data=segment_files(image_path,parent_path)
    times={'load_and_growth_seconds':time.perf_counter()-start}
    generate_faces=face_origins or (use_neural and np.allclose(data['roi'].GetSpacing(),[1.5]*3,atol=1e-5))
    start_stage=time.perf_counter();local,sweep=local_proposals(data,face_origins=generate_faces)
    graph=detect_daughters(data)
    proposals=local
    for pred in graph['seed_candidates']:
        r=next(r for r in graph['candidate_records'] if r['candidate_id']==pred['candidate_id'])
        proposals.append({**pred,'source':'graph','path_xyz_mm':r['path_xyz_mm'],
                          'stop_reason':r['stop_reason'],'path_length_mm':r['path_length_mm']})
    times['geometry_seconds']=time.perf_counter()-start_stage
    flood_records=[]
    if local_flood and use_neural and np.allclose(data['roi'].GetSpacing(),[1.5]*3,atol=1e-5):
        from src.rebuild.local_flood import flood_proposals
        stage=time.perf_counter();flooded,flood_records=flood_proposals(data);proposals+=flooded
        times['local_flood_seconds']=time.perf_counter()-stage
    # Deduplicate before neural inference, retaining all alternative evidence.
    unique=[]
    for pred in sorted(proposals,key=lambda p:(p.get('source')=='local_flood',p.get('origin_initialization')=='contact_face',p['tracking_status']!='length_complete',-p['path_length_mm'])):
        duplicate=next((old for old in unique if same_origin(old,pred)),None)
        if duplicate is not None:
            duplicate.setdefault('alternative_proposals',[]).append(pred);continue
        unique.append(pred)
    start_stage=time.perf_counter()
    to_score=[]
    for pred in unique:
        if pred.get('source')=='local_flood':
            q=np.array(data['roi'].TransformPhysicalPointToContinuousIndex(pred['seed_xyz_mm']))[::-1]
            separation=float(ndi.map_coordinates(data['distance'],q[:,None],order=1)[0])
            if separation<4 or not audit_prediction(pred,data):
                pred['neural_prescreen']='flood_geometry_or_parent_separation_failed';continue
        to_score.append(pred)
    neural=score_cpu(to_score,data,held_out_case) if use_neural else {'status':'disabled'}
    times['neural_seconds']=time.perf_counter()-start_stage
    selected=[];rejected=[]
    for i,pred in enumerate(unique,1):
        pred['instance_id']=f'candidate_{i:04d}'
        geometry_ok=audit_prediction(pred,data)
        if not geometry_ok:pred['selection_reason']='automatic_geometry_check_failed';rejected.append(pred);continue
        if pred.get('neural_distal_score',1.)<.5:
            pred['selection_reason']='weak_neural_evidence';rejected.append(pred);continue
        pred['selection_reason']='provisional_automatic_candidate';selected.append(pred)
    for a in range(len(selected)):
        for b in range(a):
            x,y=selected[a],selected[b]
            if np.linalg.norm(np.array(x['seed_xyz_mm'])-y['seed_xyz_mm'])<min(x['radius_mm'],y['radius_mm']):
                for pred,other in ((x,y),(y,x)):
                    pred.setdefault('overlapping_seed_candidates',[]).append(other['instance_id'])
                    pred['review_flags'].append('separate_ostia_or_common_trunk_unresolved')
    groups=[]
    for pred in sorted(selected,key=lambda p:-p.get('neural_distal_score',0.)):
        group=next((g for g in groups if np.linalg.norm(np.array(g['representative']['seed_xyz_mm'])-pred['seed_xyz_mm'])
                    <min(g['representative']['radius_mm'],pred['radius_mm'])),None)
        if group is None:groups.append({'representative':pred,'alternative_candidate_ids':[],
                                       'group_status':'single_proposal'} )
        else:
            group['alternative_candidate_ids'].append(pred['instance_id'])
            group['group_status']='overlapping_paths_not_confirmed_single_origin'
    origin_review_records=[]
    if verify_openings:
        from src.rebuild.opening_verification import select_verified
        verification_start=time.perf_counter()
        groups,rejected=select_verified(unique,data,face_consensus=not face_origins)
        if adaptive_rescue:
            from src.rebuild.adaptive_rescue import rescue_groups
            groups,rejected,_=rescue_groups(groups,rejected)
            from src.rebuild.origin_review import review_origins
            groups,reviewed,origin_review_records=review_origins(groups,data,held_out_case)
            unique+=reviewed
            rejected.extend(p for p in reviewed if p['verification_decision']!='origin_review_supported')
            from src.rebuild.section_review import review_sections
            groups,section_reviewed=review_sections(groups,rejected,data,held_out_case)
            unique+=section_reviewed
            rejected.extend(p for p in section_reviewed if p['verification_decision']!='section_review_supported')
        selected=[p for p in unique if p.get('verification_decision') in ('supported_local_tube','local_evidence_rescue','adaptive_supported_flood','origin_review_supported','section_review_supported')]
        for pred in unique:
            pred['legacy_selection_reason']=pred['selection_reason']
            pred['selection_reason']=pred.get('verification_decision','invalid_geometry')
        times['opening_verification_seconds']=time.perf_counter()-verification_start
    from src.rebuild.origin_triage import annotate_groups
    stage=time.perf_counter();annotate_groups(groups,data)
    times['origin_triage_seconds']=time.perf_counter()-stage
    pre_tree_groups=copy.deepcopy(groups);deferred_groups=[];tree_context={'status':'disabled'}
    if aortic_tree_review and verify_openings:
        from src.rebuild.aortic_tree_review import review_groups
        stage=time.perf_counter();groups,deferred_groups,tree_context=review_groups(groups,data)
        ids={identity for g in deferred_groups for identity in
             [g['representative']['instance_id'],*g['alternative_candidate_ids']]}
        for pred in selected:
            if pred['instance_id'] in ids:
                pred['pre_tree_selection_reason']=pred['selection_reason']
                pred['selection_reason']='deferred_tree_return_connection'
                pred['review_flags'].append('non_tree_return_connection_requires_adjudication')
                rejected.append(pred)
        selected=[p for p in selected if p['instance_id'] not in ids]
        times['aortic_tree_review_seconds']=time.perf_counter()-stage
    times['inference_seconds']=time.perf_counter()-start
    sources=[Path(__file__),Path('src/daughter_geometry.py'),Path('src/utils.py'),Path('src/rebuild/staged_growth.py'),Path('src/rebuild/daughter_graph.py'),Path('src/rebuild/opening_verification.py'),Path('src/rebuild/origin_refinement.py'),Path('src/rebuild/local_flood.py')]
    provenance={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    provenance['src/rebuild/adaptive_rescue.py']=hashlib.sha256(Path('src/rebuild/adaptive_rescue.py').read_bytes()).hexdigest()
    provenance['src/rebuild/origin_review.py']=hashlib.sha256(Path('src/rebuild/origin_review.py').read_bytes()).hexdigest()
    provenance['src/rebuild/section_review.py']=hashlib.sha256(Path('src/rebuild/section_review.py').read_bytes()).hexdigest()
    provenance['src/rebuild/origin_triage.py']=hashlib.sha256(Path('src/rebuild/origin_triage.py').read_bytes()).hexdigest()
    provenance['src/rebuild/aortic_tree_review.py']=hashlib.sha256(Path('src/rebuild/aortic_tree_review.py').read_bytes()).hexdigest()
    return {'schema_version':1,'coordinate_system':'SimpleITK LPS mm','daughters':[],
            'code_sha256':provenance,
            'opening_verification_enabled':verify_openings,
            'experimental_face_origins_enabled':face_origins,
            'face_rescue_policy':'unrestricted_experiment' if face_origins else 'CT_verified_direction_consensus_and_neural_at_least_0.8',
            'face_starts_generated':bool(generate_faces),
            'local_flood_enabled':local_flood,'local_flood_records':flood_records,
            'adaptive_rescue_enabled':adaptive_rescue,
            'origin_review_records':origin_review_records,
            'aortic_tree_review_enabled':bool(aortic_tree_review and verify_openings),
            'aortic_tree_context':tree_context,'pre_tree_review_groups':pre_tree_groups,
            'deferred_groups':deferred_groups,
            'seed_candidates':selected,'review_groups':groups,'rejected_candidates':rejected,'surface_sweep':sweep,
            'graph_status_counts':graph['status_counts'],'graph_candidate_records':graph['candidate_records'],
            'loading':data['loading'],'neural':neural,'timing':times,
            'reference_status':'No automatically approved references or anatomically confirmed daughters',
            'completeness':'unresolved; threshold growth and finite contact sampling can miss origins'},data


def save_result(result,data,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for name,array in [('parent',data['parent']),('growth',data['added']),('valid_support',data['valid_support'])]:
        image=sitk.GetImageFromArray(array.astype(np.uint8));image.CopyInformation(data['roi'])
        sitk.WriteImage(image,str(output/f'{name}.nii.gz'))
    (output/'predictions.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    lines=['# Provisional branch review record','',
           'Case disposition: unresolved. No reviewer sign-off has been generated.',
           'Masks are cropped analysis volumes in original physical coordinates; the supplied input is not edited.',
           'Review original CT, parent, case notes and draft labels in all three planes.',
           '','| Candidate | Origin diameter proxy (mm) | Path (mm) | Stop | Decision |',
           '|---|---:|---:|---|---|']
    for pred in result['seed_candidates']:
        d=pred['origin_diameter_mm'];lines.append(f"| {pred['instance_id']} | {d:.2f} | {pred['path_length_mm']:.2f} | {pred['stop_reason']} | unresolved |")
    for group in result.get('deferred_groups',[]):
        pred=group['representative'];lines.append(f"| {pred['instance_id']} | {pred['origin_diameter_mm']:.2f} | {pred['path_length_mm']:.2f} | reconnects to aortic backbone | deferred; anatomical review required |")
    lines+=['','For every candidate: verify contrast-filled connection, direct origin, separate ostia/common trunk,',
            'origin diameter, 5 mm seed, first bifurcation, width, spill and overlap. Preserve null measurements.',
            'Sweep the entire circumference for missing branches; exclude crop caps and the terminal iliac division.',
            'Record uncertainty for early splits and coarse sampling. Save edits as a new version, reopen and validate.',
            'Reviewer: ______ Date: ______ Approved/excluded IDs: ______',
            '','Machine evidence and all rejected candidates are retained in predictions.json.']
    (output/'REVIEW.md').write_text('\n'.join(lines))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--parent',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--neural',action='store_true')
    parser.add_argument('--legacy-selection',action='store_true',help='Reproduce previous neural cutoff and seed-overlap grouping')
    parser.add_argument('--aortic-tree-review',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--experimental-face-origins',action='store_true',help='Additional exact contact-face starts; development ablation increased false detections')
    args=parser.parse_args();sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    start=time.perf_counter();result,data=infer(args.image,args.parent,args.neural,verify_openings=not args.legacy_selection,
                                             face_origins=args.experimental_face_origins,aortic_tree_review=args.aortic_tree_review)
    save_result(result,data,args.output)
    print(json.dumps({'provisional_candidates':len(result['seed_candidates']),
                      'elapsed_including_output_seconds':time.perf_counter()-start,**result['timing']}))


if __name__=='__main__':main()
