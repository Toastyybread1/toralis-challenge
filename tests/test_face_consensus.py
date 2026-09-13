import unittest
from unittest.mock import patch
from src.rebuild.opening_verification import select_verified


class FaceConsensusTests(unittest.TestCase):
    def proposal(self,identity,face=True,score=.9,direction=0):
        return dict(instance_id=identity,origin_initialization='contact_face' if face else 'backward_ray',
            trial=0,direction_trial=direction,neural_distal_score=score,
            ostium_xyz_mm=[0.,0.,0.],seed_xyz_mm=[5.,0.,0.],path_xyz_mm=[[0.,0.,0.],[5.,0.,0.],[10.,0.,0.]],
            radius_mm=1.,origin_diameter_mm=2.,automatic_checks={'valid':True})

    def select(self,proposals):
        evidence=dict(opening_patch_26=1,sampling_mm=1.,supported_sections=5,clipped_sections=0,
                      median_aspect=1.2,radius_ratio=1.2,median_contrast_hu=200.,
                      seed_parent_distance_mm=4.5,median_offcentre_ratio=.1)
        with patch('src.rebuild.opening_verification.opening_context',return_value=None),patch(
                'src.rebuild.opening_verification.verify_candidate',side_effect=lambda *args:dict(evidence)):
            return select_verified(proposals,{})

    def test_isolated_high_score_face_does_not_add_vessel(self):
        p=self.proposal('a');groups,rejected=self.select([p])
        self.assertEqual(groups,[]);self.assertEqual(len(rejected),1)

    def test_repeated_same_direction_not_independent_consensus(self):
        groups,_=self.select([self.proposal('a'),self.proposal('b')])
        self.assertEqual(groups,[])

    def test_distinct_directions_recover_one_group(self):
        groups,_=self.select([self.proposal('a'),self.proposal('b',direction=1)])
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['representative']['face_consensus_candidate_ids'],['b'])

    def test_weak_or_missing_network_cannot_enable_face_rescue(self):
        for score in (.6,None):
            a=self.proposal('a',score=.6);b=self.proposal('b',score=.6,direction=1)
            if score is None:
                del a['neural_distal_score'];del b['neural_distal_score']
            groups,_=self.select([a,b]);self.assertEqual(groups,[])

    def test_face_score_cannot_displace_established_origin(self):
        old=self.proposal('old',face=False,score=.6)
        new=self.proposal('new',score=.99,direction=1)
        groups,_=self.select([new,old])
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['representative']['instance_id'],'old')

    def test_converging_distinct_ostia_do_not_corroborate(self):
        a=self.proposal('a');b=self.proposal('b',direction=1)
        b['ostium_xyz_mm']=[0.,5.,0.];b['path_xyz_mm'][0]=b['ostium_xyz_mm']
        groups,_=self.select([a,b]);self.assertEqual(groups,[])

    def test_flood_needs_stronger_network_support(self):
        p=self.proposal('flood',face=False,score=.85);p['source']='local_flood'
        groups,_=self.select([p]);self.assertEqual(groups,[])
        p=self.proposal('flood',face=False,score=.95);p['source']='local_flood'
        groups,_=self.select([p]);self.assertEqual(len(groups),1)

    def test_flood_does_not_displace_established_origin(self):
        old=self.proposal('old',face=False,score=.6)
        flood=self.proposal('flood',face=False,score=.99);flood['source']='local_flood'
        groups,_=self.select([flood,old])
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['representative']['instance_id'],'old')


if __name__=='__main__':unittest.main()
