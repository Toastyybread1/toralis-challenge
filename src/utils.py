# Shared NIfTI I/O and paired physical resampling. This module handles geometry,
# not branch detection. NiBabel affines and SimpleITK coordinates use different
# conventions; the file readers perform that conversion, not manual sign flips.
import os
import shutil
import tempfile

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from nibabel.processing import resample_from_to


def _prepare_readable_path(path):
    """
    Return a path that libraries can read correctly.

    Handles gzip-compressed NIfTI files that were
    incorrectly named with a .nii extension.
    """

    path = str(path)

    with open(path, "rb") as file:
        is_gzip = file.read(2) == b"\x1f\x8b"

    if is_gzip and not path.endswith(".gz"):
        with tempfile.NamedTemporaryFile(
            suffix=".nii.gz",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name

        shutil.copyfile(path, temp_path)

        return temp_path, True

    return path, False


def _load_with_nibabel(path):
    """
    Load the NIfTI fully into memory.
    """

    image = nib.load(path)

    return nib.Nifti1Image(
        np.asanyarray(image.dataobj),
        image.affine.copy(),
        image.header.copy(),
    )


def _build_orthonormal_target(image):
    """
    Build the nearest orthonormal physical grid
    while preserving the original physical volume.
    """

    affine = image.affine.copy()

    spatial = affine[:3, :3]

    spacing = np.linalg.norm(
        spatial,
        axis=0,
    )

    direction = spatial / spacing

    # Nearest orthogonal matrix using SVD
    U, _, Vt = np.linalg.svd(direction)

    corrected_direction = U @ Vt

    # How much did each axis move?
    correction_angles = []

    for axis in range(3):
        old_axis = direction[:, axis]
        new_axis = corrected_direction[:, axis]

        dot = np.clip(
            np.dot(old_axis, new_axis),
            -1.0,
            1.0,
        )

        angle = np.degrees(
            np.arccos(dot)
        )

        correction_angles.append(angle)

    # Put spacing back
    target_spatial = (
        corrected_direction
        @ np.diag(spacing)
    )

    nx, ny, nz = image.shape[:3]

    # Use voxel boundaries so we do not clip
    # any part of the original volume.
    corners = np.array([
        [x, y, z, 1.0]
        for x in (-0.5, nx - 0.5)
        for y in (-0.5, ny - 0.5)
        for z in (-0.5, nz - 0.5)
    ])

    world_corners = (
        affine @ corners.T
    ).T[:, :3]

    inverse_target_spatial = np.linalg.inv(
        target_spatial
    )

    target_coordinates = (
        inverse_target_spatial
        @ world_corners.T
    ).T

    min_coord = target_coordinates.min(
        axis=0
    )

    max_coord = target_coordinates.max(
        axis=0
    )

    target_shape = np.ceil(
        max_coord - min_coord
    ).astype(int)

    # min_coord represents the lower voxel boundary.
    # Shift half a voxel inward to get voxel centre 0.
    target_origin = target_spatial @ (
        min_coord + 0.5
    )

    target_affine = np.eye(4)

    target_affine[:3, :3] = (
        target_spatial
    )

    target_affine[:3, 3] = (
        target_origin
    )

    return (
        tuple(target_shape),
        target_affine,
        correction_angles,
    )


def _resample_nifti_pair(
    image_path,
    mask_path,
):
    """
    Load CT and mask using nibabel and resample both
    to the same nearest orthonormal physical grid.
    """

    image = _load_with_nibabel(
        image_path
    )

    mask = _load_with_nibabel(
        mask_path
    )

    if image.shape != mask.shape:
        raise ValueError(
            "CT and mask shapes do not match."
        )

    if not np.allclose(
        image.affine,
        mask.affine,
    ):
        raise ValueError(
            "CT and mask affines do not match."
        )

    (
        target_shape,
        target_affine,
        correction_angles,
    ) = _build_orthonormal_target(
        image
    )

    print(
        "WARNING: non-orthonormal geometry detected."
    )

    print(
        "Resampling CT and mask to nearest "
        "orthonormal physical grid."
    )

    print(
        "Maximum axis correction:",
        f"{max(correction_angles):.6f}",
        "degrees",
    )

    # Covering the source extent does not preserve every lumen voxel or its
    # measured volume: interpolation can alter narrow vessels and boundaries.
    # CT: linear interpolation
    resampled_image = resample_from_to(
        image,
        (
            target_shape,
            target_affine,
        ),
        order=1,
    )

    # Mask: nearest-neighbour interpolation
    resampled_mask = resample_from_to(
        mask,
        (
            target_shape,
            target_affine,
        ),
        order=0,
    )

    # Force mask to binary
    mask_data = (
        np.asanyarray(
            resampled_mask.dataobj
        ) > 0.5
    ).astype(np.uint8)

    resampled_mask = nib.Nifti1Image(
        mask_data,
        target_affine,
    )

    # Make qform and sform agree
    resampled_image.set_qform(
        target_affine,
        code=1,
    )

    resampled_image.set_sform(
        target_affine,
        code=1,
    )

    resampled_mask.set_qform(
        target_affine,
        code=1,
    )

    resampled_mask.set_sform(
        target_affine,
        code=1,
    )

    # Write temporary corrected files
    image_temp = tempfile.NamedTemporaryFile(
        suffix=".nii.gz",
        delete=False,
    )

    mask_temp = tempfile.NamedTemporaryFile(
        suffix=".nii.gz",
        delete=False,
    )

    image_temp_path = image_temp.name
    mask_temp_path = mask_temp.name

    image_temp.close()
    mask_temp.close()

    nib.save(
        resampled_image,
        image_temp_path,
    )

    nib.save(
        resampled_mask,
        mask_temp_path,
    )

    try:
        sitk_image = sitk.ReadImage(
            image_temp_path
        )

        sitk_mask = sitk.ReadImage(
            mask_temp_path
        )

    finally:
        os.remove(
            image_temp_path
        )

        os.remove(
            mask_temp_path
        )

    return sitk_image, sitk_mask


def read_nifti_pair(
    image_path,
    mask_path,
    metadata=None,
):
    """
    Robustly load a CT and aorta mask.

    Handles:
    - normal .nii
    - normal .nii.gz
    - gzip-compressed files incorrectly named .nii
    - slightly non-orthonormal image geometry
    """

    if metadata is not None:
        metadata.update(loader='src.utils.read_nifti_pair', geometry_resampled=False)

    image_readable = None
    mask_readable = None

    image_is_temp = False
    mask_is_temp = False

    try:
        (
            image_readable,
            image_is_temp,
        ) = _prepare_readable_path(
            image_path
        )

        (
            mask_readable,
            mask_is_temp,
        ) = _prepare_readable_path(
            mask_path
        )

        # First try normal SimpleITK loading.
        try:
            image = sitk.ReadImage(
                image_readable
            )

            mask = sitk.ReadImage(
                mask_readable
            )

            return image, mask

        except RuntimeError as error:

            error_message = str(error)

            # Only use the fallback for the specific
            # non-orthonormal geometry problem.
            if (
                "orthonormal direction cosines"
                not in error_message
            ):
                raise

            if metadata is not None:
                metadata.update(geometry_resampled=True,
                    reason='Nonorthonormal input; original paired resampling fallback')

            return _resample_nifti_pair(
                image_readable,
                mask_readable,
            )

    finally:

        if (
            image_is_temp
            and image_readable is not None
            and os.path.exists(
                image_readable
            )
        ):
            os.remove(
                image_readable
            )

        if (
            mask_is_temp
            and mask_readable is not None
            and os.path.exists(
                mask_readable
            )
        ):
            os.remove(
                mask_readable
            )