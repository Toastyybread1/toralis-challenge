"""Riffaud-style aortic-backbone and off-backbone branch review.

The paper assumes a supplied tree. Extraction from binary growth, mask-anchored
backbone selection and uncertainty handling here are explicit adaptations.
No anatomical naming, fixed daughter count or forced spanning tree is used.
"""
import heapq
import time
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize
from src.centreline_extraction import skeleton_graph


def shortest_path(points,adjacency,start,end,allowed=None):
    queue=[(0.,start)];distance={start:0.};previous={}
    while queue:
        d,u=heapq.heappop(queue)
        if d!=distance[u]:continue
        if u==end:
            path=[u]
            while path[-1]!=start:path.append(previous[path[-1]])
            return path[::-1]
        for v in adjacency[u]:
            if allowed is not None and v not in allowed:continue
            trial=d+float(np.linalg.norm(points[u]-points[v]))
            if trial<distance.get(v,np.inf):
                distance[v]=trial;previous[v]=u;heapq.heappush(queue,(trial,v))
    return None


def off_backbone_components(adjacency,backbone):
    """Retain complete outgoing components; multiple attachments stay ambiguous."""
    trunk=set(backbone);remaining=set(range(len(adjacency)))-trunk;components=[]
    while remaining:
        component={remaining.pop()};stack=list(component);attachments=set()
        while stack:
            u=stack.pop();attachments.update(adjacency[u]&trunk)
            for v in adjacency[u]&remaining:
                remaining.remove(v);component.add(v);stack.append(v)
        edge_count=sum(len(adjacency[u]&component) for u in component)//2
        components.append(dict(nodes=sorted(component),attachments=sorted(attachments),
                               cyclic=edge_count>=len(component)))
    return components


def is_unbranched_return(component,adjacency):
    """A route joining the backbone twice, with no outgoing daughter arm.

This violates the paper's single-root tree-branch assumption. It is not proof
that no anatomical anastomosis exists, so the correct disposition is deferred.
"""
    return (len(component['attachments'])==2 and not component['cyclic']
            and bool(component['nodes']) and all(len(adjacency[u])==2 for u in component['nodes']))


def build_context(data,max_voxels=2000000,max_nodes=15000):
    start=time.perf_counter();parent=data['parent'];mask=(parent|data['added'])&data['valid_support']
    if mask.size>max_voxels:return {'status':'volume_budget_exceeded'}
    skeleton=skeletonize(np.pad(mask,1),method='lee')[1:-1,1:-1,1:-1]
    if skeleton.sum()>max_nodes:return {'status':'node_budget_exceeded'}
    coords,edges,adjacency,_=skeleton_graph(skeleton)
    if len(coords)<2:return {'status':'insufficient_skeleton'}
    image=data['roi'];spacing=np.array(image.GetSpacing())[::-1]
    points=np.array([image.TransformIndexToPhysicalPoint([int(v) for v in q[::-1]]) for q in coords])
    inside=parent[tuple(coords.T)];parent_nodes=np.flatnonzero(inside)
    if len(parent_nodes)<2:return {'status':'missing_parent_backbone'}
    extents=np.array([(q.min(),q.max()) for q in np.where(parent)])
    axis=int(np.argmax(np.diff(extents,axis=1).ravel()*spacing))
    start_node=int(parent_nodes[np.argmin(coords[parent_nodes,axis])]);end_node=int(parent_nodes[np.argmax(coords[parent_nodes,axis])])
    backbone=shortest_path(points,adjacency,start_node,end_node,set(parent_nodes.tolist()))
    if backbone is None:return {'status':'disconnected_parent_backbone'}
    components=off_backbone_components(adjacency,backbone)
    node_component={u:i for i,c in enumerate(components) for u in c['nodes']}
    return dict(status='graph_extracted',points=points,coords=coords,adjacency=adjacency,
        backbone=backbone,inside=inside,components=components,node_component=node_component,
        tree=cKDTree(points),seconds=time.perf_counter()-start,
        node_count=len(points),edge_count=len(edges),axis_zyx=axis,
        caveat='Shortest backbone constrained to supplied parent; off-backbone cycles are not repaired')


