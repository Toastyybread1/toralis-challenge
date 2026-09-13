# Master integration verification - 2026-09-13

Combined branches: integration/branchforge-working (7bd3549) and nika-setup
(7296590). Both original branch tips are preserved. Master is a merge commit,
not a rewrite of either branch. No models were retrained.

## Included and preserved

- Nika's current CPU detector, geometry loader, review pipeline, tests and the
  25 already-published development prediction JSONs.
- BranchForge's native Slicer GUI, readable/raw JSON, existing optional AR viewer,
  launch scripts and Windows setup tutorial.
- Ten supplied 76,443-byte checkpoints and two training manifests, with hashes
  in config/models-manifest.json. Binary-safe Git attributes preserve hashes.
- Actual estimated paths joined through export audit IDs, not list order.
  Path status/stop reason remain visible; traces are not vessel segmentations.
- Explicit held-out model selection for development subjects 019-023.
- Legacy CLI preserved in run_legacy.py with its original source modules,
  inspection utilities and tests. evaluate.py remains the legacy evaluator.

Local handoff ZIPs, original scans, reference labels, derived scan volumes,
private AR settings and scratch files are not added by this integration.
Historical tracked Git LFS scans remain unchanged in repository history.

## Targeted fixes

- Resolve merge conflicts without discarding either UI or detector implementation.
- Accept a no-proposals result as empty only when no retained groups exist;
  missing requested neural evidence remains an error.
- Reject output paths that would overwrite CT/mask inputs.
- Resolve model paths relative to the repository, not the caller's directory.
- Keep pure JSON unchanged; validate optional path sidecars against IDs,
  coordinates, radii, path extent and the 5 mm seed before rendering.
- Copy gzip files misleadingly named .nii to private temporary .nii.gz display
  files. Slicer can load these; original image bytes remain unchanged.
- Bundle model verification and CPU-only PyTorch in Windows setup; master is
  the bootstrap's default branch. No fresh-machine install was performed.

## Checks performed on this PC

Environment: Windows x64, CPython 3.12.14 external .venv, PyTorch 2.11.0+cpu,
Slicer 5.12.4. CPU checkpoint loading uses weights_only=True and strict state
dictionary validation, with held-out training-case checks.

| Check | Result |
| --- | --- |
| Supplied ZIP and all 53 artifact SHA256 values | Verified; only inference weights/manifests installed for publication |
| Ten checkpoint structures and training exclusions | Passed |
| Existing combined detector/legacy tests | 165 passed |
| New CLI integration regressions | 2 passed |
| Extension contract/path/input-file tests | 13 passed |
| Python compilation and pip dependency check | Passed |
| Windows PowerShell 5.1 bootstrap parsing | Passed |
| Subject 21 CLI, held-out pair 21 | Four daughters, exact JSON match to committed development output |
| Subject 21 native GUI subprocess | Four daughters, four mapped paths, RAS markers and JSON roundtrip verified |
| Subject 24 CLI | Completed paired resampling; zero exported daughters |

Native GUI evidence: [master-slicer-report.json](verification/master-slicer-report.json).
The successful foreground run took about 38.7 seconds including UI verification
and screenshot. One earlier background GUI run completed around 318.8 seconds
and exceeded the original smoke-test timeout; its cause is not established.
Subject-21 standalone inference measured 35.3 seconds; subject-24 inference
measured 69.7 seconds during this development session. These runs do not establish
the challenge's runtime target on organizer hardware. Performance needs profiling
on a controlled machine and representative scan set.

The initial native loading failure on misleading .nii extensions was reproduced,
fixed and covered by two tests; the successful native run uses those same inputs.

## Reproduce the GUI test

Supply the teammate's subject021_smoke_inputs.zip under the project's
codex check this folder and extract its data tree to tmp/integration-handoff.
Start a NEW Slicer instance with the BranchForge module directory and
slicer-extension/tests/master_smoke.py as --python-script. Keep the window
foregrounded. The test writes local artifacts under slicer-extension/artifacts/master
and leaves its successful real-study window open. Never run this script in an
existing user scene. Its 600-second timeout is diagnostic, not a runtime target.

## Remaining limitations

The teammate's 91.9% development F1 applies to five tuned, draft-labelled cases,
not hidden-test accuracy or all 25 cases. The integration checks reproduction and
display correctness; it does not establish anatomical accuracy. Graph budget
skips, uncertain traces, missed candidates and case-24 zero detections remain.
No model-free run inherits the neural model's reported score.

The original AR implementation is preserved, not newly verified on physical phones
in this merge. New visible centerline models use the existing owned-geometry export
path. AR credentials are separate and are never bundled by the installer.

GUI export remains pure challenge JSON. Review sidecars are loaded into memory
before temporary run cleanup; use the CLI with a persistent output folder to keep
full review masks and path files for later inspection.
