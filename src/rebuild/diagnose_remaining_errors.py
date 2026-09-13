"""Reference-assisted failure diagnosis; never an inference or scoring change.

Frozen predictions are matched first. Labels/guides then localize failures and
produce CT review panels. No decisions or edits are written to organizer files.
"""
import json
import argparse
from pathlib import Path
import zipfile
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from src.evaluate_predictions import compare
from src.daughter_geometry import measure_branch,path_lumen_supported,sample,section
from src.rebuild.staged_growth import segment_files
from src.rebuild.border import border_faces,reference_border_distances


def xyz_index(image,p):
    return list(image.TransformPhysicalPointToContinuousIndex([float(v) for v in p]))


def nearest_records(records,origin,n=3):
    records=[r for r in records if r.get('ostium_xyz_mm') is not None]
    records=sorted(records,key=lambda r:np.linalg.norm(np.array(r['ostium_xyz_mm'])-origin))[:n]
    keys=('instance_id','candidate_id','status','selection_reason','verification_decision','tracking_status',
          'origin_diameter_mm','neural_distal_score','automatic_checks','local_evidence','path_length_mm')
    return [{**{k:r[k] for k in keys if k in r},'origin_error_mm':float(np.linalg.norm(np.array(r['ostium_xyz_mm'])-origin))}
            for r in records]


def opening_probe(data,q,direction):
    """Disambiguate the tracker's generic 'unbounded_origin_section' reason."""
    spacing=np.array(data['roi'].GetSpacing())[::-1];point=q*spacing
    tangent=direction/np.linalg.norm(direction);previous=point.copy();inside=None
    for distance in np.arange(.25,6.01,.25):
        probe=point-tangent*distance
        if sample(data['parent'],probe,spacing,0)>=.5:
            inside=probe;outside=previous;break
        previous=probe
    if inside is None:return {'status':'no_parent_crossing'}
    for _ in range(12):
        midpoint=(inside+outside)/2
        if sample(data['parent'],midpoint,spacing,0)>=.5:inside=midpoint
        else:outside=midpoint
    origin=(inside+outside)/2;probe=origin+.5*tangent
    parts=section(data['added'],probe,tangent,spacing)
    centres=[p for p in parts if p['contains_centre']]
    return {'status':'probe_measured','probe_in_parent':sample(data['parent'],probe,spacing,0)>=.5,
            'probe_in_growth':sample(data['added'],probe,spacing,0)>=.5,
            'number_of_section_components':len(parts),'centre_component_count':len(centres),
            'centre_component_clipped':any(p['edge'] for p in centres),
            'centre_component_area_mm2':[p['area'] for p in centres]}


