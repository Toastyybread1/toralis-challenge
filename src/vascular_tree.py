"""Riffaud tree definitions plus organiser-specific proximal stopping rules.

Input must be an already extracted centreline tree in physical millimetres.
This module does not extract a tree from CT or segmentation. No anatomical
naming, minimum long-branch pruning, or forced spanning-tree repair is applied.
"""
import numpy as np


def validate_tree(points_xyz_mm, edges):
    points=np.asarray(points_xyz_mm,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or not len(points) or not np.isfinite(points).all():
        raise ValueError('Expected finite N by 3 physical points')
    adjacency=[set() for _ in points];seen=set()
    for edge in edges:
        if len(edge)!=2 or any(not isinstance(v,(int,np.integer)) for v in edge):
            raise ValueError('Edges must contain two integer node indices')
        a,b=map(int,edge)
        if min(a,b)<0 or max(a,b)>=len(points) or a==b:raise ValueError('Invalid edge')
        key=tuple(sorted((a,b)))
        if key in seen:raise ValueError('Duplicate edge')
        if np.linalg.norm(points[a]-points[b])<=1e-10:raise ValueError('Zero-length edge')
        seen.add(key);adjacency[a].add(b);adjacency[b].add(a)
    visited={0};stack=[0]
    while stack:
        for node in adjacency[stack.pop()]:
            if node not in visited:visited.add(node);stack.append(node)
    if len(visited)!=len(points):raise ValueError('Disconnected graph; unresolved topology')
    if len(seen)!=len(points)-1:raise ValueError('Cyclic graph; unresolved topology')
    return points,adjacency


def follow_primary_branch(points_xyz_mm, edges, origin_node, first_node, max_length_mm=10.,seed_distance_mm=5.):
    """Follow a selected outgoing edge to the first split, leaf, or length cap.

    The caller must place origin_node at the supplied parent boundary and select
    the outgoing daughter edge. The origin's own degree is intentionally ignored.
    A split before 5 mm is unresolved; a leaf before 10 mm is incomplete.
    Degree-three topology is a candidate bifurcation, not anatomical confirmation.
    """
    points,adjacency=validate_tree(points_xyz_mm,edges)
    if not np.isfinite([max_length_mm,seed_distance_mm]).all() or not 0<seed_distance_mm<=max_length_mm:
        raise ValueError('Require 0 < seed distance <= maximum length')
    if not isinstance(origin_node,(int,np.integer)) or not 0<=origin_node<len(points):raise ValueError('Invalid origin node')
    if first_node not in adjacency[origin_node]:raise ValueError('First node must neighbour origin')
    path=[points[origin_node].copy()];node_path=[int(origin_node)]
    previous=origin_node;current=first_node;length=0.;split=None;outgoing=[]
    while True:
        segment=float(np.linalg.norm(points[current]-path[-1]))
        if length+segment>max_length_mm:
            path.append(path[-1]+(points[current]-path[-1])*(max_length_mm-length)/segment)
            length=max_length_mm;stop='length_limit';break
        path.append(points[current].copy());node_path.append(int(current));length+=segment
        if len(adjacency[current])>=3:
            split=int(current);outgoing=sorted(int(n) for n in adjacency[current] if n!=previous)
            stop='graph_bifurcation';break
        if length>=max_length_mm-1e-10:stop='length_limit';break
        forward=adjacency[current]-{previous}
        if not forward:stop='leaf';break
        previous,current=current,next(iter(forward))
    path=np.asarray(path);arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]
    seed=None
    if length>=seed_distance_mm-1e-10:
        seed=[float(np.interp(seed_distance_mm,arc,path[:,k])) for k in range(3)]
    status=('ambiguous_early_bifurcation' if split is not None and seed is None else
            'bifurcation_review_required' if split is not None else
            'length_complete' if stop=='length_limit' else 'incomplete_leaf')
    return {'path_xyz_mm':path.tolist(),'path_length_mm':length,'visited_node_indices':node_path,
            'seed_xyz_mm':seed,'stop_reason':stop,'tracking_status':status,
            'bifurcation_node':split,'outgoing_node_indices':outgoing,
            'bifurcation_xyz_mm':points[split].tolist() if split is not None else None,
            'anatomical_confirmation':'pending'}
