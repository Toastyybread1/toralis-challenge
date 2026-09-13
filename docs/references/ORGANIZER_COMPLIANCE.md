# Organizer review record: application alignment

The supplied review record is preserved verbatim in ORGANIZER_REVIEW_RECORD.md and governs this audit. It is a reference-annotation review procedure, including visual adjudication and release sign-off. Automatic detection cannot itself complete those human decisions. The organizer labels remain the project reference; their pending register remains pending.

## Ordered workflow and current implementation

| Required step | Current behavior / remaining work |
|---|---|
| Matching CT, parent, daughter labels, notes and three-plane alignment | CT/parent geometry is checked before detection. Original inputs are preserved. Reports fingerprint inputs and record processing geometry. ITK-SNAP inspection, label import and reading all case notes remain pending visual review. |
| Preserve dimensions, spacing, physical geometry and integer instances | Source files are not modified; internal ROI is reported separately. The reader may resample nonorthogonal inputs, so original hashes and reader geometry are recorded. No reviewed daughter-instance masks are exported yet. |
| Continuous direct aortic lumen | Face-connected expansion starts at the parent; the review checks sampled path and seed support in one expansion component. Contrast continuity, common trunks and direct versus downstream anatomy still require visual adjudication. |
| Parent-boundary ostium | Half-occupancy boundary convention; independently rechecked in physical coordinates. Corrections to parent imperfections must be recorded by the reviewer. |
| Perpendicular origin diameter >=2 mm | Existing area-equivalent origin diameter is recorded separately from seed radius. Borderline eligibility and partial-volume uncertainty remain visual-review items. |
| Seed 5 mm along path within lumen | Independently interpolate saved arc length; check seed in expanded daughter outside parent. Expansion support is not per-instance mask support. |
| Stop at 10 mm or first bifurcation | New report flags numerical truncation before 10 mm unless a possible bifurcation is recorded. True first bifurcation remains unconfirmed. Early splits before 5 mm retain located rejection records and unresolved policy; no downstream seed is invented. |
| Lumen width, leakage, holes, fragments, overlaps | Local leakage mode is experimental. Per-daughter segmentation, instance overlap checks and anatomical spill assessment are not implemented; report explicitly marks them unavailable/pending. |
| Guide, direction and mask coverage | Unit outward direction, saved path and sampled expansion support are checked. Full lumen extent and guide correctness remain pending. |
| Null and measurement flags | Null values remain unresolved. Evaluator skips unavailable optional errors instead of treating null as zero or crashing. |
| Entire parent sweep, no fixed named/count assumption | Algorithm examines generated contacts across the supplied parent, with no anatomical naming/count prior. This does not prove exhaustive detection. Circumference sweep, excluded candidates, image-quality gaps and scoring policy remain pending. |
| Crop caps and iliac split | Existing terminal-plane heuristic remains; no explicit anatomical iliac classifier. Review record requires visual confirmation. |
| Versioned masks, reopening checks and provenance | Prediction/review JSON are saved and reopened; source/outputs are fingerprinted. Human-reviewed outputs are protected from overwrite, requiring a new output name. Edited-mask saving and visual reinspection remain a future workflow. |
| Decisions, case disposition, sign-off | Every predicted branch starts unresolved. Automatic failures yield further edits required. No case is automatically approved, including empty results. Reviewer/date/release fields are unset. |

## Outputs and verification

Every CLI run now emits a .review.json beside prediction JSON, diagnostics and preview. It records automatic checks, pending visual checks, measurement methods, candidate rejection coordinates, provenance and blank review decisions. A passing automatic report does not mean the record has been completed.

Ran all five organizer cases with local_bulk leakage and single contact initialization, preserving that experiment's predictions exactly. Case 21 has one predicted branch (branch_003 in that output, not necessarily the same organizer ID) whose path ends before 10 mm for a reason other than bifurcation. Its report is further edits required. Other runs have no automatic failures but remain unresolved. Cases 19 and 23 are empty and are not certified complete.

The contact-fallback experiment remains opt-in. It increased 3 mm matches from 6 to 10 but also extras from 3 to 8, so it is not promoted as a validated improvement. Organizer-review work took priority before further tuning.

Reproduce the review run using the existing run.py command, optionally with --leakage-mode local_bulk. Use a new --output filename after entering human review decisions. Do not substitute expanded-component labels for reviewed daughter-instance masks.

## Next implementation priority

Resolve the premature-track termination flagged in case 21, then add per-daughter proximal masks with connectivity, overlap and landmark-support validation. A review viewer/workflow must still support consecutive slices and explicit accept/edit/exclude/unresolved decisions before reference approval can be claimed.


## Completion-policy update

Premature numerical tracks are now excluded from exported daughters and retained with partial measurements in review diagnostics. Case 21's flagged 7.044 mm track is therefore no longer presented as completed. See completion_results/REPORT.md for the five-case comparison. Provisional bifurcations still require review.
