import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BranchForge"))
from BranchForgeLib.contract import validate_prediction, lps_to_ras, load_prediction, save_prediction, discover_cases

EXAMPLE = {"case_id": "subject001", "parent": {"instance_id": "aorta"}, "daughters": [{"instance_id": "branch_001", "parent_instance_id": "aorta", "ostium_xyz_mm": [12., -30., 180.], "seed_xyz_mm": [17., -30., 180.], "radius_mm": 2.5, "direction_xyz": [1., 0., 0.]}]}


class ContractTests(unittest.TestCase):
    def test_roundtrip_preserves_physical_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prediction.json"
            save_prediction(path, EXAMPLE)
            self.assertEqual(load_prediction(path, "subject001"), EXAMPLE)
        self.assertEqual(lps_to_ras([12., -30., 180.]), (-12., 30., 180.))
        self.assertEqual(lps_to_ras(lps_to_ras([12., -30., 180.])), (12., -30., 180.))

    def test_empty_and_variable_counts(self):
        empty = copy.deepcopy(EXAMPLE)
        empty["daughters"] = []
        self.assertEqual(validate_prediction(empty), empty)
        many = copy.deepcopy(EXAMPLE)
        for i in range(2, 9):
            branch = copy.deepcopy(EXAMPLE["daughters"][0])
            branch["instance_id"] = f"branch_{i:03d}"
            many["daughters"].append(branch)
        self.assertEqual(len(validate_prediction(many)["daughters"]), 8)

    def test_rejects_duplicates_case_mismatch_and_bad_geometry(self):
        invalid = []
        duplicate = copy.deepcopy(EXAMPLE)
        duplicate["daughters"] *= 2
        invalid.append(duplicate)
        for field, value in [("radius_mm", -1), ("radius_mm", True), ("radius_mm", math.nan), ("direction_xyz", [0, 0, 0]), ("ostium_xyz_mm", [0, math.inf, 0]), ("parent_instance_id", "branch_002")]:
            data = copy.deepcopy(EXAMPLE)
            data["daughters"][0][field] = value
            invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_prediction(data)
        with self.assertRaises(ValueError):
            validate_prediction(EXAMPLE, "subject002")

    def test_catalog_ignores_nested_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = Path(folder) / "subject001"
            subject.mkdir()
            (subject / "orig1.nii").touch()
            (subject / "mask1.nii").touch()
            nested = subject / "subject099"
            nested.mkdir()
            (nested / "orig99.nii").touch()
            (nested / "mask99.nii").touch()
            self.assertEqual([x[0] for x in discover_cases(folder)], ["subject001"])


if __name__ == "__main__":
    unittest.main()