def review_candidate(pred,data,context):
    if context['status']!='graph_extracted':return {'decision':'unresolved','reason':context['status']}
    points=context['points'];adjacency=context['adjacency'];image=data['roi']
    spacing=np.array(image.GetSpacing())[::-1]
    # Seed localization must reach an exterior skeleton, not a nearby aortic
    # centreline. Search local alternatives and preserve ambiguity.
    distances,ids=context['tree'].query(pred['seed_xyz_mm'],k=min(16,len(points)))
    choices=[(float(d),int(i)) for d,i in zip(np.atleast_1d(distances),np.atleast_1d(ids))
             if not context['inside'][i] and d<=max(float(pred['radius_mm']),float(max(spacing)))]
    if not choices:return {'decision':'unresolved','reason':'seed_not_near_exterior_skeleton'}
    _,node=choices[0];component=context['components'][context['node_component'][node]]
    record=dict(component_id=context['node_component'][node],attachment_nodes=component['attachments'],
                seed_to_skeleton_mm=choices[0][0],component_cyclic=component['cyclic'])
    if is_unbranched_return(component,adjacency):
        a,b=component['attachments'];allowed=set(component['nodes'])|{a,b}
        route=shortest_path(points,adjacency,a,b,allowed)
        from src.daughter_geometry import path_lumen_supported
        local=np.array([image.TransformPhysicalPointToContinuousIndex(v.tolist()) for v in points[route]])[:,::-1]*spacing
        supported=path_lumen_supported(local,spacing,data['parent']|data['added'],np.zeros_like(data['parent']))
        separation=float(np.linalg.norm(points[a]-points[b]))
        exterior=[u for u in route if not context['inside'][u]]
        exterior_length=sum(float(np.linalg.norm(points[u]-points[v])) for u,v in zip(route[:-1],route[1:])
                            if not context['inside'][u] and not context['inside'][v])
        record.update(return_route_xyz_mm=points[route].tolist(),return_route_supported=bool(supported),
            attachment_separation_mm=separation,exterior_return_length_mm=exterior_length)
        if supported and separation>=2*max(spacing) and exterior_length>=5:
            return {**record,'decision':'defer_return_connection','reason':'unbranched_path_reconnects_to_aortic_backbone',
                'anatomical_confirmation':'unresolved; possible segmentation bridge or anatomical reconnection'}
    if len(component['attachments'])!=1 or component['cyclic']:
        return {**record,'decision':'unresolved','reason':'multiple_aortic_attachments_or_cycle'}
    root=component['attachments'][0]
    route=shortest_path(points,adjacency,root,node,set(component['nodes'])|{root})
    transitions=[i for i in range(1,len(route)) if context['inside'][route[i-1]] and not context['inside'][route[i]]]
    if len(transitions)!=1:return {**record,'decision':'unresolved','reason':'no_unique_parent_exit'}
    index=transitions[0];a=points[route[index-1]];b=points[route[index]]
    # Bisect the actual parent voxel-cell boundary along the skeleton edge.
    for _ in range(30):
        mid=(a+b)/2;q=np.array(image.TransformPhysicalPointToContinuousIndex(mid.tolist()))[::-1]
        cell=np.floor(q+.5).astype(int)
        if data['parent'][tuple(cell)]:a=mid
        else:b=mid
    exit_point=(a+b)/2
    path=np.vstack([exit_point,points[route[index:]]])
    from src.daughter_geometry import path_lumen_supported
    local=np.array([image.TransformPhysicalPointToContinuousIndex(v.tolist()) for v in path])[:,::-1]*spacing
    if not path_lumen_supported(local,spacing,data['added'],data['parent']):
        return {**record,'decision':'unresolved','reason':'skeleton_exit_path_not_lumen_supported'}
    error=float(np.linalg.norm(exit_point-pred['ostium_xyz_mm']))
    tolerance=max(float(np.linalg.norm(spacing)),float(pred['origin_diameter_mm'])/2)
    arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
    junctions=[(route[j],float(arc[j-index+1])) for j in range(index,len(route)) if len(adjacency[route[j]])>=3]
    record.update(backbone_junction_xyz_mm=points[root].tolist(),wall_exit_xyz_mm=exit_point.tolist(),
        wall_exit_disagreement_mm=error,wall_exit_tolerance_mm=tolerance,
        path_from_wall_xyz_mm=path.tolist(),first_downstream_junction=junctions[0] if junctions else None)
    if error>tolerance:return {**record,'decision':'conflicting_origin','reason':'rooted_tree_exits_aorta_elsewhere'}
    if junctions and junctions[0][1]<5:
        return {**record,'decision':'unresolved','reason':'downstream_split_before_seed'}
    return {**record,'decision':'tree_supported','reason':'single_backbone_attachment_and_agreeing_wall_exit',
            'anatomical_confirmation':'pending'}


def review_groups(groups,data):
    context=build_context(data);retained=[];deferred=[]
    for group in groups:
        pred=group['representative'];evidence=review_candidate(pred,data,context)
        pred['aortic_tree_review']=evidence
        if evidence['decision']=='defer_return_connection':
            group['group_status']='deferred_non_tree_return_connection';deferred.append(group)
        else:retained.append(group)
    return retained,deferred,{k:context[k] for k in ('status','seconds','node_count','edge_count','caveat') if k in context}
