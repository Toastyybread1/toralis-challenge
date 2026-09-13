import unittest
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.rebuild.daughter_graph import detect_daughters,connect_endpoint


class DaughterGraphTests(unittest.TestCase):
    def test_straight_daughter_has_boundary_origin_and_five_mm_seed(self):
        z,y,x=np.indices((45,45,45));p=((x-10)**2+(y-22)**2<=25)&(z>=3)&(z<=41)
        line=np.zeros(p.shape,bool);line[22,22,10:36]=True
        daughter=(ndi.distance_transform_edt(~line)<=2)&~p
        im=sitk.GetImageFromArray(np.zeros(p.shape,np.float32))
        result=detect_daughters({'roi':im,'parent':p,'added':daughter})
        self.assertEqual(len(result['daughters']),1,msg=result['status_counts'])
        d=result['daughters'][0]
        self.assertAlmostEqual(d['ostium_xyz_mm'][0],15.5)
        r=next(r for r in result['candidate_records'] if r['status']=='provisional_daughter')
        self.assertEqual(r['tracking_status'],'length_complete')
        self.assertAlmostEqual(r['path_length_mm'],10)
        self.assertAlmostEqual(np.linalg.norm(np.array(d['seed_xyz_mm'])-d['ostium_xyz_mm']),5)

    def test_attachment_cannot_cross_background(self):
        lumen=np.zeros((5,5,10),bool);lumen[2,2,1:4]=True;lumen[2,2,5:9]=True
        path,node=connect_endpoint(lumen,(2,2,1),[(2,2,6)],np.ones(3))
        self.assertIsNone(path);self.assertIsNone(node)

if __name__=='__main__':unittest.main()
