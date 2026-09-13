"""Build the teammate handoff from the frozen export and documented implementation."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Preformatted,Image
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/pdf';OUT.mkdir(parents=True,exist_ok=True)
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyX',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=8,textColor=colors.HexColor('#243945')))
styles.add(ParagraphStyle(name='SmallX',parent=styles['BodyX'],fontSize=8,leading=11))
styles.add(ParagraphStyle(name='CodeX',fontName='Courier',fontSize=8,leading=11,spaceAfter=10))
styles['Title'].textColor=colors.HexColor('#175e65');styles['Heading1'].textColor=colors.HexColor('#175e65')
story=[]
def p(text):story.append(Paragraph(text,styles['BodyX']))
def title(n,text):story.append(Paragraph(f'{n} / {text}',styles['Heading1']));story.append(Spacer(1,8))
def step(n,name,text):p(f'<b>{n}. {name}</b><br/>{text}')
def code(text):story.append(Preformatted(text,styles['CodeX']))
def table(rows,widths,compact=False):
    data=[[Paragraph(escape(str(c)),styles['SmallX']) for c in r] for r in rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dcebe8')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#ced8dd')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),3 if compact else 6),('BOTTOMPADDING',(0,0),(-1,-1),3 if compact else 6)]));story.append(t);story.append(Spacer(1,12))
def new():story.append(PageBreak())

story.append(Paragraph('Branchseed',styles['Title']))
story.append(Paragraph('Aortic daughter detection: teammate handoff',styles['Heading2']))
p('Project snapshot: 13 September 2026. CPU implementation, exported development predictions, reproducible workflow and known limitations.')
title('01','What we are building')
p('Input: a CT scan and a binary mask containing <b>only the parent aortic lumen</b>. Output: anonymous instances of eligible arteries that connect directly to that supplied aorta. The CT contains the daughter evidence; the parent mask anchors the search.')
p('For each instance, report the opening centre, a lumen seed 5 mm along the daughter path, local radius at that seed, and initial outward unit direction. Trace up to 10 mm or the first downstream bifurcation. The minimum origin diameter is 2 mm. Do not guess a fixed number of named arteries.')
table([['Current exported result','Meaning'],['17 of 19 draft branches matched','Measured on cases 19-23 only'],['1 unmatched prediction; 2 misses','94.4% precision, 89.5% recall, 91.9% F1'],['20 cases without daughter references','Their detection accuracy is unknown'],['125 active tests pass','Implementation checks, not anatomical validation']],[180,330])
p('<b>Do not describe this as 90% accuracy across 25 cases.</b> Evaluation uses a 3 mm origin-matching tolerance on five draft-labelled development cases. These cases informed tuning. There is no independent hidden-test result and no expert anatomical sign-off.')
p('The review set is broader than the submission set: it matches 18/19 draft branches with two unmatched counted groups and one deferred candidate. The strict 2 mm export filter removes one matched case-19 candidate and one unmatched case-21 candidate. The two sets must not share the same reported score.')
table([['Read / view','Location in the project'],['Submission JSONs','outputs/predictions/subject001.json ... subject025.json'],['JSON bundle and visual checks','outputs/predictions.zip'],['Offline team presentation','outputs/team_review/index.html or Show-Team-Review.cmd'],['This handoff','outputs/pdf/Branchseed_Team_Handoff.pdf']],[180,330])
new();title('02','Steps 1-7: load, model blood intensity, grow')
step(1,'Read CT and aorta mask','The loader supports NIfTI and gzip content with misleading extensions. It reads physical origin, voxel spacing and orientation. Array indices alone are not valid exported coordinates.')
step(2,'Preserve case-24 geometry handling','Non-orthonormal input uses the original paired resampling fallback: interpolate CT and use nearest-neighbour sampling for the binary mask. This preserves the intended physical alignment on a corrected grid. A working display does not mean branches were detected.')
step(3,'Identify real source coverage','A valid-support volume distinguishes actual CT coverage from padding created during resampling. Artificial border voxels cannot be used as evidence of a vessel.')
step(4,'Crop the analysis region','Work near the supplied aorta with approximately 27 mm padding for the 25 mm growth limit. The cropped SimpleITK image retains its physical origin, spacing and direction. Original source images are not edited.')
step(5,'Fit inside/outside intensity distributions','Build smoothed histograms from the supplied parent and a surrounding exterior band (5-10 mm from the parent). The current growth call uses whole-parent sampling. The histogram model uses 512 bins and 16 HU smoothing. This adapts the first paper\'s density-comparison idea; it does not simply brighten the scan.')
step(6,'Decide which voxels may grow','The main test is f_inside / (f_inside + f_outside) >= 0.5, with a minimum inside-density support of 1% of its peak. The score is not a calibrated probability of blood. Similar-intensity veins, tissue or artifacts can still qualify.')
step(7,'Expand in 3D with spill control','Grow through face-connected eligible voxels, initially within 20 mm of the parent. The current volume_stop mode combines bulk and expansion-volume controls, then regrows within 25 mm while excluding blocked regions. Subtract the parent to obtain exterior growth. The 20/25 mm limits and numeric spill rules are implementation adaptations.')
p('<b>Output of this stage:</b> a fixed parent mask, accepted intensity map, connected exterior growth, blocked regions and valid support. This is a search segmentation, not a verified per-daughter segmentation. Missing growth can prevent any later candidate from being proposed.')
p('<b>Code:</b> src/utils.py; src/rebuild/image_support.py; intensity_growth.py; staged_growth.py; spill_control.py; src/expansion.py.')
new();title('03','Steps 8-13: propose and measure paths')
step(8,'Find possible wall openings','Collect exterior grown voxels touching the aorta, then identify contact patches. Sample up to eight spatially distinct starting sites per patch and several local outward directions. Screen obvious crop-cap candidates. Nearby real openings can still be merged by imperfect growth.')
step(9,'Generate complementary proposals','Combine local tracking with skeleton-graph proposals. At supported 1.5 mm spacing with neural mode, add face-origin proposals and bounded local flooding. These are alternative hypotheses, not separate confirmed branches.')
step(10,'Trace a supported proximal path','First establish a 5 mm path, then attempt extension toward 10 mm or a downstream split. Cross-sections guide lumen-centre tracking. Retain uncertainty if extension fails after the seed. An early split must not be silently resolved by choosing a downstream daughter.')
step(11,'Measure origin, seed and radii','Locate the origin on the supplied parent voxel-cell boundary. Compute cumulative physical arc length and interpolate the seed at 5 mm. Estimate seed radius from perpendicular lumen cross-sectional area: r = sqrt(area / pi). Measure a separate origin-diameter proxy approximately 0.5 mm beyond the wall. This proxy is sensitive to voxel sampling and spill.')
step(12,'Estimate initial direction','Use an origin-relative principal-axis estimate over the first min(3 x seed radius, available path length) mm, inspired by the second paper. Orient it outward and normalize it. Direction therefore need not exactly equal the straight origin-to-seed vector.')
step(13,'Audit geometry and deduplicate','Check actual voxel intervals along the path, not only sampled endpoints. Verify boundary contact, physical seed distance and proximal extent. Consolidate nearly identical proposals using origin distance (<1 mm), seed distance (<1.5 mm) and direction agreement (dot product >0.8). Preserve alternative evidence.')
p('<b>Physical coordinates:</b> exports use SimpleITK LPS millimetres. Negative coordinates are valid. Voxel spacing and direction are applied during conversion. A curved 5 mm path may have an origin-to-seed straight-line distance below 5 mm.')
p('<b>Code:</b> src/daughter_geometry.py; centreline_extraction.py; vascular_tree.py; src/rebuild/review_pipeline.py; daughter_graph.py; local_flood.py.')
new();title('04','Steps 14-18: select, refine and review topology')
step(14,'Score CPU neural evidence','A small existing 3D network sees local CT, parent mask and parent-distance channels. Models operate at their trained 1.5 mm spacing; unsupported spacing is reported and does not receive this neural scoring. Local crops bound memory. Scores are supporting evidence, not calibrated certainty. Development cases use held-out model pairs; unseen cases use the available ensemble.')
step(15,'Verify local opening evidence','Review sections across the first 5 mm for a bounded lumen, sensible shape and width variation, and contrast against surrounding tissue. Typical checks require at least four supported sections, no clipped section, median aspect and radius ratio <=3, and median contrast >=25 HU. Neural and stronger CT-only evidence routes differ; flood and face proposals have extra safeguards.')
step(16,'Apply constrained rescue and refinement','Adaptive rescue reconsiders strong corroborated flood proposals. Origin review tests improved wall-origin positions for selected weak candidates. Section review revisits one problematic cross-section when adjacent sections support a narrow lumen. These rules do not use an expected reference count and do not repeatedly lower all thresholds.')
step(17,'Group origins and attach review flags','Combine proposals describing the same suspected opening using origin and shared-path evidence. Aim to preserve separate wall ostia while treating a common trunk as one direct origin. Flag near-end locations, wall-parallel paths, size uncertainty and unresolved distal stops. Flags are not anatomical decisions.')
step(18,'Apply the aortic-backbone graph review','Skeletonize parent plus growth and constrain a backbone path to the supplied aorta. Examine complete off-backbone components, attachments and wall exits. A single acyclic attachment with an agreeing wall exit provides support. Preserve ambiguous cycles and competing attachments instead of forcing them into a tree.')
p('A narrow deferral rule detects an unbranched supported return route attached to the backbone twice: no side arm, attachment separation >= two native voxel spacings and exterior route >=5 mm. It defers one case-21 candidate. This is not proof that the structure is anatomically false.')
p('<b>Graph limitation:</b> 13 of 25 cases exceed the review budgets (11 volume limits, 2 node limits). Their provisional results remain; the graph stage did not validate them. The second paper starts from an extracted vascular tree, whereas our growth can contain spill and cycles.')
p('<b>Code:</b> src/rebuild/opening_verification.py; adaptive_rescue.py; origin_review.py; section_review.py; origin_triage.py; aortic_tree_review.py.')
new();title('05','Steps 19-22: export, inspect and evaluate')
step(19,'Apply challenge eligibility','Export one representative per retained group. Exclude deferred candidates. Require estimated origin diameter >=2 mm, at least 5 mm of path, a seed at 5 mm arc length, finite physical coordinates, positive seed radius and an outward nonzero direction. Normalize the direction. Near-threshold measurement errors can remove true branches.')
step(20,'Write one submission per case','Assign branch_001, branch_002, etc. Link every instance to aorta. Keep the JSON compact; diagnostics preserve internal candidate IDs and exclusion reasons. Automatic predictions do not require fabricated human approval. Empty daughters means no eligible candidate was exported, not proof that no vessel exists.')
step(21,'Preserve review evidence and visual checks','Save candidate paths, parent/growth/support masks, timings, model/source provenance and unresolved flags. Three required checks show CT, parent border, ostia and projected direction arrows. The team gallery contains all retained and deferred review groups; it is a broader selection than the challenge export.')
step(22,'Evaluate after inference/export','Only after predictions are saved, read draft references and match origins one-to-one. At the reported 3 mm development tolerance, unmatched predictions are false positives and unmatched references are misses. Excluding a true reference branch from export still counts as a miss. Unlabelled cases have no measured daughter accuracy.')
example=json.loads((ROOT/'outputs/predictions/subject019.json').read_text())
d=example['daughters'][0]
code('''{
  "case_id": "subject019",
  "parent": {"instance_id": "aorta"},
  "daughters": [
    {
      "instance_id": "branch_001",
      "parent_instance_id": "aorta",
      "ostium_xyz_mm": [13.529624, -168.116203, 281.849996],
      "seed_xyz_mm": [14.115088, -164.088172, 280.580420],
      "radius_mm": 1.236077,
      "direction_xyz": [-0.132332, 0.948285, -0.288519]
    }
  ]
}''')
p('Illustrative excerpt: the first of two exported case-19 branches, rounded here. The actual file includes both branches and full numeric precision. Radius is measured at the seed, not at the origin.')
new();title('06','Results and known failure cases')
summary=json.loads((ROOT/'outputs/predictions/diagnostics/export_summary.json').read_text())
rows=[['Case','Exported','Matched','Unmatched','Missed']]
for r in summary['cases']:
    e=r.get('agreement_3mm');rows.append([f'{r["case"]:02d}',r['daughters'],e['tp'] if e else 'Unknown',e['fp'] if e else 'Unknown',e['fn'] if e else 'Unknown'])
table(rows,[55,75,120,130,130],compact=True)
p('Total: 103 automatic predictions across 25 cases. Only 18 predictions are in the five labelled cases: 17 match and one does not. Recall = 17/19; precision = 17/18; F1 = 34/37. These are origin-discovery metrics, not segmentation overlap or an overall challenge score.')
p('<b>Case 19:</b> the 2 mm estimated-origin filter removes one reference-matched candidate. <b>Case 20:</b> one reference remains missed. <b>Case 21:</b> three matches, one unmatched exported candidate; a separate return connection remains deferred. <b>Case 24:</b> readable geometry but zero exported branches; detection accuracy is unknown.')
p('The prior 25-case CPU run completed within 60 seconds per case (maximum about 55.42 seconds, peak working set about 1.14 GB). These are measured local development-run figures, not a guarantee on organizer hardware or all unseen inputs. The current layout passes 125 tests and cases 21/24 reproduce frozen predictions and mask geometry.')
new();title('07','Visual review with teammates')
p('Double-click Show-Team-Review.cmd, or open outputs/team_review/index.html. Share outputs/team_review.zip, extract it on the other computer, then open index.html. This is offline static CT review: no Python installation, server or model weights are needed for viewing.')
img=ROOT/'outputs/predictions/visual_checks/subject019.png'
from PIL import Image as PILImage
w,h=PILImage.open(img).size
story.append(Image(str(img),width=510,height=510*h/w));story.append(Spacer(1,10))
p('<b>Above:</b> exported case-19 predictions. Cyan is the parent boundary, red is the origin, and magenta is the projected direction arrow. A 2D projection is not an in-slice vessel trace. Missing parent outline in one plane can reflect the local slice geometry; inspect consecutive and orthogonal views.')
p('The full review gallery uses magenta path samples and five consecutive slices in each of three planes. Yellow outlines show draft daughter labels where available. It includes 132 retained groups and one deferred group in 135 montages. The submission JSONs contain 103 instances after stricter export filtering.')
p('<b>Five-minute demonstration:</b> explain the inputs and two-paper adaptation; inspect case 19; show the deferred connection and remaining extra in case 21; acknowledge the case-20 miss and case-24 limitation; finish with the measured metrics and unknown coverage.')
new();title('08','Run, commit and share')
p('Run commands from the project root using Python 3.13. Source lives in src/, weights in models/, originals in data/, development references in references/, saved runs in results/ and deliverables in outputs/. The old work is outside the project in ../_branchseed_history_20260913/.')
code('python -m pip install -r config/requirements-submission.txt\npython run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz \\\n    --output prediction.json')
p('The backslash above is a visual line continuation for this document: enter the run command on one line in PowerShell. CPU neural evidence is enabled by default where spacing is supported. Missing requested weights produce an error. For development cases 19-23 add --held-out-case 21 (using the corresponding number). A new unseen case uses the available ensemble.')
code('python -m unittest discover -s tests -p "test_*.py"\npython -m tools.export_challenge_predictions\npython -m tools.build_team_review')
p('Export/gallery rebuild tools read saved results and, for evaluation, reference data. A code-only clone is not sufficient for those tasks. Inference needs compatible model weights, while viewing the offline presentation does not.')
table([['Commit to Git','Share separately / ignored by default'],['run.py, src/, tests/, tools/, config/, docs/, README.md, launcher, .gitignore','models/, data/, references/, results/, outputs/, .venv/'],['Updated tracked deletions from the relocation','Large weights, original volumes and review bundles']],[255,255])
p('<b>Git status checked:</b> the restructure has untracked source directories and tracked deletions of old locations. Commit both sides together, rather than only modifying run.py. git diff --check passed. This handoff has not staged, committed or pushed anything.')
code('git add -A\ngit diff --cached --stat\ngit commit -m "Organize detector and challenge exports"')
p('<b>How teammates see the JSONs:</b> send outputs/predictions.zip; they extract it and open subject021.json in VS Code or a text editor. To make the 25 JSONs visible directly in the Git repository despite outputs/ being ignored, intentionally stage only those files:')
code('git add -f -- outputs/predictions/subject*.json')
p('Do not assume git add -A includes ignored outputs or weights. If sharing the PDF through Git, explicitly add outputs/pdf/Branchseed_Team_Handoff.pdf as well. The 25 JSONs are automatic predictions, not expert annotations. Coordinate with the team on separate delivery of required models and permitted data.')
p('<b>Source basis:</b> organizer challenge instructions supplied by the user; local source code and frozen export_summary.json. Tahoces paper: DOI 10.1007/s11517-019-02110-x (inside/outside intensity and growth inspiration). Riffaud paper: DOI 10.1007/s11517-022-02603-2 (vascular-tree/backbone traversal and initial-direction inspiration). The implementation is an adaptation, not a full reproduction of either paper.')

def footer(canvas,doc):
    canvas.setStrokeColor(colors.HexColor('#ced8dd'));canvas.line(42,37,552,37)
    canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#526773'))
    canvas.drawString(42,24,'Branchseed | Development handoff | 13 September 2026')
    canvas.drawRightString(552,24,str(doc.page))
doc=SimpleDocTemplate(str(OUT/'Branchseed_Team_Handoff.pdf'),pagesize=(594,842),rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=48,title='Branchseed - Teammate Handoff',author='Branchseed project')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT/'Branchseed_Team_Handoff.pdf')
