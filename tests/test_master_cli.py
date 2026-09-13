"""Integration boundary regressions; inference implementation is separately tested."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.rebuild.challenge_output import main


class MasterCliTests(unittest.TestCase):
    def test_no_proposals_can_export_empty_but_missing_weights_cannot(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'empty.json'
            args = ['run.py', '--image', 'ct.nii', '--aorta-mask', 'mask.nii', '--output', str(output)]
            result = {'neural': {'status': 'no_proposals'}, 'review_groups': []}
            with patch.object(sys, 'argv', args), patch('src.rebuild.review_pipeline.infer', return_value=(result, {})), patch('src.rebuild.review_pipeline.save_result'):
                main()
                self.assertEqual(json.loads(output.read_text())['daughters'], [])
                result['neural']['status'] = 'weights_missing'
                with self.assertRaisesRegex(RuntimeError, 'Neural inference unavailable'):
                    main()

    def test_output_cannot_replace_input(self):
        with patch.object(sys, 'argv', ['run.py', '--image', 'ct.nii', '--aorta-mask', 'mask.nii', '--output', 'ct.nii']):
            with self.assertRaises(SystemExit):
                main()
