# BranchForge
Discover where smaller arteries leave the aorta, then inspect the results in a purpose-built 3D Slicer workspace.

## Install on Windows
On a Windows x64 laptop with internet access, open **Command Prompt** and paste this command:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $p=Join-Path $env:TEMP ('Install-BranchForge-'+[guid]::NewGuid()+'.ps1'); Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/Toastyybread1/toralis-challenge/main/scripts/Install-BranchForge.ps1' -OutFile $p; & $p"
```

It installs Slicer, an isolated Python environment and the supplied CPU models, then creates a desktop shortcut—no Git, GPU or training required.
Open BranchForge, choose your CT and matching aorta mask, click **Load study**, then **Run detection**; scans are supplied separately.
For development subjects 019–023, select that subject’s **held-out models** in Detect; see [Windows help](docs/WINDOWS_QUICKSTART.md) or [macOS/source setup](SLICER_GUIDE.md) if needed.

## Terminal only — no Slicer required

The same detector runs from the command line on CPU; the GUI is optional. Download the [main source ZIP](https://github.com/Toastyybread1/toralis-challenge/archive/refs/heads/main.zip), extract it, and open a terminal in the folder containing `run.py`.

**One-time setup** (Python 3.12 or 3.13, internet required):

```cmd
python scripts/setup_environment.py
```

**One-line run on Windows** (replace the input filenames):

```cmd
.venv\Scripts\python.exe run.py --image "image.nii.gz" --aorta-mask "aorta_mask.nii.gz" --output "prediction.json"
```

On macOS/Linux use `.venv/bin/python` instead. With the environment activated, this is the PDF’s exact `python run.py --image ... --aorta-mask ... --output ...` interface; it runs offline after setup with the included models. For development subjects 019–023, add the matching flag, e.g. `--held-out-case 21`; omit it for unseen cases.

## What you can do

- **Explore:** linked 3D/CT views with selectable branch openings, seeds, directions, estimated radii and traces.
- **Understand:** readable results first, unchanged challenge JSON underneath.
- **Export:** JSON, screenshots and **Export edited .nii**. NIfTI labels: **0 background / 1 edited aorta / 2 estimated traces outside it**. Preserves the CT grid; not a modified CT or full vessel segmentation. [Export details](docs/NIFTI_EXPORT.md)
- **Share in AR:** optional QR sharing at anatomical scale on compatible phones; publisher setup required. iPhone AR must be reopened for updates. [Setup and privacy](docs/AR_VIEWER.md)

## How the algorithm works—and why

1. **Load CT + aorta mask.** SimpleITK preserves physical geometry so measurements remain meaningful across voxel sizes.
2. **Adapt to contrast.** Compare inside/outside intensities, then grow connected blood-like regions. Distance and spill limits constrain leakage into nearby tissue.
3. **Propose curved paths.** Wall-contact sampling, skeleton graphs and local searches find candidate branch openings and routes.
4. **Cross-check.** Perpendicular CT sections, small CPU 3D neural networks and graph checks assess lumen support and direct connection, then group duplicate openings. Independent evidence helps reject false branches.
5. **Measure.** Return eligible openings, seeds 5 mm along each path, local radii and directions—usable starting points for downstream tracking, without assuming a fixed branch count.

## Why 3D Slicer?
Our teammate used Slicer during a hospital internship. Extensions let us redesign its UI while reusing medical-image loading, segmentation and linked views. Researchers can check predictions against the CT, not just trust a number.

## Results and limits
The final development export matched **17 of 19 draft origins**, with two misses and one false positive: **94.4% precision, 89.5% recall, 91.9% F1** at a 3 mm matching tolerance. These five cases also informed development; this is **not independent clinical validation**. Inference runs locally on CPU after setup; AR sharing is optional and online. Research prototype only.

[Three-minute pitch + demo cues](docs/PITCH_SCRIPT.md) · [Method details](docs/PIPELINE.md) · [CLI/output guide](docs/CHALLENGE_RUN.md) · [Integration and verification](docs/MASTER_INTEGRATION.md)
