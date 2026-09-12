"""One-to-one gated reference matching. Matching tolerance is a local proxy."""

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from .output import validate_prediction


def compare_predictions(prediction, reference, tolerance_mm=5.0):
    validate_prediction(prediction)
    validate_prediction(reference)
    if prediction["case_id"] != reference["case_id"]:
        raise ValueError("Prediction and reference case IDs differ")
    if not np.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("Matching tolerance must be positive")
    predicted, expected = prediction["daughters"], reference["daughters"]
    n, m = len(predicted), len(expected)
    matches = []
    if n and m:
        distances = cdist([b["ostium_xyz_mm"] for b in predicted], [b["ostium_xyz_mm"] for b in expected])
        # Unmatched dummy assignments ensure maximum cardinality before minimum distance.
        penalty = (n + m + 1) * tolerance_mm
        costs = np.full((n + m, n + m), penalty)
        costs[:n, :m] = np.where(distances <= tolerance_mm, distances, 3 * penalty)
        costs[n:, m:] = 0
        rows, columns = linear_sum_assignment(costs)
        for i, j in zip(rows, columns):
            if i < n and j < m and distances[i, j] <= tolerance_mm:
                dot = np.clip(np.dot(predicted[i]["direction_xyz"], expected[j]["direction_xyz"]), -1, 1)
                matches.append({"prediction": predicted[i]["instance_id"], "reference": expected[j]["instance_id"],
                                "ostium_error_mm": float(distances[i, j]),
                                "seed_error_mm": float(np.linalg.norm(np.array(predicted[i]["seed_xyz_mm"]) - expected[j]["seed_xyz_mm"])),
                                "radius_error_mm": abs(predicted[i]["radius_mm"] - expected[j]["radius_mm"]),
                                "direction_error_degrees": float(np.degrees(np.arccos(dot)))})
    tp = len(matches)
    return {"predicted_count": n, "reference_count": m, "matched_count": tp,
            "false_positives": n - tp, "false_negatives": m - tp,
            "precision": tp / n if n else None, "recall": tp / m if m else None,
            "f1": 2 * tp / (n + m) if n + m else None,
            "matching_tolerance_mm": tolerance_mm, "matches": matches}
