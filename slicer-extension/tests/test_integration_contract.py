"""Bundled detector discovery and custom case IDs; no Slicer dependency."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BranchForge"))
from BranchForgeLib.integration import detector_paths, detection_arguments


class IntegrationContractTests(unittest.TestCase):
    def test_custom_case_id_is_passed_as_a_single_argument(self):
        args = detection_arguments("run.py", "my scans/orig.nii", "my scans/mask.nii", "out.json", "custom case 42")
        self.assertEqual(args[-2:], ["--case-id", "custom case 42"])
        self.assertEqual(len(args), 9)
        self.assertTrue(Path(args[2]).is_absolute())
        with self.assertRaises(ValueError):
            detection_arguments("run.py", "ct.nii", "mask.nii", "out.json", " ")

    def test_finds_local_environment_and_recovers_stale_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            script = root / "run.py"
            script.touch()
            self.assertEqual(detector_paths(root, "missing-python", "missing-script"), (str(python), str(script)))
            custom = root / "custom.py"
            custom.touch()
            self.assertEqual(detector_paths(root, str(python), str(custom)), (str(python), str(custom)))


if __name__ == "__main__":
    unittest.main()
