import copy
import unittest
import numpy as np
from src.rebuild.challenge_output import export_case


class ChallengeOutputTests(unittest.TestCase):
    def sample(self):
        return {'review_groups':[{'representative':dict(instance_id='candidate_88',
            ostium_xyz_mm=[10,20,30],seed_xyz_mm=[13,22,30],direction_xyz=[3,2,0],
            path_xyz_mm=[[10,20,30],[13,20,30],[13,27,30]],origin_diameter_mm=2.,radius_mm=1.2)}]}

    def test_physical_curved_seed_and_unique_ids(self):
        r=self.sample();before=copy.deepcopy(r);p,a=export_case(r,'subject001')
        self.assertEqual(r,before)
        self.assertEqual(p['parent'],{'instance_id':'aorta'})
        self.assertEqual(p['daughters'][0]['instance_id'],'branch_001')
        self.assertEqual(p['daughters'][0]['seed_xyz_mm'],[13,22,30])
        self.assertAlmostEqual(np.linalg.norm(p['daughters'][0]['direction_xyz']),1)

    def test_ineligible_and_deferred_not_exported(self):
        r=self.sample();r['deferred_groups']=copy.deepcopy(r['review_groups'])
        r['review_groups'][0]['representative']['origin_diameter_mm']=1.99
        p,a=export_case(r,'subject001')
        self.assertEqual(p['daughters'],[]);self.assertEqual(len(a['candidates']),2)

    def test_seed_at_euclidean_five_is_not_accepted_as_arc_five(self):
        r=self.sample();r['review_groups'][0]['representative']['seed_xyz_mm']=[13,24,30]
        p,a=export_case(r,'s');self.assertEqual(p['daughters'],[])
        self.assertEqual(a['candidates'][0]['exclusion_reason'],'seed_not_at_5mm_arc_length')

    def test_nonfinite_radius_and_reversed_direction_are_rejected(self):
        for field,value in [('radius_mm',float('nan')),('direction_xyz',[-3,-2,0])]:
            r=self.sample();r['review_groups'][0]['representative'][field]=value
            self.assertEqual(export_case(r,'s')[0]['daughters'],[])


if __name__=='__main__':unittest.main()
