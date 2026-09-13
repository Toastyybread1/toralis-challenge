import unittest
import numpy as np
import nibabel as nib
from nibabel.processing import resample_from_to
import SimpleITK as sitk
from src.rebuild.image_support import resampled_support
from src.rebuild.intensity_growth import grow


class ImageSupportTests(unittest.TestCase):
    def test_support_matches_linear_resampler_with_shear_and_translation(self):
        shape=(12,13,14);source=np.eye(4);source[0,1]=.03
        target=np.diag([.8,1.2,1.5,1.]);target[:3,3]=[-1,.3,-2]
        support=resampled_support(shape,source,(18,16,15),target)
        actual=resample_from_to(nib.Nifti1Image(np.full(shape,100.,np.float32),source),((18,16,15),target),order=1)
        self.assertTrue(np.array_equal(support,np.asanyarray(actual.dataobj)>0))
        self.assertTrue(support.any());self.assertTrue((~support).any())

    def test_zero_hu_is_valid_and_padding_cannot_grow(self):
        p=np.zeros((35,35,35),bool);p[10:25,10:25,10:25]=True
        ct=np.full(p.shape,-100.,np.float32);ct[p]=0
        ct[15:20,15:20,25:35]=0
        image=sitk.GetImageFromArray(ct);mask=sitk.GetImageFromArray(p.astype(np.uint8))
        valid=np.ones(p.shape,bool);valid[:,:,30:]=False
        data=grow(image,mask,0,.5,valid_support=valid)
        self.assertTrue(data['added'][17,17,27])
        self.assertFalse(data['added'][17,17,32])
        self.assertFalse(data['accepted'][~valid].any())
        with self.assertRaises(ValueError):grow(image,mask,valid_support=np.zeros(p.shape,bool))

if __name__=='__main__':unittest.main()
