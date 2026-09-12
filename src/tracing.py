"""Skeleton graph tracing, 5 mm validation, physical geometry and deduplication."""

import numpy as np
from scipy import ndimage as ndi
from scipy.sparse.csgraph import dijkstra, minimum_spanning_tree
from skimage.graph import pixel_graph
from skimage.morphology import skeletonize

from .types import DetectedBranch, physical


def point_along_path(path, distance_mm):
    lengths = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    if distance_mm > lengths[-1] + 1e-6:
        raise ValueError("Path is shorter than the requested seed distance")
    return np.array([np.interp(distance_mm, lengths, path[:, axis]) for axis in range(3)])


def _path_to_root(predecessors, target):
    path = [target]
    while predecessors[path[-1]] >= 0:
        path.append(int(predecessors[path[-1]]))
    return path[::-1]


def _smooth_path(path, spacing_mm):
    """Reduce digital stair-step length bias before placing a 5 mm seed."""
    lengths = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    unique = np.r_[True, np.diff(lengths) > 1e-6]
    path, lengths = path[unique], lengths[unique]
    if len(path) < 3:
        return path
    sampling = max(spacing_mm / 2, 0.2)
    samples = np.linspace(0, lengths[-1], max(3, int(lengths[-1] / sampling) + 1))
    resampled = np.column_stack([np.interp(samples, lengths, path[:, a]) for a in range(3)])
    smoothed = ndi.gaussian_filter1d(resampled, sigma=0.6 / sampling, axis=0, mode="nearest")
    smoothed[0], smoothed[-1] = path[0], path[-1]
    return smoothed


def _path_confidence(candidate, path, radius, vesselness, roi, config):
    """Return a transparent 0--1 confidence and its constituent evidence."""
    length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
    sample_zyx = np.array([roi.image.TransformPhysicalPointToContinuousIndex(tuple(p))[::-1]
                           for p in path])
    path_vesselness = ndi.map_coordinates(vesselness, sample_zyx.T, order=1, mode="nearest")
    path_radius = ndi.map_coordinates(radius, sample_zyx.T, order=1, mode="nearest")
    radius_cv = float(np.std(path_radius) / max(np.mean(path_radius), 1e-6))
    outward = physical(roi.image, candidate.root_zyx) - path[0]
    outward /= max(np.linalg.norm(outward), 1e-6)
    direction = path[min(len(path) - 1, 2)] - path[0]
    direction /= max(np.linalg.norm(direction), 1e-6)
    evidence = {
        "contact": float(np.clip(candidate.score / 0.12, 0, 1)),
        "vesselness": float(np.clip(np.mean(path_vesselness), 0, 1)),
        "path_length": float(np.clip(length / config.trace_length_mm, 0, 1)),
        "radius_stability": float(np.clip(1 - 2 * radius_cv, 0, 1)),
        "outward_direction": float(np.clip((direction @ outward + 1) / 2, 0, 1)),
    }
    confidence = (0.20 * evidence["contact"] + 0.30 * evidence["vesselness"]
                  + 0.25 * evidence["path_length"] + 0.15 * evidence["radius_stability"]
                  + 0.10 * evidence["outward_direction"])
    return float(confidence), evidence


def _skeleton_graph(lumen, roi):
    """Thin each segmentation once, not the entire ROI for every retry."""
    skeleton = skeletonize(lumen | roi.aorta, method="lee")
    skeleton &= ~roi.aorta & (roi.distance >= roi.spacing_mm)
    graph, flat = pixel_graph(skeleton, connectivity=3, spacing=[roi.spacing_mm] * 3)
    return graph, np.column_stack(np.unravel_index(flat, skeleton.shape))


