from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'BranchForge'))
from BranchForgeLib.nifti_export import export_target, traced_labelmap


class NiftiExportTests(unittest.TestCase):
    def test_parent_preserved_and_path_continuous(self):
        parent = np.zeros((9, 10, 12), np.uint8)
        parent[2, 3, :3] = 1
        before = parent.copy()
        labels = traced_labelmap(parent, np.eye(4), [[[0, -3, 2], [-9, -3, 2]]])
        np.testing.assert_array_equal(labels[2, 3, :10], [1, 1, 1, 2, 2, 2, 2, 2, 2, 2])
        np.testing.assert_array_equal(parent, before)
        self.assertEqual(labels.dtype, np.uint8)
        self.assertEqual(np.count_nonzero(labels), 10)

    def test_oblique_anisotropic_grid_with_offset(self):
        matrix = np.array([[0, -2, 0, 70], [.5, 0, 0, -40], [0, 0, 3, 15], [0, 0, 0, 1.]])
        ijk = np.array([[2, 2, 2, 1], [7, 2, 2, 1]])
        lps = (ijk @ matrix.T)[:, :3] * [-1, -1, 1]
        result = traced_labelmap(np.zeros((10, 10, 10)), matrix, [lps])
        self.assertEqual(np.count_nonzero(result), 6)
        self.assertTrue(np.all(result[2, 2, 2:8] == 2))

    def test_crossing_branches_share_label_not_order(self):
        a = [[-1, -3, 2], [-5, -3, 2]]
        b = [[-3, -1, 2], [-3, -5, 2]]
        parent = np.zeros((8, 8, 8))
        np.testing.assert_array_equal(traced_labelmap(parent, np.eye(4), [a, b]),
                                      traced_labelmap(parent, np.eye(4), [b, a]))

    def test_reject_missing_invalid_or_outside_paths(self):
        for paths in [[], [[[0, 0, 0]]], [[[0, 0, 0], [np.nan, 1, 1]]],
                      [[[0, 0, 0], [-20, 0, 0]]], [[[0, 0, 0], [1, 0, 0]]]]:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                traced_labelmap(np.zeros((8, 8, 8)), np.eye(4), paths)

    def test_reject_invalid_geometry(self):
        for matrix in [np.ones((3, 3)), np.full((4, 4), np.nan), np.zeros((4, 4))]:
            with self.assertRaises(ValueError):
                traced_labelmap(np.zeros((8, 8, 8)), matrix, [[[0, 0, 0], [-2, 0, 0]]])

    def test_filename_and_original_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'ct.nii'
            original.touch()
            with self.assertRaises(ValueError):
                export_target(original, [original])
            with self.assertRaises(ValueError):
                export_target(Path(folder) / 'edited.json')
            self.assertEqual(export_target(Path(folder) / 'edited.nii.gz').name, 'edited.nii.gz')


if __name__ == '__main__':
    unittest.main()
