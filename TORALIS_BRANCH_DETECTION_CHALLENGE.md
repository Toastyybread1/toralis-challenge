# Toralis Labs BranchSeed Challenge

## Project Goal

We are building a CPU-only system for the Toralis Labs vascular branch-detection challenge.

For each unseen case, the program receives:

- a 3D CT angiography volume
- a binary mask containing only the parent abdominal aorta

The task is to automatically detect every eligible artery that directly branches from the supplied aorta.

The daughter arteries are visible in the CT image but are NOT included in the supplied aorta mask.

Do NOT assign anatomical names.

Use generic IDs like:

- branch_001
- branch_002
- branch_003

The challenge is not asking us to reconstruct the full vascular tree.

The challenge is specifically asking us to find all direct daughter arteries leaving the supplied parent aorta.

---

# Core Mental Model

Think of the aorta as a tree trunk.

The supplied binary mask tells us exactly where the trunk is.

Our job is to find every real branch that directly leaves that trunk.

The most important object is the opening where a branch leaves the aorta.

This opening is called the ostium.

A useful interpretation is:

CT + known aorta
    ↓
find distinct vessel openings in the aortic wall
    ↓
trace each opening outward
    ↓
verify it behaves like a real vessel
    ↓
return one daughter instance per direct aortic origin

This challenge is NOT:

"find every artery near the aorta"

It IS:

"find every distinct artery that directly connects to the supplied aortic lumen"

---

# Input Data

Each case contains:

- a CT volume, stored as NIfTI
- a binary parent-aorta mask, stored as NIfTI

Example:

data/
  subject001/
    orig1.nii
    mask1.nii

  subject002/
    orig2.nii
    mask2.nii

The CT and mask use the same image grid and physical coordinate system.

The aorta mask contains:

- 1 = inside the parent aortic lumen
- 0 = everything else

The daughter arteries are visible in the CT but are not labeled in the supplied mask.

Anatomical coverage varies between cases.

Some cases may contain a shorter or longer section of the aorta.

Therefore the number of visible daughter branches varies.

---

# Development vs Hidden Evaluation

A small development subset may contain example reference outputs.

Use these cases to:

- understand the expected output
- tune thresholds
- evaluate candidate detection
- inspect false positives
- inspect false negatives
- test robustness

The final evaluation cases will have hidden reference annotations.

The system must generalize to previously unseen cases.

Do not make case-specific edits.

Do not hard-code expected branch locations.

Do not hard-code a fixed number of branches.

---

# Required Output

Produce one JSON file per case.

Example structure:

{
  "case_id": "subject001",
  "parent": {
    "instance_id": "aorta"
  },
  "daughters": [
    {
      "instance_id": "branch_001",
      "parent_instance_id": "aorta",
      "ostium_xyz_mm": [12.4, -31.8, 184.6],
      "seed_xyz_mm": [15.1, -29.7, 181.2],
      "radius_mm": 2.7,
      "direction_xyz": [0.56, 0.43, -0.71]
    }
  ]
}

If no eligible daughter is visible:

{
  "case_id": "...",
  "parent": {
    "instance_id": "aorta"
  },
  "daughters": []
}

---

# Required Meaning of Each Output Field

## instance_id

Each detected daughter must have a unique ID.

Examples:

branch_001
branch_002
branch_003

Do not use anatomical names.

## parent_instance_id

Must always be:

"aorta"

for every direct daughter.

## ostium_xyz_mm

The center of the opening where the daughter artery directly leaves the parent aorta.

This must be reported in physical millimetres.

Do NOT output voxel indices.

## seed_xyz_mm

A point at the center of the daughter lumen approximately 5 mm outward from the ostium along the daughter path.

This must be reported in physical millimetres.

## radius_mm

Estimate of the local daughter-vessel lumen radius at the daughter seed.

Report in millimetres.

## direction_xyz

A unit vector pointing from the ostium into the daughter vessel.

The vector should represent the initial proximal branch direction.

---

# Physical Coordinates

This is critical.

The output coordinates must be in the physical coordinate system of the input image.

