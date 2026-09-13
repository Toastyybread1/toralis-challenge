"""Track original CT interpolation support without changing the paired loader."""
import os
import nibabel as nib
import numpy as np
from scipy import ndimage as ndi
from src.utils import _prepare_readable_path, _build_orthonormal_target


def resampled_support(source_shape,source_affine,target_shape,target_affine):
    """Match linear resampling's constant-padding convention, including edges.

    A volume of ones yields one where source interpolation is valid and zero
    where constant padding is used. No HU threshold is involved.
    """
    transform=np.linalg.solve(source_affine,target_affine)
    return ndi.affine_transform(np.ones(source_shape,dtype=np.uint8),transform[:3,:3],
        transform[:3,3],output_shape=tuple(target_shape),order=1,mode='constant',cval=0,
        prefilter=False).astype(bool)


def valid_image_support(source_path,loaded_image,loading):
    if not loading.get('geometry_resampled',False):
        return np.ones(tuple(loaded_image.GetSize())[::-1],bool)
    readable,temporary=_prepare_readable_path(source_path)
    try:
        source=nib.load(readable)
        shape,affine,_=_build_orthonormal_target(source)
        # Reuse the exact target used by the original loader, avoiding boundary
        # rounding changes from its NIfTI header round-trip.
        lps=np.eye(4);lps[:3,:3]=np.array(loaded_image.GetDirection()).reshape(3,3)@np.diag(loaded_image.GetSpacing())
        lps[:3,3]=loaded_image.GetOrigin()
        ras=np.diag([-1.,-1.,1.,1.])@lps
        if tuple(shape)!=loaded_image.GetSize() or not np.allclose(affine,ras,rtol=1e-5,atol=1e-4):
            raise ValueError('Loaded grid differs from original resampling target')
        return resampled_support(source.shape,source.affine,shape,affine).transpose(2,1,0)
    finally:
        if temporary:os.remove(readable)
