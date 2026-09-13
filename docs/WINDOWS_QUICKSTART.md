# BranchForge on a fresh Windows laptop

## Before you start

Use an Intel/AMD 64-bit Windows laptop, preferably Windows 11. This installer
does not support ARM/Snapdragon or 32-bit Windows. Windows 10 may work, but current
Slicer documentation recommends supported Windows versions.

Aim for at least **8 GB RAM and 8 GB free disk space**, plus space for your scans.
That is a practical starting point, not a guarantee every scan fits. A 4 GB laptop
may open the interface but run out of memory on real CT scans. Plug the laptop in,
close games/browser tabs, and keep internet connected during installation.
You do not need Git, VS Code, Node, an MCP server, or a dedicated GPU for detection.
Slicer's 3D view still requires compatible graphics drivers/hardware.

## Install: one paste into Command Prompt

The command downloads the installer from `main`.
The install location remains `%LOCALAPPDATA%\BranchForge`; changing the GitHub
branch does not move scans or installed files. Releases are stored by commit SHA,
and rerunning setup updates the desktop shortcut while retaining older releases.
For stronger release reproducibility, replace the branch in the URL with a reviewed commit SHA
and pass the same SHA as `-Ref` to the script.

1. Press the Windows key, type **cmd**, and open **Command Prompt** normally.
   Do not choose Run as administrator.
2. Copy this entire line, paste it, and press Enter:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $p=Join-Path $env:TEMP ('Install-BranchForge-'+[guid]::NewGuid()+'.ps1'); Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/Toastyybread1/toralis-challenge/main/scripts/Install-BranchForge.ps1' -OutFile $p; & $p"
```

This downloads and executes the team's installer: only run it if you trust the
repository. ExecutionPolicy Bypass applies to this PowerShell process; it does
not permanently change the computer's policy. Do not disable antivirus or
organization security controls to get around a block.

The script downloads application code **without the large medical dataset**,
installs/reuses Slicer **5.12.4** and standard per-user Python **3.12**, installs
the detector's pinned packages and CPU PyTorch in its own `.venv`, includes and
verifies ten supplied model checkpoints, checks package imports,
creates a **BranchForge** desktop shortcut, and opens the extension.
It checks Slicer's published SHA512 and Python's publisher signature before
executing installers. It does not install detector packages into Slicer's Python.

Allow several minutes, potentially much longer on slow internet. Some installer
stages do not show a progress bar. Keep the command window open. Windows or an
organization policy may require approval; completely unattended installation is
not guaranteed. If setup says a restart is required, restart and rerun it.

### Alternative: send two files directly

Alternatively, send **Install-BranchForge.cmd** and
**Install-BranchForge.ps1** from `scripts/` together. Save both in the same folder
and double-click the `.cmd` file. They still need internet for the application,
Slicer, Python and dependencies. No GitHub account is needed for the public repo.

## First launch: see something on screen

Once BranchForge opens, click **Explore synthetic example**. This generates
fictional anatomy and example branch markers so you can try the interface.
**It is not a real scan or a demonstration of detector accuracy.**

Next time, simply double-click **BranchForge** on the desktop. Opening the normal
Slicer shortcut does not necessarily load this extension; use our shortcut.

## Run a real scan

Obtain the challenge dataset from the team/organizer separately and unzip it.
You need both the CT and its matching parent-aorta mask. Do not upload identifiable
patient scans to public services.

Example folder:

```text
TORALIS CHALLENGE/
  subject001/
    orig1.nii       CT scan
    mask1.nii       matching aorta mask
```

1. In BranchForge, use the folder button to select the dataset folder containing
   the subject folders. Choose a subject. Alternatively, browse to the CT and mask
   separately. Both `.nii` and `.nii.gz` are supported.
2. Click **Load study** and wait for the scan to appear.
3. Check the Detect panel shows a connected pipeline. For development subjects
   019-023 select the matching **held-out models** option; otherwise use **Unseen
   study - all models**. Then click **Run detection**.
4. Inspect the predicted branches in 3D and the readable report/raw JSON.
   Empty predictions mean no branches were detected, not proof none exist.

No manual extension installation through Extension Manager is needed. The shortcut
supplies the module directory and startup script automatically.

## Common problems

| Problem | What to do |
| --- | --- |
| Download fails, GitHub 403/rate limit, or internet drops | Keep the error/log. Retry later on a working network. Completed verified source downloads can be reused. |
| Setup stops on a package error | Send the log to the team. Do not substitute random package versions or install them inside Slicer. |
| Slicer opens without BranchForge | Use the **BranchForge** desktop shortcut, not the normal Slicer shortcut. |
| Pipeline paths are missing/wrong | Expand **Connect your team's run.py**. Use the two paths printed at the end of setup: this release's `.venv\Scripts\python.exe` and `run.py`. Existing valid custom Slicer settings can override automatic discovery. |
| No subjects appear | Dataset is not bundled. Select the unzipped folder that directly contains the subject folders, or select the two image files manually. |
| Scan file is tiny or unreadable | It may be a Git LFS pointer rather than a real scan. Obtain the actual dataset from the organizer/team. |
| Black 3D view, graphics error, or crash | Update the laptop manufacturer's graphics driver. CPU-only detection does not eliminate Slicer's graphics requirements. |
| Laptop freezes or runs out of RAM | Close other applications and load one study. Try the synthetic example first. A larger-memory computer may be necessary. |
| Security policy blocks execution | Ask the device administrator; do not disable security tools. |

Logs are saved in `%TEMP%\BranchForge-setup-*.log`. Send the most recent one to
the team when asking for help. Application releases live in
`%LOCALAPPDATA%\BranchForge\releases\<commit>`; cached installers are under
`%LOCALAPPDATA%\BranchForge\downloads`.

Rerunning setup resolves the selected branch again. A new commit gets a separate
release directory/environment; existing release files and scans are not deleted.
The desktop shortcut is updated only after successful dependency checks. Old
releases can consume disk space. This is an installation copy, not a Git checkout.
The installer includes inference weights, but does not configure AR publishing credentials or upload scans.
Offline detection works after setup; optional phone/AR sharing needs separate setup.

## Verification status

Checked on the development machine: Windows PowerShell 5.1 parsing, Git blob
integrity helper against `git hash-object --no-filters`, GitHub revision/tree
availability, official Slicer/Python download responses, and compatible Windows
wheel availability for all six pinned dependencies (SimpleITK uses a compatible
CPython stable-ABI wheel). The combined detector additionally passed the local CPU model/GUI checks documented
in [master integration verification](MASTER_INTEGRATION.md). No fresh-machine
installation was performed.

The installer must be tested on a clean Windows laptop/VM before calling it a
fully verified one-click release. Syntax/helper checks on the development machine
do not prove fresh-machine installation, graphics compatibility, or real-scan
performance. Do not promise a specific install time or accuracy score.

Official prerequisites and downloads:
[Slicer requirements](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html),
[Slicer download/checksums](https://download.slicer.org/),
[Python 3.12.10](https://www.python.org/downloads/release/python-31210/).
