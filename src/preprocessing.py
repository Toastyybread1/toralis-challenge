"""Phase 1 loading. SimpleITK indices are XYZ; NumPy arrays are ZYX."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
import itertools

import numpy as np
import SimpleITK as sitk

from .types import Config, PreparedCase


@dataclass
class Case:
    image: sitk.Image
    aorta_mask: sitk.Image
    ct_zyx: np.ndarray
    mask_zyx: np.ndarray


def verify_geometry(image: sitk.Image, mask: sitk.Image) -> None:
    """Require matching scalar 3D grids; never silently align a mask."""
    for name, volume in (("CT", image), ("mask", mask)):
        if volume.GetDimension() != 3 or volume.GetNumberOfComponentsPerPixel() != 1:
            raise ValueError(f"{name} must be a scalar 3D image")
        direction = np.asarray(volume.GetDirection()).reshape(3, 3)
        if (not np.all(np.isfinite(volume.GetOrigin()))
                or not np.all(np.isfinite(volume.GetSpacing()))
                or np.any(np.asarray(volume.GetSpacing()) <= 0)
                or not np.isfinite(direction).all()
                or abs(np.linalg.det(direction)) < 1e-6
                or not np.allclose(np.linalg.norm(direction, axis=0), 1, atol=1e-5)):
            raise ValueError(f"{name} has invalid physical geometry")
    mismatches = []
    for field in ("Size", "Spacing", "Origin", "Direction"):
        left = getattr(image, f"Get{field}")()
        right = getattr(mask, f"Get{field}")()
        matches = left == right if field == "Size" else np.allclose(
            left, right, rtol=0, atol=1e-5
        )
        if not matches:
            mismatches.append(f"{field}: CT={left}, mask={right}")
    if mismatches:
        raise ValueError("CT/mask geometry mismatch: " + "; ".join(mismatches))


def read_nifti(path: str | Path) -> sitk.Image:
    """Handle gzip payloads mislabeled .nii without modifying the dataset."""
    path = Path(path)
    with path.open("rb") as stream:
        compressed = stream.read(2) == b"\x1f\x8b"
    if compressed and not str(path).lower().endswith(".gz"):
        with tempfile.TemporaryDirectory(prefix="toralis-nifti-") as directory:
            alias = Path(directory) / "volume.nii.gz"
            try:
                alias.symlink_to(path.resolve())
            except OSError:
                shutil.copyfile(path, alias)
            return _read_nifti_geometry(alias)
    return _read_nifti_geometry(path)


def _read_nifti_geometry(path: Path) -> sitk.Image:
    try:
        return sitk.ReadImage(str(path))
    except RuntimeError as error:
        if "orthonormal direction cosines" not in str(error):
            raise
        # ITK's NIfTI reader rejects shear. Preserve the file's exact affine in
        # a SimpleITK image, then explicitly resample the inference ROI below.
        import nibabel as nib
        source = nib.load(str(path))
        if len(source.shape) != 3:
            raise ValueError("CT and mask must be scalar 3D NIfTI images") from error
        unit = source.header.get_xyzt_units()[0]
        factor = {"mm": 1, "meter": 1000, "micron": 0.001, "unknown": 1}[unit]
        affine = source.affine.copy()
        affine[:3, :] *= factor
        affine[:2, :] *= -1  # NIfTI RAS to SimpleITK LPS.
        spacing = np.linalg.norm(affine[:3, :3], axis=0)
        direction = affine[:3, :3] / spacing
        if not np.isfinite(affine).all() or abs(np.linalg.det(direction)) < 1e-6:
            raise ValueError("NIfTI affine is singular or nonfinite") from error
        image = sitk.GetImageFromArray(np.ascontiguousarray(np.asanyarray(source.dataobj).transpose(2, 1, 0)))
        image.SetSpacing(spacing.tolist())
        image.SetOrigin(affine[:3, 3].tolist())
        image.SetDirection(direction.ravel().tolist())
        image.SetMetaData("toralis_geometry_source", "Exact NIfTI affine; shear preserved via nibabel fallback")
        return image


def load_case(image_path: str | Path, mask_path: str | Path) -> Case:
    """Load NIfTI inputs, validate alignment and a nonempty 0/1 mask."""
    for path in (image_path, mask_path):
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        if not str(path).lower().endswith((".nii", ".nii.gz")):
            raise ValueError(f"Expected a NIfTI file: {path}")
    image = read_nifti(image_path)
    mask = read_nifti(mask_path)
    verify_geometry(image, mask)
    ct = sitk.GetArrayFromImage(image)
    labels = sitk.GetArrayFromImage(mask)
    if not np.isfinite(ct).all():
        raise ValueError("CT contains nonfinite intensities")
    if not np.all((labels == 0) | (labels == 1)):
        raise ValueError("Aorta mask must contain only 0 and 1")
    if not np.any(labels):
        raise ValueError("Aorta mask is empty")
    return Case(image, mask, ct, labels.astype(bool))


def crop_case(case: Case, margin_mm: float = 20.0) -> Case:
    """Nika's aorta crop, retaining image geometry and a physical margin."""
    if not np.isfinite(margin_mm) or margin_mm < 0:
        raise ValueError("Crop margin must be finite and nonnegative")
    if not case.mask_zyx.any():
        raise ValueError("Aorta mask is empty")
    occupied = [np.flatnonzero(case.mask_zyx.any(axis=tuple(a for a in range(3) if a != axis)))
                for axis in range(3)]
    spatial = np.array(case.image.GetDirection()).reshape(3, 3) @ np.diag(case.image.GetSpacing())
    # Inverse rows convert a physical-radius ball into index margins, also for shear.
    margin = np.ceil(margin_mm * np.linalg.norm(np.linalg.inv(spatial), axis=1))[::-1].astype(int)
    start = np.maximum(0, np.array([v[0] for v in occupied]) - margin)
    stop = np.minimum(case.mask_zyx.shape, np.array([v[-1] + 1 for v in occupied]) + margin)
    size = (stop - start)[::-1].tolist()
    image = sitk.RegionOfInterest(case.image, size, start[::-1].tolist())
    mask = sitk.RegionOfInterest(case.aorta_mask, size, start[::-1].tolist())
    slices = tuple(slice(int(a), int(b)) for a, b in zip(start, stop))
    return Case(image, mask, case.ct_zyx[slices], case.mask_zyx[slices])


