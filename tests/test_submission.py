import unittest
import numpy as np
import SimpleITK as sitk
from src.daughter_geometry import measure_branch,export_measurement,tracking_status,path_lumen_supported
from src.submission import detect


class SubmissionTests(unittest.TestCase):
    def geometry(self):
        z,y,x=np.indices((41,41,65))
        parent=(x<12).astype(np.float32)
        lumen=((y-20)**2+(z-20)**2<=16)&(x>=12)&(x<60)
        return parent,lumen.astype(np.uint8)

    def test_seed_arc_length_radius_and_direction(self):
        p,l=self.geometry()
        m,reason=measure_branch(p,l,[20,20,12],[0,0,1],np.array([.5,.5,.5]))
        self.assertIsNone(reason);self.assertIsNotNone(m)
        self.assertAlmostEqual(np.linalg.norm(m['seed_local_mm']-m['ostium_local_mm']),5,places=3)
        self.assertAlmostEqual(m['radius_mm'],2,delta=.4)
        self.assertAlmostEqual(m['path_length_mm'],10,places=3)
        image=sitk.Image([65,41,41],sitk.sitkUInt8);image.SetSpacing((.5,.5,.5))
        image.SetOrigin((10,20,30));image.SetDirection((0,-1,0,1,0,0,0,0,1))
        result,path=export_measurement(m,image)
        np.testing.assert_allclose(result['direction_xyz'],[0,1,0],atol=.01)
        self.assertTrue(np.isfinite(path).all())

    def test_short_vessel_has_no_seed(self):
        p,l=self.geometry();l[:,:,18:]=0
        m,reason=measure_branch(p,l,[20,20,12],[0,0,1],np.array([.5,.5,.5]))
        self.assertIsNone(m)

    def test_track_beyond_seed_but_short_of_endpoint_is_incomplete(self):
        p,l=self.geometry();l[:,:,27:]=0
        m,reason=measure_branch(p,l,[20,20,12],[0,0,1],np.array([.5,.5,.5]))
        self.assertIsNone(reason)
        self.assertGreaterEqual(m['path_length_mm'],5)
        self.assertLess(m['path_length_mm'],10)
        self.assertEqual(m['tracking_status'],'incomplete')
        self.assertNotEqual(m['stop_reason'],'length_limit')

    def test_bifurcation_status_is_provisional_and_early_split_is_incomplete(self):
        self.assertEqual(tracking_status(7,'possible_bifurcation'),'bifurcation_review_required')
        self.assertEqual(tracking_status(4,'possible_bifurcation'),'incomplete')
        self.assertEqual(tracking_status(7,'iteration_limit'),'incomplete')
        self.assertEqual(tracking_status(10,'length_limit'),'length_complete')

    def test_incomplete_detection_is_retained_only_in_diagnostics(self):
        z,y,x=np.indices((60,64,72))
        p=((x-24)**2+(y-32)**2<=64)
        branch=((z-30)**2+(y-32)**2<=9)&(x>=24)&(x<=42)
        image=sitk.GetImageFromArray(np.where(p|branch,300,-100).astype(np.float32))
        image.SetSpacing((.7,.7,.7))
        mask=sitk.GetImageFromArray(p.astype(np.uint8));mask.CopyInformation(image)
        daughters,diag,_=detect(image,mask)
        self.assertEqual(daughters,[])
        partial=[c for c in diag['candidate_records'] if c.get('tracking_status')=='incomplete']
        self.assertTrue(partial)
        self.assertGreaterEqual(partial[0]['partial_measurement']['path_length_mm'],5)
        self.assertTrue(partial[0]['partial_measurement']['path_xyz_mm'])

    def test_five_mm_milestone_is_distinct_from_full_completion(self):
        p,l=self.geometry();l[:,:,27:]=0
        short,reason=measure_branch(p,l,[20,20,12],[0,0,1],np.array([.5,.5,.5]),target_length_mm=5)
        self.assertIsNone(reason)
        self.assertAlmostEqual(short['path_length_mm'],5)
        np.testing.assert_allclose(short['path_local_mm'][-1],short['seed_local_mm'])
        self.assertEqual(short['tracking_status'],'seed_milestone_complete')
        full,reason=measure_branch(p,l,[20,20,12],[0,0,1],np.array([.5,.5,.5]))
        self.assertEqual(full['tracking_status'],'incomplete')

    def test_segment_validation_detects_gap_between_valid_endpoints(self):
        lumen=np.ones((3,3,5),np.uint8);parent=np.zeros_like(lumen)
        lumen[1,1,2]=0
        self.assertFalse(path_lumen_supported([np.array([1,1,1]),np.array([1,1,3])],np.ones(3),lumen,parent))
        lumen[1,1,2]=1
        self.assertTrue(path_lumen_supported([np.array([1,1,1]),np.array([1,1,3])],np.ones(3),lumen,parent))
        parent[1,1,2]=1
        self.assertFalse(path_lumen_supported([np.array([1,1,1]),np.array([1,1,3])],np.ones(3),lumen,parent))

    def test_invalid_milestone_rejected(self):
        p,l=self.geometry()
        with self.assertRaises(ValueError):measure_branch(p,l,[20,20,12],[0,0,1],np.ones(3),target_length_mm=4)

    def test_empty_parent_valid_empty_result(self):
        im=sitk.Image([10,10,10],sitk.sitkFloat32);mask=sitk.Image([10,10,10],sitk.sitkUInt8)
        daughters,diagnostics,_=detect(im,mask)
        self.assertEqual(daughters,[])

    def test_alignment_errors_are_explicit(self):
        im=sitk.Image([10,10,10],sitk.sitkFloat32);mask=sitk.Image([10,10,10],sitk.sitkUInt8)
        mask.SetOrigin((1,0,0))
        with self.assertRaises(ValueError):detect(im,mask)

    def test_ct_to_one_daughter_and_empty_ct(self):
        z,y,x=np.indices((60,64,72))
        p=((x-24)**2+(y-32)**2<=64)
        branch=((z-30)**2+(y-32)**2<=9)&(x>=24)&(x<=60)
        image=sitk.GetImageFromArray(np.where(p|branch,300,-100).astype(np.float32))
        image.SetSpacing((.7,.7,.7))
        mask=sitk.GetImageFromArray(p.astype(np.uint8));mask.CopyInformation(image)
        daughters,_,_=detect(image,mask)
        self.assertEqual(len(daughters),1)
        self.assertAlmostEqual(daughters[0]['radius_mm'],2.1,delta=.4)
        np.testing.assert_allclose(daughters[0]['direction_xyz'],[1,0,0],atol=.05)
        image=sitk.GetImageFromArray(np.where(p,300,-100).astype(np.float32));image.CopyInformation(mask)
        daughters,_,_=detect(image,mask)
        self.assertEqual(daughters,[])


if __name__=='__main__':unittest.main()
