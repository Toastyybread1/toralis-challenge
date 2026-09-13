"""Display/export CT and parent using the original shared paired loader."""
import argparse
import json
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from src.utils import read_nifti_pair


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--parent',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    metadata={};ct,mask=read_nifti_pair(args.image,args.parent,metadata)
    for field in ('GetSize','GetSpacing','GetOrigin','GetDirection'):
        if not np.allclose(getattr(ct,field)(),getattr(mask,field)()):raise ValueError('CT/mask mismatch: '+field)
    a=sitk.GetArrayFromImage(ct);p=sitk.GetArrayFromImage(mask)>0
    if not p.any():raise ValueError('Empty parent mask')
    for name,im in [('ct',ct),('parent',mask)]:
        path=args.output/(name+'.nii.gz');sitk.WriteImage(im,str(path))
        reopened=sitk.ReadImage(str(path))
        if not np.array_equal(sitk.GetArrayFromImage(reopened),sitk.GetArrayFromImage(im)):
            raise AssertionError('Export changed voxel values')
        for field in ('GetSize','GetSpacing','GetOrigin','GetDirection'):
            if not np.allclose(getattr(im,field)(),getattr(reopened,field)()):raise AssertionError('Export changed geometry')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    fig,axes=plt.subplots(3,3,figsize=(12,10))
    bounds=np.array([(q.min(),q.max()) for q in np.where(p)])
    spacing=np.array(ct.GetSpacing())[::-1]
    slices=[]
    for axis in range(3):
        best=int(np.argmax(p.sum(axis=tuple(i for i in range(3) if i!=axis))))
        other=[i for i in range(3) if i!=axis]
        for col,offset in enumerate((-1,0,1)):
            k=int(np.clip(best+offset,0,a.shape[axis]-1));slices.append([axis,k])
            plane=np.take(p,k,axis=axis);ax=axes[axis,col]
            ax.imshow(np.take(a,k,axis=axis),cmap='gray',vmin=-100,vmax=650,
                      interpolation='nearest',aspect=spacing[other[0]]/spacing[other[1]])
            padded=np.pad(plane,1);segments=[]
            for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
                neighbour=padded[1+dy:1+dy+plane.shape[0],1+dx:1+dx+plane.shape[1]]
                for y,x in np.argwhere(plane&~neighbour):
                    segments.append([(x-.5,y+dy*.5),(x+.5,y+dy*.5)] if dy else
                                    [(x+dx*.5,y-.5),(x+dx*.5,y+.5)])
            ax.add_collection(LineCollection(segments,colors='cyan',linewidths=1.))
            ax.set_xlim(bounds[other[1],0]-10,bounds[other[1],1]+10)
            ax.set_ylim(bounds[other[0],1]+10,bounds[other[0],0]-10)
            ax.set_title(f'Array axis {axis}, slice {k}');ax.set_axis_off()
    fig.suptitle('CT + aorta using the original paired loader\nCyan: exact parent voxel-cell boundary; three consecutive slices per plane')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(args.output/'alignment.png',dpi=130);plt.close(fig)
    metadata.update(size_xyz=ct.GetSize(),spacing_xyz=ct.GetSpacing(),
                    parent_voxels=int(p.sum()),display_slices_axis_index=slices,
                    ct_mask_geometry_aligned=True,export_roundtrip_verified=True,
                    note='Display/loading verification only; does not validate daughter detection.')
    (args.output/'loading.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata))


if __name__=='__main__':main()
