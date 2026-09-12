# Combined BranchForge verification

September 12, 2026. Branch: `integration/branchforge-working`.

## What changed

- Merged main (`6eb5161`) into the extension (`7aa8956`) while retaining both
  histories. Existing branches and local scan contents were not rewritten.
- Primary and fallback segmentation now use the same tracer and validation:
  first substantial split / 10 mm limit, supported 5 mm seed, connector checks,
  full smoothed-path coverage/lumen checks, radius limits and deduplication.
- All primary tracing failures reach the retry decision, including empty
  skeletons, missing components, disconnected centerlines and failed connectors.
  The permissive fallback graph is created at most once per case.
- The GUI passes the loaded case ID with `--case-id`, auto-discovers the bundled
  detector and project `.venv`, and preserves valid explicit custom paths.
- `scripts/setup_environment.py` installs the pinned detector environment without
  modifying Slicer's Python. CMake includes the new integration helper.
- Zero-result UI wording now says "No branches detected", not that anatomy has
  been proven absent. Peak memory reporting works on Windows too.
- Current combined instructions are in the root README. The older detailed UI
  and pipeline guides remain available, clearly marked with integration notes.

## Checks actually performed

- **40 pipeline tests passed** in the project's `.venv`, including 6 added
  fallback regressions. The former early-split counterexample is now rejected
  by both paths. Tests also cover recovery from an empty primary graph,
  missing primary components, later bifurcations, gaps, and preserving a valid
  primary result when fallback fails.
- **6 pure-Python extension tests passed**, including custom case arguments and
  automatic environment discovery.
- **Native Slicer UI smoke passed**: layout, synthetic labels, LPS-to-RAS marker
  positions, export, three real study loads, selection, scene reset, error
  handling, invalid output, cancellation and restoring standard Slicer.
  [Full UI report](verification/slicer-ui-report.json).
- **Three actual detector runs through Slicer passed**, not fixture predictions:
  subject001, subject002, subject003. All returned four predictions. The first
  deliberately used `custom_case_001` to prove it no longer depends on the
  folder name. Every rendered origin was compared to the JSON's converted RAS
  position, rows were selected, exported JSON round-tripped exactly, and the
  event loop remained active. [Real integration report](verification/slicer-real-pipeline-report.json).
- **All 25 local scans completed** in fresh detector processes and produced
  schema-valid JSON. [Batch results and per-case measurements](verification/batch-evaluation.json).
  Full local predictions, diagnostics and detector overlays are under ignored
  `outputs/integration/`. Representative predictions and UI captures are bundled below.

Runtime environment: Windows, Python 3.12, the exact versions in
`requirements.txt`, and Slicer 5.12.4. Other work/tests were running on the same
machine during part of the batch; this is not a controlled organizer-hardware
benchmark. Numerical libraries are configured for four threads. Memory values
are each detector process's peak working set, not the combined GUI + OS usage.

Measured mean pipeline time: **21.20 s/case**, slowest **40.62 s**. Mean
wall-clock time including process startup and the first three debug plots:
**28.44 s/case**. Maximum recorded detector working set: **820.14 MB**.

One initial UI smoke attempt was stopped after appearing stalled. Progress
logging and timed stack dumps were added; the completed rerun passed with no
stderr errors. The stack dump during that run caught a slow native volume-load
call, not a detector failure. A diagnostic-console compatibility error in an
intermediate harness attempt was also corrected before the successful runs.
Only disposable test instances were stopped; pre-existing Slicer sessions were
left alone.

## Visual checks and sample outputs

| Subject | Actual pipeline JSON | Slicer visual check |
| --- | --- | --- |
| subject001 | [Prediction](verification/subject001.json) | [Screenshot](verification/subject001.png) |
| subject002 | [Prediction](verification/subject002.json) | [Screenshot](verification/subject002.png) |
| subject003 | [Prediction](verification/subject003.json) | [Screenshot](verification/subject003.png) |

The subject001 screenshot shows the deliberate custom-case-ID GUI test. The
bundled subject001 JSON is the normal batch output with `case_id: subject001`.
It is not the renamed GUI test export. The other outputs and screenshots use
their ordinary case IDs. These are model predictions, not reference annotations.

## Remaining scientific limits (not claimed fixed)

This is a working end-to-end baseline, **not proof of detection accuracy**.
There are no organizer reference annotations in this checkout to measure
precision/recall or coordinate error against. Subjects 017, 019 and 023 returned
zero predictions and should be inspected for misses; the high-count cases
should be checked for duplicate or false origins too. Counts alone are not
ground truth and no expected counts have been hard-coded.

Fallback still retries proposed openings; it does not discover openings that
the first detector missed. Its confidence is heuristic evidence, not a
calibrated probability. A bifurcation before 5 mm is conservatively rejected
because the requested seed cannot be placed before the split; clarify that
edge case and the final minimum-size cutoff with the organizers. The current
radius defaults are engineering choices, not official size rules.

All 25 scans tested were available locally. This merge retains the original
tracked dataset as-is; untracked subject003 and nested duplicate scan files
are not silently added. GUI tests choose the first three available studies so
a checkout does not require that particular untracked subject. External dataset
folders are supported. Native Slicer extension packaging and Linux execution
have not been tested here.
