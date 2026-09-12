from pathlib import Path
import os
import shutil
import tempfile

import nibabel as nib
import numpy as np
import SimpleITK as sitk
import matplotlib.pyplot as plt

from nibabel.processing import resample_from_to


IMAGE_PATH = Path(
    "data/TORALIS CHALLENGE/subject024/orig24.nii"
)

MASK_PATH = Path(
    "data/TORALIS CHALLENGE/subject024/mask24.nii"
)

OUTPUT_DIR = Path(
    "data/TORALIS CHALLENGE/subject024_resampled"
)

OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_IMAGE = OUTPUT_DIR / "orig24_resampled.nii.gz"
OUTPUT_MASK = OUTPUT_DIR / "mask24_resampled.nii.gz"


# -------------------------------------------------
# 1. Load a NIfTI even if gzip is mislabeled as .nii
# -------------------------------------------------

def load_nibabel(path):
    path = str(path)

    with open(path, "rb") as file:
        is_gzip = file.read(2) == b"\x1f\x8b"

    # Normal file
    if not is_gzip or path.endswith(".gz"):
        image = nib.load(path)

        # Load data now so it no longer depends on file handle
        return nib.Nifti1Image(
            np.asanyarray(image.dataobj),
            image.affine.copy(),
            image.header.copy(),
        )

    # gzip-compressed file incorrectly named .nii
    with tempfile.NamedTemporaryFile(
        suffix=".nii.gz",
        delete=False,
    ) as temp_file:
        temp_path = temp_file.name

    try:
        shutil.copyfile(path, temp_path)

        image = nib.load(temp_path)

        return nib.Nifti1Image(
            np.asanyarray(image.dataobj),
            image.affine.copy(),
            image.header.copy(),
        )

    finally:
        os.remove(temp_path)


# -------------------------------------------------
# 2. Find nearest orthogonal orientation
# -------------------------------------------------

def nearest_orthogonal_grid(image):
    affine = image.affine.copy()

    # 3x3 part = orientation + voxel scaling
    spatial = affine[:3, :3]

    # Physical size of each voxel axis
    spacing = np.linalg.norm(spatial, axis=0)

    # Remove scaling, leaving only axis directions
    direction = spatial / spacing

    print("\nOriginal normalized direction:")
    print(direction)

    print("\nOriginal orthogonality check:")
    print(direction.T @ direction)

    # Polar decomposition using SVD.
    #
    # This gives the closest orthogonal matrix to
    # the original direction matrix.
    U, _, Vt = np.linalg.svd(direction)

    corrected_direction = U @ Vt

    print("\nCorrected direction:")
    print(corrected_direction)

    print("\nCorrected orthogonality check:")
    print(corrected_direction.T @ corrected_direction)

    # IMPORTANT:
    # We do NOT force determinant +1.
    #
    # A valid medical-image orientation may contain
    # an axis reflection. We preserve the closest
    # orthogonal orientation to the original.
    print("\nOriginal determinant:", np.linalg.det(direction))
    print("Corrected determinant:", np.linalg.det(corrected_direction))

    # Show how much each axis changed
    print("\nAxis correction angles:")

    for axis in range(3):
        old_axis = direction[:, axis]
        new_axis = corrected_direction[:, axis]

        dot = np.clip(
            np.dot(old_axis, new_axis),
            -1.0,
            1.0,
        )

        angle_deg = np.degrees(np.arccos(dot))

        print(
            f"Axis {axis}: {angle_deg:.6f} degrees"
        )

    # Put voxel spacing back
    target_spatial = (
        corrected_direction @ np.diag(spacing)
    )

    # -------------------------------------------------
    # Find a target grid that covers the entire
    # ORIGINAL physical volume.
    # -------------------------------------------------

    nx, ny, nz = image.shape[:3]

    # Use voxel BOUNDARIES, not just voxel centres.
    #
    # A volume with N voxels extends from
    # -0.5 to N - 0.5 in voxel coordinates.
    corners = np.array([
        [x, y, z, 1.0]
        for x in (-0.5, nx - 0.5)
        for y in (-0.5, ny - 0.5)
        for z in (-0.5, nz - 0.5)
    ])

    # Convert original volume corners to physical space
    world_corners = (
        affine @ corners.T
    ).T[:, :3]

    # Express those same physical points in the
    # corrected orientation coordinate system
    inverse_target_spatial = np.linalg.inv(
        target_spatial
    )

    target_coordinates = (
        inverse_target_spatial
        @ world_corners.T
    ).T

    min_coord = target_coordinates.min(axis=0)
    max_coord = target_coordinates.max(axis=0)

    # Number of voxels necessary to cover the
    # complete original physical volume
    target_shape = np.ceil(
        max_coord - min_coord
    ).astype(int)

    # Target affine maps voxel CENTRES to world coords.
    #
    # min_coord is the lower voxel boundary, so
    # move half a voxel inward to obtain centre 0.
    target_origin = target_spatial @ (
        min_coord + 0.5
    )

    target_affine = np.eye(4)

    target_affine[:3, :3] = target_spatial
    target_affine[:3, 3] = target_origin

    print("\nOriginal shape:")
    print(image.shape)

    print("\nTarget shape:")
    print(tuple(target_shape))

    print("\nOriginal spacing:")
    print(spacing)

    print("\nTarget affine:")
    print(target_affine)

    return tuple(target_shape), target_affine


