import unittest
import tempfile
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.daughter_geometry import measure_branch,export_measurement
from src.rebuild.review_pipeline import same_origin,audit_prediction,local_proposals


class DocumentPipelineTests(unittest.TestCase):
    def tube(self):
        z,y,x=np.indices((40,40,50))
        parent=((x-10)**2+(y-20)**2<=25)&(z>=2)&(z<=37)
        line=np.zeros(parent.shape,bool);line[20,20,10:40]=True
        lumen=(ndi.distance_transform_edt(~line)<=2)&~parent
        image=sitk.GetImageFromArray(np.zeros(parent.shape,np.float32))
        # Exercise physical LPS coordinates rather than assuming identity.
        image.SetOrigin((31.,-24.,10.));image.SetDirection((0.,-1.,0.,1.,0.,0.,0.,0.,1.))
        return {'roi':image,'parent':parent,'added':lumen,
                'distance':ndi.distance_transform_edt(~parent),'ct':np.zeros(parent.shape,np.float32)}

    def test_ten_mm_path_has_exact_boundary_and_seed(self):
        d=self.tube()
        m,reason=measure_branch(d['parent'],d['added'],[20,20,16],[0,0,1],np.ones(3),strict_geometry=True)
        self.assertIsNotNone(m,reason)
        self.assertAlmostEqual(m['ostium_local_mm'][2],15.5,places=3)
        pred,path=export_measurement(m,d['roi']);pred.update(path_xyz_mm=path,tracking_status=m['tracking_status'])
        self.assertTrue(audit_prediction(pred,d))
        self.assertAlmostEqual(pred['path_length_mm'],10.)
        self.assertEqual(pred['review_decision'],'unresolved')
        self.assertIsNone(pred['reviewer'])

    def test_separate_ostia_not_deleted_when_seeds_converge(self):
        a={'ostium_xyz_mm':[0,0,0],'seed_xyz_mm':[5,0,0],'direction_xyz':[1,0,0]}
        b={**a,'ostium_xyz_mm':[0,2,0]}
        self.assertFalse(same_origin(a,b))
        self.assertTrue(same_origin(a,dict(a)))

    def test_disconnected_bright_structure_cannot_generate_contact(self):
        d=self.tube();d['added'][:]=False;d['added'][18:23,18:23,25:40]=True
        proposals,audit=local_proposals(d)
        self.assertEqual(proposals,[]);self.assertEqual(audit['contact_patches'],0)

    def test_seed_wrong_arc_length_fails_check(self):
        d=self.tube()
        m,_=measure_branch(d['parent'],d['added'],[20,20,16],[0,0,1],np.ones(3),strict_geometry=True)
        pred,path=export_measurement(m,d['roi']);pred.update(path_xyz_mm=path,tracking_status=m['tracking_status'])
        pred['seed_xyz_mm']=path[-1]
        self.assertFalse(audit_prediction(pred,d));self.assertFalse(pred['automatic_checks']['seed_at_5mm_arc'])

    def test_unsupported_gap_is_rejected(self):
        d=self.tube()
        m,_=measure_branch(d['parent'],d['added'],[20,20,16],[0,0,1],np.ones(3),strict_geometry=True)
        pred,path=export_measurement(m,d['roi']);pred.update(path_xyz_mm=path,tracking_status=m['tracking_status'])
        d['added'][:,:,19]=False
        self.assertFalse(audit_prediction(pred,d))
        self.assertFalse(pred['automatic_checks']['path_supported_by_connected_growth'])

    def test_small_origin_proxy_is_uncertain_not_certainly_excluded(self):
        d=self.tube()
        m,_=measure_branch(d['parent'],d['added'],[20,20,16],[0,0,1],np.ones(3),strict_geometry=True)
        pred,path=export_measurement(m,d['roi']);pred.update(path_xyz_mm=path,tracking_status=m['tracking_status'])
        from unittest.mock import patch
        with patch('src.rebuild.review_pipeline.section',return_value=[{'contains_centre':True,'edge':False,'area':np.pi*(1.91/2)**2}]):
            self.assertTrue(audit_prediction(pred,d))
        self.assertEqual(pred['diameter_eligibility'],'unresolved')

    def test_review_record_never_overwrites_human_work(self):
        from src.rebuild.review_record import write_review_record
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'review.json';path.write_text('{"reviewer_signoff":"reviewer"}')
            with self.assertRaises(FileExistsError):write_review_record({},'unused','unused','unused',path)
            self.assertIn('reviewer',path.read_text())


if __name__=='__main__':unittest.main()
