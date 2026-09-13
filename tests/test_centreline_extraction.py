import unittest
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.centreline_extraction import extract_centreline,skeleton_graph
from src.vascular_tree import follow_primary_branch

class ExtractionTests(unittest.TestCase):
    def volume(self,kind='straight'):
        line=np.zeros((45,45,55),bool);line[22,22,5:30]=True
        if kind=='y':
            for d in range(15):line[22,22+d,29+d]=True;line[22,22-d,29+d]=True
        if kind=='spur':line[22,22:27,18]=True
        return ndi.distance_transform_edt(~line)<=1.5
    def run_extract(self,mask,anchor=(22,22,5),spacing=(1,1,1)):
        im=sitk.GetImageFromArray(mask.astype(np.uint8));im.SetSpacing(spacing)
        return extract_centreline(mask,im,anchor)
    def test_tube_has_two_endpoints_and_no_split(self):
        r=self.run_extract(self.volume())
        self.assertEqual(r['status'],'tree');self.assertEqual(len(r['leaf_nodes']),2)
        self.assertEqual(r['junction_nodes'],[])
    def test_curved_tube_remains_one_path(self):
        line=np.zeros((45,45,55),bool)
        line[22,22,5:25]=True
        for d in range(15):line[22,22+d,24+d]=True
        r=self.run_extract(ndi.distance_transform_edt(~line)<=1.5)
        self.assertEqual(r['status'],'tree')
        self.assertEqual(len(r['leaf_nodes']),2)
        self.assertEqual(r['junction_nodes'],[])

    def test_y_preserves_two_outgoing_arms(self):
        r=self.run_extract(self.volume('y'))
        self.assertEqual(r['status'],'tree');self.assertEqual(len(r['leaf_nodes']),3)
        self.assertEqual(len(r['junction_clusters']),1)
        root=r['root_node'];edges=r['edges']
        first=next(b if a==root else a for a,b in edges if root in [a,b])
        path=follow_primary_branch(r['points_xyz_mm'],edges,root,first,max_length_mm=40)
        self.assertEqual(path['tracking_status'],'bifurcation_review_required')
        self.assertEqual(len(path['outgoing_node_indices']),2)
    def test_disconnected_nearby_vessel_is_excluded(self):
        mask=self.volume();mask[30:33,30:33,5:30]=True
        r=self.run_extract(mask)
        self.assertEqual(r['input_components'],2);self.assertGreater(r['excluded_disconnected_voxels'],0)
        self.assertEqual(r['junction_nodes'],[])
    def test_spur_remains_visible_for_review(self):
        r=self.run_extract(self.volume('spur'))
        self.assertEqual(r['status'],'tree');self.assertGreater(len(r['junction_nodes']),0)
        self.assertEqual(len(r['leaf_nodes']),3)
    def test_loop_not_forced_to_tree(self):
        line=np.zeros((45,45,55),bool)
        line[22,10:31,10]=True;line[22,10:31,30]=True
        line[22,10,10:31]=True;line[22,30,10:31]=True
        mask=ndi.distance_transform_edt(~line)<=1.5
        r=self.run_extract(mask,anchor=(22,10,10))
        self.assertEqual(r['status'],'unresolved_topology')
    def test_physical_geometry_and_anisotropy(self):
        mask=self.volume();im=sitk.GetImageFromArray(mask.astype(np.uint8))
        im.SetSpacing((.5,1,2));im.SetOrigin((10,20,30));im.SetDirection((0,-1,0,1,0,0,0,0,1))
        r=extract_centreline(mask,im,[22,22,5]);self.assertTrue(r['anisotropic_thinning_warning'])
        for q,p in zip(r['node_indices_zyx'],r['points_xyz_mm']):
            np.testing.assert_allclose(p,im.TransformIndexToPhysicalPoint(q[::-1]))
    def test_anchor_budget_and_binary_validation(self):
        mask=self.volume();im=sitk.GetImageFromArray(mask.astype(np.uint8))
        self.assertEqual(extract_centreline(mask,im,[0,0,0])['status'],'anchor_outside_lumen')
        self.assertEqual(extract_centreline(mask,im,[22,22,5],max_voxels=2)['status'],'volume_budget_exceeded')
        with self.assertRaises(ValueError):extract_centreline(mask.astype(int)*2,im,[22,22,5])

if __name__=='__main__':unittest.main()
