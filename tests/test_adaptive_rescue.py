import unittest
from src.rebuild.adaptive_rescue import rescue_groups


class AdaptiveRescueTests(unittest.TestCase):
    def path(self,identity,trial):
        return dict(instance_id=identity,source='local_flood',flood_patch=1,flood_trial=trial,
            verification_decision='flood_path_requires_review',verification_score=.8,
            neural_distal_score=.75,automatic_checks={'boundary':True,'support':True},review_flags=[],
            ostium_xyz_mm=[0.,0.,0.],seed_xyz_mm=[5.,0.,0.],path_xyz_mm=[[0.,0.,0.],[5.,0.,0.]],
            origin_diameter_mm=3.,radius_mm=1.5,
            local_evidence=dict(supported_sections=5,clipped_sections=0,median_contrast_hu=240.,
                median_aspect=1.7,radius_ratio=2.3,seed_parent_distance_mm=4.6,
                opening_patch_26=1,sampling_mm=1.5))

    def test_agreeing_distinct_starts_rescue_one_opening(self):
        a,b=self.path('a',0),self.path('b',1)
        groups,rejected,rescued=rescue_groups([], [a,b])
        self.assertEqual(len(groups),1);self.assertEqual(len(rescued),2);self.assertEqual(rejected,[])

    def test_single_trace_does_not_trigger_rescue(self):
        groups,_,rescued=rescue_groups([],[self.path('a',0)])
        self.assertEqual(groups,[]);self.assertEqual(rescued,[])

    def test_same_start_is_not_corroboration(self):
        groups,_,_=rescue_groups([],[self.path('a',0),self.path('b',0)])
        self.assertEqual(groups,[])

    def test_geometry_or_clipped_section_cannot_be_overridden(self):
        for reason in ('geometry','clipped'):
            a,b=self.path('a',0),self.path('b',1)
            if reason=='geometry':b['automatic_checks']['boundary']=False
            else:b['local_evidence']['clipped_sections']=1
            groups,_,_=rescue_groups([],[a,b]);self.assertEqual(groups,[])

    def test_convergent_seeds_do_not_merge_distant_wall_origins(self):
        a,b=self.path('a',0),self.path('b',1);b['ostium_xyz_mm']=[0.,8.,0.]
        b['path_xyz_mm'][0]=b['ostium_xyz_mm']
        groups,_,_=rescue_groups([],[a,b]);self.assertEqual(groups,[])

    def test_established_representative_is_preserved(self):
        old=self.path('old',3);group={'representative':old,'alternative_candidate_ids':[]}
        groups,_,_=rescue_groups([group],[self.path('a',0),self.path('b',1)])
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['representative']['instance_id'],'old')

    def test_stable_width_wins_over_general_score(self):
        a,b=self.path('stable',0),self.path('variable',1)
        a['verification_score']=.75;b['verification_score']=.9
        a['local_evidence']['radius_ratio']=1.5;b['local_evidence']['radius_ratio']=2.4
        groups,_,_=rescue_groups([],[b,a])
        self.assertEqual(groups[0]['representative']['instance_id'],'stable')


if __name__=='__main__':unittest.main()
