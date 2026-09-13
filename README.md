# BranchForge: Toralis detector + 3D Slicer workspace

This integration combines the team's CPU-only Python/SimpleITK branch detector
with the redesigned native 3D Slicer extension. The GUI invokes the actual
detector asynchronously; JSON and visual markers use the same prediction.
No web service, GPU, MCP bridge or Slicer rebuild is required for detection.

The **JSON** tab now includes a readable report above the unchanged raw JSON.
Optional **AR** sharing sends visible geometry to a live phone viewer, with a QR
code, life-size anatomical units and expiring links. This opt-in feature requires
internet; it does not change the offline detector. See [the AR setup and platform
guide](docs/AR_VIEWER.md), especially the iPhone Quick Look snapshot limitation.

## Set up (once)

**Fresh Windows laptop?** See the [one-command Windows tutorial](docs/WINDOWS_QUICKSTART.md)
and `scripts/Install-BranchForge.cmd`. This bootstrap installs Slicer and the
detector environment without Git; the tutorial explains publication status,
hardware limits, and loading your first scan.

Install Python 3.12 or 3.13 and 3D Slicer (tested locally: 5.12.4).
From this repository on Windows:

```powershell
py -3.13 scripts/setup_environment.py
```

Use `py -3.12` if you have Python 3.12. On macOS/Linux:
`python3 scripts/setup_environment.py`. Setup creates `.venv` and installs the
pinned dependencies without changing Slicer's bundled Python.
Installation needs internet; detection does not. Offline wheels are described
in [the pipeline guide](PIPELINE_GUIDE.md#offline-setup).

## Open the app

```powershell
powershell -ExecutionPolicy Bypass -File .\slicer-extension\Launch-BranchForge.ps1
```

The workspace automatically finds this checkout's `run.py` and `.venv`
unless you have valid custom pipeline paths saved in Slicer.
If the connection is wrong, expand **Pipeline** and select
`.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (macOS/Linux),
and this repository's `run.py`.

1. Choose a subject from the dataset dropdown, or select a dataset folder.
2. Click **Load study**, then **Run detection**.
3. Select predicted branches to inspect their origins, seeds, arrows and radii.
4. Export the original JSON and save a visual check.

Manual case IDs are passed explicitly to the detector. An empty result means
**no branches detected**, not proof that the scan has no eligible branches.
The synthetic example is fictional and is never passed off as detector output.

For permanent module loading and non-Windows Slicer setup, see
[the Slicer guide](SLICER_GUIDE.md). Keep the detector in a separate Python
environment; do not install its requirements into Slicer.

## Run without the GUI

```powershell
.\.venv\Scripts\python.exe run.py --image "TORALIS CHALLENGE/subject001/orig1.nii" --aorta-mask "TORALIS CHALLENGE/subject001/mask1.nii" --output outputs/subject001/prediction.json
```

On macOS/Linux replace the executable with `.venv/bin/python`.
Supports both `.nii` and `.nii.gz`. Optional `--case-id` overrides the image
folder name. `--diagnostics outputs/subject001/diagnostics.json` saves tracing
decisions and timings.

## Data and Git

This integration retains the extension branch's existing Git LFS scan history.
Install Git LFS and use `git lfs pull` if your checkout contains pointer files.
Do not run ordinary `git add .` to upload untracked duplicate scans.
Dataset discovery uses direct subject folders and ignores nested duplicates.
You can also keep the dataset outside the repository and choose it in the GUI.

The combined branch is `integration/branchforge-working`. It merges both
previously unrelated histories; existing team branches are not rewritten.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s slicer-extension/tests -p test_*.py -v
.\.venv\Scripts\python.exe evaluate.py --dataset "TORALIS CHALLENGE" --output-dir outputs/integration --visualize-cases 3
```

Native GUI tests must run in a **new** Slicer instance with `--testing`,
`--additional-module-paths slicer-extension/BranchForge`, and
`--python-script slicer-extension/tests/slicer_smoke.py` (UI/fixtures) or
`slicer-extension/tests/real_pipeline_smoke.py` (three actual detector runs).
Use absolute paths when launching Slicer. Tests close their own Slicer instance.
They write reports and screenshots under ignored `slicer-extension/artifacts/`.

## Detection safeguards and limits

Primary and fallback segmentation now use the same graph tracing, stop at the
first substantial bifurcation or 10 mm, require a 5 mm supported path, validate
the connection and the full smoothed path, and enforce radius/coverage checks.
Every primary tracing failure reaches the fallback decision. The fallback
skeleton is computed once per case, not once per candidate.

Fallback remains a retry of proposed aortic openings, not a second independent
detector. Missed proposals and false positives remain possible. Scores are
heuristic evidence, not calibrated probabilities. No organizer reference
annotations are available here, so valid JSON and passing tests **do not prove
anatomical accuracy**. A split before 5 mm is conservatively rejected because
the required seed cannot be placed before that split; confirm this edge case
and the final minimum-size rule with the organizers.

## Further context

- [Pipeline method, inspection tools and limits](PIPELINE_GUIDE.md)
- [Detailed Slicer usage and design](SLICER_GUIDE.md)
- [GUI/pipeline interface](slicer-extension/PIPELINE_CONTRACT.md)
- [Challenge specification and sponsor sources](docs/context/README.md)
- [Historical Claude UI handoff](CLAUDE.md) — predates this integration; this README is current.
