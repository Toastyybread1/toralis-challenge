# GUI / detection pipeline handoff

The pipeline team can work independently of Slicer. The interface needs two input
file paths and one JSON output file, matching the challenge brief.

## Command

```bash
python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json
```

- Support both `.nii` and `.nii.gz`.
- Use the supplied CT and parent-aorta mask without manual point placement.
- Write the result before exiting with code 0. Nonzero exit means failure.
- Standard output/error may contain progress and diagnostics.
- The GUI supplies an absolute temporary output path and runs the process with
  the script's directory as the working directory. The user chooses the Python
  executable (for example a virtual environment with SimpleITK installed).
- `case_id` must match the case ID shown when **Load study** was clicked.
  For the supplied dataset this is `subject001`, `subject002`, etc.
- The pipeline should complete all work before exiting and avoid detached child
  processes. The GUI cancels the launched process with terminate, then kill.

## JSON

```json
{
  "case_id": "subject001",
  "parent": { "instance_id": "aorta" },
  "daughters": [
    {
      "instance_id": "branch_001",
      "parent_instance_id": "aorta",
      "ostium_xyz_mm": [12.0, -30.0, 180.0],
      "seed_xyz_mm": [17.0, -30.0, 180.0],
      "radius_mm": 2.5,
      "direction_xyz": [1.0, 0.0, 0.0]
    }
  ]
}
```

These coordinates are illustrative, not annotations for subject001. Return an
empty `daughters` list when no eligible branches are found. Branch IDs must be
unique, all numbers finite, radii positive, and directions unit length. The GUI
accepts rounded unit vectors within 0.02 of unit length. Validation errors are
shown instead of silently repairing the team's predictions.

## Coordinates: the critical integration detail

The challenge requires **SimpleITK physical coordinates in millimetres**. Keep
those coordinates in the JSON. SimpleITK's physical anatomical convention is LPS
(left, posterior, superior), while Slicer uses RAS internally.

Only for display, the GUI converts both positions and direction vectors:

```python
ras = (-lps[0], -lps[1], lps[2])
```

Do not pre-flip the JSON into RAS, and do not export voxel indices. The exported
JSON retains the original LPS values. When deriving detections from arrays,
remember that `sitk.GetArrayFromImage(image)` is indexed `[z, y, x]`, while
`TransformIndexToPhysicalPoint` expects `(x, y, z)`.

For integer voxel indices:

```python
ostium_mm = image.TransformIndexToPhysicalPoint((int(x), int(y), int(z)))
```

For a subvoxel location, SimpleITK also provides
`TransformContinuousIndexToPhysicalPoint((float(x), float(y), float(z)))`.
Use the correct image geometry if the algorithm resamples the data; do not apply
the original image's index transform to resampled indices. Compute the physical
direction after incorporating spacing and orientation, then normalize it.

## What the GUI does

- Loads CT and mask and checks dimensions, spacing, origin, orientation and binary values.
- Renders the parent aorta as a translucent surface and slice overlay.
- Shows ostia and seeds as points, directions as arrows, and radii as rings.
- Synchronizes branch selection with slice centers.
- Keeps the original JSON available for inspection and export.
- Runs the team's executable without blocking Slicer's event loop.
- Clears old results when loading another case or starting a new detection.
- Rejects results for the wrong case.

## What the pipeline does

Find eligible direct daughters, estimate their ostia, follow the proximal paths,
locate the 5 mm seeds, estimate radii and directions, and write the output.
The GUI does not infer branches from the aorta mask. It also cannot verify
anatomical accuracy or the 5 mm path length from JSON alone; those need the team's
validation against reference annotations.

For the required visual checks, import genuine predictions for at least three
cases and save each workspace image. Use the synthetic example only to practice
the interface while real predictions are unavailable.
