import unittest
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.rebuild.origin_triage import triage_origin


class OriginTriageTests(unittest.TestCase):
    def fixture(self,points,spacing=(1.,1.,1.)):
        parent=np.zeros((40,20,20),bool);parent[5:35,5:15,5:10]=True
        image=sitk.GetImageFromArray(parent.astype(np.uint8));image.SetSpacing(spacing)
        image.SetOrigin((12.,-30.,9.));image.SetDirection((0.,-1.,0.,1.,0.,0.,0.,0.,1.))
        path=[image.TransformContinuousIndexToPhysicalPoint(tuple(map(float,q))) for q in points]
        return dict(ostium_xyz_mm=path[0],path_xyz_mm=path,diameter_eligibility='unresolved'),dict(
            roi=image,parent=parent,distance=ndi.distance_transform_edt(~parent,sampling=spacing[::-1]))

    def test_wall_parallel_path_is_flagged_without_rejection(self):
        p,d=self.fixture([(9.5,10,15),(12,10,15),(12,10,25)])
        r=triage_origin(p,d)
        self.assertTrue(r['distal_wall_parallel']);self.assertEqual(r['direct_origin_status'],'unresolved')
        self.assertNotIn('selection_reason',p)

    def test_outward_path_is_not_parallel(self):
        p,d=self.fixture([(9.5,10,20),(19,10,20)])
        self.assertFalse(triage_origin(p,d)['distal_wall_parallel'])

    def test_seed_only_path_is_not_extrapolated(self):
        p,d=self.fixture([(9.5,10,20),(12,10,20),(12,10,22.5)])
        r=triage_origin(p,d)
        self.assertFalse(r['distal_wall_parallel']);self.assertLessEqual(max(r['distance_sample_arclength_mm']),5.)

    def test_cap_proxy_uses_physical_spacing_and_cell_faces(self):
        p,d=self.fixture([(9.5,10,5),(12,10,5)],spacing=(1.,1.,2.))
        r=triage_origin(p,d)
        self.assertAlmostEqual(r['origin_to_nearest_parent_end_proxy_mm'],1.)
        self.assertIn('origin_near_supplied_parent_end',r['flags'])

    def test_empty_parent_is_explicit_error(self):
        p,d=self.fixture([(9.5,10,20),(19,10,20)]);d['parent'][:]=False
        with self.assertRaises(ValueError):triage_origin(p,d)


if __name__=='__main__':unittest.main()