def review_panel(ct,parent,growth,reference,origin,path,title,output,slice_label='native slice'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    array=sitk.GetArrayFromImage(ct);centre=np.array(xyz_index(ct,origin))[::-1]
    path=np.array([xyz_index(ct,p) for p in path])[:,::-1] if len(path) else np.empty((0,3))
    fig,axes=plt.subplots(3,5,figsize=(16,10))
    for axis in range(3):
        plane_axes=[a for a in range(3) if a!=axis]
        for col,offset in enumerate((-2,-1,0,1,2)):
            k=int(np.clip(round(centre[axis])+offset,0,array.shape[axis]-1));ax=axes[axis,col]
            ct_slice=np.take(array,k,axis=axis);mask=np.take(parent,k,axis=axis)
            ax.imshow(ct_slice,cmap='gray',vmin=-100,vmax=700,interpolation='nearest')
            lines=[];padded=np.pad(mask,1)
            for da,db in ((-1,0),(1,0),(0,-1),(0,1)):
                near=padded[1+da:1+da+mask.shape[0],1+db:1+db+mask.shape[1]]
                for r,c in np.argwhere(mask&~near):
                    lines.append([(c-.5,r+da*.5),(c+.5,r+da*.5)] if da else [(c+db*.5,r-.5),(c+db*.5,r+.5)])
            ax.add_collection(LineCollection(lines,colors='cyan',linewidths=.7))
            if reference is not None:
                ref=np.take(reference,k,axis=axis)>0
                if ref.any():ax.contour(ref,levels=[.5],colors='yellow',linewidths=.6)
            visible=path[abs(path[:,axis]-k)<=.5]
            if len(visible):ax.scatter(visible[:,plane_axes[1]],visible[:,plane_axes[0]],s=7,c='magenta')
            if abs(centre[axis]-k)<=.5:ax.plot(centre[plane_axes[1]],centre[plane_axes[0]],'rx',markersize=6)
            ax.set_xlim(centre[plane_axes[1]]-12,centre[plane_axes[1]]+12)
            ax.set_ylim(centre[plane_axes[0]]+12,centre[plane_axes[0]]-12)
            ax.set_title(f'axis {axis}, {slice_label} {k}',fontsize=8)
    fig.suptitle(title+'\nCyan: exact parent cell border; yellow: draft-label outline; red: origin; magenta: in-slice guide/path samples. CT window −100 to 700 HU.',fontsize=10)
    fig.tight_layout(rect=(0,0,1,.95));fig.savefig(output,dpi=105);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('rebuild/verified_openings_final'))
    parser.add_argument('--output',type=Path,default=Path('rebuild/remaining_error_audit'))
    args=parser.parse_args()
    root=args.output;root.mkdir(parents=True,exist_ok=True)
    archive=zipfile.ZipFile(r'C:\Users\nikag\Downloads\EVAL_SET-20260913T030442Z-1-001.zip')
    notes={str(c):archive.read(f'EVAL_SET/case_{c}/review_notes.md').decode() for c in range(19,24)}
    (root/'organizer_notes.json').write_text(json.dumps(notes,indent=2))
    misses=[];extras=[]
    for case in range(19,24):
        source=Path('references/border_results')/f'case_{case}'/'inputs'
        ct=sitk.ReadImage(str(source/f'orig{case}.nii.gz'));parent=sitk.ReadImage(str(source/f'aorta{case}.nii.gz'))
        full_parent=sitk.GetArrayFromImage(parent)>0
        ref_image=sitk.ReadImage(str(source/f'daughters{case}_draft.nii.gz'));full_ref=sitk.GetArrayFromImage(ref_image)
        reference=json.loads((source/'annotations.json').read_text())
        frozen=json.loads((args.input/f'subject{case:03d}'/'predictions.json').read_text())
        data=segment_files(source/f'orig{case}.nii.gz',source/f'aorta{case}.nii.gz')
        image=data['roi'];spacing=np.array(image.GetSpacing())[::-1]
        records=frozen['seed_candidates']+frozen['rejected_candidates']
        chosen=[g['representative'] for g in frozen['review_groups']]
        matched=compare({'daughters':chosen},reference,3.)
        used_ref={m['reference_index'] for m in matched['matches']};used_pred={m['prediction_index'] for m in matched['matches']}
        contact=data['added']&ndi.binary_dilation(data['parent'],structure=ndi.generate_binary_structure(3,1))
        contact_coords=np.argwhere(contact)
        faces,_,_=border_faces(data['parent'])
        face_parent=faces['parent_voxel_zyx'];axis=faces['axis_zyx'];sign=faces['sign']
        outside=face_parent.copy();outside[np.arange(len(outside)),axis]+=sign
        valid=np.all((outside>=0)&(outside<np.array(contact.shape)),axis=1)
        touched=np.zeros(len(outside),bool);touched[valid]=data['added'][tuple(outside[valid].T)]
        contact_faces={k:v[touched] for k,v in faces.items()}
        ref=full_ref[data['box']]
        full_growth=np.zeros(full_parent.shape,bool);full_growth[data['box']]=data['added']
        for j,branch in enumerate(reference['daughters']):
            if j in used_ref:continue
            origin=branch['ostium_xyz_mm'];seed=branch['seed_xyz_mm'];label=branch['label_value']
            mask=ref==label;native=np.array(xyz_index(image,origin))[::-1]
            distances=np.linalg.norm((contact_coords-native)*spacing,axis=1)
            q=contact_coords[np.argmin(distances)]
            direction=(np.array(xyz_index(image,seed))[::-1]-native)*spacing
            # Oracle initialization is diagnostic only; no resulting prediction
            # enters the benchmark or production candidate list.
            measured,reason=measure_branch(data['parent'],data['added'],q,direction,spacing,
                                          min_diameter_mm=0,target_length_mm=5,strict_geometry=True)
            guide=branch.get('centerline_xyz_mm',[])
            local_path=np.array([xyz_index(image,p) for p in guide])[:,::-1]*spacing if len(guide) else np.empty((0,3))
            seed_q=np.floor(np.array(xyz_index(image,seed))[::-1]+.5).astype(int)
            nearest=nearest_records(records,origin)
            row={'case':case,'branch':branch['instance_id'],'native_origin_xyz':xyz_index(ct,origin),
                 'reference_confidence':branch['confidence'],'reference_notes':branch['notes'],
                 'reference_voxels':int(mask.sum()),'growth_coverage':float(data['added'][mask].mean()),
                 'accepted_intensity_coverage':float(data['accepted'][mask].mean()),
                 'blocked_reference_voxels':int(np.count_nonzero(mask&data['blocked'])),
                 'seed_in_growth':bool(data['added'][tuple(seed_q)]),
                 'distance_to_grown_contact_face_mm':reference_border_distances([origin],image,contact_faces)[0],
                 'nearest_contact_voxel_mm':float(distances.min()),
                 'guide_supported_by_growth':bool(len(local_path)>1 and path_lumen_supported(local_path,spacing,data['added'],data['parent'])),
                 'nearest_proposals':nearest,'nearest_graph_attempts':nearest_records(frozen['graph_candidate_records'],origin),
                 'reference_initialized_opening_probe':opening_probe(data,q,direction),
                 'reference_initialized_trace':{'diagnostic_only':True,'status':reason or 'seed_supported',
                                                'path_length_mm':measured['path_length_mm'] if measured else None}}
            misses.append(row)
            review_panel(ct,full_parent,full_growth,full_ref==label,origin,guide,
                         f'Case {case} {branch["instance_id"]}: missed draft reference (not expert-approved)',root/f'miss_{case}_{branch["instance_id"]}.png')
        if case==21:
            for i,pred in enumerate(chosen):
                if i in used_pred:continue
                origin=pred['ostium_xyz_mm']
                nearest_ref=min(reference['daughters'],key=lambda r:np.linalg.norm(np.array(r['ostium_xyz_mm'])-origin))
                row={'case':case,'candidate':pred['instance_id'],'native_origin_xyz':xyz_index(ct,origin),
                     'native_seed_xyz':xyz_index(ct,pred['seed_xyz_mm']),
                     'nearest_reference':nearest_ref['instance_id'],
                     'nearest_reference_origin_mm':float(np.linalg.norm(np.array(nearest_ref['ostium_xyz_mm'])-origin)),
                     'nearest_reference_seed_mm':float(np.linalg.norm(np.array(nearest_ref['seed_xyz_mm'])-pred['seed_xyz_mm'])),
                     'origin_diameter_proxy_mm':pred['origin_diameter_mm'],'diameter_eligibility':pred['diameter_eligibility'],
                     'path_length_mm':pred['path_length_mm'],'local_evidence':pred['local_evidence'],
                     'alternatives':frozen['review_groups'][i]['alternative_candidate_ids'],
                     'review_status':'unresolved; no expert sign-off or scoring exclusion'}
                extras.append(row)
                review_panel(ct,full_parent,full_growth,full_ref,origin,pred['path_xyz_mm'],
                             f'Case 21 {pred["instance_id"]}: unmatched group; inspect origin and nearby lumen',root/f'extra_21_{pred["instance_id"]}.png')
    (root/'diagnosis.json').write_text(json.dumps({'misses':misses,'extras':extras},indent=2,allow_nan=False))
    for r in misses:
        print(json.dumps({'case':r['case'],'branch':r['branch'],'growth_coverage':r['growth_coverage'],
                          'contact_distance':r['distance_to_grown_contact_face_mm'],
                          'nearest_proposal_mm':r['nearest_proposals'][0]['origin_error_mm'],
                          'nearest_graph':r['nearest_graph_attempts'][0].get('status'),
                          'initialized_trace':r['reference_initialized_trace']}),flush=True)
    print(json.dumps(extras,indent=2))


if __name__=='__main__':main()
