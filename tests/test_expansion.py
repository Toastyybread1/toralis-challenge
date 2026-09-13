import unittest
import numpy as np
from scipy import ndimage as ndi
from src.expansion import bounded_expansion, fit_intensity_model


class ExpansionTests(unittest.TestCase):
    def fixture(self):
        p=np.zeros((25,25,35),bool);p[4:21,4:21,2:6]=True
        return p,np.zeros_like(p)

    def test_connected_tube_disconnected_object_and_physical_bound(self):
        p,a=self.fixture();a[11:14,11:14,6:30]=True;a[1:3,1:3,20:23]=True
        expanded,labels,c=bounded_expansion(p,a,(.5,1,2),radius_mm=4)
        self.assertTrue(expanded[p].all())
        self.assertFalse(labels[1:3,1:3,20:23].any())
        self.assertTrue(labels[12,12,13]);self.assertFalse(labels[12,12,14])
        self.assertEqual(len(c),1);self.assertTrue(c[0]['touches_distance_limit'])
        self.assertAlmostEqual(c[0]['volume_mm3'],float(np.count_nonzero(labels)))

    def test_common_trunk_and_nearby_origins(self):
        p,a=self.fixture();a[10:13,8:11,6:12]=True;a[10:13,14:17,6:12]=True
        _,_,c=bounded_expansion(p,a,(1,1,1))
        self.assertEqual(len(c),2)
        # Join farther out: preserve evidence of two separate parent contacts.
        a[10:13,8:17,11:14]=True
        _,_,c=bounded_expansion(p,a,(1,1,1))
        self.assertEqual(len(c),1);self.assertEqual(c[0]['contact_patch_count'],2)
        p,a=self.fixture();a[10:13,10:13,6:12]=True
        a[10:13,7:16,11:14]=True
        _,_,c=bounded_expansion(p,a,(1,1,1))
        self.assertEqual(c[0]['contact_patch_count'],1)

    def test_large_leak_and_crop_continuation_are_reported_not_deleted(self):
        p,a=self.fixture();a[10:13,10:13,6:10]=True;a[1:24,1:24,9:20]=True
        _,labels,c=bounded_expansion(p,a,(1,1,1))
        self.assertGreater(np.count_nonzero(labels),1000)
        self.assertEqual(c[0]['status'],'unclassified_expansion')
        p,a=self.fixture();a[10:13,10:13,:2]=True
        _,_,c=bounded_expansion(p,a,(1,1,1))
        self.assertTrue(c[0]['touches_crop_boundary'])

    def test_no_growth_and_invalid_radius(self):
        p,a=self.fixture();expanded,labels,c=bounded_expansion(p,a,(1,1,1))
        np.testing.assert_array_equal(expanded,p);self.assertEqual(c,[])
        with self.assertRaises(ValueError): bounded_expansion(p,a,(1,1,1),0)

    def test_intensity_model_separates_blood_and_background(self):
        p,a=self.fixture();ct=np.full(p.shape,-100.,np.float32);ct[p]=300
        ct[12,12,6:12]=300;ct[2,2,20]=np.nan
        distance=ndi.distance_transform_edt(~p)
        accepted,ratio,model=fit_intensity_model(ct,p,distance,np.ones(3))
        self.assertTrue(accepted[12,12,8]);self.assertFalse(accepted[2,2,15])
        self.assertFalse(accepted[2,2,20]);self.assertTrue(np.isfinite(ratio).all())
        self.assertFalse(model['used_whole_parent'])


if __name__=='__main__': unittest.main()
