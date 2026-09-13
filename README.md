# BranchForge: combined CPU detector and 3D Slicer extension

The final `master` branch combines `nika-setup` (7296590) with
`integration/branchforge-working` (7bd3549). The original branches are preserved.
The GUI invokes the new detector asynchronously, displays the unchanged challenge
JSON plus readable results, and joins review sidecars by ID to show actual
estimated centerline paths. Those traces are not segmented vessel walls.

## Windows: install and open

See the [one-command Windows tutorial](docs/WINDOWS_QUICKSTART.md).
The installer includes Slicer, an isolated Python environment, CPU PyTorch and
the ten supplied small model checkpoints. No training, Git, GPU toolkit, MCP
server or private scan download is required. Real CT/mask inputs are separate.

From a source checkout, use Python 3.12 or 3.13:

```powershell
python scripts/setup_environment.py
powershell -NoProfile -ExecutionPolicy Bypass -File slicer-extension/Launch-BranchForge.ps1
```

Never install detector dependencies into Slicer's bundled Python.
On macOS use a Python architecture matching the Slicer process; Windows uses x64.
See [Slicer setup](SLICER_GUIDE.md) for additional module paths and startup script.

## Load and detect

1. Choose the dataset folder or browse to a CT and matching parent-aorta mask.
2. Click **Load study**.
3. In Detect, select **Unseen study - all models** for genuinely new cases.
   For development subjects 019-023 select the matching **held-out models** option.
   The case ID alone does not choose a fold.
4. Click **Run detection**. Inspect origins, seeds, direction arrows, estimated
   paths, radius rings, readable report and raw JSON.

The **Explore synthetic example** button uses fictional reference geometry,
not detector results. Empty predictions do not establish that no branches exist.
The layer toggle for direction arrows also controls estimated centerlines.

## CLI and saved outputs

```powershell
.\.venv\Scripts\python.exe run.py --image "CT.nii.gz" --aorta-mask "aorta.nii.gz" --output "outputs/new-study/prediction.json" --case-id new-study
```

For development subject 21 add `--held-out-case 21`.
`--no-neural` is an explicitly different diagnostic mode, not the evaluated
AI-assisted configuration. Unsupported spacing is reported as lacking model evidence.

For output `X/prediction.json`, keep `X/diagnostics/prediction.json` and
`X/prediction_review/` with it to retain paths and provenance.
JSON alone can be imported as markers without fabricating centerlines.
Wait for successful process completion, not just JSON-file creation.
The GUI exports the original challenge JSON. Its temporary run files are cleaned
after import; in-memory paths remain visible. Use the CLI with a persistent output
folder when you also need to retain the full review sidecars and analysis masks.

Coordinates are physical LPS millimetres. Only the rendering adapter converts
to Slicer RAS (-x, -y, z); JSON and radii are unchanged.
The 2 mm origin-diameter eligibility filter is separate from radius at the 5 mm seed.

## Models and data

The ten supplied 76 KB checkpoints and two training manifests are tracked explicitly.
Checksums/provenance: [config/models-manifest.json](config/models-manifest.json).
Verify with `python scripts/verify_models.py`. Checkpoints load using
`weights_only=True` on CPU; held-out training exclusions are checked.
Do not replace them with freshly trained or random weights.

Raw scans, handoff ZIPs, reference labels, probability volumes and local review
results are not added by this integration. Historical Git LFS scan files remain
in the existing repository history; use organizer/team data or Git LFS as needed.
Only development prediction JSONs already published by the detector branch are
included under `outputs/predictions/`.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s slicer-extension/tests -p test_*.py -v
```

See [master integration verification](docs/MASTER_INTEGRATION.md) for the measured
local results and native Slicer smoke test. Passing tests are not anatomical validation.

The teammate's development export reports 17/19 draft matches, one unmatched
prediction and two misses on five tuned development cases at a 3 mm tolerance:
94.4% precision, 89.5% recall, 91.9% F1. This is not hidden-test accuracy or
accuracy across all 25 cases. Other cases lack reference comparisons.
Graph-review budget limits and uncertain paths remain documented in
[the detector method](docs/PIPELINE.md) and [challenge run guide](docs/CHALLENGE_RUN.md).

## Preserved features and earlier implementation

The existing GUI, readable JSON, opt-in phone/AR sharing and its platform
limitations remain: [AR guide](docs/AR_VIEWER.md). AR needs internet and separate
publisher configuration; ordinary inference stays offline after setup.

The original classical implementation is preserved as `run_legacy.py` and its
`src/pipeline.py` modules. `evaluate.py` remains the legacy batch evaluator;
it is not the benchmark for the new detector.
Existing inspection utilities and tests are retained. Older guides such as
`PIPELINE_GUIDE.md`, `docs/INTEGRATION_STATUS.md` and `CLAUDE.md` describe
the earlier implementation; this README is the current entry point.
The offline teammate gallery requires separately supplied saved results; its
launcher does not regenerate missing data.
