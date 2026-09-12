# Battle of the Bots

CPU-only classical baseline for the Toralis BranchSeed challenge. The program
loads a CT and parent-aorta mask, proposes direct branch openings, traces their
proximal lumen, and writes the competition JSON. It does not use a trained
neural network or anatomical names.

## Setup

Tested with Python 3.13 on macOS. Use Python 3.13 on Linux for the evaluation
environment too. Create a virtual environment, then install the pinned packages:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Inference needs no internet, model download, API, or GPU. Install dependencies
before entering the offline environment. For offline installation, prepare
wheels on a machine matching the evaluation OS, architecture, and Python:

```bash
python -m pip download -r requirements.txt -d wheelhouse
python -m pip install --no-index --find-links wheelhouse -r requirements.txt
```

## Predict One Case

With the virtual environment activated:

```bash
python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json
```

For the supplied local dataset:

```bash
.venv/bin/python run.py \
  --image /Users/kevinhou/repos/toralis-challenge/toralis-dataset/subject001/orig1.nii \
  --aorta-mask /Users/kevinhou/repos/toralis-challenge/toralis-dataset/subject001/mask1.nii \
  --output outputs/subject001/prediction.json \
  --debug-dir outputs/subject001
```

Optional flags:

- `--case-id`: defaults to the image's parent directory name.
- `--debug-dir`: save stage overlays and projected branch inspection images.
- `--diagnostics`: save timing, configuration, candidate rejection reasons, and memory.
- `--min-radius-mm`: provisional minimum radius at the seed, default 0.8 mm.
- `--working-spacing-mm`: requested isotropic working resolution, default 0.8 mm.

`prediction.json` contains `case_id`, `parent`, and `daughters`, with the exact
required branch fields. Coordinates are physical LPS millimetres. Empty results
are valid JSON but are not proof that a scan contains no eligible branches.
Invalid inputs cause a nonzero exit status and an error, not a fabricated empty
prediction. Gzip-compressed files mislabeled `.nii` are handled automatically
through a temporary alias; the dataset is never rewritten.
For a sheared NIfTI affine rejected by SimpleITK's reader, a narrow nibabel
fallback preserves the exact file affine in LPS. The inference ROI is then
explicitly resampled to an orthogonal grid; source coordinates are not silently
replaced. This fallback is recorded in the diagnostics.

## Evaluate the Dataset

```bash
.venv/bin/python evaluate.py \
  --dataset /Users/kevinhou/repos/toralis-challenge/toralis-dataset \
  --output-dir outputs/development
```

This runs each case in a fresh process with four numerical-library threads,
validates every prediction, records runtime and peak resident memory, and saves
visualizations for the first three cases. It writes `evaluation.json` and one
prediction and diagnostics JSON per case. `--visualize-cases 25` draws all cases.

If organizer references become available in competition output format, supply
`--reference-dir PATH`, containing `<case_id>.json`. One-to-one matching reports
precision, recall, F1, ostium/seed errors, radius error, and direction error.
The default 5 mm matching gate (`--match-mm`) is a development proxy, not an
official scoring tolerance. No reference annotations were present in the
provided dataset, so accuracy cannot currently be reported.

## Method

1. Verify scalar 3D image/mask shape, spacing, origin, direction, finite CT data,
   and nonempty binary mask. Preserve SimpleITK geometry.
2. Crop to the aorta bounding box plus a physical margin. Resample this ROI only
   to an isotropic grid and construct a 12 mm external search shell.
3. Use robust aortic intensity statistics and multiscale Frangi vesselness to
   segment candidate lumen within the shell, with an upper intensity cap to
   reject extremely bright structures. Identify separate contact patches
   near the wall, and require a direct lumen connection to the parent mask.
4. Skeletonize the lumen together with the aorta, then exclude the parent from
   the graph. Trace candidates using SciPy graph routines. Ignore short spurs
   and stop at the first substantial downstream split or at 10 mm.
5. Smooth digital stair steps, require at least 5 mm of supported path, place
   the seed 5 mm along that path, estimate radius with a physical distance
   transform, and normalize the ostium-to-seed direction.
6. Reject terminal-cap contacts, disconnected or wall-hugging paths, invalid
   radii, and near-identical duplicate origins/paths. Serialize validated JSON.
7. Record interpretable candidate confidence evidence (contact quality,
   vesselness, path length, radius stability, and outward direction) in
   diagnostics. Low-confidence or failed primary traces receive a local,
   permissive adaptive-tracing retry within 14 mm of their aortic-wall contact;
   evaluator-facing JSON remains limited to accepted daughters.

The working grid is capped at 3 million voxels by adapting resolution. Geometry
is preserved through the ROI image, including direction and origin; fractional
coordinates use `TransformContinuousIndexToPhysicalPoint`. Integer conversion
is also available through `index_to_physical`, which uses
`TransformIndexToPhysicalPoint`. NumPy array indices are always ZYX.

Main files:

- `src/preprocessing.py`: input validation, geometry, cropping, surface and shell.
- `src/detection.py`: intensity/vesselness segmentation and wall-contact proposals.
- `src/tracing.py`: skeleton graphs, validation, geometry, duplicate suppression.
- `src/output.py`: competition schema validation and atomic JSON writes.
- `src/visualization.py`: orthogonal Phase 1 views and branch inspection images.
- `src/evaluation.py`: optional reference comparison.
- `src/types.py`: shared dataclasses and algorithm configuration.

Debug branch images use 12 mm maximum-intensity slabs. Yellow marks the ostium
and projected direction; cyan marks the proximal path and 5 mm seed; red is the
supplied aorta. Projection can superimpose structures at different depths, so
these images support inspection but do not establish true connectivity alone.

## Tests and Current Limits

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests include NIfTI round trips, mislabeled gzip inputs, anisotropic and rotated
geometry, physical shells, single/zero branches, nearby separate openings,
downstream-connected vessels, common trunks, short or disconnected vessels,
crop and intensity augmentation, curved-path seeds, and reference matching.

This is an uncalibrated baseline. Passing synthetic tests and producing valid
JSON do not establish clinical or competition accuracy. Important limitations:

- The organizer's minimum origin size is not yet specified. The 0.8 mm minimum
  and 6 mm maximum seed radii are engineering defaults, not official cutoffs.
- Threshold leakage into adjacent bright structures can create false positives;
  low contrast, small branches, and working-grid resampling can cause misses.
- Contact patches approximate true ostia. Openings joined very close to the wall
  can still merge, and fragmented patches can produce multiple proposals.
- A first bifurcation before 5 mm currently causes rejection because a 5 mm seed
  cannot be placed on the unsplit trunk under this tracing convention.
- Tangential branches may fail the outward-distance check. Crop-end rejection
  uses a mask principal-axis heuristic and needs evaluation on atypical coverage.
- Runtime and memory measured locally do not certify the organizer's hardware.

Learned classifiers are intentionally deferred until labeled branch references
exist. Geometric, crop, and intensity robustness checks are implemented without
training on invented labels. Further tuning should use aggregate reference
performance with held-out cases, not an expected branch count for any subject.