Do NOT output raw NumPy voxel indices.

Use SimpleITK image geometry.

When converting voxel locations to physical coordinates, use something equivalent to:

SimpleITK.TransformIndexToPhysicalPoint(...)

The implementation must preserve:

- spacing
- origin
- direction matrix

Do not assume isotropic voxels.

Do not assume voxel coordinates equal millimetres.

---

# Eligibility Rules

A branch counts when:

- its lumen directly connects to the supplied parent aorta
- the contrast-filled lumen can be followed for at least approximately 5 mm beyond the aortic wall
- its origin meets the minimum size requirement specified by the organizers

For each eligible daughter:

- trace the proximal branch up to approximately 10 mm beyond the ostium
- or stop earlier at the first downstream bifurcation

Use this proximal path to estimate:

- daughter seed
- local radius
- initial direction

---

# CRITICAL IMPORTANT CASES

These rules come directly from the challenge and must strongly influence the algorithm.

These are not minor edge cases.

They are core correctness requirements.

---

## 1. Variable Scan Coverage

The supplied aorta may be short or long.

Therefore:

- do NOT assume a fixed number of branches
- do NOT assume every anatomical branch appears in every case
- do NOT assume fixed branch positions
- do NOT assume a standard anatomy is fully present
- only detect branches actually visible in the supplied scan

The output may contain:

- zero branches
- one branch
- several branches

depending on scan coverage.

The algorithm must detect a variable number of daughter instances automatically.

---

## 2. Cropped Superior and Inferior Ends Are NOT Branches

The top and bottom ends of the supplied aortic segment may appear flat because the CT or mask was cropped.

These flat ends are NOT daughter-vessel origins.

The detector must explicitly avoid treating crop boundaries as ostia.

Possible implementation ideas:

- identify the superior and inferior terminal surfaces of the aorta
- exclude candidate origins too close to those flat ends
- detect whether a candidate exits the image volume instead of entering a daughter vessel
- penalize candidates whose apparent continuation points outside scan coverage

This is a major false-positive risk.

---

## 3. Two Nearby Origins Must Stay Separate

Two daughter arteries may originate very close to each other.

If they have separate openings at the aortic wall, they count as TWO separate daughter instances.

Do not merge them simply because:

- their masks touch
- their vesselness responses overlap
- their downstream paths become close
- they form one connected component outside the aorta

Branch identity should be based primarily on distinct ostial openings at the aortic wall.

One connected component may contain multiple valid direct daughter branches.

Connected-component labeling alone is not sufficient to determine branch count.

---

## 4. A Common Trunk Counts as ONE Daughter

If one vessel directly leaves the aorta and then splits shortly afterward:

AORTA ---- trunk ----<
                      \
                       \

this counts as ONE direct aortic daughter.

Do not return the downstream split as multiple direct daughters.

The algorithm should count distinct aortic origins, not downstream branches.

Trace the branch from the ostium outward and stop at the first downstream bifurcation when estimating proximal branch geometry.

---

## 5. Daughter-of-Daughter Vessels Do NOT Count

Example:

AORTA ---- branch A ---- branch B

Only branch A is a direct daughter.

Branch B does NOT count because it does not directly originate from the aorta.

Every predicted daughter must have direct physical connectivity to the supplied aortic wall.

Downstream branches discovered during tracing must not be reported as independent direct aortic daughters.

---

## 6. Never Guess Missing Anatomy

If a vessel is:

- absent from the image
- outside scan coverage
- not visible
- cropped out

do NOT predict it.

Do not use expected anatomy to fill in missing arteries.

The task is branch discovery from image evidence, not anatomical completion.

Only visible evidence should generate a prediction.

---

## 7. Iliac Terminal Division Is Outside the Core Task

The terminal division of the aorta into the iliac arteries is outside the main challenge.

Do not treat the iliac terminal bifurcation as a standard daughter branch unless implementing the optional extension.

The core algorithm should focus on branches arising from the supplied abdominal aortic segment.

---

# Highest-Priority Interpretation Rule

Count DIRECT AORTIC OSTIA.

