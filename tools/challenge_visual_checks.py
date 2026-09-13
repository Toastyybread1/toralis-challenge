"""CT + parent border + exported origins and projected direction arrows."""
import json
from pathlib import Path
import numpy as np
import SimpleITK as sitk
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.utils import read_nifti_pair


def main():
    output=Path('outputs/predictions/visual_checks');output.mkdir(exist_ok=True)
    links=[]
    for case in (19,20,21):
        folder=Path(f'data/TORALIS CHALLENGE/subject{case:03d}')
        image,parent=read_nifti_pair(folder/f'orig{case}.nii',folder/f'mask{case}.nii')
        ct=sitk.GetArrayFromImage(image);mask=sitk.GetArrayFromImage(parent)>0
        branches=json.loads(Path(f'outputs/predictions/subject{case:03d}.json').read_text())['daughters']
        fig,axes=plt.subplots(len(branches),3,figsize=(12,4*len(branches)),squeeze=False)
        for row,p in enumerate(branches):
            q=np.array(image.TransformPhysicalPointToContinuousIndex(p['ostium_xyz_mm']))[::-1]
            end=np.array(image.TransformPhysicalPointToContinuousIndex((np.array(p['ostium_xyz_mm'])+5*np.array(p['direction_xyz'])).tolist()))[::-1]
            for axis in range(3):
                ax=axes[row,axis];others=[i for i in range(3) if i!=axis]
                index=int(np.clip(round(q[axis]),0,ct.shape[axis]-1))
                plane=np.take(ct,index,axis=axis);border=np.take(mask,index,axis=axis)
                ax.imshow(plane,cmap='gray',vmin=-100,vmax=700)
                if border.any() and not border.all():ax.contour(border,levels=[.5],colors=['cyan'],linewidths=.7)
                y,x=q[others];ey,ex=end[others]
                ax.plot(x,y,'rx',markersize=7)
                ax.annotate('',xy=(ex,ey),xytext=(x,y),arrowprops=dict(arrowstyle='->',color='magenta',lw=2))
                ax.set_xlim(max(-.5,x-16),min(plane.shape[1]-.5,x+16))
                ax.set_ylim(min(plane.shape[0]-.5,y+16),max(-.5,y-16))
                ax.set_title(f'{p["instance_id"]} | axis {axis}, slice {index}')
        fig.suptitle(f'Subject {case:03d}: exported automatic predictions\nCyan: parent mask border; red: ostium; magenta: projected 5 mm direction arrow\nArrows are 2D projections of 3D unit vectors, not in-slice vessel traces.',fontsize=12)
        fig.tight_layout(rect=(0,0,1,.94));name=f'subject{case:03d}.png'
        fig.savefig(output/name,dpi=130);plt.close(fig)
        links.append(f'<h2>Subject {case:03d}</h2><a href="../subject{case:03d}.json">Submission JSON</a><img src="{name}" style="width:100%">')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Required visual checks</title><body style="max-width:1200px;margin:30px auto;font:16px system-ui"><h1>Challenge visual checks</h1><p>Automatic predictions; anatomical review remains pending. Arrows show projected directions.</p>'+''.join(links),encoding='utf-8')


if __name__=='__main__':main()
