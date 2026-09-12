"""Physical synthetic vessels exercise challenge semantics independently of real labels."""

import unittest

import numpy as np
import SimpleITK as sitk

from src.detection import detect_candidates
from src.output import prediction_dict, validate_prediction
from src.preprocessing import Case, make_search_shell, prepare_case
from src.tracing import analyze_candidates, point_along_path
from src.types import Config
from src.evaluation import compare_predictions


def phantom(segments=(), spacing=(0.8, 0.8, 0.8), rotation=False):
    size = np.ceil(np.array([56, 56, 64]) / spacing).astype(int)
    z, y, x = np.indices(tuple(size[::-1]), dtype=np.float32)
    coordinates = np.stack([x * spacing[0] - 28, y * spacing[1] - 28, z * spacing[2]], axis=-1)
    aorta = (coordinates[..., 0] ** 2 + coordinates[..., 1] ** 2 <= 6 ** 2)
    lumen = aorta.copy()
    for start, end, radius in segments:
        start, end = np.array(start), np.array(end)
        delta = end - start
        fraction = np.clip(np.sum((coordinates - start) * delta, axis=-1) / (delta @ delta), 0, 1)
        distance = np.linalg.norm(coordinates - start - fraction[..., None] * delta, axis=-1)
        lumen |= distance <= radius
    rng = np.random.default_rng(42)
    ct = (np.where(lumen, 300, 40) + rng.normal(0, 3, aorta.shape)).astype(np.float32)
    image = sitk.GetImageFromArray(ct)
    image.SetSpacing(spacing)
    image.SetOrigin((-28, -28, 70))
    if rotation:
        angle = np.deg2rad(27)
        image.SetDirection((np.cos(angle), -np.sin(angle), 0, np.sin(angle), np.cos(angle), 0, 0, 0, 1))
    mask = sitk.GetImageFromArray(aorta.astype(np.uint8))
    mask.CopyInformation(image)
    return Case(image, mask, ct, aorta)


def run_phantom(segments=(), **kwargs):
    case = phantom(segments, **kwargs)
    config = Config()
    roi = prepare_case(case, config)
    candidates, context = detect_candidates(roi, config)
    branches = analyze_candidates(candidates, roi, context, config)
    return branches, roi, context


