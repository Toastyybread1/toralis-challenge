"""Synthetic anatomy for GUI exploration; never used as detection output."""

import numpy as np
import slicer
import vtk

from .contract import lps_to_ras
from .scene import AORTA_COLOR


def create_sample(scene):
    scene.clear()
    # All sample coordinates start in LPS. The volume matrix performs the same flip.
    spacing = .8
    z, y, x = np.mgrid[0:176, 0:112, 0:144].astype(np.float32)
    x = (x - 72) * spacing
    y = (y - 56) * spacing
    z = (z - 88) * spacing
    center_x = 2.5 * np.sin(z / 28.)
    center_y = 1.5 * np.sin(z / 34.)
    radius = 8.3 + 1.4 * np.exp(-((z + 13) / 22.) ** 2)
    parent = ((x - center_x) ** 2 + (y - center_y) ** 2 < radius ** 2) & (abs(z) < 61)
    branches = np.zeros_like(parent)
    definitions = [(0., -1., .15, 35., 3.2), (-1., -.22, -.14, 14., 2.8), (1., -.18, -.12, 9., 2.5), (.3, -1., -.1, -27., 2.0)]
    daughters = []
    for i, (dx, dy, dz, height, r) in enumerate(definitions):
        direction = np.array([dx, dy, dz], dtype=float)
        direction /= np.linalg.norm(direction)
        root = np.array([2.5 * np.sin(height / 28), 1.5 * np.sin(height / 34), height])
        root_radius = 8.3 + 1.4 * np.exp(-((height + 13) / 22.) ** 2)
        origin = root + direction * root_radius
        seed = origin + direction * 5.
        for distance in np.linspace(2, 35, 85):
            point = root + direction * distance
            branches |= (x - point[0]) ** 2 + (y - point[1]) ** 2 + (z - point[2]) ** 2 < r ** 2
        daughters.append({"instance_id": f"branch_{i + 1:03d}", "parent_instance_id": "aorta", "ostium_xyz_mm": origin.tolist(), "seed_xyz_mm": seed.tolist(), "radius_mm": r, "direction_xyz": direction.tolist()})
    body = (x / 54.) ** 2 + (y / 41.) ** 2 < 1
    rng = np.random.default_rng(12)
    image = np.where(body, 35. + rng.normal(0, 5, x.shape), -950).astype(np.int16)
    spine = (x / 8) ** 2 + ((y - 25) / 9) ** 2 < 1
    image[spine] = 480
    image[parent | branches] = 350
    scene.ct = scene.own(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "SYNTHETIC - CT"))
    matrix = vtk.vtkMatrix4x4()
    matrix.SetElement(0, 0, -spacing)
    matrix.SetElement(1, 1, -spacing)
    matrix.SetElement(2, 2, spacing)
    origin_ras = lps_to_ras((-72 * spacing, -56 * spacing, -88 * spacing))
    for axis in range(3):
        matrix.SetElement(axis, 3, origin_ras[axis])
    scene.ct.SetIJKToRASMatrix(matrix)
    slicer.util.updateVolumeFromArray(scene.ct, image)
    scene.ct.CreateDefaultDisplayNodes()
    scene.ct.GetDisplayNode().AutoWindowLevelOff()
    scene.ct.GetDisplayNode().SetWindowLevel(700, 220)
    for mask, name, color in [(parent, "Parent aorta", AORTA_COLOR), (branches & ~parent, "Synthetic daughter anatomy", (.48, .60, .66))]:
        label = scene.own(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", name + " mask"))
        label.SetIJKToRASMatrix(matrix)
        slicer.util.updateVolumeFromArray(label, mask.astype(np.uint8))
        label.CreateDefaultDisplayNodes()
        node = scene.segmentation_from_label(label, name, color)
        if name == "Parent aorta":
            scene.aorta = node
        else:
            scene.preview = node
            node.GetDisplayNode().SetOpacity3D(.35)
    slicer.util.setSliceViewerLayers(background=scene.ct, foreground=None, label=None)
    scene.focus_aorta()
    return {"case_id": "synthetic_demo", "parent": {"instance_id": "aorta"}, "daughters": daughters}