def _trace_candidate(candidate, roi, context, config, graph, coords, contact_id, report):
    """Identical topology, connector and path validation for BOTH segmentations."""
    def reject(reason):
        report["rejected"] = reason

    def reject_target(reason):
        counts = report["target_rejections"]
        counts[reason] = counts.get(reason, 0) + 1

    if not len(coords):
        reject("empty_skeleton")
        return None

    # A local graph prevents crossing back through the aorta or walking far downstream.
    allowed = (context.labels[tuple(coords.T)] == candidate.component_id)
    allowed &= roi.distance[tuple(coords.T)] >= max(roi.spacing_mm, roi.distance[tuple(candidate.root_zyx)] - 0.8)
    allowed &= np.linalg.norm((coords - candidate.ostium_zyx) * roi.spacing_mm, axis=1) <= config.fallback_radius_mm
    selection = np.flatnonzero(allowed)
    if not selection.size:
        reject("no_skeleton_near_contact")
        return None
    local_coords = coords[selection]
    root = int(np.argmin(np.linalg.norm(local_coords - candidate.root_zyx, axis=1)))
    gap = np.linalg.norm(local_coords[root] - candidate.root_zyx) * roi.spacing_mm
    if gap > max(3.0, context.radius[tuple(candidate.root_zyx)]):
        reject("disconnected_centerline")
        return None
    connector = np.linspace(candidate.root_zyx, local_coords[root], max(2, int(gap / roi.spacing_mm * 3)))
    if not np.all(context.lumen[tuple(np.rint(connector).astype(int).T)]):
        reject("centerline_connector_leaves_lumen")
        return None
    local_graph = graph[selection][:, selection].tocsr()
    # Collapse digital skeleton cycles with SciPy's deterministic minimum spanning forest.
    tree = minimum_spanning_tree(local_graph)
    tree = (tree + tree.T).tocsr()
    distances, predecessors = dijkstra(tree, directed=False, indices=root,
                                       return_predecessors=True, limit=18)
    reachable = np.flatnonzero(np.isfinite(distances))
    children = [[] for _ in selection]
    for node in reachable:
        if predecessors[node] >= 0:
            children[predecessors[node]].append(node)
    height = np.zeros(len(selection))
    for node in reachable[np.argsort(distances[reachable])[::-1]]:
        parent = predecessors[node]
        if parent >= 0:
            height[parent] = max(height[parent], height[node] + distances[node] - distances[parent])
    targets = [i for i in reachable if not children[i] and distances[i] >= 2]
    best = None
    for target in targets:
        node_path = _path_to_root(predecessors, target)
        report["max_length_before_split_mm"] = max(report["max_length_before_split_mm"], float(distances[target]))
        # Stop at the first junction whose two outgoing arms persist beyond pixel spurs.
        for j, node in enumerate(node_path):
            substantial = [child for child in children[node]
                           if height[child] + distances[child] - distances[node] >= 2.5]
            if len(substantial) > 1:
                node_path = node_path[:j + 1]
                break
        path_zyx = np.vstack([candidate.ostium_zyx, candidate.root_zyx, local_coords[node_path]])
        path = _smooth_path(physical(roi.image, path_zyx), roi.spacing_mm)
        length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
        report["max_length_mm"] = max(report["max_length_mm"], length)
        if length < config.min_length_mm:
            reject_target("short_or_early_split")
            continue
        if length > config.trace_length_mm:
            cumulative = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
            path = np.vstack([path[cumulative < config.trace_length_mm],
                              point_along_path(path, config.trace_length_mm)])
        seed = point_along_path(path, config.min_length_mm)
        seed_zyx = np.array(roi.image.TransformPhysicalPointToContinuousIndex(tuple(seed)))[::-1]
        wall_distance = float(ndi.map_coordinates(roi.distance, seed_zyx[:, None], order=1)[0])
        if wall_distance < 2.5:
            reject_target("wall_hugging")
            continue
        radius = float(ndi.map_coordinates(context.radius, seed_zyx[:, None], order=1)[0])
        if not config.min_radius_mm <= radius <= config.max_radius_mm:
            reject_target("radius")
            continue
        # Do not validate a branch with samples outside image coverage or segmented lumen.
        fine_path = np.vstack([point_along_path(path, d) for d in np.r_[np.arange(
            0, min(length, config.trace_length_mm), roi.spacing_mm / 2), min(length, config.trace_length_mm)]])
        fine_zyx = np.array([roi.image.TransformPhysicalPointToContinuousIndex(tuple(p))[::-1]
                             for p in fine_path])
        inside = np.all((fine_zyx >= 0) & (fine_zyx <= np.array(roi.ct.shape) - 1), axis=1)
        if not inside.all():
            reject_target("outside_coverage")
            continue
        if not np.all(ndi.map_coordinates((context.lumen | roi.aorta).astype(np.uint8),
                                          fine_zyx.T, order=0, mode="constant")):
            reject_target("path_leaves_lumen")
            continue
        confidence, evidence = _path_confidence(candidate, path, context.radius,
                                                context.vesselness, roi, config)
        if best is None or confidence > best.score:
            direction = seed - path[0]
            direction /= np.linalg.norm(direction)
            best = DetectedBranch(path[0], seed, radius, direction, path, confidence, contact_id)
            report["confidence"] = confidence
            report["confidence_evidence"] = evidence
    if best is None:
        reject("short_split_nonoutward_or_invalid_radius")
    else:
        report["accepted"] = True
    return best