Do not count downstream vessel branches.

A prediction should correspond to exactly one distinct opening in the supplied aortic wall.

The conceptual pipeline should be:

aorta wall
    ↓
find distinct vessel openings
    ↓
trace outward
    ↓
verify at least ~5 mm of daughter lumen
    ↓
one opening = one daughter instance

---

# Evaluation Priorities

The challenge scoring strongly prioritizes branch discovery.

Priority order:

1. Branch discovery
2. Ostium localization
3. Daughter-instance quality
4. Compute efficiency
5. Reproducibility

Approximate scoring emphasis:

- Branch discovery: 45%
- Ostium localization: 25%
- Daughter-instance quality: 15%
- Compute efficiency: 10%
- Reproducibility: 5%

This means:

Finding the correct number of branches is more important than perfectly estimating radius.

The detector should initially optimize for strong branch recall while controlling false positives.

Duplicate predictions are especially harmful because predictions are matched one-to-one against references.

---

# Runtime / Hardware Constraints

The hidden evaluation environment is CPU-only.

Assume:

- 4 CPU cores
- 8 GB RAM
- no GPU
- no internet access
- target approximately <= 60 seconds per case

The system must run on a standard laptop.

Do not make the core pipeline depend on:

- CUDA
- GPUs
- cloud APIs
- online model downloads
- external services
- internet access

All required dependencies and models must be available locally.

---

# Required Command-Line Interface

The program must support a terminal command like:

python run.py \
  --image image.nii.gz \
  --aorta-mask aorta_mask.nii.gz \
  --output prediction.json

The frontend, if any, is optional.

The core prediction pipeline must work independently from the frontend.

The judges should be able to run the algorithm directly from the command line.

---

# Recommended Baseline Algorithm

Do NOT begin with deep learning.

Start with a classical, CPU-friendly, aorta-guided detection pipeline.

The supplied aorta mask is a very strong prior.

Use it aggressively.

---

## Overall Pipeline

CT volume
+
aorta mask
    ↓
load with SimpleITK
    ↓
validate geometry
    ↓
extract aortic surface
    ↓
create thin search shell around the aortic wall
    ↓
analyze CT intensity inside shell
    ↓
apply vesselness / tubular enhancement
    ↓
generate candidate structures touching aorta
    ↓
identify distinct ostial openings
    ↓
trace each candidate outward
    ↓
reject candidates that do not persist >= ~5 mm
    ↓
estimate proximal centerline
    ↓
compute ostium
    ↓
compute seed
    ↓
estimate radius
    ↓
estimate direction
    ↓
remove duplicates / enforce important-case rules
    ↓
convert to physical coordinates
    ↓
write JSON

---

# Key Algorithmic Principle

Do not search the entire abdomen.

Use the supplied aorta mask as a spatial anchor.

Construct a narrow region around the aorta and search only there for direct daughter origins.

This greatly reduces:

- search space
- false positives
- runtime
- memory usage

---

# Step 1: Load Data

Use SimpleITK.

Load:

- CT image
- aorta mask

Verify:

- same size
- same spacing
- same origin
- same direction
- compatible physical coordinate systems

Extract NumPy arrays only after preserving the image metadata.

Keep the SimpleITK image object available for coordinate conversion.

---

# Step 2: Aorta Surface

Compute the boundary of the supplied aorta mask.

Possible methods:

- binary erosion
- surface = mask XOR eroded_mask

or equivalent morphology.

The aortic surface is where direct daughter ostia must occur.

---

# Step 3: Search Shell

Create a narrow search shell around the aortic wall.

Example:

- dilate aorta mask outward by approximately 5–10 mm
- subtract the original aorta mask

Conceptually:

expanded_aorta - original_aorta = outer search shell

The shell should be defined in millimetres, not arbitrary voxel counts.

Use image spacing when converting desired distances to morphology parameters.

Possible shell thickness to test:

- 5 mm
- 8 mm
- 10 mm

Tune using development cases.

---

# Step 4: Vessel Enhancement

Inside the search region, identify bright tubular structures.

