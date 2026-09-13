import unittest
import importlib.util


@unittest.skipUnless(importlib.util.find_spec('torch'),'Optional learning dependencies not installed')
class LearnedSegmentationTests(unittest.TestCase):
    def test_folds_exclude_validation_subject(self):
        from src.rebuild.learned_segmentation import held_out_split
        for c in range(19,24):
            train=held_out_split(list(range(19,24)),c)
            self.assertNotIn(c,train);self.assertEqual(len(train),4)

    def test_ignored_voxels_have_zero_loss_gradient(self):
        import torch
        from src.rebuild.learned_segmentation import masked_loss
        logits=torch.zeros((1,1,4,4,4),requires_grad=True)
        target=torch.zeros_like(logits);target[:,:,1,1,1]=1
        mask=torch.zeros_like(logits);mask[:,:,:2]=1
        loss=masked_loss(logits,target,mask);loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(torch.all(logits.grad[mask==0]==0))
        self.assertTrue(torch.any(logits.grad[mask>0]!=0))

    def test_network_preserves_odd_input_size(self):
        import torch
        from src.rebuild.learned_segmentation import SmallUNet
        torch.set_num_threads(2)
        model=SmallUNet()
        with torch.no_grad():self.assertEqual(tuple(model(torch.zeros(1,3,9,11,13)).shape),(1,1,9,11,13))

if __name__=='__main__':unittest.main()
