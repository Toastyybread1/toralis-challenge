"""Derived labels on the CT grid; never infer daughter lumen from display tubes."""

from pathlib import Path
import numpy as np


def export_target(path, protected_paths=()):
    target = Path(path).expanduser().resolve()
    if not str(target).lower().endswith(('.nii', '.nii.gz')):
        raise ValueError('Choose a .nii or .nii.gz filename.')
    for source in protected_paths:
        if not source:
            continue
        source = Path(source).resolve()
        if target == source or (target.exists() and source.exists() and target.samefile(source)):
            raise ValueError('Choose a new file: original CT and mask inputs cannot be overwritten.')
    return target


def traced_labelmap(parent_kji, ijk_to_ras, paths_lps):
    """0=background, 1=current parent, 2=estimated centerlines outside parent.

    Parent wins overlaps. All branches share label 2; branch identities and
    measurements belong in prediction JSON. Sampling is in voxel space so
    oblique/anisotropic grids receive continuous 26-connected thin paths.
    """
    parent = np.asarray(parent_kji)
    matrix = np.asarray(ijk_to_ras, dtype=float)
    if parent.ndim != 3 or not all(parent.shape):
        raise ValueError('The parent labelmap must be a nonempty 3D array.')
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1]):
        raise ValueError('Invalid CT physical geometry.')
    ras_to_ijk = np.linalg.inv(matrix)
    paths_lps = list(paths_lps)
    if not paths_lps:
        raise ValueError('No traced paths are available. Run detection; JSON alone does not contain traces.')
    result = (parent != 0).astype(np.uint8)
    dimensions = np.array(parent.shape[::-1])
    for path in paths_lps:
        points = np.asarray(path, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
            raise ValueError('A traced path has invalid physical coordinates.')
        ras = points * [-1, -1, 1]
        ijk = (np.c_[ras, np.ones(len(ras))] @ ras_to_ijk.T)[:, :3]
        # Reject rather than silently clipping paths onto an image boundary.
        if np.any(ijk < -.5) or np.any(ijk >= dimensions - .5):
            raise ValueError('A trace is outside the CT grid. Check the study/result pairing.')
        for start, end in zip(ijk[:-1], ijk[1:]):
            steps = max(1, int(np.ceil(np.max(np.abs(end - start)) * 4)))
            cells = np.floor(np.linspace(start, end, steps + 1) + .5).astype(int)
            i, j, k = cells.T
            outside_parent = result[k, j, i] != 1
            result[k[outside_parent], j[outside_parent], i[outside_parent]] = 2
    return result
