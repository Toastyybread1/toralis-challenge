"""Build a portable, offline review of the frozen results; never runs inference."""
import argparse
import json
import shutil
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path('results/aortic_tree_verified'))
    parser.add_argument('--output',type=Path,default=Path('outputs/team_review'))
    args=parser.parse_args();source=args.results;out=args.output
    out.mkdir(parents=True,exist_ok=True)
    rows=json.loads((source/'summary.json').read_text())
    if len(rows)!=25 or any('error' in r for r in rows):raise ValueError('25 completed cases required')
    values=[r['review_group_agreement_3mm'] for r in rows if 'review_group_agreement_3mm' in r]
    tp,fp,fn=[sum(v[k] for v in values) for k in ('tp','fp','fn')]
    deferred=sum(r.get('deferred_groups',0) for r in rows)
    for name in ('REPORT.md','summary.json','audit.json','validation.json'):
        shutil.copy2(source/name,out/name)
    cleanup=Path('docs/CLEANUP_VALIDATION.json')
    if cleanup.exists():shutil.copy2(cleanup,out/'cleanup_validation.json')
    shutil.copytree(source/'review_panels',out/'review_panels',dirs_exist_ok=True)
    for folder in source.glob('subject*'):
        if not folder.is_dir():continue
        target=out/folder.name;target.mkdir(exist_ok=True)
        for name in ('predictions.json','review_record.json','REVIEW.md'):
            if (folder/name).exists():shutil.copy2(folder/name,target/name)
    gallery=(source/'index.html').read_text(encoding='utf-8')
    gallery=gallery.replace('<h1>', '<p><a href="index.html">← Team overview</a></p><h1>',1)
    gallery=gallery.replace('</html>', '''<script>
function openCase(){const d=document.getElementById(location.hash.slice(1));if(d){d.open=true;d.scrollIntoView();}}
window.addEventListener('hashchange',openCase);openCase();
</script></html>''')
    (out/'cases.html').write_text(gallery,encoding='utf-8')
    buttons=''.join(f'<a class="case" href="cases.html#case{r["case"]}">{r["case"]:02d}</a>' for r in rows)
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aortic daughter vessels — team review</title><style>
*{box-sizing:border-box}body{margin:0;background:#eef3f5;color:#153242;font:17px/1.6 system-ui}main{max-width:1120px;margin:auto;padding:48px 24px}h1{font-size:42px;line-height:1.15;margin:12px 0 20px}h2{font-size:25px;margin-top:0}.eyebrow{font-size:13px;text-transform:uppercase;letter-spacing:2px;color:#31766b}a{color:#176c85}section{background:white;border:1px solid #d4dfe2;border-radius:12px;padding:26px;margin:24px 0}.stats,.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.stat{border-top:3px solid #277a70;padding:12px 0}.stat strong{display:block;font-size:34px}.muted{color:#506772}.warning{background:#fff5dc;border-color:#e2d3aa}.case{display:inline-block;border:1px solid #c2d4da;border-radius:6px;text-decoration:none;padding:8px 13px;margin:5px}.button{display:inline-block;background:#175e65;color:white;padding:11px 20px;border-radius:7px;text-decoration:none;margin:8px 8px 8px 0}li{margin:8px 0}img{max-width:100%}@media(max-width:700px){.stats,.steps{grid-template-columns:1fr}h1{font-size:32px}}@media print{.case,.button{color:#153242;background:white}section{break-inside:avoid}}
</style><main><div class="eyebrow">Branchseed / frozen CPU results / 25 cases</div>
<h1>Where do daughter vessels<br>leave the aorta?</h1>
<p>We start with a CT scan and an aorta-only mask, grow into nearby contrast-filled tissue, then review whether candidate paths have a direct aortic origin.</p>
<a class="button" href="cases.html#case21">Inspect case 21</a><a class="button" href="cases.html">Browse all 25 cases</a>
<section><h2>What the evaluation supports</h2><div class="stats">
<div class="stat"><strong>TP/TOTAL</strong>draft origins matched</div><div class="stat"><strong>FP</strong>unmatched counted groups</div><div class="stat"><strong>DEFERRED</strong>candidate deferred</div></div>
<p><b>PRECISION precision · RECALL recall · FONE F1</b> at 3 mm origin tolerance.</p>
<p class="muted">Only cases 19–23 have daughter draft references. These are development results, not independent anatomical accuracy. The other 20 cases have no measured daughter accuracy.</p></section>
<section><h2>How the current method works</h2><div class="steps">
<div><b>1 · Preserve the aorta</b><p>Read physical geometry and keep the supplied parent border fixed. Case 24 retains its paired resampling fallback.</p></div>
<div><b>2 · Fill nearby lumen</b><p>Compare inside/outside CT intensities using the first paper's idea, with bounded growth and spill checks.</p></div>
<div><b>3 · Propose paths</b><p>Find candidate wall contacts and track supported paths in 3D. Existing CPU neural evidence helps rank candidates.</p></div>
<div><b>4 · Check geometry</b><p>Review origin, perpendicular sections, physical 5 mm seed distance and the first downstream split.</p></div>
<div><b>5 · Trace to the backbone</b><p>Use the second paper's graph concept to examine aortic attachments. Keep common trunks together and preserve uncertain graph connections.</p></div>
<div><b>6 · Review uncertainty</b><p>Defer a supported, unbranched return connection. Retain other unresolved candidates for anatomical review.</p></div></div></section>
<section class="warning"><h2>What we still cannot claim</h2><p>Case 20 has one missed reference. Case 21 has two unmatched counted groups, plus one deferred return connection. Thirteen cases exceed the graph-review size limits. Tree support does not certify anatomy, and the fill is not an approved per-vessel segmentation.</p><p>The raw proposal set still has three unmatched groups: the precision improvement comes from withholding one ambiguous candidate, not proving it false.</p></section>
<section><h2>A five-minute walkthrough</h2><ol>
<li><a href="cases.html#case19">Case 19:</a> show a reference-matched example and explain the supplied aortic border.</li>
<li><a href="cases.html#case21">Case 21:</a> compare the retained candidates with the deferred return-path evidence.</li>
<li><a href="cases.html#case20">Case 20:</a> show the remaining miss and discuss the accuracy limit.</li>
<li><a href="cases.html#case24">Case 24:</a> distinguish correct image loading from successful vessel detection.</li></ol>
<p><b>Read the montage:</b> cyan = exact supplied parent border; yellow = draft daughter outline where available; red = candidate origin; magenta = path samples in the displayed slice. Each montage contains five consecutive slices in each of three planes. Missing marks on one slice do not mean a missing 3D detection.</p></section>
<section><h2>Choose a case</h2>BUTTONS</section>
<section><h2>Reproducibility</h2><p>All 25 cases completed on CPU, with a maximum of MAXTIME seconds per case. The original result set passed 147 tests; the cleanup validation is documented in the repository. Raw paths and mask arrays were preserved.</p><p><a href="REPORT.md">Full method and limitations</a> · <a href="summary.json">Per-case evaluation</a> · <a href="validation.json">Frozen result validation</a></p><p class="muted">This folder works offline. Share the whole folder or its ZIP, then open index.html. It contains CT review images and prediction evidence; it does not include source volumes or model weights.</p></section></main></html>'''
    replacements={'TP/TOTAL':f'{tp}/{tp+fn}','>FP<':f'>{fp}<','>DEFERRED<':f'>{deferred}<',
        'PRECISION':f'{tp/(tp+fp):.1%}','RECALL':f'{tp/(tp+fn):.1%}','FONE':f'{2*tp/(2*tp+fp+fn):.1%}',
        'BUTTONS':buttons,'MAXTIME':f'{max(r["whole_process_seconds"] for r in rows):.2f}'}
    for key,value in replacements.items():page=page.replace(key,value)
    if cleanup.exists():
        checks=json.loads(cleanup.read_text())
        page=page.replace('The original result set passed 147 tests; the cleanup validation is documented in the repository.',
            f'The original result set passed 147 tests. After archiving retired experiments, all {checks["active_tests_passed"]} active tests pass; cases 21 and 24 reproduce their frozen results exactly. <a href="cleanup_validation.json">Cleanup validation</a>.')
    (out/'index.html').write_text(page,encoding='utf-8')
    (out/'START_HERE.txt').write_text('Open index.html in a browser. Keep all files together. No installation or internet required.\n')
    shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name)
    print(f'Built {out}/index.html and {out}.zip')


if __name__=='__main__':main()
