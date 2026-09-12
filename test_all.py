from pathlib import Path

import numpy as np

from utils import read_nifti_pair


DATA_DIR = Path("data/TORALIS CHALLENGE")
CROP_MARGIN_MM = 20.0


def test_subject(subject_dir):

    # -------------------------------------------------
    # 1. Find CT and mask files
    # -------------------------------------------------

    image_files = (
        list(subject_dir.glob("orig*.nii"))
        + list(subject_dir.glob("orig*.nii.gz"))
    )

    mask_files = (
        list(subject_dir.glob("mask*.nii"))
        + list(subject_dir.glob("mask*.nii.gz"))
    )

    if len(image_files) != 1:
        return False, f"Expected 1 CT file, found {len(image_files)}"

    if len(mask_files) != 1:
        return False, f"Expected 1 mask file, found {len(mask_files)}"

    image_path = image_files[0]
    mask_path = mask_files[0]


    # -------------------------------------------------
    # 2. Load CT and mask
    # -------------------------------------------------

    image, mask = read_nifti_pair(
        image_path,
        mask_path,
    )


    # -------------------------------------------------
    # 3. Check alignment
    # -------------------------------------------------

    if image.GetSize() != mask.GetSize():
        return False, "Size mismatch"

    if not np.allclose(
        image.GetSpacing(),
        mask.GetSpacing(),
    ):
        return False, "Spacing mismatch"

    if not np.allclose(
        image.GetOrigin(),
        mask.GetOrigin(),
    ):
        return False, "Origin mismatch"

    if not np.allclose(
        image.GetDirection(),
        mask.GetDirection(),
    ):
        return False, "Direction mismatch"


    # -------------------------------------------------
    # 4. Convert mask to NumPy
    # -------------------------------------------------

    import SimpleITK as sitk

    aorta = sitk.GetArrayFromImage(
        mask
    ).astype(bool)

    aorta_voxels = np.count_nonzero(
        aorta
    )

    if aorta_voxels == 0:
        return False, "Empty aorta mask"


    # -------------------------------------------------
    # 5. Find aorta bounding box
    # -------------------------------------------------

    coords = np.argwhere(aorta)

    z_min, y_min, x_min = coords.min(
        axis=0
    )

    z_max, y_max, x_max = coords.max(
        axis=0
    )


    # -------------------------------------------------
    # 6. Convert physical margin to voxel counts
    # -------------------------------------------------

    sx, sy, sz = image.GetSpacing()

    margin_x = int(
        np.ceil(CROP_MARGIN_MM / sx)
    )

    margin_y = int(
        np.ceil(CROP_MARGIN_MM / sy)
    )

    margin_z = int(
        np.ceil(CROP_MARGIN_MM / sz)
    )


    # -------------------------------------------------
    # 7. Get shape in NumPy order
    # -------------------------------------------------

    size_x, size_y, size_z = (
        image.GetSize()
    )

    ct_shape = (
        size_z,
        size_y,
        size_x,
    )


    # -------------------------------------------------
    # 8. Compute crop boundaries
    # -------------------------------------------------

    z0 = max(
        0,
        z_min - margin_z,
    )

    z1 = min(
        ct_shape[0],
        z_max + margin_z + 1,
    )

    y0 = max(
        0,
        y_min - margin_y,
    )

    y1 = min(
        ct_shape[1],
        y_max + margin_y + 1,
    )

    x0 = max(
        0,
        x_min - margin_x,
    )

    x1 = min(
        ct_shape[2],
        x_max + margin_x + 1,
    )


    # -------------------------------------------------
    # 9. Compute crop size
    # -------------------------------------------------

    crop_shape = (
        int(z1 - z0),
        int(y1 - y0),
        int(x1 - x0),
    )


    return True, {
        "original_shape": ct_shape,
        "crop_shape": crop_shape,
        "spacing": image.GetSpacing(),
        "aorta_voxels": int(aorta_voxels),
    }


def main():

    subjects = sorted(
        DATA_DIR.glob("subject*")
    )

    print(
        f"Found {len(subjects)} subjects\n"
    )

    passed = 0

    for subject_dir in subjects:

        name = subject_dir.name

        try:

            success, result = test_subject(
                subject_dir
            )

            if success:

                passed += 1

                print(
                    f"[PASS] {name} | "
                    f"original={result['original_shape']} | "
                    f"crop={result['crop_shape']} | "
                    f"spacing={result['spacing']} | "
                    f"aorta_voxels={result['aorta_voxels']}"
                )

            else:

                print(
                    f"[FAIL] {name} | {result}"
                )

        except Exception as error:

            print(
                f"[ERROR] {name} | {error}"
            )

    print("\n--------------------")
    print(
        f"Passed: {passed}/{len(subjects)}"
    )
    print("--------------------")


if __name__ == "__main__":
    main()