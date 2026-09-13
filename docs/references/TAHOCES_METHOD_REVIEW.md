# Tahoces paper: verified methods and adaptation plan

Source: user-provided s11517-019-02110-x.pdf, Tahoces et al., Medical & Biological
Engineering & Computing 58 (2020), 903-919. Relevant full pages and figures were
extracted and visually inspected. No inference algorithm was changed here.
This supersedes the earlier abstract-only Tahoces comparison in PROJECT_REVIEW.
The Riffaud full method has still not been reviewed.

## Verified branch algorithm

Section 2.1, printed pp. 905-907 (PDF pages 3-5), Figs. 3-7:

1. Input comprises CT, a parent-only aorta segmentation, aortic centreline,
   orthogonal cross-sections, and intensity probability distributions inside
   and around the lumen. Figure 3 identifies KDE distributions. These come
   from earlier segmentation/density-estimation work (references 2, 3 and 28).
2. Expand the aorta into connected regions compatible with blood intensities.
   First expansion is limited to 20 mm from the original segmentation.
3. Identify excessive expansions as wrong branches (the heart is an example);
   discard tiny isolated additions. Repeat with a larger distance limit while
   excluding the regions marked as wrong expansions.
4. Subtract the original mask from the expanded volume to obtain branches.
5. Find branch voxels neighbouring the parent as contact regions. Select the
   contact voxel with the greatest distance to the branch edge, rather than
   a centroid. Map each contact to the nearest aortic centreline point.
6. Group and label major supra-aortic and visceral branches using anatomical
   order, direction, diameter and volume. The visceral rules discard branches
   directed toward the feet or back; these are not suitable universal rules
   for our all-eligible-daughters challenge.

The described branch stage does not use our Frangi filter or our bounded
Dijkstra tracer. Two-phase volume expansion is not equivalent to merely
computing a geometric shell. Our 20 mm crop margin is not its 20 mm expansion.

## Mapping to current code

| Paper step | Current implementation | Decision |
|---|---|---|
| CT + parent-only mask | utils.py and run.py | Reuse |
| Aortic centreline/cross-sections | Absent | Needed for faithful pipeline; not necessary for initial growth experiment |
| Inside/outside density models | Global inside median/MAD only | Add exterior/background comparison; an adaptation unless referenced estimator is reproduced |
| Two-phase intensity expansion | Absent | Main algorithmic difference; prototype separately |
| Expansion leakage/volume rejection | Absent | Must accompany growth diagnostics |
| Expanded-minus-parent branches | Thresholded contact patches instead | Obtain actual proximal candidate volumes before locating contacts |
| Contact maximum edge-distance | Score-weighted centroid representative | Replace only after candidate volume geometry is available |
| Anatomical naming/direction pruning | Absent | Intentionally omit for challenge scope |
| Required 5 mm seed/radius | Not the paper's challenge output | Separate development and validation still required |

## What must not be copied blindly

- Fixed named artery groups and directional exclusions can remove eligible
  daughters. Partial abdomen scans may not contain the supra-aortic reference
  group or the left subclavian artery used in the paper's grouping logic.
- The paper's first expansion distance is not a path length or vessel radius.
- Selecting a contact point near the centre of the segmented opening does not
  by itself deliver the challenge's seed 5 mm along a daughter centreline.
- Large-volume rejection may confuse a genuine common trunk with leakage;
  evaluate it on local proximal geometry and preserve distinct wall contacts.
- A naive 3D distance transform of the detached branch treats its cut contact
  face as background. That can bias all contact distances toward the cut face.
  The paper does not fully specify this implementation detail; define and test
  whether opening-plane or side-wall distance is used before copying the rule.

## Missing reproduction details

The branch description does not supply an executable probability acceptance
rule, exact voxel-neighbour connectivity, numerical small/large added-volume
thresholds, or the second expansion distance. It also refers to a learned
subclavian-to-visceral separation threshold without providing its value here.
The referenced density-estimation method needs separate reading for a faithful
implementation. Any choices made now must be recorded as adaptation parameters,
not attributed to the paper. Some geometric pruning is intentionally out of scope.

## Dataset, results and limits

Section 2.4 (p. 911): 63 contrast CT scans, 33 for development and 30 for testing.
Selection required slice thickness below 1 mm and visibility of aortic root and
supra-aortic arteries; mean thickness was 0.625 mm. Our approximately 1.5 mm
cases differ materially. Test-set entry additionally required the celiac trunk.

Table 1 (p. 913): 168 TP, 15 FN, 2 FP across named branches; total recall 91.8%,
precision 98.8%. For the four visceral categories alone, the table gives
79 TP, 14 FN, 2 FP: pooled recall 79/93=84.95%, precision 79/81=97.53%
(our calculation, not a separately reported metric). Right renal recall is
73.7%. These are named-branch results, not all-daughter ostium matching.

The conclusion on p. 917 states 95%/100%, inconsistent with Table 1 and the
abstract. Prefer the explicit table counts; do not silently mix these values.
The aortic-root localization error is not daughter-ostium localization error.

Section 3 (p. 912): C++ implementation under 30 s, excluding disk image loading,
on an i7-4790 3.6 GHz with 16 GB RAM. This is not directly comparable to our
incomplete Python pipeline's local wall times or a four-core/8-GB guarantee.

## Next bounded experiment, before replacing anything

Preserve the current baseline. First establish a documented growth model using
inside and nearby outside intensity samples. Then implement a diagnostic,
distance-bounded connected expansion from the supplied parent. Save the added
volume and per-component contact/volume statistics, including where growth
hits its bound. Do not emit final daughters or silently delete large regions.

Test a connected tube, disconnected equally bright object, leakage into a large
region, common trunk, neighbouring openings and a cropped parent continuation.
Compare overlays on 001, 006, 016, 018 and 024 and use reference annotations or
expert assessment before choosing expansion rejection thresholds. Once this
works, add the second phase and centre-of-opening refinement one at a time.
