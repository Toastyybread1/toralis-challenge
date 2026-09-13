import unittest
import numpy as np
import SimpleITK as sitk
from src.daughter_geometry import measure_branch,export_measurement
from src.review_validation import build_review
from src.evaluate_predictions import compare
from src.submission import contact_start_points

class ReviewTests(unittest.TestCase):
    def fixture(self):
        z,y,x=np.indices((41,41,65))
        parent=(x<12).astype(np.float32)
        lumen=(((y-20)**2+(z-20)**2<=16)&(x>=12)&(x<60)).astype(np.uint8)
        m,reason=measure_branch(parent,lumen,[20,20,12],[0,0,1],np.array([.5,.5,.5]))
        self.assertIsNone(reason)
        im=sitk.GetImageFromArray(lumen);im.SetSpacing((.5,.5,.5))
        im.SetOrigin((10,20,30));im.SetDirection((0,-1,0,1,0,0,0,0,1))
        branch,path=export_measurement(m,im)
        branch.update(instance_id='branch_001',parent_instance_id='aorta')
        details={k:m[k] for k in ['origin_diameter_mm','stop_reason']}
        details.update(instance_id='branch_001',path_xyz_mm=path)
        return {'case_id':'synthetic','daughters':[branch]}, {'branches':[details]},(im,parent,lumen)

    def test_valid_geometry_never_auto_approves(self):
        pred,diag,context=self.fixture();r=build_review(pred,diag,context)
        self.assertEqual(r['automatic_failure_count'],0)
        self.assertEqual(r['case_disposition'],'unresolved')
        self.assertIsNone(r['reviewer_sign_off']);self.assertEqual(r['approved_branch_ids'],[])
        self.assertTrue(all(v=='pending' for v in r['case_review'].values()))

    def test_wrong_seed_and_short_stop_fail(self):
        pred,diag,context=self.fixture();pred['daughters'][0]['seed_xyz_mm'][0]+=4
        r=build_review(pred,diag,context)
        self.assertEqual(r['branches'][0]['automatic_checks']['seed_at_5mm_along_path'],'fail')
        self.assertEqual(r['case_disposition'],'further edits required')
        pred,diag,context=self.fixture()
        diag['branches'][0]['path_xyz_mm']=diag['branches'][0]['path_xyz_mm'][:-3]
        diag['branches'][0]['stop_reason']='lost_lumen'
        r=build_review(pred,diag,context)
        self.assertEqual(r['branches'][0]['automatic_checks']['distal_stop_10mm_or_bifurcation_flag'],'fail')

    def test_null_reference_measurement_is_not_zero_or_error(self):
        pred,_,_=self.fixture();ref={'daughters':[dict(pred['daughters'][0],radius_mm=None)]}
        result=compare(pred,ref,3)
        self.assertEqual(result['tp'],1)
        self.assertNotIn('radius_absolute_error_mm',result['matches'][0])
        pred['daughters'][0]['radius_mm']=None
        _,diag,context=self.fixture();r=build_review(pred,diag,context)
        self.assertEqual(r['branches'][0]['automatic_checks']['seed_radius_present_positive_finite'],'unresolved')

    def test_empty_case_is_not_complete_or_approved(self):
        r=build_review({'case_id':'empty','daughters':[]},{},None)
        self.assertEqual(r['case_disposition'],'unresolved')
        self.assertEqual(r['completeness'],'not established by automatic detection')

    def test_reviewed_output_requires_new_version(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from src.review_validation import protect_reviewed_output
        pred,diag,context=self.fixture();review=build_review(pred,diag,context)
        with patch.object(Path,'exists',return_value=True):
            with patch.object(Path,'read_text',return_value=json.dumps(review)):
                protect_reviewed_output('prediction.json')
            review['branches'][0]['decision']='accept'
            with patch.object(Path,'read_text',return_value=json.dumps(review)):
                with self.assertRaises(ValueError):protect_reviewed_output('prediction.json')

    def test_contact_trials_are_bounded_and_metric(self):
        coords=np.array([[0,0,x] for x in range(10)])
        clearance=np.ones((1,1,10));clearance[0,0,0]=2
        chosen=contact_start_points(coords,clearance,np.array([1,1,.5]),max_points=3,separation_mm=2)
        self.assertEqual([p[2] for p in chosen],[0,4,8])

if __name__=='__main__':unittest.main()
