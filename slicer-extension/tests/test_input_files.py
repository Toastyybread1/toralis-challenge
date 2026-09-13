from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'BranchForge'))
from BranchForgeLib.input_files import display_input_path


class InputFileTests(unittest.TestCase):
    def test_misnamed_gzip_is_copied_without_changing_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.nii'
            content = b'\x1f\x8bexample'
            source.write_bytes(content)
            target = Path(display_input_path(source, tmp))
            self.assertNotEqual(source, target)
            self.assertTrue(target.name.endswith('.nii.gz'))
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(source.read_bytes(), content)

    def test_uncompressed_input_keeps_its_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.nii'
            source.write_bytes(b'not gzip')
            self.assertEqual(display_input_path(source, tmp), str(source))