def _trace_report():
    return {"max_length_mm": 0.0, "max_length_before_split_mm": 0.0,
            "target_rejections": {}}


def analyze_candidates(candidates, roi, context, config):
    from dataclasses import replace

    graph, coords = _skeleton_graph(context.lumen, roi)
    fallback_graph = fallback_coords = fallback_context = None
    branches, reports, rejections = [], [], {}
    for contact_id, candidate in enumerate(candidates):
        primary = _trace_report()
        best = _trace_candidate(candidate, roi, context, config, graph, coords, contact_id, primary)
        report = {"contact_id": contact_id,
                  "ostium_xyz_mm": physical(roi.image, candidate.ostium_zyx).tolist(),
                  "contact_voxels": len(candidate.contact_voxels), "primary": primary}
        report.update(primary)
        needs_retry = best is None or best.score < config.confidence_fallback_threshold
        retry = {"attempted": False, "result": "primary_confidence_sufficient"}
        if needs_retry:
            if context.fallback_lumen is None or context.fallback_radius is None:
                retry["result"] = "fallback_not_available"
            else:
                # Retry every primary rejection, including empty skeletons and gaps.
                if fallback_context is None:
                    labels, _ = ndi.label(context.fallback_lumen, structure=np.ones((3, 3, 3)))
                    fallback_context = replace(context, lumen=context.fallback_lumen,
                                               radius=context.fallback_radius, labels=labels)
                    fallback_graph, fallback_coords = _skeleton_graph(context.fallback_lumen, roi)
                retry = _trace_report()
                retry["attempted"] = True
                root_component = int(fallback_context.labels[tuple(candidate.root_zyx)])
                fallback = None
                if root_component:
                    fallback_candidate = replace(candidate, component_id=root_component)
                    fallback = _trace_candidate(fallback_candidate, roi, fallback_context, config,
                                                fallback_graph, fallback_coords, contact_id, retry)
                else:
                    retry["rejected"] = "fallback_root_not_in_lumen"
                retry["result"] = "fallback_accepted" if fallback is not None else retry.get("rejected")
                if fallback is not None and (best is None or fallback.score > best.score):
                    best = fallback
                    retry["selected"] = True
                    report["confidence"] = fallback.score
                    report["confidence_evidence"] = retry["confidence_evidence"]
        report["fallback"] = retry
        if best is None:
            reason = primary.get("rejected", "invalid_trace")
            rejections[reason] = rejections.get(reason, 0) + 1
        else:
            report.pop("rejected", None)
            report["accepted"] = True
            branches.append(best)
        reports.append(report)
    result = deduplicate_branches(branches)
    context.diagnostics.update(trace_rejections=rejections, traced_count=len(branches),
                               duplicates_removed=len(branches) - len(result), detected_count=len(result),
                               trace_candidates=reports)
    return result


def deduplicate_branches(branches):
    """Suppress only near-identical origins and paths, preserving nearby separate openings."""
    kept = []
    for branch in sorted(branches, key=lambda b: -b.score):
        duplicate = any(
            np.linalg.norm(branch.ostium_xyz_mm - other.ostium_xyz_mm) < 1.0
            and np.linalg.norm(branch.seed_xyz_mm - other.seed_xyz_mm) < 1.5
            and branch.direction_xyz @ other.direction_xyz > 0.9
            for other in kept
        )
        if not duplicate:
            kept.append(branch)
    return sorted(kept, key=lambda b: tuple(b.ostium_xyz_mm[::-1]))
