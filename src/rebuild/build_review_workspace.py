"""Build an all-case review index after frozen inference; no detector edits."""
import argparse
import html
import json
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from src.rebuild.report_review_pipeline import pooled
from src.rebuild.diagnose_remaining_errors import review_panel
from src.rebuild.review_record import write_review_record
from src.utils import read_nifti_pair


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path('results/aortic_tree_verified'))
    args=parser.parse_args();root=args.results
    rows=json.loads((root/'summary.json').read_text())
    if len(rows)!=25 or any('error' in r for r in rows):raise ValueError('Require 25 successful cases')
    document=Path(r'C:\Users\nikag\.codex\attachments\221ae0cc-9929-4d68-aa43-395e00587b2a\pasted-text.txt')
    baseline_root=Path('results/protocol_review_final');checks=[];sections=[];triage=[]
    figures=root/'review_panels';figures.mkdir(exist_ok=True)
    for row in rows:
        case=row['case'];folder=root/f'subject{case:03d}'
        result=json.loads((folder/'predictions.json').read_text())
        old=json.loads((baseline_root/folder.name/'predictions.json').read_text())
        reps=[g['representative'] for g in result['review_groups']]
        old_reps=[g['representative'] for g in old['review_groups']]
        raw_reps=[g['representative'] for g in result.get('pre_tree_review_groups',result['review_groups'])]
        deferred=[g['representative'] for g in result.get('deferred_groups',[])]
        identical=(len(raw_reps)==len(old_reps) and all(a['ostium_xyz_mm']==b['ostium_xyz_mm'] and
            a['path_xyz_mm']==b['path_xyz_mm'] for a,b in zip(raw_reps,old_reps)))
        unchanged=all(np.array_equal(sitk.GetArrayFromImage(sitk.ReadImage(str(folder/f))),
            sitk.GetArrayFromImage(sitk.ReadImage(str(baseline_root/folder.name/f))))
            for f in ('parent.nii.gz','growth.nii.gz'))
        checks.append(dict(case=case,unchanged_predictions=identical,unchanged_masks=unchanged,**row['checks']))
        source=Path('data/TORALIS CHALLENGE')/folder.name
        record=folder/'review_record.json'
        if not record.exists():write_review_record(result,source/f'orig{case}.nii',source/f'mask{case}.nii',document,record)
        ct,parent=read_nifti_pair(source/f'orig{case}.nii',source/f'mask{case}.nii')
        parent_array=sitk.GetArrayFromImage(parent)>0
        ref=None
        if 19<=case<=23:
            ref=sitk.GetArrayFromImage(sitk.ReadImage(f'references/border_results/case_{case}/inputs/daughters{case}_draft.nii.gz'))
        # Every retained group must have an image. Priority changes ordering,
        # never coverage: truncating this list hides successful detections.
        prioritized=sorted(reps+deferred,key=lambda p:-sum(f!='origin_diameter_requires_adjudication'
            for f in p['direct_origin_review']['flags']))
        show=prioritized
        images=[]
        for p in show:
            name=f'case{case}_{p["instance_id"]}.png'
            status='DEFERRED return connection' if p in deferred else 'provisional, direct origin unresolved'
            review_panel(ct,parent_array,None,ref,p['ostium_xyz_mm'],p['path_xyz_mm'],
                f'Case {case}: {p["instance_id"]}; {status}',figures/name,
                slice_label='corrected slice' if result['loading']['geometry_resampled'] else 'native slice')
            images.append(f'<a href="review_panels/{name}"><img loading="lazy" src="review_panels/{name}" alt="Case {case} multi-plane CT review"></a>')
            if p in deferred:
                name=f'case{case}_{p["instance_id"]}_return.png'
                review_panel(ct,parent_array,None,ref,p['ostium_xyz_mm'],p['aortic_tree_review']['return_route_xyz_mm'],
                    f'Case {case}: extracted return connection, NOT a confirmed daughter path',figures/name)
                images.append(f'<p>Deferred evidence: the extracted route connects to the backbone twice. Anatomical status remains unresolved.</p><img loading="lazy" src="review_panels/{name}" alt="Extracted return connection">')
        if not show:
            centre=np.mean(np.argwhere(parent_array),axis=0)[::-1]
            origin=ct.TransformContinuousIndexToPhysicalPoint(centre.tolist());name=f'case{case}_coverage.png'
            review_panel(ct,parent_array,None,ref,origin,[],f'Case {case}: coverage preview; red marker is parent centre, NOT a branch',figures/name,
                slice_label='corrected slice' if result['loading']['geometry_resampled'] else 'native slice')
            images.append(f'<img loading="lazy" src="review_panels/{name}" alt="Parent coverage only">')
        entries=[]
        for p in reps+deferred:
            evidence=p['direct_origin_review'];q=ct.TransformPhysicalPointToContinuousIndex(p['ostium_xyz_mm'])
            triage.append(dict(case=case,candidate=p['instance_id'],origin_index_xyz=list(q),**evidence))
            entries.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [p['instance_id'],
                ', '.join(f'{v:.2f}' for v in q),f"{p['origin_diameter_mm']:.2f}",
                ('DEFERRED; ' if p in deferred else '')+p.get('aortic_tree_review',{}).get('decision','not reviewed')+'; '+
                ('; '.join(evidence['flags']) or 'Anatomy still unresolved')])+'</tr>')
        e=row.get('review_group_agreement_3mm')
        metric=f"Draft comparison: {e['tp']} matches, {e['fp']} unmatched groups, {e['fn']} misses." if e else 'No daughter reference labels: anatomical accuracy unknown.'
        sections.append(f'''<details id="case{case}" {'open' if case==21 else ''}><summary>Case {case:02d} — {len(reps)} provisional groups, {len(deferred)} deferred</summary>
<p>{metric} CPU {row['whole_process_seconds']:.2f} seconds. Resampled geometry: {result['loading']['geometry_resampled']}.</p>
<p><a href="subject{case:03d}/predictions.json">All prediction evidence</a> · <a href="subject{case:03d}/review_record.json">Checklist record</a></p>
<table><tr><th>Candidate</th><th>Origin index XYZ</th><th>Diameter proxy mm</th><th>Review priority</th></tr>{''.join(entries)}</table>
<p>Showing all {len(reps)} provisional and {len(deferred)} deferred groups. Montages show five consecutive slices in each plane. Paths appear only on intersected slices; an absent path on one slice is not an absent detection.</p>{''.join(images)}</details>''')
        print(f'Case {case}: {len(reps)} groups, {max(1,len(show))} montages',flush=True)
    assert all(all(v for k,v in c.items() if k!='case') for c in checks)
    metrics=pooled(rows,'review_group_agreement_3mm')
    report=dict(metrics=metrics,checks=checks,cases=25,review_records=25,
        max_cpu_seconds=max(r['whole_process_seconds'] for r in rows),
        under60=sum(r['within_60_seconds'] for r in rows),
        max_memory_mb=max(r['peak_working_set_mb'] for r in rows),triage=triage)
    (root/'audit.json').write_text(json.dumps(report,indent=2))
    (root/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Branchseed — 25-case review</title>
<style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:0 20px;color:#182d40;background:#f5f7fa}h1{font-size:30px}details{background:white;border:1px solid #cad4de;border-radius:8px;padding:18px;margin:16px 0}summary{font-size:20px;font-weight:650;cursor:pointer}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:9px;border:1px solid #dbe2e9;text-align:left}img{width:100%;height:auto;margin:14px 0}a{color:#175b96}.note{padding:18px;border-left:4px solid #b37914;background:#fff6df}</style>
<h1>Branchseed: review all 25 cases</h1><p>CT evidence, aortic-backbone review and unresolved questions. Deferred candidates remain visible.</p>
<p class="note">Only cases 19–23 have draft daughter labels. The 3 mm origin comparison measures development agreement, not complete segmentation accuracy. Flags prioritise review; a wall-parallel vessel is not automatically false. No cases are anatomically signed off.</p>
<p>The tree review can defer a supported route that reconnects to the aortic backbone without an outgoing arm. Other ambiguous graphs remain provisional. This is not anatomical sign-off. Expand a case to inspect all evidence.</p>
'''+''.join(sections)+'</html>',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('triage','checks')}))


if __name__=='__main__':main()