def orthonormal_reference(image: sitk.Image, spacing_xyz=None, *, max_voxels=None,
                          preserve_aligned_grid=False) -> sitk.Image:
    """Nika's nearest-orthogonal grid, enclosing voxel boundaries without clipping.

    Reflections are valid orientations and are retained. The detector supplies
    only its cropped ROI and a voxel budget; full-volume repair is optional.
    preserve_aligned_grid retains the detector's established center sampling
    when the source direction is already orthogonal.
    """
    verify_geometry(image, image)
    direction = np.array(image.GetDirection()).reshape(3, 3)
    u, _, vt = np.linalg.svd(direction)
    corrected = u @ vt
    angles = np.degrees(np.arccos(np.clip(np.sum(direction * corrected, axis=0), -1, 1)))
    spacing = np.array(image.GetSpacing() if spacing_xyz is None else spacing_xyz, dtype=float)
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Target spacing requires three finite positive values")
    if max_voxels is not None and (not isinstance(max_voxels, int) or max_voxels < 1):
        raise ValueError("Voxel budget must be a positive integer")
    corners = np.array(list(itertools.product(*[(-0.5, n - 0.5) for n in image.GetSize()])))
    spatial = direction @ np.diag(image.GetSpacing())
    projected = corners @ spatial.T @ corrected
    lower, upper = projected.min(axis=0), projected.max(axis=0)
    extent = upper - lower
    center_grid = preserve_aligned_grid and np.allclose(direction.T @ direction, np.eye(3),
                                                       rtol=0, atol=1e-5)
    if center_grid:
        corrected = direction
        extent = (np.array(image.GetSize()) - 1) * image.GetSpacing()

    def grid_size():
        if center_grid:
            return np.floor(extent / spacing).astype(int) + 1
        return np.maximum(1, np.ceil(extent / spacing - 1e-7).astype(int))

    size = grid_size()
    if max_voxels is not None:
        spacing *= max(1.0, (np.prod(extent / spacing) / max_voxels) ** (1 / 3))
        size = grid_size()
        while np.prod(size) > max_voxels:
            spacing *= 1.01
            size = grid_size()
    reference = sitk.Image(size.tolist(), sitk.sitkFloat32)
    reference.SetSpacing(spacing.tolist())
    reference.SetDirection(corrected.ravel().tolist())
    origin = (image.GetOrigin() if center_grid else
              (np.array(image.GetOrigin()) + corrected @ (lower + spacing / 2)).tolist())
    reference.SetOrigin(origin)
    reference.SetMetaData("toralis_max_axis_correction_degrees", str(float(angles.max())))
    return reference


