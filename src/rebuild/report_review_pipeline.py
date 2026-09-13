"""Post-inference draft comparison, review panels and an honest results report."""
import argparse
import html
import json
from pathlib import Path
import numpy as np
import SimpleITK as sitk


def pooled(rows,key):
    values=[r[key] for r in rows if key in r]
    counts={k:sum(v[k] for v in values) for k in ('tp','fp','fn')}
    tp,fp,fn=(counts[k] for k in ('tp','fp','fn'))
    return {**counts,'precision':tp/(tp+fp) if tp+fp else None,
            'recall':tp/(tp+fn) if tp+fn else None,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def panels(case,result,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import ListedColormap
    from src.evaluate_predictions import compare
    source=Path('references/border_results')/f'case_{case}'/'inputs'
    ct=sitk.ReadImage(str(source/f'orig{case}.nii.gz'));a=sitk.GetArrayFromImage(ct)
    p=sitk.GetArrayFromImage(sitk.ReadImage(str(source/f'aorta{case}.nii.gz')))>0
    refmask=sitk.GetArrayFromImage(sitk.ReadImage(str(source/f'daughters{case}_draft.nii.gz')))
    reference=json.loads((source/'annotations.json').read_text())
    chosen=[g['representative'] for g in result['review_groups']]
    comparison=compare({'daughters':chosen},reference,3.)
    matches={m['reference_index']:m['prediction_index'] for m in comparison['matches']}
    failure_rows=[]
    for j,branch in enumerate(reference['daughters']):
        origin=np.array(ct.TransformPhysicalPointToContinuousIndex(branch['ostium_xyz_mm']))[::-1]
        seed=np.array(ct.TransformPhysicalPointToContinuousIndex(branch['seed_xyz_mm']))[::-1]
        matched=chosen[matches[j]] if j in matches else None
        candidates=result['seed_candidates']+result['rejected_candidates']
        nearest=min(candidates,key=lambda q:np.linalg.norm(np.array(q['ostium_xyz_mm'])-branch['ostium_xyz_mm'])) if candidates else None
        failure_rows.append({'branch':branch['instance_id'],'matched_group':matched['instance_id'] if matched else None,
            'nearest_candidate':nearest['instance_id'] if nearest else None,
            'nearest_origin_error_mm':float(np.linalg.norm(np.array(nearest['ostium_xyz_mm'])-branch['ostium_xyz_mm'])) if nearest else None,
            'nearest_selection_reason':nearest['selection_reason'] if nearest else 'no_supported_path',
            'nearest_review_flags':nearest['review_flags'] if nearest else []})
        path=np.array([ct.TransformPhysicalPointToContinuousIndex(q) for q in matched['path_xyz_mm']])[:,::-1] if matched else np.empty((0,3))
        fig,axes=plt.subplots(3,3,figsize=(10,10))
        for axis in range(3):
            axes2=[k for k in range(3) if k!=axis]
            for col,offset in enumerate((-1,0,1)):
                k=int(np.clip(round(origin[axis])+offset,0,a.shape[axis]-1));ax=axes[axis,col]
                image=np.take(a,k,axis=axis);parent=np.take(p,k,axis=axis);ref=np.take(refmask,k,axis=axis)
                ax.imshow(image,cmap='gray',vmin=-100,vmax=650,interpolation='nearest')
                # Exact pixel-cell edges, not interpolated marching-squares
                # diagonals: the cyan border uses the supplied 0/1 convention.
                edge_segments=[]
                padded=np.pad(parent,1)
                for da,db in ((-1,0),(1,0),(0,-1),(0,1)):
                    neighbour=padded[1+da:1+da+parent.shape[0],1+db:1+db+parent.shape[1]]
                    rr,cc=np.nonzero(parent&~neighbour)
                    for row,col_index in zip(rr,cc):
                        if da:edge_segments.append([(col_index-.5,row+da*.5),(col_index+.5,row+da*.5)])
                        else:edge_segments.append([(col_index+db*.5,row-.5),(col_index+db*.5,row+.5)])
                ax.add_collection(LineCollection(edge_segments,colors='cyan',linewidths=.8))
                ax.imshow(np.ma.masked_where(ref==0,ref>0),cmap=ListedColormap(['darkorange']),alpha=.35,vmin=0,vmax=1,interpolation='nearest')
                for point,marker in ((origin,'o'),(seed,'*')):
                    if abs(point[axis]-k)<=.5:ax.plot(point[axes2[1]],point[axes2[0]],marker,color='yellow',markersize=6)
                visible=path[np.abs(path[:,axis]-k)<=.5]
                if len(visible):ax.scatter(visible[:,axes2[1]],visible[:,axes2[0]],s=9,c='magenta')
                for which, setter in ((1,ax.set_xlim),(0,ax.set_ylim)):
                    centre=origin[axes2[which]];setter(centre-10,centre+10) if which else setter(centre+10,centre-10)
                ax.set_title(f'axis {axis}, slice {k}',fontsize=9)
        name=f'case{case}_{branch["instance_id"]}.png'
        fig.suptitle(f'Case {case}: {branch["instance_id"]} — '+('matched review group' if matched else 'MISSED review group')+
                     '\nCyan: parent; orange: draft labels; yellow: reference landmarks; magenta: in-slice predicted path',fontsize=10)
        fig.tight_layout(rect=(0,0,1,.94));fig.savefig(out/name,dpi=110);plt.close(fig)
    (out/f'case{case}_discrepancies.json').write_text(json.dumps(failure_rows,indent=2))
    return failure_rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,default=Path('rebuild/document_pipeline_final'))
    args=parser.parse_args();root=args.input;rows=json.loads((root/'summary.json').read_text())
    successful=[r for r in rows if 'error' not in r]
    evalrows=[r for r in successful if 'draft_reference_agreement' in r]
    for r in evalrows:r['raw_agreement_3mm']=r['draft_reference_agreement']['3.0']
    totals={name:pooled(evalrows,key) for name,key in [('all_retained_candidates','raw_agreement_3mm'),
            ('review_group_representatives','review_group_agreement_3mm'),('length_complete_candidates','complete_path_agreement_3mm')]}
    errors=[m['seed_error_mm'] for r in evalrows for m in r['review_group_agreement_3mm']['matches'] if 'seed_error_mm' in m]
    totals['matched_group_seed_errors_mm']={'median':float(np.median(errors)) if errors else None,'maximum':max(errors) if errors else None}
    totals['runtime']={'cases_completed':len(successful),'cases_attempted':len(rows),
                       'under_60_seconds':sum(r['within_60_seconds'] for r in rows),
                       'median_seconds':float(np.median([r['whole_process_seconds'] for r in rows])),
                       'maximum_seconds':max(r['whole_process_seconds'] for r in rows),
                       'maximum_peak_working_set_mb':max(r['peak_working_set_mb'] for r in successful)}
    (root/'aggregate_metrics.json').write_text(json.dumps(totals,indent=2))
    previews=root/'review_panels';previews.mkdir(exist_ok=True)
    failures=[]
    for r in evalrows:
        result=json.loads((root/f'subject{r["case"]:03d}'/'predictions.json').read_text())
        failures.extend([{'case':r['case'],**v} for v in panels(r['case'],result,previews)])
    (root/'reference_discrepancies.json').write_text(json.dumps(failures,indent=2))
    table=['| Case | Raw candidates | Review groups | Group matches | Unmatched groups | Missed drafts | CPU seconds |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for r in successful:
        e=r.get('review_group_agreement_3mm',{})
        table.append(f"| {r['case']} | {r['seed_candidates']} | {r['review_groups']} | {e.get('tp','—')} | {e.get('fp','—')} | {e.get('fn','—')} | {r['whole_process_seconds']:.2f} |")
    metrics=totals['review_group_representatives'];runtime=totals['runtime']
    text=f'''# CPU document-guided daughter pipeline: measured results

This is an implemented proposal-and-review system, not an expert-approved segmentation.
The supplied review record explicitly leaves all 19 reference branches pending.
No new expert decisions, corrected ground truth or confirmed all-vessel count were fabricated.

## Measured development agreement

Review-group representatives: {metrics['tp']} matched, {metrics['fp']} unmatched,
{metrics['fn']} missed draft branches at a 3 mm ostium tolerance.
Precision {metrics['precision']:.1%}; recall {metrics['recall']:.1%}; F1 {metrics['f1']:.1%}.
This tolerance is our development comparison setting, not asserted organizer policy.
Groups with overlapping paths retain every distinct origin as an unresolved alternative.
Group-representative scores are NOT confirmed daughter-count accuracy.
Raw-candidate and 10 mm path scores are separately recorded in aggregate_metrics.json.
The previous hybrid's development comparison was 8 matches, 3 extras, 11 misses.
These five cases were repeatedly inspected during development. Existing neural folds exclude
the evaluated case, but this is not an independent test of all design decisions.
The other twenty cases have no reviewed daughter reference; their accuracy is unknown.

## CPU and geometry

{runtime['cases_completed']}/{runtime['cases_attempted']} runs completed; {runtime['under_60_seconds']} under 60 seconds.
Median whole-process time {runtime['median_seconds']:.2f} s, maximum {runtime['maximum_seconds']:.2f} s.
Maximum measured process peak working set {runtime['maximum_peak_working_set_mb']:.1f} MB.
Wall times include process startup, loading, growth, inference and saved outputs. Review-panel
rendering is a separate development operation. CPU inference only; thread counts limited to four.
This laptop measurement is not a guarantee on a slower organizer CPU, nor an enforced 8 GB sandbox.
Case 24 uses the original paired nonorthonormal-geometry fallback, including its support mask.
The loaded parent is unchanged and saved-array/physical-grid checks are recorded per case.

## Implemented method

1. Read CT and the supplied parent through the existing loader; validate geometry and valid CT support.
2. Reuse Tahoces-inspired blood/background density growth: 20 mm first pass, block excessive growth,
   regrow to 25 mm, then subtract the supplied parent. The .5 density-ratio cutoff and numerical spill
   rules are project adaptations, not values reproduced from the paper.
3. Enumerate all grown-lumen contacts around the parent. Test up to eight spaced starts per contact
   patch and up to three local directions (outgoing mean, surface normal, principal axis).
   This includes posterior surfaces and unnamed candidates, but cannot discover intensity-rejected
   origins and cannot certify exhaustive sampling of a very large merged contact patch.
4. Trace a supported 5 mm physical path, then attempt extension to 10 mm. Verify every crossed
   voxel cell, preserve exact parent voxel-face origins and retain seed-only paths if later extension fails.
5. Reuse Riffaud-style connected acyclic tree traversal to the first degree-three junction, leaf or
   10 mm. Cycles, early bifurcations and missing attachments remain visible in graph audit records.
   Local cross-section split checks are an additional heuristic, not proof that no bifurcation exists.
6. Measure perpendicular lumen sections 0.5 mm distal to the boundary as an explicit origin-diameter
   proxy, independently of seed radius. A one-native-voxel band around 2 mm requires review; it is
   not a statistical confidence interval. Do not silently reject a 1.91 mm proxy as certainly ineligible.
7. Estimate direction using an origin-relative principal axis over up to 3 seed radii of the path,
   inspired by Riffaud. Check seed placement by physical arc length.
8. Optionally score local CT patches with the existing small networks entirely on CPU. No network
   download or training is performed by inference. Models only support their trained 1.5 mm spacing;
   other grids use geometry alone, explicitly reported. Five labelled cases use held-out model pairs;
   new cases use the five-pair ensemble. These weak draft-trained scores are not calibrated probabilities.
9. Remove only near-identical origin/path proposals. Preserve separate ostia with convergent seeds;
   place overlapping paths into review groups, with every alternative kept in predictions.json.
10. Save cropped parent/growth/support masks, candidate paths, nullable review fields, rejection
    reasons, code/model hashes and a per-case review record. All fields remain unresolved until review.

## What remains unverified

The document is a review protocol, not an automatic classifier. Contrast-filled vessel identity,
true ostial diameter at coarse sampling, first anatomical bifurcation, terminal iliac exclusion,
complete detection and reviewer sign-off are still unresolved. Crop-cap rejection is geometric;
terminal iliac identity is explicitly flagged rather than guessed from a fixed anatomical list.
No corrected instance segmentation is exported: growth is a proposal mask and may still spill.
Original draft annotations and input dimensions are untouched. Cropped analysis masks preserve
physical coordinates but are not replacements for the full-size reference annotation files.

## All-case results

'''+ '\n'.join(table)+'''

## Run and inspect

From the repository root:

```powershell
.venv\\Scripts\\python.exe -m src.rebuild.review_pipeline --image PATH_TO_CT --parent PATH_TO_AORTA --output OUTPUT_DIRECTORY --neural
.venv\\Scripts\\python.exe -m src.rebuild.run_review_pipeline --neural --output rebuild/document_pipeline_final
```

The standalone command assumes a new unseen scan. For development cases 19–23, use the batch
runner so their training fold is excluded. Omit --neural for the pure classical CPU variant.
review_panels contains consecutive slices in all three orientations around every draft origin.
Only in-slice landmarks/path samples are drawn; no projected line pretends to be in the displayed slice.

Paper sources: https://doi.org/10.1007/s11517-019-02110-x and https://doi.org/10.1007/s11517-022-02603-2.
The previously read full-paper method reviews remain in TAHOCES_METHOD_REVIEW.md and RIFFAUD_METHOD_REVIEW.md.
'''
    (root/'REPORT.md').write_text(text,encoding='utf-8')
    entries=''.join(f'<figure><figcaption>{html.escape(p.stem)}</figcaption><img loading="lazy" src="review_panels/{p.name}" width="850"></figure>' for p in sorted(previews.glob('*.png')))
    (root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Daughter review</title><style>body{font:16px system-ui;margin:32px;max-width:1000px}img{max-width:100%}</style><h1>Draft-reference review panels</h1><p>Not expert-approved ground truth. See REPORT.md and reference_discrepancies.json.</p>'+entries,encoding='utf-8')
    print(json.dumps(totals,indent=2))


if __name__=='__main__':main()
