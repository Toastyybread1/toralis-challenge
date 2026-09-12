"""Competition JSON serialization, with strict numeric and schema validation."""

import json
from pathlib import Path

import numpy as np


def prediction_dict(case_id, branches):
    data = {"case_id": case_id, "parent": {"instance_id": "aorta"}, "daughters": [
        {"instance_id": f"branch_{i:03d}", "parent_instance_id": "aorta",
         "ostium_xyz_mm": branch.ostium_xyz_mm.tolist(),
         "seed_xyz_mm": branch.seed_xyz_mm.tolist(), "radius_mm": float(branch.radius_mm),
         "direction_xyz": branch.direction_xyz.tolist()}
        for i, branch in enumerate(branches, 1)
    ]}
    validate_prediction(data)
    return data


def validate_prediction(data):
    if not isinstance(data, dict) or not isinstance(data.get("case_id"), str) or not data["case_id"]:
        raise ValueError("case_id must be a nonempty string")
    if data.get("parent") != {"instance_id": "aorta"} or not isinstance(data.get("daughters"), list):
        raise ValueError("Invalid parent or daughters")
    identifiers = set()
    for branch in data["daughters"]:
        if not isinstance(branch, dict):
            raise ValueError("Every daughter must be an object")
        identifier = branch.get("instance_id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Daughter IDs must be unique nonempty strings")
        identifiers.add(identifier)
        if branch.get("parent_instance_id") != "aorta":
            raise ValueError("Every daughter must have parent aorta")
        for field in ("ostium_xyz_mm", "seed_xyz_mm", "direction_xyz"):
            value = branch.get(field)
            if (not isinstance(value, list) or len(value) != 3
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)
                    or not np.isfinite(value).all()):
                raise ValueError(f"{field} must contain three finite numbers")
        radius = branch.get("radius_mm")
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not np.isfinite(radius) or radius <= 0:
            raise ValueError("radius_mm must be finite and positive")
        direction = np.array(branch["direction_xyz"])
        displacement = np.array(branch["seed_xyz_mm"]) - branch["ostium_xyz_mm"]
        if not np.isclose(np.linalg.norm(direction), 1, atol=1e-5) or direction @ displacement <= 0:
            raise ValueError("Direction must be unit length and point into daughter")
    return data


def write_prediction_json(path, data):
    validate_prediction(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)
