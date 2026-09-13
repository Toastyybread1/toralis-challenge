"""Physical boundary entry and unsupported-path regression tests."""
import unittest
import numpy as np
from src.daughter_geometry import measure_branch, path_lumen_supported


class FaceOriginTests(unittest.TestCase):
    def fixture(self):
        z,y,x=np.indices((25,25,35))
        parent=x<=8
        lumen=((z-12)**2+(y-12)**2<=4)&(x>8)&(x<30)
        return parent,lumen

    def test_anisotropic_face_and_five_mm_arc(self):
        parent,lumen=self.fixture();spacing=np.array([2.,1.,1.5])
        m,reason=measure_branch(parent,lumen,[12,12,9],[0,0,1],spacing,
            strict_geometry=True,origin_local_mm=np.array([12,12,8.5])*spacing)
        self.assertIsNotNone(m,reason)
        self.assertEqual(m['ostium_local_mm'][2],12.75)
        self.assertAlmostEqual(m['seed_local_mm'][2]-12.75,5.)
        self.assertTrue(path_lumen_supported(m['path_local_mm'],spacing,lumen,parent))

    def test_arbitrary_exterior_origin_rejected(self):
        p,l=self.fixture()
        m,reason=measure_branch(p,l,[12,12,9],[0,0,1],np.ones(3),
            strict_geometry=True,origin_local_mm=[12,12,9.])
        self.assertIsNone(m);self.assertEqual(reason,'unsupported_face_entry')

    def test_inward_direction_rejected(self):
        p,l=self.fixture()
        m,reason=measure_branch(p,l,[12,12,9],[0,0,-1],np.ones(3),
            strict_geometry=True,origin_local_mm=[12,12,8.5])
        self.assertIsNone(m);self.assertEqual(reason,'unsupported_face_entry')

    def test_gap_before_seed_cannot_be_bridged(self):
        p,l=self.fixture();l[:,:,11]=False
        m,reason=measure_branch(p,l,[12,12,9],[0,0,1],np.ones(3),
            strict_geometry=True,origin_local_mm=[12,12,8.5])
        self.assertIsNone(m)


if __name__=='__main__':unittest.main()
