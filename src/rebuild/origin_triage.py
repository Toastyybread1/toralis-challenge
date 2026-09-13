"""Flag ambiguous direct-origin evidence without deleting possible vessels.

These are review priorities, not anatomical diagnoses or reference-based filters.
Physical endpoint proximity uses the longest parent-grid axis as a coarse cap
proxy. A wall-parallel path can be a real branch and must not be rejected solely
for remaining close to the aorta.
"""
import numpy as np
from scipy import ndimage as ndi


def triage_origin(pred,data):
    image=data['roi'];spacing=np.array(image.GetSpacing())[::-1]
    parent=data['parent'];occupied=np.where(parent)
    if not len(occupied[0]):raise ValueError('Cannot assess origin against an empty parent')
    bounds=np.array([(a.min()-.5,a.max()+.5) for a in occupied])
    axis=int(np.argmax(np.diff(bounds,axis=1).ravel()*spacing))
    origin=np.array(image.TransformPhysicalPointToContinuousIndex(pred['ostium_xyz_mm']))[::-1]
    endpoint_distance=float(min(abs(origin[axis]-bounds[axis]))*spacing[axis])
    points=np.array([image.TransformPhysicalPointToContinuousIndex(v) for v in pred['path_xyz_mm']])[:,::-1]
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0)*spacing,axis=1))]
    lengths=np.arange(0.,arc[-1]+1e-6,.5)
    indices=np.array([np.interp(lengths,arc,points[:,k]) for k in range(3)])
    separation=ndi.map_coordinates(data['distance'],indices,order=1)
    distal=separation[lengths>=5.]
    # Require an actually traced distal interval; never extrapolate a seed-only
    # path to 10 mm. The distance field is centre-based, not exact face distance.
    parallel=bool(arc[-1]>=9.5 and len(distal)>=9 and distal.max()<=4.
                  and np.ptp(distal)<=max(spacing))
    flags=[]
    if endpoint_distance<=2*spacing[axis]:flags.append('origin_near_supplied_parent_end')
    if parallel:flags.append('distal_path_remains_close_to_parent')
    if pred.get('diameter_eligibility')=='unresolved':flags.append('origin_diameter_requires_adjudication')
    return dict(flags=flags,origin_to_nearest_parent_end_proxy_mm=endpoint_distance,
        parent_long_axis_zyx=axis,measured_path_length_mm=float(arc[-1]),
        distance_sample_arclength_mm=lengths.tolist(),parent_distance_samples_mm=separation.tolist(),
        distal_wall_parallel=parallel,direct_origin_status='unresolved',
        effect='review priority only; candidate and evaluation count unchanged',
        caveat='Parent end proxy and centre-based distance do not establish crop-cap anatomy or vessel parentage')


def annotate_groups(groups,data):
    for group in groups:
        p=group['representative'];p['direct_origin_review']=triage_origin(p,data)
    return groups
