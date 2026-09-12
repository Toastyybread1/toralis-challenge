"""Regressions for fallback bypasses found during the integration review."""
import unittest
from unittest.mock import patch
import numpy as np
from scipy import ndimage as ndi

from test_detection import phantom
from src.detection import detect_candidates
from src.preprocessing import prepare_case
from src.tracing import analyze_candidates, _skeleton_graph
from src.types import Config


class FallbackTests(unittest.TestCase):
    def prepare(self, segments, **options):
        config = Config(**options)
        roi = prepare_case(phantom(segments), config)
        candidates, context = detect_candidates(roi, config)
        self.assertTrue(candidates)
        return candidates, roi, context, config

    def test_early_bifurcation_cannot_be_bypassed(self):
        args = self.prepare([((4, 0, 32), (9, 0, 32), 1.2),
                             ((9, 0, 32), (20, 7, 32), 1.2),
                             ((9, 0, 32), (20, -7, 32), 1.2)])
        self.assertEqual(analyze_candidates(*args), [])
        report = args[2].diagnostics["trace_candidates"][0]
        self.assertTrue(report["fallback"]["attempted"])
        self.assertGreater(report["fallback"]["target_rejections"]["short_or_early_split"], 0)

    def test_empty_primary_skeleton_retries_and_recovers(self):
        args = self.prepare([((4, 0, 32), (19, 0, 32), 2)])
        args[2].lumen[:] = False
        with patch("src.tracing._skeleton_graph", wraps=_skeleton_graph) as builder:
            branches = analyze_candidates(*args)
            self.assertEqual(builder.call_count, 2)
        self.assertEqual(len(branches), 1)
        report = args[2].diagnostics["trace_candidates"][0]
        self.assertEqual(report["primary"]["rejected"], "empty_skeleton")
        self.assertTrue(report["fallback"]["selected"])
        self.assertNotIn("rejected", report)
        self.assertLessEqual(np.linalg.norm(np.diff(branches[0].path_xyz_mm, axis=0), axis=1).sum(), 10.00001)

    def test_missing_primary_component_retries(self):
        args = self.prepare([((4, 0, 32), (19, 0, 32), 2)])
        args[2].labels[:] = 0
        self.assertEqual(len(analyze_candidates(*args)), 1)
        report = args[2].diagnostics["trace_candidates"][0]
        self.assertEqual(report["primary"]["rejected"], "no_skeleton_near_contact")
        self.assertTrue(report["fallback"]["selected"])

    def test_fallback_stops_at_first_later_split(self):
        args = self.prepare([((4, 0, 32), (14, 0, 32), 1.6),
                             ((14, 0, 32), (22, 6, 32), 1.6),
                             ((14, 0, 32), (22, -6, 32), 1.6)])
        args[2].lumen[:] = False
        branches = analyze_candidates(*args)
        self.assertEqual(len(branches), 1)
        self.assertLess(branches[0].path_xyz_mm[-1, 0], 16)

    def test_fallback_cannot_jump_a_gap(self):
        candidates, roi, context, config = self.prepare([((4, 0, 32), (19, 0, 32), 2)])
        context.lumen[:] = False
        # Remove a full cross-section before the required 5 mm seed.
        cut = roi.image.TransformPhysicalPointToIndex((10., 0., 102.))[0]
        context.fallback_lumen[:, :, cut:cut + 2] = False
        context.fallback_radius = ndi.distance_transform_edt(context.fallback_lumen | roi.aorta,
                                                            sampling=roi.spacing_mm).astype(np.float32)
        self.assertEqual(analyze_candidates(candidates, roi, context, config), [])

    def test_failed_retry_keeps_valid_primary(self):
        args = self.prepare([((4, 0, 32), (19, 0, 32), 2)], confidence_fallback_threshold=0.99999)
        args[2].fallback_lumen[:] = False
        branches = analyze_candidates(*args)
        self.assertEqual(len(branches), 1)
        self.assertTrue(args[2].diagnostics["trace_candidates"][0]["accepted"])


if __name__ == "__main__":
    unittest.main()
