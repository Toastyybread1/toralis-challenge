"""Reference-free origin proposals from the already supported proximal lumen.

Estimate a local axis from distal path samples, then retrace from its intersection
with the supplied parent. The result must pass the normal voxel support audit.
An extrapolated axis is a proposal, never proof of an anatomical ostium.
"""
import numpy as np
from src.daughter_geometry import measure_branch,export_measurement


def refine_origins(proposals,data):
    image=data['roi'];spacing=np.array(image.GetSpacing())[::-1]
    output=[]
    for identity,pred in enumerate(proposals):
        path=np.array([image.TransformPhysicalPointToContinuousIndex(v) for v in pred['path_xyz_mm']])[:,::-1]*spacing
        arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
        for low,high in ((1.,3.),(2.,4.)):
            samples=np.array([[np.interp(s,arc,path[:,a]) for a in range(3)] for s in np.linspace(low,high,9)])
            centre=samples.mean(axis=0);_,_,axes=np.linalg.svd(samples-centre,full_matrices=False)
            tangent=axes[0]
            if np.dot(tangent,samples[-1]-samples[0])<0:tangent=-tangent
            m,reason=measure_branch(data['parent'],data['added'],centre/spacing,tangent,spacing,
                                  min_diameter_mm=0.,target_length_mm=5.,strict_geometry=True)
            if m is None:continue
            extended,_=measure_branch(data['parent'],data['added'],centre/spacing,tangent,spacing,
                                     min_diameter_mm=0.,target_length_mm=10.,strict_geometry=True)
            if extended is not None:m=extended
            else:
                m['tracking_status']='seed_only_distal_unresolved';m['stop_reason']='refined_extension_unresolved'
            p,world=export_measurement(m,image)
            p.update(source='axis_refinement',origin_initialization='proximal_axis_parent_intersection',
                     refinement_parent_proposal=identity,axis_fit_interval_mm=[low,high],
                     path_xyz_mm=world,origin_diameter_mm=m['origin_diameter_mm'],
                     tracking_status=m['tracking_status'],stop_reason=m['stop_reason'],path_length_mm=m['path_length_mm'],
                     parent_instance_id='aorta',anatomical_confirmation='pending')
            output.append(p)
    return output
