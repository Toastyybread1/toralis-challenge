"""Current growth -> boundary contacts -> Riffaud-style primary-branch traversal.

Tree extraction and contact anchoring are our adaptations. All output remains
experimental; topology in a leaky segmentation is not anatomical proof.
"""
import heapq
from collections import Counter
import numpy as np
from scipy import ndimage as ndi
import SimpleITK as sitk
from src.centreline_extraction import extract_centreline
from src.vascular_tree import follow_primary_branch
from src.daughter_geometry import section,path_lumen_supported

STEPS=[np.eye(3,dtype=int)[a]*s for a in range(3) for s in (-1,1)]


def connect_endpoint(lumen,start,targets,spacing,max_length=5.):
    """Physical shortest face-connected attachment, bounded to 5 mm/5000 visits."""
    start=tuple(start);target_set={tuple(q):i for i,q in enumerate(targets)}
    queue=[(0.,start)];dist={start:0.};previous={};visited=0
    while queue and visited<5000:
        length,q=heapq.heappop(queue)
        if length!=dist[q]:continue
        visited+=1
        if q in target_set:
            path=[q]
            while path[-1]!=start:path.append(previous[path[-1]])
            return list(reversed(path)),target_set[q]
        for step in STEPS:
            n=tuple(np.array(q)+step)
            if any(v<0 or v>=lumen.shape[a] for a,v in enumerate(n)) or not lumen[n]:continue
            candidate=length+float(np.linalg.norm(step*spacing))
            if candidate<=max_length and candidate<dist.get(n,np.inf):
                dist[n]=candidate;previous[n]=q;heapq.heappush(queue,(candidate,n))
    return None,None


