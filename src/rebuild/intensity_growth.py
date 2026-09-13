"""Stage 2 experiment: inside/outside density modelling and 20-mm 3D growth.

No branch counting, tracking, graph analysis, or reference-dependent fitting.
Compare interior-only blood sampling with whole-parent sampling; keep all
other parameters fixed. Neither model is a calibrated blood probability.
"""
import json,time
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.utils import read_nifti_pair
from src.expansion import fit_intensity_model,bounded_expansion
from src.rebuild.border import validate_pair


def grow(ct_image,parent_image,margin_mm=1.,ratio_threshold=.6,radius_mm=20.,valid_support=None):
    if not np.isfinite(radius_mm) or radius_mm<=0:raise ValueError('Positive finite growth radius required')
    parent=validate_pair(ct_image,parent_image)
    if valid_support is not None:
        valid_support=np.asarray(valid_support,dtype=bool)
        if valid_support.shape!=parent.shape:raise ValueError('Support shape mismatch')
        if np.any(parent&~valid_support):raise ValueError('Parent outside valid CT support')
    if not parent.any():raise ValueError('Empty parent: no blood samples available')
    spacing=np.array(ct_image.GetSpacing())[::-1]
    bounds=[]
    for axis in range(3):
        ids=np.flatnonzero(np.any(parent,axis=tuple(a for a in range(3) if a!=axis)))
        bounds.append((ids[0],ids[-1]))
    bounds=np.array(bounds);pad=np.ceil((radius_mm+2)/spacing).astype(int)
    lo=np.maximum(0,bounds[:,0]-pad);hi=np.minimum(parent.shape,bounds[:,1]+pad+1)
    box=tuple(slice(a,b) for a,b in zip(lo,hi))
    roi=sitk.RegionOfInterest(ct_image,[int(v) for v in (hi-lo)[::-1]],[int(v) for v in lo[::-1]])
    p=parent[box];ct=sitk.GetArrayFromImage(roi).astype(np.float32)
    support=np.ones(p.shape,bool) if valid_support is None else valid_support[box]
    fitting_ct=ct if support.all() else np.where(support,ct,np.nan)
    distance=ndi.distance_transform_edt(~p,sampling=spacing)
    accepted,ratio,model=fit_intensity_model(fitting_ct,p,distance,spacing[::-1],ratio_threshold=ratio_threshold,interior_margin_mm=margin_mm)
    accepted &= support
    expanded,labels,components=bounded_expansion(p,accepted,spacing[::-1],radius_mm,distance)
    if not expanded[p].all():raise AssertionError('Parent changed')
    return {'roi':roi,'box':box,'ct':ct,'parent':p,'distance':distance,
            'accepted':accepted,'ratio':ratio,'added':expanded&~p,'model':model,'components':components,'valid_support':support}


def evaluate(added,reference_labels,spacing_xyz,distance):
    volume=float(np.prod(spacing_xyz));ref=reference_labels>0
    overlap=int(np.count_nonzero(added&ref));outside=int(np.count_nonzero(added&~ref))
    branches=[]
    for label in sorted(set(np.unique(reference_labels))-{0}):
        target=reference_labels==label
        branches.append({'label':int(label),'reference_voxels':int(target.sum()),
                         'covered_voxels':int(np.count_nonzero(added&target)),
                         'coverage_fraction':float(np.mean(added[target]))})
    # This shell includes caps and unlabelled anatomy; it is not a true-negative ROI.
    shell=(distance>0)&(distance<=10)
    return {'reference_voxels':int(ref.sum()),'covered_reference_voxels':overlap,
            'reference_coverage':overlap/int(ref.sum()) if ref.any() else None,
            'grown_volume_mm3':float(added.sum()*volume),
            'outside_reference_volume_mm3':outside*volume,
            'outside_reference_within10mm_volume_mm3':float(np.count_nonzero(added&~ref&shell)*volume),
            'outside_reference_interpretation':'disagreement, not confirmed leakage; references cover finite proximal segments',
            'branches':branches}


