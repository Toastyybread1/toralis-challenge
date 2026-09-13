import unittest
import numpy as np
from src.vascular_tree import validate_tree,follow_primary_branch

class TreeTests(unittest.TestCase):
    def test_curved_path_seed_uses_arc_length(self):
        p=[[0,0,0],[3,0,0],[3,4,0],[3,12,0]]
        r=follow_primary_branch(p,[(0,1),(1,2),(2,3)],0,1)
        self.assertEqual(r['tracking_status'],'length_complete')
        np.testing.assert_allclose(r['seed_xyz_mm'],[3,2,0])
        np.testing.assert_allclose(r['path_xyz_mm'][-1],[3,7,0])
        self.assertEqual(r['path_length_mm'],10)

    def test_first_split_stops_before_selecting_downstream_daughter(self):
        p=[[0,0,0],[4,0,0],[7,0,0],[10,3,0],[10,-3,0]]
        r=follow_primary_branch(p,[(0,1),(1,2),(2,3),(2,4)],0,1)
        self.assertEqual(r['bifurcation_node'],2)
        self.assertEqual(r['outgoing_node_indices'],[3,4])
        self.assertEqual(r['path_length_mm'],7)
        self.assertEqual(r['visited_node_indices'],[0,1,2])
        self.assertEqual(r['tracking_status'],'bifurcation_review_required')

    def test_early_split_has_no_invented_seed(self):
        p=[[0,0,0],[3,0,0],[7,3,0],[7,-3,0]]
        r=follow_primary_branch(p,[(0,1),(1,2),(1,3)],0,1)
        self.assertIsNone(r['seed_xyz_mm'])
        self.assertEqual(r['tracking_status'],'ambiguous_early_bifurcation')

    def test_selected_origin_edge_ignores_parent_junction(self):
        p=[[0,0,0],[11,0,0],[0,5,0],[0,-5,0]]
        r=follow_primary_branch(p,[(0,1),(0,2),(0,3)],0,1)
        self.assertIsNone(r['bifurcation_node'])
        self.assertEqual(r['tracking_status'],'length_complete')

    def test_leaf_before_limit_is_incomplete(self):
        r=follow_primary_branch([[0,0,0],[7,0,0]],[(0,1)],0,1)
        self.assertEqual(r['tracking_status'],'incomplete_leaf')
        self.assertEqual(r['seed_xyz_mm'],[5,0,0])

    def test_graph_errors_are_not_repaired_into_anatomy(self):
        p=[[0,0,0],[1,0,0],[1,1,0]]
        for edges in [[(0,1)],[(0,1),(1,2),(2,0)],[(0,1),(1,0),(1,2)]]:
            with self.assertRaises(ValueError):validate_tree(p,edges)
        with self.assertRaises(ValueError):validate_tree([[0,0,0],[0,0,0]],[(0,1)])

    def test_rigid_transform_preserves_distance_and_transforms_seed(self):
        p=np.array([[0,0,0],[3,0,0],[3,4,0],[3,12,0]],float)
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        moved=p@rotation.T+[10,20,30]
        r=follow_primary_branch(moved,[(0,1),(1,2),(2,3)],0,1)
        np.testing.assert_allclose(r['seed_xyz_mm'],np.array([3,2,0])@rotation.T+[10,20,30])
        self.assertEqual(r['path_length_mm'],10)

if __name__=='__main__':unittest.main()
