"""Challenge JSON contract. Pure Python; deliberately independent of Slicer."""

import copy
import json
import math
from pathlib import Path


def vector(value, field):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field} must contain three numbers.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(f"{field} must contain finite numbers.")
    return tuple(float(v) for v in value)


def validate_prediction(data, expected_case=None):
    """Validate without normalizing or changing the team's output."""
    if not isinstance(data, dict):
        raise ValueError("The prediction must be a JSON object.")
    case = data.get("case_id")
    if not isinstance(case, str) or not case.strip():
        raise ValueError("case_id must be a non-empty string.")
    if expected_case and case != expected_case:
        raise ValueError(f"Results belong to '{case}', but the loaded case is '{expected_case}'.")
    if not isinstance(data.get("parent"), dict) or data["parent"].get("instance_id") != "aorta":
        raise ValueError("parent.instance_id must be 'aorta'.")
    daughters = data.get("daughters")
    if not isinstance(daughters, list):
        raise ValueError("daughters must be a list (it can be empty).")
    ids = set()
    for i, branch in enumerate(daughters):
        prefix = f"daughters[{i}]"
        if not isinstance(branch, dict):
            raise ValueError(f"{prefix} must be an object.")
        name = branch.get("instance_id")
        if not isinstance(name, str) or not name.strip() or name == "aorta" or name in ids:
            raise ValueError(f"{prefix} needs a unique, non-empty instance_id other than 'aorta'.")
        ids.add(name)
        if branch.get("parent_instance_id") != "aorta":
            raise ValueError(f"{name}: parent_instance_id must be 'aorta'.")
        start = vector(branch.get("ostium_xyz_mm"), f"{name}.ostium_xyz_mm")
        end = vector(branch.get("seed_xyz_mm"), f"{name}.seed_xyz_mm")
        direction = vector(branch.get("direction_xyz"), f"{name}.direction_xyz")
        norm = math.sqrt(sum(v * v for v in direction))
        if abs(norm - 1.0) > 0.02:
            raise ValueError(f"{name}: direction_xyz must be a unit vector; length is {norm:.3f}.")
        if math.dist(start, end) < 1e-6:
            raise ValueError(f"{name}: the seed must differ from the ostium.")
        radius = branch.get("radius_mm")
        if isinstance(radius, bool) or not isinstance(radius, (float, int)) or not math.isfinite(radius) or radius <= 0:
            raise ValueError(f"{name}: radius_mm must be a positive finite number.")
    return copy.deepcopy(data)


def load_prediction(path, expected_case=None):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return validate_prediction(json.load(stream), expected_case)


def save_prediction(path, data):
    validated = validate_prediction(data)
    Path(path).write_text(json.dumps(validated, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def lps_to_ras(point):
    """SimpleITK physical LPS -> Slicer world RAS. Also valid for vectors.

    Export remains LPS; only the visual representation uses this conversion.
    """
    x, y, z = point
    return (-x, -y, z)


def discover_cases(root):
    """Only direct subject folders, avoiding accidental nested dataset copies."""
    cases = []
    for folder in sorted(Path(root).iterdir()):
        if not folder.is_dir():
            continue
        images = sorted(p for p in folder.glob("orig*.nii*") if p.name.endswith((".nii", ".nii.gz")))
        masks = sorted(p for p in folder.glob("mask*.nii*") if p.name.endswith((".nii", ".nii.gz")))
        if len(images) == 1 and len(masks) == 1:
            cases.append((folder.name, str(images[0]), str(masks[0])))
    return cases

