import importlib
import sys
import unittest
from unittest.mock import patch


class DispatchTests(unittest.TestCase):
    def test_import_does_not_parse_arguments(self):
        with patch.object(sys,'argv',['run.py']):
            module=importlib.import_module('run');importlib.reload(module)

    def test_review_mask_alias_and_argv_restoration(self):
        import run
        original=sys.argv
        with patch('src.rebuild.review_pipeline.main',side_effect=lambda:list(sys.argv[1:])):
            result=run.main(['--document-review','--aorta-mask=mask.nii','--image','ct.nii','--output','out'])
        self.assertIn('--parent=mask.nii',result);self.assertNotIn('--document-review',result)
        self.assertIs(sys.argv,original)

    def test_submission_mode_still_dispatches(self):
        import run
        with patch('src.rebuild.challenge_output.main',return_value='submission') as entry:
            self.assertEqual(run.main(['--output','out.json']),'submission')
        entry.assert_called_once()


if __name__=='__main__':unittest.main()
