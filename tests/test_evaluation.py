import unittest
from src.evaluate_predictions import compare


class EvaluationTests(unittest.TestCase):
    def test_duplicate_counts_as_false_positive(self):
        d={'ostium_xyz_mm':[0,0,0]}
        r=compare({'daughters':[d,d]},{'daughters':[d]},2)
        self.assertEqual((r['tp'],r['fp'],r['fn']),(1,1,0))

    def test_unmatched_and_empty(self):
        r=compare({'daughters':[{'ostium_xyz_mm':[10,0,0]}]},
                  {'daughters':[{'ostium_xyz_mm':[0,0,0]}]},2)
        self.assertEqual((r['tp'],r['fp'],r['fn']),(0,1,1))
        self.assertEqual(compare({'daughters':[]},{'daughters':[]},2)['matches'],[])


if __name__=='__main__':unittest.main()
