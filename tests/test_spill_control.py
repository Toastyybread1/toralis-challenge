import unittest
import numpy as np
from scipy import ndimage as ndi
from src.expansion import local_leakage_block
from src.rebuild.spill_control import porous_bulk_block


class PorousSpillTests(unittest.TestCase):
    def test_porosity_does_not_hide_large_bulk_and_feeder_survives(self):
        mask=np.zeros((42,42,70),bool)
        mask[8:34,8:34,30:62]=True
        # Open channels defeat an ordinary interior-ball test.
        mask[9:34:3,9:34:3,30:62]=False
        mask[19:22,19:22,3:31]=True
        labels,_=ndi.label(mask)
        components=[{'component_id':1,'volume_mm3':float(mask.sum())}]
        old=local_leakage_block(labels,components,(1,1,1))
        new=porous_bulk_block(labels,components,(1,1,1))
        self.assertFalse(old.any())
        self.assertTrue(new[20,20,45])
        self.assertFalse(new[20,20,10])
        self.assertFalse(new[~mask].any())

    def test_long_narrow_anisotropic_component_is_not_bulk(self):
        labels=np.zeros((12,12,240),int);labels[3:8,3:8,1:239]=1
        components=[{'component_id':1,'volume_mm3':6000}]
        self.assertFalse(porous_bulk_block(labels,components,(.5,1.,1.5)).any())
        with self.assertRaises(ValueError):porous_bulk_block(labels,components,(1,0,1))
        with self.assertRaises(ValueError):porous_bulk_block(labels,components,(1,1,1),closing_radius_mm=0)

if __name__=='__main__':unittest.main()
