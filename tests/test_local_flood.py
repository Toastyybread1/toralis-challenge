import unittest
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.rebuild.local_flood import flood_proposals
from src.rebuild.review_pipeline import audit_prediction


class LocalFloodTests(unittest.TestCase):
    def fixture(self):
        z,y,x=np.indices((25,25,35));parent=x<=8
        line=np.zeros(parent.shape,bool)
        for xx in range(9,25):line[12,12+max(0,xx-13)//3,xx]=True
        lumen=(ndi.distance_transform_edt(~line)<=1.7)&~parent
        image=sitk.GetImageFromArray(np.zeros(parent.shape,np.float32))
        image.SetOrigin((20.,-15.,3.));image.SetDirection((0.,-1.,0.,1.,0.,0.,0.,0.,1.))
        return dict(roi=image,parent=parent,added=lumen,valid_support=np.ones_like(parent),
                    distance=ndi.distance_transform_edt(~parent))

    def test_curved_lumen_produces_supported_physical_seed(self):
        d=self.fixture();predictions,_=flood_proposals(d)
        self.assertTrue(predictions)
        for p in predictions:
            self.assertTrue(audit_prediction(p,d))
            self.assertAlmostEqual(p['path_length_mm'],5.)
            self.assertEqual(p['tracking_status'],'seed_only_distal_unresolved')

    def test_disconnected_lumen_cannot_be_reached(self):
        d=self.fixture();d['added'][:,:,:10]=False
        p,records=flood_proposals(d);self.assertEqual(p,[]);self.assertEqual(records,[])

    def test_invalid_ct_gap_blocks_flood(self):
        d=self.fixture();d['valid_support'][:,:,11]=False
        p,records=flood_proposals(d);self.assertEqual(p,[])
        self.assertTrue(any(r['status']=='flood_does_not_reach_6mm' for r in records))


if __name__=='__main__':unittest.main()
