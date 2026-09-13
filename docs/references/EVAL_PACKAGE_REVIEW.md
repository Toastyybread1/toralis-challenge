# Evaluation package review

The user confirms that EVAL_SET was supplied by the organisers. Treat it as the authoritative project reference for implementation and evaluation. Its embedded draft/review-pending flags and unresolved fields remain part of that reference; they do not justify disregarding its supplied branch labels. All 55 manifest file hashes and sizes match; ZIP CRC checks pass. All five CT and parent-mask pairs are byte-identical to existing subjects 019–023. This review therefore compares existing unchanged submission_results predictions; inference was not rerun and the detector was not tuned.

## File meanings

- orig*.nii.gz: CT input.
- aorta*.nii.gz: parent-only input mask.
- daughters*_draft.nii.gz: proposed daughter labels, 0 background and 1..N separate branches.
- aorta_and_daughters*_draft.nii.gz: viewing overlay, 1 parent and 2..N+1 daughters. Do not pass this as the parent mask.
- annotations.json: draft origins, seeds, directions, approximate measurements and review status.
- tracing_guides.json: approximate tracing guides, not adjudicated centrelines.
- review_notes.md, excluded_candidate.json and REVIEWER_CHECKLIST.md: unresolved anatomy and review priorities.

Physical coordinates are SimpleITK LPS millimetres. Voxel guides use XYZ, whereas NumPy arrays use ZYX. A null radius is unresolved, not zero. The 2 mm eligibility threshold refers to origin diameter, not seed radius. Sixteen of 19 radii are null; the other three are approximate threshold estimates. All guides are recorded as 10 mm, but this does not prove anatomical continuity or absence of earlier bifurcation.

## Existing detector versus drafts

Matching is one-to-one by physical ostium distance, not branch ID. A 3 mm tolerance below is illustrative, not an organiser-approved scoring rule.

| Case | Draft branches | Predictions | Matches within 3 mm |
|---|---:|---:|---:|
| 19 | 3 | 0 | 0 |
| 20 | 4 | 1 | 0 |
| 21 | 3 | 4 | 2 |
| 22 | 6 | 3 | 3 |
| 23 | 3 | 0 | 0 |
| Total | 19 | 8 | 5 |

At 2/3/5 mm tolerances there are respectively 4/5/6 matches. Case 20's prediction is 3.53 mm from one draft origin. At 3 mm, 14 draft branches and 3 predictions remain unmatched. Against the supplied organiser labels, these are 14 false negatives and 3 false positives at the illustrative 3 mm tolerance. This is a local comparison against the authoritative package, not an official score: the matching tolerance has not been established as organiser policy. Optional null measurements were omitted in memory for comparison, without changing source annotations.

## What to investigate first

1. Inspect case 19 at each draft ostium and seed with the detector's accepted-intensity mask, expansion and contact candidates. It has four contact patches, all rejected: two no outgoing volume, one minimum diameter, one terminal cap. These aggregate reasons do not establish which stage lost each draft branch.
2. Record a per-reference stage audit: intensity accepted, connected to parent, survives component blocking, contact generated, tracking survives, final output. This separates failure to generate a candidate from rejection of a generated candidate.
3. Review case 23: three patches fail outgoing-volume support and two have unbounded origin sections. Its two posterior draft branches are themselves low-confidence, with uncertain separate origins and minimum diameter.
4. Count unmatched predictions in case 21 as false positives against the supplied labels for this comparison. Preserve the package's unresolved-anatomy notes when diagnosing those disagreements; do not add reference branches ourselves.
5. Follow the organiser's supplied origin boundaries, eligibility rules and branch instances. Do not invent values for null radii or override unresolved early-bifurcation conventions. Report performance against the supplied labels with the matching rule stated explicitly. Keep this baseline frozen while reviewing. If these cases are used for tuning, reserve other cases for independent evaluation.

The five scans have 1.5 mm isotropic voxels: a 2 mm origin spans only about 1.33 voxels. Borderline diameter and connectivity are therefore sensitive to partial volume and thresholding; interpolation cannot restore missing resolution. This also differs from the submillimetre slice-thickness requirement described in the supplied Tahoces paper. Global intensity modelling is a plausible failure source, especially for small partial-volume branches, but requires the stage audit before changing thresholds.

Detailed per-case distances and review notes: eval_package_review/comparison.json.
