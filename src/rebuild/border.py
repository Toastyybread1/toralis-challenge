"""Step 1: unchanged parent mask -> exact exposed voxel faces.

Voxel centres carry integer indices; a voxel cell extends +/-0.5 index along
its axes. Boundary faces lie between a parent cell and background (or outside
image coverage). No smoothing, filling, resampling or vessel detection occurs.
"""
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi


def validate_pair(ct,mask):
    if ct.GetDimension()!=3 or mask.GetDimension()!=3:raise ValueError('Expected 3D inputs')
    for field in ['GetSize','GetSpacing','GetOrigin','GetDirection']:
        if not np.allclose(getattr(ct,field)(),getattr(mask,field)(),atol=1e-6,rtol=0):
            raise ValueError('Input geometry mismatch: '+field)
    direction=np.array(mask.GetDirection()).reshape(3,3)
    if not np.allclose(direction.T@direction,np.eye(3),atol=1e-6):raise ValueError('Nonorthogonal geometry: no automatic resampling allowed')
    values=sitk.GetArrayFromImage(mask)
    if not np.isin(values,[0,1]).all():raise ValueError('Parent mask must be binary 0/1')
    return values.astype(bool)


def border_faces(parent):
    parent=np.asarray(parent,dtype=bool)
    if parent.ndim!=3:raise ValueError('Expected 3D parent array')
    indices=[];axes=[];signs=[];cuts=[]
    padded=np.pad(parent,1)
    for axis in range(3):
        for sign in [-1,1]:
            slices=[slice(1,n+1) for n in parent.shape]
            slices[axis]=slice(1+sign,parent.shape[axis]+1+sign)
            exposed=parent&~padded[tuple(slices)]
            q=np.argwhere(exposed)
            indices.append(q);axes.extend([axis]*len(q));signs.extend([sign]*len(q))
            cuts.extend((q[:,axis]==(0 if sign==-1 else parent.shape[axis]-1)).tolist())
    q=np.concatenate(indices).astype(np.int32)
    axis=np.asarray(axes,np.int8);sign=np.asarray(signs,np.int8)
    centre=q.astype(float)
    centre[np.arange(len(q)),axis]+=sign*.5
    inner=np.zeros_like(parent);inner[tuple(q.T)]=True
    outer=ndi.binary_dilation(parent,structure=ndi.generate_binary_structure(3,1))&~parent
    return {'parent_voxel_zyx':q,'axis_zyx':axis,'sign':sign,
            'face_centres_index_zyx':centre,'image_cut_face':np.asarray(cuts,bool)},inner,outer


def reference_border_distances(points_lps,image,faces):
    """Exact Euclidean distance to exposed rectangular voxel faces, in mm."""
    centres=faces['face_centres_index_zyx'];axis=faces['axis_zyx']
    spacing=np.array(image.GetSpacing())[::-1]
    half=np.broadcast_to(.5*spacing,centres.shape).copy()
    half[np.arange(len(axis)),axis]=0
    values=[]
    for point in points_lps:
        if not len(centres):values.append(None);continue
        q=np.array(image.TransformPhysicalPointToContinuousIndex([float(v) for v in point]))[::-1]
        delta=np.maximum(np.abs((centres-q)*spacing)-half,0)
        values.append(float(np.min(np.linalg.norm(delta,axis=1))))
    return values


def save_border(ct,mask,output):
    from pathlib import Path
    output=Path(output);output.mkdir(exist_ok=True,parents=True)
    parent=validate_pair(ct,mask);faces,inner,outer=border_faces(parent)
    for name,array in [('parent',parent),('inner_border',inner),('outer_neighbours',outer)]:
        im=sitk.GetImageFromArray(array.astype(np.uint8));im.CopyInformation(mask)
        path=output/(name+'.nii.gz');sitk.WriteImage(im,str(path))
        reopened=sitk.ReadImage(str(path))
        if not np.array_equal(sitk.GetArrayFromImage(reopened),array):raise AssertionError('Array roundtrip failed')
        validate_pair(ct,reopened)
    np.savez_compressed(output/'border_faces.npz',**faces,spacing_xyz=mask.GetSpacing(),
                        origin_lps_mm=mask.GetOrigin(),direction=mask.GetDirection())
    spacing=np.array(mask.GetSpacing())[::-1]
    area=sum(float(np.prod(np.delete(spacing,a))) for a in faces['axis_zyx'])
    return faces,{'parent_voxels':int(parent.sum()),'inner_border_voxels':int(inner.sum()),
                  'outer_neighbour_voxels':int(outer.sum()),'exposed_faces':len(faces['axis_zyx']),
                  'image_cut_faces':int(faces['image_cut_face'].sum()),'surface_area_mm2':area,
                  'geometry_and_voxel_roundtrip':'pass','parent_unchanged':True}
