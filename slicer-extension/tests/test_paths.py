import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'BranchForge'))
from BranchForgeLib.paths import load_path_evidence
from BranchForgeLib.integration import detection_arguments


class PathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / 'result.json'
        self.branch = dict(instance_id='branch_001', ostium_xyz_mm=[0, 0, 0],
                           seed_xyz_mm=[3, 2, 0], radius_mm=1., direction_xyz=[.6, .8, 0])
        self.prediction = {'daughters': [self.branch]}
        self.rep = {**self.branch, 'instance_id': 'candidate_9',
                    'path_xyz_mm': [[0, 0, 0], [3, 0, 0], [3, 7, 0]], 'stop_reason': 'length_limit'}
        self.audit = {'candidates': [{'instance_id': 'branch_001', 'source_candidate': 'candidate_9', 'exclusion_reason': None}]}

    def sidecars(self, rep=None):
        folder = self.file.parent / 'diagnostics'
        folder.mkdir(exist_ok=True)
        (folder / self.file.name).write_text(json.dumps(self.audit))
        folder = self.file.parent / 'result_review'
        folder.mkdir(exist_ok=True)
        (folder / 'predictions.json').write_text(json.dumps({'review_groups': [
            {'representative': {**self.rep, 'instance_id': 'ignored'}},
            {'representative': rep or self.rep}], 'neural': {'status': 'scored'}}))

    def test_id_mapping_preserves_export(self):
        self.sidecars()
        before = copy.deepcopy(self.prediction)
        paths, note = load_path_evidence(self.file, self.prediction)
        self.assertEqual(paths['branch_001']['source_candidate'], 'candidate_9')
        self.assertEqual(paths['branch_001']['path_length_mm'], 10.)
        self.assertEqual(self.prediction, before)
        self.assertIn('scored', note)

    def test_no_sidecars_means_no_fabricated_path(self):
        self.assertEqual(load_path_evidence(self.file, self.prediction)[0], {})

    def test_stale_or_nonfinite_path_is_rejected(self):
        for edit in ({'seed_xyz_mm': [3, 3, 0]}, {'path_xyz_mm': [[0, 0, 0], [float('nan'), 0, 0]]}):
            self.sidecars({**self.rep, **edit})
            with self.assertRaises(ValueError):
                load_path_evidence(self.file, self.prediction)

    def test_duplicate_mapping_is_rejected(self):
        self.audit['candidates'] *= 2
        self.sidecars()
        with self.assertRaises(ValueError):
            load_path_evidence(self.file, self.prediction)

    def test_explicit_fold_only(self):
        self.assertNotIn('--held-out-case', detection_arguments('run.py', 'a', 'b', 'c', 'subject021'))
        self.assertEqual(detection_arguments('run.py', 'a', 'b', 'c', 'custom', 21)[-2:], ['--held-out-case', '21'])


if __name__ == '__main__':
    unittest.main()
