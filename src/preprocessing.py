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

    occupied = [np.flatnonzero(case.mask_zyx.any(axis=tuple(a for a in range(3) if a != axis)))
                for axis in range(3)]
    spacing = np.array(case.image.GetSpacing())[::-1]
    margin = np.ceil((config.shell_mm + 3 * max(config.vessel_scales_mm)) / spacing).astype(int)
    start = np.maximum(0, np.array([v[0] for v in occupied]) - margin)
    stop = np.minimum(case.mask_zyx.shape, np.array([v[-1] + 1 for v in occupied]) + margin)
    size = (stop - start)[::-1]
    region = sitk.RegionOfInterest(case.image, size.tolist(), start[::-1].tolist())
    mask = sitk.RegionOfInterest(case.aorta_mask, size.tolist(), start[::-1].tolist())
    direction = np.array(region.GetDirection()).reshape(3, 3)
    output_direction = direction
    output_origin = region.GetOrigin()
    extent = (np.array(region.GetSize()) - 1) * region.GetSpacing()
    if not np.allclose(direction.T @ direction, np.eye(3), atol=1e-5):
        u, _, vt = np.linalg.svd(direction)
        output_direction = u @ vt
        corners = np.array([region.TransformIndexToPhysicalPoint([int(v) for v in p])
                            for p in itertools.product(*[(0, n - 1) for n in region.GetSize()])])
        projected = corners @ output_direction
        output_origin = (output_direction @ projected.min(axis=0)).tolist()
        extent = np.ptp(projected, axis=0)
    step = max(config.working_spacing_mm, (np.prod(extent) / config.max_roi_voxels) ** (1 / 3))
    output_size = np.floor(extent / step).astype(int) + 1
    while np.prod(output_size) > config.max_roi_voxels:
        step *= 1.01
        output_size = np.floor(extent / step).astype(int) + 1
    reference = sitk.Image(output_size.tolist(), sitk.sitkFloat32)
    reference.SetOrigin(output_origin)
    reference.SetDirection(output_direction.ravel().tolist())
    reference.SetSpacing([step] * 3)
    image = sitk.Resample(region, reference, sitk.Transform(), sitk.sitkLinear, -1024, sitk.sitkFloat32)
    mask_image = sitk.Resample(mask, reference, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
    aorta = sitk.GetArrayFromImage(mask_image).astype(bool)
    if not aorta.any():
        raise ValueError("Aorta disappeared on the working grid; decrease working spacing")
    distance, nearest = ndi.distance_transform_edt(~aorta, sampling=step, return_indices=True)
    return PreparedCase(image, sitk.GetArrayFromImage(image), aorta, step,
                        distance.astype(np.float32), nearest,
                        (distance > 0) & (distance <= config.shell_mm))