Possible filters:

- Frangi vesselness
- Sato vesselness
- Hessian-based vessel enhancement

The purpose of vesselness is to identify voxels that look tube-like.

Do not rely only on vesselness.

Combine vesselness with CT intensity.

Contrast-filled arteries should generally appear bright compared with nearby soft tissue.

---

# Step 5: Adaptive Intensity Thresholding

Avoid using one fixed CT threshold for all patients if possible.

Contrast level may vary across scans.

Use the supplied aorta as an intensity reference.

Possible statistics:

- median CT value inside the aortic lumen
- mean CT value inside the aortic lumen
- lower percentile inside aorta
- local vessel-to-background contrast

Then define a candidate threshold relative to the aorta.

Example concept:

aorta_median = median(CT values inside aorta)

candidate voxels = voxels that are:

- sufficiently bright relative to aorta intensity
- sufficiently vessel-like
- located in the search shell

Tune this on development cases.

Do not hard-code assumptions without testing.

---

# Step 6: Generate Branch Candidates

Candidate structures should:

- lie near the aorta
- directly contact or emerge from the aortic boundary
- have vessel-like appearance
- be sufficiently bright
- extend outward from the aorta

Connected components can help generate candidate regions.

However:

IMPORTANT:
Connected components are NOT equivalent to daughter instances.

One component may contain:

- two nearby true ostia
- one common trunk that later bifurcates
- vessel structures that touch downstream

The final branch identity must be based on direct aortic origins.

---

# Step 7: Identify Ostial Openings

For each candidate structure:

find where it directly intersects or contacts the aortic wall.

The goal is to estimate the center of the daughter opening.

This point becomes the ostium candidate.

Nearby contact regions may need to be separated if they represent distinct openings.

Possible strategies:

- connected components on the aorta-contact surface
- clustering of contact voxels
- geodesic separation along the aortic surface
- local morphology
- local center-of-mass calculation

This is one of the most important parts of the algorithm.

---

# Step 8: Trace Candidate Outward

Starting from an ostium candidate:

trace the suspected daughter vessel outward from the aorta.

The candidate must remain consistent with a vessel for approximately 5 mm.

Reject candidates that:

- terminate almost immediately
- are isolated bright noise
- represent artifacts
- represent crop boundaries
- fail to form a plausible tubular path

Possible tracing approaches:

- skeletonization
- graph search
- region growing
- local intensity tracking
- vesselness-guided path search
- shortest-path / minimum-cost path

Prefer lightweight CPU-compatible methods.

---

# Step 9: Proximal Centerline

For a valid daughter candidate:

estimate a short proximal centerline.

Only the first approximately 10 mm is needed.

Stop earlier if the first downstream bifurcation occurs.

This proximal centerline is used to compute:

- seed
- direction
- radius

Do not reconstruct the full distal vascular tree.

---

# Step 10: Daughter Seed

The daughter seed should be approximately 5 mm outward from the ostium along the daughter path.

Walk along the estimated centerline using physical distance.

Do not assume five voxels equals 5 mm.

Use voxel spacing.

---

# Step 11: Direction

Estimate the initial daughter direction from the proximal centerline.

A simple baseline:

direction = seed_position - ostium_position

Normalize:

direction = direction / ||direction||

Output:

[x, y, z]

The vector must point from the aorta into the daughter vessel.

A better estimate may average several proximal centerline points to reduce noise.

---

# Step 12: Radius

Estimate local lumen radius at the daughter seed.

Possible baseline:

- segment local daughter lumen
- compute Euclidean distance transform
- radius ≈ distance from centerline seed to vessel boundary

Report in millimetres.

The radius estimate does not need to be perfect in the first baseline.

Branch discovery and ostium accuracy are higher priority.

---

# Step 13: Duplicate Removal

Each real direct daughter should appear once.

Duplicates count as false positives.

Possible duplicate logic:

- compare ostium distance in physical mm
- compare proximal direction
- compare overlap of traced paths
- merge highly similar detections that originate from the same ostium

BUT:

