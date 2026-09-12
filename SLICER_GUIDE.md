# BranchForge

> Historical UI guide, retained from the extension branch. The detector is now
> bundled and auto-discovered; use [README.md](README.md) for current setup and
> [integration status](docs/INTEGRATION_STATUS.md) for verified results.

A dedicated 3D Slicer workspace for the Toralis Labs branch discovery challenge.
Load a CT and parent-aorta mask, explore the anatomy, and inspect the detector's
branch origins, seeds, directions, radius estimates and JSON output.

For the design brief and project context, read [CLAUDE.md](CLAUDE.md). It covers
the full challenge requirements, Toralis's background, the implementation, and
team responsibilities. Original documents and visual baselines are in
[docs/context](docs/context/README.md).

## Start the GUI on Windows

Requires **3D Slicer 5.8 or newer** (developed and verified on 5.12.4). No
compilation or additional Python packages are needed for the GUI.

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\slicer-extension\Launch-BranchForge.ps1
```

This starts a separate Slicer window, opens the BranchForge workspace and loads
the first local study. If Slicer is installed somewhere other than the default
location, add `-SlicerPath "C:\path\to\Slicer.exe"`. The execution-policy
argument applies only to that launcher process.

To add the module to an existing Slicer installation instead:

1. Open **Edit > Application Settings > Modules**.
2. Add this repository's `slicer-extension/BranchForge` directory to **Additional module paths**.
3. Restart Slicer and select **Vascular Modeling > BranchForge**.

On macOS/Linux, launch Slicer with:

```bash
/path/to/Slicer --additional-module-paths /path/to/toralis-challenge/slicer-extension/BranchForge --python-script /path/to/toralis-challenge/slicer-extension/scripts/launch.py
```

## The workspace

The workspace replaces Slicer's generic chrome with a purpose-built layout:

- **Header**: the BranchForge mark, a live **Load / Detect / Explore** rail that
  ticks off each stage, a case chip naming the active study (or flagging the
  synthetic example), quick actions for fit / layout / capture, and
  **Back to Slicer**.
- **Left panel**: a three-step segmented control, **Study**, **Detect** and
  **Display**, each a scrollable set of cards.
- **Centre**: the 3D anatomy above three CT planes. Each plane has a compact
  header with its orientation and the live slice position in millimetres.
- **Right panel**: results. A branch count, the source of the results, then
  **Branches**, **Details** and **JSON** views with export actions below.

### 1. Study

Pick one of the local subjects from the dropdown (the 25-case catalog is found
automatically), or open **Choose files manually** to browse for a CT, a mask and
a case ID. Click **Load study**. The active-study card shows the case, voxel
dimensions, spacing and file names. Changing the dropdown or fields only changes
the *pending* choice; nothing is reassigned until you click Load study.

### 2. Detect

The pipeline card shows whether a detector is connected. Open **Connect your
team's run.py**, choose the team's Python executable and `run.py`, and the pill
turns green. **Run detection** launches it in a separate process with an
animated activity bar and elapsed timer; the viewer stays interactive and
**Cancel** is always available. **Import prediction JSON** visualises a saved
`prediction.json` without running anything. The status banner explains every
outcome: success, failure (with a **View pipeline log** link), cancellation, an
empty-but-valid result, or a rejected file. Short toast notifications confirm
actions over the 3D view.

### 3. Explore

Click a branch row to inspect it. Its arrow and radius ring pulse in the 3D
view, the other branches dim, and the three CT planes centre on its origin.
**Details** shows the origin and seed in LPS millimetres, the unit direction with
an axial compass (radiological orientation) plus a superior/inferior gauge, the
radius at the seed, and the straight-line origin-to-seed distance. Double-click a
row or press **Fly to branch** to glide the camera onto the origin. **N** and
**P** step through branches.

**Display** offers animated switches for the aorta, origins/seeds, arrows,
radius rings and labels, an aorta opacity slider, CT window presets (vessels,
soft tissue, bone), **Fit anatomy** and a **3D only / 3D + slices** toggle.

Keyboard shortcuts while the workspace is open: **F** fit, **L** layout,
**1 / 2 / 3** panel pages, **N / P** next / previous branch, **Ctrl+E** export,
**Ctrl+I** import, **Ctrl+Shift+S** save a visual check.

**Export prediction JSON** preserves the supplied numerical values and physical
coordinates. **Copy JSON** and **Copy branch** put the same data on the
clipboard. **Save visual check** captures the workspace as a PNG for the
challenge's required three-case verification.

**Explore synthetic example** generates a fictional CT, aorta and four reference
branches locally. It is visibly labelled as synthetic in the header, the results
panel and the study card, its case ID is `synthetic_demo`, and detection is
disabled. It is a GUI demonstration, not a detector, prediction, benchmark or
evaluation result. Loading a real study clears all synthetic geometry and results.

**Back to Slicer** restores the previous Slicer toolbars, menu, style, view
settings and layout. The extension only removes its own study/result nodes when
switching cases.

## Team integration

The detection team owns the algorithm. The GUI launches exactly this interface:

```bash
python run.py --image /path/to/orig.nii --aorta-mask /path/to/mask.nii --output /path/to/prediction.json
```

The script runs in a separate process, with its own Python environment and its
working directory set to the script's directory. Install pipeline dependencies
in that environment. The GUI does not install them or require the pipeline to
import Slicer. Exit with code 0 after writing valid JSON; failures show the log.

See [the integration contract](slicer-extension/PIPELINE_CONTRACT.md) for the
schema, coordinate handling and division of work. The production detection
`run.py` is intentionally left for the detection team; no pretend detector is
included.

## Repository layout

```text
slicer-extension/
  BranchForge/             Python scripted Slicer module and visual assets
    BranchForgeLib/        JSON contract, rendering adapter, synthetic example, UI kit
    Resources/             Stylesheet and SVG icon set
  scripts/launch.py        Starts the module inside Slicer
  Launch-BranchForge.ps1   Windows launcher
  tests/                   Contract and Slicer integration checks
  PIPELINE_CONTRACT.md     Handoff to the detection team