def detect_daughters(data):
    image=data['roi'];p=data['parent'];lumen=data['added'];spacing=np.array(image.GetSpacing())[::-1]
    labels,count=ndi.label(lumen,structure=ndi.generate_binary_structure(3,1))
    contacts=lumen&ndi.binary_dilation(p,structure=ndi.generate_binary_structure(3,1))
    clearance=ndi.distance_transform_edt(np.pad(p|lumen,1),sampling=spacing)[1:-1,1:-1,1:-1]
    records=[];daughters=[];graphs={};objects=ndi.find_objects(labels)
    extents=np.array([(np.flatnonzero(np.any(p,axis=tuple(b for b in range(3) if b!=a)))[[0,-1]]) for a in range(3)])
    long_axis=int(np.argmax(np.diff(extents,axis=1).ravel()*spacing))
    for component,region in enumerate(objects,1):
        local=labels[region]==component;base=np.array([s.start for s in region])
        contact_labels,n=ndi.label(contacts[region]&local,structure=np.ones((3,3,3)))
        if not n:continue
        crop=sitk.RegionOfInterest(image,[int(v) for v in local.shape[::-1]],[int(v) for v in base[::-1]])
        graph=None
        for contact in range(1,n+1):
            coords=np.argwhere(contact_labels==contact)+base
            q=coords[np.argmax(clearance[tuple(coords.T)])]
            neighbours=[q+step for step in STEPS if np.all(q+step>=0) and np.all(q+step<p.shape) and p[tuple(q+step)]]
            if not neighbours:continue
            parent_neighbour=neighbours[0];origin=(q+parent_neighbour)/2
            record={'candidate_id':f'contact_{component}_{contact}','component_id':component,
                    'contact_count_in_component':int(n),'ostium_xyz_mm':list(image.TransformContinuousIndexToPhysicalPoint(origin[::-1].tolist())),
                    'status':'pending','anatomical_confirmation':'pending'}
            records.append(record)
            if local.sum()*np.prod(spacing)<8:
                record['status']='insufficient_segment_volume';continue
            if q[long_axis]<=extents[long_axis,0] or q[long_axis]>=extents[long_axis,1]:
                record['status']='terminal_parent_contact_review';continue
            if graph is None:
                graph=extract_centreline(local,crop,q-base,max_voxels=250000,max_skeleton_nodes=5000)
                graphs[component]=graph
            record['graph_status']=graph['status']
            if graph['status']!='tree':record['status']=graph['status'];continue
            points=np.array(graph['points_xyz_mm']);indices=np.array(graph['node_indices_zyx'])
            endpoints=graph['leaf_nodes']
            if not endpoints:record['status']='no_graph_endpoint';continue
            attachment,which=connect_endpoint(local,q-base,indices[endpoints],spacing)
            if attachment is None:record['status']='no_supported_endpoint_attachment';continue
            root=endpoints[which];attachment=np.array(attachment)+base
            # Select an actual exposed face pointing toward the attached tree.
            tangent=indices[root]+base-q
            if np.linalg.norm(tangent)>0:
                parent_neighbour=max(neighbours,key=lambda v:np.dot((q-v)*spacing,tangent*spacing))
                origin=(q+parent_neighbour)/2
                record['ostium_xyz_mm']=list(image.TransformContinuousIndexToPhysicalPoint(origin[::-1].tolist()))
            extra=[record['ostium_xyz_mm']]+[list(image.TransformIndexToPhysicalPoint([int(v) for v in x[::-1]])) for x in attachment[:-1]]
            allpoints=points.tolist()+extra;edges=list(graph['edges']);new_ids=list(range(len(points),len(allpoints)))
            chain=new_ids+[root];edges+=list(zip(chain[:-1],chain[1:]))
            result=follow_primary_branch(allpoints,edges,chain[0],chain[1])
            record.update(result)
            path=np.array([image.TransformPhysicalPointToContinuousIndex(v) for v in result['path_xyz_mm']])[:,::-1]*spacing
            if not path_lumen_supported(path,spacing,lumen,p):record['status']='unsupported_graph_path';continue
            if result['seed_xyz_mm'] is None:
                record['status']=result['tracking_status'];continue
            arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
            def at(length):return np.array([np.interp(length,arc,path[:,a]) for a in range(3)])
            origin_axis=at(min(3.,arc[-1]))-path[0]
            seed_axis=at(min(6.,arc[-1]))-at(4.)
            if min(np.linalg.norm(origin_axis),np.linalg.norm(seed_axis))<1e-8:
                record['status']='degenerate_direction';continue
            # Offset into the daughter avoids sampling exactly on the cut face.
            opening=[s for s in section(lumen,at(min(.5,arc[-1])),origin_axis,spacing) if s['contains_centre']]
            seed_sections=[s for s in section(lumen,at(5.),seed_axis,spacing) if s['contains_centre']]
            if not opening or not seed_sections or opening[0]['edge'] or seed_sections[0]['edge']:
                record['status']='unresolved_cross_section';continue
            diameter=2*np.sqrt(opening[0]['area']/np.pi)
            record['origin_diameter_estimate_mm']=float(diameter)
            if diameter<2:record['status']='below_minimum_origin_diameter';continue
            direction=np.array(image.GetDirection()).reshape(3,3)@seed_axis[::-1];direction/=np.linalg.norm(direction)
            record['status']='provisional_daughter'
            prediction={'instance_id':f'branch_{len(daughters)+1:03d}','parent_instance_id':'aorta',
                'ostium_xyz_mm':record['ostium_xyz_mm'],'seed_xyz_mm':result['seed_xyz_mm'],
                'radius_mm':float(np.sqrt(seed_sections[0]['area']/np.pi)),'direction_xyz':direction.tolist(),
                'tracking_status':result['tracking_status'],'candidate_id':record['candidate_id'],
                'anatomical_confirmation':'pending'}
            daughters.append(prediction)
    complete=[d for d in daughters if d['tracking_status'] in ('length_complete','bifurcation_review_required')]
    return {'daughters':complete,'seed_candidates':daughters,'candidate_records':records,'graphs':graphs,
            'status_counts':dict(Counter(r['status'] for r in records)),
            'warning':'Provisional graph-derived candidates, not expert-validated daughter counts. Incomplete leaves and bifurcations require review.'}
