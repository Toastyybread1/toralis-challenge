# Toralis Evaluate Case

## Purpose

Evaluate one Toralis BranchSeed case using the current project pipeline.

Use this skill when asked to evaluate, test, inspect, or debug a single case.

## Inputs

Expected inputs:

- CT image path
- aorta mask path
- optional reference JSON path
- optional output directory

Example:

image:
data/subject001/orig1.nii.gz

mask:
data/subject001/mask1.nii.gz

reference:
data/subject001/reference.json

output:
outputs/subject001/

## Workflow

1. Read AGENTS.md before doing anything.

2. Run the current prediction pipeline:

python run.py \
  --image <image_path> \
  --aorta-mask <mask_path> \
  --output <output_dir>/prediction.json

3. Measure:
- runtime
- whether the command completed successfully
- whether valid JSON was created

4. Validate the JSON schema.

Check:
- case_id exists
- parent.instance_id == "aorta"
- daughters is a list
- every daughter has a unique instance_id
- every daughter has parent_instance_id == "aorta"
- ostium_xyz_mm has 3 values
- seed_xyz_mm has 3 values
- radius_mm is numeric and positive
- direction_xyz has 3 values
- direction_xyz is approximately unit length

5. Report prediction summary:
- number of detected daughters
- each branch ID
- ostium
- seed
- radius
- direction

6. Generate debug visualizations.

At minimum show:
- CT slice with aorta mask overlay
- detected ostia
- daughter-direction arrows

If available, also visualize:
- search shell
- vesselness response
- branch candidates
- traced centerlines

Save visualizations into the case output directory.

7. Check important challenge cases.

Inspect for:
- false detections at superior/inferior crop ends
- two nearby ostia accidentally merged
- one common trunk accidentally split into multiple daughters
- daughter-of-daughter vessels incorrectly counted
- duplicate detections
- branches guessed outside scan coverage

8. If a reference JSON is provided, compare predictions against it.

Report:
- predicted branch count
- reference branch count
- likely matches
- likely false positives
- likely false negatives
- ostium distance for matched branches, in mm

Use one-to-one matching.

Do not match one prediction to multiple references.

9. Report likely failure causes.

Examples:
- threshold too strict
- threshold too loose
- vesselness missed small branch
- crop-end false positive
- candidate merged with nearby branch
- tracing failed before 5 mm
- duplicate suppression too aggressive
- direction estimate unstable
- radius estimate too large or too small

10. Do not automatically change code unless explicitly asked.

By default:
- evaluate
- visualize
- diagnose
- recommend next changes

Do not silently tune thresholds or modify algorithms.

## Final Report Format

Return:

### Case
<case id>

### Runtime
<seconds>

### Predictions
<count>

### Branches
- branch_001: ostium=..., radius=..., direction=...
- branch_002: ...

### Important-case checks
- crop-end false positive: yes/no
- nearby ostia merged: yes/no
- common trunk split: yes/no
- daughter-of-daughter counted: yes/no
- duplicates: yes/no

### Reference comparison
If reference exists:
- reference count
- matched count
- false positives
- false negatives
- mean ostium error
- max ostium error

### Likely issues
<short diagnosis>

### Recommended next step
<one or two concrete changes>