import unittest
import numpy as np
import SimpleITK as sitk
from src.rebuild.border import border_faces,validate_pair,reference_border_distances

class BorderTests(unittest.TestCase):
    def test_single_voxel_exact_six_faces_and_distances(self):
        a=np.zeros((5,5,5),bool);a[2,2,2]=True
        f,inner,outer=border_faces(a)
        self.assertEqual(len(f['axis_zyx']),6);self.assertEqual(inner.sum(),1);self.assertEqual(outer.sum(),6)
        im=sitk.GetImageFromArray(a.astype(np.uint8));im.SetSpacing((2,3,4))
        im.SetOrigin((10,20,30));im.SetDirection((0,-1,0,1,0,0,0,0,1))
        face=im.TransformContinuousIndexToPhysicalPoint((2.5,2.,2.))
        centre=im.TransformIndexToPhysicalPoint((2,2,2))
        np.testing.assert_allclose(reference_border_distances([face,centre],im,f),[0,1])
    def test_shared_faces_removed_and_holes_preserved(self):
        a=np.zeros((5,5,5),bool);a[1:4,1:4,1:4]=True
        f,_,_=border_faces(a);self.assertEqual(len(f['axis_zyx']),54)
        a[2,2,2]=False;f,_,outer=border_faces(a)
        self.assertEqual(len(f['axis_zyx']),60);self.assertTrue(outer[2,2,2])
    def test_crop_faces_and_empty_mask(self):
        f,inner,outer=border_faces(np.ones((3,3,3),bool))
        self.assertEqual(f['image_cut_face'].sum(),54);self.assertEqual(inner.sum(),26);self.assertFalse(outer.any())
        f,inner,outer=border_faces(np.zeros((3,3,3),bool));self.assertEqual(len(f['axis_zyx']),0)
    def test_no_silent_geometry_or_multiclass_conversion(self):
        a=sitk.Image([5,5,5],sitk.sitkUInt8);b=sitk.Image(a);b.SetOrigin((1,0,0))
        with self.assertRaises(ValueError):validate_pair(a,b)
        b=sitk.Image(a);b[2,2,2]=2
        with self.assertRaises(ValueError):validate_pair(a,b)

if __name__=='__main__':unittest.main()