Do not accidentally merge two separate nearby ostia.

The aortic wall opening should be the primary identity criterion.

---

# Step 14: Crop-End Filtering

Explicitly detect the superior and inferior ends of the supplied aorta.

Reject candidates that originate from those flat cropped surfaces unless there is strong evidence of a true lateral daughter opening.

This should be implemented as a dedicated rule, not left to chance.

---

# Suggested Libraries

Prefer:

- SimpleITK
- NumPy
- SciPy
- scikit-image
- matplotlib
- scikit-learn only if needed later

Potential utilities:

SimpleITK:
- NIfTI loading
- image geometry
- physical coordinate conversion

NumPy:
- array operations

SciPy:
- morphology
- distance transforms
- connected components

scikit-image:
- Frangi
- Sato
- Hessian filters
- skeletonization
- morphology
- measure / labeling

matplotlib:
- debug visualizations

scikit-learn:
- optional later-stage lightweight classifier

---

# Avoid Initially

Do not start with:

- 3D U-Net
- nnU-Net
- transformers
- large CNNs
- GPU training
- cloud inference
- LLM-based image interpretation

We have:

- small development data
- CPU-only evaluation
- limited RAM
- runtime constraints

Start with classical methods.

---

# Optional Lightweight Machine Learning

Only add ML after the classical baseline works.

A useful role for ML:

classify candidate branches as:

- real direct daughter
- false positive

Possible models:

- Logistic Regression
- Random Forest
- Gradient Boosting

Potential candidate features:

- mean CT intensity
- max CT intensity
- contrast relative to aorta
- mean vesselness
- max vesselness
- component size
- physical length
- estimated radius
- contact area with aorta
- tubularness
- direction
- distance from crop ends
- persistence beyond 5 mm
- local background intensity
- ostium shape features

Train the classifier on candidate-level feature vectors.

Do NOT train a giant model on whole 3D CTs as the first approach.

---

# Data Augmentation

Augmentation should be added only after the baseline detection pipeline works.

Possible uses:

- robustness testing
- threshold tuning
- lightweight classifier training

---

## Geometric Augmentation

Possible transforms:

- small rotations
- small translations
- small scaling
- mild deformation

If transforming labeled data, transform consistently:

- CT
- aorta mask
- ostium coordinates
- seed coordinates
- branch directions
- radius if scaling is applied

Keep transformations anatomically reasonable.

Avoid extreme warping.

---

## Intensity Augmentation

Possible variations:

- contrast scaling
- brightness shift
- mild Gaussian noise
- mild blur

Goal:

make the detector less dependent on one exact CTA intensity distribution.

---

## Crop Augmentation

This is especially relevant because the challenge includes variable scan coverage.

Take a case and crop:

- superior section
- inferior section
- both

Use this to test whether the detector:

- still detects visible daughters
- does not hallucinate missing branches
- does not mistake crop boundaries for ostia

---

## Synthetic Branch Geometry

Optional advanced augmentation.

Generate simplified synthetic vessel structures with:

- random branch radius
- random branch angle
- random branch position
- random branch count
- nearby separate ostia
- common trunks
- branches close to crop boundaries

Use these primarily for stress testing.

Do not rely on unrealistic synthetic anatomy as the sole training distribution.

---

# Stress Tests Derived From Important Cases

Build targeted tests for the challenge rules.

---

## Stress Test A: Variable Branch Count

Cases should contain:

- 0 branches
- 1 branch
- multiple branches

The detector must not assume a fixed number.

---

## Stress Test B: Crop Boundaries

Crop the aorta close to a flat superior or inferior end.

Expected:

- no false branch prediction from the crop surface

---

## Stress Test C: Nearby Ostia

Create or identify two close but separate daughter origins.

Expected:

- two branch instances

---

## Stress Test D: Common Trunk

One direct daughter leaves the aorta and splits downstream.

Expected:

- one direct daughter

---

## Stress Test E: Daughter-of-Daughter

One direct daughter produces another branch downstream.

Expected:

- report only the direct daughter

---

## Stress Test F: Missing Anatomy

