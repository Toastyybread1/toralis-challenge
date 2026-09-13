"""Diagnostic first-stage aorta expansion inspired by Tahoces section 2.1.1.

The 20 mm bound is from the paper. Density estimation, acceptance thresholds,
sampling bands and connectivity are explicit adaptations, not reproduced code.
No added region is classified as a real branch or silently discarded.
"""
import numpy as np
from scipy import ndimage as ndi


def fit_intensity_model(ct, parent, distance_mm, spacing_xyz, ratio_threshold=0.6, interior_margin_mm=1.):
    """Compare smoothed histograms from parent interior and a 5--10 mm band.

    The exterior band is mixed tissue (including possible vessels), not labelled
    background. The equal-prior density ratio is not a calibrated probability.
    Reject negligible parent density to avoid accepting unsupported tail ratios.
    """
    if not 0 < ratio_threshold < 1:
        raise ValueError("Density ratio threshold must be in (0, 1).")
    if not np.isfinite(interior_margin_mm) or interior_margin_mm<0:
        raise ValueError('Interior margin must be nonnegative and finite')
    finite = np.isfinite(ct)
    inside_distance = ndi.distance_transform_edt(np.pad(parent, 1), sampling=spacing_xyz[::-1])
    interior = parent & (inside_distance[1:-1, 1:-1, 1:-1] > interior_margin_mm) & finite
    del inside_distance
    fallback = int(interior.sum()) < 32
    inside = ct[parent & finite] if fallback else ct[interior]
    outside = ct[(~parent) & (distance_mm >= 5) & (distance_mm <= 10) & finite]
    if inside.size < 2 or outside.size < 32:
        raise ValueError("Insufficient finite inside/outside samples for intensity modelling.")
    # Robust range limits sensitivity to isolated metal/extreme values. Values
    # beyond the histogram are excluded from growth rather than clipped to blood.
    lo = float(min(np.quantile(inside, .001), np.quantile(outside, .001)) - 64)
    hi = float(max(np.quantile(inside, .999), np.quantile(outside, .999)) + 64)
    edges = np.linspace(lo, hi, 513)
    centres = (edges[:-1] + edges[1:]) / 2
    width = edges[1] - edges[0]
    densities = []
    for values in (inside, outside):
        histogram = np.histogram(values, edges)[0].astype(float)
        density = ndi.gaussian_filter1d(histogram, sigma=16 / width, mode='constant')
        density /= density.sum() * width
        densities.append(density)
    inside_density, outside_density = densities
    eligible = finite & (ct >= lo) & (ct <= hi)
    values = ct[eligible]
    fi = np.interp(values, centres, inside_density, left=0, right=0)
    fo = np.interp(values, centres, outside_density, left=0, right=0)
    ratio = fi / np.maximum(fi + fo, 1e-12)
    score = np.zeros(ct.shape, dtype=np.float32)
    score[eligible] = ratio
    accepted = np.zeros(ct.shape, dtype=bool)
    accepted[eligible] = (ratio >= ratio_threshold) & (fi >= .01 * inside_density.max())
    stats = {'inside_samples': int(inside.size), 'outside_samples': int(outside.size),
             'used_whole_parent': bool(fallback or interior_margin_mm==0),'interior_margin_mm':float(interior_margin_mm), 'inside_median_hu': float(np.median(inside)),
             'outside_median_hu': float(np.median(outside)),
             'histogram_centres_hu': centres.tolist(),
             'inside_density': inside_density.tolist(), 'outside_density': outside_density.tolist()}
    return accepted, score, stats


