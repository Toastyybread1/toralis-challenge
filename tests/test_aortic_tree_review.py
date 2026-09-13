import unittest
import numpy as np
from src.rebuild.aortic_tree_review import shortest_path, off_backbone_components, is_unbranched_return, review_candidate


def graph(n, edges):
    a=[set() for _ in range(n)]
    for u,v in edges:a[u].add(v);a[v].add(u)
    return a


class AorticTreeReviewTests(unittest.TestCase):
    def test_common_trunk_keeps_both_descendants_in_one_component(self):
        a=graph(6,[(0,1),(1,2),(1,3),(3,4),(3,5)])
        c=off_backbone_components(a,[0,1,2])
        self.assertEqual(len(c),1)
        self.assertEqual(c[0]['nodes'],[3,4,5])
        self.assertEqual(c[0]['attachments'],[1])
        self.assertFalse(is_unbranched_return(c[0],a))

    def test_separate_origins_remain_separate(self):
        a=graph(5,[(0,1),(1,2),(0,3),(1,4)])
        c=off_backbone_components(a,[0,1,2])
        self.assertEqual(sorted(x['attachments'] for x in c),[[0],[1]])

    def test_return_connection_is_distinguished_from_side_branch(self):
        a=graph(5,[(0,1),(1,2),(0,3),(3,4),(4,2)])
        self.assertTrue(is_unbranched_return(off_backbone_components(a,[0,1,2])[0],a))
        a.append({4});a[4].add(5)
        self.assertFalse(is_unbranched_return(off_backbone_components(a,[0,1,2])[0],a))

    def test_cycle_is_preserved_as_ambiguous(self):
        a=graph(6,[(0,1),(1,2),(1,3),(3,4),(4,5),(5,3)])
        c=off_backbone_components(a,[0,1,2])[0]
        self.assertTrue(c['cyclic'])
        self.assertFalse(is_unbranched_return(c,a))

    def test_backbone_cannot_shortcut_through_exterior(self):
        p=np.array([[0,0,0],[0,10,0],[2,0,0],[1,0,0]],float)
        a=graph(4,[(0,1),(1,2),(0,3),(3,2)])
        self.assertEqual(shortest_path(p,a,0,2),[0,3,2])
        self.assertEqual(shortest_path(p,a,0,2,{0,1,2}),[0,1,2])
        self.assertIsNone(shortest_path(p,a,0,2,{0,2}))

    def test_budget_failure_does_not_reject_a_candidate(self):
        r=review_candidate({}, {}, {'status':'volume_budget_exceeded'})
        self.assertEqual(r['decision'],'unresolved')


if __name__=='__main__':unittest.main()
