"""Export only BranchForge-owned visible geometry. No CT voxels or study identifiers.

MRML world RAS millimetres -> glTF right-handed Y-up metres: (x, z, -y)/1000.
Translation is anchored to the parent aorta, independent of visibility/selection.
"""
import json
import struct
import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy


def visible(node):
    display = node.GetDisplayNode() if node and node.GetScene() else None
    return bool(display and display.GetVisibility() and display.GetVisibility3D())


def signature(scene):
    state = [scene.selected]
    for node in scene.nodes + scene.branch_nodes:
        if not node or not node.GetScene() or not node.IsA('vtkMRMLDisplayableNode') or node.IsA('vtkMRMLVolumeNode'):
            continue
        display = node.GetDisplayNode()
        if not display:
            continue
        transform = node.GetParentTransformNode()
        state.extend((node.GetID(), node.GetMTime() if node.IsA('vtkMRMLMarkupsNode') else 0, transform.GetMTime() if transform else 0,
                      bool(display.GetVisibility()), bool(display.GetVisibility3D())))
        if node.IsA('vtkMRMLSegmentationNode'):
            state.append(node.GetSegmentation().GetMTime())
            state.append(round(display.GetOpacity3D(), 3))
            for i in range(node.GetSegmentation().GetNumberOfSegments()):
                sid = node.GetSegmentation().GetNthSegmentID(i)
                state.extend((display.GetSegmentVisibility(sid), display.GetSegmentVisibility3D(sid),
                              display.GetSegmentOpacity3D(sid), node.GetSegmentation().GetSegment(sid).GetColor()))
        elif node.IsA('vtkMRMLModelNode'):
            state.extend((node.GetPolyData().GetMTime(), display.GetColor()))
            # Selected-marker pulse is cosmetic. Do not upload a new mesh every animation frame.
        elif node.IsA('vtkMRMLMarkupsNode'):
            state.extend((display.GetPointLabelsVisibility(), display.GetGlyphSize()))
    return repr(state)


def world_poly(poly, node):
    transform = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(node.GetParentTransformNode(), None, transform)
    filt = vtk.vtkTransformPolyDataFilter()
    filt.SetInputData(poly)
    filt.SetTransform(transform)
    filt.Update()
    return filt.GetOutput()


def build_glb(parts, anchor):
    """parts = (polydata in world RAS mm, colour, opacity). Returns self-contained GLB."""
    binary = bytearray()
    document = {'asset': {'version': '2.0', 'generator': 'BranchForge'}, 'scene': 0,
                'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [], 'materials': [],
                'bufferViews': [], 'accessors': []}
    all_bounds = []

    def accessor(array, kind, component, target, bounds=False):
        raw = array.tobytes()
        while len(binary) % 4:
            binary.append(0)
        view = len(document['bufferViews'])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(raw), 'target': target})
        binary.extend(raw)
        item = {'bufferView': view, 'componentType': component, 'count': len(array), 'type': kind}
        if bounds:
            item.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        document['accessors'].append(item)
        return len(document['accessors']) - 1

    for poly, color, opacity in parts:
        triangles = vtk.vtkTriangleFilter()
        triangles.SetInputData(poly)
        triangles.PassLinesOff()
        triangles.PassVertsOff()
        triangles.Update()
        mesh = triangles.GetOutput()
        if not mesh.GetNumberOfPolys():
            continue
        if mesh.GetNumberOfPolys() > 20000:
            reduce = vtk.vtkDecimatePro()
            reduce.SetInputData(mesh)
            reduce.SetTargetReduction(1 - 20000 / mesh.GetNumberOfPolys())
            reduce.PreserveTopologyOn()
            reduce.Update()
            mesh = reduce.GetOutput()
        points = vtk_to_numpy(mesh.GetPoints().GetData()).astype(np.float64) - np.asarray(anchor)
        points = (points[:, [0, 2, 1]] * [1, 1, -1] * .001).astype('<f4')
        if not np.isfinite(points).all():
            raise ValueError('Scene contains non-finite geometry.')
        all_bounds.extend((points.min(axis=0), points.max(axis=0)))
        normals_filter = vtk.vtkPolyDataNormals()
        normals_filter.SetInputData(mesh)
        normals_filter.SplittingOff()
        normals_filter.ConsistencyOn()
        normals_filter.Update()
        mesh = normals_filter.GetOutput()
        normals = vtk_to_numpy(mesh.GetPointData().GetNormals())[:, [0, 2, 1]]
        normals = (normals * [1, 1, -1]).astype('<f4')
        indices = vtk_to_numpy(mesh.GetPolys().GetData()).reshape(-1, 4)[:, 1:].flatten().astype('<u4')
        position = accessor(points, 'VEC3', 5126, 34962, True)
        normal = accessor(normals, 'VEC3', 5126, 34962)
        index = accessor(indices, 'SCALAR', 5125, 34963)
        number = len(document['meshes'])
        # glTF factors are linear, while Slicer UI colours are sRGB.
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in color]
        document['materials'].append({'pbrMetallicRoughness': {'baseColorFactor': linear + [float(opacity)],
                    'metallicFactor': 0, 'roughnessFactor': .48}, 'doubleSided': True,
                    'alphaMode': 'BLEND' if opacity < .999 else 'OPAQUE'})
        document['meshes'].append({'primitives': [{'attributes': {'POSITION': position, 'NORMAL': normal},
                                                  'indices': index, 'material': number}]})
        document['nodes'].append({'mesh': number, 'name': f'Geometry {number + 1}'})
        document['scenes'][0]['nodes'].append(number)
    if binary:
        document['buffers'] = [{'byteLength': len(binary)}]
    else:
        for key in ('meshes', 'materials', 'bufferViews', 'accessors'):
            document.pop(key)
    raw_json = json.dumps(document, separators=(',', ':'), allow_nan=False).encode()
    raw_json += b' ' * (-len(raw_json) % 4)
    binary += b'\0' * (-len(binary) % 4)
    chunks = struct.pack('<II', len(raw_json), 0x4E4F534A) + raw_json
    if binary:
        chunks += struct.pack('<II', len(binary), 0x004E4942) + binary
    glb = struct.pack('<III', 0x46546C67, 2, 12 + len(chunks)) + chunks
    if len(glb) > 2_000_000:
        raise ValueError('Visible scene is larger than the 2 MB sharing limit. Hide some markers or simplify the surface.')
    dimensions = ((np.max(all_bounds, axis=0) - np.min(all_bounds, axis=0)) * 1000).tolist() if all_bounds else [0, 0, 0]
    return glb, dimensions, len(document['nodes'])


