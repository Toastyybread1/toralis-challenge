"""Rendering adapter. All MRML coordinates are RAS, all result data stays LPS."""

import math
from pathlib import Path
import tempfile
import numpy as np
import slicer
import vtk

from .contract import lps_to_ras
from .input_files import display_input_path
from .nifti_export import export_target, traced_labelmap
from .ui import fly_camera

COLORS = [(1.0, .66, .43), (.53, .74, 1.0), (.82, .65, 1.0), (1.0, .80, .42), (.43, .87, .90), (1.0, .52, .65)]
AORTA_COLOR = (.43, .86, .73)
ORIGIN_COLOR = (1., .72, .42)
SEED_COLOR = (.92, .95, 1.)


class BranchScene:
    def __init__(self):
        self.nodes = []
        self.branch_nodes = []
        self.ct = None
        self.aorta = None
        self.preview = None
        self.points = None
        self.seed_points = None
        self.arrows = []
        self.radii = []
        self.paths = []
        self.selected = None
        self.mask_voxels = 0
        self.mask_volume_ml = 0.0
        self.input_cache = None

    def own(self, node, branch=False):
        node.SetAttribute("BranchForge.Owned", "1")
        (self.branch_nodes if branch else self.nodes).append(node)
        return node

    @staticmethod
    def remove_nodes(nodes):
        for node in list(nodes):
            if node and node.GetScene():
                dependents = []
                if hasattr(node, "GetNumberOfDisplayNodes"):
                    dependents += [node.GetNthDisplayNode(i) for i in range(node.GetNumberOfDisplayNodes())]
                if hasattr(node, "GetStorageNode"):
                    dependents.append(node.GetStorageNode())
                slicer.mrmlScene.RemoveNode(node)
                for child in dependents:
                    if child and child.GetScene():
                        slicer.mrmlScene.RemoveNode(child)
        nodes.clear()

    def clear_results(self):
        self.remove_nodes(self.branch_nodes)
        self.arrows, self.radii = [], []
        self.paths = []
        self.points = self.seed_points = None
        self.selected = None

    def clear(self):
        self.clear_results()
        self.remove_nodes(self.nodes)
        self.ct = self.aorta = self.preview = None
        if self.input_cache is not None:
            self.input_cache.cleanup()
            self.input_cache = None

    def load_case(self, image_path, mask_path):
        """Build transactionally: keep the current study if the new files are invalid."""
        new = BranchScene()
        try:
            new.input_cache = tempfile.TemporaryDirectory(prefix='branchforge-display-')
            display_image = display_input_path(image_path, new.input_cache.name)
            display_mask = display_input_path(mask_path, new.input_cache.name)
            new.ct = new.own(slicer.util.loadVolume(display_image, {"name": "CT", "show": False}))
            label = new.own(slicer.util.loadLabelVolume(display_mask, {"name": "Aorta input", "show": False}))
            if new.ct.GetImageData().GetDimensions() != label.GetImageData().GetDimensions():
                raise ValueError("CT and mask dimensions differ. Choose the matching pair.")
            image_matrix, mask_matrix = vtk.vtkMatrix4x4(), vtk.vtkMatrix4x4()
            new.ct.GetIJKToRASMatrix(image_matrix)
            label.GetIJKToRASMatrix(mask_matrix)
            a = slicer.util.arrayFromVTKMatrix(image_matrix)
            b = slicer.util.arrayFromVTKMatrix(mask_matrix)
            if not np.allclose(a, b, atol=1e-4, rtol=1e-5):
                raise ValueError("CT and mask physical geometry differ (spacing, origin or orientation).")
            mask = slicer.util.arrayFromVolume(label)
            if not np.any(mask):
                raise ValueError("The supplied aorta mask is empty.")
            if not np.all((mask == 0) | (mask == 1)):
                raise ValueError("The aorta mask must be binary: 0 outside and 1 inside the aorta.")
            # Plain bookkeeping on the supplied mask; not a measurement claim about the anatomy.
            new.mask_voxels = int(np.count_nonzero(mask))
            new.mask_volume_ml = new.mask_voxels * float(np.prod(label.GetSpacing())) / 1000.0
            new.aorta = new.segmentation_from_label(label, "Parent aorta", AORTA_COLOR)
            new.ct.GetDisplayNode().AutoWindowLevelOff()
            new.ct.GetDisplayNode().SetWindowLevel(700, 220)
            self.clear()
            self.__dict__.update(new.__dict__)
            slicer.util.setSliceViewerLayers(background=self.ct, label=None, foreground=None)
            self.focus_aorta()
        except Exception:
            new.clear()
            raise

    def segmentation_from_label(self, label, name, color):
        segment = self.own(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", name))
        segment.CreateDefaultDisplayNodes()
        segment.SetReferenceImageGeometryParameterFromVolumeNode(self.ct)
        if not slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(label, segment):
            raise ValueError("Unable to create the aorta surface.")
        for i in range(segment.GetSegmentation().GetNumberOfSegments()):
            item = segment.GetSegmentation().GetNthSegment(i)
            item.SetName(name)
            item.SetColor(color)
        segment.CreateClosedSurfaceRepresentation()
        display = segment.GetDisplayNode()
        display.SetOpacity3D(.75)
        display.SetOpacity2DFill(.14)
        display.SetOpacity2DOutline(.9)
        return segment

    def export_edited_nifti(self, path, evidence, protected_paths=()):
        """Save the current parent plus real estimated paths, preserving CT geometry."""
        target = export_target(path, protected_paths)
        if self.ct is None or self.aorta is None:
            raise ValueError('Load a CT and parent-aorta mask first.')
        if self.ct.GetParentTransformNode() or self.aorta.GetParentTransformNode():
            raise ValueError('Export requires the original study coordinate frame; remove external transforms first.')
        segmentation = self.aorta.GetSegmentation()
        if segmentation.GetNumberOfSegments() != 1:
            raise ValueError('Expected one parent-aorta segment. Export extra segments using Slicer Segmentations.')
        parent = slicer.util.arrayFromSegmentBinaryLabelmap(
            self.aorta, segmentation.GetNthSegmentID(0), self.ct)
        if parent.shape != slicer.util.arrayFromVolume(self.ct).shape:
            raise ValueError('The edited segmentation extends beyond the CT grid; resolve this before export.')
        matrix = vtk.vtkMatrix4x4()
        self.ct.GetIJKToRASMatrix(matrix)
        labels = traced_labelmap(parent, slicer.util.arrayFromVTKMatrix(matrix),
                                 [item['path_xyz_mm'] for item in evidence.values()])
        node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode', 'BranchForge export')
        created = [node]
        try:
            node.SetIJKToRASMatrix(matrix)
            slicer.util.updateVolumeFromArray(node, labels)
            # Validate a temporary NIfTI round trip before touching the destination.
            with tempfile.TemporaryDirectory(prefix='.branchforge-export-', dir=str(target.parent)) as folder:
                staged = Path(folder) / target.name
                if not slicer.util.saveNode(node, str(staged)):
                    raise OSError('Unable to write the NIfTI labelmap.')
                check = slicer.util.loadLabelVolume(str(staged), {'show': False, 'name': 'Export verification'})
                created.append(check)
                restored = vtk.vtkMatrix4x4()
                check.GetIJKToRASMatrix(restored)
                if not np.allclose(slicer.util.arrayFromVTKMatrix(restored), slicer.util.arrayFromVTKMatrix(matrix), atol=1e-4, rtol=1e-6):
                    raise ValueError('NIfTI cannot preserve this CT geometry exactly enough; export cancelled.')
                if not np.array_equal(slicer.util.arrayFromVolume(check), labels):
                    raise ValueError('NIfTI voxel verification failed; export cancelled.')
                staged.replace(target)
        finally:
            self.remove_nodes(created)
        return target

    @staticmethod
    def view():
        lm = slicer.app.layoutManager()
        return lm.threeDWidget(0).threeDView() if lm.threeDViewCount else None

    def framing(self):
        """Default camera for the loaded aorta: center, position and parallel scale in RAS."""
        if not self.aorta:
            return None
        bounds = [0.0] * 6
        self.aorta.GetRASBounds(bounds)
        center = [(bounds[i * 2] + bounds[i * 2 + 1]) * .5 for i in range(3)]
        extent = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 30.)
        position = [center[0] + extent * 1.2, center[1] + extent * 2.4, center[2] + extent * .35]
        return center, position, extent * .60

    def focus_aorta(self, animated=False):
        frame = self.framing()
        if not frame:
            return
        center, position, scale = frame
        slicer.util.resetSliceViews()
        slicer.modules.markups.logic().JumpSlicesToLocation(*center, True)
        view = self.view()
        if not view:
            return
        renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
        camera = renderer.GetActiveCamera()
        camera.ParallelProjectionOn()
        camera.SetViewUp(0, 0, 1)
        if animated:
            fly_camera(view, center, position, scale)
        else:
            camera.SetFocalPoint(center)
            camera.SetPosition(position)
            camera.SetParallelScale(scale)
            renderer.ResetCameraClippingRange()
            view.scheduleRender()

    def fly_to(self, point_ras, radius_mm):
        """Glide the camera onto a branch origin, keeping the current viewing direction."""
        view = self.view()
        if not view:
            return
        camera = view.renderWindow().GetRenderers().GetFirstRenderer().GetActiveCamera()
        focal = np.array(camera.GetFocalPoint(), dtype=float)
        offset = np.array(camera.GetPosition(), dtype=float) - focal
        distance = float(np.linalg.norm(offset)) or 300.
        direction = offset / distance
        target = np.array(point_ras, dtype=float)
        fly_camera(view, target.tolist(), (target + direction * distance).tolist(), max(16., float(radius_mm) * 7.))
        slicer.modules.markups.logic().JumpSlicesToLocation(*point_ras, True)

    def model(self, polydata, name, color, opacity=1.0):
        node = self.own(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name), branch=True)
        node.SetAndObservePolyData(polydata)
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        display.SetColor(color)
        display.SetOpacity(opacity)
        display.SetBackfaceCulling(False)
        display.SetVisibility2D(True)
        display.SetSliceIntersectionThickness(2)
        display.SetAmbient(.18)
        display.SetDiffuse(.82)
        display.SetSpecular(.35)
        display.SetPower(28)
        return node

    def render_results(self, data, paths=None):
        self.clear_results()
        self.points = self.own(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Branch origins"), True)
        self.seed_points = self.own(slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Daughter seeds"), True)
        for node, color, size in [(self.points, ORIGIN_COLOR, 2.2), (self.seed_points, SEED_COLOR, 1.3)]:
            node.CreateDefaultDisplayNodes()
            node.SetLocked(True)
            display = node.GetDisplayNode()
            display.SetSelectedColor(color)
            display.SetColor(color)
            display.SetUseGlyphScale(False)
            display.SetGlyphSize(size)
            display.SetTextScale(1.5)
            display.SetPointLabelsVisibility(node == self.points)
        for i, branch in enumerate(data["daughters"]):
            start = np.array(lps_to_ras(branch["ostium_xyz_mm"]), dtype=float)
            seed = np.array(lps_to_ras(branch["seed_xyz_mm"]), dtype=float)
            direction = np.array(lps_to_ras(branch["direction_xyz"]), dtype=float)
            direction /= np.linalg.norm(direction)
            color = COLORS[i % len(COLORS)]
            evidence = (paths or {}).get(branch['instance_id'])
            if evidence:
                points = vtk.vtkPoints()
                line = vtk.vtkPolyLine()
                line.GetPointIds().SetNumberOfIds(len(evidence['path_xyz_mm']))
                for j, point in enumerate(evidence['path_xyz_mm']):
                    points.InsertNextPoint(*lps_to_ras(point))
                    line.GetPointIds().SetId(j, j)
                cells = vtk.vtkCellArray()
                cells.InsertNextCell(line)
                poly = vtk.vtkPolyData()
                poly.SetPoints(points)
                poly.SetLines(cells)
                tube = vtk.vtkTubeFilter()
                tube.SetInputData(poly)
                tube.SetRadius(.22)  # Display thickness only, not the vessel radius.
                tube.SetNumberOfSides(10)
                tube.Update()
                node = self.model(tube.GetOutput(), branch['instance_id'] + ' estimated centerline', color)
                node.SetAttribute('BranchForge.SourceCandidate', evidence['source_candidate'])
                self.paths.append(node)
            self.points.AddControlPoint(vtk.vtkVector3d(*start), branch["instance_id"])
            self.seed_points.AddControlPoint(vtk.vtkVector3d(*seed), "")
            # VTK arrows start at the origin and point along +X. Build an orthonormal basis.
            helper = np.array([0., 0., 1.]) if abs(direction[2]) < .9 else np.array([0., 1., 0.])
            side = np.cross(direction, helper)
            side /= np.linalg.norm(side)
            up = np.cross(direction, side)
            length = max(9., min(16., math.dist(start, seed) * 1.7))
            matrix = vtk.vtkMatrix4x4()
            for row in range(3):
                for col, axis in enumerate((direction, side, up)):
                    matrix.SetElement(row, col, axis[row] * length)
                matrix.SetElement(row, 3, start[row])
            arrow = vtk.vtkArrowSource()
            arrow.SetTipResolution(28)
            arrow.SetShaftResolution(24)
            arrow.SetTipRadius(.11)
            arrow.SetTipLength(.32)
            arrow.SetShaftRadius(.03)
            transform = vtk.vtkTransform()
            transform.SetMatrix(matrix)
            transformed = vtk.vtkTransformPolyDataFilter()
            transformed.SetTransform(transform)
            transformed.SetInputConnection(arrow.GetOutputPort())
            transformed.Update()
            self.arrows.append(self.model(transformed.GetOutput(), branch["instance_id"] + " direction", color))
            # A ring illustrates the radius estimate at the seed, not a segmented vessel wall.
            ring = vtk.vtkRegularPolygonSource()
            ring.SetCenter(seed)
            ring.SetNormal(direction)
            ring.SetRadius(branch["radius_mm"])
            ring.SetNumberOfSides(72)
            ring.GeneratePolygonOff()
            tube = vtk.vtkTubeFilter()
            tube.SetInputConnection(ring.GetOutputPort())
            tube.SetRadius(.16)
            tube.SetNumberOfSides(10)
            tube.Update()
            self.radii.append(self.model(tube.GetOutput(), branch["instance_id"] + " radius estimate", color, .85))

    def highlight(self, index, data):
        self.selected = index
        for i, node in enumerate(self.arrows):
            node.GetDisplayNode().SetOpacity(1. if i == index else .3)
            self.radii[i].GetDisplayNode().SetOpacity(1. if i == index else .22)
        point = lps_to_ras(data["daughters"][index]["ostium_xyz_mm"])
        slicer.modules.markups.logic().JumpSlicesToLocation(*point, True)

    def selected_displays(self):
        if self.selected is None or self.selected >= len(self.arrows):
            return []
        return [self.arrows[self.selected].GetDisplayNode(), self.radii[self.selected].GetDisplayNode()]

    def visibility(self, aorta=True, origins=True, arrows=True, radii=True, labels=True, opacity=.75):
        if self.aorta:
            display = self.aorta.GetDisplayNode()
            display.SetVisibility(aorta)
            display.SetOpacity3D(opacity)
        if self.points:
            self.points.GetDisplayNode().SetVisibility(origins)
            self.points.GetDisplayNode().SetPointLabelsVisibility(labels)
        if self.seed_points:
            self.seed_points.GetDisplayNode().SetVisibility(origins)
        for node in self.arrows:
            node.GetDisplayNode().SetVisibility(arrows)
        for node in self.paths:
            node.GetDisplayNode().SetVisibility(arrows)
        for node in self.radii:
            node.GetDisplayNode().SetVisibility(radii)