class DetectionTests(unittest.TestCase):
    def test_zero_branches_and_crop_ends(self):
        branches, _, _ = run_phantom()
        self.assertEqual(len(branches), 0)
        self.assertEqual(prediction_dict("empty", branches)["daughters"], [])

    def test_one_branch(self):
        branches, _, context = run_phantom([((4, 0, 32), (19, 0, 32), 2)])
        self.assertEqual(len(branches), 1, context.diagnostics)
        branch = branches[0]
        self.assertLess(np.linalg.norm(branch.ostium_xyz_mm - [6, 0, 102]), 2)
        self.assertLess(np.linalg.norm(branch.seed_xyz_mm - [11, 0, 102]), 2)
        self.assertGreater(branch.direction_xyz[0], 0.9)
        self.assertLess(abs(branch.radius_mm - 2), 1)
        validate_prediction(prediction_dict("one", branches))

    def test_nearby_separate_openings(self):
        branches, _, context = run_phantom([((4, 0, 28), (19, 0, 28), 1.6),
                                            ((4, 0, 34), (19, 0, 34), 1.6)])
        self.assertEqual(len(branches), 2, context.diagnostics)

    def test_common_trunk_and_downstream_daughters(self):
        branches, _, context = run_phantom([((4, 0, 32), (14, 0, 32), 1.6),
                                            ((14, 0, 32), (22, 6, 32), 1.6),
                                            ((14, 0, 32), (22, -6, 32), 1.6)])
        self.assertEqual(len(branches), 1, context.diagnostics)
        self.assertLess(branches[0].path_xyz_mm[-1, 0], 16)

    def test_short_branch_rejected(self):
        branches, _, context = run_phantom([((4, 0, 32), (7.5, 0, 32), 1)])
        self.assertEqual(len(branches), 0, context.diagnostics)

    def test_openings_connected_downstream_remain_separate(self):
        branches, _, context = run_phantom([((4, 0, 28), (18, 0, 28), 1.6),
                                            ((4, 0, 35), (18, 0, 35), 1.6),
                                            ((18, 0, 28), (18, 0, 35), 1.6)])
        self.assertEqual(len(branches), 2, context.diagnostics)

    def test_no_origin_for_disconnected_vessel(self):
        branches, _, context = run_phantom([((12, 0, 28), (23, 0, 28), 1.6)])
        self.assertEqual(len(branches), 0, context.diagnostics)

    def test_crop_removes_missing_anatomy(self):
        case = phantom([((4, 0, 50), (19, 0, 50), 2)])
        image, mask = case.image[:, :, :40], case.aorta_mask[:, :, :40]
        cropped = Case(image, mask, sitk.GetArrayFromImage(image), sitk.GetArrayFromImage(mask).astype(bool))
        config = Config()
        roi = prepare_case(cropped, config)
        candidates, context = detect_candidates(roi, config)
        self.assertEqual(analyze_candidates(candidates, roi, context, config), [])

    def test_mask_terminal_caps_do_not_become_branches(self):
        case = phantom()
        case.mask_zyx[:12] = False
        case.mask_zyx[-12:] = False
        mask = sitk.GetImageFromArray(case.mask_zyx.astype(np.uint8))
        mask.CopyInformation(case.image)
        case.aorta_mask = mask
        config = Config()
        roi = prepare_case(case, config)
        candidates, context = detect_candidates(roi, config)
        self.assertEqual(analyze_candidates(candidates, roi, context, config), [], context.diagnostics)
        self.assertGreater(context.diagnostics["rejected_contacts"]["crop_end"], 0)

    def test_intensity_augmentation(self):
        for scale, offset in [(0.65, 0), (1.15, 25)]:
            case = phantom([((4, 0, 32), (19, 0, 32), 2)])
            case.ct_zyx = case.ct_zyx * scale + offset
            image = sitk.GetImageFromArray(case.ct_zyx)
            image.CopyInformation(case.image)
            case.image = image
            config = Config()
            roi = prepare_case(case, config)
            candidates, context = detect_candidates(roi, config)
            self.assertEqual(len(analyze_candidates(candidates, roi, context, config)), 1, context.diagnostics)

    def test_very_bright_attached_structure_is_not_lumen(self):
        case = phantom([((4, 0, 32), (19, 0, 32), 2)])
        external_bright = ~case.mask_zyx & (case.ct_zyx > 200)
        case.ct_zyx[external_bright] = 2500
        image = sitk.GetImageFromArray(case.ct_zyx)
        image.CopyInformation(case.image)
        case.image = image
        config = Config()
        roi = prepare_case(case, config)
        candidates, context = detect_candidates(roi, config)
        self.assertEqual(analyze_candidates(candidates, roi, context, config), [])

    def test_rotated_anisotropic_geometry(self):
        branches, _, context = run_phantom([((4, 0, 32), (19, 0, 32), 2)],
                                            spacing=(0.7, 0.9, 1.2), rotation=True)
        self.assertEqual(len(branches), 1, context.diagnostics)
        direction = [np.cos(np.deg2rad(27)), np.sin(np.deg2rad(27)), 0]
        self.assertGreater(branches[0].direction_xyz @ direction, 0.9)

    def test_physical_shell(self):
        mask = np.zeros((9, 9, 9), dtype=bool)
        mask[4, 4, 4] = True
        shell = make_search_shell(mask, (2, 1, 0.5), 1.1)
        self.assertFalse(shell[5, 4, 4])
        self.assertTrue(shell[4, 5, 4])
        self.assertTrue(shell[4, 4, 6])
        self.assertFalse(shell[4, 4, 4])

    def test_seed_follows_curved_path(self):
        path = np.array([[0, 0, 0], [3, 0, 0], [3, 4, 0]])
        np.testing.assert_allclose(point_along_path(path, 5), [3, 2, 0])

    def test_reject_invalid_output(self):
        with self.assertRaises(ValueError):
            validate_prediction({"case_id": "x", "parent": {"instance_id": "aorta"},
                                 "daughters": [{"instance_id": "b", "radius_mm": float("nan")}]})

    def test_matching_counts_duplicate_as_false_positive(self):
        def branch(identifier, x):
            return {"instance_id": identifier, "parent_instance_id": "aorta",
                    "ostium_xyz_mm": [x, 0, 0], "seed_xyz_mm": [x + 5, 0, 0],
                    "direction_xyz": [1, 0, 0], "radius_mm": 1}
        reference = {"case_id": "test", "parent": {"instance_id": "aorta"},
                     "daughters": [branch("r1", 0), branch("r2", 20)]}
        prediction = {**reference, "daughters": [branch("p1", 0), branch("p2", 0.5)]}
        result = compare_predictions(prediction, reference)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["false_negatives"], 1)


if __name__ == "__main__":
    unittest.main()