Crop away a known branch.

Expected:

- do not predict it

---

# Visual Verification Requirement

Provide simple visual checks for at least three cases.

The visualization should show:

- aorta mask
- detected ostia
- daughter direction arrows

An elaborate clinical frontend is not required.

Useful debug visualizations:

- axial slice with aorta overlay
- coronal slice
- sagittal slice
- search shell
- vesselness map
- candidate regions
- detected ostia
- traced daughter centerlines
- direction vectors

A simple matplotlib or lightweight Streamlit visualization is enough.

---

# Recommended Project Structure

toralis-branchseed/

  AGENTS.md

  run.py

  requirements.txt

  README.md

  data/
    subject001/
      image.nii.gz
      aorta_mask.nii.gz

  src/
    __init__.py
    types.py
    preprocessing.py
    detection.py
    tracing.py
    output.py
    visualization.py

  tests/
    test_preprocessing.py
    test_detection.py
    test_output.py

  outputs/

  docs/
    branchseedchallenge.pdf

---

# Shared Data Structures

Use clear interfaces between modules.

Example:

from dataclasses import dataclass
import numpy as np

@dataclass
class CandidateBranch:
    voxels: np.ndarray
    contact_voxels: np.ndarray
    score: float

@dataclass
class DetectedBranch:
    ostium_index: np.ndarray
    seed_index: np.ndarray
    radius_mm: float
    direction_xyz: np.ndarray

These structures can evolve as needed.

Keep module boundaries clean.

---

# Team Split

We have three developers.

Split work by clear interfaces.

---

## Person 1 — Preprocessing, Geometry, Visualization

Own:

- NIfTI loading
- SimpleITK metadata
- coordinate conversion
- spacing / origin / direction
- aorta surface
- search shell
- debug visualization

Expected functions:

load_case(...)
validate_geometry(...)
extract_aorta_surface(...)
make_search_shell(...)
index_to_physical(...)
physical_to_index(...)
show_case(...)
show_candidates(...)

Deliverable:

A reliable preprocessing module that provides:

- CT array
- aorta mask array
- search shell
- image spacing
- image metadata
- physical-coordinate conversion

---

## Person 2 — Candidate Detection

Own:

- vesselness
- intensity thresholding
- connected components
- candidate generation
- ostium-contact region proposal
- maximize branch recall

Expected function:

detect_candidates(...) -> list[CandidateBranch]

Focus:

find nearly every plausible real branch, even if some false positives remain initially.

Because branch discovery is the highest-weight scoring category.

Test:

- Frangi
- Sato
- Hessian vessel filters
- adaptive CT thresholding
- aortic contact filtering
- component-size filtering

Do not hard-code anatomy.

---

## Person 3 — Tracing, Validation, Final Output

Own:

- candidate tracing
- skeletonization
- centerline estimation
- 5 mm persistence validation
- ostium
- seed
- direction
- radius
- duplicate removal
- important-case logic
- JSON generation

Expected functions:

trace_candidate(...)
validate_candidate(...)
estimate_ostium(...)
estimate_seed(...)
estimate_direction(...)
estimate_radius(...)
deduplicate_branches(...)
write_prediction_json(...)

This person should implement:

- nearby-origin separation
- common-trunk handling
- daughter-of-daughter rejection
- crop-end rejection
- duplicate suppression

---

# Integration Contract

Person 2 should return a clean candidate list.

Person 3 should not depend on internal implementation details from Person 2.

Suggested interface:

detect_candidates(
    ct,
    aorta_mask,
    search_shell,
    spacing,
    ...
) -> list[CandidateBranch]

Then:

analyze_candidates(
    candidates,
    ct,
    aorta_mask,
    spacing,
    image_metadata,
    ...
) -> list[DetectedBranch]

Finally:

write_prediction_json(
    case_id,
    detected_branches,
    image,
    output_path
)

---

# Development Phases

Do not build everything at once.

---

## Phase 1 — Data Inspection

Goal:

correctly load one case.

Implement:

