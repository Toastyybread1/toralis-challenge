"""Proximal lumen tracking and physical measurements for a classical baseline.

These geometry heuristics are challenge adaptations, not Tahoces parameters.
The supplied parent and expanded binary lumen remain the main error sources.
"""
import numpy as np
from scipy import ndimage as ndi


def sample(array, point_mm, spacing_zyx, order=1):
    return float(ndi.map_coordinates(array, (np.asarray(point_mm)/spacing_zyx)[:,None],
                                     order=order, mode='constant', cval=0)[0])


def section(lumen, centre, tangent, spacing, half_width=6., pixel=.4):
    """Connected lumen areas in a physical plane perpendicular to the tangent."""
    tangent=np.asarray(tangent,dtype=float);tangent/=np.linalg.norm(tangent)
    basis=np.eye(3)[np.argmin(np.abs(tangent))]
    u=np.cross(tangent,basis);u/=np.linalg.norm(u);v=np.cross(tangent,u)
    axis=np.arange(-half_width,half_width+pixel*.5,pixel)
    a,b=np.meshgrid(axis,axis,indexing='ij')
    points=centre[:,None,None]+u[:,None,None]*a+v[:,None,None]*b
    values=ndi.map_coordinates(lumen.astype(np.uint8,copy=False),points/spacing[:,None,None],
                               order=0,mode='constant',cval=0)>0
    labels,n=ndi.label(values)
    objects=[]
    for label in range(1,n+1):
        coords=np.argwhere(labels==label)
        offset=np.array([axis[coords[:,0]].mean(),axis[coords[:,1]].mean()])
        objects.append({'area':float(len(coords)*pixel**2),'offset':offset,
                        'centre':centre+u*offset[0]+v*offset[1],
                        'contains_centre':bool(labels[len(axis)//2,len(axis)//2]==label),
                        'edge':bool(np.any((coords==0)|(coords==len(axis)-1)))})
    objects.sort(key=lambda o:np.linalg.norm(o['offset']))
    return objects


def tracking_status(path_length_mm, stop_reason):
    """Distinguish completed length, provisional split, and numerical failure.

    A possible split still requires anatomical review. Reaching the seed alone
    never establishes the required distal stopping point.
    """
    if path_length_mm>=10-1e-5:return 'length_complete'
    if path_length_mm>=5-1e-5 and stop_reason=='possible_bifurcation':
        return 'bifurcation_review_required'
    return 'incomplete'


def path_lumen_supported(path_mm,spacing_zyx,lumen,parent):
    """Check every voxel-cell interval crossed by each polyline segment."""
    spacing=np.asarray(spacing_zyx,float)
    for a,b in zip(path_mm[:-1],path_mm[1:]):
        a=np.asarray(a)/spacing;b=np.asarray(b)/spacing;delta=b-a
        cuts=[0.,1.]
        for axis in range(3):
            if abs(delta[axis])<1e-12:continue
            lo,hi=sorted((a[axis],b[axis]))
            for plane in np.arange(np.floor(lo-.5)+1,np.ceil(hi-.5))+.5:
                t=(plane-a[axis])/delta[axis]
                if 0<t<1:cuts.append(float(t))
        cuts=sorted(set(cuts))
        for start,end in zip(cuts[:-1],cuts[1:]):
            # Ignore only the numerical boundary-bisection tolerance.
            if (end-start)*np.linalg.norm(delta*spacing)<1e-4:continue
            q=np.floor(a+delta*((start+end)/2)+.5).astype(int)
            if np.any(q<0) or np.any(q>=lumen.shape):return False
            if not lumen[tuple(q)] or parent[tuple(q)]:return False
    return True


def measure_branch(parent, lumen, contact_index, direction, spacing_zyx,
                   min_diameter_mm=2., step_mm=.5, target_length_mm=10., strict_geometry=False,
                   origin_local_mm=None):
    """Trace up to 10 mm; estimate seed radius using perpendicular lumen area.

    Stops on loss of lumen, sharp bend, crop edge, large section, or two nearby
    disjoint forward lumen sections (provisional bifurcation detector).
    Early splits before 5 mm are flagged ambiguous instead of inventing a seed.
    """
    if target_length_mm not in (5.,10.):raise ValueError('Target length must be 5 or 10 mm')
    # The isolated 5-mm rebuild uses the verified voxel-cell border.
    # Keep the existing 10-mm baseline's interpolation convention unchanged.
    parent_order=0 if target_length_mm==5 or strict_geometry else 1
    spacing=np.asarray(spacing_zyx,dtype=float)
    point=np.asarray(contact_index,dtype=float)*spacing
    tangent=np.asarray(direction,dtype=float)
    if np.linalg.norm(tangent)<1e-8:return None,'no_initial_direction'
    tangent/=np.linalg.norm(tangent)
    # Find an inside-to-outside crossing behind the contact. Half occupancy
    # of the interpolated mask is our explicit subvoxel boundary convention.
    if origin_local_mm is not None:
        if not strict_geometry:raise ValueError('Explicit origins require strict geometry')
        ostium=np.asarray(origin_local_mm,dtype=float)
        # Check both sides of the actual cell face. A nearby point or a ray
        # crossing some other part of the aorta is not an opening anchor.
        if (sample(parent,ostium-tangent*1e-3,spacing,0)<.5 or
                sample(parent,ostium+tangent*1e-3,spacing,0)>=.5 or
                not path_lumen_supported([ostium,ostium+tangent*.5],spacing,lumen,parent)):
            return None,'unsupported_face_entry'
    else:
        previous=point.copy();inside=None
        for distance in np.arange(.25,6.01,.25):
            probe=point-tangent*distance
            if sample(parent,probe,spacing,parent_order) >= .5:
                inside=probe;outside=previous;break
            previous=probe
        if inside is None:return None,'no_parent_crossing'
        for _ in range(12):
            midpoint=(inside+outside)/2
            if sample(parent,midpoint,spacing,parent_order)>=.5:inside=midpoint
            else:outside=midpoint
        ostium=(inside+outside)/2
    path=[ostium];length=0.;radius_at_seed=None;seed=None;stop='iteration_limit'
    # Measure the opening on the daughter side; this is not the seed radius.
    origin_offset=.5 if strict_geometry else max(.5,spacing.min())
    initial=section(lumen,ostium+tangent*origin_offset,tangent,spacing)
    if strict_geometry:initial=[part for part in initial if part['contains_centre']]
    if not initial or initial[0]['edge']:return None,'unbounded_origin_section'
    origin_diameter=2*np.sqrt(initial[0]['area']/np.pi)
    if origin_diameter<min_diameter_mm:return None,'origin_below_minimum'
    for _ in range(40):
        predicted=path[-1]+tangent*step_mm
        index=predicted/spacing
        if np.any(index<0) or np.any(index>np.array(parent.shape)-1):stop='image_boundary';break
        parts=section(lumen,predicted,tangent,spacing)
        parts=[p for p in parts if np.linalg.norm(p['offset'])<=2.5 and p['area']>=.5]
        if not parts:stop='lost_lumen';break
        if len(parts)>1 and parts[1]['area']>=max(.8,.3*parts[0]['area']):
            stop='possible_bifurcation';break
        part=parts[0]
        if part['edge'] or part['area']>np.pi*6**2:stop='large_or_clipped_section';break
        # Recenter gradually so large, irregular regions cannot jerk the path.
        shift=part['centre']-predicted
        if np.linalg.norm(shift)>step_mm:shift*=step_mm/np.linalg.norm(shift)
        next_point=predicted+shift
        if strict_geometry and not path_lumen_supported([path[-1],next_point],spacing,lumen,parent):
            # Centroid correction can cut a voxel corner across the parent or
            # a gap. Back off that correction; never bridge unsupported cells.
            supported=False
            for fraction in (.5,.25,0.):
                candidate=predicted+fraction*shift
                if path_lumen_supported([path[-1],candidate],spacing,lumen,parent):
                    next_point=candidate;supported=True;break
            if not supported:stop='path_leaves_daughter_lumen';break
        if sample(lumen,next_point,spacing,0)<.5 or sample(parent,next_point,spacing,parent_order)>=.5:
            stop='left_daughter_lumen';break
        delta=next_point-path[-1];segment=np.linalg.norm(delta)
        new_direction=delta/segment
        if np.dot(new_direction,tangent)<.65:stop='sharp_turn';break
        if length+segment>target_length_mm:
            next_point=path[-1]+delta*(target_length_mm-length)/segment;segment=target_length_mm-length
        if seed is None and length+segment>=5:
            seed=path[-1]+(next_point-path[-1])*((5-length)/segment)
            sections=section(lumen,seed,new_direction,spacing)
            if (not sections or sections[0]['edge'] or not sections[0]['contains_centre']
                    or sample(lumen,seed,spacing,0)<.5):return None,'invalid_seed_section'
            radius_at_seed=float(np.sqrt(sections[0]['area']/np.pi))
        path.append(next_point);length+=segment
        tangent=.5*tangent+.5*new_direction;tangent/=np.linalg.norm(tangent)
        if length>=target_length_mm-1e-6:stop='length_limit';break
    if seed is None:return None,('ambiguous_early_bifurcation' if stop=='possible_bifurcation' else stop)
    if (target_length_mm==5 or strict_geometry) and not path_lumen_supported(path,spacing,lumen,parent):
        return None,'path_leaves_daughter_lumen'
    direction=seed-ostium;direction/=np.linalg.norm(direction)
    return {'ostium_local_mm':ostium,'seed_local_mm':seed,'direction_local':direction,
            'radius_mm':radius_at_seed,'origin_diameter_mm':float(origin_diameter),
            'path_local_mm':np.array(path),'path_length_mm':float(length),'stop_reason':stop,
            'tracking_status':('seed_milestone_complete' if target_length_mm==5 and length>=5-1e-6 else tracking_status(length,stop))},None


def export_measurement(measurement, image):
    spacing=np.asarray(image.GetSpacing())[::-1]
    def world(p):
        return np.asarray(image.TransformContinuousIndexToPhysicalPoint(tuple(float(v) for v in (p/spacing)[::-1])))
    ostium=world(measurement['ostium_local_mm']);seed=world(measurement['seed_local_mm'])
    direction=seed-ostium;direction/=np.linalg.norm(direction)
    return {'ostium_xyz_mm':ostium.tolist(),'seed_xyz_mm':seed.tolist(),
            'radius_mm':measurement['radius_mm'],'direction_xyz':direction.tolist()}, [world(p).tolist() for p in measurement['path_local_mm']]
