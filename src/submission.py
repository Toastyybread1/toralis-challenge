"""CPU submission baseline: controlled expansion, proximal geometry, JSON.

Every cutoff is an explicit adaptation. Predictions remain unvalidated against
expert references; sidecar diagnostics preserve rejection and ambiguity reasons.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from time import perf_counter
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.expansion import fit_intensity_model, bounded_expansion, local_leakage_block
from src.daughter_geometry import measure_branch, export_measurement
from src.utils import read_nifti_pair


def contact_start_points(coords, clearance, spacing_zyx, max_points=8, separation_mm=2.):
    """Try thick contact sites first, then spatially distinct alternatives.

    Deterministic metric nonmaximum suppression bounds tracking work per patch.
    These are initialization trials, not separate daughter instances.
    """
    values=clearance[tuple(coords.T)]
    order=np.argsort(-values,kind='stable')
    chosen=[]
    for index in order:
        point=coords[index]
        if all(np.linalg.norm((point-old)*spacing_zyx)>=separation_mm for old in chosen):
            chosen.append(point)
            if len(chosen)>=max_points:break
    return chosen


def detect(image,mask,min_diameter_mm=2.,density_ratio=.6,audit=None,leakage_mode="whole_component",contact_mode="single",target_length_mm=10.):
    if target_length_mm not in (5.,10.):raise ValueError('Target length must be 5 or 10 mm')
    if contact_mode not in ('single','fallback'):raise ValueError('Unknown contact mode')
    if leakage_mode not in ('whole_component','local_bulk'):raise ValueError('Unknown leakage mode')
    if image.GetDimension()!=3 or mask.GetDimension()!=3:raise ValueError('Expected 3D inputs')
    for getter in ('GetSize','GetSpacing','GetOrigin','GetDirection'):
        if not np.allclose(getattr(image,getter)(),getattr(mask,getter)(),rtol=0,atol=1e-5):
            raise ValueError(f'Input geometry mismatch: {getter}')
    full=sitk.GetArrayViewFromImage(mask)!=0
    if not full.any():return [],{'warning':'empty_parent','rejections':{}},None
    spacing=np.array(image.GetSpacing())[::-1]
    bounds=[]
    for axis in range(3):
        ids=np.flatnonzero(np.any(full,axis=tuple(a for a in range(3) if a!=axis)))
        bounds.append((ids[0],ids[-1]))
    bounds=np.array(bounds);margin=np.ceil(27/spacing).astype(int)
    lo=np.maximum(0,bounds[:,0]-margin);hi=np.minimum(full.shape,bounds[:,1]+margin+1)
    roi=sitk.RegionOfInterest(image,[int(v) for v in (hi-lo)[::-1]],[int(v) for v in lo[::-1]])
    p=full[tuple(slice(a,b) for a,b in zip(lo,hi))].copy()
    ct=sitk.GetArrayFromImage(roi).astype(np.float32)
    distance=ndi.distance_transform_edt(~p,sampling=spacing)
    accepted,score,model=fit_intensity_model(ct,p,distance,spacing[::-1],density_ratio)
    _,first_labels,components=bounded_expansion(p,accepted,spacing[::-1],20,distance)
    # Explicit leakage proxy: enormous additions are not safe to expand again.
    # This may remove a true branch joined to leakage; retain reasons in sidecar.
    blocked_ids=[c['component_id'] for c in components if c['volume_mm3']>5000]
    tiny_ids=[c['component_id'] for c in components if c['volume_mm3']<2]
    blocked=(local_leakage_block(first_labels,components,spacing[::-1])
             if leakage_mode=="local_bulk" else np.isin(first_labels,blocked_ids+tiny_ids))
    expanded,labels,second=bounded_expansion(p,accepted&~blocked,spacing[::-1],25,distance)
    daughter_lumen=(expanded&~p).astype(np.uint8)
    structure=ndi.generate_binary_structure(3,1)
    contacts=(labels>0)&ndi.binary_dilation(p,structure=structure)
    contact_labels,count=ndi.label(contacts,structure=np.ones((3,3,3)))
    # Parent stays present for distance-to-side-wall estimation at the opening.
    clearance=ndi.distance_transform_edt(expanded,sampling=spacing)
    outward=np.gradient(ndi.gaussian_filter(distance.astype(np.float32),sigma=1),*spacing)
    # Optional in-memory diagnostics for reference-guided stage audits. Never
    # feed reference annotations into inference or retain arrays by default.
    if audit is not None:
        audit.update(roi=roi,parent=p,ct=ct,accepted=accepted,score=score,
                     first_labels=first_labels,blocked=blocked,labels=labels,
                     contact_labels=contact_labels,model=model,candidates=[])
    rejected=Counter();measurements=[];paths=[];candidate_records=[]
    candidate=None
    def reject(reason):
        rejected[reason]+=1
        if candidate is not None:candidate['outcome']=reason
    parent_float=p.astype(np.float32)
    parent_bounds=bounds-lo[:,None]
    # Dominant physical extent identifies the longitudinal array axis. Only
    # face continuations at the exact terminal planes are rejected, not a band.
    longitudinal=int(np.argmax((parent_bounds[:,1]-parent_bounds[:,0])*spacing))
    trials=[]
    for label,region in enumerate(ndi.find_objects(contact_labels),1):
        coords=np.argwhere(contact_labels[region]==label)+np.array([s.start for s in region])
        if not len(coords):continue
        points=contact_start_points(coords,clearance,spacing,max_points=8 if contact_mode=='fallback' else 1)
        trials.extend((label,point) for point in points)
    successful_contacts=set();attempted=0
    for label,point in trials:
        if label in successful_contacts:continue
        attempted+=1
        candidate={'contact_label':label,
            'point_xyz_mm':list(roi.TransformIndexToPhysicalPoint([int(v) for v in point[::-1]])),
            'outcome':'pending'}
        candidate_records.append(candidate)
        if audit is not None:audit['candidates'].append(candidate)
        normal=np.array([g[tuple(point)] for g in outward])
        if np.linalg.norm(normal)<1e-8:reject('no_normal');continue
        normal/=np.linalg.norm(normal)
        near_end=(point[longitudinal]<=parent_bounds[longitudinal,0] or point[longitudinal]>=parent_bounds[longitudinal,1])
        if near_end and abs(normal[longitudinal])>.7:reject('terminal_cap_or_iliac');continue
        component_id=labels[tuple(point)]
        # Estimate an initial outgoing axis from same-component voxels within
        # 5 mm, weighting farther voxels. Avoid assuming anatomical artery names.
        lower=np.maximum(0,point-np.ceil(5/spacing).astype(int))
        upper=np.minimum(p.shape,point+np.ceil(5/spacing).astype(int)+1)
        box=tuple(slice(a,b) for a,b in zip(lower,upper))
        local=np.argwhere(labels[box]==component_id)+lower
        deltas=(local-point)*spacing
        keep=(np.linalg.norm(deltas,axis=1)<=5)&(deltas@normal>.5)
        if not keep.any():reject('no_outgoing_volume');continue
        direction=np.average(deltas[keep],axis=0,weights=np.maximum(distance[tuple(local[keep].T)],.1))
        result,reason=measure_branch(parent_float,daughter_lumen,point,direction,spacing,min_diameter_mm,target_length_mm=target_length_mm)
        if result is None:reject(reason);continue
        prediction,path=export_measurement(result,roi)
        candidate['tracking_status']=result['tracking_status']
        if result['tracking_status']=='incomplete':
            # Keep recoverable evidence in diagnostics, not the daughter list.
            candidate['partial_measurement']={**prediction,
                'path_xyz_mm':path,'path_length_mm':result['path_length_mm'],
                'origin_diameter_mm':result['origin_diameter_mm'],
                'stop_reason':result['stop_reason']}
            reject('incomplete_track_'+result['stop_reason']);continue
        # Merge only highly similar initial paths, not every nearby origin.
        duplicate=False
        for old,oldpath in zip(measurements,paths):
            close=np.linalg.norm(np.array(old['ostium_xyz_mm'])-prediction['ostium_xyz_mm'])<1
            same=np.linalg.norm(np.array(old['seed_xyz_mm'])-prediction['seed_xyz_mm'])<1
            if close and same and np.dot(old['direction_xyz'],prediction['direction_xyz'])>.9:
                duplicate=True;break
        if duplicate:successful_contacts.add(label);reject('duplicate_path');continue
        if candidate is not None:candidate['outcome']='accepted';candidate['ostium_xyz_mm']=prediction['ostium_xyz_mm']
        prediction['parent_instance_id']='aorta'
        prediction['_details']={k:result[k] for k in ('origin_diameter_mm','path_length_mm','stop_reason','tracking_status')}
        measurements.append(prediction);paths.append(path);successful_contacts.add(label)
    order=sorted(range(len(measurements)),key=lambda i:tuple(measurements[i]['ostium_xyz_mm']))
    measurements=[measurements[i] for i in order];paths=[paths[i] for i in order]
    details=[]
    for i,prediction in enumerate(measurements,1):
        prediction['instance_id']=f'branch_{i:03d}'
        details.append({'instance_id':prediction['instance_id'],**prediction.pop('_details'),'path_xyz_mm':paths[i-1]})
    diagnostics={'target_length_mm':target_length_mm,'model_inside_median_hu':model['inside_median_hu'],
        'leakage_mode':leakage_mode,'blocked_voxels':int(blocked.sum()),
        'phase1_components':len(components),'blocked_large_components':blocked_ids,
        'blocked_tiny_components':len(tiny_ids),'phase2_components':len(second),
        'candidate_records':candidate_records,
        'contact_mode':contact_mode,'contact_trials':attempted,'contact_patches':count,'rejections':dict(rejected),'branches':details,
        'warning':'Experimental predictions; accuracy unmeasured. Early bifurcations before 5 mm are omitted and flagged.'}
    return measurements,diagnostics,(roi,p,labels)


def preview(output,context,daughters):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    if context is None:return
    roi,parent,labels=context
    ct=sitk.GetArrayFromImage(roi)
    fig,axes=plt.subplots(1,3,figsize=(13,5))
    # Maximum projections show all origins and arrows; CT MIPs can overlap
    # anatomy and are visual checks, not evidence of centreline correctness.
    for axis,ax in enumerate(axes):
        plane_spacing=np.delete(np.array(roi.GetSpacing())[::-1],axis)
        ax.imshow(np.max(ct,axis=axis),cmap='gray',vmin=-100,vmax=600,aspect=plane_spacing[0]/plane_spacing[1])
        silhouette=np.any(parent,axis=axis)
        if silhouette.any() and not silhouette.all():ax.contour(silhouette,levels=[.5],colors='cyan')
        for d in daughters:
            a=np.array(roi.TransformPhysicalPointToContinuousIndex(d['ostium_xyz_mm']))[::-1]
            b=np.array(roi.TransformPhysicalPointToContinuousIndex(d['seed_xyz_mm']))[::-1]
            a=np.delete(a,axis);b=np.delete(b,axis)
            ax.plot(a[1],a[0],'ro',ms=3)
            ax.annotate('',xy=(b[1],b[0]),xytext=(a[1],a[0]),arrowprops={'arrowstyle':'->','color':'lime'})
        ax.set_title(f'Array-axis {axis} projection')
    fig.suptitle(f'{len(daughters)} experimental predictions | cyan parent, red origins, green directions')
    fig.tight_layout();fig.savefig(output,dpi=140);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--aorta-mask',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--min-origin-diameter-mm',type=float,default=2.)
    parser.add_argument('--density-ratio',type=float,default=.6)
    parser.add_argument('--leakage-mode',choices=['whole_component','local_bulk'],default='whole_component',
                        help='local_bulk preserves narrow feeders of oversized regions; experimental')
    parser.add_argument('--contact-mode',choices=['single','fallback'],default='single')
    args=parser.parse_args()
    if not np.isfinite(args.min_origin_diameter_mm) or args.min_origin_diameter_mm<=0:parser.error('Minimum diameter must be positive')
    if not 0<args.density_ratio<1:parser.error('Density ratio must be in (0,1)')
    from src.review_validation import protect_reviewed_output
    protect_reviewed_output(args.output)
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    start=perf_counter();image,mask=read_nifti_pair(args.image,args.aorta_mask)
    daughters,diagnostics,context=detect(image,mask,args.min_origin_diameter_mm,args.density_ratio,leakage_mode=args.leakage_mode,contact_mode=args.contact_mode)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    payload={'case_id':Path(args.image).parent.name,'parent':{'instance_id':'aorta'},'daughters':daughters}
    output.write_text(json.dumps(payload,indent=2,allow_nan=False))
    preview(output.with_suffix('.png'),context,daughters)
    from src.review_validation import build_review, file_fingerprint
    review=build_review(payload,diagnostics,context,min_diameter_mm=args.min_origin_diameter_mm)
    review['original_geometry']={'size_xyz':list(image.GetSize()),'spacing_xyz_mm':list(image.GetSpacing()),
        'origin_lps_mm':list(image.GetOrigin()),'direction':list(image.GetDirection()),
        'note':'Geometry after input reader; consult original input hashes if reader resampled nonorthogonal data'}
    review['review_record']=file_fingerprint(Path(__file__).with_name('ORGANIZER_REVIEW_RECORD.md'))
    review['inputs']={'ct':file_fingerprint(args.image),'parent_mask':file_fingerprint(args.aorta_mask)}
    review['outputs']={'prediction':file_fingerprint(output),'preview':file_fingerprint(output.with_suffix('.png')) if context is not None else None}
    review_path=output.with_suffix('.review.json')
    review_path.write_text(json.dumps(review,indent=2,allow_nan=False))
    # Confirm the saved review and prediction can be reopened without changing values.
    if json.loads(review_path.read_text())!=review or json.loads(output.read_text())!=payload:
        raise RuntimeError('Saved-output round-trip failed')
    diagnostics['total_seconds']=perf_counter()-start
    diagnostics['config']={'min_origin_diameter_mm':args.min_origin_diameter_mm,'density_ratio':args.density_ratio,
        'first_radius_mm':20,'second_radius_mm':25,'max_component_mm3':5000,'min_component_mm3':2,
        'leakage_mode':args.leakage_mode,'contact_mode':args.contact_mode,'version':'experimental-expansion-1'}
    output.with_suffix('.diagnostics.json').write_text(json.dumps(diagnostics,indent=2,allow_nan=False))
    print(json.dumps({'case_id':payload['case_id'],'daughters':len(daughters),'seconds':diagnostics['total_seconds']}))


if __name__=='__main__':main()
