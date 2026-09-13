import unittest
from unittest.mock import patch
from src.utils import read_nifti_pair

class OriginalLoaderTests(unittest.TestCase):
    def test_original_geometry_fallback_and_metadata(self):
        metadata={}
        with patch('src.utils._prepare_readable_path',side_effect=lambda p:(p,False)), \
             patch('src.utils.sitk.ReadImage',side_effect=RuntimeError('orthonormal direction cosines')), \
             patch('src.utils._resample_nifti_pair',return_value=('ct','mask')) as fallback:
            self.assertEqual(read_nifti_pair('ct.nii','mask.nii',metadata),('ct','mask'))
            fallback.assert_called_once_with('ct.nii','mask.nii')
        self.assertTrue(metadata['geometry_resampled'])

    def test_unrelated_read_errors_do_not_trigger_resampling(self):
        with patch('src.utils._prepare_readable_path',side_effect=lambda p:(p,False)), \
             patch('src.utils.sitk.ReadImage',side_effect=RuntimeError('missing file')), \
             patch('src.utils._resample_nifti_pair') as fallback:
            with self.assertRaises(RuntimeError):read_nifti_pair('ct','mask')
            fallback.assert_not_called()

if __name__=='__main__':unittest.main()
