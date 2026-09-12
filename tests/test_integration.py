"""Regression tests for the shared Nika/detector preprocessing and CLIs."""

import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from src.dataset import find_case_files
from src.output import validate_prediction
from src.preprocessing import crop_case, load_case, orthonormal_reference, resample_case
from utils import read_nifti_pair


ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "subject001"
        self.folder.mkdir()
        z, y, x = np.indices((28, 30, 32))
        self.mask = (((x - 16) ** 2 + (y - 15) ** 2 < 5 ** 2)
                     & (z > 3) & (z < 24)).astype(np.uint8)
        self.ct = np.where(self.mask, 300, -100).astype(np.int16)
        self.ct_path = self.folder / "orig1.nii.gz"
        self.mask_path = self.folder / "mask1.nii.gz"

    def write_case(self, shear=0.0, reflected=False, units="mm"):
        affine = np.array([[0.8, shear, 0, -50], [0, 1.2, 0, 12],
                           [0, 0, -2.5 if reflected else 2.5, 100], [0, 0, 0, 1]])
        factor = {"mm": 1, "meter": 0.001, "micron": 1000}[units]
        affine[:3] *= factor
        for array, path in ((self.ct, self.ct_path), (self.mask, self.mask_path)):
            volume = nib.Nifti1Image(array.transpose(2, 1, 0), affine)
            volume.header.set_xyzt_units(units)
            nib.save(volume, path)
        return load_case(self.ct_path, self.mask_path)

    def command(self, script, *args):
        return subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=60)

    def assert_covers(self, source, reference):
        corners = itertools.product(*[(-0.5, size - 0.5) for size in source.GetSize()])
        for corner in corners:
            world = source.TransformContinuousIndexToPhysicalPoint(corner)
            index = np.array(reference.TransformPhysicalPointToContinuousIndex(world))
            self.assertTrue(np.all(index >= -0.5 - 1e-6), index)
            self.assertTrue(np.all(index <= np.array(reference.GetSize()) - 0.5 + 1e-6), index)

    def test_reference_covers_boundary_corners_and_retains_reflections(self):
        for shear, reflected in ((0, False), (0.03, False), (-0.04, True)):
            with self.subTest(shear=shear, reflected=reflected):
                case = self.write_case(shear, reflected)
                reference = orthonormal_reference(case.image, [1.1] * 3, max_voxels=15000)
                self.assert_covers(case.image, reference)
                direction = np.array(reference.GetDirection()).reshape(3, 3)
                np.testing.assert_allclose(direction.T @ direction, np.eye(3), atol=1e-8)
                self.assertEqual(np.linalg.det(direction) < 0, reflected)
                self.assertLessEqual(np.prod(reference.GetSize()), 15000)

    def test_crop_retains_mask_and_physical_coordinates(self):
        case = self.write_case(0.03)
        cropped = crop_case(case, 2.0)
        self.assertEqual(cropped.mask_zyx.sum(), case.mask_zyx.sum())
        self.assertLess(cropped.mask_zyx.size, case.mask_zyx.size)
        first = np.argwhere(cropped.mask_zyx)[0][::-1].astype(int).tolist()
        world = cropped.image.TransformIndexToPhysicalPoint(first)
        original = case.image.TransformPhysicalPointToIndex(world)
        self.assertEqual(cropped.image.GetPixel(first), case.image.GetPixel(original))
        self.assertTrue(case.mask_zyx[original[::-1]])

    def test_detector_preserves_sampling_on_already_orthogonal_scans(self):
        case = self.write_case()
        reference = orthonormal_reference(case.image, [0.8] * 3,
                                          max_voxels=3000000, preserve_aligned_grid=True)
        self.assertEqual(reference.GetOrigin(), case.image.GetOrigin())
        self.assertEqual(reference.GetDirection(), case.image.GetDirection())
        extent = (np.array(case.image.GetSize()) - 1) * case.image.GetSpacing()
        np.testing.assert_array_equal(reference.GetSize(), np.floor(extent / 0.8).astype(int) + 1)
        case = self.write_case(0.03)
        reference = orthonormal_reference(case.image, [0.8] * 3,
                                          max_voxels=3000000, preserve_aligned_grid=True)
        self.assert_covers(case.image, reference)

    def test_pair_resampling_is_binary_aligned_and_preserves_inputs(self):
        case = self.write_case(0.03)
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.ct_path, self.mask_path)}
        image, mask = read_nifti_pair(self.ct_path, self.mask_path)
        self.assertEqual(image.GetSize(), mask.GetSize())
        self.assertEqual(image.GetDirection(), mask.GetDirection())
        self.assertEqual(image.GetOrigin(), mask.GetOrigin())
        self.assert_covers(case.image, image)
        labels = sitk.GetArrayFromImage(mask)
        self.assertEqual(set(np.unique(labels)), {0, 1})
        self.assertGreater(sitk.GetArrayFromImage(image)[labels > 0].mean(), 200)
        self.assertLess(abs(labels.sum() / case.mask_zyx.sum() - 1), 0.05)
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_source_units_remain_millimetres_through_resampling(self):
        for units in ("meter", "micron"):
            with self.subTest(units=units):
                case = self.write_case(0.03, units=units)
                np.testing.assert_allclose(case.image.GetOrigin(), [50, -12, 100], atol=1e-5)
                reference = orthonormal_reference(case.image)
                self.assert_covers(case.image, reference)
                np.testing.assert_allclose(reference.GetSpacing(), case.image.GetSpacing())

    def test_invalid_masks_are_rejected_before_resampling(self):
        for value in (0, 2):
            self.mask[:] = value
            with self.assertRaises(ValueError):
                self.write_case(0.03)
            with self.assertRaises(ValueError):
                read_nifti_pair(self.ct_path, self.mask_path)

    def test_pair_mismatch_is_not_silently_repaired(self):
        self.write_case(0.03)
        volume = nib.load(self.mask_path)
        affine = volume.affine.copy()
        affine[0, 3] += 1
        nib.save(nib.Nifti1Image(self.mask.transpose(2, 1, 0), affine), self.mask_path)
        with self.assertRaisesRegex(ValueError, "Origin"):
            read_nifti_pair(self.ct_path, self.mask_path)

    def test_orthogonal_export_roundtrips_in_simpleitk(self):
        corrected = resample_case(self.write_case(0.03, reflected=True))
        for name, image in (("image", corrected.image), ("mask", corrected.aorta_mask)):
            path = self.root / f"{name}.nii.gz"
            sitk.WriteImage(image, str(path))
            reloaded = sitk.ReadImage(str(path))
            np.testing.assert_allclose(reloaded.GetOrigin(), image.GetOrigin(), atol=1e-4)
            np.testing.assert_array_equal(sitk.GetArrayFromImage(reloaded), sitk.GetArrayFromImage(image))

    def test_inspection_and_competition_cli_work_from_another_directory(self):
        self.write_case(0.03)
        output = self.root / "inspection"
        args = ("--image", self.ct_path, "--aorta-mask", self.mask_path)
        result = self.command("inspect_case.py", *args, "--output-dir", output, "--resample")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mask_volume_change_percent", json.loads((output / "statistics.json").read_text()))
        for name in ("original.png", "cropped.png", "orthogonal.png"):
            self.assertGreater((output / name).stat().st_size, 1000)
        result = self.command("run.py", *args, "--output", output / "prediction.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        validate_prediction(json.loads((output / "prediction.json").read_text()))

    def test_batch_reports_failures_and_ignores_non_nifti_suffixes(self):
        self.write_case()
        (self.folder / "orig1.nii.gz.backup").touch()
        self.assertEqual(find_case_files(self.folder), (self.ct_path, self.mask_path))
        (self.root / "subject002").mkdir()
        report = self.root / "checks.json"
        result = self.command("test_all.py", "--dataset", self.root, "--output", report)
        self.assertEqual(result.returncode, 1, result.stderr)
        statuses = [r["status"] for r in json.loads(report.read_text())]
        self.assertEqual(statuses, ["ok", "failed"])
        result = self.command("evaluate.py", "--dataset", self.root,
                              "--output-dir", self.root / "predictions", "--visualize-cases", 0)
        self.assertEqual(result.returncode, 1, result.stderr)
        rows = json.loads((self.root / "predictions" / "evaluation.json").read_text())
        self.assertEqual([r["status"] for r in rows], ["ok", "failed"])

    def test_empty_dataset_fails_instead_of_passing_zero_cases(self):
        empty = self.root / "empty"
        empty.mkdir()
        result = self.command("test_all.py", "--dataset", empty)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no case directories", result.stderr)

    def test_entry_points_are_safe_to_import(self):
        result = subprocess.run([sys.executable, "-c", "import run, inspect_case, inspect_024, test_all, utils"],
                                cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
