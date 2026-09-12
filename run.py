import argparse

import SimpleITK as sitk
import numpy as np
import matplotlib.pyplot as plt

from utils import read_nifti_pair


# -------------------------------------------------
# 1. Read file paths from the command line
# -------------------------------------------------

parser = argparse.ArgumentParser()

parser.add_argument("--image", required=True)
parser.add_argument("--aorta-mask", required=True)

args = parser.parse_args()


# -------------------------------------------------
# 2. Load CT and aorta mask
# -------------------------------------------------

print("Loading CT:", args.image)
print("Loading mask:", args.aorta_mask)

image, mask = read_nifti_pair(
    args.image,
    args.aorta_mask,
)


# -------------------------------------------------
# 3. Make sure CT and mask line up
# -------------------------------------------------

print("\nChecking alignment...")

assert image.GetSize() == mask.GetSize(), "Size mismatch"

assert np.allclose(
    image.GetSpacing(),
    mask.GetSpacing(),
), "Spacing mismatch"

assert np.allclose(
    image.GetOrigin(),
    mask.GetOrigin(),
), "Origin mismatch"

assert np.allclose(
    image.GetDirection(),
    mask.GetDirection(),
), "Direction mismatch"

print("CT and mask are aligned.")


# -------------------------------------------------
# 4. Convert to NumPy arrays
# -------------------------------------------------

# NumPy uses [z, y, x]
ct = sitk.GetArrayFromImage(image)

# True = aorta
# False = everything else
aorta = sitk.GetArrayFromImage(mask).astype(bool)

print("\nCT shape:", ct.shape)
print("Mask shape:", aorta.shape)
print("CT spacing (x, y, z) in mm:", image.GetSpacing())
print("Aorta voxels:", np.count_nonzero(aorta))

if np.count_nonzero(aorta) == 0:
    raise ValueError("Aorta mask is empty.")

print("\nDATA CHECK PASSED")


# -------------------------------------------------
# 5. Find the 3D bounding box of the aorta
# -------------------------------------------------

coords = np.argwhere(aorta)

z_min, y_min, x_min = coords.min(axis=0)
z_max, y_max, x_max = coords.max(axis=0)

print("\nAorta bounding box:")
print("z:", z_min, "to", z_max)
print("y:", y_min, "to", y_max)
print("x:", x_min, "to", x_max)


# -------------------------------------------------
# 6. Choose how much physical space to keep
# -------------------------------------------------

CROP_MARGIN_MM = 20.0


# -------------------------------------------------
# 7. Convert physical margin to voxel counts
# -------------------------------------------------

# SimpleITK spacing is (x, y, z)
sx, sy, sz = image.GetSpacing()

margin_x = int(np.ceil(CROP_MARGIN_MM / sx))
margin_y = int(np.ceil(CROP_MARGIN_MM / sy))
margin_z = int(np.ceil(CROP_MARGIN_MM / sz))

print("\nCrop margin:", CROP_MARGIN_MM, "mm")

print(
    "Margin in voxels (x, y, z):",
    margin_x,
    margin_y,
    margin_z,
)


# -------------------------------------------------
# 8. Compute safe crop boundaries
# -------------------------------------------------

z0 = max(0, z_min - margin_z)
z1 = min(ct.shape[0], z_max + margin_z + 1)

y0 = max(0, y_min - margin_y)
y1 = min(ct.shape[1], y_max + margin_y + 1)

x0 = max(0, x_min - margin_x)
x1 = min(ct.shape[2], x_max + margin_x + 1)


# -------------------------------------------------
# 9. Crop CT and mask using the same bounds
# -------------------------------------------------

ct_crop = ct[
    z0:z1,
    y0:y1,
    x0:x1,
]

aorta_crop = aorta[
    z0:z1,
    y0:y1,
    x0:x1,
]

print("\nOriginal CT shape:", ct.shape)
print("Cropped CT shape:", ct_crop.shape)


# -------------------------------------------------
# 10. Visual check before cropping
# -------------------------------------------------

z_middle_original = (
    z_min + z_max
) // 2

plt.figure()

plt.imshow(
    ct[z_middle_original],
    cmap="gray",
)

plt.contour(
    aorta[z_middle_original],
    levels=[0.5],
)

plt.title(
    f"Original CT + aorta mask | slice {z_middle_original}"
)

plt.show()


# -------------------------------------------------
# 11. Visual check after cropping
# -------------------------------------------------

z_middle_crop = (
    z_middle_original - z0
)

plt.figure()

plt.imshow(
    ct_crop[z_middle_crop],
    cmap="gray",
)

plt.contour(
    aorta_crop[z_middle_crop],
    levels=[0.5],
)

plt.title(
    f"Cropped CT around aorta | {CROP_MARGIN_MM:.0f} mm margin"
)

plt.show()