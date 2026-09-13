import unittest
from src.rebuild.hybrid_candidates import overlapping_seed,path_score
import numpy as np
import SimpleITK as sitk


class HybridTests(unittest.TestCase):
    def test_separate_small_vessels_are_not_grouped(self):
        a={'seed_xyz_mm':[0,0,0],'radius_mm':1.}
        self.assertFalse(overlapping_seed(a,{'seed_xyz_mm':[2.1,0,0],'radius_mm':1.}))
        self.assertTrue(overlapping_seed(a,{'seed_xyz_mm':[.5,0,0],'radius_mm':1.2}))
        self.assertFalse(overlapping_seed(a,{'seed_xyz_mm':[1.1,0,0],'radius_mm':5.}))

    def test_weak_origin_does_not_zero_distal_evidence(self):
        probability=np.ones((10,10,10),np.float32)*.8;probability[:,:,:2]=0
        im=sitk.GetImageFromArray(probability)
        self.assertAlmostEqual(path_score([[0,5,5],[5,5,5]],probability,im),.8,places=5)
        with self.assertRaises(ValueError):path_score([[0,5,5],[4,5,5]],probability,im)

if __name__=='__main__':unittest.main()
