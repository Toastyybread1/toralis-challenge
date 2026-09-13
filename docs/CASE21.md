# Case 21: what the three unmatched groups mean

Update: the [aortic-backbone review](../results/aortic_tree_verified/REPORT.md)
now defers `candidate_0013`: its extracted route returns to the backbone without
an outgoing arm. The counted set has three draft matches and two extras; the
deferred candidate remains visible and anatomically unresolved. The descriptions
below document the original six-group set, which is preserved in the outputs.

All three retained draft branches are already matched. The issue is three
additional provisional groups, not three missing known branches. The organizer
notes explicitly say this case is not certified exhaustive. No anatomical labels
were changed to make the score look better.

Coordinates below are zero-based native voxel indices in XYZ order; calculations
and exported paths use physical LPS millimetres.

| Candidate | Origin XYZ | Evidence | Current disposition |
|---|---|---|---|
| candidate_0002 | 92.04, 131.08, 146.50 | A bright path follows a vessel close to the wall; its 5–10 mm interval stays about 2.3–3.0 mm from the parent. This is consistent with the region of the looping vessel the organizers withheld near [92,130,143] and [93,134,158]. Neural score is high (0.96), but that does not prove an independent aortic origin. | Keep unresolved; determine whether apparent contact is an ostium, partial-volume bridge, or a vessel arising elsewhere. |
| candidate_0013 | 96.86, 116.50, 194.29 | Thin posterior path goes approximately along the aorta toward the upper coverage. Its distal interval stays about 3.0–3.5 mm from the parent. The origin diameter proxy is 3.09 mm, but distal section diameters fall to about 1.69 mm. Those distal measurements do not themselves prove the ostium fails the 2 mm rule. | Keep unresolved; inspect direct continuity and diameter in orthogonal planes. It must not be declared false simply because it is absent from the draft. |
| candidate_0019 | 109.96, 124.50, 135.88 | Approximately 2.07 mm above the inferior parent-cell cap proxy; origin diameter proxy 1.81 mm. This coincides with the organizer's uncertain posterior region near [110,123,136], with inferior mask cap at z135. | Keep unresolved; the true origin may be at/below the supplied coverage and minimum diameter is uncertain. |

## What the code now does

The same `origin_triage.py` logic runs on every case and uses CT/parent/path data,
not organizer notes or case-specific coordinates. It adds review evidence for:

- proximity within two native voxels of a supplied-parent end proxy;
- a genuinely traced distal interval of a roughly 10 mm path that remains within
  4 mm of the parent with little distance variation;
- already-recorded diameter uncertainty.

These are **review flags, not automatic exclusions**. A real daughter may run
parallel to the aorta. The end proxy uses the longest grid axis, not a fitted
anatomical cap plane. The parent distance field is centre-based. Do not interpret
these values as clinical diagnoses or exact subvoxel wall distances.

Every one of case 21's six group representatives has a montage with five
consecutive slices in all three planes in the all-case review workspace. Cyan is
the supplied parent cell boundary, yellow is draft label outline, red is the
predicted origin, and magenta marks the path only where it crosses that slice.
A border or path being absent from one displayed plane is not absence in 3D.

## What would resolve this

Review the full CT and parent overlay, trace both directions from the suspicious
contact, and establish one visible direct wall opening. Measure the origin on an
appropriate perpendicular plane; preserve uncertainty near the native resolution.
For the inferior candidate, inspect whether that opening is actually inside the
supplied parent coverage. Then record accept/edit/exclude/unresolved in a new
review version. No expert sign-off or ITK-SNAP inspection was performed here.

The raw development metric remains **3 matches + 3 unmatched groups** for case 21.
The whole five-case metric remains 18/19 matches with 3 unmatched groups. This
investigation explains and flags the failure modes; it does not pretend the
anatomy has been conclusively solved.