def bounded_expansion(parent, accepted, spacing_xyz, radius_mm=20, distance_mm=None):
    """Grow face-connected accepted voxels from the parent within a metric bound.

    Return the expanded binary mask, integer labels of added regions, and
    component diagnostics. Component counts are not daughter-instance counts.
    """
    parent = np.asarray(parent, dtype=bool)
    accepted = np.asarray(accepted, dtype=bool)
    spacing = np.asarray(spacing_xyz, dtype=float)
    if parent.ndim != 3 or parent.shape != accepted.shape or not parent.any():
        raise ValueError("Expected matching 3D arrays and a nonempty parent.")
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or (spacing <= 0).any():
        raise ValueError("Expected three positive finite spacings.")
    if not np.isfinite(radius_mm) or radius_mm <= 0:
        raise ValueError("Expansion radius must be finite and positive.")
    if distance_mm is None:
        distance_mm = ndi.distance_transform_edt(~parent, sampling=spacing[::-1])
    if distance_mm.shape != parent.shape:
        raise ValueError("Distance map shape mismatch.")
    neighbourhood = ndi.generate_binary_structure(3, 1)
    domain = distance_mm <= radius_mm
    expanded = ndi.binary_propagation(parent, structure=neighbourhood,
                                      mask=parent | (domain & accepted))
    added = expanded & ~parent
    labels, count = ndi.label(added, structure=neighbourhood)
    contact = added & ndi.binary_dilation(parent, structure=neighbourhood)
    limit_surface = domain & ndi.binary_dilation(~domain, structure=neighbourhood)
    edge = np.zeros(parent.shape, dtype=bool)
    for axis in range(3):
        slices = [slice(None)] * 3
        for index in (0,-1):
            slices[axis] = index
            edge[tuple(slices)] = True
    diagnostics = []
    sizes = np.bincount(labels.ravel(), minlength=count+1)
    for component, region in enumerate(ndi.find_objects(labels), 1):
        component_mask = labels[region] == component
        contacts = component_mask & contact[region]
        _, contact_count = ndi.label(contacts, structure=neighbourhood)
        diagnostics.append({'component_id': component,
            'added_voxels': int(sizes[component]),
            'volume_mm3': float(sizes[component] * np.prod(spacing)),
            'contact_voxels': int(contacts.sum()), 'contact_patch_count': int(contact_count),
            'max_parent_distance_mm': float(distance_mm[region][component_mask].max()),
            'touches_distance_limit': bool(np.any(component_mask & limit_surface[region])),
            'touches_crop_boundary': bool(np.any(component_mask & edge[region])),
            'status': 'unclassified_expansion'})
    return expanded, labels, diagnostics


def local_leakage_block(first_labels, components, spacing_xyz, bulk_radius_mm=6.):
    """Remove bulky portions of oversized additions, preserving narrow feeders.

    A metric morphological opening (EDT erosion then dilation) marks regions
    containing a ball of radius bulk_radius_mm. Only >5000 mm3 components are
    considered; small components keep baseline handling. The 6 mm default is
    an adaptation aligned with the tracker's maximum section radius, not a
    paper-specified threshold. Broad vessels can still be removed.
    """
    spacing=np.asarray(spacing_xyz,dtype=float)[::-1]
    if spacing.shape!=(3,) or not np.isfinite(spacing).all() or (spacing<=0).any():
        raise ValueError('Positive finite spacing required')
    if not np.isfinite(bulk_radius_mm) or bulk_radius_mm<=0:
        raise ValueError('Positive finite bulk radius required')
    large=[c['component_id'] for c in components if c['volume_mm3']>5000]
    tiny=[c['component_id'] for c in components if c['volume_mm3']<2]
    oversized=np.isin(first_labels,large)
    blocked=np.isin(first_labels,tiny)
    if oversized.any():
        # Padding treats crop faces as exterior rather than infinite tissue.
        clearance=ndi.distance_transform_edt(np.pad(oversized,1),sampling=spacing)[1:-1,1:-1,1:-1]
        core=clearance>bulk_radius_mm
        if core.any():
            opened=ndi.distance_transform_edt(~core,sampling=spacing)<=bulk_radius_mm
            blocked|=oversized&opened
    return blocked