TORALIS CHALLENGE/         Existing dataset; managed by the team with Git LFS
```

`BranchForgeLib/ui.py` holds the design tokens, tinted icons, painted controls
(segmented tabs, toggle switches, workflow rail, direction compass, slice
headers, toasts, press ripples) and the animation helpers. Everything in it is
cosmetic; data and coordinates never pass through it.

The CMake files support normal Slicer extension packaging. Local development
works directly through the module path without building Slicer.

## Development checks

Run the pure Python data-contract tests:

```bash
python -m unittest discover -s slicer-extension/tests -p test_contract.py -v
```

For visual and MRML integration checks, start a **separate test Slicer instance**:

```powershell
& 'C:\path\to\Slicer.exe' --testing --no-splash --ignore-slicerrc --additional-module-paths "$PWD\slicer-extension\BranchForge" --python-script "$PWD\slicer-extension\tests\slicer_smoke.py"
```

This test loads the synthetic example and three supplied CT/mask pairs, checks
coordinate conversion and export, exercises selection, camera fly-to, layout
switching, pipeline fixtures, cancellation and scene close, captures screenshots,
and exits. Test outputs are kept in the ignored `slicer-extension/artifacts/qa`
directory. The real-case screenshots demonstrate loading only; scored visual
checks still need the team's actual branch predictions.

To eyeball the interface after a change, `tests/visual_tour.py` opens a normal
interactive window, walks through every page and tab, saves screenshots under
`slicer-extension/artifacts/qa/tour`, and leaves the app open:

```powershell
& 'C:\path\to\Slicer.exe' --no-splash --additional-module-paths "$PWD\slicer-extension\BranchForge" --python-script "$PWD\slicer-extension\tests\visual_tour.py"
```

## Scope and attribution

This is an interface prototype for the challenge. Aorta geometry comes from the
provided mask. Branch overlays represent the imported JSON; they do not imply a
full daughter-vessel segmentation. Radius rings represent local estimates, and
arrow lengths are illustrative. The direction compass and the straight-line
origin-to-seed distance are computed only from the JSON fields. No confidence or
accuracy scores are invented.

Built with [3D Slicer](https://www.slicer.org/), Qt/PythonQt, VTK and NumPy.
Coordinates follow [Slicer's documented RAS/LPS conventions](https://slicer.readthedocs.io/en/latest/user_guide/coordinate_systems.html).
The extension is independently authored; Slicer itself is not copied or
redistributed in this repository. MCP-Slicer is optional for assisted development
and is not required to use the extension.