def resample_case(case: Case, reference: sitk.Image | None = None) -> Case:
    """Resample CT linearly and the binary mask with nearest-neighbor interpolation."""
    verify_geometry(case.image, case.aorta_mask)
    if reference is None:
        reference = orthonormal_reference(case.image)
    image = sitk.Resample(case.image, reference, sitk.Transform(), sitk.sitkLinear, -1024, sitk.sitkFloat32)
    mask = sitk.Resample(case.aorta_mask, reference, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
    for key in reference.GetMetaDataKeys():
        image.SetMetaData(key, reference.GetMetaData(key))
    aorta = sitk.GetArrayFromImage(mask).astype(bool)
    if not aorta.any():
        raise ValueError("Aorta disappeared on the working grid; decrease working spacing")
    return Case(image, mask, sitk.GetArrayFromImage(image), aorta)


def read_nifti_pair(image_path: str | Path, mask_path: str | Path):
    """Validated, orthogonal image pair for Nika's preprocessing callers.

    Inference uses load_case + prepare_case to resample only a bounded ROI.
    """
    case = load_case(image_path, mask_path)
    direction = np.array(case.image.GetDirection()).reshape(3, 3)
    if not np.allclose(direction.T @ direction, np.eye(3), rtol=0, atol=1e-5):
        case = resample_case(case)
    return case.image, case.aorta_mask


def index_to_physical(image: sitk.Image, index_xyz) -> tuple[float, ...]:
    """Convert an integer XYZ voxel index to physical LPS millimetres."""
    index = np.asarray(index_xyz)
    if index.shape != (3,) or not np.isfinite(index).all() or np.any(index != np.floor(index)):
        raise ValueError("Expected three integer XYZ indices")
    if np.any(index < 0) or np.any(index >= image.GetSize()):
        raise ValueError("Index is outside the image")
    return image.TransformIndexToPhysicalPoint([int(i) for i in index])


def mask_center_physical(case: Case) -> tuple[float, ...]:
    """Return the mask centroid without allocating a full coordinate grid."""
    counts = case.mask_zyx.sum()
    center_zyx = [
        float(np.dot(np.arange(case.mask_zyx.shape[axis]),
                     case.mask_zyx.sum(axis=tuple(a for a in range(3) if a != axis))) / counts)
        for axis in range(3)
    ]
    return case.image.TransformContinuousIndexToPhysicalPoint(center_zyx[::-1])


def basic_statistics(case: Case) -> dict:
    def summarize(values):
        return {"min": float(values.min()), "max": float(values.max()),
                "mean": float(values.mean(dtype=np.float64)),
                "std": float(values.std(dtype=np.float64))}

    count = int(case.mask_zyx.sum())
    return {
        "geometry_verified": True,
        "size_xyz": list(case.image.GetSize()),
        "array_shape_zyx": list(case.ct_zyx.shape),
        "spacing_xyz_mm": list(case.image.GetSpacing()),
        "origin_lps_mm": list(case.image.GetOrigin()),
        "direction": list(case.image.GetDirection()),
        "ct_dtype": str(case.ct_zyx.dtype),
        "ct_intensity": summarize(case.ct_zyx),
        "aorta_intensity": summarize(case.ct_zyx[case.mask_zyx]),
        "aorta_voxels": count,
        "aorta_volume_mm3": float(count * np.prod(case.image.GetSpacing()) *
                                  abs(np.linalg.det(np.array(case.image.GetDirection()).reshape(3, 3)))),
        "aorta_centroid_lps_mm": list(mask_center_physical(case)),
    }


def extract_aorta_surface(mask: np.ndarray) -> np.ndarray:
    from scipy import ndimage as ndi
    return mask & ~ndi.binary_erosion(mask, border_value=0)


def make_search_shell(mask: np.ndarray, spacing_zyx, thickness_mm=12.0) -> np.ndarray:
    """Physical-distance shell outside a nonempty mask."""
    from scipy import ndimage as ndi
    if not np.any(mask) or thickness_mm <= 0:
        raise ValueError("Shell requires a nonempty mask and positive thickness")
    distance = ndi.distance_transform_edt(~mask, sampling=spacing_zyx)
    return (distance > 0) & (distance <= thickness_mm)


def prepare_case(case: Case, config: Config) -> PreparedCase:
    """Crop first, then resample a bounded ROI to isotropic working voxels."""
    from scipy import ndimage as ndi

    cropped = crop_case(case, config.shell_mm + 3 * max(config.vessel_scales_mm))
    reference = orthonormal_reference(cropped.image, [config.working_spacing_mm] * 3,
                                      max_voxels=config.max_roi_voxels, preserve_aligned_grid=True)
    resampled = resample_case(cropped, reference)
    step = resampled.image.GetSpacing()[0]
    aorta = resampled.mask_zyx
    distance, nearest = ndi.distance_transform_edt(~aorta, sampling=step, return_indices=True)
    return PreparedCase(resampled.image, resampled.ct_zyx, aorta, step,
                        distance.astype(np.float32), nearest,
                        (distance > 0) & (distance <= config.shell_mm))
