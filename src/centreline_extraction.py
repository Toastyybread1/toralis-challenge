"""Experimental Lee skeleton to physical graph; never force loops into trees.

The input is a binary daughter lumen and a voxel inside its desired component.
This is our extractor, not PRAEVAorta or a reproduction of Riffaud's extraction.
"""
from itertools import product
import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize
from src.vascular_tree import validate_tree

OFFSETS=[o for o in product((-1,0,1),repeat=3) if o!=(0,0,0)]


def skeleton_graph(skeleton):
    coords=np.argwhere(skeleton)
    lookup={tuple(p):i for i,p in enumerate(coords)}
    adjacency=[set() for _ in coords]
    removed=0
    for i,p in enumerate(coords):
        for offset in OFFSETS:
            q=p+offset;j=lookup.get(tuple(q))
            if j is None or j<=i:continue
            # A diagonal with an existing intermediate voxel in its unit box
            # shortcuts that voxel's route. Remove only this local redundancy.
            if sum(v!=0 for v in offset)>1:
                lower=np.minimum(p,q);upper=np.maximum(p,q)
                intermediates=product(*(range(int(a),int(b)+1) for a,b in zip(lower,upper)))
                if any(r!=tuple(p) and r!=tuple(q) and r in lookup for r in intermediates):
                    removed+=1;continue
            adjacency[i].add(j);adjacency[j].add(i)
    edges=[(i,j) for i,neighbors in enumerate(adjacency) for j in sorted(neighbors) if j>i]
    return coords,edges,adjacency,removed


def extract_centreline(lumen, image, anchor_index_zyx, max_voxels=2000000,max_skeleton_nodes=100000):
    """Select the anchor's face-connected component and thin only its crop.

    Geometry is transformed by the supplied SimpleITK image. Thinning itself
    uses native voxels; anisotropic images are flagged, not silently resampled.
    Crop-cut endpoints, short spurs and adjacent junction nodes remain explicit.
    """
    lumen=np.asarray(lumen)
    if lumen.ndim!=3 or tuple(lumen.shape)!=tuple(image.GetSize())[::-1]:raise ValueError('Lumen/image dimensions differ')
    if not np.isin(lumen,[0,1]).all():raise ValueError('Expected binary lumen, not instance labels')
    anchor=np.asarray(anchor_index_zyx)
    if anchor.shape!=(3,) or not np.isfinite(anchor).all() or not np.equal(anchor,np.round(anchor)).all():raise ValueError('Expected integer voxel anchor')
    anchor=anchor.astype(int)
    if np.any(anchor<0) or np.any(anchor>=lumen.shape) or not lumen[tuple(anchor)]:
        return {'status':'anchor_outside_lumen','points_xyz_mm':[],'edges':[]}
    labels,count=ndi.label(lumen,structure=ndi.generate_binary_structure(3,1))
    component_id=int(labels[tuple(anchor)]);region=ndi.find_objects(labels)[component_id-1]
    local=labels[region]==component_id
    base=np.array([s.start for s in region])
    stats={'input_components':int(count),'selected_component_voxels':int(local.sum()),
           'excluded_disconnected_voxels':int(np.count_nonzero(labels)-local.sum()),
           'native_spacing_xyz_mm':list(image.GetSpacing()),
           'anisotropic_thinning_warning':not np.allclose(image.GetSpacing(),image.GetSpacing()[0]),
           'touches_input_boundary':any(s.start==0 or s.stop==lumen.shape[i] for i,s in enumerate(region))}
    if local.size>max_voxels:return {'status':'volume_budget_exceeded',**stats,'points_xyz_mm':[],'edges':[]}
    skel=skeletonize(np.pad(local,1),method='lee')[1:-1,1:-1,1:-1]
    if skel.sum()>max_skeleton_nodes:return {'status':'node_budget_exceeded',**stats,'points_xyz_mm':[],'edges':[]}
    coords,edges,adjacency,removed=skeleton_graph(skel)
    coords=coords+base
    points=[list(image.TransformIndexToPhysicalPoint([int(v) for v in q[::-1]])) for q in coords]
    stats['diagonal_shortcuts_removed']=removed
    if not points:return {'status':'empty_skeleton',**stats,'points_xyz_mm':[],'edges':[]}
    status='tree'
    try:validate_tree(points,edges)
    except ValueError as error:status='unresolved_topology';stats['topology_reason']=str(error)
    anchor_mm=np.array(image.TransformIndexToPhysicalPoint([int(v) for v in anchor[::-1]]))
    distances=np.linalg.norm(np.array(points)-anchor_mm,axis=1);root=int(np.argmin(distances))
    junctions=[i for i,n in enumerate(adjacency) if len(n)>=3]
    leaves=[i for i,n in enumerate(adjacency) if len(n)==1]
    junction_set=set(junctions);clusters=[]
    while junction_set:
        group={junction_set.pop()};stack=list(group)
        while stack:
            for n in adjacency[stack.pop()]&junction_set:
                junction_set.remove(n);group.add(n);stack.append(n)
        clusters.append(sorted(group))
    # Report terminal arm lengths, without deleting possible true small vessels.
    arms=[]
    for leaf in leaves:
        prev=None;node=leaf;length=0
        while True:
            forward=adjacency[node]-({prev} if prev is not None else set())
            if not forward or len(adjacency[node])>=3:break
            nxt=next(iter(forward));length+=float(np.linalg.norm(np.array(points[nxt])-points[node]));prev,node=node,nxt
        arms.append({'leaf_node':leaf,'junction_or_other_leaf':node,'length_mm':length,
                     'short_arm_review':length<2.})
    return {'status':status,**stats,'points_xyz_mm':points,'edges':[list(e) for e in edges],
            'node_indices_zyx':coords.tolist(),'root_node':root,'anchor_to_skeleton_mm':float(distances[root]),
            'root_is_endpoint':len(adjacency[root])==1,'junction_nodes':junctions,
            'junction_clusters':clusters,'junction_localization_uncertain':any(len(g)>1 for g in clusters),
            'leaf_nodes':leaves,'terminal_arms':arms,'anatomical_confirmation':'pending'}