# -------------------------------------------------
# 3. Load original CT and mask
# -------------------------------------------------

print("Loading subject024...")

image = load_nibabel(IMAGE_PATH)
mask = load_nibabel(MASK_PATH)

print("\nImage shape:", image.shape)
print("Mask shape:", mask.shape)

print(
    "Same affine:",
    np.allclose(image.affine, mask.affine),
)

if image.shape != mask.shape:
    raise ValueError("CT and mask shapes do not match.")

if not np.allclose(image.affine, mask.affine):
    raise ValueError("CT and mask affines do not match.")


# -------------------------------------------------
# 4. Build ONE corrected grid
# -------------------------------------------------

target_shape, target_affine = (
    nearest_orthogonal_grid(image)
)


# -------------------------------------------------
# 5. Resample CT
# -------------------------------------------------

print("\nResampling CT...")

# order=1 = linear interpolation
resampled_image = resample_from_to(
    image,
    (target_shape, target_affine),
    order=1,
)


# -------------------------------------------------
# 6. Resample binary mask
# -------------------------------------------------

print("Resampling mask...")

# order=0 = nearest-neighbour.
#
# This is important for a mask because we do NOT
# want interpolation to create values such as
# 0.2, 0.5, 0.8.
resampled_mask = resample_from_to(
    mask,
    (target_shape, target_affine),
    order=0,
)


# -------------------------------------------------
# 7. Force mask back to binary
# -------------------------------------------------

mask_data = (
    np.asanyarray(resampled_mask.dataobj) > 0.5
).astype(np.uint8)

resampled_mask = nib.Nifti1Image(
    mask_data,
    target_affine,
)


# -------------------------------------------------
# 8. Ensure NIfTI transforms agree
# -------------------------------------------------

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


# -------------------------------------------------
# 9. Save corrected files
# -------------------------------------------------

nib.save(
    resampled_image,
    OUTPUT_IMAGE,
)

nib.save(
    resampled_mask,
    OUTPUT_MASK,
)

print("\nSaved:")
print(OUTPUT_IMAGE)
print(OUTPUT_MASK)


# -------------------------------------------------
# 10. Verify SimpleITK can now read them
# -------------------------------------------------

print("\nTesting with SimpleITK...")

sitk_image = sitk.ReadImage(
    str(OUTPUT_IMAGE)
)

sitk_mask = sitk.ReadImage(
    str(OUTPUT_MASK)
)

print("SimpleITK successfully loaded both files.")

print("\nSimpleITK image size:")
print(sitk_image.GetSize())

print("\nSimpleITK spacing:")
print(sitk_image.GetSpacing())

print("\nSimpleITK direction:")
print(sitk_image.GetDirection())


# -------------------------------------------------
# 11. Verify CT and mask still align
# -------------------------------------------------

assert (
    sitk_image.GetSize()
    == sitk_mask.GetSize()
)

assert np.allclose(
    sitk_image.GetSpacing(),
    sitk_mask.GetSpacing(),
)

assert np.allclose(
    sitk_image.GetOrigin(),
    sitk_mask.GetOrigin(),
)

assert np.allclose(
    sitk_image.GetDirection(),
    sitk_mask.GetDirection(),
)

print("\nCT and mask remain aligned.")


# -------------------------------------------------
# 12. Compare mask physical volume before/after
# -------------------------------------------------

original_mask_data = (
    np.asanyarray(mask.dataobj) > 0.5
)

original_voxel_volume = abs(
    np.linalg.det(
        image.affine[:3, :3]
    )
)

original_mask_volume = (
    np.count_nonzero(original_mask_data)
    * original_voxel_volume
)

new_mask_array = sitk.GetArrayFromImage(
    sitk_mask
).astype(bool)

new_spacing = sitk_image.GetSpacing()

new_voxel_volume = (
    new_spacing[0]
    * new_spacing[1]
    * new_spacing[2]
)

new_mask_volume = (
    np.count_nonzero(new_mask_array)
    * new_voxel_volume
)

difference_percent = (
    100.0
    * abs(
        new_mask_volume
        - original_mask_volume
    )
    / original_mask_volume
)

print("\nMask physical volume check:")

print(
    "Original:",
    original_mask_volume,
    "mm^3"
)

print(
    "Resampled:",
    new_mask_volume,
    "mm^3"
)

print(
    "Difference:",
    difference_percent,
    "%"
)


# -------------------------------------------------
# 13. Visual alignment check
# -------------------------------------------------

ct_array = sitk.GetArrayFromImage(
    sitk_image
)

mask_array = sitk.GetArrayFromImage(
    sitk_mask
).astype(bool)

# Choose the slice with the most aorta pixels
slice_areas = np.count_nonzero(
    mask_array,
    axis=(1, 2),
)

best_z = int(np.argmax(slice_areas))

print(
    "\nVisualizing slice:",
    best_z
)

plt.figure()

plt.imshow(
    ct_array[best_z],
    cmap="gray",
)

plt.contour(
    mask_array[best_z],
    levels=[0.5],
)

plt.title(
    "Subject024 after physical resampling"
)

plt.show()