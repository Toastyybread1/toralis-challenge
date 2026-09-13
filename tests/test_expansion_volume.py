import unittest
import numpy as np
from src.rebuild.spill_control import expansion_volume_block


class ExpansionVolumeTests(unittest.TestCase):
    def test_abrupt_expansion_blocked_but_proximal_tube_retained(self):
        labels=np.zeros((25,25,20),int)
        labels[11:14,11:14,1:7]=1
        labels[5:20,5:20,7:18]=1
        distance=np.broadcast_to(np.arange(20),(25,25,20)).astype(float)
        blocked,audit=expansion_volume_block(labels,[{'component_id':1}],distance,(1,1,1))
        self.assertFalse(blocked[12,12,5])
        self.assertTrue(blocked[12,12,8])
        self.assertEqual(audit[0]['blocked_from_parent_distance_mm'],6)
        self.assertFalse(blocked[labels==0].any())

    def test_constant_tube_is_retained_and_units_are_physical(self):
        labels=np.zeros((10,10,24),int);labels[3:7,3:7,1:23]=1
        distance=np.broadcast_to(np.arange(24)*.5,labels.shape)
        blocked,audit=expansion_volume_block(labels,[{'component_id':1}],distance,(.5,1,2))
        self.assertFalse(blocked.any())
        self.assertIsNone(audit[0]['blocked_from_parent_distance_mm'])
        self.assertAlmostEqual(sum(audit[0]['band_volumes_mm3']),float(np.count_nonzero(labels)))
        with self.assertRaises(ValueError):expansion_volume_block(labels,[{'component_id':1}],distance,(1,1,1),band_mm=0)

if __name__=='__main__':unittest.main()