def plot(case,models,annotations,reference,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,(name,data) in zip(axes,models.items()):
        m=data['model'];x=m['histogram_centres_hu']
        ax.plot(x,m['inside_density'],label='inside aorta');ax.plot(x,m['outside_density'],label='outside 5-10 mm')
        ax.set_xlim(-150,850);ax.set_xlabel('CT intensity (HU)');ax.set_ylabel('Density');ax.set_title(name);ax.legend()
    fig.tight_layout();fig.savefig(out/'intensity_models.png',dpi=130);plt.close(fig)
    # Three consecutive native axial slices around each reference seed, for
    # both models. Draw only in-slice labels, never projected guide paths.
    for branch in annotations['daughters']:
        fig,axes=plt.subplots(2,3,figsize=(11,7))
        for row,(name,data) in enumerate(models.items()):
            roi=data['roi'];q=np.array(roi.TransformPhysicalPointToContinuousIndex(branch['seed_xyz_mm']))[::-1]
            ref=reference[data['box']];spacing=np.array(roi.GetSpacing())[::-1]
            for col,offset in enumerate([-1,0,1]):
                ax=axes[row,col];k=int(np.clip(round(q[0])+offset,0,data['ct'].shape[0]-1))
                ax.imshow(data['ct'][k],cmap='gray',vmin=-100,vmax=650,interpolation='nearest')
                rgba=np.zeros((*data['ct'][k].shape,4));rgba[data['added'][k]]=[0,1,0,.35]
                rgba[data['parent'][k]]=[0,.8,1,.2];ax.imshow(rgba,interpolation='nearest')
                target=ref[k]==branch['label_value']
                if target.any():ax.contour(target,levels=[.5],colors='orange',linewidths=1.3)
                ax.set_xlim(q[2]-9/spacing[2],q[2]+9/spacing[2]);ax.set_ylim(q[1]+9/spacing[1],q[1]-9/spacing[1])
                ax.set_aspect(spacing[1]/spacing[2]);ax.set_title(f'{name} | ROI z={k}')
        fig.suptitle(f"Case {case}, {branch['instance_id']}: three consecutive slices\nCyan parent, green growth, orange reference daughter contour")
        fig.tight_layout(rect=[0,0,1,.91]);fig.savefig(out/(branch['instance_id']+'.png'),dpi=130);plt.close(fig)


def main():
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    output=Path('rebuild/intensity_growth_results');output.mkdir(exist_ok=True,parents=True);rows=[]
    for case in range(19,24):
        source=Path('references/border_results')/f'case_{case}'/'inputs';out=output/f'case_{case}';out.mkdir(exist_ok=True)
        ct,parent=read_nifti_pair(source/f'orig{case}.nii.gz',source/f'aorta{case}.nii.gz')
        models={};row={'case':case,'models':{}}
        for name,margin in [('interior_3mm',3.),('whole_parent',0.)]:
            start=time.perf_counter();data=grow(ct,parent,margin);seconds=time.perf_counter()-start;models[name]=data
            for suffix,arr in [('growth',data['added']),('blood_score',data['ratio'])]:
                im=sitk.GetImageFromArray(arr.astype(np.uint8 if suffix=='growth' else np.float32));im.CopyInformation(data['roi'])
                sitk.WriteImage(im,str(out/(name+'_'+suffix+'.nii.gz')))
            row['models'][name]={'growth_seconds':seconds,'inside_median_hu':data['model']['inside_median_hu'],
                'parameters':{'interior_margin_mm':margin,'density_ratio':.6,'first_growth_radius_mm':20},
                'components':data['components']}
        # Organizer targets loaded only after both inference runs finish.
        reference=sitk.GetArrayFromImage(sitk.ReadImage(str(source/f'daughters{case}_draft.nii.gz')))
        annotations=json.loads((source/'annotations.json').read_text())
        for name,data in models.items():
            row['models'][name]['evaluation']=evaluate(data['added'],reference[data['box']],ct.GetSpacing(),data['distance'])
        plot(case,models,annotations,reference,out)
        (out/'comparison.json').write_text(json.dumps(row,indent=2));rows.append(row)
        print(json.dumps({'case':case,'models':{n:r['evaluation'] for n,r in row['models'].items()}}),flush=True)
    (output/'summary.json').write_text(json.dumps(rows,indent=2))

if __name__=='__main__':main()
