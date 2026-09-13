"""Safety boundaries for bounded origin and merged-plane reinspection."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import SimpleITK as sitk
from src.rebuild.origin_review import eligible_replacement, review_origins
from src.rebuild.section_review import flagged, repaired_evidence
from src.rebuild.opening_verification import plane_evidence


class ProtocolReviewTests(unittest.TestCase):
    def proposal(self):
        sections=[dict(supported=True,edge=False,radius_mm=1.,contrast_hu=150.,
                       lumen_median_hu=250.,aspect=1.,offcentre_ratio=0.) for _ in range(5)]
        return dict(source='local_flood',automatic_checks={'boundary':True,'support':True},
            ostium_xyz_mm=[0.,0.,0.],seed_xyz_mm=[5.,0.,0.],
            path_xyz_mm=[[0.,0.,0.],[5.,0.,0.]],radius_mm=1.,origin_diameter_mm=2.,
            neural_distal_score=.6,local_evidence=dict(sections=sections,
                supported_sections=5,clipped_sections=0,radius_ratio=1.,
                median_contrast_hu=250.,seed_parent_distance_mm=4.,
                opening_patch_26=1,sampling_mm=1.5))

    def clipped(self):
        p=self.proposal();p['local_evidence']['clipped_sections']=1
        p['local_evidence']['sections'][2].update(edge=True,radius_mm=4.)
        return p

    def repair(self,p,replacement=None):
        if replacement is None:replacement=self.proposal()['local_evidence']['sections'][0]
        with patch('src.rebuild.section_review.path_samples',return_value=(np.zeros((5,3)),np.ones((5,3)),None)), \
             patch('src.rebuild.section_review.plane_evidence',return_value=replacement):
            return repaired_evidence(p,{'roi':None})

    def test_origin_requires_valid_geometry_and_scored_improvement(self):
        old=self.proposal();old['neural_distal_score']=.45
        p=self.proposal();self.assertTrue(eligible_replacement(old,p))
        for checks,score in [({},.9),({'support':False},.9),({'support':True},None),({'support':True},.46)]:
            q=copy.deepcopy(p);q.update(automatic_checks=checks,neural_distal_score=score)
            self.assertFalse(eligible_replacement(old,q))

    def test_origin_cannot_jump_to_separate_wall_opening(self):
        old=self.proposal();old['neural_distal_score']=.45
        p=self.proposal();p['ostium_xyz_mm']=[0.,8.,0.]
        p['path_xyz_mm'][0]=p['ostium_xyz_mm']
        self.assertFalse(eligible_replacement(old,p))

    def test_strong_existing_opening_does_not_trigger_dense_search(self):
        group={'representative':self.proposal()}
        with patch('src.rebuild.origin_review.flood_proposals') as flood:
            groups,tested,records=review_origins([group],{})
        flood.assert_not_called();self.assertIs(groups[0],group)
        self.assertEqual(tested,[]);self.assertEqual(records,[])

    def test_two_clipped_sections_or_invalid_geometry_are_not_repaired(self):
        p=self.clipped();self.assertTrue(flagged(p))
        for checks,clipped in [({},1),({'support':False},1),({'support':True},2)]:
            q=copy.deepcopy(p);q['automatic_checks']=checks
            q['local_evidence']['clipped_sections']=clipped
            self.assertFalse(flagged(q));self.assertIsNone(self.repair(q))

    def test_repair_preserves_original_and_four_bounded_planes(self):
        p=self.clipped();before=copy.deepcopy(p)
        f,index=self.repair(p)
        self.assertEqual(index,2);self.assertEqual(f['clipped_sections'],0)
        self.assertEqual(p,before)
        for i in [0,1,3,4]:self.assertEqual(f['sections'][i],before['local_evidence']['sections'][i])

    def test_missing_centre_and_persistent_spill_reject_repair(self):
        for field in ['supported','edge']:
            replacement=self.proposal()['local_evidence']['sections'][0]
            replacement[field]=(field=='edge')
            self.assertIsNone(self.repair(self.clipped(),replacement))

    def test_inconsistent_intensity_or_width_rejects_repair(self):
        for field,value in [('contrast_hu',50.),('lumen_median_hu',500.),('radius_mm',2.)]:
            replacement=self.proposal()['local_evidence']['sections'][0]
            replacement[field]=value
            self.assertIsNone(self.repair(self.clipped(),replacement))

    def test_opening_cannot_create_lumen_or_edit_3d_segmentation(self):
        z,y,x=np.indices((25,25,25));lumen=(y-12)**2+(x-12)**2<=4
        data={'roi':sitk.GetImageFromArray(np.zeros(lumen.shape,np.float32)),
              'added':lumen,'parent':np.zeros_like(lumen),'valid_support':np.ones_like(lumen),
              'ct':np.where(lumen,300.,50.).astype(np.float32)}
        before=lumen.copy();centre=np.array([12.,12.,12.]);tangent=np.array([1.,0.,0.])
        raw=plane_evidence(centre,tangent,data)
        repaired=plane_evidence(centre,tangent,data,neck_opening_mm=.5)
        self.assertLessEqual(repaired['area_mm2'],raw['area_mm2'])
        self.assertTrue(np.array_equal(before,data['added']))
        self.assertFalse(plane_evidence(np.array([12.,4.,4.]),tangent,data,neck_opening_mm=.5)['supported'])


if __name__=='__main__':unittest.main()
