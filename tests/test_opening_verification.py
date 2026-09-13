import unittest
import numpy as np
import SimpleITK as sitk
from src.rebuild.opening_verification import plane_evidence,same_opening,evidence_decision


class OpeningVerificationTests(unittest.TestCase):
    def proposal(self,origin=(0.,0.,0.),seed=(5.,0.,0.)):
        return {'ostium_xyz_mm':list(origin),'seed_xyz_mm':list(seed),
                'path_xyz_mm':[list(origin),list(seed),[10.,0.,0.]],
                'radius_mm':1.,'origin_diameter_mm':2.,'neural_distal_score':.1,
                'local_evidence':{'opening_patch_26':1,'sampling_mm':1.,
                'supported_sections':5,'clipped_sections':0,'median_aspect':1.2,
                'radius_ratio':1.2,'median_contrast_hu':200.,'seed_parent_distance_mm':4.5}}

    def test_strong_local_lumen_can_rescue_weak_neural_score(self):
        self.assertEqual(evidence_decision(self.proposal()),'local_evidence_rescue')

    def test_high_neural_score_cannot_rescue_unbounded_tissue(self):
        p=self.proposal();p['neural_distal_score']=.99;p['local_evidence']['clipped_sections']=3
        self.assertEqual(evidence_decision(p),'local_evidence_unresolved')

    def test_bright_path_hugging_parent_is_not_neural_rescue(self):
        p=self.proposal();p['local_evidence']['seed_parent_distance_mm']=1.
        self.assertEqual(evidence_decision(p),'local_evidence_unresolved')

    def test_separate_ostia_with_converging_seeds_are_preserved(self):
        a=self.proposal();b=self.proposal((0.,4.,0.))
        self.assertFalse(same_opening(a,b))

    def test_offset_seed_on_same_proximal_path_is_duplicate(self):
        a=self.proposal();b=self.proposal((.5,0.,0.),(7.,0.,0.))
        self.assertTrue(same_opening(a,b));self.assertTrue(same_opening(b,a))

    def test_near_origins_with_separate_paths_are_preserved(self):
        a=self.proposal();b=self.proposal((0.,1.,0.),(0.,6.,0.));b['path_xyz_mm']=[[0.,1.,0.],[0.,6.,0.],[0.,10.,0.]]
        self.assertFalse(same_opening(a,b))

    def test_plane_measures_ct_contrast_and_rejects_missing_centre(self):
        z,y,x=np.indices((25,25,25));lumen=(y-12)**2+(x-12)**2<=4
        data={'roi':sitk.GetImageFromArray(np.zeros(lumen.shape,np.float32)),
              'added':lumen,'parent':np.zeros_like(lumen),'valid_support':np.ones_like(lumen),
              'ct':np.where(lumen,300.,50.).astype(np.float32)}
        f=plane_evidence(np.array([12.,12.,12.]),np.array([1.,0.,0.]),data)
        self.assertTrue(f['supported']);self.assertFalse(f['edge']);self.assertGreater(f['contrast_hu'],200.)
        self.assertLess(f['aspect'],1.1)
        f=plane_evidence(np.array([12.,4.,4.]),np.array([1.,0.,0.]),data)
        self.assertFalse(f['supported'])


if __name__=='__main__':unittest.main()
