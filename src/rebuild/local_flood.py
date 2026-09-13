"""Bounded face-connected flooding and supported proximal paths, without labels.

Uses the existing intensity-accepted, spill-controlled lumen. It cannot create
missing contrast information. Flood paths do not establish bifurcation topology.
"""
import numpy as np
from scipy import ndimage as ndi
from skimage.graph import MCP_Geometric
from src.submission import contact_start_points
from src.daughter_geometry import path_lumen_supported,section,export_measurement


def smooth_supported(path,spacing,lumen,parent):
    path=np.asarray(path,float).copy()
    # Smooth stair steps only when both adjacent segments stay in exterior lumen.
    for _ in range(4):
        for i in range(1,len(path)-1):
            q=(path[i-1]+2*path[i]+path[i+1])/4
            if path_lumen_supported([path[i-1],q,path[i+1]],spacing,lumen,parent):path[i]=q
    return path


def flood_proposals(data,max_starts=4,max_targets=3,min_target_radius_mm=6.,target_spacing_mm=3.,angular_targets=False,patch_ids=None):
    image=data['roi'];spacing=np.array(image.GetSpacing())[::-1]
    parent=data['parent'];lumen=data['added']&data['valid_support']&~parent
    contact=lumen&ndi.binary_dilation(parent,structure=ndi.generate_binary_structure(3,1))
    labels,_=ndi.label(contact,np.ones((3,3,3)))
    clearance=ndi.distance_transform_edt(np.pad(parent|lumen,1),sampling=spacing)[1:-1,1:-1,1:-1]
    bounds=np.array([(v.min(),v.max()) for v in np.where(parent)])
    long_axis=int(np.argmax((bounds[:,1]-bounds[:,0])*spacing))
    proposals=[];records=[]
    for patch,box in enumerate(ndi.find_objects(labels),1):
        if patch_ids is not None and patch not in patch_ids:continue
        coords=np.argwhere(labels[box]==patch)+np.array([s.start for s in box])
        starts=contact_start_points(coords,clearance,spacing,max_points=max_starts,separation_mm=2.)
        for trial,q in enumerate(starts):
            rec=dict(patch=patch,trial=trial,start_index_zyx=q.tolist(),status='no_supported_path');records.append(rec)
            if q[long_axis]<=bounds[long_axis,0] or q[long_axis]>=bounds[long_axis,1]:
                rec['status']='terminal_parent_contact_review';continue
            pad=np.ceil(10/spacing).astype(int);lo=np.maximum(0,q-pad);hi=np.minimum(parent.shape,q+pad+1)
            local_box=tuple(slice(int(a),int(b)) for a,b in zip(lo,hi))
            local=lumen[local_box].copy();grid=np.indices(local.shape).transpose(1,2,3,0)
            radial=np.linalg.norm((grid+lo-q)*spacing,axis=-1);local &= radial<=10.
            if local.sum()>20000:rec['status']='local_volume_budget';continue
            # Penalize thin bridges while keeping all growth-connected routes.
            cost=np.where(local,1.+2./np.maximum(clearance[local_box],.5)**2,np.inf)
            flood=MCP_Geometric(cost,fully_connected=False,sampling=tuple(spacing))
            distances,_=flood.find_costs([tuple(q-lo)])
            reachable=local&np.isfinite(distances)
            rec['flooded_voxels']=int(reachable.sum())
            targets=np.argwhere(reachable&(radial>=min_target_radius_mm)&(radial<=9))
            if not len(targets):rec['status']='flood_does_not_reach_6mm';continue
            quality=clearance[tuple((targets+lo).T)]/np.maximum(distances[tuple(targets.T)],1.)
            chosen=[]
            order=np.argsort(-quality)
            if angular_targets:
                vectors=(targets+lo-q)*spacing
                unit=vectors/np.linalg.norm(vectors,axis=1)[:,None]
                directions=np.array([(a,b,c) for a in (-1,0,1) for b in (-1,0,1) for c in (-1,0,1) if a or b or c],float)
                directions/=np.linalg.norm(directions,axis=1)[:,None]
                spread=[]
                for direction in directions:
                    ids=np.flatnonzero(unit@direction>=.866)
                    if len(ids):spread.append(ids[np.argmax(quality[ids])])
                order=list(dict.fromkeys(spread))+order.tolist()
            for idx in order:
                endpoint=targets[idx]
                if any(np.linalg.norm((endpoint-old)*spacing)<target_spacing_mm for old in chosen):continue
                chosen.append(endpoint)
                if len(chosen)>=max_targets:break
            rec['targets_tested']=len(chosen);rec['paths_created']=0
            for target in chosen:
                cells=np.array(flood.traceback(tuple(target)))+lo
                if len(cells)<2:continue
                forward=(cells[min(3,len(cells)-1)]-q)*spacing
                neighbours=[]
                for axis in range(3):
                    for sign in (-1,1):
                        n=q.copy();n[axis]+=sign
                        if np.all(n>=0) and np.all(n<parent.shape) and parent[tuple(n)]:neighbours.append(n)
                if not neighbours:continue
                n=max(neighbours,key=lambda n:np.dot((q-n)*spacing,forward))
                origin=(q+n)*.5*spacing
                path=smooth_supported(np.vstack([origin,cells*spacing]),spacing,lumen,parent)
                arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
                if arc[-1]<5:continue
                at=lambda s:np.array([np.interp(s,arc,path[:,a]) for a in range(3)])
                seed=at(5.);tangent=seed-at(4.)
                path=np.vstack([path[arc<5-1e-8],seed])
                if not path_lumen_supported(path,spacing,lumen,parent):continue
                parts=[s for s in section(lumen,seed,tangent,spacing) if s['contains_centre'] and not s['edge']]
                if not parts:continue
                m=dict(ostium_local_mm=origin,seed_local_mm=seed,radius_mm=float(np.sqrt(parts[0]['area']/np.pi)),path_local_mm=path)
                pred,world=export_measurement(m,image)
                pred.update(source='local_flood',origin_initialization='flood_contact_face',path_xyz_mm=world,
                    tracking_status='seed_only_distal_unresolved',stop_reason='flood_topology_unresolved',path_length_mm=5.,
                    parent_instance_id='aorta',anatomical_confirmation='pending',flood_patch=patch,flood_trial=trial)
                proposals.append(pred);rec['paths_created']+=1
            if rec['paths_created']:rec['status']='supported_seed_paths'
    return proposals,records
