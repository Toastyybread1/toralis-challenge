import unittest
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.rebuild.staged_growth import stages


class StagedGrowthTests(unittest.TestCase):
    def fixture(self):
        p=np.zeros((49,49,65),bool);p[18:31,18:31,2:8]=True
        a=p.copy();a[23:26,23:26,8:15]=True
        # A narrow feeder opening into a large bright region.
        a[11:38,11:38,15:42]=True
        roi=sitk.GetImageFromArray(p.astype(np.uint8))
        distance=ndi.distance_transform_edt(~p)
        return dict(parent=p,accepted=a,roi=roi,distance=distance,added=a&~p&(distance<=25))

    def test_bulk_rejection_preserves_feeder_and_blocks_reentry(self):
        d=self.fixture();out=stages(d)
        self.assertTrue(out['first_added'][24,24,24])
        self.assertTrue(out['blocked'].any())
        self.assertTrue(out['added'][24,24,12])
        self.assertFalse(out['added'][24,24,24])
        self.assertFalse(np.any(out['added']&out['blocked']))
        self.assertFalse(np.any(out['added']&d['parent']))

    def test_whole_rejection_loses_feeder_and_second_pass_extends_small_tube(self):
        d=self.fixture();out=stages(d,'whole_component')
        self.assertFalse(out['added'][24,24,12])
        d['accepted']=d['parent'].copy();d['accepted'][23:26,23:26,8:40]=True
        out=stages(d)
        self.assertFalse(out['first_added'][24,24,30])
        self.assertTrue(out['added'][24,24,30])
        self.assertFalse(out['added'][24,24,33])

if __name__=='__main__':unittest.main()