def export_scene(scene, prediction=None, synthetic=False):
    if not scene.aorta or not scene.aorta.GetScene():
        raise ValueError('Load a study before sharing.')
    bounds = [0.] * 6
    scene.aorta.GetRASBounds(bounds)
    anchor = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, bounds[4]]
    parts = []
    for node in (scene.aorta, scene.preview):
        if not visible(node):
            continue
        node.CreateClosedSurfaceRepresentation()
        display = node.GetDisplayNode()
        segmentation = node.GetSegmentation()
        for i in range(segmentation.GetNumberOfSegments()):
            sid = segmentation.GetNthSegmentID(i)
            if not display.GetSegmentVisibility(sid) or not display.GetSegmentVisibility3D(sid):
                continue
            poly = vtk.vtkPolyData()
            node.GetClosedSurfaceRepresentation(sid, poly)
            parts.append((world_poly(poly, node), segmentation.GetSegment(sid).GetColor(),
                          display.GetOpacity3D() * display.GetSegmentOpacity3D(sid)))
    for collection in (scene.arrows, scene.radii):
        for i, node in enumerate(collection):
            if visible(node):
                opacity = (1. if i == scene.selected else .3) if scene.selected is not None else node.GetDisplayNode().GetOpacity()
                parts.append((world_poly(node.GetPolyData(), node), node.GetDisplayNode().GetColor(), opacity))
    for node in (scene.points, scene.seed_points):
        if not visible(node):
            continue
        display = node.GetDisplayNode()
        for i in range(node.GetNumberOfControlPoints()):
            if not node.GetNthControlPointVisibility(i):
                continue
            position = [0., 0., 0.]
            node.GetNthControlPointPositionWorld(i, position)
            sphere = vtk.vtkSphereSource()
            sphere.SetCenter(position)
            sphere.SetRadius(display.GetGlyphSize() / 2)
            sphere.SetThetaResolution(12)
            sphere.SetPhiResolution(8)
            sphere.Update()
            parts.append((sphere.GetOutput(), display.GetSelectedColor(), 1.))
            if node == scene.points and display.GetPointLabelsVisibility():
                text = vtk.vtkVectorText()
                text.SetText(f'B{i + 1}')
                pose = vtk.vtkTransform()
                pose.Translate(position[0] + 2, position[1], position[2] + 2)
                pose.RotateX(90)
                pose.Scale(2, 2, 2)
                transformed = vtk.vtkTransformPolyDataFilter()
                transformed.SetInputConnection(text.GetOutputPort())
                transformed.SetTransform(pose)
                transformed.Update()
                parts.append((transformed.GetOutput(), (1., .8, .5), 1.))
    glb, dimensions, count = build_glb(parts, anchor)
    return glb, {'dimensionsMm': dimensions, 'meshCount': count,
                 'branchCount': len(prediction['daughters']) if prediction else 0,
                 'synthetic': synthetic, 'labelsVisible': bool(visible(scene.points) and scene.points.GetDisplayNode().GetPointLabelsVisibility())}
