"""Tahoces-inspired two-pass experiment; numeric rejection rules are adaptations.

No reference input, anatomical naming, branch counting, or parent modification.
"""
import json
import time
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from src.expansion import bounded_expansion, local_leakage_block
from src.rebuild.intensity_growth import grow, evaluate, plot
from src.utils import read_nifti_pair


def stages(data, mode='local_bulk', bulk_radius_mm=6.):
    if mode not in ('local_bulk', 'whole_component', 'porous_bulk', 'volume_stop'):
        raise ValueError('Unknown rejection mode')
    p=data['parent']; spacing=data['roi'].GetSpacing()
    first,labels,components=bounded_expansion(p,data['accepted'],spacing,20,data['distance'])
    volume_audit=[]
    if mode in ('porous_bulk','volume_stop'):
        from src.rebuild.spill_control import porous_bulk_block
        blocked=porous_bulk_block(labels,components,spacing,bulk_radius_mm=bulk_radius_mm)
        if mode=='volume_stop':
            from src.rebuild.spill_control import expansion_volume_block
            volume_block,volume_audit=expansion_volume_block(labels,components,data['distance'],spacing)
            blocked|=volume_block
    elif mode=='local_bulk':
        blocked=local_leakage_block(labels,components,spacing,bulk_radius_mm=bulk_radius_mm)
    else:
        ids=[c['component_id'] for c in components if c['volume_mm3']>5000 or c['volume_mm3']<2]
        blocked=np.isin(labels,ids)
    blocked &= ~p
    expanded,_,final_components=bounded_expansion(p,data['accepted']&~blocked,spacing,25,data['distance'])
    if np.any(expanded&blocked) or not expanded[p].all():
        raise AssertionError('Blocked regions reentered or parent changed')
    return {**data,'added':expanded&~p,'raw_added':data['added'],'blocked':blocked,'first_added':first&~p,
            'components':final_components,'first_components':components,'mode':mode,'volume_audit':volume_audit}


def segment(ct, parent, ratio_threshold=.5, bulk_radius_mm=6.,mode='volume_stop',valid_support=None):
    """Current experimental growth entry point; returns raw and rejected masks.

    Bulk and volume-stop filtering are provisional, not validated classifiers.
    Use mode='porous_bulk' or 'local_bulk' to reproduce previous baselines.
    """
    data=grow(ct,parent,0,ratio_threshold,radius_mm=25,valid_support=valid_support)
    return stages(data,mode=mode,bulk_radius_mm=bulk_radius_mm)


def segment_files(image_path, parent_path, ratio_threshold=.5, mode='volume_stop'):
    """Preferred file entry point: original loading plus valid-source support.

    Image-only callers must supply valid_support after any padded resampling;
    source coverage cannot be inferred reliably from CT intensities.
    """
    from src.rebuild.image_support import valid_image_support
    loading={}
    ct,parent=read_nifti_pair(image_path,parent_path,metadata=loading)
    support=valid_image_support(image_path,ct,loading)
    data=segment(ct,parent,ratio_threshold=ratio_threshold,mode=mode,valid_support=support)
    return {**data,'loading':loading}


def main():
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    root=Path('rebuild/staged_growth_results');root.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in range(19,24):
        source=Path('references/border_results')/f'case_{case}'/'inputs'
        ct,parent=read_nifti_pair(source/f'orig{case}.nii.gz',source/f'aorta{case}.nii.gz')
        row={'case':case,'experiments':{}}
        for threshold in (.5,.45,.4):
            start=time.perf_counter()
            # 27-mm crop includes the complete second pass and its boundary.
            data=grow(ct,parent,0,threshold,radius_mm=25)
            models={'raw_25mm':data,**{mode:stages(data,mode) for mode in ('whole_component','local_bulk')}}
            models['local_bulk_3mm']=stages(data,bulk_radius_mm=3.)
            seconds=time.perf_counter()-start
            # Targets are used only after all three masks have been inferred.
            ref=sitk.GetArrayFromImage(sitk.ReadImage(str(source/f'daughters{case}_draft.nii.gz')))
            annotations=json.loads((source/'annotations.json').read_text())
            out=root/f'case_{case}'/f'cutoff_{threshold}';out.mkdir(parents=True,exist_ok=True)
            result={'seconds_all_modes':seconds,'parameters':{'density_ratio':threshold,
                'first_radius_mm':20,'second_radius_mm':25,'oversized_mm3':5000,
                'tiny_mm3':2,'bulk_radii_mm':[6,3],'interior_margin_mm':0},'models':{}}
            for name,d in models.items():
                result['models'][name]=evaluate(d['added'],ref[d['box']],ct.GetSpacing(),d['distance'])
                for suffix,arr in [('growth',d['added'])]+([('blocked',d['blocked'])] if 'blocked' in d else []):
                    im=sitk.GetImageFromArray(arr.astype(np.uint8));im.CopyInformation(d['roi'])
                    sitk.WriteImage(im,str(out/f'{name}_{suffix}.nii.gz'))
            plot(case,{k:models[k] for k in ('raw_25mm','local_bulk')},annotations,ref,out)
            (out/'comparison.json').write_text(json.dumps(result,indent=2))
            row['experiments'][str(threshold)]=result
            print(case,threshold,{k:round(v['reference_coverage']*100,1) for k,v in result['models'].items()},flush=True)
        rows.append(row)
        (root/'summary.json').write_text(json.dumps(rows,indent=2))

if __name__=='__main__':main()
