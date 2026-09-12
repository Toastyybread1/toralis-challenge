"""Synthetic geometry checks; these do not validate a development case."""

import tempfile
import unittest
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import SimpleITK as sitk

from src.preprocessing import basic_statistics, index_to_physical, load_case, verify_geometry
from src.preprocessing import prepare_case
from src.types import Config
from src.visualization import show_case


class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        z, y, x = np.indices((24, 40, 48))
        mask = (((x - 24) * 0.8) ** 2 + ((y - 20) * 1.2) ** 2 <= 6 ** 2)
        self.image = sitk.GetImageFromArray(np.where(mask, 300, -100).astype(np.int16))
        self.image.SetSpacing((0.8, 1.2, 2.5))
        self.image.SetOrigin((-50, 12, 100))
        angle = np.deg2rad(20)
        self.image.SetDirection((np.cos(angle), 0, np.sin(angle),
                                 0, 1, 0, -np.sin(angle), 0, np.cos(angle)))
        self.mask = sitk.GetImageFromArray(mask.astype(np.uint8))
        self.mask.CopyInformation(self.image)

    def load(self):
        sitk.WriteImage(self.image, str(self.root / "image.nii.gz"))
        sitk.WriteImage(self.mask, str(self.root / "mask.nii.gz"))
        return load_case(self.root / "image.nii.gz", self.root / "mask.nii.gz")

    def test_roundtrip_statistics_and_coordinates(self):
        case = self.load()
        self.assertEqual(case.ct_zyx.shape, (24, 40, 48))
        report = basic_statistics(case)
        self.assertEqual(report["aorta_intensity"]["mean"], 300)
        self.assertAlmostEqual(report["aorta_volume_mm3"],
                               int(case.mask_zyx.sum()) * 0.8 * 1.2 * 2.5, places=2)
        expected = np.array(self.image.GetOrigin()) + np.array(
            self.image.GetDirection()).reshape(3, 3) @ (np.array([4, 5, 6]) * self.image.GetSpacing())
        np.testing.assert_allclose(index_to_physical(case.image, [4, 5, 6]), expected, atol=1e-5)
        with self.assertRaises(ValueError):
            index_to_physical(case.image, [0.5, 0, 0])

    def test_each_geometry_mismatch(self):
        for field, value in [("Spacing", (1, 1, 1)), ("Origin", (0, 0, 0)),
                             ("Direction", tuple(np.eye(3).ravel()))]:
            with self.subTest(field=field):
                mask = sitk.Image(self.mask)
                getattr(mask, f"Set{field}")(value)
                with self.assertRaisesRegex(ValueError, field):
                    verify_geometry(self.image, mask)
        with self.assertRaisesRegex(ValueError, "Size"):
            verify_geometry(self.image, sitk.Image([2, 3, 4], sitk.sitkUInt8))

    def test_invalid_masks(self):
        for value in (0, 2):
            with self.subTest(value=value):
                self.mask = sitk.Image(self.image.GetSize(), sitk.sitkUInt8) + value
                self.mask.CopyInformation(self.image)
                with self.assertRaises(ValueError):
                    self.load()

    def test_gzip_with_nii_extension(self):
        self.load()
        (self.root / "image.nii.gz").rename(self.root / "image.nii")
        (self.root / "mask.nii.gz").rename(self.root / "mask.nii")
        case = load_case(self.root / "image.nii", self.root / "mask.nii")
        self.assertEqual(case.ct_zyx.shape, (24, 40, 48))

    def test_sheared_nifti_preserves_world_coordinates(self):
        import nibabel as nib
        affine = np.array([[0.8, 0.03, 0, -50], [0, 1.2, 0, 12], [0, 0, 2.5, 100], [0, 0, 0, 1]])
        for filename, image in (("ct.nii.gz", self.image), ("mask.nii.gz", self.mask)):
            array = sitk.GetArrayFromImage(image).transpose(2, 1, 0)
            nib.save(nib.Nifti1Image(array, affine), self.root / filename)
        case = load_case(self.root / "ct.nii.gz", self.root / "mask.nii.gz")
        expected = (affine @ [4, 5, 6, 1])[:3] * [-1, -1, 1]
        np.testing.assert_allclose(index_to_physical(case.image, [4, 5, 6]), expected, atol=1e-5)
        roi = prepare_case(case, Config())
        direction = np.array(roi.image.GetDirection()).reshape(3, 3)
        np.testing.assert_allclose(direction.T @ direction, np.eye(3), atol=1e-5)
        self.assertTrue(roi.aorta.any())

    def test_oblique_overlays(self):
        case = self.load()
        figure = show_case(case, self.root / "overlay.png")
        self.addCleanup(plt.close, figure)
        self.assertEqual(len(figure.axes), 3)
        for ax in figure.axes:
            ct, mask = [artist.get_array() for artist in ax.images]
            self.assertGreater(mask.count(), 0)
            self.assertGreater(float(ct[~np.ma.getmaskarray(mask)].mean()), 200)
        self.assertGreater((self.root / "overlay.png").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
