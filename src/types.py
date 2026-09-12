"""Shared interfaces. Array indices are ZYX; physical coordinates are LPS XYZ."""

from dataclasses import dataclass, field

import numpy as np
import SimpleITK as sitk


@dataclass(frozen=True)
class Config:
    working_spacing_mm: float = 0.8
    shell_mm: float = 12.0
    min_radius_mm: float = 0.8
    max_radius_mm: float = 6.0
    min_length_mm: float = 5.0
    trace_length_mm: float = 10.0
    contact_distance_mm: float = 1.6
    fallback_radius_mm: float = 14.0
    confidence_fallback_threshold: float = 0.62
    max_roi_voxels: int = 3_000_000
    vessel_scales_mm: tuple[float, ...] = (0.8, 1.4, 2.2)

    def __post_init__(self):
        values = [self.working_spacing_mm, self.shell_mm, self.min_radius_mm,
                  self.max_radius_mm, self.min_length_mm, self.trace_length_mm,
                  self.contact_distance_mm, self.fallback_radius_mm, *self.vessel_scales_mm]
        if not np.isfinite(values).all() or min(values) <= 0:
            raise ValueError("Configuration distances must be finite and positive")
        if self.min_radius_mm > self.max_radius_mm:
            raise ValueError("Minimum radius cannot exceed maximum radius")
        if self.min_length_mm != 5.0:
            raise ValueError("The competition seed distance is fixed at 5 mm")
        if self.trace_length_mm < self.min_length_mm or self.shell_mm < self.trace_length_mm:
            raise ValueError("Require shell >= trace length >= 5 mm")
        if self.max_roi_voxels < 1000:
            raise ValueError("ROI voxel budget is too small")
        if not 0 < self.confidence_fallback_threshold < 1:
            raise ValueError("Fallback confidence threshold must be between zero and one")


@dataclass
class PreparedCase:
    image: sitk.Image
    ct: np.ndarray
    aorta: np.ndarray
    spacing_mm: float
    distance: np.ndarray
    nearest_aorta: np.ndarray
    shell: np.ndarray


@dataclass
class CandidateBranch:
    contact_voxels: np.ndarray
    root_zyx: np.ndarray
    ostium_zyx: np.ndarray
    component_id: int
    score: float


@dataclass
class DetectionContext:
    lumen: np.ndarray
    vesselness: np.ndarray
    radius: np.ndarray
    labels: np.ndarray
    diagnostics: dict = field(default_factory=dict)
    fallback_lumen: np.ndarray | None = None
    fallback_radius: np.ndarray | None = None


@dataclass
class DetectedBranch:
    ostium_xyz_mm: np.ndarray
    seed_xyz_mm: np.ndarray
    radius_mm: float
    direction_xyz: np.ndarray
    path_xyz_mm: np.ndarray
    score: float
    contact_id: int


def physical(image: sitk.Image, indices_zyx: np.ndarray) -> np.ndarray:
    indices = np.asarray(indices_zyx, dtype=float)
    return np.array([image.TransformContinuousIndexToPhysicalPoint(tuple(p[::-1]))
                     for p in indices.reshape(-1, 3)]).reshape(indices.shape)
