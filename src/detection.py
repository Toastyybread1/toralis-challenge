"""Aorta-anchored intensity/vesselness segmentation and separate wall openings."""

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import frangi

from .types import CandidateBranch, Config, DetectionContext, PreparedCase


def detect_candidates(roi: PreparedCase, config: Config):
    spacing = roi.spacing_mm
    smooth = ndi.gaussian_filter(roi.ct, sigma=0.45 / spacing)
    interior = ndi.distance_transform_edt(roi.aorta, sampling=spacing) >= 1.0
    values = smooth[interior if interior.any() else roi.aorta]
    median = float(np.median(values))
    spread = max(15.0, float(np.median(np.abs(values - median))) * 1.4826)
    low = max(60.0, 0.55 * median)
    high = max(low, median - 2.5 * spread)
    upper = max(700.0, median + 8 * spread)
    normalized = np.clip((smooth - low) / max(median - low, 1), 0, 1.5)
    vesselness = frangi(normalized, sigmas=[s / spacing for s in config.vessel_scales_mm],
                       black_ridges=False, alpha=0.5, beta=0.5, gamma=0.15)
    vesselness[~roi.shell] = 0
    positive = vesselness[vesselness > 0]
    scale = max(float(np.percentile(positive, 99)) if positive.size else 1, 1e-6)
    vesselness = np.clip(vesselness / scale, 0, 1).astype(np.float32)
    lumen = roi.shell & ((smooth >= high) | ((smooth >= low) & (vesselness >= 0.08)))
    lumen &= roi.ct <= upper
    # Retain a permissive mask only for a local retry after normal tracing
    # fails; primary candidate detection remains conservative.
    fallback_low = max(40.0, median - 3.5 * spread)
    fallback_lumen = roi.shell & (smooth >= fallback_low) & (roi.ct <= upper)
    fallback_lumen &= (vesselness >= 0.025) | (smooth >= median - 1.25 * spread)
    fallback_lumen |= lumen
    # Radius uses the lumen union, so the aortic wall is not an artificial lumen edge.
    radius = ndi.distance_transform_edt(lumen | roi.aorta, sampling=spacing).astype(np.float32)
    labels, _ = ndi.label(lumen, structure=np.ones((3, 3, 3)))
    level = max(config.contact_distance_mm, 1.5 * spacing)
    contact = lumen & (roi.distance >= level) & (roi.distance < level + spacing)
    contact &= radius >= max(0.6, config.min_radius_mm * 0.75)
    openings, count = ndi.label(contact, structure=np.ones((3, 3, 3)))
    mask_points = np.argwhere(roi.aorta)[::max(1, int(roi.aorta.sum()) // 10000)]
    center = mask_points.mean(axis=0)
    _, _, axes = np.linalg.svd((mask_points - center) * spacing, full_matrices=False)
    long_axis = axes[0]
    projections = (mask_points - center) @ long_axis * spacing
    min_projection, max_projection = projections.min(), projections.max()
    candidates = []
    rejected = {"small_contact": 0, "crop_end": 0, "no_direct_connection": 0}
    for component_id, region in enumerate(ndi.find_objects(openings), 1):
        if region is None:
            continue
        coords = np.argwhere(openings[region] == component_id) + np.array([s.start for s in region])
        if len(coords) * spacing ** 2 < np.pi * config.min_radius_mm ** 2 * 0.5:
            rejected["small_contact"] += 1
            continue
        weights = radius[tuple(coords.T)] ** 2
        centroid = np.average(coords, axis=0, weights=weights)
        root = coords[np.argmin(np.sum((coords - centroid) ** 2, axis=1))]
        inside = roi.nearest_aorta[:, *root]
        outward = root - inside
        norm = np.linalg.norm(outward)
        projection = (inside - center) @ long_axis * spacing
        at_end = min(projection - min_projection, max_projection - projection) < 2.5
        if at_end and abs(outward @ long_axis) / max(norm, 1e-8) > 0.65:
            rejected["crop_end"] += 1
            continue
        line = np.linspace(inside, root, max(3, int(norm * 4) + 1))
        samples = np.rint(line).astype(int)
        if not np.all((lumen | roi.aorta)[tuple(samples.T)]):
            rejected["no_direct_connection"] += 1
            continue
        is_inside = roi.aorta[tuple(samples.T)]
        crossing = np.flatnonzero(~is_inside)[0]
        ostium = (line[crossing - 1] + line[crossing]) / 2
        candidates.append(CandidateBranch(coords, root, ostium, int(labels[tuple(root)]),
                                          float(np.mean(vesselness[tuple(coords.T)]))))
    fallback_radius = ndi.distance_transform_edt(fallback_lumen | roi.aorta, sampling=spacing).astype(np.float32)
    return candidates, DetectionContext(lumen, vesselness, radius, labels, {
        "aorta_median": median, "aorta_robust_std": spread,
        "low_threshold": low, "high_threshold": high, "upper_intensity_limit": upper,
        "contact_components": count, "candidate_count": len(candidates),
        "rejected_contacts": rejected, "working_spacing_mm": spacing,
        "roi_shape_zyx": list(roi.aorta.shape), "fallback_low_threshold": fallback_low,
    }, fallback_lumen, fallback_radius)
