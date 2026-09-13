import unittest
import numpy as np
from scipy import ndimage as ndi
from src.expansion import local_leakage_block

class LocalLeakageTests(unittest.TestCase):
    def test_preserves_narrow_feeder_and_blocks_bulky_region_anisotropic(self):
        mask=np.zeros((42,42,80),bool)
        mask[18:23,18:23,2:35]=True
        mask[8:34,8:34,34:75]=True
        labels,_=ndi.label(mask)
        spacing=(.5,1.,1.5)
        components=[{'component_id':1,'volume_mm3':float(mask.sum()*np.prod(spacing))}]
        blocked=local_leakage_block(labels,components,spacing)
        self.assertFalse(blocked[20,20,10])
        self.assertTrue(blocked[20,20,50])
        self.assertFalse(blocked[~mask].any())
        self.assertGreater((mask&~blocked).sum(),0)

    def test_long_thin_oversized_region_is_retained(self):
        labels=np.zeros((12,12,240),int);labels[3:8,3:8,1:239]=1
        blocked=local_leakage_block(labels,[{'component_id':1,'volume_mm3':5950}],(1,1,1))
        self.assertFalse(blocked.any())

    def test_small_component_unchanged_tiny_removed_and_invalid_inputs(self):
        labels=np.zeros((8,8,8),int);labels[2:5,2:5,2:5]=1;labels[6,6,6]=2
        components=[{'component_id':1,'volume_mm3':27},{'component_id':2,'volume_mm3':1}]
        blocked=local_leakage_block(labels,components,(1,1,1))
        self.assertFalse(blocked[labels==1].any());self.assertTrue(blocked[6,6,6])
        with self.assertRaises(ValueError):local_leakage_block(labels,components,(0,1,1))
        with self.assertRaises(ValueError):local_leakage_block(labels,components,(1,1,1),0)

if __name__=='__main__':unittest.main()
