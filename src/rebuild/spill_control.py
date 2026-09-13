"""Experimental porous-bulk rejection, not a paper-specified classifier.

Close small gaps only in a temporary shape used to measure bulk. Never add
closed voxels to the vessel mask or modify the parent. Process additions
separately so nearby disconnected regions cannot combine into one large core.
"""
import numpy as np
from scipy import ndimage as ndi


def porous_bulk_block(labels,components,spacing_xyz,bulk_radius_mm=6.,closing_radius_mm=2.):
    spacing=np.asarray(spacing_xyz,dtype=float)[::-1]
    if spacing.shape!=(3,) or not np.isfinite(spacing).all() or np.any(spacing<=0):
        raise ValueError('Positive finite spacing required')
    if not np.isfinite([bulk_radius_mm,closing_radius_mm]).all() or min(bulk_radius_mm,closing_radius_mm)<=0:
        raise ValueError('Positive finite radii required')
    blocked=np.zeros(labels.shape,bool)
    objects=ndi.find_objects(labels)
    for c in components:
        identity=c['component_id'];region=objects[identity-1]
        original=labels[region]==identity
        if c['volume_mm3']<2:
            blocked[region]|=original
            continue
        if c['volume_mm3']<=5000:continue
        # Padding prevents clipping dilation and treats crop faces as exterior.
        pad=np.ceil((closing_radius_mm+bulk_radius_mm)/spacing).astype(int)+2
        padded=np.pad(original,tuple((int(v),int(v)) for v in pad))
        dilated=ndi.distance_transform_edt(~padded,sampling=spacing)<=closing_radius_mm
        closed=ndi.distance_transform_edt(dilated,sampling=spacing)>closing_radius_mm
        clearance=ndi.distance_transform_edt(closed,sampling=spacing)
        core=clearance>bulk_radius_mm
        if core.any():
            bulk=ndi.distance_transform_edt(~core,sampling=spacing)<=bulk_radius_mm
            inner=tuple(slice(int(v),int(v)+size) for v,size in zip(pad,original.shape))
            blocked[region]|=original&bulk[inner]
    return blocked


def expansion_volume_block(labels,components,distance_mm,spacing_xyz,band_mm=2.,
                           expansion_factor=4.,min_band_volume_mm3=250.):
    """Flag abrupt added-volume increases in successive parent-distance bands.

    This is a local adaptation of excessive-volume rejection, not a numerical
    rule published by Tahoces. Distance is radial from the parent, not vessel
    arclength. Whole-component distal cuts can remove siblings; retain audit
    records and evaluate losses before promoting this experiment.
    """
    spacing=np.asarray(spacing_xyz,dtype=float)
    if spacing.shape!=(3,) or not np.isfinite(spacing).all() or np.any(spacing<=0):
        raise ValueError('Positive finite spacing required')
    if not np.isfinite([band_mm,expansion_factor,min_band_volume_mm3]).all() or band_mm<=0 or expansion_factor<=1 or min_band_volume_mm3<=0:
        raise ValueError('Invalid volume-rule parameters')
    if labels.shape!=distance_mm.shape:raise ValueError('Distance shape mismatch')
    blocked=np.zeros(labels.shape,bool);records=[];volume=float(np.prod(spacing))
    objects=ndi.find_objects(labels)
    for c in components:
        identity=c['component_id'];region=objects[identity-1];mask=labels[region]==identity
        distances=distance_mm[region][mask]
        # Right-closed physical bands: (0,2], (2,4], etc.
        bins=np.maximum(0,np.ceil(distances/band_mm).astype(int)-1)
        amounts=np.bincount(bins)*volume
        record={'component_id':identity,'band_volumes_mm3':amounts.tolist(),
                'band_mm':band_mm,'blocked_from_parent_distance_mm':None}
        # Start beyond the first two bands so the immediate opening is retained.
        for index in range(2,len(amounts)):
            previous=amounts[index-1]
            if previous>0 and amounts[index]>=min_band_volume_mm3 and amounts[index]>=expansion_factor*previous:
                start=index*band_mm
                blocked[region]|=mask&(distance_mm[region]>start)
                record.update(blocked_from_parent_distance_mm=start,
                              expansion_factor_observed=float(amounts[index]/previous))
                break
        records.append(record)
    return blocked,records