- NIfTI loading
- shape reporting
- spacing reporting
- origin reporting
- direction reporting
- mask statistics
- CT intensity statistics
- basic visualization

Success condition:

we understand the data layout and can visually confirm the aorta mask aligns with the CT.

---

## Phase 2 — Aorta Surface and Search Shell

Implement:

- aortic surface extraction
- physical-distance-aware dilation
- outer search shell

Success condition:

visualize a thin shell surrounding the aortic wall.

---

## Phase 3 — Candidate Detection

Implement:

- vesselness
- adaptive intensity threshold
- connected components
- aorta-contact filtering

Success condition:

candidate regions visually appear near plausible daughter origins.

Do not worry about perfect false-positive control yet.

---

## Phase 4 — Candidate Tracing

Implement:

- centerline / skeleton
- branch persistence
- path length in mm

Success condition:

candidate paths can be followed outward for at least 5 mm.

---

## Phase 5 — Branch Geometry

Implement:

- ostium
- seed
- direction
- radius

Success condition:

one manually inspected case produces plausible geometry.

---

## Phase 6 — Important Case Logic

Implement:

- crop-end filtering
- nearby-origin separation
- common-trunk logic
- daughter-of-daughter filtering
- duplicate suppression

Success condition:

the algorithm follows challenge semantics, not just image connectivity.

---

## Phase 7 — JSON and CLI

Implement:

python run.py \
  --image image.nii.gz \
  --aorta-mask aorta_mask.nii.gz \
  --output prediction.json

Success condition:

the full pipeline runs from terminal without manual input.

---

## Phase 8 — Development-Set Evaluation

Run all available labeled development cases.

Measure:

- number of predicted daughters
- number of reference daughters
- false positives
- false negatives
- ostium distance
- runtime
- memory usage

Inspect failures visually.

Tune thresholds based on aggregate behavior, not one case.

---

## Phase 9 — Augmentation / ML

Only after baseline works:

- geometric augmentation
- intensity augmentation
- crop augmentation
- candidate-level lightweight ML

Do not add complexity unless it improves validation behavior.

---

# First Milestone

The first milestone is NOT:

"perfect branch detection"

The first milestone is:

CT + aorta mask
    ↓
search shell
    ↓
reasonable branch candidates
    ↓
debug visualization

Once this works, tracing and output can be layered on top.

---

# First Codex Task

When starting the project in Codex, do not ask Codex to build the entire system at once.

Start with:

Read AGENTS.md and the challenge PDF.

We are implementing Phase 1 only.

Inspect the repository and available dataset structure.

Create:

- src/preprocessing.py
- src/visualization.py

Implement:

- loading CT NIfTI with SimpleITK
- loading the aorta mask
- verifying image/mask geometry
- extracting NumPy arrays
- reporting dimensions
- spacing
- origin
- direction
- CT intensity statistics
- aorta-mask statistics
- axial/coronal/sagittal visualizations with aorta overlay

Run this on one development case.

Do not implement branch detection yet.

Keep everything CPU-only.

Explain the code after implementation.

---

# Coding Principles

Prefer:

- simple
- modular
- measurable
- debuggable
- CPU-friendly
- deterministic

Avoid:

- hidden assumptions
- giant monolithic functions
- hard-coded case IDs
- hard-coded branch count
- hard-coded anatomical names
- GPU-only libraries
- online dependencies
- premature optimization
- premature ML

Every major stage should be visually inspectable.

---

# Final Submission Requirements

The project should eventually include:

- source code
- dependency/environment file
- README with setup command
- README with run command
- JSON predictions for development cases
- required visual checks
- five-minute demo
- explanation of method
- runtime discussion
- known failure cases

The CLI must work on unseen cases without manual point placement or case-specific edits.

---

# Final Priority Order

When making tradeoffs, prioritize:

1. correct number of direct daughter branches
2. accurate ostium location
3. correct branch identity semantics
4. correct seed and direction
5. reasonable radius
6. runtime
7. polish / frontend

Do not sacrifice core branch detection for a fancy UI.

The most important thing is a reliable CPU-only detector that finds direct aortic branch origins correctly.